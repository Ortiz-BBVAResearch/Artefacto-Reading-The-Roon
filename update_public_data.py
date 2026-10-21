"""Refresh the public series of the explorer's data.json: current growth, NFCI, funds rate,
VIX, oil, geopolitical risk and economic policy uncertainty. Nothing is estimated: the
model's distributions, Hidden Dissent and the SPF are left untouched (they come from the
replication pipeline and the Tsang-Yang data site). Run: python update_public_data.py data.json
"""
import io, json, sys, datetime as dt
import pandas as pd, requests

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
GPR  = "https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls"
FREDMD = "https://files.stlouisfed.org/files/htdocs/fred-md/monthly/current.csv"
EPU  = "https://www.policyuncertainty.com/media/US_Policy_Uncertainty_Data.xlsx"
FIRST = "1994Q2"   # first origin used for the expanding standardization of the external measures

def fred(sid):
    r = requests.get(FRED.format(sid=sid), timeout=60); r.raise_for_status()
    s = pd.read_csv(io.StringIO(r.text), na_values=".")
    s.columns = ["date", "v"]; s["date"] = pd.to_datetime(s["date"]); return s.dropna().set_index("date")["v"]

def qmean(s):   # quarterly mean, label "YYYYQn"
    q = s.resample("QE").mean().dropna(); return {f"{d.year}Q{(d.month-1)//3+1}": float(v) for d, v in q.items()}

def qlast(s):
    q = s.resample("QE").last().dropna(); return {f"{d.year}Q{(d.month-1)//3+1}": float(v) for d, v in q.items()}

def growth_annualised(gdp):
    g = 100 * ((gdp / gdp.shift(1)) ** 4 - 1); return {f"{d.year}Q{(d.month-1)//3+1}": round(float(v), 1) for d, v in g.dropna().items()}

GPR_MONTHLY = {}; EPU_MONTHLY = {}
def gpr_quarterly():
    r = requests.get(GPR, timeout=60); r.raise_for_status()
    df = pd.read_excel(io.BytesIO(r.content))
    col = [c for c in df.columns if str(c).upper() == "GPR"][0]
    df["date"] = pd.to_datetime(df["month"]); GPR_MONTHLY["gpr"] = mmean(df.set_index("date")[col]); return qmean(df.set_index("date")[col])

def epu_quarterly():
    r = requests.get(EPU, timeout=60); r.raise_for_status()
    df = pd.read_excel(io.BytesIO(r.content)).dropna(subset=["Year", "Month"])
    df["date"] = pd.to_datetime(dict(year=df["Year"].astype(int), month=df["Month"].astype(int), day=1))
    col = [c for c in df.columns if "Three" in str(c) or "News" in str(c)][0]
    EPU_MONTHLY["epu"] = mmean(df.set_index("date")[col]); return qmean(df.set_index("date")[col])

SPF_GROWTH = "https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/survey-of-professional-forecasters/data-files/median/medianGrowth.xlsx"
def spf_growth_consensus():
    """SPF median real GDP growth, averaged over the four quarters after the survey quarter (horizons 2-5), as in Table 1 of the paper."""
    r = requests.get(SPF_GROWTH, timeout=60); r.raise_for_status()
    x = pd.read_excel(io.BytesIO(r.content), sheet_name=None)
    sh = [k for k in x if str(k).upper().startswith("RGDP")]; df = x[sh[0]] if sh else list(x.values())[0]
    cols = [c for c in df.columns if str(c).upper() in ("DRGDP2", "DRGDP3", "DRGDP4", "DRGDP5")]
    df = df.dropna(subset=["YEAR", "QUARTER"])
    out = {}
    for _, row in df.iterrows():
        v = [row[c] for c in cols if pd.notna(row[c])]
        if len(v) == 4: out[f"{int(row['YEAR'])}Q{int(row['QUARTER'])}"] = round(float(sum(v) / 4), 2)
    return out

def yoy_quarterly(s):  # monthly price index -> quarterly mean -> % change on a year earlier
    q = s.resample("QE").mean().dropna(); y = 100 * (q / q.shift(4) - 1)
    return {f"{d.year}Q{(d.month-1)//3+1}": round(float(v), 2) for d, v in y.dropna().items()}

def fredmd_groups():
    """Download the current FRED-MD vintage, apply its transformation codes, aggregate to quarters,
    and summarize each of the four groups of the paper's panel by its first principal component
    (standardized over 2007Q4 onward, sign anchored so that higher = stronger activity, higher
    inflation, higher long rates, higher equity prices). Descriptive only: the model uses the 123 series."""
    import numpy as np, os
    r = requests.get(FREDMD, timeout=120); r.raise_for_status()
    raw = pd.read_csv(io.StringIO(r.text))
    codes = raw.iloc[0, 1:].astype(float); df = raw.iloc[1:].copy()
    df["date"] = pd.to_datetime(df.iloc[:, 0]); df = df.set_index("date").drop(columns=raw.columns[0]).astype(float)
    fam = json.load(open(os.path.join(os.path.dirname(__file__), "family_map.json")))
    def tr(x, c):
        c = int(c)
        if c == 1: return x
        if c == 2: return x.diff()
        if c == 3: return x.diff().diff()
        if c == 4: return np.log(x)
        if c == 5: return np.log(x).diff()
        if c == 6: return np.log(x).diff().diff()
        if c == 7: return x.pct_change().diff()
        return x
    T = pd.DataFrame({c: tr(df[c], codes[c]) for c in df.columns if c in fam})
    M = T[T.index >= "2007-10-01"].copy()
    Q = T.resample("QE").mean(); Q = Q[Q.index >= "2007-10-01"]
    # drop the last quarter if its last month is missing
    lastm = df.index.max(); qend = Q.index.max()
    if lastm.month % 3 != 0: Q = Q.iloc[:-1]
    out = []; anchors = {"REAL": "INDPRO", "MARKETS": "S&P 500", "NOMINAL": "CPIAUCSL", "CREDIT_RATES": "GS10"}
    res = {}
    for F in ["REAL", "NOMINAL", "CREDIT_RATES", "MARKETS"]:
        cols = [c for c in Q.columns if fam.get(c) == F]
        X = Q[cols].copy(); X = X.fillna(X.mean())
        Z = (X - X.mean()) / X.std(ddof=0); Z = Z.fillna(0.0)
        U, S, Vt = np.linalg.svd(Z.values, full_matrices=False); pc = Z.values @ Vt[0]; share = float(S[0]**2 / (S**2).sum())
        a = Q[anchors[F]].values if anchors[F] in Q else Z.values[:, 0]
        m = ~np.isnan(a)
        if np.corrcoef(pc[m], a[m])[0, 1] < 0: pc = -pc
        pc = (pc - pc.mean()) / pc.std()
        res[F] = (pc, share)
    for i, d in enumerate(Q.index):
        rec = {"o": f"{d.year}Q{(d.month-1)//3+1}"}
        for F, (pc, share) in res.items(): rec[F] = round(float(pc[i]), 3); rec[F + "_share"] = round(share, 3)
        out.append(rec)
    # monthly version of the same summaries (same method on the monthly transformed panel)
    outm = []; resm = {}
    for F in ["REAL", "NOMINAL", "CREDIT_RATES", "MARKETS"]:
        cols = [c for c in M.columns if fam.get(c) == F]
        X = M[cols].copy(); X = X.fillna(X.mean())
        Z = (X - X.mean()) / X.std(ddof=0); Z = Z.fillna(0.0)
        U, S, Vt = np.linalg.svd(Z.values, full_matrices=False); pc = Z.values @ Vt[0]
        a = M[anchors[F]].values if anchors[F] in M else Z.values[:, 0]; m = ~np.isnan(a)
        if np.corrcoef(pc[m], a[m])[0, 1] < 0: pc = -pc
        resm[F] = (pc - pc.mean()) / pc.std()
    for i, d in enumerate(M.index):
        rec = {"m": d.strftime("%Y-%m")}
        for F, pc in resm.items(): rec[F] = round(float(pc[i]), 3)
        outm.append(rec)
    return out, str(raw.columns[0]), outm


def mmean(s):  # monthly mean, label "YYYY-MM"
    m = s.resample("ME").mean().dropna(); return {d.strftime("%Y-%m"): round(float(v), 4) for d, v in m.items()}

def yoy_monthly(s):
    m = s.resample("ME").mean().dropna(); y = 100 * (m / m.shift(12) - 1)
    return {d.strftime("%Y-%m"): round(float(v), 2) for d, v in y.dropna().items()}

def monthly_block(data, nfci_s, ff_s, vix_s, oil_s, pce_s, core_s, gpr_m, epu_m, groups_m):
    """data['monthly'] = {'series': [{m, nfci, ff, vix, oil, gpr, epu, pce_yoy, corepce_yoy}], 'groups': [{m, REAL, ...}]} from 2007-10."""
    cols = {"nfci": mmean(nfci_s), "ff": mmean(ff_s), "vix": mmean(vix_s), "oil": mmean(oil_s), "pce_yoy": yoy_monthly(pce_s), "corepce_yoy": yoy_monthly(core_s), "gpr": gpr_m or {}, "epu": epu_m or {}}
    keys = sorted(k for c in cols.values() for k in c if k >= "2007-10")
    rows = []
    for k in sorted(set(keys)):
        row = {"m": k}
        for name, c in cols.items():
            if k in c: row[name] = c[k]
        rows.append(row)
    data["monthly"] = {"series": rows, "groups": groups_m or []}

def expanding_z(series_dict, first=FIRST):
    keys = sorted(k for k in series_dict if k >= first); out = {}
    vals = []
    for k in keys:
        vals.append(series_dict[k]); s = pd.Series(vals)
        out[k] = None if len(vals) < 8 or s.std(ddof=1) == 0 else round(float((series_dict[k] - s.mean()) / s.std(ddof=1)), 3)
    return out

def complete_quarter(q):  # only quarters whose last month has data
    today = dt.date.today(); yq = f"{today.year}Q{(today.month-1)//3+1}"; return q < yq

def main(path):
    data = json.load(open(path))
    log = []
    gdp = fred("GDPC1"); g = growth_annualised(gdp)
    nfci_s = fred("NFCI"); ff_s = fred("DFF"); vix_s = fred("VIXCLS"); oil_s = fred("DCOILWTICO")
    nfci = qmean(nfci_s); ff = qmean(ff_s); vix = qmean(vix_s); oil = qmean(oil_s)
    try: gpr = gpr_quarterly()
    except Exception as e: gpr = {}; log.append(f"GPR not refreshed: {e}")
    try: epu = epu_quarterly()
    except Exception as e: epu = {}; log.append(f"EPU not refreshed: {e}")

    try: pce_s = fred("PCEPI"); core_s = fred("PCEPILFE"); pce = yoy_quarterly(pce_s); corepce = yoy_quarterly(core_s)
    except Exception as e: pce = {}; corepce = {}; pce_s = core_s = pd.Series(dtype=float); log.append(f"PCE inflation not refreshed: {e}")
    try: spf = spf_growth_consensus(); log.append(f"SPF growth consensus through {max(spf)}")
    except Exception as e: spf = {}; log.append(f"SPF growth consensus not refreshed: {e}")

    # quarterly state: extend / refresh g, nfci, ff, inflation, spf; keep hd as it is
    Q = {r["q"]: r for r in data["series"]["quarterly"]}
    for q in sorted(set(g) | set(nfci) | set(ff) | set(pce) | set(spf)):
        if q < "1994Q1" or not complete_quarter(q): continue
        row = Q.setdefault(q, {"q": q})
        if q in g: row["g"] = g[q]
        if q in nfci: row["nfci"] = round(nfci[q], 3)
        if q in ff: row["ff"] = round(ff[q], 2)
        if q in pce: row["pce_yoy"] = pce[q]
        if q in corepce: row["corepce_yoy"] = corepce[q]
        if q in spf: row["spf"] = spf[q]
    data["series"]["quarterly"] = [Q[k] for k in sorted(Q)]

    # external measures in "sig": extend raw values at new origins, expanding z from 1994Q2
    ext = {"VIX": vix, "OIL": oil, "GPR": gpr, "EPU": epu}
    for s in data.get("sig", []):
        if s["k"] not in ext or not ext[s["k"]]: continue
        src = ext[s["k"]]; z = expanding_z(src)
        have = {v[0] for v in s["v"]}
        for q in sorted(src):
            if q >= "2007Q4" and q not in have and complete_quarter(q):
                s["v"].append([q, round(src[q], 4), z.get(q)]); log.append(f"{s['k']} + {q}")
        s["v"].sort(key=lambda v: v[0])

    groups_m = None
    try:
        groups, vint, groups_m = fredmd_groups(); data["groups"] = groups; log.append(f"FRED-MD groups recomputed through {groups[-1]['o']} (vintage column: {vint})")
        data.setdefault("meta", {})["fredmd_vintage"] = dt.date.today().isoformat()
    except Exception as e: log.append(f"FRED-MD not refreshed: {e}")
    try:
        monthly_block(data, nfci_s, ff_s, vix_s, oil_s, pce_s, core_s, GPR_MONTHLY.get("gpr"), EPU_MONTHLY.get("epu"), groups_m or (data.get("monthly", {}) or {}).get("groups"))
        log.append(f"monthly block through {data['monthly']['series'][-1]['m']}")
    except Exception as e: log.append(f"monthly block not refreshed: {e}")
    data.setdefault("meta", {})["public_refresh"] = dt.date.today().isoformat()
    json.dump(data, open(path, "w"), separators=(",", ":"))
    with open("update_log.md", "a") as f:
        f.write(f"\n## {dt.date.today().isoformat()} public refresh\n" + ("\n".join(f"- {l}" for l in log) or "- no new quarters") + "\n")
    print("\n".join(log) or "no new quarters")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data.json")

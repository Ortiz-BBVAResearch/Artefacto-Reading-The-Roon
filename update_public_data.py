"""Refresh the public series of the explorer's data.json: current growth, NFCI, funds rate,
VIX, oil, geopolitical risk and economic policy uncertainty. Nothing is estimated: the
model's distributions, Hidden Dissent and the SPF are left untouched (they come from the
replication pipeline and the Tsang-Yang data site). Run: python update_public_data.py data.json
"""
import io, json, sys, datetime as dt
import pandas as pd, requests

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
GPR  = "https://www.matteoiacoviello.com/gpr_files/data_gpr_export.xls"
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

def gpr_quarterly():
    r = requests.get(GPR, timeout=60); r.raise_for_status()
    df = pd.read_excel(io.BytesIO(r.content))
    col = [c for c in df.columns if str(c).upper() == "GPR"][0]
    df["date"] = pd.to_datetime(df["month"]); return qmean(df.set_index("date")[col])

def epu_quarterly():
    r = requests.get(EPU, timeout=60); r.raise_for_status()
    df = pd.read_excel(io.BytesIO(r.content)).dropna(subset=["Year", "Month"])
    df["date"] = pd.to_datetime(dict(year=df["Year"].astype(int), month=df["Month"].astype(int), day=1))
    col = [c for c in df.columns if "Three" in str(c) or "News" in str(c)][0]
    return qmean(df.set_index("date")[col])

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
    nfci = qmean(fred("NFCI")); ff = qmean(fred("DFF")); vix = qmean(fred("VIXCLS")); oil = qmean(fred("DCOILWTICO"))
    try: gpr = gpr_quarterly()
    except Exception as e: gpr = {}; log.append(f"GPR not refreshed: {e}")
    try: epu = epu_quarterly()
    except Exception as e: epu = {}; log.append(f"EPU not refreshed: {e}")

    # quarterly state: extend / refresh g, nfci, ff; keep hd and spf as they are
    Q = {r["q"]: r for r in data["series"]["quarterly"]}
    for q in sorted(set(g) | set(nfci) | set(ff)):
        if q < "1994Q1" or not complete_quarter(q): continue
        row = Q.setdefault(q, {"q": q})
        if q in g: row["g"] = g[q]
        if q in nfci: row["nfci"] = round(nfci[q], 3)
        if q in ff: row["ff"] = round(ff[q], 2)
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

    data.setdefault("meta", {})["public_refresh"] = dt.date.today().isoformat()
    json.dump(data, open(path, "w"), separators=(",", ":"))
    with open("update_log.md", "a") as f:
        f.write(f"\n## {dt.date.today().isoformat()} public refresh\n" + ("\n".join(f"- {l}" for l in log) or "- no new quarters") + "\n")
    print("\n".join(log) or "no new quarters")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data.json")

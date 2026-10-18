#!/usr/bin/env python3
"""Live ABG H=4 estimator. The frozen SUM/MEAN solvers are embedded below."""
from __future__ import annotations
import argparse, hashlib, io, json, re, sys, datetime as dt
from pathlib import Path
import numpy as np
import pandas as pd
import requests
from scipy.optimize import minimize
from dataclasses import dataclass

TAUS=np.round(np.arange(.05,1.0,.05),2)
LAMBDA={"LOWER":0.5623413251903491,"CENTER":100.0,"UPPER":100.0}
NUISANCE=['RPI', 'W875RX1', 'DPCERA3M086SBEA', 'CMRMTSPLx', 'RETAILx', 'INDPRO', 'IPFPNSS', 'IPFINAL', 'IPCONGD', 'IPDCONGD', 'IPNCONGD', 'IPBUSEQ', 'IPMAT', 'IPDMAT', 'IPNMAT', 'IPMANSICS', 'IPB51222S', 'IPFUELS', 'CUMFNS', 'HWI', 'HWIURATIO', 'CLF16OV', 'CE16OV', 'UNRATE', 'UEMPMEAN', 'UEMPLT5', 'UEMP5TO14', 'UEMP15OV', 'UEMP15T26', 'UEMP27OV', 'CLAIMSx', 'PAYEMS', 'USGOOD', 'CES1021000001', 'USCONS', 'MANEMP', 'DMANEMP', 'NDMANEMP', 'SRVPRD', 'USTPU', 'USWTRADE', 'USTRADE', 'USFIRE', 'USGOVT', 'CES0600000007', 'AWOTMAN', 'AWHMAN', 'HOUST', 'HOUSTNE', 'HOUSTMW', 'HOUSTS', 'HOUSTW', 'PERMIT', 'PERMITNE', 'PERMITMW', 'PERMITS', 'PERMITW', 'AMDMNOx', 'ANDENOx', 'AMDMUOx', 'BUSINVx', 'ISRATIOx', 'M1SL', 'M2SL', 'M2REAL', 'BOGMBASE', 'TOTRESNS', 'NONBORRES', 'BUSLOANS', 'REALLN', 'NONREVSL', 'CONSPI', 'S&P 500', 'S&P div yield', 'S&P PE ratio', 'FEDFUNDS', 'TB3MS', 'TB6MS', 'GS1', 'GS5', 'GS10', 'AAA', 'BAA', 'TB3SMFFM', 'TB6SMFFM', 'T1YFFM', 'T5YFFM', 'T10YFFM', 'AAAFFM', 'BAAFFM', 'EXSZUSx', 'EXJPUSx', 'EXUSUKx', 'EXCAUSx', 'WPSFD49207', 'WPSFD49502', 'WPSID61', 'WPSID62', 'OILPRICEx', 'PPICMM', 'CPIAUCSL', 'CPIAPPSL', 'CPITRNSL', 'CPIMEDSL', 'CUSR0000SAC', 'CUSR0000SAD', 'CUSR0000SAS', 'CPIULFSL', 'CUSR0000SA0L2', 'CUSR0000SA0L5', 'PCEPI', 'DDURRG3M086SBEA', 'DNDGRG3M086SBEA', 'DSERRG3M086SBEA', 'CES0600000008', 'CES2000000008', 'CES3000000008', 'DTCOLNVHFNM', 'DTCTHFNM', 'INVEST', 'VIXCLSx']
BASELINE={"M2":[-0.8237453990140917, 0.5125034389396174, 0.960357317827054, 1.20929897508905, 1.6110260199483015, 1.8015531419161137, 1.9770034818330675, 2.122374341650983, 2.3154215589334135, 2.598004790111399, 2.7354558263010933, 2.950406148063403, 3.185314387599906, 3.5255334373918994, 3.9364874198979143, 4.146071781737769, 4.392036691267567, 4.774695663524771, 6.054277952268137],"M3":[0.0975187444177394, 0.934176153788468, 1.337894444137154, 1.2903371727853516, 1.4523888325104255, 1.7902498229860675, 2.022262689222205, 2.2144621942169778, 2.418874260924424, 2.677116774831174, 2.812240148193411, 3.0550122171860674, 3.311655642069935, 3.707334438029075, 3.9101014727947736, 4.225230402646658, 4.420060048990284, 4.8099480461015744, 5.886354745269242]}
ROOT=Path(__file__).resolve().parents[1]
FRED_PAGE="https://www.stlouisfed.org/research/economists/mccracken/fred-databases"
FRED_GRAPH="https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
SPF_PAGE="https://www.philadelphiafed.org/surveys-and-data/real-time-data-research/dispersion-forecasts"

# A local copy of the objective's check-loss primitive used by the sealed solver.
def pinball_sum(residuals,tau):
    residuals=np.asarray(residuals,dtype=float); tau=float(tau)
    return float(np.sum(np.where(residuals>=0,tau*residuals,(tau-1)*residuals)))

_SUM_SOURCE='"""\nScenarioLab — Protocol B partitioned penalized quantile regression.\n\nThis module is deliberately separate from the certified E12 solver.\n\nScientific objective\n--------------------\n\n    mean pinball\n    + lambda * ||beta_P||^2\n\nwhere P is an explicitly declared subset of slope coefficients.\n\nThe intercept is always unpenalized.\n\nInternally the exact-primal solver uses SUM pinball, so the equivalent\nsolver penalty is\n\n    penalty_internal = n * lambda\n\nNo E12 solver is modified.\n"""\n\nfrom dataclasses import dataclass\n\nimport numpy as np\nfrom scipy.optimize import minimize\n\n@dataclass(frozen=True)\nclass ProtocolBQuantileResult:\n    intercept: float\n    coef: np.ndarray\n    tau: float\n    lambda_mean: float\n    penalty_internal: float\n    penalized_mask: np.ndarray\n    objective_sum: float\n    objective_mean: float\n    success: bool\n    message: str\n    n_iter: int\n\n    def predict(self, X):\n        X = np.asarray(\n            X,\n            dtype=float,\n        )\n\n        if X.ndim == 1:\n            X = X.reshape(\n                1,\n                -1,\n            )\n\n        return (\n            self.intercept\n            + X @ self.coef\n        )\n\n\ndef _validate(\n    X,\n    y,\n    tau,\n    lambda_mean,\n    penalized_mask,\n):\n\n    X = np.asarray(\n        X,\n        dtype=float,\n    )\n\n    y = np.asarray(\n        y,\n        dtype=float,\n    ).ravel()\n\n    if X.ndim == 1:\n        X = X.reshape(\n            -1,\n            1,\n        )\n\n    if X.ndim != 2:\n        raise ValueError(\n            "X must be 2D."\n        )\n\n    if X.shape[0] != len(y):\n        raise ValueError(\n            "X/y length mismatch."\n        )\n\n    if len(y) == 0:\n        raise ValueError(\n            "Empty estimation sample."\n        )\n\n    if not np.isfinite(X).all():\n        raise ValueError(\n            "X contains non-finite values."\n        )\n\n    if not np.isfinite(y).all():\n        raise ValueError(\n            "y contains non-finite values."\n        )\n\n    tau = float(tau)\n    lambda_mean = float(\n        lambda_mean\n    )\n\n    if not 0.0 < tau < 1.0:\n        raise ValueError(\n            "tau must lie strictly between 0 and 1."\n        )\n\n    if lambda_mean < 0.0:\n        raise ValueError(\n            "lambda_mean must be non-negative."\n        )\n\n    mask = np.asarray(\n        penalized_mask,\n        dtype=bool,\n    ).ravel()\n\n    if len(mask) != X.shape[1]:\n        raise ValueError(\n            "penalized_mask length mismatch."\n        )\n\n    return (\n        X,\n        y,\n        tau,\n        lambda_mean,\n        mask,\n    )\n\n\ndef penalty_value(\n    beta,\n    lambda_mean,\n    penalized_mask,\n):\n    """\n    Mean-loss-scale L2 penalty.\n    """\n\n    beta = np.asarray(\n        beta,\n        dtype=float,\n    ).ravel()\n\n    mask = np.asarray(\n        penalized_mask,\n        dtype=bool,\n    ).ravel()\n\n    if len(beta) != len(mask):\n        raise ValueError(\n            "beta/mask length mismatch."\n        )\n\n    return float(\n        float(lambda_mean)\n        * np.dot(\n            beta[mask],\n            beta[mask],\n        )\n    )\n\n\ndef penalty_gradient(\n    beta,\n    lambda_mean,\n    penalized_mask,\n):\n    """\n    Gradient of the mean-loss-scale penalty\n    with respect to slopes only.\n    """\n\n    beta = np.asarray(\n        beta,\n        dtype=float,\n    ).ravel()\n\n    mask = np.asarray(\n        penalized_mask,\n        dtype=bool,\n    ).ravel()\n\n    if len(beta) != len(mask):\n        raise ValueError(\n            "beta/mask length mismatch."\n        )\n\n    g = np.zeros_like(\n        beta,\n        dtype=float,\n    )\n\n    g[mask] = (\n        2.0\n        * float(lambda_mean)\n        * beta[mask]\n    )\n\n    return g\n\n\ndef mean_objective(\n    intercept,\n    beta,\n    X,\n    y,\n    tau,\n    lambda_mean,\n    penalized_mask,\n):\n    """\n    Public scientific Protocol-B objective.\n    """\n\n    X, y, tau, lambda_mean, mask = (\n        _validate(\n            X,\n            y,\n            tau,\n            lambda_mean,\n            penalized_mask,\n        )\n    )\n\n    beta = np.asarray(\n        beta,\n        dtype=float,\n    ).ravel()\n\n    if len(beta) != X.shape[1]:\n        raise ValueError(\n            "beta length mismatch."\n        )\n\n    residual = (\n        y\n        - float(intercept)\n        - X @ beta\n    )\n\n    return float(\n        pinball_sum(\n            residual,\n            tau,\n        )\n        / len(y)\n        + penalty_value(\n            beta,\n            lambda_mean,\n            mask,\n        )\n    )\n\n\ndef fit_protocol_b_penalized_quantile(\n    X,\n    y,\n    tau,\n    lambda_mean,\n    penalized_mask,\n    *,\n    maxiter=10000,\n    ftol=1e-11,\n):\n    """\n    Fit Protocol-B partitioned ridge quantile regression.\n\n    X contains slopes only; intercept is estimated internally\n    and never penalized.\n\n    lambda_mean is defined in the frozen scientific metric:\n\n        mean pinball + lambda_mean * ||beta_P||^2\n    """\n\n    (\n        X,\n        y,\n        tau,\n        lambda_mean,\n        mask,\n    ) = _validate(\n        X,\n        y,\n        tau,\n        lambda_mean,\n        penalized_mask,\n    )\n\n    n, p = X.shape\n\n    penalty_internal = (\n        n\n        * lambda_mean\n    )\n\n    ia = 0\n    ib0 = 1\n    ib1 = 1 + p\n    iu0 = ib1\n    iu1 = iu0 + n\n    iv0 = iu1\n    iv1 = iv0 + n\n\n    k = (\n        1\n        + p\n        + 2 * n\n    )\n\n    alpha0 = float(\n        np.quantile(\n            y,\n            tau,\n            method="linear",\n        )\n    )\n\n    beta0 = np.zeros(\n        p,\n        dtype=float,\n    )\n\n    residual0 = (\n        y\n        - alpha0\n    )\n\n    u0 = np.maximum(\n        residual0,\n        0.0,\n    )\n\n    v0 = np.maximum(\n        -residual0,\n        0.0,\n    )\n\n    z0 = np.empty(\n        k,\n        dtype=float,\n    )\n\n    z0[ia] = alpha0\n    z0[ib0:ib1] = beta0\n    z0[iu0:iu1] = u0\n    z0[iv0:iv1] = v0\n\n    def primal_objective(z):\n\n        beta = z[\n            ib0:ib1\n        ]\n\n        u = z[\n            iu0:iu1\n        ]\n\n        v = z[\n            iv0:iv1\n        ]\n\n        return float(\n            tau * np.sum(u)\n            + (1.0 - tau)\n            * np.sum(v)\n            + penalty_internal\n            * np.dot(\n                beta[mask],\n                beta[mask],\n            )\n        )\n\n    def primal_gradient(z):\n\n        g = np.zeros(\n            k,\n            dtype=float,\n        )\n\n        beta = z[\n            ib0:ib1\n        ]\n\n        gb = np.zeros(\n            p,\n            dtype=float,\n        )\n\n        gb[mask] = (\n            2.0\n            * penalty_internal\n            * beta[mask]\n        )\n\n        g[\n            ib0:ib1\n        ] = gb\n\n        g[\n            iu0:iu1\n        ] = tau\n\n        g[\n            iv0:iv1\n        ] = (\n            1.0\n            - tau\n        )\n\n        return g\n\n    def equality(z):\n\n        alpha = z[ia]\n\n        beta = z[\n            ib0:ib1\n        ]\n\n        u = z[\n            iu0:iu1\n        ]\n\n        v = z[\n            iv0:iv1\n        ]\n\n        return (\n            y\n            - alpha\n            - X @ beta\n            - u\n            + v\n        )\n\n    eq_jac = np.zeros(\n        (\n            n,\n            k,\n        ),\n        dtype=float,\n    )\n\n    eq_jac[:, ia] = -1.0\n\n    eq_jac[\n        :,\n        ib0:ib1,\n    ] = -X\n\n    rows = np.arange(\n        n\n    )\n\n    eq_jac[\n        rows,\n        iu0 + rows,\n    ] = -1.0\n\n    eq_jac[\n        rows,\n        iv0 + rows,\n    ] = 1.0\n\n    def equality_jac(_z):\n        return eq_jac\n\n    constraints = [\n        {\n            "type": "eq",\n            "fun": equality,\n            "jac": equality_jac,\n        }\n    ]\n\n    bounds = (\n        [(None, None)]\n        * (1 + p)\n        + [(0.0, None)]\n        * (2 * n)\n    )\n\n    result = minimize(\n        primal_objective,\n        z0,\n        method="SLSQP",\n        jac=primal_gradient,\n        bounds=bounds,\n        constraints=constraints,\n        options={\n            "maxiter":\n                int(maxiter),\n            "ftol":\n                float(ftol),\n            "disp":\n                False,\n        },\n    )\n\n    z = np.asarray(\n        result.x,\n        dtype=float,\n    )\n\n    intercept = float(\n        z[ia]\n    )\n\n    coef = (\n        z[\n            ib0:ib1\n        ]\n        .copy()\n    )\n\n    obj_sum = float(\n        primal_objective(\n            z\n        )\n    )\n\n    obj_mean = float(\n        obj_sum\n        / n\n    )\n\n    # Independent scientific-objective identity.\n    manual_mean = mean_objective(\n        intercept,\n        coef,\n        X,\n        y,\n        tau,\n        lambda_mean,\n        mask,\n    )\n\n    if not np.isclose(\n        obj_mean,\n        manual_mean,\n        rtol=1e-9,\n        atol=1e-9,\n    ):\n        raise RuntimeError(\n            "SUM/MEAN objective identity failed: "\n            f"{obj_mean} != {manual_mean}"\n        )\n\n    return ProtocolBQuantileResult(\n        intercept=intercept,\n        coef=coef,\n        tau=tau,\n        lambda_mean=lambda_mean,\n        penalty_internal=(\n            penalty_internal\n        ),\n        penalized_mask=(\n            mask.copy()\n        ),\n        objective_sum=obj_sum,\n        objective_mean=obj_mean,\n        success=bool(\n            result.success\n        ),\n        message=str(\n            result.message\n        ),\n        n_iter=int(\n            result.nit\n        ),\n    )\n'
_MEAN_SOURCE='"""\nScenarioLab — Protocol B partitioned penalized quantile regression.\n\nThis module is deliberately separate from the certified E12 solver.\n\nScientific objective\n--------------------\n\n    mean pinball\n    + lambda * ||beta_P||^2\n\nwhere P is an explicitly declared subset of slope coefficients.\n\nThe intercept is always unpenalized.\n\nInternally the exact-primal solver uses SUM pinball, so the equivalent\nsolver penalty is\n\n    penalty_internal = n * lambda\n\nNo E12 solver is modified.\n"""\n\nfrom dataclasses import dataclass\n\nimport numpy as np\nfrom scipy.optimize import minimize\n\n@dataclass(frozen=True)\nclass ProtocolBQuantileResult:\n    intercept: float\n    coef: np.ndarray\n    tau: float\n    lambda_mean: float\n    penalty_internal: float\n    penalized_mask: np.ndarray\n    objective_sum: float\n    objective_mean: float\n    success: bool\n    message: str\n    n_iter: int\n\n    def predict(self, X):\n        X = np.asarray(\n            X,\n            dtype=float,\n        )\n\n        if X.ndim == 1:\n            X = X.reshape(\n                1,\n                -1,\n            )\n\n        return (\n            self.intercept\n            + X @ self.coef\n        )\n\n\ndef _validate(\n    X,\n    y,\n    tau,\n    lambda_mean,\n    penalized_mask,\n):\n\n    X = np.asarray(\n        X,\n        dtype=float,\n    )\n\n    y = np.asarray(\n        y,\n        dtype=float,\n    ).ravel()\n\n    if X.ndim == 1:\n        X = X.reshape(\n            -1,\n            1,\n        )\n\n    if X.ndim != 2:\n        raise ValueError(\n            "X must be 2D."\n        )\n\n    if X.shape[0] != len(y):\n        raise ValueError(\n            "X/y length mismatch."\n        )\n\n    if len(y) == 0:\n        raise ValueError(\n            "Empty estimation sample."\n        )\n\n    if not np.isfinite(X).all():\n        raise ValueError(\n            "X contains non-finite values."\n        )\n\n    if not np.isfinite(y).all():\n        raise ValueError(\n            "y contains non-finite values."\n        )\n\n    tau = float(tau)\n    lambda_mean = float(\n        lambda_mean\n    )\n\n    if not 0.0 < tau < 1.0:\n        raise ValueError(\n            "tau must lie strictly between 0 and 1."\n        )\n\n    if lambda_mean < 0.0:\n        raise ValueError(\n            "lambda_mean must be non-negative."\n        )\n\n    mask = np.asarray(\n        penalized_mask,\n        dtype=bool,\n    ).ravel()\n\n    if len(mask) != X.shape[1]:\n        raise ValueError(\n            "penalized_mask length mismatch."\n        )\n\n    return (\n        X,\n        y,\n        tau,\n        lambda_mean,\n        mask,\n    )\n\n\ndef penalty_value(\n    beta,\n    lambda_mean,\n    penalized_mask,\n):\n    """\n    Mean-loss-scale L2 penalty.\n    """\n\n    beta = np.asarray(\n        beta,\n        dtype=float,\n    ).ravel()\n\n    mask = np.asarray(\n        penalized_mask,\n        dtype=bool,\n    ).ravel()\n\n    if len(beta) != len(mask):\n        raise ValueError(\n            "beta/mask length mismatch."\n        )\n\n    return float(\n        float(lambda_mean)\n        * np.dot(\n            beta[mask],\n            beta[mask],\n        )\n    )\n\n\ndef penalty_gradient(\n    beta,\n    lambda_mean,\n    penalized_mask,\n):\n    """\n    Gradient of the mean-loss-scale penalty\n    with respect to slopes only.\n    """\n\n    beta = np.asarray(\n        beta,\n        dtype=float,\n    ).ravel()\n\n    mask = np.asarray(\n        penalized_mask,\n        dtype=bool,\n    ).ravel()\n\n    if len(beta) != len(mask):\n        raise ValueError(\n            "beta/mask length mismatch."\n        )\n\n    g = np.zeros_like(\n        beta,\n        dtype=float,\n    )\n\n    g[mask] = (\n        2.0\n        * float(lambda_mean)\n        * beta[mask]\n    )\n\n    return g\n\n\ndef mean_objective(\n    intercept,\n    beta,\n    X,\n    y,\n    tau,\n    lambda_mean,\n    penalized_mask,\n):\n    """\n    Public scientific Protocol-B objective.\n    """\n\n    X, y, tau, lambda_mean, mask = (\n        _validate(\n            X,\n            y,\n            tau,\n            lambda_mean,\n            penalized_mask,\n        )\n    )\n\n    beta = np.asarray(\n        beta,\n        dtype=float,\n    ).ravel()\n\n    if len(beta) != X.shape[1]:\n        raise ValueError(\n            "beta length mismatch."\n        )\n\n    residual = (\n        y\n        - float(intercept)\n        - X @ beta\n    )\n\n    return float(\n        pinball_sum(\n            residual,\n            tau,\n        )\n        / len(y)\n        + penalty_value(\n            beta,\n            lambda_mean,\n            mask,\n        )\n    )\n\n\ndef fit_protocol_b_penalized_quantile(\n    X,\n    y,\n    tau,\n    lambda_mean,\n    penalized_mask,\n    *,\n    maxiter=10000,\n    ftol=1e-11,\n):\n    """\n    Fit Protocol-B partitioned ridge quantile regression.\n\n    X contains slopes only; intercept is estimated internally\n    and never penalized.\n\n    lambda_mean is defined in the frozen scientific metric:\n\n        mean pinball + lambda_mean * ||beta_P||^2\n    """\n\n    (\n        X,\n        y,\n        tau,\n        lambda_mean,\n        mask,\n    ) = _validate(\n        X,\n        y,\n        tau,\n        lambda_mean,\n        penalized_mask,\n    )\n\n    n, p = X.shape\n\n    penalty_internal = (\n        lambda_mean\n    )\n\n    ia = 0\n    ib0 = 1\n    ib1 = 1 + p\n    iu0 = ib1\n    iu1 = iu0 + n\n    iv0 = iu1\n    iv1 = iv0 + n\n\n    k = (\n        1\n        + p\n        + 2 * n\n    )\n\n    alpha0 = float(\n        np.quantile(\n            y,\n            tau,\n            method="linear",\n        )\n    )\n\n    beta0 = np.zeros(\n        p,\n        dtype=float,\n    )\n\n    residual0 = (\n        y\n        - alpha0\n    )\n\n    u0 = np.maximum(\n        residual0,\n        0.0,\n    )\n\n    v0 = np.maximum(\n        -residual0,\n        0.0,\n    )\n\n    z0 = np.empty(\n        k,\n        dtype=float,\n    )\n\n    z0[ia] = alpha0\n    z0[ib0:ib1] = beta0\n    z0[iu0:iu1] = u0\n    z0[iv0:iv1] = v0\n\n    def primal_objective(z):\n\n        beta = z[\n            ib0:ib1\n        ]\n\n        u = z[\n            iu0:iu1\n        ]\n\n        v = z[\n            iv0:iv1\n        ]\n\n        return float(\n            (tau / n) * np.sum(u)\n            + ((1.0 - tau) / n)\n            * np.sum(v)\n            + penalty_internal\n            * np.dot(\n                beta[mask],\n                beta[mask],\n            )\n        )\n\n    def primal_gradient(z):\n\n        g = np.zeros(\n            k,\n            dtype=float,\n        )\n\n        beta = z[\n            ib0:ib1\n        ]\n\n        gb = np.zeros(\n            p,\n            dtype=float,\n        )\n\n        gb[mask] = (\n            2.0\n            * penalty_internal\n            * beta[mask]\n        )\n\n        g[\n            ib0:ib1\n        ] = gb\n\n        g[\n            iu0:iu1\n        ] = tau / n\n\n        g[\n            iv0:iv1\n        ] = (\n            (1.0 - tau)\n            / n\n        )\n\n        return g\n\n    def equality(z):\n\n        alpha = z[ia]\n\n        beta = z[\n            ib0:ib1\n        ]\n\n        u = z[\n            iu0:iu1\n        ]\n\n        v = z[\n            iv0:iv1\n        ]\n\n        return (\n            y\n            - alpha\n            - X @ beta\n            - u\n            + v\n        )\n\n    eq_jac = np.zeros(\n        (\n            n,\n            k,\n        ),\n        dtype=float,\n    )\n\n    eq_jac[:, ia] = -1.0\n\n    eq_jac[\n        :,\n        ib0:ib1,\n    ] = -X\n\n    rows = np.arange(\n        n\n    )\n\n    eq_jac[\n        rows,\n        iu0 + rows,\n    ] = -1.0\n\n    eq_jac[\n        rows,\n        iv0 + rows,\n    ] = 1.0\n\n    def equality_jac(_z):\n        return eq_jac\n\n    constraints = [\n        {\n            "type": "eq",\n            "fun": equality,\n            "jac": equality_jac,\n        }\n    ]\n\n    bounds = (\n        [(None, None)]\n        * (1 + p)\n        + [(0.0, None)]\n        * (2 * n)\n    )\n\n    result = minimize(\n        primal_objective,\n        z0,\n        method="SLSQP",\n        jac=primal_gradient,\n        bounds=bounds,\n        constraints=constraints,\n        options={\n            "maxiter":\n                int(maxiter),\n            "ftol":\n                float(ftol),\n            "disp":\n                False,\n        },\n    )\n\n    z = np.asarray(\n        result.x,\n        dtype=float,\n    )\n\n    intercept = float(\n        z[ia]\n    )\n\n    coef = (\n        z[\n            ib0:ib1\n        ]\n        .copy()\n    )\n\n    obj_sum = float(\n        primal_objective(\n            z\n        )\n    )\n\n    obj_mean = float(\n        obj_sum\n    )\n\n    # Independent scientific-objective identity.\n    manual_mean = mean_objective(\n        intercept,\n        coef,\n        X,\n        y,\n        tau,\n        lambda_mean,\n        mask,\n    )\n\n    if not np.isclose(\n        obj_mean,\n        manual_mean,\n        rtol=1e-9,\n        atol=1e-9,\n    ):\n        raise RuntimeError(\n            "SUM/MEAN objective identity failed: "\n            f"{obj_mean} != {manual_mean}"\n        )\n\n    return ProtocolBQuantileResult(\n        intercept=intercept,\n        coef=coef,\n        tau=tau,\n        lambda_mean=lambda_mean,\n        penalty_internal=(\n            n * lambda_mean\n        ),\n        penalized_mask=(\n            mask.copy()\n        ),\n        objective_sum=obj_sum,\n        objective_mean=obj_mean,\n        success=bool(\n            result.success\n        ),\n        message=str(\n            result.message\n        ),\n        n_iter=int(\n            result.nit\n        ),\n    )\n'
_SUM_NS={"np":np,"pd":pd,"minimize":minimize,"dataclass":dataclass,"pinball_sum":pinball_sum}
_MEAN_NS={"np":np,"pd":pd,"minimize":minimize,"dataclass":dataclass,"pinball_sum":pinball_sum}
exec(_SUM_SOURCE,_SUM_NS)
exec(_MEAN_SOURCE,_MEAN_NS)
fit_sum=_SUM_NS["fit_protocol_b_penalized_quantile"]
fit_mean=_MEAN_NS["fit_protocol_b_penalized_quantile"]


def get_current_fredmd_url(session):
    page=session.get(FRED_PAGE,timeout=60); page.raise_for_status()
    html=page.text
    # The official page updates the current.csv link to each newly released vintage.
    m=re.search(r'href="([^"]+\.csv[^\"]*)"[^>]*>\s*current\.csv',html,re.I)
    if not m:
        m=re.search(r'href="([^"]+\.csv[^\"]*)"[^>]*>\s*202\d-\d\d\.csv',html,re.I)
    if not m: raise RuntimeError("Could not resolve the official FRED-MD current.csv link")
    from urllib.parse import urljoin
    return urljoin(FRED_PAGE,m.group(1))


def load_fredmd(session):
    url=get_current_fredmd_url(session)
    response=session.get(url,timeout=120); response.raise_for_status()
    raw=pd.read_csv(io.BytesIO(response.content),header=None,dtype=str)
    if raw.shape[0]<4: raise RuntimeError("FRED-MD file is incomplete")
    names=raw.iloc[0,1:].astype(str).str.strip().tolist()
    tcodes=pd.to_numeric(raw.iloc[1,1:],errors="raise").astype(int).tolist()
    dates=pd.to_datetime(raw.iloc[2:,0],errors="raise")
    monthly=raw.iloc[2:,1:].copy(); monthly.columns=names; monthly.index=pd.DatetimeIndex(dates)
    monthly=monthly.apply(pd.to_numeric,errors="coerce")
    all_quarters=monthly.index.to_period("Q")
    complete=[]
    for q in sorted(set(all_quarters)):
        present=set(monthly.index[all_quarters==q].month)
        if present.issuperset({int(q.start_time.month),int(q.start_time.month)+1,int(q.start_time.month)+2}): complete.append(q)
    if not complete: raise RuntimeError("FRED-MD has no complete quarter")
    latest=max(complete)
    columns=[]
    for j,name in enumerate(names):
        s=monthly[name].copy(); q=s.index.to_period("Q"); s.index=q
        rawq=s.groupby(level=0).mean()
        rawq=rawq.where(s.groupby(level=0).count().eq(3))
        t=int(tcodes[j])
        if t==1: z=rawq
        elif t==2: z=rawq.diff()
        elif t==3: z=rawq.diff().diff()
        elif t==4: z=np.log(rawq.where(rawq>0))
        elif t==5: z=np.log(rawq.where(rawq>0)).diff()
        elif t==6: z=np.log(rawq.where(rawq>0)).diff().diff()
        elif t==7: z=(rawq.pct_change(fill_method=None)*100).diff()
        else: raise RuntimeError(f"Unknown FRED-MD tcode {t} for {name}")
        columns.append(z.rename(name))
    X=pd.concat(columns,axis=1).sort_index().ffill()
    # Distinguish release vintage from the last monthly observation: the
    # September 2026 FRED-MD release currently contains data through August.
    m=re.search(r"(\d{4}-\d{2})-md\.csv",url,re.I)
    vintage=m.group(1) if m else str(monthly.index.max().to_period("M"))
    last_month=str(monthly.index.max().to_period("M"))
    return X,latest,url,vintage,last_month


def fred_series(session,sid):
    r=session.get(FRED_GRAPH.format(sid),timeout=60); r.raise_for_status()
    d=pd.read_csv(io.StringIO(r.text),na_values=".")
    d.columns=["date","value"]
    return pd.Series(pd.to_numeric(d.value,errors="coerce").to_numpy(),index=pd.to_datetime(d.date),name=sid).dropna()


def quarter_series(s):
    q=s.copy(); q.index=q.index.to_period("Q")
    return q.groupby(level=0).mean().astype(float)


def load_signals(session,data):
    # SPF D2, RGDP, horizon T+4, same published construction used in the frozen bridge.
    page=session.get(SPF_PAGE,timeout=60); page.raise_for_status()
    html=page.text
    m=re.search(r'href="([^"]+Dispersion_2\.xlsx[^\"]*)"',html,re.I)
    if not m: raise RuntimeError("Could not resolve Philadelphia Fed SPF D2 workbook")
    from urllib.parse import urljoin
    wb=session.get(urljoin(SPF_PAGE,m.group(1)),timeout=120); wb.raise_for_status()
    xls=pd.ExcelFile(io.BytesIO(wb.content))
    spf=None
    # The Philadelphia Fed workbook places its column header on row 10,
    # after the title and documentation rows. Only the RGDP worksheet is used.
    if "RGDP" in xls.sheet_names:
        frame=pd.read_excel(xls,sheet_name="RGDP",header=9)
        frame.columns=[str(c).strip() for c in frame.columns]
        if "Survey_Date(T)" in frame and "RGDP_D2(T+4)" in frame:
            d=frame[["Survey_Date(T)","RGDP_D2(T+4)"]].copy()
            d["q"]=pd.PeriodIndex(d["Survey_Date(T)"].astype(str).str.strip(),freq="Q")
            spf=pd.Series(pd.to_numeric(d["RGDP_D2(T+4)"],errors="coerce").to_numpy(),index=d.q).dropna()
    if spf is None: raise RuntimeError("SPF D2 workbook lacks Survey_Date(T)/RGDP_D2(T+4)")
    signals={"SPF":spf}
    for item in data.get("sig",[]):
        key=item.get("k")
        if key not in {"GPR","EPU","VIX","OIL"}: continue
        pairs=item.get("v",[])
        signals[key]=pd.Series({pd.Period(str(row[0]),freq="Q"):float(row[1]) for row in pairs if len(row)>1 and row[1] is not None})
    # Replace online series with latest official values; the updater has already refreshed these too.
    return signals


def pf1(raw,index,origin,first):
    avail=raw.reindex(index[:origin+1]).dropna().astype(float)
    avail=avail.loc[avail.index>=pd.Period(first,freq="Q")]
    if avail.empty: raise RuntimeError(f"No observations for {raw.name} by origin {index[origin]}")
    mu=float(avail.mean()); sd=float(avail.std(ddof=0))
    if not np.isfinite(sd) or sd<=0: raise RuntimeError(f"Invalid scale for {raw.name}")
    z=pd.Series(0.0,index=index[:origin+1],name=raw.name)
    z.loc[avail.index]=(avail-mu)/sd
    return z


def estimate_one(X_public,y,index,origin,tau,lam,nuisance,focals):
    h=4; t=int(origin); last=t-h
    Xt=X_public.iloc[:last+1].copy(); Xp=X_public.iloc[[t]].copy()
    yt=y.iloc[h:t+1].copy(); yt.index=Xt.index
    if Xt.isna().any().any() or Xp.isna().any().any() or yt.isna().any(): raise RuntimeError("Missing data in sealed estimation window")
    mu=Xt.mean(axis=0); sd=Xt.std(axis=0,ddof=0)
    if (sd<=1e-14).any(): raise RuntimeError("Zero predictor standard deviation")
    pieces=[(Xt-mu)/sd]; preds=[(Xp-mu)/sd]
    names=[]
    for name,(raw,first) in focals.items():
        zz=pf1(raw,index,t,first)
        parts=zz.iloc[:last+1].to_frame(name); pred=pd.DataFrame({name:[zz.iloc[-1]]},index=Xp.index)
        pieces.append(parts); preds.append(pred); names.append(name)
    fit=pd.concat(pieces,axis=1); pred=pd.concat(preds,axis=1)
    penalized=np.asarray([str(c) in set(nuisance) for c in fit.columns],dtype=bool)
    primary=fit_sum(fit.to_numpy(),yt.to_numpy(),tau=float(tau),lambda_mean=float(lam),penalized_mask=penalized)
    model=primary
    if not primary.success:
        model=fit_mean(fit.to_numpy(),yt.to_numpy(),tau=float(tau),lambda_mean=float(lam),penalized_mask=penalized)
        if not model.success: raise RuntimeError(f"SUM and MEAN solvers failed at {index[t]} q{tau}")
    val=float(model.predict(pred.to_numpy())[0])
    if not np.isfinite(val): raise RuntimeError("Nonfinite forecast")
    return val


def lambda_for(tau):
    return LAMBDA["LOWER"] if tau<=.25 else (LAMBDA["UPPER"] if tau>=.75 else LAMBDA["CENTER"])


def make_bank(X,g,nfci,signals,origin,models=None):
    idx=X.index; t=idx.get_loc(origin)
    base=X[NUISANCE].copy(); base["GDP_GROWTH_CURRENT"]=g.ffill().reindex(idx)
    nfci_raw=nfci.reindex(idx)
    focals={"M3":{"NFCI_PF1":(nfci_raw,"1994Q2")}}
    for k,first in {"SPF":"1994Q2","GPR":"1994Q2","EPU":"1994Q2","VIX":"1990Q1","OIL":"1986Q1"}.items():
        focals[k]={f"{k}_PF1":(signals[k].reindex(idx),first)}
    bank={}
    for model in (models or ["M2","M3","SPF","GPR","EPU","VIX","OIL"]):
        Xp=base.copy(); focal=focals.get(model,{})
        if model=="M3": focal=focals["M3"]
        vals=[]
        for tau in TAUS:
            vals.append(estimate_one(Xp,g.rolling(4,min_periods=4).mean(),idx,t,tau,lambda_for(tau),NUISANCE,focal))
        bank[model]=vals
    return bank


def check_gate(X,g,nfci,signals,data,log_path):
    origin=pd.Period("2025Q1",freq="Q")
    # The reproduction gate is only for the two sealed baseline banks;
    # do not spend time fitting the five external-signal variants here.
    bank=make_bank(X,g,nfci,signals,origin,models=["M2","M3"])
    rec=next((r for r in data["dist"] if r.get("o")=="2025Q1"),None)
    if not rec: raise RuntimeError("2025Q1 sealed distribution missing")
    diffs={}
    for k in ["M2","M3"]:
        if len(rec[k])!=19: raise RuntimeError(f"Invalid baseline {k}")
        diffs[k]=float(np.max(np.abs(np.asarray(bank[k])-np.asarray(rec[k],dtype=float))))
    msg=(f"Origin gate 2025Q1 ({dt.datetime.now(dt.timezone.utc).date()}): "
         + ", ".join(f"{k} max_abs_diff={v:.12g}" for k,v in diffs.items()))
    with open(log_path,"a",encoding="utf-8") as f: f.write("\n- "+msg+"\n")
    print(msg)
    if max(diffs.values())>0.15: raise RuntimeError("Reproduction gate failed; data.json not written")
    return diffs


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("data",nargs="?",default="data.json"); args=parser.parse_args()
    path=Path(args.data); original=path.read_bytes(); data=json.loads(original)
    session=requests.Session(); session.headers["User-Agent"]="ReadingTheRoom-live-estimator/1.0"
    X,latest,url,vintage,last_month=load_fredmd(session)
    # Freeze the 2025Q1 benchmark check before any mutation/output.
    idx=pd.period_range("1973Q1",max(latest,pd.Period("2025Q1",freq="Q"))+4,freq="Q")
    X=X.reindex(idx).ffill()
    g=quarter_series(fred_series(session,"A191RL1Q225SBEA")); g=g.reindex(idx)
    nfci=quarter_series(fred_series(session,"NFCI")).reindex(idx)
    sig=load_signals(session,data)
    for k in sig: sig[k]=sig[k].reindex(idx)
    gate=check_gate(X,g,nfci,sig,data,ROOT/"update_log.md")
    # Only append origins with a complete three-month FRED-MD quarter.
    latest=min(latest,idx[-1]-4)
    have={r.get("o") for r in data["dist"]}
    alt_rows={}
    additions=[]
    for origin in pd.period_range("2025Q2",latest,freq="Q"):
        if str(origin) in have: continue
        bank=make_bank(X,g,nfci,sig,origin)
        target=origin+4; actual=g.rolling(4,min_periods=4).mean().get(target,np.nan)
        key=str(origin)
        row={"o":key,"t":str(target),"y":None if pd.isna(actual) else float(actual),
             "window":"live","M2":bank["M2"],"M3":bank["M3"],"M2_HD":None,"M3_HD":None}
        additions.append(row)
        for k in ["SPF","GPR","EPU","VIX","OIL"]:
            alt_rows.setdefault(k,{})[key]=bank[k]
        print(f"estimated live origin {origin} -> {target}",flush=True)
    if additions:
        data["dist"].extend(additions); data["dist"].sort(key=lambda r:r["o"])
    for k,rows in alt_rows.items():
        alt=next((a for a in data.get("alt",[]) if a.get("k")==k),None)
        if alt is None: raise RuntimeError(f"Alternative model {k} missing from data.json")
        alt.setdefault("q",[]).extend(rows[o] for o in sorted(rows))
    # Resolve prior live targets when GDP observations arrive; preserve all forecast arrays.
    actuals=g.rolling(4,min_periods=4).mean()
    for r in data["dist"]:
        if r.get("window")=="live":
            q=pd.Period(r["t"],freq="Q")
            if q in actuals.index and pd.notna(actuals.loc[q]): r["y"]=float(actuals.loc[q]); r["window"]="resolved_live"
    data.setdefault("meta",{}).update({"live_through":str(latest),"fredmd_vintage":vintage,
        "fredmd_last_observation_month":last_month,
        "estimator_hash":hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    # Atomic write is deliberately last: a failed gate leaves data.json byte-for-byte untouched.
    tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(data,separators=(",",":")),encoding="utf-8"); tmp.replace(path)
    with open(ROOT/"update_log.md","a",encoding="utf-8") as f:
        f.write(f"\n- Live estimate through {latest}; FRED-MD vintage {vintage} (last monthly observation {last_month}); gate M2={gate['M2']:.12g}, M3={gate['M3']:.12g}; new origins={len(additions)}.\n")
    print(f"PASS: latest origin {latest}; new origins {len(additions)}")

if __name__=="__main__": main()

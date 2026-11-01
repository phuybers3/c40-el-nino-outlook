"""Quantile regressions of daily values on the RONI lead and the trend.

    python code/03_fit_quantiles.py [--daily PATH] [--out PATH] [--reps 100] [--seed 20261031] [--workers 7]

For every city, season and variable (temperature, precipitation on wet days,
relative humidity) the model

    Q_tau(y | t, RONI) = intercept + b * RONI(Sep-Nov, t-1) + c * (year - tbar)

is fitted at tau = 0.05, 0.5 and 0.95 by iteratively reweighted least squares
(statsmodels QuantReg). Uncertainty comes from a year-block bootstrap: whole
seasons are drawn with replacement, the same draws for all three quantiles,
so the difference between the 95th and 5th percentile effects has a valid
test. Each cell writes three quantile rows and two "95th-5th" rows (one for
the El Niño difference, one for the trend difference) in the column layout of
the table shipped on 2026-10-31. The 1,701 quantile rows form one family for
the Benjamini-Hochberg flag.

Rainfall cells with fewer than MIN_WET_DAYS wet days over the record are
skipped; the nine skipped on 2026-10-31 had at most 243, the thinnest fitted
cell had 347.

Point estimates agree with the shipped table to three or four significant
digits; the shipped solver stopped slightly short of the optimum. Bootstrap
standard errors differ within Monte Carlo noise (about 7% for 100 replicates).
"""
from __future__ import annotations

import argparse
import os
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
QUANTILES = [0.05, 0.5, 0.95]
VARS = {"temperature": "tmean", "precipitation": "precip", "rel_humidity": "rh"}
WET_MM = 1.0
MIN_WET_DAYS = 300
MAX_ITER = 1000
P_TOL = 1e-6
COLUMNS = [
    "city", "season", "variable", "quantile", "n_days", "n_years", "trend_per_decade", "trend_se_per_decade",
    "trend_p", "trend_lo80", "trend_hi80", "enso_effect", "enso_se", "enso_p", "enso_lo80", "enso_hi80",
    "level_2027_neutral", "crossing_points", "intercept", "tbar", "seconds", "fits", "fits_hit_iteration_cap",
    "enso_difference", "enso_difference_se", "enso_difference_p", "enso_difference_lo80", "enso_difference_hi80",
    "trend_difference", "trend_difference_se", "trend_difference_p", "trend_difference_lo80", "trend_difference_hi80",
    "enso_q_fdr", "enso_survives_fdr",
]

_DAILY: pd.DataFrame | None = None


def _load(path: str) -> None:
    global _DAILY
    _DAILY = pd.read_parquet(path)


def _fit(y: np.ndarray, X: np.ndarray, q: float) -> tuple[np.ndarray, bool]:
    import statsmodels.api as sm
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        res = sm.QuantReg(y, X).fit(q=q, max_iter=MAX_ITER, p_tol=P_TOL)
        capped = any("Maximum number of iterations" in str(i.message) for i in w)
    return res.params, capped


def _summary(point: float, reps: np.ndarray) -> dict:
    se = float(np.std(reps, ddof=1))
    lo, hi = np.percentile(reps, [10, 90])
    p = float(2 * stats.norm.sf(abs(point) / se)) if se > 0 else float("nan")
    return {"se": se, "p": p, "lo80": float(lo), "hi80": float(hi)}


def fit_cell(task: tuple) -> list[dict]:
    city, season, var, reps, seed, forecast_year = task
    t0 = time.time()
    d = _DAILY[(_DAILY["city"] == city) & (_DAILY["season"] == season)]
    if var == "precipitation":
        d = d[d["precip"] >= WET_MM]
        if len(d) < MIN_WET_DAYS:
            return []
    y = d[VARS[var]].to_numpy(float)
    yr = d["year"].to_numpy(int)
    lead = d["roni_lead"].to_numpy(float)
    tbar = yr.mean()
    X = np.column_stack([np.ones(len(y)), lead, yr - tbar])
    years = np.unique(yr)
    by_year = {v: np.flatnonzero(yr == v) for v in years}

    point = {}
    capped = 0
    for q in QUANTILES:
        point[q], c = _fit(y, X, q)
        capped += c
    rng = np.random.default_rng(seed)
    boot = {q: np.empty((reps, 3)) for q in QUANTILES}
    for r in range(reps):
        draw = rng.choice(years, size=len(years), replace=True)
        idx = np.concatenate([by_year[v] for v in draw])
        for q in QUANTILES:
            boot[q][r], c = _fit(y[idx], X[idx], q)
            capped += c
    fits = len(QUANTILES) * (1 + reps)

    # Crossing: rows of the data where the fitted 5th exceeds the 50th or the 50th the 95th.
    f = {q: X @ point[q] for q in QUANTILES}
    crossings = int(np.sum((f[0.05] > f[0.5]) | (f[0.5] > f[0.95])))
    seconds = time.time() - t0
    base = {"city": city, "season": season, "variable": var, "n_days": len(y), "n_years": len(years)}
    rows = []
    for q in QUANTILES:
        b, c = point[q][1], point[q][2]
        sb, sc = _summary(b, boot[q][:, 1]), _summary(c * 10, boot[q][:, 2] * 10)
        rows.append({**base, "quantile": q,
                     "trend_per_decade": c * 10, "trend_se_per_decade": sc["se"], "trend_p": sc["p"], "trend_lo80": sc["lo80"], "trend_hi80": sc["hi80"],
                     "enso_effect": b, "enso_se": sb["se"], "enso_p": sb["p"], "enso_lo80": sb["lo80"], "enso_hi80": sb["hi80"],
                     "level_2027_neutral": point[q][0] + c * (forecast_year - tbar), "crossing_points": crossings,
                     "intercept": point[q][0], "tbar": tbar, "seconds": seconds, "fits": fits, "fits_hit_iteration_cap": capped})
    de = point[0.95][1] - point[0.05][1]
    se_ = _summary(de, boot[0.95][:, 1] - boot[0.05][:, 1])
    rows.append({**base, "quantile": "95th-5th", "enso_difference": de, "enso_difference_se": se_["se"], "enso_difference_p": se_["p"],
                 "enso_difference_lo80": se_["lo80"], "enso_difference_hi80": se_["hi80"]})
    dt = (point[0.95][2] - point[0.05][2]) * 10
    st = _summary(dt, (boot[0.95][:, 2] - boot[0.05][:, 2]) * 10)
    rows.append({**base, "quantile": "95th-5th", "trend_difference": dt, "trend_difference_se": st["se"], "trend_difference_p": st["p"],
                 "trend_difference_lo80": st["lo80"], "trend_difference_hi80": st["hi80"]})
    return rows


def bh_qvalues(p: np.ndarray) -> np.ndarray:
    m = len(p)
    order = np.argsort(p)
    ranked = p[order] * m / np.arange(1, m + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(q, 1.0)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--daily", default=str(ROOT / "data/processed/daily_panel.parquet"))
    ap.add_argument("--out", default=str(ROOT / "data/processed/quantile_results.csv"))
    ap.add_argument("--reps", type=int, default=100)
    ap.add_argument("--seed", type=int, default=20261031)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--forecast-year", type=int, default=2027)
    ap.add_argument("--fdr", type=float, default=0.05)
    ap.add_argument("--limit", type=int, default=0, help="fit only the first N cells (smoke test)")
    args = ap.parse_args()

    cells = pd.read_parquet(args.daily, columns=["city", "season"]).drop_duplicates().values.tolist()
    tasks = [(c, s, v, args.reps, args.seed + i, args.forecast_year)
             for i, ((c, s), v) in enumerate((cs, v) for v in VARS for cs in cells)]
    if args.limit:
        tasks = tasks[: args.limit]
    print(f"{len(tasks)} cells, {args.reps} bootstrap replicates, {args.workers} workers", flush=True)
    rows, done, t0 = [], 0, time.time()
    with ProcessPoolExecutor(max_workers=args.workers, initializer=_load, initargs=(args.daily,)) as ex:
        for out in ex.map(fit_cell, tasks, chunksize=4):
            rows.extend(out)
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(tasks)} cells, {time.time() - t0:.0f} s", flush=True)
    df = pd.DataFrame(rows)
    isq = df["quantile"] != "95th-5th"
    df["enso_q_fdr"] = np.nan
    df.loc[isq, "enso_q_fdr"] = bh_qvalues(df.loc[isq, "enso_p"].to_numpy())
    df["enso_survives_fdr"] = df["enso_q_fdr"] <= args.fdr
    df = df[COLUMNS]
    df["quantile"] = df["quantile"].astype(str)  # 0.05/0.5/0.95 and "95th-5th" share the column
    df.to_csv(args.out, index=False)
    df.to_parquet(Path(args.out).with_suffix(".parquet"), index=False)
    print(f"{len(df)} rows -> {args.out}; capped fits {int(df.loc[isq, 'fits_hit_iteration_cap'].sum() / 3)} of "
          f"{int(df.loc[isq, 'fits'].sum() / 3)}; FDR survivors {int(df['enso_survives_fdr'].sum())}; {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()

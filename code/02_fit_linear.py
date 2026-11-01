"""Fit the seasonal model for every city, season and variable.

    y(t) = a + b * RONI(Sep-Nov, t-1) + c * (t - tbar) + e

Input is data/processed/seasonal_panel.csv (one row per city, season, year).
Output is data/processed/linear_results.csv and .parquet, one row per city,
season and variable, with the columns the site exporter and the facts builder
read. The column order matches the table shipped on 2026-10-31 so the two can
be diffed.

    python code/02_fit_linear.py [--panel PATH] [--out PATH] [--forecast-year 2027]

Rebuilt 2026-11 from the shipped table; every stored number reproduces to
floating-point precision (see code/validate.py).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
VARS = ["temperature", "precipitation", "wet_day_share", "rel_humidity"]
BASELINE = (1991, 2020)
COLUMNS = [
    "city", "season", "variable", "region", "lat", "lon", "n_years", "first_year",
    "last_year", "tbar", "normal_1991_2020", "tercile_low", "tercile_high",
    "trend_per_decade", "trend_se_per_decade", "trend_p", "enso_effect", "enso_se",
    "enso_p", "partial_r2", "sd_detrended", "sd_residual", "a2027", "var_a2027",
    "cov_a2027_b", "var_b", "roni_lead_min", "roni_lead_max", "enso_q_fdr",
    "enso_survives_fdr",
]


def fit_cell(d: pd.DataFrame, var: str, forecast_year: int) -> dict:
    """OLS of one variable on RONI lead and centred year; t-tests on n-3 df."""
    d = d.dropna(subset=[var]).sort_values("year")
    y = d[var].to_numpy(float)
    yr = d["year"].to_numpy(float)
    x = d["roni_lead"].to_numpy(float)
    n = len(y)
    tbar = yr.mean()
    X = np.column_stack([np.ones(n), x, yr - tbar])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = n - X.shape[1]
    s2 = resid @ resid / dof
    cov = s2 * np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    p = 2 * stats.t.sf(np.abs(beta / se), dof)

    # Trend-only fit: its residual spread is the "detrended" spread, and the
    # share of that spread the RONI term removes is the partial R².
    Xt = X[:, [0, 2]]
    bt, *_ = np.linalg.lstsq(Xt, y, rcond=None)
    rt = y - Xt @ bt
    sd_detrended = np.sqrt(rt @ rt / (n - 2))
    partial_r2 = 1 - (resid @ resid) / (rt @ rt)

    # Level of the trend line in the forecast year at RONI = 0, with the
    # variance terms the outlook spread needs.
    g = np.array([1.0, 0.0, forecast_year - tbar])
    a_fc = g @ beta
    var_a = g @ cov @ g
    cov_ab = g @ cov[:, 1]

    base = y[(yr >= BASELINE[0]) & (yr <= BASELINE[1])]
    t_lo, t_hi = np.percentile(base, [100 / 3, 200 / 3])

    return {
        "n_years": n, "first_year": int(yr[0]), "last_year": int(yr[-1]), "tbar": tbar,
        "normal_1991_2020": base.mean(), "tercile_low": t_lo, "tercile_high": t_hi,
        "trend_per_decade": beta[2] * 10, "trend_se_per_decade": se[2] * 10, "trend_p": p[2],
        "enso_effect": beta[1], "enso_se": se[1], "enso_p": p[1],
        "partial_r2": partial_r2, "sd_detrended": sd_detrended, "sd_residual": np.sqrt(s2),
        "a2027": a_fc, "var_a2027": var_a, "cov_a2027_b": cov_ab, "var_b": cov[1, 1],
    }


def bh_qvalues(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg q-values over one family of tests."""
    m = len(p)
    order = np.argsort(p)
    ranked = p[order] * m / np.arange(1, m + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(q, 1.0)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--panel", default=ROOT / "data/processed/seasonal_panel.csv")
    ap.add_argument("--out", default=ROOT / "data/processed/linear_results.csv")
    ap.add_argument("--forecast-year", type=int, default=2027)
    ap.add_argument("--fdr", type=float, default=0.05)
    args = ap.parse_args()

    panel = pd.read_csv(args.panel)
    lead_min, lead_max = panel["roni_lead"].min(), panel["roni_lead"].max()
    rows = []
    for (city, season), d in panel.groupby(["city", "season"], sort=False):
        meta = d.iloc[0]
        for var in VARS:
            r = {"city": city, "season": season, "variable": var, "region": meta["region"],
                 "lat": meta["lat"], "lon": meta["lon"]}
            r.update(fit_cell(d, var, args.forecast_year))
            r["roni_lead_min"], r["roni_lead_max"] = lead_min, lead_max
            rows.append(r)
    out = pd.DataFrame(rows)
    # One family: 96 cities x 2 seasons x 4 variables = 768 tests of b.
    out["enso_q_fdr"] = bh_qvalues(out["enso_p"].to_numpy())
    out["enso_survives_fdr"] = out["enso_q_fdr"] <= args.fdr
    out = out[COLUMNS]
    out.to_csv(args.out, index=False)
    out.to_parquet(Path(args.out).with_suffix(".parquet"), index=False)
    print(f"{len(out)} rows -> {args.out}; FDR survivors {int(out['enso_survives_fdr'].sum())}")


if __name__ == "__main__":
    main()

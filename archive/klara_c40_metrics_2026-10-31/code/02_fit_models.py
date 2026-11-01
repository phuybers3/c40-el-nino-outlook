"""
Step 2 - Fit the models.

For every city x season (DJF, MAM) x variable:

A. LINEAR MODEL on seasonal values (one value per year, 1951-2025)
       y_t = a + b * RONI_lead_t + c * (t - tbar) + e_t
   b  = ENSO effect per +1 °C of Sep-Nov RONI      c = trend per year (reported per decade)
   Also: partial R² of ENSO (share of detrended variance ENSO explains), residual SD
   ("intrinsic variability" left after trend and ENSO), and the pieces the spreadsheet
   needs to forecast 2027 with live formulas.

B. QUANTILE REGRESSIONS on daily values (temperature, rainfall on wet days, relative humidity)
       Q_tau(y_d) = a_tau + b_tau * RONI_lead_t(d) + c_tau * (t(d) - tbar),  tau = 0.05, 0.50, 0.95
   Three fits, estimated jointly in one year-block bootstrap (the same resampled years for all
   three), so the difference between the 95th and 5th percentile slopes has a valid interval.

Writes data/processed/linear_results.parquet and quantile_results.parquet.
"""
import os
# One numerical thread per worker process: without this, numpy on a Mac can start many threads in
# each of the parallel workers and they fight over the same cores.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
import time
import zlib
import numpy as np
import pandas as pd
from multiprocessing import Pool
from scipy import stats
import config as C

LINEAR_VARS = ["temperature", "precipitation", "wet_day_share", "rel_humidity"]
QR_VARS = {"temperature": "tmean", "precipitation": "precip", "rel_humidity": "rh"}


# ---------------------------------------------------------------- helpers
ITER_LOG = {"fits": 0, "capped": 0}


def fast_quantreg(X, y, q, beta0=None, max_iter=300, tol=1e-6, eps=None):
    """Quantile regression by iteratively reweighted least squares (same solver as the main notebook).
    beta0 = optional starting values (bootstrap draws start from the full-sample estimate).
    eps   = smallest residual used in the weights; scaled to the data so that ties (many identical
            rounded values) cannot produce near-infinite weights and endless oscillation."""
    if eps is None:
        eps = max(1e-6, 1e-4 * float(np.median(np.abs(y - np.median(y)))))
    beta = np.linalg.lstsq(X, y, rcond=None)[0] if beta0 is None else beta0.copy()
    ITER_LOG["fits"] += 1
    for _ in range(max_iter):
        r = y - X @ beta
        w = np.where(r > 0, q, 1 - q) / np.maximum(np.abs(r), eps)
        WX = X * w[:, None]
        new = np.linalg.solve(X.T @ WX, WX.T @ y)
        if np.max(np.abs(new - beta)) < tol:
            return new
        beta = new
    ITER_LOG["capped"] += 1
    return beta


def bh_fdr(p):
    """Benjamini-Hochberg q-values."""
    p = np.asarray(p, float)
    ok = np.isfinite(p)
    q = np.full_like(p, np.nan)
    pv = p[ok]
    order = np.argsort(pv)
    ranked = pv[order] * len(pv) / np.arange(1, len(pv) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty_like(pv)
    out[order] = np.minimum(ranked, 1)
    q[ok] = out
    return q


# ---------------------------------------------------------------- A. linear model
def fit_linear(g, var):
    g = g.dropna(subset=[var, "roni_lead"])
    yrs = g["year"].values.astype(float)
    x = g["roni_lead"].values
    y = g[var].values.astype(float)
    n = len(y)
    tbar = yrs.mean()
    X = np.column_stack([np.ones(n), x, yrs - tbar])
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    resid = y - X @ beta
    dof = n - 3
    s2 = resid @ resid / dof
    cov = s2 * XtX_inv
    se = np.sqrt(np.diag(cov))
    tstat = beta / se
    p = 2 * stats.t.sf(np.abs(tstat), dof)
    # trend-only model -> partial R² of ENSO
    T = X[:, [0, 2]]
    rt = y - T @ np.linalg.lstsq(T, y, rcond=None)[0]
    sse_t, sse_f = rt @ rt, resid @ resid
    # 2027 "no-ENSO" level: a27 = a + c * (2027 - tbar); its variance and covariance with b
    L = np.array([1.0, 0.0, C.FORECAST_YEAR - tbar])
    a27 = L @ beta
    var_a27 = L @ cov @ L
    cov_a27_b = L @ cov[:, 1]
    base = g.loc[(g["year"] >= C.BASELINE[0]) & (g["year"] <= C.BASELINE[1]), var]
    return dict(
        n_years=n, first_year=int(yrs.min()), last_year=int(yrs.max()), tbar=tbar,
        normal_1991_2020=base.mean(), tercile_low=base.quantile(1 / 3), tercile_high=base.quantile(2 / 3),
        trend_per_decade=10 * beta[2], trend_se_per_decade=10 * se[2], trend_p=p[2],
        enso_effect=beta[1], enso_se=se[1], enso_p=p[1],
        partial_r2=(sse_t - sse_f) / sse_t if sse_t > 0 else np.nan,
        sd_detrended=np.sqrt(sse_t / (n - 2)), sd_residual=np.sqrt(s2),
        a2027=a27, var_a2027=var_a27, cov_a2027_b=cov_a27_b, var_b=cov[1, 1],
        roni_lead_min=x.min(), roni_lead_max=x.max(),
    )


# ---------------------------------------------------------------- B. quantile regressions
def fit_quantiles(args):
    t0 = time.time()
    ITER_LOG["fits"] = ITER_LOG["capped"] = 0
    city, season, var, d = args
    col = QR_VARS[var]
    d = d.dropna(subset=[col, "roni_lead"])
    if var == "precipitation":
        d = d[d[col] >= C.WET_DAY_MM]
    if d["year"].nunique() < 30 or len(d) < 300:
        return []
    yrs = d["year"].values.astype(float)
    tbar = yrs.mean()
    X = np.column_stack([np.ones(len(d)), d["roni_lead"].values, yrs - tbar])
    y = d[col].values.astype(float)
    taus = C.QUANTILES
    point = np.array([fast_quantreg(X, y, q) for q in taus])                     # (3 taus, 3 coefs)
    uy = np.unique(d["year"].values)
    idx_by_year = {u: np.flatnonzero(d["year"].values == u) for u in uy}
    rng = np.random.default_rng(zlib.crc32(f"{city}|{season}|{var}".encode()))
    boots = np.full((C.N_BOOT, len(taus), 3), np.nan)
    for b in range(C.N_BOOT):
        pick = rng.choice(uy, len(uy), replace=True)
        ii = np.concatenate([idx_by_year[u] for u in pick])
        for k, q in enumerate(taus):
            try:
                boots[b, k] = fast_quantreg(X[ii], y[ii], q, beta0=point[k], max_iter=150, tol=1e-5)
            except np.linalg.LinAlgError:
                pass
    # crossing check: do the fitted 5th/50th/95th lines keep their order at every observed (RONI, year)?
    grid = np.unique(X[:, 1:], axis=0)
    G = np.column_stack([np.ones(len(grid)), grid])
    fq = G @ point.T
    crossings = int(np.sum((np.diff(fq, axis=1) < 0).any(axis=1)))
    out = []
    for k, q in enumerate(taus):
        bk = boots[:, k, :]
        se = np.nanstd(bk, axis=0, ddof=1)
        z = point[k] / se
        p = 2 * stats.norm.sf(np.abs(z))
        a27 = point[k, 0] + point[k, 2] * (C.FORECAST_YEAR - tbar)
        out.append(dict(
            city=city, season=season, variable=var, quantile=q, n_days=len(y), n_years=len(uy),
            trend_per_decade=10 * point[k, 2], trend_se_per_decade=10 * se[2], trend_p=p[2],
            trend_lo80=10 * np.nanpercentile(bk[:, 2], 10), trend_hi80=10 * np.nanpercentile(bk[:, 2], 90),
            enso_effect=point[k, 1], enso_se=se[1], enso_p=p[1],
            enso_lo80=np.nanpercentile(bk[:, 1], 10), enso_hi80=np.nanpercentile(bk[:, 1], 90),
            level_2027_neutral=a27, crossing_points=crossings, intercept=point[k, 0], tbar=tbar,
            seconds=time.time() - t0, fits=ITER_LOG["fits"], fits_hit_iteration_cap=ITER_LOG["capped"],
        ))
    # tail difference: 95th minus 5th percentile slopes, same bootstrap draws
    for name, j, scale in [("enso", 1, 1), ("trend", 2, 10)]:
        diff = (boots[:, -1, j] - boots[:, 0, j]) * scale
        est = (point[-1, j] - point[0, j]) * scale
        se = np.nanstd(diff, ddof=1)
        out.append(dict(city=city, season=season, variable=var, quantile="95th-5th", n_days=len(y), n_years=len(uy),
                        **{f"{name}_difference": est, f"{name}_difference_se": se,
                           f"{name}_difference_p": 2 * stats.norm.sf(abs(est / se)),
                           f"{name}_difference_lo80": np.nanpercentile(diff, 10),
                           f"{name}_difference_hi80": np.nanpercentile(diff, 90)}))
    return out


def main():
    seasonal = pd.read_parquet(C.PROCESSED / "seasonal_panel.parquet")
    daily = pd.read_parquet(C.PROCESSED / "daily_panel.parquet")

    # A. linear
    rows = []
    for (city, season), g in seasonal.groupby(["city", "season"], sort=False):
        meta = g.iloc[0][["region", "lat", "lon"]].to_dict()
        for var in LINEAR_VARS:
            rows.append(dict(city=city, season=season, variable=var, **meta, **fit_linear(g, var)))
    lin = pd.DataFrame(rows)
    lin["enso_q_fdr"] = bh_fdr(lin["enso_p"])
    lin["enso_survives_fdr"] = lin["enso_q_fdr"] < C.FDR_ALPHA
    lin.to_parquet(C.PROCESSED / "linear_results.parquet", index=False)
    print(f"Linear models: {len(lin)} fits; ENSO p<0.05: {(lin['enso_p'] < 0.05).sum()}, "
          f"survive FDR: {lin['enso_survives_fdr'].sum()}")

    # B. quantile regressions (parallel)
    jobs = [(city, season, var, g[["year", "roni_lead", col]].copy())
            for (city, season), g in daily.groupby(["city", "season"], sort=False)
            for var, col in QR_VARS.items()]
    print(f"Quantile regressions: {len(jobs)} city-season-variable sets x {len(C.QUANTILES)} quantiles, "
          f"{C.N_BOOT} bootstrap draws each ...")
    res, t0 = [], time.time()
    with Pool() as pool:
        for i, r in enumerate(pool.imap_unordered(fit_quantiles, jobs, chunksize=1), 1):
            res.append(r)
            if r and r[0].get("fits_hit_iteration_cap", 0) > 0.2 * r[0].get("fits", 1):
                print(f"    slow to converge: {r[0]['city']} {r[0]['season']} {r[0]['variable']} "
                      f"({r[0]['fits_hit_iteration_cap']}/{r[0]['fits']} fits hit the cap, {r[0]['seconds']:.0f}s)", flush=True)
            if i % 24 == 0 or i == len(jobs):
                el = time.time() - t0
                print(f"  {i}/{len(jobs)} done, {el / 60:.1f} min elapsed, ~{el / i * (len(jobs) - i) / 60:.0f} min left", flush=True)
    qr = pd.DataFrame([r for rr in res for r in rr])
    qr["quantile"] = qr["quantile"].astype(str)
    main_rows = qr["quantile"] != "95th-5th"
    qr.loc[main_rows, "enso_q_fdr"] = bh_fdr(qr.loc[main_rows, "enso_p"])
    qr["enso_survives_fdr"] = qr["enso_q_fdr"] < C.FDR_ALPHA
    qr.to_parquet(C.PROCESSED / "quantile_results.parquet", index=False)
    m = qr[main_rows]
    print(f"Quantile fits: {len(m)}; ENSO p<0.05: {(m['enso_p'] < 0.05).sum()}, survive FDR: {m['enso_survives_fdr'].sum()}; "
          f"sets with crossing fitted lines: {(m.groupby(['city', 'season', 'variable'])['crossing_points'].first() > 0).sum()}")


if __name__ == "__main__":
    main()
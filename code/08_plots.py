"""One figure per city: figures/<City>.png, four rows by two seasons.

    python code/08_plots.py [--cities "Lima" "Tokyo"] [--workers N] [--out DIR]

Columns are Dec–Feb and Mar–May. The first row is the Sep–Nov RONI of the
previous year, the predictor, as bars coloured El Niño or La Niña, with the
forecast year's estimate from facts_meta.json hatched and its spread as an
error bar. The next three rows are daily mean temperature, wet-day rainfall
and relative humidity: dots are each year's observed 5th, 50th and 95th
percentile of the daily values, lines are the quantile-regression fit
(trend plus El Niño, so they wiggle with RONI) from quantile_results.csv,
and a diamond is the fitted value for the forecast year at the RONI estimate.
Each panel's subtitle gives the trend per decade and the El Niño confidence
at each percentile under the rule set recorded in facts_meta.json: Strong
when the effect survives the false-discovery-rate correction, then the
p-value tiers.
"""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import NullFormatter, ScalarFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SEASONS = [("DJF", "Dec–Feb"), ("MAM", "Mar–May")]
QUANTILES = [0.05, 0.5, 0.95]
QVARS = [("temperature", "tmean", "Daily mean temperature (°C)"),
         ("precipitation", "precip", "Wet-day rainfall (mm/day)"),
         ("rel_humidity", "rh", "Daily relative humidity (%)")]
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#ffffff"
Q_COL = {0.05: "#2a78d6", 0.5: "#1baf7a", 0.95: "#eb6834"}  # cold/low, median, hot/high
EL_NINO, LA_NINA = "#eb6834", "#2a78d6"
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
                     "font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#c3c2b7", "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.labelcolor": INK2, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE})


def confidence_label(p: float, survives_fdr: bool, meta: dict) -> str:
    """The label of 04_build_facts.py: Strong by the FDR flag when the rules say so, then the p tiers."""
    table = meta["confidence"]
    if meta["strong_is_fdr"]:
        if survives_fdr:
            return table[0][1]
        table = table[1:]
    out = table[0][1]
    for lo, name in table:
        if p >= lo:
            out = name
    return out


def short_label(label: str) -> str:
    return "none" if label == "No identifiable effect" else label.lower()


def yearly_percentiles(daily: pd.DataFrame, wet_mm: float) -> dict[str, pd.DataFrame]:
    """Per variable: a frame indexed by (city, season, year) with one column per quantile."""
    out = {}
    for var, col, _ in QVARS:
        d = daily[daily["precip"] >= wet_mm] if var == "precipitation" else daily
        out[var] = d.groupby(["city", "season", "year"], observed=True)[col].quantile(QUANTILES).unstack()
    return out


def draw_city(job: dict) -> str:
    city, meta, out_dir = job["city"], job["meta"], Path(job["out_dir"])
    roni, roni_sd, y_fc = meta["son_2026_roni"], meta["son_2026_roni_sd"], meta["forecast_year"]
    fig, axes = plt.subplots(4, 2, figsize=(13, 11), sharex=True,
                             gridspec_kw={"height_ratios": [0.6, 1, 1, 1]}, layout="constrained")
    for j, (season, season_name) in enumerate(SEASONS):
        s = job["seasonal"][season]  # year -> roni_lead
        years, lead = s.index.to_numpy(), s.to_numpy()
        ax = axes[0, j]
        ax.bar(years, lead, color=np.where(lead >= 0, EL_NINO, LA_NINA), width=0.8, linewidth=0)
        ax.bar([y_fc], [roni], color=EL_NINO, alpha=0.4, width=0.8, hatch="//", edgecolor=EL_NINO, linewidth=0)
        if roni_sd > 0:
            ax.errorbar([y_fc], [roni], yerr=[roni_sd], color=INK, lw=0.8, capsize=2)
        ax.axhline(0, color=MUTED, lw=0.6)
        ax.set_ylabel("Sep–Nov RONI of the\nprevious year (°C)")
        ax.set_title(f"{city} — {season_name}", loc="left", fontsize=11, fontweight="bold", color=INK)
        for i, (var, _, ylab) in enumerate(QVARS, 1):
            ax = axes[i, j]
            emp = job["percentiles"][var].get(season)
            fits = job["fits"].get((season, var), {})
            subtitle = []
            for qv in QUANTILES:
                if emp is not None and qv in emp.columns:
                    e = emp[qv].dropna()
                    ax.scatter(e.index, e.to_numpy(), s=10, color=Q_COL[qv], alpha=0.55, linewidths=0)
                f = fits.get(qv)
                if f is None:
                    continue
                c = f["trend_per_decade"] / 10
                fit = f["intercept"] + f["enso_effect"] * lead + c * (years - f["tbar"])
                ax.plot(years, fit, color=Q_COL[qv], lw=1.5)
                y_hat = f["intercept"] + f["enso_effect"] * roni + c * (y_fc - f["tbar"])
                ax.plot([y_fc], [y_hat], "D", color=Q_COL[qv], mec=SURFACE, mew=1.0, ms=7)
                subtitle.append((f"{int(qv * 100)}th {f['trend_per_decade']:+.2f}",
                                 f"{int(qv * 100)}th {short_label(confidence_label(f['enso_p'], f['enso_survives_fdr'], meta))}"))
            if var == "precipitation":
                ax.set_yscale("log")
                ax.yaxis.set_major_formatter(ScalarFormatter())
                ax.yaxis.set_minor_formatter(NullFormatter())
            ax.set_ylabel(ylab)
            ax.grid(axis="y", color=GRID, lw=0.5)
            if subtitle:
                ax.set_title("Trend per decade: " + ", ".join(t[0] for t in subtitle) + "\nEl Niño effect: "
                             + ", ".join(t[1] for t in subtitle), loc="left", fontsize=8, color=INK2)
            else:
                ax.set_title("No quantile fit: too few wet days", loc="left", fontsize=8, color=INK2)
    axes[-1, 0].set_xlim(meta["fit_years"][0] - 1, y_fc + 1.5)
    estimate = "estimate" if meta["son_2026_estimated"] else "observed"
    handles = [plt.Line2D([], [], color=Q_COL[q], marker="o", lw=1.5, label=f"{int(q * 100)}th percentile") for q in QUANTILES]
    handles.append(plt.Line2D([], [], marker="D", ls="", color=MUTED, mec=SURFACE,
                              label=f"{y_fc} fit at Sep–Nov {y_fc - 1} RONI = {roni:+.2f} ± {roni_sd:.2f} ({estimate})"))
    fig.legend(handles=handles, loc="outside lower center", ncol=4, frameon=False)
    fig.suptitle("Dots: observed percentiles of the daily values in each season. Lines: quantile regression on the trend "
                 "and the previous Sep–Nov RONI. Bars: the RONI predictor, El Niño orange and La Niña blue.",
                 x=0.01, ha="left", fontsize=9, color=INK2)
    path = out_dir / f"{city}.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return str(path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--meta", default=ROOT / "data/processed/facts_meta.json")
    ap.add_argument("--seasonal", default=ROOT / "data/processed/seasonal_panel.csv")
    ap.add_argument("--daily", default=ROOT / "data/processed/daily_panel.parquet")
    ap.add_argument("--quantiles", default=ROOT / "data/processed/quantile_results.csv")
    ap.add_argument("--cities-file", default=ROOT / "data/cities.csv")
    ap.add_argument("--out", default=ROOT / "figures")
    ap.add_argument("--cities", nargs="*", help="draw only these cities")
    ap.add_argument("--workers", type=int, default=min(7, os.cpu_count() or 1))
    args = ap.parse_args()

    meta = json.load(open(args.meta))
    seasonal = pd.read_csv(args.seasonal)
    daily = pd.read_parquet(args.daily, columns=["city", "season", "year", "tmean", "precip", "rh"])
    qt = pd.read_csv(args.quantiles)
    qt["quantile"] = qt["quantile"].astype(str)
    qt = qt[qt["quantile"].isin(["0.05", "0.5", "0.95"])]
    cities = list(pd.read_csv(args.cities_file)["city"])
    if args.cities:
        missing = set(args.cities) - set(cities)
        if missing:
            raise SystemExit(f"not in data/cities.csv: {sorted(missing)}")
        cities = args.cities
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    pct = yearly_percentiles(daily, meta["wet_day_mm"])

    jobs = []
    for city in cities:
        job = {"city": city, "meta": meta, "out_dir": str(out_dir), "seasonal": {}, "percentiles": {}, "fits": {}}
        for season, _ in SEASONS:
            s = seasonal[(seasonal["city"] == city) & (seasonal["season"] == season)].sort_values("year")
            job["seasonal"][season] = s.set_index("year")["roni_lead"]
        for var, _, _ in QVARS:
            frame = pct[var]
            job["percentiles"][var] = {season: frame.loc[(city, season)] for season, _ in SEASONS
                                       if (city, season) in frame.index.droplevel("year")}
        for _, r in qt[qt["city"] == city].iterrows():
            job["fits"].setdefault((r["season"], r["variable"]), {})[float(r["quantile"])] = {
                "intercept": float(r["intercept"]), "enso_effect": float(r["enso_effect"]), "tbar": float(r["tbar"]),
                "trend_per_decade": float(r["trend_per_decade"]), "enso_p": float(r["enso_p"]),
                "enso_survives_fdr": bool(r["enso_survives_fdr"])}
        jobs.append(job)

    if args.workers > 1 and len(jobs) > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            paths = list(pool.map(draw_city, jobs))
    else:
        paths = [draw_city(j) for j in jobs]
    print(f"Saved {len(paths)} figures to {out_dir} ({len(list(out_dir.glob('*.png')))} PNG files there)")


if __name__ == "__main__":
    main()

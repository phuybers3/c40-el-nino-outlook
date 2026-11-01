"""
Step 4 - One figure per city: figures/<City>.png

Columns: Dec–Feb (DJF) and Mar–May (MAM).
Rows:
  1. Sep–Nov RONI of the previous year (the predictor), bars colored El Niño / La Niña.
  2-4. Temperature, wet-day rainfall, relative humidity: dots = each year's observed 5th, 50th and
       95th percentile of daily values; lines = the quantile-regression fit (trend + ENSO), which
       wiggles with RONI; a diamond = the fitted value for 2027 with this year's Sep–Nov RONI.
The panel title gives the ENSO confidence label and the trend per decade at each percentile.
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config as C

INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
Q_COL = {0.05: "#2a78d6", 0.5: "#52514e", 0.95: "#eb6834"}
EN, LN = "#eb6834", "#2a78d6"
QVARS = [("temperature", "tmean", "Daily mean temperature (°C)"),
         ("precipitation", "precip", "Wet-day rainfall (mm/day)"),
         ("rel_humidity", "rh", "Daily relative humidity (%)")]
plt.rcParams.update({"font.family": "sans-serif", "font.size": 9, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.edgecolor": "#c3c2b7", "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.labelcolor": INK2})


def conf_label(p):
    lab = C.CONFIDENCE[0][1]
    for p0, l in C.CONFIDENCE:
        if p >= p0:
            lab = l
    return lab


def main():
    seasonal = pd.read_parquet(C.PROCESSED / "seasonal_panel.parquet")
    daily = pd.read_parquet(C.PROCESSED / "daily_panel.parquet")
    qr = pd.read_parquet(C.PROCESSED / "quantile_results.parquet")
    qr = qr[qr["quantile"] != "95th-5th"].copy()
    qr["q"] = qr["quantile"].astype(float)
    C.FIGURES.mkdir(parents=True, exist_ok=True)
    for city, *_ in C.C40_CITIES:
        dcity = daily[daily["city"] == city]
        if dcity.empty:
            continue
        fig, axes = plt.subplots(4, 2, figsize=(13, 11), sharex=True,
                                 gridspec_kw={"height_ratios": [0.6, 1, 1, 1]}, layout="constrained")
        for j, season in enumerate(C.SEASONS):
            s = seasonal[(seasonal["city"] == city) & (seasonal["season"] == season)].sort_values("year")
            ax = axes[0, j]
            ax.bar(s["year"], s["roni_lead"], color=np.where(s["roni_lead"] >= 0, EN, LN), width=0.8)
            ax.bar([C.FORECAST_YEAR], [C.SON_2026_RONI], color=EN, alpha=0.45, width=0.8, hatch="//", edgecolor=EN)
            ax.axhline(0, color=MUTED, lw=0.6)
            ax.set_ylabel("Sep–Nov RONI\n(previous year, °C)")
            ax.set_title(f"{city} — {'Dec–Feb' if season == 'DJF' else 'Mar–May'}", loc="left", fontsize=11, fontweight="bold", color=INK)
            for i, (var, col, ylab) in enumerate(QVARS, 1):
                ax = axes[i, j]
                d = dcity[dcity["season"] == season]
                if var == "precipitation":
                    d = d[d[col] >= C.WET_DAY_MM]
                emp = d.groupby("year")[col].quantile(C.QUANTILES).unstack()
                lead = s.set_index("year")["roni_lead"]
                fits = qr[(qr["city"] == city) & (qr["season"] == season) & (qr["variable"] == var)]
                titles = []
                for qv in C.QUANTILES:
                    if qv not in emp.columns:
                        continue
                    ax.scatter(emp.index, emp[qv], s=9, color=Q_COL[qv], alpha=0.55, lw=0)
                    f = fits[fits["q"] == qv]
                    if f.empty:
                        continue
                    f = f.iloc[0]
                    yrs = lead.index.values
                    c = f["trend_per_decade"] / 10
                    fit = f["intercept"] + f["enso_effect"] * lead.values + c * (yrs - f["tbar"])
                    ax.plot(yrs, fit, color=Q_COL[qv], lw=1.4)
                    y27 = f["intercept"] + f["enso_effect"] * C.SON_2026_RONI + c * (C.FORECAST_YEAR - f["tbar"])
                    ax.plot([C.FORECAST_YEAR], [y27], "D", color=Q_COL[qv], mec=INK, ms=6)
                    titles.append((f"{int(qv * 100)}th {f['trend_per_decade']:+.2f}",
                                   f"{int(qv * 100)}th {conf_label(f['enso_p']).lower().replace('no identifiable effect', 'none')}"))
                if var == "precipitation":
                    ax.set_yscale("log")
                ax.set_ylabel(ylab)
                ax.grid(axis="y", color=GRID, lw=0.5)
                if titles:
                    ax.set_title("Trend per decade: " + ", ".join(t[0] for t in titles) + "\nENSO confidence: "
                                 + ", ".join(t[1] for t in titles), loc="left", fontsize=8, color=INK2)
        axes[-1, 0].set_xlim(C.FIT_START - 1, C.FORECAST_YEAR + 1.5)
        handles = [plt.Line2D([], [], color=Q_COL[q], marker="o", lw=1.4, label=f"{int(q * 100)}th percentile")
                   for q in C.QUANTILES] + [plt.Line2D([], [], marker="D", ls="", color=MUTED, mec=INK,
                                                       label=f"2027 fit (Sep–Nov 2026 RONI = {C.SON_2026_RONI:+.1f})")]
        fig.legend(handles=handles, loc="outside lower center", ncol=4, frameon=False)
        fig.suptitle("Dots: observed percentiles of daily values each season · Lines: quantile regression on trend + "
                     "previous Sep–Nov RONI", x=0.01, ha="left", fontsize=9, color=INK2)
        fig.savefig(C.FIGURES / f"{city}.png", dpi=130)
        plt.close(fig)
    print(f"Saved {len(list(C.FIGURES.glob('*.png')))} figures to {C.FIGURES}")


if __name__ == "__main__":
    main()

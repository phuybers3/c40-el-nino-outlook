"""
Step 1 - Prepare data.

Reads the ERA5 daily city files and the RONI table, and writes two tidy tables:

  data/processed/seasonal_panel.parquet   one row per city x season x year
      temperature    seasonal mean of daily mean temperature (°C)
      precipitation  seasonal total (mm)
      wet_day_share  % of days with >= 1 mm
      rel_humidity   seasonal mean of daily mean relative humidity (%)
      roni_lead      Sep-Nov RONI of the previous calendar year (the predictor)

  data/processed/daily_panel.parquet      one row per city x season x day (for quantile regression)

Season-years: DJF 2025 = Dec 2024 + Jan-Feb 2025. A season is kept only if at least
MIN_SEASON_COVERAGE of its days exist.
"""
import numpy as np
import pandas as pd
import config as C


def read_roni(path=C.RONI_FILE):
    """CPC RONI table (SEAS YR ANOM, overlapping 3-month seasons) -> DataFrame(season, year, roni)."""
    df = pd.read_csv(path, sep=r"\s+")
    df.columns = ["season", "year", "roni"]
    return df.astype({"year": int, "roni": float})


def roni_lead(roni, years):
    """Sep-Nov RONI of year t-1 for each target season-year t."""
    son = roni[roni["season"] == C.PREDICTOR_SEASON].set_index("year")["roni"]
    return pd.Series([son.get(y - 1, np.nan) for y in years], index=years)


def assign_season_year(d, months):
    d = d[d["date"].dt.month.isin(months)].copy()
    d["year"] = d["date"].dt.year
    if months[0] > months[-1]:                       # DJF: December belongs to the next year
        d.loc[d["date"].dt.month >= months[0], "year"] += 1
    return d


def main():
    roni = read_roni()
    seasonal_rows, daily_rows = [], []
    missing = []
    for city, region, lat, lon in C.C40_CITIES:
        f = C.ERA5_DIR / f"{city}.parquet"
        if not f.exists():
            missing.append(city)
            continue
        d = pd.read_parquet(f)
        d["date"] = pd.to_datetime(d["date"])
        for season, months in C.SEASONS.items():
            s = assign_season_year(d, months)
            s = s[(s["year"] >= C.FIT_START) & (s["year"] <= C.FIT_END)]
            n_full = s.groupby("year").size().max()
            g = s.groupby("year")
            agg = pd.DataFrame({
                "n_days": g.size(),
                "temperature": g["tmean"].mean(),
                "precipitation": g["precip"].sum(),
                "wet_day_share": g["precip"].apply(lambda v: 100 * (v >= C.WET_DAY_MM).mean()),
                "rel_humidity": g["rh"].mean(),
            })
            agg = agg[agg["n_days"] >= C.MIN_SEASON_COVERAGE * n_full]
            agg["roni_lead"] = roni_lead(roni, agg.index).values
            agg = agg.reset_index().assign(city=city, region=region, lat=lat, lon=lon, season=season)
            seasonal_rows.append(agg)
            keep_years = set(agg["year"])
            s = s[s["year"].isin(keep_years)]
            daily_rows.append(s[["date", "year", "tmean", "precip", "rh"]].assign(city=city, season=season))
    seasonal = pd.concat(seasonal_rows, ignore_index=True).dropna(subset=["roni_lead"])
    daily = pd.concat(daily_rows, ignore_index=True)
    daily = daily.merge(seasonal[["city", "season", "year", "roni_lead"]], on=["city", "season", "year"])
    C.PROCESSED.mkdir(parents=True, exist_ok=True)
    seasonal.to_parquet(C.PROCESSED / "seasonal_panel.parquet", index=False)
    daily.to_parquet(C.PROCESSED / "daily_panel.parquet", index=False)
    son = roni[roni["season"] == C.PREDICTOR_SEASON]
    print(f"Cities: {seasonal['city'].nunique()} of {len(C.C40_CITIES)}"
          + (f" (missing files: {missing})" if missing else ""))
    print(f"Season-years: {seasonal.groupby(['city', 'season']).size().describe()[['min', 'max']].to_dict()}")
    print(f"Years {seasonal['year'].min()}-{seasonal['year'].max()}; daily rows {len(daily):,}")
    print(f"Latest SON RONI in file: {son['year'].max()} ({son['roni'].iloc[-1]:+.2f}); "
          f"forecast uses SON 2026 = {C.SON_2026_RONI:+.2f} ± {C.SON_2026_RONI_SD} (config)")


if __name__ == "__main__":
    main()

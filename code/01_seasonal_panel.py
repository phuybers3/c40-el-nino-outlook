"""Collapse the daily panel to one row per city, season and year.

    python code/01_seasonal_panel.py [--daily PATH] [--cities PATH] [--out PATH]

Season mean temperature, season rainfall total, the share of days with at
least WET_MM of rain, and season mean relative humidity, with the Sep-Nov
RONI of the preceding year carried through. A season is kept only when at
least 97% of its days are present; in the ERA5 panel shipped on 2026-10-31
every season has 90 to 92 days, so the rule never bites there.
"""
import argparse
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WET_MM = 1.0
MIN_DAY_SHARE = 0.97
SEASON_DAYS = {"DJF": 90, "MAM": 92}  # non-leap lengths; the rule is applied to these
COLUMNS = ["year", "n_days", "temperature", "precipitation", "wet_day_share", "rel_humidity",
           "roni_lead", "city", "region", "lat", "lon", "season"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--daily", default=ROOT / "data/processed/daily_panel.parquet")
    ap.add_argument("--cities", default=ROOT / "data/cities.csv")
    ap.add_argument("--out", default=ROOT / "data/processed/seasonal_panel.csv")
    args = ap.parse_args()

    d = pd.read_parquet(args.daily)
    d["wet"] = (d["precip"] >= WET_MM).astype(float)
    g = d.groupby(["city", "season", "year"], sort=False)
    out = g.agg(n_days=("tmean", "size"), temperature=("tmean", "mean"), precipitation=("precip", "sum"),
                wet_day_share=("wet", "mean"), rel_humidity=("rh", "mean"), roni_lead=("roni_lead", "first")).reset_index()
    out["wet_day_share"] *= 100
    expected = out["season"].map(SEASON_DAYS)
    keep = out["n_days"] >= MIN_DAY_SHARE * expected
    if (~keep).any():
        print("dropping incomplete seasons:", out.loc[~keep, ["city", "season", "year", "n_days"]].to_dict("records"))
    out = out[keep]
    cities = pd.read_csv(args.cities)
    out = out.merge(cities[["city", "region", "lat", "lon"]], on="city", how="left")
    out = out.sort_values(["region", "city", "season", "year"], kind="stable") if False else out
    out[COLUMNS].to_csv(args.out, index=False)
    out[COLUMNS].to_parquet(Path(args.out).with_suffix(".parquet"), index=False)
    print(f"{len(out)} rows -> {args.out}")


if __name__ == "__main__":
    main()

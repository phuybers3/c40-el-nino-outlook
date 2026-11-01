"""Write the data files the site reads: site/data/meta.json, cities.json and city/<slug>.json.

    python code/06_export_site.py [--facts PATH] [--paragraphs PATH] [--site-data DIR]

Inputs: data/processed/city_facts.json and facts_meta.json (04), the seasonal
and daily panels (01), linear_results.csv (02), quantile_results.csv (03),
data/cities.csv, and the paragraphs JSON written by 05 (keyed "City|SEASON").
Scalars are rounded to 4 decimals and series to 3, as in the files shipped on
2026-10-31; the layout is unchanged so the page code needs no change for a
re-export, and new fields are added alongside the old ones.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
VARS = ["temperature", "precipitation", "wet_day_share", "rel_humidity"]
QVARS = {"temperature": "tmean", "precipitation": "precip", "rel_humidity": "rh"}
WET_MM = 1.0


def rnd(x, dp=4):
    if x is None:
        return None
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, np.integer)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return None if np.isnan(x) else round(float(x), dp)
    if isinstance(x, dict):
        return {k: rnd(v, dp) for k, v in x.items()}
    if isinstance(x, list):
        return [rnd(v, dp) for v in x]
    return x


def yearly_percentiles(daily: pd.DataFrame, years: list[int], var: str) -> dict:
    """5th, 50th and 95th percentile of the daily values in each season; wet days only for rain."""
    d = daily[daily["precip"] >= WET_MM] if var == "precipitation" else daily
    col = QVARS[var]
    out = {"p05": [], "p50": [], "p95": []}
    groups = {y: g[col].to_numpy() for y, g in d.groupby("year")}
    for y in years:
        v = groups.get(y)
        if v is None or len(v) == 0:
            for k in out:
                out[k].append(None)
        else:
            p = np.percentile(v, [5, 50, 95])
            for k, val in zip(out, p):
                out[k].append(round(float(val), 3))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--facts", default=ROOT / "data/processed/city_facts.json")
    ap.add_argument("--facts-meta", default=ROOT / "data/processed/facts_meta.json")
    ap.add_argument("--paragraphs", default=ROOT / "data/processed/city_paragraphs.json")
    ap.add_argument("--paragraph-source", default="docs/city_paragraphs.md")
    ap.add_argument("--seasonal", default=ROOT / "data/processed/seasonal_panel.csv")
    ap.add_argument("--daily", default=ROOT / "data/processed/daily_panel.parquet")
    ap.add_argument("--linear", default=ROOT / "data/processed/linear_results.csv")
    ap.add_argument("--quantiles", default=ROOT / "data/processed/quantile_results.csv")
    ap.add_argument("--cities", default=ROOT / "data/cities.csv")
    ap.add_argument("--site-data", default=ROOT / "site/data")
    ap.add_argument("--exported", default=dt.date.today().isoformat())
    ap.add_argument("--index-only", action="store_true", help="rewrite cities.json and meta.json but not the city files")
    args = ap.parse_args()

    facts = json.load(open(args.facts))
    fmeta = json.load(open(args.facts_meta))
    paras = json.load(open(args.paragraphs)) if Path(args.paragraphs).exists() else {}
    seasonal = pd.read_csv(args.seasonal)
    daily = pd.read_parquet(args.daily)
    lin = pd.read_csv(args.linear).set_index(["city", "season", "variable"])
    qt = pd.read_csv(args.quantiles)
    qt["quantile"] = qt["quantile"].astype(str)
    qt = qt[qt["quantile"].isin(["0.05", "0.5", "0.95"])].set_index(["city", "season", "variable", "quantile"])
    cities = pd.read_csv(args.cities).set_index("city")
    out_dir = Path(args.site_data)
    (out_dir / "city").mkdir(parents=True, exist_ok=True)
    for stale in (out_dir / "city").glob("*.json"):
        stale.unlink()

    by_city: dict[str, dict] = {}
    for rec in facts:
        city, season = rec["city"], rec["season"]
        meta = cities.loc[city]
        c = by_city.setdefault(city, {"name": city, "slug": meta["slug"], "region": rec["region"],
                                      "lat": float(meta["lat"]), "lon": float(meta["lon"]), "seasons": {}})
        panel = seasonal[(seasonal["city"] == city) & (seasonal["season"] == season)].sort_values("year")
        d = daily[(daily["city"] == city) & (daily["season"] == season)]
        years = [int(y) for y in panel["year"]]
        s = {
            "season_name": rec["season_name"], "years": years,
            "roni_lead": [round(float(v), 2) for v in panel["roni_lead"]],
            "paragraph": paras.get(f"{city}|{season}", ""),
            "variables": {},
        }
        for var in VARS:
            x = dict(rec["variables"][var])
            lr = lin.loc[(city, season, var)]
            v = {k: rnd(val) for k, val in x.items()}
            v["values"] = [round(float(val), 3) for val in panel[var]]
            v["forecast_mean"] = rnd(x["normal_1991_2020"] + x["expected_anomaly_2027"])
            v["forecast_sd"] = rnd(x.get("forecast_sd"))
            v["fit"] = rnd({"a2027": lr["a2027"], "b": x.get("enso_effect_shrunk_per_degC", x["enso_effect_per_degC"]),
                            "c": lr["trend_per_decade"] / 10, "tercile_low": lr["tercile_low"], "tercile_high": lr["tercile_high"]})
            if var in QVARS:
                v["yearly"] = yearly_percentiles(d, years, var)
                v["quantile_fit"] = None  # null for rain seasons too dry to fit (9 cells)
            if var in QVARS and "percentiles" in x:
                qf = {}
                for key, qq in [("p05", "0.05"), ("p50", "0.5"), ("p95", "0.95")]:
                    r = qt.loc[(city, season, var, qq)]
                    qf[key] = rnd({"intercept": r["intercept"], "b": r["enso_effect"], "c": r["trend_per_decade"] / 10, "tbar": r["tbar"]})
                v["quantile_fit"] = qf
            s["variables"][var] = v
        # The map index rounds the unrounded facts. Temperature stays at the top level for the
        # cover counts; every variable sits under "variables" for the map's variable switch.
        def brief(x):
            return {"confidence": x["confidence"], "survives_fdr": x["survives_fdr"], "effect": round(x["effect_this_season"], 3),
                    "size": x["size"], "p_above": round(x["p_above"], 3), "p_below": round(x["p_below"], 3)}
        s["_index"] = {**brief(rec["variables"]["temperature"]), "has_paragraph": bool(s["paragraph"]),
                       "variables": {var: brief(x) for var, x in rec["variables"].items()}}
        c["seasons"][season] = s

    index = []
    for c in by_city.values():
        seasons = {season: s.pop("_index") for season, s in c["seasons"].items()}
        index.append({"name": c["name"], "slug": c["slug"], "region": c["region"], "lat": c["lat"], "lon": c["lon"], "seasons": seasons})
        if not args.index_only:
            (out_dir / "city" / f"{c['slug']}.json").write_text(json.dumps(c, ensure_ascii=False, separators=(",", ":")))
    (out_dir / "cities.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")))

    meta = {
        "son_2026_roni": fmeta["son_2026_roni"], "son_2026_roni_sd": fmeta["son_2026_roni_sd"],
        "son_2026_estimated": fmeta["son_2026_estimated"], "son_2026_roni_source": fmeta.get("son_2026_roni_source", ""),
        "forecast_year": fmeta["forecast_year"], "fit_years": fmeta["fit_years"], "baseline": fmeta["baseline"],
        "typical_el_nino": fmeta["typical_el_nino"], "wet_day_mm": fmeta["wet_day_mm"],
        "confidence": fmeta["confidence"], "strong_is_fdr": fmeta.get("strong_is_fdr", False), "shrink": fmeta.get("shrink", False),
        "size": fmeta["size"], "dry_season_mm": fmeta.get("dry_season_mm"), "n_tests": fmeta.get("n_tests", 768),
        "roni_record_max": fmeta.get("roni_record_max"), "rules": fmeta.get("rules", "legacy"),
        "quantile_bootstrap_reps": fmeta.get("quantile_bootstrap_reps"), "quantile_capped_share": fmeta.get("quantile_capped_share"),
        "paragraph_source": args.paragraph_source, "exported": args.exported,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    print(f"{len(by_city)} city files, cities.json and meta.json -> {out_dir}")


if __name__ == "__main__":
    main()

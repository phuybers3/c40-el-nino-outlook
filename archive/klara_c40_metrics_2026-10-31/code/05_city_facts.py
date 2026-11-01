"""
Step 5 - Per-city facts for the paragraphs, and CSV copies of every results table.

Re-computes in Python exactly what the spreadsheet formulas compute (labels, this season's effect,
size, forecast odds), using the values in config.py, and writes:
  data/processed/city_facts.json        one entry per city x season, everything a paragraph needs
  data/processed/*.csv                  linear_results, quantile_results, seasonal_panel
The paragraphs are written from city_facts.json following docs/translation_guide.md.
"""
import json
import numpy as np
import pandas as pd
from scipy.stats import norm
import config as C


def label(value, table):
    out = table[0][1]
    for lo, lab in table:
        if value >= lo:
            out = lab
    return out


WORDS = {"temperature": ("a warmer-than-normal season", "a cooler-than-normal season"),
         "precipitation": ("a wetter-than-normal season", "a drier-than-normal season"),
         "wet_day_share": ("more rainy days than normal", "fewer rainy days than normal"),
         "rel_humidity": ("a more humid season than normal", "a less humid season than normal")}


def forecast_words(var, pb, pn, pa):
    """Same rule as the spreadsheet's 'Forecast in words' column (never prints 99-100%)."""
    m = max(pb, pn, pa)
    if m < 0.4:
        return "Near-equal odds of below, near and above normal"
    lead = ("Very likely (>95%)" if m > 0.95 else f"Likely ({m:.0%})" if m >= 0.66 else
            f"More likely than not ({m:.0%})" if m >= 0.5 else f"Slightly favored ({m:.0%})")
    cat = WORDS[var][0] if m == pa else (WORDS[var][1] if m == pb else "a near-normal season")
    return f"{lead}: {cat}"


def main():
    lin = pd.read_parquet(C.PROCESSED / "linear_results.parquet")
    qr = pd.read_parquet(C.PROCESSED / "quantile_results.parquet")
    x, sx = C.SON_2026_RONI, C.SON_2026_RONI_SD
    facts = []
    for (city, season), g in lin.groupby(["city", "season"], sort=False):
        entry = {"city": city, "region": g["region"].iloc[0], "season": season,
                 "season_name": {"DJF": "Dec 2026–Feb 2027", "MAM": "Mar–May 2027"}[season],
                 "son_2026_roni": x, "son_2026_roni_estimated": sx > 0, "variables": {}}
        for _, r in g.iterrows():
            eff = r["enso_effect"] * x
            mean = r["a2027"] + eff
            sd = np.sqrt(r["sd_residual"] ** 2 + r["var_a2027"] + x ** 2 * r["var_b"] + 2 * x * r["cov_a2027_b"]
                         + r["enso_effect"] ** 2 * sx ** 2)
            pb = norm.cdf(r["tercile_low"], mean, sd)
            pa = 1 - norm.cdf(r["tercile_high"], mean, sd)
            ratio = abs(eff) / r["sd_residual"]
            v = {
                "normal_1991_2020": r["normal_1991_2020"],
                "trend_per_decade": r["trend_per_decade"], "trend_p": r["trend_p"],
                "trend_total_since_1951": r["trend_per_decade"] * (C.FIT_END - C.FIT_START + 1) / 10,
                "enso_effect_per_degC": r["enso_effect"], "enso_p": r["enso_p"],
                "confidence": label(r["enso_p"], C.CONFIDENCE), "survives_fdr": bool(r["enso_survives_fdr"]),
                "fraction_explained": r["partial_r2"], "intrinsic_sd": r["sd_residual"],
                "effect_this_season": eff, "effect_ratio": ratio, "size": label(ratio, C.SIZE),
                "size_typical_el_nino": label(abs(r["enso_effect"] * C.TYPICAL_EL_NINO) / r["sd_residual"], C.SIZE),
                "once_every_n_years_without_el_nino": (None if ratio < 0.5 else
                                                      (">100" if 1 / norm.sf(ratio) > 100 else round(1 / norm.sf(ratio)))),
                "expected_anomaly_2027": mean - r["normal_1991_2020"],
                "p_below": pb, "p_near": 1 - pb - pa, "p_above": pa,
                "forecast_words": forecast_words(r["variable"], pb, 1 - pb - pa, pa),
                "within_record": bool(r["roni_lead_min"] <= x <= r["roni_lead_max"]),
            }
            if r["variable"] == "temperature" and r["trend_per_decade"] > 0 and r["trend_p"] < 0.05:
                v["years_of_warming_equivalent"] = eff / (r["trend_per_decade"] / 10)
            if r["variable"] == "precipitation" and r["normal_1991_2020"] > 0:
                v["trend_pct_of_normal_per_decade"] = 100 * r["trend_per_decade"] / r["normal_1991_2020"]
            q = qr[(qr["city"] == city) & (qr["season"] == season) & (qr["variable"] == r["variable"])]
            if not q.empty:
                pct = {}
                for _, qq in q[q["quantile"] != "95th-5th"].iterrows():
                    pct[{"0.05": "p05", "0.5": "p50", "0.95": "p95"}[qq["quantile"]]] = {
                        "trend_per_decade": qq["trend_per_decade"], "trend_p": qq["trend_p"],
                        "enso_effect_per_degC": qq["enso_effect"], "enso_p": qq["enso_p"],
                        "confidence": label(qq["enso_p"], C.CONFIDENCE), "shift_this_season": qq["enso_effect"] * x,
                        "lines_cross": bool(qq["crossing_points"] > 0)}
                tail = q[q["quantile"] == "95th-5th"].groupby("city").first().iloc[0]
                pct["tails"] = {k: tail[k] for k in ["enso_difference", "enso_difference_p",
                                                      "trend_difference", "trend_difference_p"]}
                v["percentiles"] = pct
            entry["variables"][r["variable"]] = v
        facts.append(entry)

    def clean(o):
        if isinstance(o, dict):
            return {k: clean(v) for k, v in o.items()}
        if isinstance(o, float):
            return None if not np.isfinite(o) else round(o, 4)
        if isinstance(o, (np.floating, np.integer)):
            return clean(float(o))
        return o
    with open(C.PROCESSED / "city_facts.json", "w", encoding="utf-8") as f:
        json.dump(clean(facts), f, ensure_ascii=False, indent=1)
    lin.to_csv(C.PROCESSED / "linear_results.csv", index=False)
    qr.to_csv(C.PROCESSED / "quantile_results.csv", index=False)
    pd.read_parquet(C.PROCESSED / "seasonal_panel.parquet").to_csv(C.PROCESSED / "seasonal_panel.csv", index=False)
    print(f"Wrote city_facts.json ({len(facts)} city-seasons) and CSV copies to {C.PROCESSED}")


if __name__ == "__main__":
    main()

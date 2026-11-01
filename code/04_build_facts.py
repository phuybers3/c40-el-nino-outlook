"""Turn the fitted tables into the per-city facts the paragraphs and the site use.

    python code/04_build_facts.py --rules legacy|new [--roni 2.2 --roni-sd 0.25 --roni-estimated]
                                  [--roni-source TEXT] [--no-shrink] [--out PATH]

Reads data/processed/linear_results.csv and quantile_results.csv and writes
data/processed/city_facts.json: a list of 192 records (96 cities x 2 seasons),
each holding the four variables with their trend, El Niño effect, confidence
and size labels, return period, and the forecast-year outlook. Also writes
data/processed/facts_meta.json with the label tables and the RONI assumption,
which the site exporter copies into site/data/meta.json.

Rule sets. "legacy" reproduces the facts shipped on 2026-10-31 exactly (see
code/validate_facts.py): six confidence tiers cut on the p-value alone, and the
outlook centre uses the fitted El Niño effect at face value whatever its
confidence. "new" is the revision of 2026-11: four tiers with Strong defined
by surviving the false-discovery-rate correction, the El Niño effect shrunk
toward zero by an empirical-Bayes factor before it enters the outlook and the
size label, an explicit split of the forecast anomaly into its trend and El
Niño parts, a dry-season flag for rainfall normals under 25 mm, and even-odds
wording for chances between 45% and 55%.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
VARS = ["temperature", "precipitation", "wet_day_share", "rel_humidity"]
QVARS = ["temperature", "precipitation", "rel_humidity"]  # quantile fits exist for these
SEASON_NAME = {"DJF": "Dec {y0}–Feb {y1}", "MAM": "Mar–May {y1}"}
TYPICAL_EL_NINO = 1.5  # RONI of a typical event, for the size_typical label
SIZE_TIERS = [[0.0, "Negligible"], [0.25, "Noticeable"], [0.5, "Substantial"], [1.0, "Dominant"]]
RETURN_PERIOD_MIN_RATIO = 0.5  # below half a normal swing the return period is not quoted
DRY_SEASON_MM = 25.0

RULES = {
    "legacy": {
        # [lower p bound, label]; the label applies from that p up to the next row's p.
        "confidence": [[0.0, "Strong"], [0.01, "Clear"], [0.05, "Modest"], [0.1, "Detectable"],
                       [0.2, "Weak"], [0.5, "No identifiable effect"]],
        "strong_is_fdr": False,
        "shrink": False,
        "even_odds": False,
        "dry_season_flag": False,
    },
    "new": {
        "confidence": [[0.0, "Strong"], [0.0, "Clear"], [0.05, "Suggestive"], [0.1, "No identifiable effect"]],
        "strong_is_fdr": True,
        "shrink": True,
        "even_odds": True,
        "dry_season_flag": True,
    },
}
# Wording of the outlook, keyed on the largest of the three tercile chances.
# Boundaries recovered from the shipped facts: 0.95, 0.66, 0.5, 0.4 (the
# "likely" cut sits at 0.66: 0.6598 was still "more likely than not").
DIRECTION = {
    "temperature": ("a cooler-than-normal season", "a near-normal season", "a warmer-than-normal season"),
    "precipitation": ("a drier-than-normal season", "a near-normal season", "a wetter-than-normal season"),
    "wet_day_share": ("fewer rainy days than normal", "a near-normal season", "more rainy days than normal"),
    "rel_humidity": ("a less humid season than normal", "a near-normal season", "a more humid season than normal"),
}


def label_from_table(table: list[list], x: float) -> str:
    out = table[0][1]
    for lo, name in table:
        if x >= lo:
            out = name
    return out


def confidence_label(p: float, survives_fdr: bool, rules: dict) -> str:
    if rules["strong_is_fdr"]:
        if survives_fdr:
            return "Strong"
        return label_from_table(rules["confidence"][1:], p)
    return label_from_table(rules["confidence"], p)


def forecast_words(var: str, p_below: float, p_near: float, p_above: float, rules: dict) -> str:
    probs = [p_below, p_near, p_above]
    i = int(np.argmax(probs))
    m = probs[i]
    what = DIRECTION[var][i]
    pct = int(round(m * 100))
    if m >= 0.95:
        return f"Very likely (>95%): {what}"
    if m >= 0.66:
        return f"Likely ({pct}%): {what}"
    if rules["even_odds"] and 0.45 <= m < 0.55:
        return f"About even odds ({pct}%): {what}"
    if m >= 0.5:
        return f"More likely than not ({pct}%): {what}"
    if m >= 0.4:
        return f"Slightly favored ({pct}%): {what}"
    return "Near-equal odds of below, near and above normal"


def return_period(ratio: float):
    """How often a season this far from the trend occurs by chance: 1 / P(Z > ratio).

    Quoted only from half a normal swing upward, rounded to whole years, and
    written ">100" beyond a century (9 of 768 cells in the shipped facts).
    """
    if ratio < RETURN_PERIOD_MIN_RATIO:
        return None
    years = 1 / stats.norm.sf(ratio)
    return ">100" if years > 100 else int(round(years))


def shrink_factors(lin: pd.DataFrame) -> pd.Series:
    """Empirical-Bayes shrinkage of b within each season x variable.

    tau² is the spread of true effects across the 96 cities, estimated by the
    method of moments as var(b) − mean(se²) and floored at zero. Each city's
    factor tau²/(tau² + se²) multiplies its fitted b. Across the eight groups
    the mean factor is 0.64 to 0.87; the least certain cells drop to a sixth.
    """
    out = pd.Series(1.0, index=lin.index)
    for _, g in lin.groupby(["season", "variable"]):
        tau2 = max(0.0, g["enso_effect"].var(ddof=1) - (g["enso_se"] ** 2).mean())
        out[g.index] = tau2 / (tau2 + g["enso_se"] ** 2)
    return out


def percentile_block(qrows: pd.DataFrame, roni: float, rules: dict) -> dict | None:
    """The 5th/50th/95th quantile fits of one cell plus the tail-difference tests."""
    if qrows.empty:
        return None
    out = {}
    for key, qq in [("p05", "0.05"), ("p50", "0.5"), ("p95", "0.95")]:
        r = qrows[qrows["quantile"] == qq]
        if r.empty:
            return None
        r = r.iloc[0]
        out[key] = {
            "trend_per_decade": float(r["trend_per_decade"]), "trend_p": float(r["trend_p"]),
            "enso_effect_per_degC": float(r["enso_effect"]), "enso_p": float(r["enso_p"]),
            "confidence": confidence_label(float(r["enso_p"]), bool(r["enso_survives_fdr"]), rules),
            "shift_this_season": float(r["enso_effect"]) * roni,
            "lines_cross": bool(float(r["crossing_points"]) > 0),
        }
    diff = qrows[qrows["quantile"] == "95th-5th"]
    tails = {}
    for _, r in diff.iterrows():
        if pd.notna(r["enso_difference"]):
            tails["enso_difference"] = float(r["enso_difference"]); tails["enso_difference_p"] = float(r["enso_difference_p"])
        if pd.notna(r["trend_difference"]):
            tails["trend_difference"] = float(r["trend_difference"]); tails["trend_difference_p"] = float(r["trend_difference_p"])
    out["tails"] = tails
    return out


def variable_facts(r: pd.Series, qrows: pd.DataFrame, roni: float, roni_sd: float, factor: float,
                   forecast_year: int, rules: dict) -> dict:
    b_raw = float(r["enso_effect"])
    b = b_raw * factor if rules["shrink"] else b_raw
    sd = float(r["sd_residual"])
    normal = float(r["normal_1991_2020"])
    effect = b * roni
    ratio = abs(effect) / sd
    conf = confidence_label(float(r["enso_p"]), bool(r["enso_survives_fdr"]), rules)

    # Outlook: trend line in the forecast year plus the El Niño term; the spread
    # adds parameter uncertainty and the uncertainty of this year's RONI. Under
    # shrinkage the posterior variance of b is factor x se², and the covariance
    # with the trend level scales the same way.
    f = factor if rules["shrink"] else 1.0
    mean = float(r["a2027"]) + effect
    var = sd ** 2 + float(r["var_a2027"]) + roni ** 2 * f * float(r["var_b"]) + 2 * roni * f * float(r["cov_a2027_b"]) + b ** 2 * roni_sd ** 2
    fsd = float(np.sqrt(var))
    p_below = float(stats.norm.cdf((float(r["tercile_low"]) - mean) / fsd))
    p_above = float(stats.norm.sf((float(r["tercile_high"]) - mean) / fsd))
    p_near = 1.0 - p_below - p_above

    out = {
        "normal_1991_2020": normal,
        "trend_per_decade": float(r["trend_per_decade"]),
        "trend_p": float(r["trend_p"]),
        "trend_total_since_1951": float(r["trend_per_decade"]) * int(r["n_years"]) / 10,
        "enso_effect_per_degC": b_raw,
        "enso_p": float(r["enso_p"]),
        "confidence": conf,
        "survives_fdr": bool(r["enso_survives_fdr"]),
        "fraction_explained": float(r["partial_r2"]),
        "intrinsic_sd": sd,
        "effect_this_season": effect,
        "effect_ratio": ratio,
        "size": label_from_table(SIZE_TIERS, ratio),
        "size_typical_el_nino": label_from_table(SIZE_TIERS, abs(b) * TYPICAL_EL_NINO / sd),
        "once_every_n_years_without_el_nino": return_period(ratio),
        "expected_anomaly_2027": mean - normal,
        "forecast_mean": mean, "forecast_sd": fsd,
        "p_below": p_below, "p_near": p_near, "p_above": p_above,
        "forecast_words": forecast_words(r["variable"], p_below, p_near, p_above, rules),
        "within_record": bool(float(r["roni_lead_min"]) <= roni <= float(r["roni_lead_max"])),
    }
    if rules["shrink"]:
        out["enso_effect_shrunk_per_degC"] = b
        out["shrink_factor"] = float(factor)
        out["effect_this_season_raw"] = b_raw * roni
    if rules["dry_season_flag"] or rules["shrink"]:
        out["trend_part_2027"] = float(r["a2027"]) - normal
        out["roni_upper_within_record"] = bool(roni + roni_sd <= float(r["roni_lead_max"]))
    if r["variable"] == "temperature":
        # Years of trend that the El Niño push equals; left out when the trend is
        # not clearly positive (10 of 192 cells in the shipped facts). The bar is
        # p < 0.05, as in the original 05_city_facts.py and the workbook formula.
        if float(r["trend_per_decade"]) > 0 and float(r["trend_p"]) < 0.05:
            out["years_of_warming_equivalent"] = effect / (float(r["trend_per_decade"]) / 10)
    if r["variable"] == "precipitation":
        out["trend_pct_of_normal_per_decade"] = float(r["trend_per_decade"]) / normal * 100
        if rules["dry_season_flag"]:
            out["dry_season"] = bool(normal < DRY_SEASON_MM)
    if r["variable"] in QVARS:
        pc = percentile_block(qrows, roni, rules)
        if pc is not None:
            out["percentiles"] = pc
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--rules", choices=RULES, default="new")
    ap.add_argument("--linear", default=ROOT / "data/processed/linear_results.csv")
    ap.add_argument("--quantiles", default=ROOT / "data/processed/quantile_results.csv")
    ap.add_argument("--out", default=ROOT / "data/processed/city_facts.json")
    ap.add_argument("--meta-out", default=ROOT / "data/processed/facts_meta.json")
    ap.add_argument("--forecast-year", type=int, default=2027)
    ap.add_argument("--roni", type=float, default=2.2, help="Sep-Nov RONI of the year before the forecast season")
    ap.add_argument("--roni-sd", type=float, default=0.25)
    ap.add_argument("--roni-estimated", action="store_true", default=True)
    ap.add_argument("--roni-observed", dest="roni_estimated", action="store_false")
    ap.add_argument("--roni-source", default="", help="one sentence on where the RONI estimate comes from")
    ap.add_argument("--no-shrink", action="store_true", help="switch shrinkage off under the new rules")
    args = ap.parse_args()
    rules = dict(RULES[args.rules])
    if args.no_shrink:
        rules["shrink"] = False

    lin = pd.read_csv(args.linear)
    qt = pd.read_csv(args.quantiles)
    qt["quantile"] = qt["quantile"].astype(str)
    median_rows = qt[qt["quantile"] == "0.5"]  # one row per cell carries the fit counts
    capped_share = float(median_rows["fits_hit_iteration_cap"].sum() / median_rows["fits"].sum())
    bootstrap_reps = int(round(median_rows["fits"].iloc[0] / 3 - 1))
    factors = shrink_factors(lin)
    y1 = args.forecast_year
    records = []
    for (city, season), g in lin.groupby(["city", "season"], sort=False):
        rec = {
            "city": city, "region": g.iloc[0]["region"], "season": season,
            "season_name": SEASON_NAME[season].format(y0=y1 - 1, y1=y1),
            "son_2026_roni": args.roni, "son_2026_roni_estimated": bool(args.roni_estimated),
            "variables": {},
        }
        for var in VARS:
            r = g[g["variable"] == var].iloc[0]
            qrows = qt[(qt["city"] == city) & (qt["season"] == season) & (qt["variable"] == var)]
            rec["variables"][var] = variable_facts(r, qrows, args.roni, args.roni_sd, float(factors[r.name]), y1, rules)
        records.append(rec)

    Path(args.out).write_text(json.dumps(records, indent=1, ensure_ascii=False))
    meta = {
        "rules": args.rules,
        "son_2026_roni": args.roni, "son_2026_roni_sd": args.roni_sd, "son_2026_estimated": bool(args.roni_estimated),
        "son_2026_roni_source": args.roni_source,
        "forecast_year": y1,
        "fit_years": [int(lin["first_year"].min()), int(lin["last_year"].max())],
        "baseline": [1991, 2020],
        "typical_el_nino": TYPICAL_EL_NINO,
        "wet_day_mm": 1.0,
        "confidence": rules["confidence"],
        "strong_is_fdr": rules["strong_is_fdr"],
        "shrink": rules["shrink"],
        "size": SIZE_TIERS,
        "dry_season_mm": DRY_SEASON_MM if rules["dry_season_flag"] else None,
        "n_tests": int(len(lin)),
        "roni_record_max": float(lin["roni_lead_max"].max()),
        "quantile_bootstrap_reps": bootstrap_reps,
        "quantile_capped_share": capped_share,
    }
    Path(args.meta_out).write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    print(f"{len(records)} records -> {args.out} (rules={args.rules}, shrink={rules['shrink']}, RONI {args.roni}±{args.roni_sd})")


if __name__ == "__main__":
    main()

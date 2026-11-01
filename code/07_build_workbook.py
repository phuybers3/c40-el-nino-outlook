"""Build C40_ENSO_outlook.xlsx from the fitted tables under the current rule set.

    python code/07_build_workbook.py [--linear PATH] [--quantiles PATH] [--meta PATH] [--out PATH]

Tabs
  README       what is where and how to update the outlook
  Settings     the inputs a reader may change: the Sep-Nov RONI and its spread,
               the shrinkage switch and the eight tau^2 values behind the
               shrinkage factors, the dry-season cut, the typical El Nino
  Lookup       the confidence, size, outlook-wording and direction tables
  Summary      one row per city and season, headline numbers pulled from Linear
  Linear       one row per city, season and variable: trend, El Nino effect,
               labels, the 2027 outlook and its words
  Quantiles    one row per city, season, variable and percentile (5th, 50th, 95th)
  Tails        95th minus 5th percentile: does El Nino or the trend move the
               extremes differently?
  Definitions  every column explained

Fitted statistics are values from data/processed/linear_results.csv and
quantile_results.csv. Every derived column is a live formula: the confidence
label (Strong = survives the false-discovery-rate correction, then Clear,
Suggestive and no effect on the p-value), the shrinkage factor
tau^2 / (tau^2 + se^2), the shrunk effect this season, the size label, the
2027 centre and spread, the tercile chances, the return period and the words
with the even-odds band. Changing the RONI on the Settings tab updates the
whole workbook. The rule tables come from code/04_build_facts.py and
data/processed/facts_meta.json; code/validate_workbook.py evaluates the
formulas in Python and compares every cell with data/processed/city_facts.json,
because the file is never calculated by Excel on disk.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
VARS = ["temperature", "precipitation", "wet_day_share", "rel_humidity"]
QVARS = ["temperature", "precipitation", "rel_humidity"]
SEASONS = ["DJF", "MAM"]
VNAME = {"temperature": "Mean temperature", "precipitation": "Rainfall total",
         "wet_day_share": "Share of wet days", "rel_humidity": "Relative humidity"}
UNITS = {"temperature": "°C", "precipitation": "mm", "wet_day_share": "% of days", "rel_humidity": "% RH"}
QNAME = {"temperature": "Daily mean temperature", "precipitation": "Wet-day rainfall", "rel_humidity": "Daily relative humidity"}
QUNITS = {"temperature": "°C", "precipitation": "mm/day", "rel_humidity": "% RH"}
PCT_NAME = {"0.05": "5th", "0.5": "50th", "0.95": "95th"}
# Wording of the outlook by variable and most likely tercile, as in 04_build_facts.py.
DIRECTION = {
    "temperature": ("a cooler-than-normal season", "a near-normal season", "a warmer-than-normal season"),
    "precipitation": ("a drier-than-normal season", "a near-normal season", "a wetter-than-normal season"),
    "wet_day_share": ("fewer rainy days than normal", "a near-normal season", "more rainy days than normal"),
    "rel_humidity": ("a less humid season than normal", "a near-normal season", "a more humid season than normal"),
}
TAIL_NAMES = {"temperature": ("coldest days", "hottest days"), "precipitation": ("light-rain days", "heavy-rain days"),
              "rel_humidity": ("driest-air days", "most humid days")}
CONF_PHRASES = {
    "Strong": "The El Niño effect survives the false-discovery-rate correction across all 768 tests.",
    "Clear": "p < 0.05 on its own, but not after the correction for 768 tests.",
    "Suggestive": "p between 0.05 and 0.10: a hint, not a finding.",
    "No identifiable effect": "p of 0.10 or more.",
}
SIZE_PHRASES = {"Negligible": "Small next to a normal year-to-year swing; unlikely to be noticed.",
                "Noticeable": "A quarter to a half of a normal swing; a modest tilt to the season.",
                "Substantial": "Half to a whole normal swing; a shift people would likely notice.",
                "Dominant": "Larger than a normal year-to-year swing; would dominate the season."}
# Outlook wording: [largest tercile chance from (>=), wording, upper bound for the even-odds band]
WORDING = [[0.95, "Very likely (>95%)", None], [0.66, "Likely", None], [0.45, "About even odds", 0.55],
           [0.5, "More likely than not", None], [0.4, "Slightly favored", None],
           [None, "Near-equal odds of below, near and above normal", None]]

FONT = "Arial"
H_FILL = PatternFill("solid", fgColor="1F3A5F")
H_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
B_FONT = Font(name=FONT, size=10)
BOLD = Font(name=FONT, size=10, bold=True)
ITALIC = Font(name=FONT, size=10, italic=True)
IN_FONT = Font(name=FONT, size=10, color="0000FF", bold=True)
IN_FILL = PatternFill("solid", fgColor="FFF2CC")
TITLE = Font(name=FONT, size=14, bold=True)
WRAP = Alignment(wrap_text=True, vertical="top")
CONF_COLORS = {"Strong": ("1F6F3F", "FFFFFF"), "Clear": ("4E9A5E", "FFFFFF"),
               "Suggestive": ("D9EAD3", "000000"), "No identifiable effect": ("FFFFFF", "000000")}
SIZE_COLORS = {"Dominant": ("C65911", "FFFFFF"), "Substantial": ("F4B183", "000000"),
               "Noticeable": ("FBE5D6", "000000"), "Negligible": ("FFFFFF", "000000")}

# Settings cells read by the formulas. The row numbers are fixed by write_settings().
S_X, S_SD, S_TYP, S_YEAR, S_FDR = "Settings!$B$4", "Settings!$B$5", "Settings!$B$6", "Settings!$B$7", "Settings!$B$8"
S_DRY, S_SHRINK, S_RPMIN, S_TAILP, S_TRENDP = "Settings!$B$9", "Settings!$B$10", "Settings!$B$11", "Settings!$B$12", "Settings!$B$13"
TAU_ROW0 = 17
TAU_KEYS = f"Settings!$A${TAU_ROW0}:$A${TAU_ROW0 + 7}"
TAU_VALS = f"Settings!$B${TAU_ROW0}:$B${TAU_ROW0 + 7}"
# Lookup cells. Confidence rows 5-8 (Strong by the FDR flag, then three p tiers),
# size rows 14-17, wording rows 22-27, direction words rows 32-35.
CONF_STRONG, CONF_P, CONF_L = "Lookup!$B$5", "Lookup!$A$6:$A$8", "Lookup!$B$6:$B$8"
SIZE_R, SIZE_L = "Lookup!$A$14:$A$17", "Lookup!$B$14:$B$17"
W_ROW0 = 22
DIR_ROW0 = 32
DIR_KEYS, DIR_HEAD, DIR_TABLE = (f"Lookup!$A${DIR_ROW0}:$A${DIR_ROW0 + 3}", f"Lookup!$B${DIR_ROW0 - 1}:$D${DIR_ROW0 - 1}",
                                 f"Lookup!$B${DIR_ROW0}:$D${DIR_ROW0 + 3}")


def header(ws, row, names, widths=None):
    for j, name in enumerate(names, 1):
        c = ws.cell(row=row, column=j, value=name)
        c.font, c.fill, c.alignment = H_FONT, H_FILL, Alignment(wrap_text=True, vertical="center")
        if widths:
            ws.column_dimensions[get_column_letter(j)].width = widths[j - 1]
    ws.row_dimensions[row].height = 48


def body_font(ws, r0, r1, c1):
    for row in ws.iter_rows(min_row=r0, max_row=r1, max_col=c1):
        for c in row:
            c.font = B_FONT


def color_labels(ws, rng, colors):
    for label, (fill, ink) in colors.items():
        ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=[f'"{label}"'],
                                                       fill=PatternFill("solid", fgColor=fill),
                                                       font=Font(name=FONT, size=10, color=ink)))


def number_formats(ws, fmt: dict, n: int):
    for col, f in fmt.items():
        for (c,) in ws[f"{col}2:{col}{n}"]:
            c.number_format = f


def shrink_tau2(lin: pd.DataFrame) -> dict[str, float]:
    """tau^2 per season and variable, as in 04_build_facts.shrink_factors: var(b) - mean(se^2), floored at 0."""
    out = {}
    for (season, var), g in lin.groupby(["season", "variable"]):
        out[f"{season}|{var}"] = max(0.0, float(g["enso_effect"].var(ddof=1) - (g["enso_se"] ** 2).mean()))
    return out


def write_readme(wb: Workbook, meta: dict) -> None:
    ws = wb.active
    ws.title = "README"
    y0, y1 = meta["forecast_year"] - 1, meta["forecast_year"]
    roni = f"{meta['son_2026_roni']:+.2f} ± {meta['son_2026_roni_sd']:.2f} °C"
    lines = [
        ("C40 cities: El Niño and trend outlook for Dec–Feb and Mar–May", TITLE),
        ("", None),
        (f"This workbook holds, for every C40 city and for Dec {y0}–Feb {y1} and Mar–May {y1}, how temperature, rainfall, "
         "the share of rainy days and relative humidity have responded to El Niño since 1951, separately from the long-term "
         "trend, and what that implies for the coming seasons. Weather is ERA5 at one grid point per city. The El Niño index "
         "is NOAA CPC's Relative Oceanic Niño Index (RONI) for the Sep–Nov before each season.", None),
        ("", None),
        (f"The outlook rests on one number: the Sep–Nov {y0} RONI on the Settings tab, now {roni}. "
         + meta["son_2026_roni_source"], None),
        ("", None),
        ("Fitted statistics are values from the regressions. Everything derived from them is a live formula that reads the "
         "Settings and Lookup tabs: the confidence and size labels, the shrunk El Niño effect this season, the expected "
         "2027 season and its spread, the chances of a below-, near- and above-normal season, the return period and the "
         "words. Change an input and every dependent cell updates. Blue text on yellow marks the cells meant to be edited.", None),
        ("", None),
        ("Tabs", BOLD),
        ("Settings holds the RONI estimate and its spread, the shrinkage switch with the eight τ² values behind the shrinkage "
         "factors, the dry-season cut, the typical El Niño used for one label, and the thresholds the formulas read.", None),
        ("Lookup holds the confidence tiers, the size tiers, the outlook wording with its even-odds band, and the direction "
         "words for each variable. Edit a threshold or a phrase and every label follows.", None),
        ("Summary gives one row per city and season with the headline numbers for each variable, pulled from Linear.", None),
        ("Linear gives the seasonal model, one row per city, season and variable, with the outlook.", None),
        ("Quantiles gives the daily quantile regressions, one row per city, season, variable and percentile.", None),
        ("Tails gives the 95th minus the 5th percentile: whether El Niño or the trend moves the extremes differently.", None),
        ("Definitions explains every column.", None),
        ("", None),
        ("Rules", BOLD),
        ("Confidence has four tiers. Strong means the El Niño effect survives the Benjamini–Hochberg correction at 5% across "
         "all 768 seasonal tests; Clear is p < 0.05 on its own; Suggestive is p < 0.10; the rest has no identifiable effect. "
         "The El Niño effect is shrunk toward zero by an empirical-Bayes factor τ²/(τ² + se²), with τ² the spread of true "
         "effects across the 96 cities for that season and variable, before it enters the outlook, the size label and the "
         "words; the confidence label still uses the unshrunk test. Rainfall seasons with a 1991–2020 normal under "
         f"{meta['dry_season_mm']:.0f} mm are flagged as dry seasons and get no El Niño statement and no rainfall outlook on "
         "the site. Chances between 45% and 55% are written as about even odds.", None),
        ("", None),
        ("Updating", BOLD),
        (f"When CPC publishes the Sep–Nov {y0} RONI in early December, enter the value in Settings!B4 and set Settings!B5 to 0. "
         "The figures, the city paragraphs and the website need the pipeline re-run (code/run.py).", None),
        ("", None),
        ("Sources: ERA5 hourly reanalysis (ECMWF via Copernicus) at the city's grid point; RONI from NOAA CPC "
         "(https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt). Built by code/07_build_workbook.py.", None),
    ]
    for i, (t, f) in enumerate(lines, 1):
        c = ws.cell(row=i, column=1, value=t)
        c.font = f or B_FONT
        c.alignment = WRAP
    ws.column_dimensions["A"].width = 140


def write_settings(wb: Workbook, meta: dict, tau2: dict[str, float], mean_factor: dict[str, float]) -> None:
    ws = wb.create_sheet("Settings")
    ws["A1"], ws["A1"].font = "Settings (edit the blue cells)", TITLE
    header(ws, 3, ["Input", "Value", "Notes and source"], [58, 12, 120])
    y0 = meta["forecast_year"] - 1
    rows = [
        (f"Sep–Nov {y0} RONI (°C), the predictor for both seasons", meta["son_2026_roni"], True,
         ("ESTIMATE. " if meta["son_2026_estimated"] else "Observed. ") + meta["son_2026_roni_source"]),
        ("Uncertainty of that value (1 SD, °C)", meta["son_2026_roni_sd"], True, "Set to 0 once the Sep–Nov value is observed."),
        ("Typical El Niño RONI (°C)", meta["typical_el_nino"], True, "Used only for the label 'Size in a typical El Niño'."),
        ("Forecast season-year", meta["forecast_year"], False,
         f"DJF {meta['forecast_year']} = Dec {y0}–Feb {meta['forecast_year']}; MAM {meta['forecast_year']} = Mar–May {meta['forecast_year']}. "
         "The trend level in that year is fixed by the regressions (hidden columns of Linear); changing this cell changes nothing."),
        ("FDR level", 0.05, False, "Benjamini–Hochberg false-discovery rate behind the 'Survives FDR' flags, computed in Python over "
         f"{meta['n_tests']} seasonal tests and over the quantile tests as a second family."),
        ("Dry-season cut (mm)", meta["dry_season_mm"], True, "Rainfall seasons whose 1991–2020 normal is below this get the dry-season flag; "
         "the site then gives no El Niño statement and no rainfall outlook for them."),
        ("Apply shrinkage (1 = yes, 0 = no)", 1 if meta["shrink"] else 0, True,
         "With 1, each El Niño effect is multiplied by τ²/(τ² + se²) before it enters the outlook, the size label and the words. "
         "With 0 the fitted effects are used at face value, as on the site shipped on 2026-10-31."),
        ("Return period quoted from a ratio of", 0.5, True, "'Once every N years without El Niño' is left blank when the effect is "
         "less than this many residual standard deviations."),
        ("Tail-difference p for naming a tail", 0.1, True, "On the Tails tab the sentence names the tail that moves most when the "
         "95th − 5th difference has p below this."),
        ("Trend p for the warming equivalent", 0.05, True, "The 'Equivalent years of warming trend' column is filled only when the "
         "temperature trend is positive with p below this."),
    ]
    for i, (a, b, editable, note) in enumerate(rows, 4):
        ws.cell(row=i, column=1, value=a).font = B_FONT
        cb = ws.cell(row=i, column=2, value=b)
        cb.font, cb.fill = (IN_FONT, IN_FILL) if editable else (B_FONT, PatternFill())
        cn = ws.cell(row=i, column=3, value=note)
        cn.font, cn.alignment = B_FONT, WRAP
    ws["A15"] = "Shrinkage: spread of true El Niño effects across the 96 cities (τ²) by season and variable"
    ws["A15"].font = BOLD
    header(ws, 16, ["Season | variable", "τ² (effect per °C, squared)", "Note"])
    ws.row_dimensions[16].height = 32
    for i, (key, val) in enumerate(tau2.items()):
        r = TAU_ROW0 + i
        ws.cell(row=r, column=1, value=key).font = B_FONT
        c = ws.cell(row=r, column=2, value=val)
        c.font, c.fill, c.number_format = IN_FONT, IN_FILL, "0.000000"
        ws.cell(row=r, column=3, value=f"Method of moments: var(b) − mean(se²) across the cities, floored at 0. "
                                       f"Mean factor across the cities {mean_factor[key]:.2f}.").font = B_FONT
    ws.cell(row=TAU_ROW0 + 9, column=1, value="Each Linear row computes its own factor τ²/(τ² + se²) from these values. "
            "Re-running code/run.py refreshes them from the fitted table.").font = ITALIC


def write_lookup(wb: Workbook, meta: dict) -> None:
    ws = wb.create_sheet("Lookup")
    ws["A1"], ws["A1"].font = "Lookup tables (edit thresholds or wording; labels update everywhere)", TITLE
    ws["A3"], ws["A3"].font = "CONFIDENCE that an El Niño effect exists", BOLD
    header(ws, 4, ["p-value from (≥)", "Label", "…to (<)", "Plain-language phrase"], [18, 24, 10, 90])
    conf = meta["confidence"]  # [[0, Strong], [0, Clear], [0.05, Suggestive], [0.1, No identifiable effect]]
    ws.cell(row=5, column=1, value="survives FDR").font = B_FONT
    ws.cell(row=5, column=2, value=conf[0][1])
    ws.cell(row=5, column=3, value="—")
    ws.cell(row=5, column=4, value=CONF_PHRASES[conf[0][1]])
    for i, (p0, lab) in enumerate(conf[1:]):
        r = 6 + i
        c = ws.cell(row=r, column=1, value=p0)
        c.font, c.fill = IN_FONT, IN_FILL
        ws.cell(row=r, column=2, value=lab)
        ws.cell(row=r, column=3, value=f"=A{r + 1}" if i < len(conf) - 2 else 1)
        ws.cell(row=r, column=4, value=CONF_PHRASES[lab])
    ws["A9"] = ("Strong is decided by the 'Survives FDR' flag, not by a p cut: with 768 tests about one in twenty would reach "
                "p < 0.05 by chance. The three p tiers apply to the effects that fail the correction.")
    ws["A9"].font = ITALIC
    color_labels(ws, "B5:B8", CONF_COLORS)

    ws["A11"], ws["A11"].font = "SIZE of the effect next to natural variability: |shrunk effect this season| ÷ residual SD", BOLD
    ws["A12"] = "A ratio of 0.1 means this season's El Niño push is a tenth of a normal year-to-year swing."
    ws["A12"].font = ITALIC
    header(ws, 13, ["Ratio from (≥)", "Label", "…to (<)", "Plain-language phrase"])
    for i, (r0, lab) in enumerate(meta["size"]):
        r = 14 + i
        c = ws.cell(row=r, column=1, value=r0)
        c.font, c.fill = IN_FONT, IN_FILL
        ws.cell(row=r, column=2, value=lab)
        ws.cell(row=r, column=3, value=f"=A{r + 1}" if i < len(meta["size"]) - 1 else "—")
        ws.cell(row=r, column=4, value=SIZE_PHRASES[lab])
    color_labels(ws, "B14:B17", SIZE_COLORS)

    ws["A19"], ws["A19"].font = "OUTLOOK WORDING from the largest of the three tercile chances", BOLD
    ws["A20"] = ("The first row that applies wins, top to bottom; the even-odds row applies between its two bounds, and the "
                 "last row is the fallback. The chance is printed in the words except in the first row.")
    ws["A20"].font = ITALIC
    header(ws, 21, ["Largest chance from (≥)", "Wording", "…to (<), even-odds band only", "Note"])
    notes = ["No percentage printed.", "", "Written instead of 'More likely than not' between the two bounds.", "", "",
             "Fallback when no row above applies."]
    for i, (lo, words, hi) in enumerate(WORDING):
        r = W_ROW0 + i
        if lo is not None:
            c = ws.cell(row=r, column=1, value=lo)
            c.font, c.fill = IN_FONT, IN_FILL
        ws.cell(row=r, column=2, value=words).font = IN_FONT
        if hi is not None:
            c = ws.cell(row=r, column=3, value=hi)
            c.font, c.fill = IN_FONT, IN_FILL
        ws.cell(row=r, column=4, value=notes[i]).font = B_FONT

    ws["A29"], ws["A29"].font = "DIRECTION WORDS by variable and most likely tercile", BOLD
    header(ws, DIR_ROW0 - 1, ["Variable", "Below", "Near", "Above"])
    for i, var in enumerate(VARS):
        r = DIR_ROW0 + i
        ws.cell(row=r, column=1, value=var).font = B_FONT
        for j, words in enumerate(DIRECTION[var], 2):
            ws.cell(row=r, column=j, value=words).font = IN_FONT
    for col, w in zip("ABCD", (22, 44, 26, 90)):
        ws.column_dimensions[col].width = w


LINEAR_COLS = [
    # key, header, width
    ("key", "Key", 8), ("city", "City", 16), ("region", "Region", 18), ("season", "Season", 7),
    ("variable", "Variable", 16), ("unit", "Unit", 9), ("years", "Years", 10), ("n_years", "N years", 7),
    ("normal", "Normal 1991–2020", 10), ("trend", "Trend per decade", 9), ("trend_se", "Trend SE", 8),
    ("trend_p", "Trend p", 8), ("trend_total", "Trend since the first year (per decade × years ÷ 10)", 10),
    ("enso", "El Niño effect per +1 °C RONI (fitted)", 11), ("enso_se", "El Niño SE", 8), ("enso_p", "El Niño p", 8),
    ("fdr_q", "FDR q", 8), ("fdr", "Survives FDR", 8), ("confidence", "Confidence", 14),
    ("partial_r2", "Fraction of variability explained by El Niño", 11), ("sd_resid", "Intrinsic variability (residual SD)", 11),
    ("sd_detr", "Year-to-year SD (detrended)", 11), ("factor", "Shrinkage factor τ²/(τ²+se²)", 9),
    ("enso_shrunk", "Shrunk El Niño effect per +1 °C RONI", 11), ("effect", "El Niño effect this season (shrunk × RONI)", 12),
    ("effect_raw", "El Niño effect this season, unshrunk", 11), ("ratio", "Effect ÷ intrinsic variability", 10),
    ("size", "Size", 12), ("size_typ", "Size in a typical El Niño", 12), ("return_period", "Without El Niño, a season this far from the trend: about once every N years", 14),
    ("warming_years", "Equivalent years of warming trend", 11), ("trend_part", "Trend part of the 2027 anomaly", 10),
    ("mean_2027", "Expected 2027 value", 10), ("anomaly", "Expected anomaly vs 1991–2020", 10), ("fsd", "Forecast spread (SD)", 9),
    ("p_below", "P(below normal)", 9), ("p_near", "P(near normal)", 9), ("p_above", "P(above normal)", 9),
    ("tercile", "Most likely tercile", 9), ("p_max", "Largest chance", 9), ("outcome", "Most likely outcome", 24),
    ("words", "Forecast in words", 44), ("in_range", "RONI within the fitted range?", 10),
    ("upper_in_range", "RONI + 1 SD within the fitted range?", 10), ("dry", "Dry season (rain only)", 9),
    ("trend_pct", "Trend as % of normal per decade (rain only)", 10),
    ("_var", "_var", 9), ("_group", "_group", 9), ("_a2027", "_a2027", 9), ("_var_a2027", "_var_a2027", 9),
    ("_cov", "_cov_a2027_b", 9), ("_var_b", "_var_b", 9), ("_tlo", "_tercile_low", 9), ("_thi", "_tercile_high", 9),
    ("_rmin", "_roni_min", 9), ("_rmax", "_roni_max", 9),
]
LC = {key: get_column_letter(i + 1) for i, (key, _, _) in enumerate(LINEAR_COLS)}


def write_linear(wb: Workbook, lin: pd.DataFrame) -> None:
    ws = wb.create_sheet("Linear")
    header(ws, 1, [h for _, h, _ in LINEAR_COLS], [w for _, _, w in LINEAR_COLS])
    c = LC
    for i, r in lin.iterrows():
        k = i + 2
        v = r["variable"]
        values = {
            "key": f"{r['city']}|{r['season']}|{v}", "city": r["city"], "region": r["region"], "season": r["season"],
            "variable": VNAME[v], "unit": UNITS[v], "years": f"{r['first_year']}–{r['last_year']}", "n_years": int(r["n_years"]),
            "normal": r["normal_1991_2020"], "trend": r["trend_per_decade"], "trend_se": r["trend_se_per_decade"],
            "trend_p": r["trend_p"], "enso": r["enso_effect"], "enso_se": r["enso_se"], "enso_p": r["enso_p"],
            "fdr_q": r["enso_q_fdr"], "fdr": "Yes" if r["enso_survives_fdr"] else "No", "partial_r2": r["partial_r2"],
            "sd_resid": r["sd_residual"], "sd_detr": r["sd_detrended"],
            "_var": v, "_group": f"{r['season']}|{v}", "_a2027": r["a2027"], "_var_a2027": r["var_a2027"],
            "_cov": r["cov_a2027_b"], "_var_b": r["var_b"], "_tlo": r["tercile_low"], "_thi": r["tercile_high"],
            "_rmin": r["roni_lead_min"], "_rmax": r["roni_lead_max"],
        }
        pct = f'ROUND({c["p_max"]}{k}*100,0)'
        tau2 = f"INDEX({TAU_VALS},MATCH({c['_group']}{k},{TAU_KEYS},0))"
        formulas = {
            "trend_total": f"={c['trend']}{k}*{c['n_years']}{k}/10",
            "confidence": f'=IF({c["fdr"]}{k}="Yes",{CONF_STRONG},INDEX({CONF_L},MATCH({c["enso_p"]}{k},{CONF_P},1)))',
            "factor": f"=IF({S_SHRINK}=1,{tau2}/({tau2}+{c['enso_se']}{k}^2),1)",
            "enso_shrunk": f"={c['enso']}{k}*{c['factor']}{k}",
            "effect": f"={c['enso_shrunk']}{k}*{S_X}",
            "effect_raw": f"={c['enso']}{k}*{S_X}",
            "ratio": f'=IF({c["sd_resid"]}{k}>0,ABS({c["effect"]}{k})/{c["sd_resid"]}{k},"")',
            "size": f'=IF({c["ratio"]}{k}="","",INDEX({SIZE_L},MATCH({c["ratio"]}{k},{SIZE_R},1)))',
            "size_typ": f'=IF({c["sd_resid"]}{k}>0,INDEX({SIZE_L},MATCH(ABS({c["enso_shrunk"]}{k})*{S_TYP}/{c["sd_resid"]}{k},{SIZE_R},1)),"")',
            "return_period": (f'=IF({c["ratio"]}{k}="","",IF({c["ratio"]}{k}<{S_RPMIN},"",'
                              f'IF(1/(1-NORMSDIST({c["ratio"]}{k}))>100,">100",ROUND(1/(1-NORMSDIST({c["ratio"]}{k})),0))))'),
            "trend_part": f"={c['_a2027']}{k}-{c['normal']}{k}",
            "mean_2027": f"={c['_a2027']}{k}+{c['effect']}{k}",
            "anomaly": f"={c['mean_2027']}{k}-{c['normal']}{k}",
            "fsd": (f"=SQRT({c['sd_resid']}{k}^2+{c['_var_a2027']}{k}+{S_X}^2*{c['factor']}{k}*{c['_var_b']}{k}"
                    f"+2*{S_X}*{c['factor']}{k}*{c['_cov']}{k}+{c['enso_shrunk']}{k}^2*{S_SD}^2)"),
            "p_below": f"=NORMDIST({c['_tlo']}{k},{c['mean_2027']}{k},{c['fsd']}{k},TRUE)",
            "p_above": f"=1-NORMDIST({c['_thi']}{k},{c['mean_2027']}{k},{c['fsd']}{k},TRUE)",
            "p_near": f"=1-{c['p_below']}{k}-{c['p_above']}{k}",
            "tercile": (f'=IF(AND({c["p_below"]}{k}>={c["p_near"]}{k},{c["p_below"]}{k}>={c["p_above"]}{k}),"Below",'
                        f'IF({c["p_near"]}{k}>={c["p_above"]}{k},"Near","Above"))'),
            "p_max": f"=MAX({c['p_below']}{k},{c['p_near']}{k},{c['p_above']}{k})",
            "outcome": f"=INDEX({DIR_TABLE},MATCH({c['_var']}{k},{DIR_KEYS},0),MATCH({c['tercile']}{k},{DIR_HEAD},0))",
            "words": (f'=IF({c["p_max"]}{k}>=Lookup!$A${W_ROW0},Lookup!$B${W_ROW0}&": "&{c["outcome"]}{k},'
                      f'IF({c["p_max"]}{k}>=Lookup!$A${W_ROW0 + 1},Lookup!$B${W_ROW0 + 1}&" ("&{pct}&"%): "&{c["outcome"]}{k},'
                      f'IF(AND({c["p_max"]}{k}>=Lookup!$A${W_ROW0 + 2},{c["p_max"]}{k}<Lookup!$C${W_ROW0 + 2}),'
                      f'Lookup!$B${W_ROW0 + 2}&" ("&{pct}&"%): "&{c["outcome"]}{k},'
                      f'IF({c["p_max"]}{k}>=Lookup!$A${W_ROW0 + 3},Lookup!$B${W_ROW0 + 3}&" ("&{pct}&"%): "&{c["outcome"]}{k},'
                      f'IF({c["p_max"]}{k}>=Lookup!$A${W_ROW0 + 4},Lookup!$B${W_ROW0 + 4}&" ("&{pct}&"%): "&{c["outcome"]}{k},'
                      f'Lookup!$B${W_ROW0 + 5})))))'),
            "in_range": f'=IF(AND({S_X}>={c["_rmin"]}{k},{S_X}<={c["_rmax"]}{k}),"Yes","No")',
            "upper_in_range": f'=IF({S_X}+{S_SD}<={c["_rmax"]}{k},"Yes","No")',
        }
        if v == "temperature":
            formulas["warming_years"] = (f'=IF(AND({c["trend"]}{k}>0,{c["trend_p"]}{k}<{S_TRENDP}),'
                                         f'{c["effect"]}{k}/({c["trend"]}{k}/10),"")')
        if v == "precipitation":
            formulas["dry"] = f'=IF({c["normal"]}{k}<{S_DRY},"Yes","No")'
            formulas["trend_pct"] = f"={c['trend']}{k}/{c['normal']}{k}*100"
        for key, val in {**values, **formulas}.items():
            ws[f"{c[key]}{k}"] = val
    n = len(lin) + 1
    body_font(ws, 2, n, len(LINEAR_COLS))
    fmt = {"normal": "0.00", "trend": "0.000", "trend_se": "0.000", "trend_p": "0.000", "trend_total": "0.00", "enso": "0.000",
           "enso_se": "0.000", "enso_p": "0.0000", "fdr_q": "0.0000", "partial_r2": "0.00", "sd_resid": "0.00", "sd_detr": "0.00",
           "factor": "0.00", "enso_shrunk": "0.000", "effect": "0.00", "effect_raw": "0.00", "ratio": "0.00", "warming_years": "0.0",
           "trend_part": "0.00", "mean_2027": "0.00", "anomaly": "0.00", "fsd": "0.00", "p_below": "0%", "p_near": "0%",
           "p_above": "0%", "p_max": "0%", "trend_pct": "0.0"}
    number_formats(ws, {c[k]: f for k, f in fmt.items()}, n)
    for key, _, _ in LINEAR_COLS:
        if key.startswith("_") or key == "key":
            ws.column_dimensions[c[key]].hidden = True
    ws.freeze_panes = f"{c['unit']}2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(LINEAR_COLS))}{n}"
    color_labels(ws, f"{c['confidence']}2:{c['confidence']}{n}", CONF_COLORS)
    color_labels(ws, f"{c['size']}2:{c['size']}{n}", SIZE_COLORS)
    ws[f"{c['effect']}1"].comment = Comment("Shrunk El Niño effect per °C × Settings!B4. Change B4 to update.", "pipeline")
    ws[f"{c['p_below']}1"].comment = Comment("Normal distribution: centre = trend level in 2027 + shrunk El Niño effect; spread = "
                                             "residual SD, coefficient uncertainty and RONI uncertainty (Settings!B5). "
                                             "Terciles from 1991–2020.", "pipeline")


QCOLS = [("city", "City", 16), ("season", "Season", 7), ("variable", "Variable", 22), ("unit", "Unit", 8),
         ("pct", "Percentile", 9), ("n_days", "N days", 8), ("n_years", "N years", 7), ("trend", "Trend per decade", 10),
         ("trend_se", "Trend SE", 9), ("trend_p", "Trend p", 8), ("trend_lo", "Trend 80% low", 9), ("trend_hi", "Trend 80% high", 9),
         ("enso", "El Niño effect per +1 °C RONI", 12), ("enso_se", "El Niño SE", 9), ("enso_p", "El Niño p", 8),
         ("enso_lo", "El Niño 80% low", 9), ("enso_hi", "El Niño 80% high", 9), ("fdr_q", "FDR q", 8), ("fdr", "Survives FDR", 8),
         ("confidence", "Confidence", 14), ("shift", "Shift this season (effect × RONI)", 12), ("cross", "Fitted lines cross?", 9),
         ("key", "Key", 8)]
QC = {key: get_column_letter(i + 1) for i, (key, _, _) in enumerate(QCOLS)}


def write_quantiles(wb: Workbook, qt: pd.DataFrame) -> int:
    ws = wb.create_sheet("Quantiles")
    q = qt[qt["quantile"].isin(PCT_NAME)].reset_index(drop=True)
    header(ws, 1, [h for _, h, _ in QCOLS], [w for _, _, w in QCOLS])
    c = QC
    for i, r in q.iterrows():
        k = i + 2
        v = r["variable"]
        values = {"city": r["city"], "season": r["season"], "variable": QNAME[v], "unit": QUNITS[v],
                  "pct": PCT_NAME[r["quantile"]], "n_days": int(r["n_days"]), "n_years": int(r["n_years"]),
                  "trend": r["trend_per_decade"], "trend_se": r["trend_se_per_decade"], "trend_p": r["trend_p"],
                  "trend_lo": r["trend_lo80"], "trend_hi": r["trend_hi80"], "enso": r["enso_effect"], "enso_se": r["enso_se"],
                  "enso_p": r["enso_p"], "enso_lo": r["enso_lo80"], "enso_hi": r["enso_hi80"], "fdr_q": r["enso_q_fdr"],
                  "fdr": "Yes" if r["enso_survives_fdr"] else "No", "cross": "Yes" if float(r["crossing_points"]) > 0 else "No",
                  "key": f"{r['city']}|{r['season']}|{v}|{PCT_NAME[r['quantile']]}"}
        formulas = {
            "confidence": f'=IF({c["fdr"]}{k}="Yes",{CONF_STRONG},INDEX({CONF_L},MATCH({c["enso_p"]}{k},{CONF_P},1)))',
            "shift": f"={c['enso']}{k}*{S_X}",
        }
        for key, val in {**values, **formulas}.items():
            ws[f"{c[key]}{k}"] = val
    n = len(q) + 1
    body_font(ws, 2, n, len(QCOLS))
    fmt = {k: "0.000" for k in ["trend", "trend_se", "trend_lo", "trend_hi", "enso", "enso_se", "enso_lo", "enso_hi", "shift"]}
    fmt.update({"trend_p": "0.0000", "enso_p": "0.0000", "fdr_q": "0.0000"})
    number_formats(ws, {c[k]: f for k, f in fmt.items()}, n)
    ws.column_dimensions[c["key"]].hidden = True
    ws.freeze_panes = f"{c['n_days']}2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(QCOLS))}{n}"
    color_labels(ws, f"{c['confidence']}2:{c['confidence']}{n}", CONF_COLORS)
    return len(q)


TCOLS = [("city", "City", 16), ("season", "Season", 7), ("variable", "Variable", 22), ("unit", "Unit", 8),
         ("e05", "El Niño slope: 5th", 10), ("e95", "El Niño slope: 95th", 10), ("ediff", "El Niño: 95th − 5th", 10),
         ("elo", "80% low", 9), ("ehi", "80% high", 9), ("ep", "p", 8), ("etext", "What El Niño does to the tails", 44),
         ("t05", "Trend per decade: 5th", 10), ("t95", "Trend per decade: 95th", 10), ("tdiff", "Trend: 95th − 5th", 10),
         ("tlo", "80% low", 9), ("thi", "80% high", 9), ("tp", "p", 8), ("ttext", "What the trend does to the tails", 44),
         ("key", "Key", 8)]
TC = {key: get_column_letter(i + 1) for i, (key, _, _) in enumerate(TCOLS)}


def tail_sentence(k: int, lo_col: str, hi_col: str, diff_col: str, p_col: str, lo_name: str, hi_name: str, lead: str) -> str:
    """Which tail moves most, in which direction, and what happens to the spread; one formula."""
    def clause(col, name):
        return (f'"{lead} the {name} most ("&IF({col}{k}>0,"upward","downward")&"); "'
                f'&IF({diff_col}{k}>0,"spread widens","spread narrows")')
    return (f'=IF(OR({p_col}{k}="",{p_col}{k}>={S_TAILP}),"Both tails move alike",'
            f'IF(ABS({hi_col}{k})>=ABS({lo_col}{k}),{clause(hi_col, hi_name)},{clause(lo_col, lo_name)}))')


def write_tails(wb: Workbook, qt: pd.DataFrame) -> int:
    ws = wb.create_sheet("Tails")
    diff = qt[qt["quantile"] == "95th-5th"]
    enso = diff.dropna(subset=["enso_difference"]).set_index(["city", "season", "variable"])
    trend = diff.dropna(subset=["trend_difference"]).set_index(["city", "season", "variable"])
    slopes = qt[qt["quantile"].isin(PCT_NAME)].set_index(["city", "season", "variable", "quantile"])
    cells = diff[["city", "season", "variable"]].drop_duplicates().reset_index(drop=True)
    header(ws, 1, [h for _, h, _ in TCOLS], [w for _, _, w in TCOLS])
    c = TC
    for i, r in cells.iterrows():
        k = i + 2
        idx = (r["city"], r["season"], r["variable"])
        v = r["variable"]
        e, t = enso.loc[idx], trend.loc[idx]
        lo_name, hi_name = TAIL_NAMES[v]
        values = {"city": r["city"], "season": r["season"], "variable": QNAME[v], "unit": QUNITS[v],
                  "e05": slopes.loc[idx + ("0.05",), "enso_effect"], "e95": slopes.loc[idx + ("0.95",), "enso_effect"],
                  "ediff": e["enso_difference"], "elo": e["enso_difference_lo80"], "ehi": e["enso_difference_hi80"], "ep": e["enso_difference_p"],
                  "t05": slopes.loc[idx + ("0.05",), "trend_per_decade"], "t95": slopes.loc[idx + ("0.95",), "trend_per_decade"],
                  "tdiff": t["trend_difference"], "tlo": t["trend_difference_lo80"], "thi": t["trend_difference_hi80"], "tp": t["trend_difference_p"],
                  "key": "|".join(idx)}
        formulas = {"etext": tail_sentence(k, c["e05"], c["e95"], c["ediff"], c["ep"], lo_name, hi_name, "El Niño moves"),
                    "ttext": tail_sentence(k, c["t05"], c["t95"], c["tdiff"], c["tp"], lo_name, hi_name, "The trend changes")}
        for key, val in {**values, **formulas}.items():
            ws[f"{c[key]}{k}"] = val
    n = len(cells) + 1
    body_font(ws, 2, n, len(TCOLS))
    number_formats(ws, {c[k]: "0.000" for k in ["e05", "e95", "ediff", "elo", "ehi", "ep", "t05", "t95", "tdiff", "tlo", "thi", "tp"]}, n)
    ws.column_dimensions[c["key"]].hidden = True
    ws.freeze_panes = f"{c['e05']}2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(TCOLS))}{n}"
    return len(cells)


SUMMARY_PULLS = [("Trend/decade", "trend", "0.00"), ("Confidence", "confidence", None), ("Effect this season", "effect", "0.00"),
                 ("Size", "size", None), ("Expected anomaly 2027", "anomaly", "0.00"), ("P(below)", "p_below", "0%"),
                 ("P(above)", "p_above", "0%"), ("Outlook", "words", None)]
SUMMARY_SHORT = {"temperature": "Temp", "precipitation": "Rain", "wet_day_share": "Rainy days", "rel_humidity": "RH"}


def write_summary(wb: Workbook, lin: pd.DataFrame) -> int:
    ws = wb.create_sheet("Summary", 1)
    cols = [("City", 16), ("Region", 18), ("Season", 7)]
    pulls = []  # (column index, variable, Linear column key, number format)
    for v in VARS:
        for lab, key, f in SUMMARY_PULLS:
            cols.append((f"{SUMMARY_SHORT[v]}: {lab}", 40 if key == "words" else 11))
            pulls.append((len(cols), v, key, f))
        if v == "precipitation":
            cols.append(("Rain: Dry season", 9))
            pulls.append((len(cols), v, "dry", None))
    header(ws, 1, [c for c, _ in cols], [w for _, w in cols])
    keys = lin[["city", "region", "season"]].drop_duplicates().reset_index(drop=True)
    for i, r in keys.iterrows():
        k = i + 2
        ws.cell(row=k, column=1, value=r["city"])
        ws.cell(row=k, column=2, value=r["region"])
        ws.cell(row=k, column=3, value=r["season"])
        for j, v, key, f in pulls:
            col = LC[key]
            c = ws.cell(row=k, column=j, value=f'=IFERROR(INDEX(Linear!${col}:${col},MATCH($A{k}&"|"&$C{k}&"|{v}",Linear!$A:$A,0)),"")')
            if f:
                c.number_format = f
    n = len(keys) + 1
    body_font(ws, 2, n, len(cols))
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{n}"
    for j, v, key, f in pulls:
        if key == "confidence":
            color_labels(ws, f"{get_column_letter(j)}2:{get_column_letter(j)}{n}", CONF_COLORS)
        if key == "size":
            color_labels(ws, f"{get_column_letter(j)}2:{get_column_letter(j)}{n}", SIZE_COLORS)
    return len(keys)


def write_definitions(wb: Workbook) -> None:
    ws = wb.create_sheet("Definitions")
    defs = [
        ("Linear", "Trend per decade", "c × 10 from y = a + b·RONI + c·(year − mean year) + e, fitted to one value per season, 1951–2025, holding El Niño fixed. Units per decade."),
        ("Linear", "Trend since the first year", "Trend per decade × number of years ÷ 10: the fitted change over the record."),
        ("Linear", "El Niño effect per +1 °C RONI (fitted)", "b in the same model: the change in the seasonal value for each +1 °C of the previous Sep–Nov RONI (three months before DJF, six before MAM), at face value."),
        ("Linear", "El Niño p / FDR q / Survives FDR", "p from the t-test on b (n − 3 degrees of freedom). q is the Benjamini–Hochberg adjusted p across all 768 seasonal tests; Survives FDR means q below the level on Settings. Both are computed in Python."),
        ("Linear", "Confidence", "Strong when the effect survives FDR; otherwise the Lookup tier for p: Clear below 0.05, Suggestive below 0.10, else no identifiable effect. The label uses the unshrunk test."),
        ("Linear", "Fraction of variability explained by El Niño", "Partial R²: (SSE trend-only − SSE trend+El Niño) ÷ SSE trend-only. 0.25 means El Niño accounts for a quarter of the detrended year-to-year variation."),
        ("Linear", "Intrinsic variability (residual SD)", "Standard deviation of what is left after removing the trend and El Niño: the season-to-season noise El Niño cannot explain."),
        ("Linear", "Year-to-year SD (detrended)", "Standard deviation after removing only the trend, El Niño included."),
        ("Linear", "Shrinkage factor", "τ²/(τ² + se²), with τ² from the Settings tab for the row's season and variable and se the standard error of b. 1 when the Settings switch is 0."),
        ("Linear", "Shrunk El Niño effect per +1 °C RONI", "b × shrinkage factor: the effect pulled toward zero in proportion to how uncertain it is. This is the effect the outlook, the size label and the words use."),
        ("Linear", "El Niño effect this season", "Shrunk effect × the Sep–Nov RONI on Settings. The unshrunk version is beside it for comparison."),
        ("Linear", "Effect ÷ intrinsic variability / Size", "|El Niño effect this season| ÷ residual SD; the Size label comes from the Lookup tiers. 0.1 means this year's push is a tenth of a normal swing."),
        ("Linear", "Size in a typical El Niño", "The same label computed with the typical El Niño RONI on Settings instead of this year's value: the city's general sensitivity."),
        ("Linear", "…about once every N years", "How rare this season's El Niño push would be without El Niño: 1 ÷ (1 − Φ(ratio)), the one-sided normal tail of the ratio. Blank below the ratio on Settings (0.5, less rare than once in three years); '>100' when rarer than once a century."),
        ("Linear", "Equivalent years of warming trend", "Temperature only, when the trend is positive with p below the Settings threshold: El Niño effect this season ÷ trend per year."),
        ("Linear", "Trend part of the 2027 anomaly", "The trend line extended to 2027 minus the 1991–2020 normal: what the outlook would say with no El Niño."),
        ("Linear", "Expected 2027 value / anomaly", "Trend level in 2027 + El Niño effect this season; the anomaly subtracts the 1991–2020 normal."),
        ("Linear", "Forecast spread (SD)", "√(residual SD² + variance of the 2027 trend level + RONI² × factor × variance of b + 2 × RONI × factor × their covariance + shrunk b² × RONI uncertainty²). The factor also scales the posterior variance of b under shrinkage."),
        ("Linear", "P(below / near / above normal)", "Normal distribution with that centre and spread against the 1991–2020 terciles. Each is a third with no information. The trend alone already tilts warming cities toward 'above'."),
        ("Linear", "Most likely tercile / Largest chance / Most likely outcome", "The tercile with the largest chance (the first of a tie, in the order below, near, above), that chance, and the direction words for it from Lookup."),
        ("Linear", "Forecast in words", "The Lookup wording for the largest chance, top row first: Very likely from 95% without a percentage, Likely from 66%, About even odds between 45% and 55%, More likely than not from 50%, Slightly favored from 40%, otherwise near-equal odds. The percentage is rounded to a whole number."),
        ("Linear", "RONI within the fitted range? / RONI + 1 SD within?", "Whether the Sep–Nov RONI on Settings, and that value plus one SD, lie inside the range of Sep–Nov values the model was fitted on; beyond it the straight line is extrapolated."),
        ("Linear", "Dry season (rain only)", "Yes when the 1991–2020 rainfall normal is below the cut on Settings. The site gives these seasons no El Niño statement and no rainfall outlook; the workbook still shows the numbers."),
        ("Linear", "Trend as % of normal per decade (rain only)", "Trend per decade ÷ the 1991–2020 normal × 100."),
        ("Quantiles", "Percentile / Trend / El Niño effect", "Separate quantile regressions of daily values at the 5th, 50th and 95th percentile with the same predictors (intercept, RONI, year). Rainfall uses wet days (≥ 1 mm) only; nine rain seasons with too few wet days have no fit."),
        ("Quantiles", "SE, 80% low/high, p, FDR q", "From a 100-replicate year-block bootstrap (all days of a resampled year kept together, the same draws for all three percentiles). p from the bootstrap SE under a normal approximation; q from Benjamini–Hochberg across the 1,701 quantile tests as their own family."),
        ("Quantiles", "Confidence", "The same four tiers as on Linear, from the quantile test's own FDR flag and p."),
        ("Quantiles", "Shift this season", "El Niño effect at that percentile × the Sep–Nov RONI on Settings: how far the coldest, typical or hottest days are expected to move. Unshrunk."),
        ("Quantiles", "Fitted lines cross?", "Yes if the fitted 5th, 50th and 95th lines change order anywhere in the observed range, a sign the linear quantile model is strained."),
        ("Tails", "Slopes and 95th − 5th difference", "El Niño (per °C RONI) and trend (per decade) coefficients at the 5th and 95th percentile, and their difference with its bootstrap 80% interval and p. A positive difference means the spread widens. The sentence names the tail with the larger move and its direction when p is below the Settings threshold, otherwise 'Both tails move alike'."),
        ("Summary", "All columns", "Pulled from Linear by city, season and variable. The Outlook column repeats Forecast in words; the Dry season flag marks rain seasons the site does not forecast."),
    ]
    header(ws, 1, ["Tab", "Column", "Definition"], [12, 44, 150])
    for i, row in enumerate(defs, 2):
        for j, v in enumerate(row, 1):
            cell = ws.cell(row=i, column=j, value=v)
            cell.font, cell.alignment = B_FONT, WRAP


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--linear", default=ROOT / "data/processed/linear_results.csv")
    ap.add_argument("--quantiles", default=ROOT / "data/processed/quantile_results.csv")
    ap.add_argument("--meta", default=ROOT / "data/processed/facts_meta.json")
    ap.add_argument("--out", default=ROOT / "C40_ENSO_outlook.xlsx")
    args = ap.parse_args()

    meta = json.load(open(args.meta))
    lin = pd.read_csv(args.linear).reset_index(drop=True)
    qt = pd.read_csv(args.quantiles)
    qt["quantile"] = qt["quantile"].astype(str)
    tau2 = {f"{s}|{v}": 0.0 for s in SEASONS for v in VARS}
    tau2.update(shrink_tau2(lin))
    mean_factor = {}
    for key, t2 in tau2.items():
        season, var = key.split("|")
        g = lin[(lin["season"] == season) & (lin["variable"] == var)]
        mean_factor[key] = float((t2 / (t2 + g["enso_se"] ** 2)).mean()) if len(g) else float("nan")

    wb = Workbook()
    write_readme(wb, meta)
    write_settings(wb, meta, tau2, mean_factor)
    write_lookup(wb, meta)
    write_linear(wb, lin)
    nq = write_quantiles(wb, qt)
    nt = write_tails(wb, qt)
    ns = write_summary(wb, lin)
    write_definitions(wb)
    wb.save(args.out)
    print(f"Saved {args.out}  (Linear {len(lin)} rows, Quantiles {nq}, Tails {nt}, Summary {ns})")


if __name__ == "__main__":
    main()

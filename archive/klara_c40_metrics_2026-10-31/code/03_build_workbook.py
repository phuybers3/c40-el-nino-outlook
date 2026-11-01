"""
Step 3 - Build the spreadsheet C40_ENSO_metrics.xlsx.

Tabs
  README        what is where, how to update
  Settings      the inputs you may change (blue): Sep-Nov 2026 RONI, its spread, a "typical" El Nino
  Lookup        confidence and size thresholds + the words each label stands for
  Summary       one row per city x season, headline numbers for each variable (pulled from Linear)
  Linear        one row per city x season x variable: trend, ENSO effect, labels, 2027 forecast
  Quantiles     one row per city x season x variable x percentile (5th, 50th, 95th)
  Tails         95th minus 5th percentile: does ENSO / the trend move the extremes differently?
  Definitions   every column explained

Fitted statistics are values (they come from the regressions). Everything derived from them -
labels, this season's effect, size relative to natural variability, the 2027 forecast and its
tercile probabilities - is a live formula reading Settings and Lookup, so changing an input
there updates the whole workbook.
"""
import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import CellIsRule
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.comments import Comment
import config as C

FONT = "Arial"
H_FILL = PatternFill("solid", fgColor="1F3A5F")
H_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
B_FONT = Font(name=FONT, size=10)
IN_FONT = Font(name=FONT, size=10, color="0000FF", bold=True)
IN_FILL = PatternFill("solid", fgColor="FFF2CC")
TITLE = Font(name=FONT, size=14, bold=True)
WRAP = Alignment(wrap_text=True, vertical="top")
THIN = Border(bottom=Side(style="thin", color="BFBFBF"))
UNITS = {"temperature": "°C", "precipitation": "mm", "wet_day_share": "% of days", "rel_humidity": "% RH"}
VNAME = {"temperature": "Mean temperature", "precipitation": "Rainfall total", "wet_day_share": "Wet-day share",
         "rel_humidity": "Relative humidity"}
QNAME = {"temperature": "Daily mean temperature", "precipitation": "Wet-day rainfall", "rel_humidity": "Daily relative humidity"}
CONF_COLORS = {"Strong": "1F6F3F", "Clear": "4E9A5E", "Modest": "A9D18E", "Detectable": "E2EFDA",
               "Weak": "F2F2F2", "No identifiable effect": "FFFFFF"}

# Settings cells (referenced by formulas everywhere)
S_X, S_SD, S_TYP, S_YEAR = "Settings!$B$4", "Settings!$B$5", "Settings!$B$6", "Settings!$B$7"
CONF_P, CONF_L = "Lookup!$A$5:$A$10", "Lookup!$B$5:$B$10"
SIZE_R, SIZE_L = "Lookup!$A$16:$A$19", "Lookup!$B$16:$B$19"


def header(ws, row, cols, widths=None):
    for j, name in enumerate(cols, 1):
        c = ws.cell(row=row, column=j, value=name)
        c.font, c.fill, c.alignment = H_FONT, H_FILL, Alignment(wrap_text=True, vertical="center")
        if widths:
            ws.column_dimensions[get_column_letter(j)].width = widths[j - 1]
    ws.row_dimensions[row].height = 42


def body_font(ws, r0, r1, c1):
    for row in ws.iter_rows(min_row=r0, max_row=r1, max_col=c1):
        for c in row:
            c.font = B_FONT


def color_confidence(ws, rng):
    for label, col in CONF_COLORS.items():
        ws.conditional_formatting.add(rng, CellIsRule(operator="equal", formula=[f'"{label}"'],
                                                       fill=PatternFill("solid", fgColor=col),
                                                       font=Font(name=FONT, size=10, color="FFFFFF" if label in ("Strong", "Clear") else "000000")))


def build():
    lin = pd.read_parquet(C.PROCESSED / "linear_results.parquet")
    qr = pd.read_parquet(C.PROCESSED / "quantile_results.parquet")
    order = {c: i for i, (c, *_) in enumerate(C.C40_CITIES)}
    vorder = {v: i for i, v in enumerate(["temperature", "precipitation", "wet_day_share", "rel_humidity"])}
    lin = lin.sort_values(["city", "season", "variable"], key=lambda s: s.map(order) if s.name == "city" else
                          (s.map(vorder) if s.name == "variable" else s)).reset_index(drop=True)
    wb = Workbook()

    # ------------------------------------------------------------------ README
    ws = wb.active
    ws.title = "README"
    lines = [
        ("C40 cities: ENSO and trend metrics for Dec–Feb and Mar–May", TITLE),
        ("", None),
        ("What this workbook answers, for every C40 city, for Dec–Feb (DJF) and Mar–May (MAM):", Font(name=FONT, bold=True)),
        ("1. Trend: how much the season has been warming (or getting wetter / more humid), per decade, 1951–2025.", None),
        ("2. ENSO: after removing the trend, does Sep–Nov RONI (the ENSO index) predict the season? How strongly, and how big is the effect next to normal year-to-year variability?", None),
        ("3. Extremes: quantile regressions of daily values at the 5th, 50th and 95th percentile — how the coldest/driest, typical and hottest/wettest days are changing, and how ENSO moves each.", None),
        ("4. Forecast: the expected Dec 2026–Feb 2027 and Mar–May 2027 season given this El Niño, with the odds of a below / near / above-normal season.", None),
        ("", None),
        ("Tabs", Font(name=FONT, bold=True)),
        ("Settings — the inputs you can change (blue on yellow). Change Sep–Nov 2026 RONI there when CPC publishes it; every forecast updates.", None),
        ("Lookup — the thresholds behind the Confidence and Size labels. Edit them and every label updates.", None),
        ("Summary — one row per city and season, headline numbers.", None),
        ("Linear — the seasonal linear model, one row per city × season × variable.", None),
        ("Quantiles — the daily quantile regressions, one row per city × season × variable × percentile.", None),
        ("Tails — 95th minus 5th percentile: do ENSO or the trend move the extremes differently?", None),
        ("Definitions — every column, its formula and its units.", None),
        ("", None),
        ("Color code: blue text on yellow = input you may edit · black = value from the regressions or a formula.", None),
        ("Data: ERA5 hourly reanalysis at the city's grid point (ECMWF via Copernicus) · RONI from NOAA CPC (relative Oceanic Niño Index).", None),
        ("Method and assumptions: see docs/translation_guide.md and the methods document.", None),
    ]
    for i, (t, f) in enumerate(lines, 1):
        c = ws.cell(row=i, column=1, value=t)
        c.font = f or B_FONT
        c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 130

    # ------------------------------------------------------------------ Settings
    ws = wb.create_sheet("Settings")
    ws["A1"], ws["A1"].font = "Settings (edit the blue cells)", TITLE
    ws["A3"], ws["B3"], ws["C3"] = "Input", "Value", "Notes and source"
    for c in ("A3", "B3", "C3"):
        ws[c].font, ws[c].fill = H_FONT, H_FILL
    rows = [
        ("Sep–Nov 2026 RONI (°C) — the predictor for DJF and MAM 2027", C.SON_2026_RONI,
         "ESTIMATE until CPC publishes SON 2026 (early Dec 2026). Basis: RONI JJA 2026 = +1.36, JAS 2026 = +1.69 "
         "(CPC RONI.ascii.txt); CPC ENSO discussion 8 Oct 2026: 83% chance RONI ≥ +2.5 in OND. Replace with the published value."),
        ("Uncertainty of that value (1 SD, °C)", C.SON_2026_RONI_SD, "Set to 0 once SON 2026 is observed."),
        ("“Typical strong El Niño” RONI for framing (°C)", C.TYPICAL_EL_NINO, "Used only in the ‘typical El Niño effect’ column."),
        ("Forecast season-year", C.FORECAST_YEAR, "DJF 2027 = Dec 2026–Feb 2027; MAM 2027 = Mar–May 2027. Regression constants are fixed at 2027."),
        ("FDR level", C.FDR_ALPHA, "Benjamini–Hochberg false discovery rate used for the ‘Survives FDR’ flag (computed in Python)."),
    ]
    for i, (a, b, n) in enumerate(rows, 4):
        ws.cell(row=i, column=1, value=a).font = B_FONT
        cb = ws.cell(row=i, column=2, value=b)
        cb.font, cb.fill = (IN_FONT, IN_FILL) if i <= 6 else (B_FONT, PatternFill())
        cn = ws.cell(row=i, column=3, value=n)
        cn.font, cn.alignment = B_FONT, WRAP
    ws.column_dimensions["A"].width = 58
    ws.column_dimensions["B"].width = 10
    ws.column_dimensions["C"].width = 110

    # ------------------------------------------------------------------ Lookup
    ws = wb.create_sheet("Lookup")
    ws["A1"], ws["A1"].font = "Lookup tables (edit thresholds or wording; labels update everywhere)", TITLE
    ws["A3"] = "CONFIDENCE that an ENSO effect exists — from the p-value of the ENSO term"
    ws["A3"].font = Font(name=FONT, bold=True)
    for j, h in enumerate(["p-value from (≥)", "Label", "…to (<)", "Plain-language phrase"], 1):
        c = ws.cell(row=4, column=j, value=h)
        c.font, c.fill = H_FONT, H_FILL
    phrases = {
        "Strong": "There is a strong, well-established ENSO effect.",
        "Clear": "There is a clear ENSO effect.",
        "Modest": "There is a modest but consistent ENSO signal.",
        "Detectable": "An ENSO effect is detectable but uncertain.",
        "Weak": "There are weak hints of an ENSO effect, not distinguishable from chance.",
        "No identifiable effect": "No identifiable ENSO effect.",
    }
    for i, (p0, lab) in enumerate(C.CONFIDENCE):
        r = 5 + i
        ws.cell(row=r, column=1, value=p0)
        ws.cell(row=r, column=2, value=lab)
        ws.cell(row=r, column=3, value=f"=IFERROR(A{r + 1},1)" if i < len(C.CONFIDENCE) - 1 else 1)
        ws.cell(row=r, column=4, value=phrases[lab])
        ws.cell(row=r, column=1).font = IN_FONT
        ws.cell(row=r, column=1).fill = IN_FILL
    ws["A13"] = "SIZE of the effect next to natural variability — |ENSO effect this season| ÷ intrinsic variability (residual SD)"
    ws["A13"].font = Font(name=FONT, bold=True)
    ws["A14"] = "A ratio of 0.1 means this season's ENSO push is 10% of a normal year-to-year swing: people would not notice it."
    ws["A14"].font = Font(name=FONT, italic=True, size=10)
    for j, h in enumerate(["Ratio from (≥)", "Label", "…to (<)", "Plain-language phrase"], 1):
        c = ws.cell(row=15, column=j, value=h)
        c.font, c.fill = H_FONT, H_FILL
    sphr = {"Negligible": "Small next to normal year-to-year swings; unlikely to be noticed.",
            "Noticeable": "Noticeable in the statistics; a modest tilt to the season.",
            "Substantial": "A substantial shift that people would likely notice.",
            "Dominant": "Larger than a typical year-to-year swing; would dominate the season."}
    for i, (r0, lab) in enumerate(C.SIZE):
        r = 16 + i
        ws.cell(row=r, column=1, value=r0).font = IN_FONT
        ws.cell(row=r, column=1).fill = IN_FILL
        ws.cell(row=r, column=2, value=lab)
        ws.cell(row=r, column=3, value=f"=A{r + 1}" if i < len(C.SIZE) - 1 else "—")
        ws.cell(row=r, column=4, value=sphr[lab])
    for col, w in zip("ABCD", (16, 24, 10, 80)):
        ws.column_dimensions[col].width = w
    ws["A22"] = ("Note: with 768 linear tests, about 1 in 20 would reach p < 0.05 by chance alone. ‘Survives FDR’ marks "
                 "effects that remain significant after the Benjamini–Hochberg correction for that many tests.")
    ws["A22"].font = Font(name=FONT, italic=True, size=10)
    color_confidence(ws, "B5:B10")

    # ------------------------------------------------------------------ Linear
    ws = wb.create_sheet("Linear")
    cols = ["Key", "City", "Region", "Season", "Variable", "Unit", "Years", "N years", "Normal 1991–2020",
            "Trend per decade", "Trend SE", "Trend p", "ENSO effect per +1 °C RONI", "ENSO SE", "ENSO p",
            "FDR q", "Survives FDR", "Confidence", "Fraction of variability explained by ENSO",
            "Intrinsic variability (residual SD)", "Year-to-year SD (detrended)",
            "ENSO effect this season (Sep–Nov 2026 RONI)", "Effect ÷ intrinsic variability", "Size",
            "Effect of a typical strong El Niño", "Equivalent years of warming trend",
            "Expected 2027 value", "Expected anomaly vs 1991–2020", "P(below normal)", "P(near normal)",
            "P(above normal)", "Most likely tercile", "RONI within historical range?",
            "_a2027", "_var_a2027", "_cov_a2027_b", "_var_b", "_tercile_low", "_tercile_high", "_roni_min", "_roni_max",
            "Size in a typical strong El Niño", "Without El Niño, a season this far from the trend: about once every N years",
            "Forecast in words"]
    widths = [8, 16, 18, 7, 16, 9, 10, 7, 10, 9, 8, 8, 11, 8, 8, 8, 8, 14, 11, 11, 11, 12, 10, 12, 11, 11,
              10, 10, 9, 9, 9, 10, 11] + [9] * 8 + [14, 16, 40]
    WORDS = {"temperature": ("a warmer-than-normal season", "a cooler-than-normal season"),
             "precipitation": ("a wetter-than-normal season", "a drier-than-normal season"),
             "wet_day_share": ("more rainy days than normal", "fewer rainy days than normal"),
             "rel_humidity": ("a more humid season than normal", "a less humid season than normal")}
    header(ws, 1, cols, widths)
    for i, r in lin.iterrows():
        k = i + 2
        v = r["variable"]
        vals = [f"{r['city']}|{r['season']}|{v}", r["city"], r["region"], r["season"], VNAME[v], UNITS[v],
                f"{r['first_year']}–{r['last_year']}", r["n_years"], r["normal_1991_2020"],
                r["trend_per_decade"], r["trend_se_per_decade"], r["trend_p"], r["enso_effect"], r["enso_se"],
                r["enso_p"], r["enso_q_fdr"], "Yes" if r["enso_survives_fdr"] else "No"]
        for j, val in enumerate(vals, 1):
            ws.cell(row=k, column=j, value=val)
        ws.cell(row=k, column=18, value=f"=INDEX({CONF_L},MATCH(O{k},{CONF_P},1))")
        ws.cell(row=k, column=19, value=r["partial_r2"])
        ws.cell(row=k, column=20, value=r["sd_residual"])
        ws.cell(row=k, column=21, value=r["sd_detrended"])
        ws.cell(row=k, column=22, value=f"=M{k}*{S_X}")
        ws.cell(row=k, column=23, value=f"=IF(T{k}>0,ABS(V{k})/T{k},\"\")")
        ws.cell(row=k, column=24, value=f"=IF(W{k}=\"\",\"\",INDEX({SIZE_L},MATCH(W{k},{SIZE_R},1)))")
        ws.cell(row=k, column=25, value=f"=M{k}*{S_TYP}")
        ws.cell(row=k, column=26, value=(f"=IF(AND(J{k}>0,L{k}<0.05),V{k}/(J{k}/10),\"\")" if v == "temperature" else ""))
        ws.cell(row=k, column=27, value=f"=AH{k}+M{k}*{S_X}")
        ws.cell(row=k, column=28, value=f"=AA{k}-I{k}")
        sd = f"SQRT(T{k}^2+AI{k}+{S_X}^2*AK{k}+2*{S_X}*AJ{k}+M{k}^2*{S_SD}^2)"
        ws.cell(row=k, column=29, value=f"=NORMDIST(AL{k},AA{k},{sd},TRUE)")
        ws.cell(row=k, column=31, value=f"=1-NORMDIST(AM{k},AA{k},{sd},TRUE)")
        ws.cell(row=k, column=30, value=f"=1-AC{k}-AE{k}")
        ws.cell(row=k, column=32, value=f"=IF(AE{k}>=MAX(AC{k},AD{k}),\"Above\",IF(AC{k}>=AD{k},\"Below\",\"Near\"))")
        ws.cell(row=k, column=33, value=f"=IF(AND({S_X}>=AN{k},{S_X}<=AO{k}),\"Yes\",\"Beyond record — extrapolated\")")
        for j, key in enumerate(["a2027", "var_a2027", "cov_a2027_b", "var_b", "tercile_low", "tercile_high",
                                 "roni_lead_min", "roni_lead_max"], 34):
            ws.cell(row=k, column=j, value=r[key])
        # Size if this were a typical strong El Niño (Settings!B6) instead of this year's
        ws.cell(row=k, column=42, value=f"=IF(T{k}>0,INDEX({SIZE_L},MATCH(ABS(M{k}*{S_TYP})/T{k},{SIZE_R},1)),\"\")")
        # How rare this season's ENSO push would be without El Niño: one-sided normal tail of the ratio
        ws.cell(row=k, column=43, value=(f"=IF(W{k}=\"\",\"\",IF(W{k}<0.5,\"\",IF(1/(1-NORMSDIST(W{k}))>100,\">100\","
                                         f"ROUND(1/(1-NORMSDIST(W{k})),0))))"))
        up, down = WORDS[v]
        m = f"MAX(AC{k},AD{k},AE{k})"
        pct = f"TEXT({m},\"0%\")"
        ws.cell(row=k, column=44, value=(
            f"=IF({m}<0.4,\"Near-equal odds of below, near and above normal\","
            f"IF({m}>0.95,\"Very likely (>95%)\",IF({m}>=0.66,\"Likely (\"&{pct}&\")\","
            f"IF({m}>=0.5,\"More likely than not (\"&{pct}&\")\",\"Slightly favored (\"&{pct}&\")\")))"
            f"&\": \"&IF(AF{k}=\"Above\",\"{up}\",IF(AF{k}=\"Below\",\"{down}\",\"a near-normal season\")))"))
    n = len(lin) + 1
    body_font(ws, 2, n, len(cols))
    fmt = {"I": "0.00", "J": "0.000", "K": "0.000", "L": "0.000", "M": "0.000", "N": "0.000", "O": "0.0000",
           "P": "0.0000", "S": "0.00", "T": "0.00", "U": "0.00", "V": "0.00", "W": "0.00", "Y": "0.00", "Z": "0.0",
           "AA": "0.00", "AB": "0.00", "AC": "0%", "AD": "0%", "AE": "0%"}
    for col, f in fmt.items():
        for c in ws[f"{col}2:{col}{n}"]:
            c[0].number_format = f
    for col in ["A"] + [get_column_letter(j) for j in range(34, 42)]:
        ws.column_dimensions[col].hidden = True
    ws.freeze_panes = "F2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{n}"
    color_confidence(ws, f"R2:R{n}")
    ws["V1"].comment = Comment("ENSO effect per °C × Settings!B4 (Sep–Nov 2026 RONI). Change B4 to update.", "pipeline")
    ws["AC1"].comment = Comment("Normal-distribution forecast: mean = trend level in 2027 + ENSO effect; spread = "
                                "residual SD + coefficient uncertainty + RONI uncertainty (Settings!B5). Terciles = 1991–2020.", "pipeline")

    # ------------------------------------------------------------------ Quantiles
    ws = wb.create_sheet("Quantiles")
    q = qr[qr["quantile"] != "95th-5th"].copy()
    q["qn"] = q["quantile"].astype(float)
    q = q.sort_values(["city", "season", "variable", "qn"],
                      key=lambda s: s.map(order) if s.name == "city" else s).reset_index(drop=True)
    cols = ["City", "Season", "Variable", "Unit", "Percentile", "N days", "N years", "Trend per decade",
            "Trend 80% low", "Trend 80% high", "Trend p", "ENSO effect per +1 °C RONI", "ENSO 80% low",
            "ENSO 80% high", "ENSO p", "FDR q", "Survives FDR", "Confidence", "Shift this season (Sep–Nov 2026 RONI)",
            "Fitted lines cross?"]
    header(ws, 1, cols, [16, 7, 22, 8, 10, 8, 7, 10, 9, 9, 8, 12, 9, 9, 8, 8, 8, 14, 13, 10])
    for i, r in q.iterrows():
        k = i + 2
        v = r["variable"]
        vals = [r["city"], r["season"], QNAME[v], UNITS[v] if v != "precipitation" else "mm/day",
                {0.05: "5th", 0.5: "50th", 0.95: "95th"}[r["qn"]], r["n_days"], r["n_years"],
                r["trend_per_decade"], r["trend_lo80"], r["trend_hi80"], r["trend_p"], r["enso_effect"],
                r["enso_lo80"], r["enso_hi80"], r["enso_p"], r["enso_q_fdr"], "Yes" if r["enso_survives_fdr"] else "No"]
        for j, val in enumerate(vals, 1):
            ws.cell(row=k, column=j, value=val)
        ws.cell(row=k, column=18, value=f"=INDEX({CONF_L},MATCH(O{k},{CONF_P},1))")
        ws.cell(row=k, column=19, value=f"=L{k}*{S_X}")
        ws.cell(row=k, column=20, value="Yes" if r["crossing_points"] > 0 else "No")
    n = len(q) + 1
    body_font(ws, 2, n, len(cols))
    for col, f in {"H": "0.000", "I": "0.000", "J": "0.000", "K": "0.000", "L": "0.000", "M": "0.000", "N": "0.000",
                   "O": "0.0000", "P": "0.0000", "S": "0.00"}.items():
        for c in ws[f"{col}2:{col}{n}"]:
            c[0].number_format = f
    ws.freeze_panes = "F2"
    ws.auto_filter.ref = f"A1:T{n}"
    color_confidence(ws, f"R2:R{n}")

    # ------------------------------------------------------------------ Tails
    ws = wb.create_sheet("Tails")
    t = qr[qr["quantile"] == "95th-5th"].groupby(["city", "season", "variable"]).first().reset_index()
    t = t.sort_values(["city", "season", "variable"], key=lambda s: s.map(order) if s.name == "city" else s).reset_index(drop=True)
    qq = qr[qr["quantile"] != "95th-5th"].copy()
    qq["qn"] = qq["quantile"].astype(float)
    slope = qq.set_index(["city", "season", "variable", "qn"])[["enso_effect", "trend_per_decade"]]
    TAIL_NAMES = {"temperature": ("coldest days", "hottest days"), "precipitation": ("light-rain days", "heavy-rain days"),
                  "rel_humidity": ("driest-air days", "most humid days")}

    def describe(b05, b95, p, lo_name, hi_name, lead):
        """Plain sentence: which tail moves most, in which direction, and what happens to the spread."""
        if not np.isfinite(p) or p >= 0.1:
            return "Both tails move alike"
        name, b = (hi_name, b95) if abs(b95) >= abs(b05) else (lo_name, b05)
        direction = "upward" if b > 0 else "downward"
        spread = "spread widens" if b95 - b05 > 0 else "spread narrows"
        return f"{lead} the {name} most ({direction}); {spread}"

    cols = ["City", "Season", "Variable", "Unit", "ENSO slope: 5th", "ENSO slope: 95th", "ENSO: 95th − 5th",
            "80% low", "80% high", "p", "What ENSO does to the tails",
            "Trend/decade: 5th", "Trend/decade: 95th", "Trend: 95th − 5th", "80% low", "80% high", "p",
            "What the trend does to the tails"]
    header(ws, 1, cols, [16, 7, 22, 8, 10, 10, 10, 9, 9, 8, 44, 10, 10, 10, 9, 9, 8, 44])
    for i, r in t.iterrows():
        k = i + 2
        v = r["variable"]
        lo_name, hi_name = TAIL_NAMES[v]
        e05, e95 = (slope.loc[(r["city"], r["season"], v, qv), "enso_effect"] for qv in (0.05, 0.95))
        t05, t95 = (slope.loc[(r["city"], r["season"], v, qv), "trend_per_decade"] for qv in (0.05, 0.95))
        vals = [r["city"], r["season"], QNAME[v], UNITS[v] if v != "precipitation" else "mm/day",
                e05, e95, r["enso_difference"], r["enso_difference_lo80"], r["enso_difference_hi80"], r["enso_difference_p"],
                describe(e05, e95, r["enso_difference_p"], lo_name, hi_name, "El Niño moves"),
                t05, t95, r["trend_difference"], r["trend_difference_lo80"], r["trend_difference_hi80"], r["trend_difference_p"],
                describe(t05, t95, r["trend_difference_p"], lo_name, hi_name, "The trend changes")]
        for j, val in enumerate(vals, 1):
            ws.cell(row=k, column=j, value=val)
    n = len(t) + 1
    body_font(ws, 2, n, len(cols))
    for col in ["E", "F", "G", "H", "I", "J", "L", "M", "N", "O", "P", "Q"]:
        for c in ws[f"{col}2:{col}{n}"]:
            c[0].number_format = "0.000"
    ws.freeze_panes = "E2"
    ws.auto_filter.ref = f"A1:R{n}"

    # ------------------------------------------------------------------ Summary (pulls from Linear)
    ws = wb.create_sheet("Summary", 1)
    cs = [("City", 16), ("Region", 18), ("Season", 7)]
    blocks = [("temperature", "Temp"), ("precipitation", "Rain"), ("rel_humidity", "RH")]
    pulls = [("Trend/decade", "J", "0.00"), ("ENSO effect/°C", "M", "0.00"), ("Confidence", "R", None),
             ("Size", "X", None), ("Expected anomaly 2027", "AB", "0.00"), ("P(above)", "AE", "0%"), ("P(below)", "AC", "0%")]
    for v, short in blocks:
        for lab, _, _ in pulls:
            cs.append((f"{short}: {lab}", 11))
    header(ws, 1, [c for c, _ in cs], [w for _, w in cs])
    keys = lin[["city", "region", "season"]].drop_duplicates().reset_index(drop=True)
    for i, r in keys.iterrows():
        k = i + 2
        ws.cell(row=k, column=1, value=r["city"])
        ws.cell(row=k, column=2, value=r["region"])
        ws.cell(row=k, column=3, value=r["season"])
        j = 4
        for v, _ in blocks:
            for lab, col, f in pulls:
                c = ws.cell(row=k, column=j, value=f"=IFERROR(INDEX(Linear!${col}:${col},MATCH($A{k}&\"|\"&$C{k}&\"|{v}\",Linear!$A:$A,0)),\"\")")
                if f:
                    c.number_format = f
                j += 1
    n = len(keys) + 1
    body_font(ws, 2, n, len(cs))
    ws.freeze_panes = "D2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cs))}{n}"
    for jj in (6, 13, 20):
        color_confidence(ws, f"{get_column_letter(jj)}2:{get_column_letter(jj)}{n}")

    # ------------------------------------------------------------------ Definitions
    ws = wb.create_sheet("Definitions")
    defs = [
        ("Linear", "Trend per decade", "c × 10 from y = a + b·RONI_lead + c·(year − mean year) + e, fit on one value per season, 1951–2025. Units per decade. Holds ENSO fixed."),
        ("Linear", "ENSO effect per +1 °C RONI", "b in the same model: change in the seasonal value for each +1 °C of the PREVIOUS Sep–Nov RONI (3 months before DJF, 6 months before MAM)."),
        ("Linear", "ENSO p / FDR q / Survives FDR", "p from the t-test on b (n − 3 degrees of freedom). q = Benjamini–Hochberg adjusted across all 768 linear ENSO tests. Survives FDR = q < Settings!B8."),
        ("Linear", "Confidence", "Label for p from the Lookup tab (formula)."),
        ("Linear", "Fraction of variability explained by ENSO", "Partial R²: (SSE trend-only − SSE trend+ENSO) ÷ SSE trend-only. 0.25 = ENSO accounts for a quarter of the detrended year-to-year variation."),
        ("Linear", "Intrinsic variability (residual SD)", "Standard deviation of what is left after removing trend and ENSO: the season-to-season noise ENSO cannot explain."),
        ("Linear", "Year-to-year SD (detrended)", "Standard deviation after removing only the trend (ENSO included)."),
        ("Linear", "ENSO effect this season", "b × Sep–Nov 2026 RONI (Settings!B4)."),
        ("Linear", "Effect ÷ intrinsic variability / Size", "|ENSO effect this season| ÷ residual SD; Size label from the Lookup tab. 0.1 = this year's ENSO push is 10% of a normal swing."),
        ("Linear", "Effect of a typical strong El Niño", "b × Settings!B6."),
        ("Linear", "Equivalent years of warming trend", "Temperature only, when the trend is positive and p < 0.05: ENSO effect this season ÷ trend per year."),
        ("Linear", "Expected 2027 value / anomaly", "a + c·(2027 − mean year) + b·RONI: the trend extended to 2027 plus this season's ENSO effect; anomaly = minus the 1991–2020 normal."),
        ("Linear", "P(below/near/above normal)", "Normal distribution with that mean and SD = √(residual² + coefficient uncertainty + b²·RONI uncertainty²), against the 1991–2020 terciles. Each is ⅓ with no information. The trend alone already tilts toward ‘above’ for warming cities."),
        ("Linear", "Size in a typical strong El Niño", "The same Size label computed with Settings!B6 (RONI +1.5) instead of this year's value: the city's general sensitivity to a strong El Niño."),
        ("Linear", "…about once every N years", "How rare this season's ENSO push would be without El Niño: 1 ÷ (1 − Φ(ratio)), the one-sided normal tail of ‘Effect ÷ intrinsic variability’. Blank below a ratio of 0.5 (less rare than once in 3 years); ‘>100’ when rarer than once a century."),
        ("Linear", "Forecast in words", "The highest of P(below/near/above) in words: Very likely (>95%), Likely (≥66%), More likely than not (≥50%), Slightly favored (≥40%), otherwise near-equal odds. Probabilities above 95% are never printed as 99–100%: the bell-curve tails overstate certainty that far out."),
        ("Linear", "RONI within historical range?", "Whether Sep–Nov 2026 RONI lies inside the range of Sep–Nov values used in the fit (otherwise the straight line is extrapolated)."),
        ("Quantiles", "Percentile / Trend / ENSO effect", "Separate quantile regressions of DAILY values at the 5th, 50th and 95th percentile with the same predictors (intercept, RONI_lead, year). Rainfall uses wet days (≥ 1 mm) only."),
        ("Quantiles", "80% low/high, p", "From a year-block bootstrap (all days of a resampled year kept together; same draws for all three percentiles). p from the bootstrap SE (normal approximation)."),
        ("Quantiles", "Shift this season", "ENSO effect at that percentile × Sep–Nov 2026 RONI: how far the coldest/typical/hottest days are expected to move."),
        ("Quantiles", "Fitted lines cross?", "Yes if the fitted 5th/50th/95th lines change order anywhere in the observed range (a sign the linear quantile model is strained)."),
        ("Tails", "Slopes and 95th − 5th difference", "ENSO (per °C RONI) and trend (per decade) coefficients at the 5th and 95th percentile, and their difference with a bootstrap 80% interval and p. Difference > 0 = the spread widens (upper tail rises more or falls less). The sentence names the tail with the larger move and its direction when p < 0.1, otherwise ‘Both tails move alike’."),
    ]
    header(ws, 1, ["Tab", "Column", "Definition"], [12, 40, 140])
    for i, (a, b, c) in enumerate(defs, 2):
        for j, v in enumerate((a, b, c), 1):
            cell = ws.cell(row=i, column=j, value=v)
            cell.font, cell.alignment = B_FONT, WRAP

    wb.save(C.WORKBOOK)
    print(f"Saved {C.WORKBOOK}  (Linear {len(lin)} rows, Quantiles {len(q)}, Tails {len(t)}, Summary {len(keys)})")


if __name__ == "__main__":
    build()

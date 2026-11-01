"""Write the city-season paragraphs from data/processed/city_facts.json.

    python3 code/05_write_paragraphs.py --facts data/processed/city_facts.json --rules legacy \
        --out docs/city_paragraphs_legacy.md --json-out data/processed/city_paragraphs.json
    python3 code/05_write_paragraphs.py --facts ... --rules legacy --check site/data/city

The 192 paragraphs shipped on 2026-10-31 were written by Klara Kuemmerle's
06_write_paragraphs.py (archive/klara_c40_metrics_2026-10-31/code/). This
file follows the general rules of that script: the effective confidence label
(Strong or Clear dropped one step when the effect fails the FDR correction),
the guards on every sentence, her rounding, and her station-check table, now
in code/paragraph_overrides.json. Under --rules legacy it reproduces the
shipped text; --check compares the regenerated paragraphs with the ones in
site/data/city/<slug>.json and reports the count of exact matches and a diff
of the first differing sentence for each mismatch. Non-breaking spaces
(U+00A0, written before every "°C" and "mm") are treated as ordinary spaces in
the comparison and written as U+00A0 in the output.

Under --rules new the same builders run with the revised rule set described
in docs/PARAGRAPH_GENERATOR_NOTES.md: four confidence tiers in which Strong
already means "survives FDR" (so no label is dropped), an attribution clause
that compares the trend part with the El Niño part of the forecast anomaly, a
25 mm dry-season cut that silences the rainfall effect and outlook, "about
even odds" for chances between 45% and 55%, a closing sentence that names the
range of the RONI estimate when its upper end exceeds the record, and two
station-check entries of its own. The two rule sets differ only through the
RULES dictionary; the sentence builders are shared.

Every threshold and every phrase lives in RULES. Station-check decisions live
in code/paragraph_overrides.json. Inputs are read only; the facts and the
site are never modified.

Standard library only (json, re, argparse, os, sys, csv).

--json-out writes a JSON object keyed "<city>|<season>" (for example
"Nairobi|DJF") whose value is the paragraph string; code/06_export_site.py
looks paragraphs up by that key. --out writes a markdown file with one
heading per paragraph and the reviewer notes (station checks, drizzle bias)
as italic lines that the site never shows.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NBSP = " "
SEASON_TEXT = {"DJF": "Dec–Feb", "MAM": "Mar–May"}
VARIABLES = ("temperature", "precipitation", "wet_day_share", "rel_humidity")

# ---------------------------------------------------------------------------
# RULES: one dictionary per rule set. "legacy" reproduces the 2026-10-31 text.
# ---------------------------------------------------------------------------

LEGACY = {
    # Confidence labels in order; a Strong or Clear label that fails the FDR
    # correction is read one step lower ("effective label") when fdr_drop is
    # set. Every clause follows the effective label.
    "conf_order": ["Strong", "Clear", "Modest", "Detectable", "Weak", "No identifiable effect"],
    "fdr_drop": True,
    # Any label read from the facts passes through this map first (identity
    # for legacy; the new rules use it to run on legacy-labelled facts).
    "label_map": {},
    # Under the new rules Strong means "survives the FDR correction"; legacy
    # keeps the p < 0.01 label as stored.
    "fdr_means_strong": False,
    # Effective labels that get a full effect sentence ("established"), the
    # "uncertain" wording ("hint"), or "no identifiable" / "no clear link".
    "established": ["Strong", "Clear", "Modest"],
    "hint": ["Detectable"],
    # Temperature El Niño sentence by effective label. {lead} is "fall" north
    # of the equator and "Sep–Nov" south of it. The fraction clause is added
    # for fraction_labels when the rounded share is at least fraction_min_pct.
    "temp_enso": {
        "Strong": ("There is a strong, well-established El Niño effect on temperature: "
                   "after El Niño conditions in the preceding {lead}, {S} tends to run {dir}"),
        "Clear": ("There is a clear El Niño effect on temperature: "
                  "after El Niño conditions in the preceding {lead}, {S} tends to run {dir}"),
        "Modest": ("There is a modest but consistent El Niño signal on temperature: "
                   "after El Niño conditions in the preceding {lead}, {S} tends to run {dir}"),
    },
    "temp_fraction": ", and El Niño accounts for about {fe}% of the year-to-year ups and downs",
    "fraction_labels": ["Strong", "Clear"],
    "fraction_min_pct": 10,
    "temp_hint": "El Niño's effect on {S} temperature is detectable but uncertain, a slight tilt toward a {dir} season.",
    "temp_enso_none": "El Niño has no identifiable effect on {S} temperature.",
    "temp_enso_none_merged": " and no identifiable El Niño link.",
    # "Without El Niño, a season this warm would come about once every N
    # years": effective labels that quote the return period.
    "return_period_labels": ["Strong", "Clear"],
    # The push sentence adds a size phrase for the small sizes and the
    # years-of-warming clause for years_min <= years <= years_max with a
    # warming effect.
    "push_size_phrase": {
        "Negligible": "small next to normal year-to-year swings and unlikely to be noticed",
        "Noticeable": "a noticeable tilt, though ordinary variability can easily outweigh it",
    },
    "years_min": 3,
    "years_max": 60,
    # Rainfall and humidity: adjective of the effect by effective label, the
    # sentence that carries it, and the closing size clause by size tier.
    "effect_adj": {
        "Strong": "a strong, well-established effect",
        "Clear": "a clear effect",
        "Modest": "a modest but consistent effect",
    },
    "effect_sentence": "El Niño has {adj} toward {target}{extras}, {size_clause}",
    "effect_sentence_by_label": {},
    "size_clause": {
        "Negligible": "but this year's shift is small next to normal swings",
        "Noticeable": "and this year's shift is a noticeable tilt",
        "Substantial": "and this year's shift is substantial",
        "Dominant": "and this year's shift is larger than a normal year-to-year swing",
    },
    "size_clause_by_label": {},
    "size_tiers": [[0.0, "Negligible"], [0.25, "Noticeable"], [0.5, "Substantial"], [1.0, "Dominant"]],
    "rain_hint_no_trend": "{S} rainfall shows no clear long-term trend, and only an uncertain hint of an El Niño effect.",
    "rain_hint_after_lead": "El Niño's effect is uncertain, with a slight tilt toward a {dir} season",
    "hum_hint_no_trend": "Humidity shows no clear long-term trend, and only an uncertain hint of an El Niño effect.",
    "hum_hint": "El Niño's effect on humidity is uncertain",
    # Stored labels of the 95th-percentile fit that earn "more intense
    # heavy-rain days"; the rainy-days clause follows the established group of
    # wet_day_share below a wet-day normal of wet_day_max_normal percent.
    "p95_labels": ["Strong", "Clear"],
    "tail_own_labels": ["Strong", "Clear"],
    "wet_day_max_normal": 90.0,
    # A trend is clear below this p. Temperature also needs the slope rounded
    # to 0.05 to be at least temp_trend_min; humidity needs hum_trend_min
    # points per decade; rainfall needs rain_pct_min percent of normal per
    # decade (2 to 2.5 reads "risen/fallen slightly").
    "trend_p": 0.05,
    "temp_trend_min": 0.05,
    "hum_trend_min": 0.1,
    "rain_pct_min": 2.0,
    # Below this 1991–2020 normal the rainfall sentence opens "Very little
    # rain falls in ...". The new rules cut at 25 mm and say nothing else.
    "dry_mm": 30.0,
    "dry_silences_effect": False,
    "dry_under": "about <%d",
    # Tail clauses: p of the 95th–5th difference below these.
    "tail_trend_p": 0.10,
    "tail_enso_p": 0.10,
    # Outlook bands on the largest tercile chance, from the top. "strict"
    # means the chance must exceed the bound.
    "chance_bands": [
        [0.95, True, "is", "very likely (more than 95% chance)"],
        [0.66, False, "is", "likely (about {pct}% chance)"],
        [0.5, False, "is", "more likely than not (about {pct}%)"],
        [0.4, False, "is", "slightly favored (about {pct}%)"],
    ],
    "plural_verb": {"is": "are", "has": "have"},
    "temp_even": "the temperature odds are close to even",
    "temp_near": "near-normal temperatures",
    # Rainfall and humidity outlook clauses appear from outlook_min; labels
    # outside the established group need outlook_min_other unless a
    # station-check clause applies first.
    "outlook_min": 0.55,
    "outlook_min_other": 0.66,
    # Attribution clauses after an outlook statement.
    "attribution_mode": "legacy",
    "attr_temp_trend": ", mostly because of the long-term warming trend rather than El Niño",
    "attr_other_trend": ", mostly because of the long-term trend rather than El Niño",
    "attr_station_drying": ", partly because of an uncertain long-term drying trend",
    "attr_enso_uncertain": ", resting on an El Niño effect that is not clearly established",
    "attr_below_clear": [],
    "attr_small_ratio": 0.25,
    # The shipped text writes "roughly 1 points" (Lagos MAM); legacy keeps it.
    "hum_total_plural_fault": True,
    # Written once, before the closing sentence, when the Sep–Nov RONI used
    # for the outlook exceeds the largest Sep–Nov value in the fit.
    "extrapolation": ("This El Niño is stronger than any in the record used here, so the estimate "
                      "extends the historical relationship beyond what has been observed."),
    "extrapolation_estimated": None,
    "closing": ("This outlook is based on the El Niño strength expected for Sep–Nov 2026 "
                "and will be updated when it is observed in early December."),
    "closing_beyond_record": None,
}


def _new_rules():
    """The 2026-11 rule set: LEGACY with the documented differences."""
    r = json.loads(json.dumps(LEGACY))
    # 1. Four labels; Strong already means "survives FDR", so nothing drops.
    r["conf_order"] = ["Strong", "Clear", "Suggestive", "No identifiable effect"]
    r["fdr_drop"] = False
    r["label_map"] = {"Modest": "Suggestive", "Detectable": "No identifiable effect",
                      "Weak": "No identifiable effect"}
    r["fdr_means_strong"] = True
    r["established"] = ["Strong", "Clear", "Suggestive"]
    r["hint"] = []
    r["temp_enso"] = {
        "Strong": LEGACY["temp_enso"]["Strong"],
        "Clear": ("There is a clear El Niño signal on temperature: "
                  "after El Niño conditions in the preceding {lead}, {S} tends to run {dir}"),
        "Suggestive": ("There is a suggestive but uncertain El Niño signal on temperature: "
                       "after El Niño conditions in the preceding {lead}, {S} tends to run {dir}"),
    }
    r["fraction_labels"] = ["Strong"]
    r["return_period_labels"] = ["Strong"]
    r["effect_adj"] = {
        "Strong": "a strong, well-established effect",
        "Clear": "a clear effect",
    }
    r["effect_sentence_by_label"] = {
        "Suggestive": "El Niño may have an effect toward {target}{extras}, though the evidence is thin, {size_clause}",
    }
    # After "though the evidence is thin" the small-size clause joins with
    # "and": both are caveats.
    r["size_clause_by_label"] = {
        "Suggestive": {"Negligible": "and this year's shift is small next to normal swings"},
    }
    # 2. Attribution by comparing |trend part| with |El Niño part|.
    r["attribution_mode"] = "parts"
    r["attr_below_clear"] = ["Suggestive", "No identifiable effect"]
    # 3. Dry seasons: 25 mm, and nothing but the normal is said.
    r["dry_mm"] = 25.0
    r["dry_silences_effect"] = True
    r["dry_under"] = "under %d"
    # 4. "about even odds" for 45–55%.
    r["chance_bands"] = [
        [0.95, True, "is", "very likely (more than 95% chance)"],
        [0.66, False, "is", "likely (about {pct}% chance)"],
        [0.55, False, "is", "more likely than not (about {pct}%)"],
        [0.45, False, "has", "about even odds (about {pct}%)"],
        [0.4, False, "is", "slightly favored (about {pct}%)"],
    ]
    # 5. "1 point", and the closing sentence names the range of the estimate
    #    when its upper end lies beyond the fitted record.
    r["hum_total_plural_fault"] = False
    r["extrapolation_estimated"] = ("The El Niño expected for Sep–Nov 2026 is stronger than any in the record "
                                    "used here, so the outlook extends the historical relationship beyond what "
                                    "has been observed.")
    r["closing_beyond_record"] = ("This outlook is based on the El Niño strength expected for Sep–Nov 2026, "
                                  "whose upper range exceeds any in the record used here, and will be "
                                  "updated when it is observed in early December.")
    return r


RULES = {"legacy": LEGACY, "new": _new_rules()}


# ---------------------------------------------------------------------------
# Number formatting (the original's helpers; round() is Python's half-to-even)
# ---------------------------------------------------------------------------

def r05(x):
    """Round to the nearest 0.05."""
    return round(x * 20) / 20


def num(x, nd=1):
    """Plain number without trailing zeros: 0.30 -> "0.3", 2.0 -> "2", -0.0 -> "0"."""
    s = ("%." + str(nd) + "f") % x
    s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def pct(p):
    """Chance as a percent rounded to 5."""
    return "%d%%" % int(round(p * 20) * 5)


def half_up(x):
    """Round half away from zero (the original rounded 1.25 swings to "1 times")."""
    return int(abs(x) + 0.5) * (1 if x >= 0 else -1)


def ratio_text(r):
    if r >= 1.25:
        return "about %s times a normal year-to-year swing" % num(half_up(r * 2) / 2)
    if r >= 0.95:
        return "about as large as a normal year-to-year swing"
    v = int(round(r * 10) * 10)
    return ("about %d%% of a normal year-to-year swing" % v) if v > 0 else "less than 10% of a normal year-to-year swing"


def amount(x):
    """Humidity points per decade: to 0.5 from 1 point, else to 0.1."""
    a = abs(x)
    return num(round(a * 2) / 2, 1) if a >= 1 else num(round(a, 1), 1)


def label_from_tiers(tiers, x):
    out = tiers[0][1]
    for lo, name in tiers:
        if x >= lo:
            out = name
    return out


# ---------------------------------------------------------------------------
# Context: one city-season record plus rules and station checks
# ---------------------------------------------------------------------------

class Cell(object):
    """One city-season with helpers the sentence builders share."""

    def __init__(self, rec, rules, checks, confirmed, lat):
        self.rec = rec
        self.R = rules
        self.checks = checks
        self.confirmed = confirmed
        self.city = rec["city"]
        self.season = rec["season"]
        self.S = SEASON_TEXT[rec["season"]]
        self.season_name = rec["season_name"]
        self.lead = "fall" if lat >= 0 else "Sep–Nov"
        self.v = rec["variables"]
        self.estimated = bool(rec.get("son_2026_roni_estimated", True))
        self.notes = []

    def stored_label(self, var):
        """Confidence label as stored, after the rule set's mapping."""
        x = self.v[var]
        lab = self.R["label_map"].get(x["confidence"], x["confidence"])
        if self.R["fdr_means_strong"] and x.get("survives_fdr"):
            lab = "Strong"
        return lab

    def label(self, var):
        """Effective label: Strong or Clear drop one step when the effect fails FDR."""
        lab = self.stored_label(var)
        if self.R["fdr_drop"] and lab in ("Strong", "Clear") and not self.v[var].get("survives_fdr"):
            order = self.R["conf_order"]
            lab = order[order.index(lab) + 1]
        return lab

    def group(self, var):
        lab = self.label(var)
        if lab in self.R["established"]:
            return "established"
        if lab in self.R["hint"]:
            return "hint"
        return "none"

    def map_label(self, lab):
        return self.R["label_map"].get(lab, lab)

    def size(self, var):
        x = self.v[var]
        return x.get("size") or label_from_tiers(self.R["size_tiers"], x["effect_ratio"])

    def check(self, var):
        """Station-check entry for this city, season and variable, or None."""
        entry = self.checks.get("%s|%s|%s" % (self.city, self.season, var))
        if entry and entry.get("note"):
            self.note(entry["note"])
        return entry

    def note(self, text):
        if text not in self.notes:
            self.notes.append(text)

    def is_confirmed(self, var):
        return "%s|%s|%s" % (self.city, self.season, var) in self.confirmed

    def pct(self, var):
        return self.v[var].get("percentiles") or {}

    def tails(self, var):
        return self.pct(var).get("tails") or {}

    def crossing(self, var):
        pc = self.pct(var)
        return any((pc.get(k) or {}).get("lines_cross") for k in ("p05", "p50", "p95"))

    def trend_clear(self, var):
        return self.v[var]["trend_p"] < self.R["trend_p"]

    def trend_part(self, var):
        x = self.v[var]
        if x.get("trend_part_2027") is not None:
            return x["trend_part_2027"]
        return x["expected_anomaly_2027"] - x["effect_this_season"]


# ---------------------------------------------------------------------------
# Temperature
# ---------------------------------------------------------------------------

def temp_sentences(c):
    R, t = c.R, c.v["temperature"]
    out = []
    chk = c.check("temperature")
    tr, tp = t["trend_per_decade"], t["trend_p"]
    pc, tails = c.pct("temperature"), c.tails("temperature")
    crossing = c.crossing("temperature")
    has_trend = tp < R["trend_p"] and abs(r05(tr)) >= R["temp_trend_min"] and not chk
    if has_trend:
        word = "warmed" if tr > 0 else "cooled"
        s = "%s in %s has %s by about %s °C per decade since 1951, roughly %s °C in all" % (
            c.S, c.city, word, num(abs(r05(tr)), 2), num(abs(tr) * 7.5, 1))
        if pc and not crossing:
            p05 = (pc.get("p05") or {}).get("trend_per_decade")
            p95 = (pc.get("p95") or {}).get("trend_per_decade")
            dp = tails.get("trend_difference_p")
            if dp is not None and dp < R["tail_trend_p"] and p05 is not None and p95 is not None:
                if tr > 0 and p95 > p05:
                    s += ", and the hottest days have warmed faster than the coldest (about %s vs %s °C per decade)" % (
                        num(r05(p95), 2), num(r05(p05), 2))
                elif tr > 0:
                    s += ", with the coldest days warming fastest, so cold extremes are becoming rarer"
        out.append(s + ".")
    elif chk and chk.get("text"):
        out.append(chk["text"])
    else:
        out.append("%s temperatures in %s show no clear long-term trend." % (c.S, c.city))

    lab, grp = c.label("temperature"), c.group("temperature")
    d = "warmer" if t["enso_effect_per_degC"] >= 0 else "cooler"
    if grp == "established":
        s = R["temp_enso"][lab].format(lead=c.lead, S=c.S, dir=d)
        if lab in R["fraction_labels"] and t.get("fraction_explained"):
            fe = int(round(t["fraction_explained"] * 20) * 5)
            if fe >= R["fraction_min_pct"]:
                s += R["temp_fraction"].format(fe=fe)
        out.append(s + ".")
        s = "With this year's strong El Niño, that push is " + ratio_text(t["effect_ratio"])
        size = c.size("temperature")
        if size in R["push_size_phrase"]:
            s += ", " + R["push_size_phrase"][size]
        yw = t.get("years_of_warming_equivalent")
        if yw and R["years_min"] <= yw <= R["years_max"] and t["enso_effect_per_degC"] > 0:
            s += ", roughly as much warmth as %d years of the long-term trend" % int(round(yw))
        out.append(s + ".")
        n = t.get("once_every_n_years_without_el_nino")
        if n and lab in R["return_period_labels"]:
            when = "less than once a century" if n == ">100" else "about once every %d years" % int(n)
            out.append("Without El Niño, a %s this %s would come %s." % (c.S, "warm" if d == "warmer" else "cool", when))
    elif grp == "hint":
        out.append(R["temp_hint"].format(S=c.S, dir=d))
    else:
        if out[-1].endswith("show no clear long-term trend."):
            out[-1] = out[-1][:-1] + R["temp_enso_none_merged"]
        else:
            out.append(R["temp_enso_none"].format(S=c.S))

    # extremes and El Niño: only with a confident tail and tails that differ
    if pc and not crossing and grp == "established":
        own = [c.map_label((pc.get(k) or {}).get("confidence")) for k in ("p05", "p95")]
        ep = tails.get("enso_difference_p")
        if any(x in R["tail_own_labels"] for x in own) and ep is not None and ep < R["tail_enso_p"]:
            s05, s95 = pc["p05"]["shift_this_season"], pc["p95"]["shift_this_season"]
            if abs(s95) >= abs(s05):
                out.append("El Niño moves the hottest days most: this season they are expected to shift by about %s °C, "
                           "against %s °C for the coldest days." % (num(round(s95, 1), 1), num(round(s05, 1), 1)))
            else:
                out.append("El Niño moves the coldest days most: this season they are expected to shift by about %s °C, "
                           "against %s °C for the hottest days." % (num(round(s05, 1), 1), num(round(s95, 1), 1)))
    return out


# ---------------------------------------------------------------------------
# Rainfall and humidity
# ---------------------------------------------------------------------------

def is_dry(c):
    p = c.v["precipitation"]
    if p.get("dry_season") is not None and c.R["dry_silences_effect"]:
        return bool(p["dry_season"])
    return p["normal_1991_2020"] < c.R["dry_mm"]


def effect_sentence(c, var, target, extras=""):
    R, lab = c.R, c.label(var)
    tmpl = R["effect_sentence_by_label"].get(lab, R["effect_sentence"])
    size = c.size(var)
    size_clause = R["size_clause_by_label"].get(lab, {}).get(size, R["size_clause"][size])
    return tmpl.format(adj=R["effect_adj"].get(lab), target=target, extras=extras, size_clause=size_clause)


def rain_sentence(c):
    """One sentence on rainfall: trend and El Niño. Returns (text or None, quiet)."""
    R, v = c.R, c.v["precipitation"]
    w = c.v.get("wet_day_share")
    normal = v["normal_1991_2020"]
    pct_tr = v.get("trend_pct_of_normal_per_decade")
    trend_txt = None
    if is_dry(c):
        n = int(round(normal / 5) * 5)
        trend_txt = "Very little rain falls in %s in %s (%s mm in a normal season)" % (
            c.S, c.city, ("about %d" % n) if n else (R["dry_under"] % 5))
        if R["dry_silences_effect"]:
            return trend_txt + ".", False
    else:
        chk = c.check("precipitation")
        if chk:
            if chk["kind"] == "slight_decline":
                trend_txt = "%s rainfall has declined slightly, though station records do not show the decline clearly" % c.S
            elif chk["kind"] == "unverified" and v["trend_p"] < R["trend_p"]:
                trend_txt = ("%s is the dry season in %s; rainfall has tended to %s in this record, "
                             "a trend that station records cannot yet confirm"
                             % (c.S, c.city, "decline" if v["trend_per_decade"] < 0 else "rise"))
        elif v["trend_p"] < R["trend_p"] and pct_tr is not None and abs(pct_tr) >= R["rain_pct_min"]:
            r = int(round(abs(pct_tr) / 5) * 5)
            word = "risen" if pct_tr > 0 else "fallen"
            trend_txt = ("%s rainfall has %s by about %d%% per decade" % (c.S, word, r)) if r else \
                        ("%s rainfall has %s slightly" % (c.S, word))
    lab, grp = c.label("precipitation"), c.group("precipitation")
    d = "wetter" if v["enso_effect_per_degC"] >= 0 else "drier"
    enso_txt = None
    if grp == "established":
        extra = ""
        if w and c.group("wet_day_share") == "established" \
                and (w["enso_effect_per_degC"] >= 0) == (v["enso_effect_per_degC"] >= 0) \
                and w["normal_1991_2020"] < R["wet_day_max_normal"]:
            extra = " with %s rainy days" % ("more" if d == "wetter" else "fewer")
        p95 = c.pct("precipitation").get("p95") or {}
        if p95 and not p95.get("lines_cross") and c.map_label(p95.get("confidence")) in R["p95_labels"] \
                and (p95["enso_effect_per_degC"] >= 0) == (v["enso_effect_per_degC"] >= 0):
            extra += "%s %s intense heavy-rain days" % (" and" if extra else " with", "more" if d == "wetter" else "less")
        enso_txt = effect_sentence(c, "precipitation", "a %s season" % d, extra)
    elif grp == "hint":
        enso_txt = R["rain_hint_after_lead"].format(dir=d)
    if trend_txt and enso_txt:
        return "%s. %s." % (trend_txt, enso_txt[0].upper() + enso_txt[1:]), False
    if trend_txt:
        return "%s, with no clear El Niño link." % trend_txt, False
    if enso_txt:
        if grp == "hint":
            return R["rain_hint_no_trend"].format(S=c.S), False
        return "%s rainfall shows no clear long-term trend, but %s." % (c.S, enso_txt), False
    return None, True


def rh_sentence(c, temp_rising):
    R, v = c.R, c.v["rel_humidity"]
    chk = c.check("rel_humidity")
    tr, tp = v["trend_per_decade"], v["trend_p"]
    trend_txt = None
    if chk:
        if chk.get("text"):
            trend_txt = chk["text"].rstrip(".")
        elif chk["kind"] == "none":
            trend_txt = "Relative humidity shows no clear long-term trend in station records"
        elif chk["kind"] == "uncertain":
            trend_txt = "Relative humidity may have risen, but station records do not confirm it"
        elif chk["kind"] == "value":
            x = float(chk["value"])
            trend_txt = "Relative humidity has %s by about %s point%s per decade since 1951" % (
                "fallen" if x < 0 else "risen", amount(x), "s" if abs(x) != 1 else "")
    elif tp < R["trend_p"] and abs(tr) >= R["hum_trend_min"]:
        total = int(round(abs(tr) * 7.5))
        unit_total = "points" if (total != 1 or R["hum_total_plural_fault"]) else "point"
        trend_txt = "Relative humidity has %s by about %s point%s per decade, roughly %d %s since 1951" % (
            "risen" if tr > 0 else "fallen", amount(tr), "" if amount(tr) == "1" else "s", total, unit_total)
        if c.is_confirmed("rel_humidity"):
            trend_txt += " (a change weather-station records confirm)"
        if tr < 0 and temp_rising:
            trend_txt += "; because warmer air holds more moisture, this does not necessarily mean the air is drier"
    lab, grp = c.label("rel_humidity"), c.group("rel_humidity")
    d = "more humid" if v["enso_effect_per_degC"] >= 0 else "less humid"
    enso_txt = None
    if grp == "established":
        enso_txt = effect_sentence(c, "rel_humidity", "a %s %s" % (d, c.S))
    elif grp == "hint":
        enso_txt = R["hum_hint"]
    if trend_txt and enso_txt:
        # The two join with ", and" unless either already carries a clause of
        # its own (a semicolon, a parenthesis, a station "but", a "though").
        if ";" in trend_txt or "(" in trend_txt or ", but" in trend_txt or ", though" in enso_txt \
                or (chk and chk.get("text")):
            return "%s. %s." % (trend_txt, enso_txt[0].upper() + enso_txt[1:]), False
        return "%s, and %s." % (trend_txt, enso_txt), False
    if trend_txt:
        return trend_txt + ".", False
    if enso_txt:
        if grp == "hint":
            return R["hum_hint_no_trend"], False
        return "Humidity shows no clear long-term trend, but %s." % enso_txt, False
    return None, True


# ---------------------------------------------------------------------------
# Outlook
# ---------------------------------------------------------------------------

def chance_band(c, m, plural=False):
    """'is likely (about 70% chance)' for the largest tercile chance m, or None below the lowest band."""
    for lo, strict, verb, tmpl in c.R["chance_bands"]:
        if (m > lo) if strict else (m >= lo):
            if plural:
                verb = c.R["plural_verb"][verb]
            return verb + " " + tmpl.format(pct=pct(m)[:-1])
    return None


CAT = {"temperature": ("a warmer-than-normal season", "a cooler-than-normal season"),
       "precipitation": ("a wetter-than-normal season", "a drier-than-normal season"),
       "rel_humidity": ("a more humid season than normal", "a less humid season than normal")}


def forecast(c, var):
    """(statement, largest chance, side) with side 'above', 'below' or 'near'; statement None below the lowest band."""
    x = c.v[var]
    probs = [x["p_below"], x["p_near"], x["p_above"]]
    i = max(range(3), key=lambda k: probs[k])
    m = probs[i]
    side = ("below", "near", "above")[i]
    if var == "temperature" and side == "near":
        cat, band = c.R["temp_near"], chance_band(c, m, plural=True)
    else:
        cat = CAT[var][0] if side == "above" else (CAT[var][1] if side == "below" else "a near-normal season")
        band = chance_band(c, m)
    if band is None:
        return None, m, side
    return "%s %s" % (cat, band), m, side


def attribution_parts(c, var, side):
    """New rules: compare the trend part with the El Niño part of the anomaly."""
    R, x = c.R, c.v[var]
    tp, ep, sd = c.trend_part(var), x["effect_this_season"], x["intrinsic_sd"]
    sign = 1 if side == "above" else -1
    if abs(tp) < R["attr_small_ratio"] * sd and abs(ep) < R["attr_small_ratio"] * sd:
        return ""
    if abs(tp) > abs(ep):
        if tp * sign <= 0 or (var == "temperature" and tp <= 0):
            return ""
        return R["attr_temp_trend"] if var == "temperature" else R["attr_other_trend"]
    if c.label(var) in R["attr_below_clear"] and ep * sign > 0:
        return R["attr_enso_uncertain"]
    return ""


def outlook(c):
    R, t = c.R, c.v["temperature"]
    ft, mt, side = forecast(c, "temperature")
    if ft:
        sent = "For %s, %s" % (c.season_name, ft)
        a = t["expected_anomaly_2027"]
        if side != "near" and abs(a) >= 0.05 and (a > 0) == (side == "above"):
            sent += ", about %s °C %s the 1991–2020 average" % (num(round(abs(a), 1), 1), "above" if a > 0 else "below")
        if R["attribution_mode"] == "parts":
            sent += attribution_parts(c, "temperature", side)
        elif c.group("temperature") != "established" and side == "above" and t["trend_per_decade"] > 0:
            sent += R["attr_temp_trend"]
    else:
        sent = "For %s, %s" % (c.season_name, R["temp_even"])
    others = []
    for var in ("precipitation", "rel_humidity"):
        if var == "precipitation" and is_dry(c) and R["dry_silences_effect"]:
            continue
        f, m, sd = forecast(c, var)
        if not f or m < R["outlook_min"] or sd == "near":
            continue
        chk = c.checks.get("%s|%s|%s" % (c.city, c.season, var))
        grp = c.group(var)
        trend_side = "above" if c.v[var]["trend_per_decade"] > 0 else "below"
        txt = f
        if var == "precipitation" and chk and chk["kind"] in ("unverified", "slight_decline") and sd == "below":
            txt += R["attr_station_drying"]
        elif var == "rel_humidity" and chk and chk["kind"] in ("none", "uncertain"):
            continue
        elif grp != "established" and m < R["outlook_min_other"]:
            continue
        elif R["attribution_mode"] == "parts":
            txt += attribution_parts(c, var, sd)
        elif grp != "established" and c.trend_clear(var) and sd == trend_side:
            txt += R["attr_other_trend"]
        others.append(txt)
    if others:
        sent += "; " + ", and ".join(others)
    parts = [sent + "."]
    beyond_record = not t.get("within_record", True)
    if beyond_record:
        parts.append((R["extrapolation_estimated"] if c.estimated else None) or R["extrapolation"])
    if c.estimated:
        # While the center is within the record but the upper end of the
        # estimate is not, the closing sentence says so; when the center
        # itself is beyond, the sentence above has said it.
        upper_beyond = R["closing_beyond_record"] and t.get("roni_upper_within_record") is False
        parts.append(R["closing_beyond_record"] if (upper_beyond and not beyond_record) else R["closing"])
    return parts


# ---------------------------------------------------------------------------
# Paragraph assembly
# ---------------------------------------------------------------------------

def paragraph(rec, rules, checks, confirmed, lat):
    """Returns (text, reviewer notes)."""
    c = Cell(rec, rules, checks, confirmed, lat)
    V = c.v
    sents = temp_sentences(c)
    temp_rising = V["temperature"]["trend_p"] < rules["trend_p"] and V["temperature"]["trend_per_decade"] > 0
    rain, rq = rain_sentence(c)
    rh, hq = rh_sentence(c, temp_rising)
    if rain:
        sents.append(rain)
    if rh:
        sents.append(rh)
    if rq and hq:
        sents.append("Rainfall and humidity show no clear trend or El Niño link.")
    elif rq:
        sents.append("Rainfall shows no clear trend or El Niño link.")
    elif hq:
        sents.append("Humidity shows no clear trend or El Niño link.")
    sents += outlook(c)
    if (V.get("wet_day_share") or {}).get("normal_1991_2020", 0) >= rules["wet_day_max_normal"]:
        c.note("ERA5 shows rain on more than 90% of days here (too much light drizzle, a known ERA5 bias), "
               "so rainy-day statements are left out.")
    text = " ".join(sents).replace(" °C", NBSP + "°C").replace(" mm", NBSP + "mm")
    return text, c.notes


def load_overrides(path, rule_name):
    """(station checks, confirmed set) for one rule set: the 'shared' block updated by the set's own block."""
    if not os.path.exists(path):
        return {}, set()
    data = json.load(open(path, encoding="utf-8"))
    checks = {}
    for block in ("shared", rule_name):
        for key, val in data.get("station_check", {}).get(block, {}).items():
            checks[key] = dict(val)
    return checks, set(data.get("confirmed", []))


def load_latitudes(path):
    """City -> latitude, from data/cities.csv (the pipeline's list) or a site cities.json."""
    if path.endswith(".csv"):
        import csv
        with open(path, encoding="utf-8") as f:
            return {r["city"]: float(r["lat"]) for r in csv.DictReader(f)}
    cities = json.load(open(path, encoding="utf-8"))
    return {c["name"]: c["lat"] for c in cities}


def generate(facts, rules, checks, confirmed, lats):
    paras, notes = {}, {}
    for rec in facts:
        key = "%s|%s" % (rec["city"], rec["season"])
        paras[key], notes[key] = paragraph(rec, rules, checks, confirmed, lats.get(rec["city"], 0.0))
    return paras, notes


def write_markdown(paras, notes, facts, path, rule_name):
    lines = ["# City paragraphs (%s rules)" % rule_name, "",
             "Generated by code/05_write_paragraphs.py from data/processed/city_facts.json. "
             "*Italic lines are reviewer notes and do not appear on the website.*", ""]
    for rec in facts:
        key = "%s|%s" % (rec["city"], rec["season"])
        lines += ["## %s %s" % (rec["city"], rec["season"]), "", paras[key], ""]
        for nt in notes[key]:
            lines += ["*Reviewer: %s*" % nt, ""]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Comparison with the shipped paragraphs
# ---------------------------------------------------------------------------

def split_sentences(text):
    return re.split(r"(?<=\.) (?=[A-Z])", text)


def first_diff(a, b):
    """Minimal diff of the first differing sentence: common prefix, then the two tails."""
    sa, sb = split_sentences(a), split_sentences(b)
    for x, y in zip(sa, sb):
        if x != y:
            i = 0
            while i < min(len(x), len(y)) and x[i] == y[i]:
                i += 1
            j = 0
            while j < min(len(x), len(y)) - i and x[-1 - j] == y[-1 - j]:
                j += 1
            cut = lambda s: s[max(0, i - 25):i] + "[" + s[i:len(s) - j] + "]" + s[len(s) - j:len(s) - j + 25]
            return cut(x), cut(y)
    if len(sa) != len(sb):
        extra = sa[len(sb):] if len(sa) > len(sb) else sb[len(sa):]
        return ("extra in %s: " % ("original" if len(sa) > len(sb) else "generated")) + " ".join(extra), ""
    return "", ""


def check(paras, site_dir):
    matches, mismatches = 0, []
    for name in sorted(os.listdir(site_dir)):
        if not name.endswith(".json"):
            continue
        d = json.load(open(os.path.join(site_dir, name), encoding="utf-8"))
        for season, sd in d["seasons"].items():
            key = "%s|%s" % (d["name"], season)
            orig = (sd.get("paragraph") or "").replace(NBSP, " ")
            gen = paras.get(key, "").replace(NBSP, " ")
            if orig == gen:
                matches += 1
            else:
                mismatches.append((d["name"], season, first_diff(orig, gen)))
    print("%d of %d paragraphs match exactly" % (matches, matches + len(mismatches)))
    for city, season, (o, g) in mismatches:
        print("\n%s %s" % (city, season))
        print("  original : %s" % o)
        print("  generated: %s" % g)
    return len(mismatches)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--facts", default=os.path.join(ROOT, "data", "processed", "city_facts.json"))
    ap.add_argument("--rules", choices=sorted(RULES), default="legacy")
    ap.add_argument("--overrides", default=os.path.join(ROOT, "code", "paragraph_overrides.json"))
    ap.add_argument("--cities", default=os.path.join(ROOT, "data", "cities.csv"),
                    help="city list with latitudes (hemisphere decides 'fall' vs 'Sep–Nov'); data/cities.csv or a site cities.json")
    ap.add_argument("--out", help="markdown file with all paragraphs and reviewer notes")
    ap.add_argument("--json-out", help='JSON object keyed "City|SEASON" -> paragraph')
    ap.add_argument("--check", metavar="DIR", help="compare with site/data/city/*.json")
    args = ap.parse_args(argv)

    facts = json.load(open(args.facts, encoding="utf-8"))
    rules = RULES[args.rules]
    checks, confirmed = load_overrides(args.overrides, args.rules)
    lats = load_latitudes(args.cities)
    paras, notes = generate(facts, rules, checks, confirmed, lats)

    if args.out:
        write_markdown(paras, notes, facts, args.out, args.rules)
        print("%d paragraphs -> %s" % (len(paras), args.out))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(paras, fh, ensure_ascii=False, indent=1)
        print("%d paragraphs -> %s" % (len(paras), args.json_out))
    if args.check:
        return 1 if check(paras, args.check) else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())

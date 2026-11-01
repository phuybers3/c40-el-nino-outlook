"""
Step 6 - Write the city paragraphs from city_facts.json, following docs/translation_guide.md.

Writes docs/city_paragraphs_DRAFT.md (one paragraph per city and season). Step 7 puts them on the website.
Re-run 5 -> 6 -> 7 whenever the numbers change (e.g. when CPC publishes Sep–Nov 2026 RONI in December):
the paragraphs then update with the numbers instead of having to be rewritten by hand.

STATION_CHECK below holds the decisions from the October 2026 station check (notebook Section 39):
trends that weather stations do not confirm are softened or not quoted. Edit it if new checks are done.
"""
import json
import sys
from pathlib import Path
import config as C

LAT = {name: lat for name, region, lat, lon in C.C40_CITIES}
ESTIMATED = C.SON_2026_RONI_SD > 0
SNAME = {"DJF": "Dec–Feb", "MAM": "Mar–May"}

# ---------------------------------------------------------------- station-check decisions (Oct 2026)
# key: (city, season, variable) -> how to treat the long-term trend
STATION_CHECK = {
    ("Ahmedabad", "DJF", "rel_humidity"): ("none", "Station records (Ahmedabad airport) show no humidity trend; ERA5's rise is not used."),
    ("Ahmedabad", "MAM", "rel_humidity"): ("none", "Station records show no rise in spring humidity; ERA5's rise is not used."),
    ("Dhaka", "DJF", "rel_humidity"): ("uncertain", "The station record (1997–2025) shows no trend; ERA5's rise is treated as uncertain."),
    ("Beijing", "MAM", "rel_humidity"): ("value:-1.0", "Station records confirm the decline but at about 1 point per decade, smaller than ERA5."),
    ("Vancouver", "DJF", "precipitation"): ("slight_decline", "The Vancouver Harbour station shows only a slight, uncertain decline (about −2% per decade), not ERA5's −10%."),
    ("Freetown", "DJF", "precipitation"): ("unverified", "No usable station record; ERA5's dry-season rainfall trend is unverified."),
    ("Lagos", "DJF", "precipitation"): ("unverified", "No usable station record; ERA5's dry-season rainfall trend is unverified."),
    ("Lagos", "DJF", "wet_day_share"): ("unverified", "No usable station record."),
    ("Accra", "DJF", "precipitation"): ("unverified", "No usable station record; ERA5's dry-season rainfall trend is unverified."),
    ("Accra", "DJF", "wet_day_share"): ("unverified", "No usable station record."),
    ("Santiago", "MAM", "temperature"): ("none", "ERA5 shows slight cooling that no usable station record can confirm; inland Santiago would normally be expected to warm."),
}
CONFIRMED = {  # station-confirmed trends worth saying so
    ("Delhi", "DJF", "rel_humidity"), ("Delhi", "MAM", "rel_humidity"),
    ("Hangzhou", "MAM", "rel_humidity"), ("Shanghai", "MAM", "rel_humidity"),
}

# ---------------------------------------------------------------- wording tables (translation guide §4–6)
CONF_ORDER = ["Strong", "Clear", "Modest", "Detectable", "Weak", "No identifiable effect"]
CONF_PHRASE = {"Strong": "a strong, well-established El Niño effect", "Clear": "a clear El Niño effect",
               "Modest": "a modest but consistent El Niño signal"}
CONF_ADJ = {"Strong": "a strong, well-established effect", "Clear": "a clear effect", "Modest": "a modest but consistent effect"}
DIR = {"temperature": ("warmer", "cooler"), "precipitation": ("wetter", "drier"),
       "rel_humidity": ("more humid", "less humid"), "wet_day_share": ("more rainy days", "fewer rainy days")}
CAT = {"temperature": ("a warmer-than-normal season", "a cooler-than-normal season"),
       "precipitation": ("a wetter-than-normal season", "a drier-than-normal season"),
       "wet_day_share": ("more rainy days than normal", "fewer rainy days than normal"),
       "rel_humidity": ("a more humid season than normal", "a less humid season than normal")}


def eff_conf(v):
    """Confidence used in the text: Strong/Clear that do not survive FDR are downgraded one step (§4a)."""
    c = v.get("confidence") or "No identifiable effect"
    if c in ("Strong", "Clear") and not v.get("survives_fdr"):
        c = CONF_ORDER[CONF_ORDER.index(c) + 1]
    return c


def r05(x):
    return round(x * 20) / 20


def num(x, nd=1):
    s = f"{x:.{nd}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def pct(p):
    return f"{int(round(p * 20) * 5)}%"


def ratio_text(r):
    if r >= 1.25:
        return f"about {num(round(r * 2) / 2)} times a normal year-to-year swing"
    if r >= 0.95:
        return "about as large as a normal year-to-year swing"
    v = int(round(r * 10) * 10)
    return f"about {v}% of a normal year-to-year swing" if v > 0 else "less than 10% of a normal year-to-year swing"


SIZE_PHRASE = {"Negligible": "small next to normal year-to-year swings and unlikely to be noticed",
               "Noticeable": "a noticeable tilt, though ordinary variability can easily outweigh it",
               "Substantial": "a substantial shift that people would likely notice",
               "Dominant": "larger than a typical year-to-year swing and likely to dominate the season"}


SIZE_CLAUSE = {"Negligible": "but this year's shift is small next to normal swings",
               "Noticeable": "and this year's shift is a noticeable tilt",
               "Substantial": "and this year's shift is substantial",
               "Dominant": "and this year's shift is larger than a normal year-to-year swing"}


def odds(p):
    if p > 0.95:
        return "very likely (more than 95% chance)"
    if p >= 0.66:
        return f"likely (about {pct(p)} chance)"
    if p >= 0.5:
        return f"more likely than not (about {pct(p)})"
    return f"slightly favored (about {pct(p)})"


def forecast(var, v):
    pb, pn, pa = v["p_below"], v["p_near"], v["p_above"]
    m = max(pb, pn, pa)
    if m < 0.4:
        return None, m, None
    near = "near-normal temperatures" if var == "temperature" else "a near-normal season"
    cat = CAT[var][0] if m == pa else (CAT[var][1] if m == pb else near)
    side = "above" if m == pa else ("below" if m == pb else "near")
    verb = "are" if cat.endswith("temperatures") else "is"
    return f"{cat} {verb} {odds(m)}", m, side


# ---------------------------------------------------------------- sentences
def temp_sentences(city, s, v, lead, notes):
    S = SNAME[s]
    out = []
    chk = STATION_CHECK.get((city, s, "temperature"))
    tr, tp = v["trend_per_decade"], v["trend_p"]
    pc = v.get("percentiles") or {}
    tails = pc.get("tails") or {}
    crossing = any((pc.get(k) or {}).get("lines_cross") for k in ("p05", "p50", "p95"))
    has_trend = tp < 0.05 and abs(r05(tr)) >= 0.05 and not chk
    if has_trend:
        word = "warmed" if tr > 0 else "cooled"
        t = f"{S} in {city} has {word} by about {num(abs(r05(tr)), 2)} °C per decade since 1951, roughly {num(abs(tr) * 7.5, 1)} °C in all"
        if pc and not crossing:
            p05, p95 = (pc.get("p05") or {}).get("trend_per_decade"), (pc.get("p95") or {}).get("trend_per_decade")
            if tails.get("trend_difference_p") is not None and tails["trend_difference_p"] < 0.1 and p05 is not None:
                if tr > 0 and p95 > p05:
                    t += f", and the hottest days have warmed faster than the coldest (about {num(r05(p95), 2)} vs {num(r05(p05), 2)} °C per decade)"
                elif tr > 0:
                    t += ", with the coldest days warming fastest, so cold extremes are becoming rarer"
        out.append(t + ".")
    else:
        if chk:
            notes.append(chk[1])
        out.append(f"{S} temperatures in {city} show no clear long-term trend.")

    c = eff_conf(v)
    up, down = DIR["temperature"]
    d = up if v["enso_effect_per_degC"] >= 0 else down
    if c in CONF_PHRASE:
        t = f"There is {CONF_PHRASE[c]} on temperature: after El Niño conditions in {lead}, {S} tends to run {d}"
        if c in ("Strong", "Clear") and v.get("fraction_explained"):
            fe = int(round(v["fraction_explained"] * 20) * 5)
            if fe >= 10:
                t += f", and El Niño accounts for about {fe}% of the year-to-year ups and downs"
        out.append(t + ".")
        t = f"With this year's strong El Niño, that push is {ratio_text(v['effect_ratio'])}"
        if v["size"] in ("Negligible", "Noticeable"):
            t += f", {SIZE_PHRASE[v['size']]}"
        yw = v.get("years_of_warming_equivalent")
        if yw and 3 <= yw <= 60 and v["enso_effect_per_degC"] > 0:
            t += f", roughly as much warmth as {int(round(yw))} years of the long-term trend"
        out.append(t + ".")
        n = v.get("once_every_n_years_without_el_nino")
        if n and c in ("Strong", "Clear"):
            when = "less than once a century" if n == ">100" else f"about once every {int(n)} years"
            out.append(f"Without El Niño, a {S} this {'warm' if d == 'warmer' else 'cool'} would come {when}.")
    elif c == "Detectable":
        out.append(f"El Niño's effect on {S} temperature is detectable but uncertain, a slight tilt toward a {d} season.")
    else:
        if out and out[-1].endswith("show no clear long-term trend."):
            out[-1] = out[-1].replace("show no clear long-term trend.", "show no clear long-term trend and no identifiable El Niño link.")
        else:
            out.append(f"El Niño has no identifiable effect on {S} temperature.")

    # extremes and El Niño (only with a confident percentile and tails that differ)
    if pc and not crossing and c in CONF_PHRASE:
        confs = [eff_conf({"confidence": (pc.get(k) or {}).get("confidence"), "survives_fdr": True}) for k in ("p05", "p95")]
        if any(x in ("Strong", "Clear") for x in confs) and (tails.get("enso_difference_p") or 1) < 0.1:
            s05, s95 = pc["p05"]["shift_this_season"], pc["p95"]["shift_this_season"]
            if abs(s95) >= abs(s05):
                out.append(f"El Niño moves the hottest days most: this season they are expected to shift by about {num(round(s95, 1), 1)} °C, against {num(round(s05, 1), 1)} °C for the coldest days.")
            else:
                out.append(f"El Niño moves the coldest days most: this season they are expected to shift by about {num(round(s05, 1), 1)} °C, against {num(round(s95, 1), 1)} °C for the hottest days.")
    return out


def rain_sentence(city, s, v, w, lead, notes):
    """One sentence on rainfall: trend + El Niño (+ rainy days). Returns (sentence or None, quiet?)."""
    S = SNAME[s]
    normal = v["normal_1991_2020"]
    chk = STATION_CHECK.get((city, s, "precipitation"))
    pct_tr = v.get("trend_pct_of_normal_per_decade")
    dry = normal < 30
    trend_txt = None
    if dry:
        trend_txt = f"Very little rain falls in {S} in {city} (about {int(round(normal / 5) * 5) or '<5'} mm in a normal season)"
    elif chk:
        notes.append(chk[1])
        if chk[0] == "slight_decline":
            trend_txt = f"{S} rainfall has declined slightly, though station records do not show the decline clearly"
        elif chk[0] == "unverified" and v["trend_p"] < 0.05:
            trend_txt = (f"{S} is the dry season in {city}; rainfall has tended to {'decline' if v['trend_per_decade'] < 0 else 'rise'}"
                         f" in this record, a trend that station records cannot yet confirm")
    elif v["trend_p"] < 0.05 and pct_tr is not None and abs(pct_tr) >= 2:
        r = int(round(abs(pct_tr) / 5) * 5)
        trend_txt = (f"{S} rainfall has {'risen' if pct_tr > 0 else 'fallen'} by about {r}% per decade" if r
                     else f"{S} rainfall has {'risen' if pct_tr > 0 else 'fallen'} slightly")
    c = eff_conf(v)
    up, down = DIR["precipitation"]
    d = up if v["enso_effect_per_degC"] >= 0 else down
    enso_txt = None
    if c in CONF_PHRASE:
        extra = ""
        if w and eff_conf(w) in CONF_PHRASE and (w["enso_effect_per_degC"] >= 0) == (v["enso_effect_per_degC"] >= 0) \
                and w["normal_1991_2020"] < 90:
            extra = f" with {'more' if d == 'wetter' else 'fewer'} rainy days"
        p95 = ((v.get("percentiles") or {}).get("p95") or {})
        if p95 and not p95.get("lines_cross") and p95.get("confidence") in ("Strong", "Clear") \
                and (p95["enso_effect_per_degC"] >= 0) == (v["enso_effect_per_degC"] >= 0):
            extra += f"{' and' if extra else ' with'} {'more' if d == 'wetter' else 'less'} intense heavy-rain days"
        enso_txt = f"El Niño has {CONF_ADJ[c]} toward a {d} season{extra}, {SIZE_CLAUSE[v['size']]}"
    elif c == "Detectable":
        enso_txt = f"El Niño's effect is uncertain, with a slight tilt toward a {d} season"
    if trend_txt and enso_txt:
        if True:
            return f"{trend_txt}. {enso_txt[0].upper() + enso_txt[1:]}.", False
        return f"{trend_txt}, and {enso_txt}.", False
    if trend_txt:
        return f"{trend_txt}, with no clear El Niño link.", False
    if enso_txt:
        if c == "Detectable":
            return f"{S} rainfall shows no clear long-term trend, and only an uncertain hint of an El Niño effect.", False
        return f"{S} rainfall shows no clear long-term trend, but {enso_txt}.", False
    return None, True


def rh_sentence(city, s, v, temp_rising, lead, notes):
    S = SNAME[s]
    chk = STATION_CHECK.get((city, s, "rel_humidity"))
    tr, tp = v["trend_per_decade"], v["trend_p"]
    trend_txt = None

    def amount(x):
        a = abs(x)
        return num(round(a * 2) / 2, 1) if a >= 1 else num(round(a, 1), 1)
    if chk:
        notes.append(chk[1])
        if chk[0] == "none":
            trend_txt = f"Relative humidity shows no clear long-term trend in station records"
        elif chk[0] == "uncertain":
            trend_txt = f"Relative humidity may have risen, but station records do not confirm it"
        elif chk[0].startswith("value:"):
            x = float(chk[0].split(":")[1])
            trend_txt = f"Relative humidity has {'fallen' if x < 0 else 'risen'} by about {amount(x)} point{'s' if abs(x) != 1 else ''} per decade since 1951"
    elif tp < 0.05 and abs(tr) >= 0.1:
        trend_txt = (f"Relative humidity has {'risen' if tr > 0 else 'fallen'} by about {amount(tr)} point{'' if amount(tr) == '1' else 's'} per decade, "
                     f"roughly {int(round(abs(tr) * 7.5))} points since 1951")
        if (city, s, "rel_humidity") in CONFIRMED:
            trend_txt += " (a change weather-station records confirm)"
        if tr < 0 and temp_rising:
            trend_txt += "; because warmer air holds more moisture, this does not necessarily mean the air is drier"
    c = eff_conf(v)
    up, down = DIR["rel_humidity"]
    d = up if v["enso_effect_per_degC"] >= 0 else down
    enso_txt = None
    if c in CONF_PHRASE:
        enso_txt = f"El Niño has {CONF_ADJ[c]} toward a {d} {S}, {SIZE_CLAUSE[v['size']]}"
    elif c == "Detectable":
        enso_txt = "El Niño's effect on humidity is uncertain"
    if trend_txt and enso_txt:
        sep = ". " if ";" in trend_txt or "(" in trend_txt else ", and "
        return f"{trend_txt}{sep}{enso_txt[0].upper() + enso_txt[1:] if sep == '. ' else enso_txt}.", False
    if trend_txt:
        return f"{trend_txt}.", False
    if enso_txt:
        if c == "Detectable":
            return "Humidity shows no clear long-term trend, and only an uncertain hint of an El Niño effect.", False
        return f"Humidity shows no clear long-term trend, but {enso_txt}.", False
    return None, True


def outlook(city, s, entry, temp_conf):
    V = entry["variables"]
    S_full = entry["season_name"]
    parts = []
    t = V["temperature"]
    ft, mt, side = forecast("temperature", t)
    if ft:
        sent = f"For {S_full}, {ft}"
        a = t["expected_anomaly_2027"]
        if side != "near" and abs(a) >= 0.05:
            sent += f", about {num(round(abs(a), 1), 1)} °C {'above' if a > 0 else 'below'} the 1991–2020 average"
        if temp_conf not in CONF_PHRASE and side == "above" and t["trend_per_decade"] > 0:
            sent += ", mostly because of the long-term warming trend rather than El Niño"
    else:
        sent = f"For {S_full}, the temperature odds are close to even"
    others = []
    for var in ("precipitation", "rel_humidity"):
        f, m, sd = forecast(var, V[var])
        if f and m >= 0.55 and sd != "near":
            txt = f
            chk = STATION_CHECK.get((city, s, var))
            ec = eff_conf(V[var])
            tr = V[var]["trend_per_decade"]
            trend_side = "above" if tr > 0 else "below"
            if var == "precipitation" and chk and chk[0] in ("unverified", "slight_decline") and sd == "below":
                txt += ", partly because of an uncertain long-term drying trend"
            elif var == "rel_humidity" and chk and chk[0] in ("none", "uncertain"):
                continue
            elif ec not in CONF_PHRASE and m < 0.66:
                continue
            elif ec not in CONF_PHRASE and V[var]["trend_p"] < 0.05 and sd == trend_side:
                txt += ", mostly because of the long-term trend rather than El Niño"
            others.append(txt)
    if others:
        sent += "; " + ", and ".join(others) if len(others) <= 2 else ""
    parts.append(sent + ".")
    if not t.get("within_record", True):
        parts.append("This El Niño is stronger than any in the record used here, so the estimate extends the historical relationship beyond what has been observed.")
    if ESTIMATED:
        parts.append("This outlook is based on the El Niño strength expected for Sep–Nov 2026 and will be updated when it is observed in early December.")
    return parts


def paragraph(entry):
    city, s = entry["city"], entry["season"]
    V = entry["variables"]
    lead = "the preceding fall" if LAT.get(city, 0) >= 0 else "the preceding Sep–Nov"
    notes = []
    sents = temp_sentences(city, s, V["temperature"], lead, notes)
    temp_rising = V["temperature"]["trend_p"] < 0.05 and V["temperature"]["trend_per_decade"] > 0
    rain, rq = rain_sentence(city, s, V["precipitation"], V.get("wet_day_share"), lead, notes)
    rh, hq = rh_sentence(city, s, V["rel_humidity"], temp_rising, lead, notes)
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
    sents += outlook(city, s, entry, eff_conf(V["temperature"]))
    if (V.get("wet_day_share") or {}).get("normal_1991_2020", 0) >= 90:
        notes.append("ERA5 shows rain on more than 90% of days here (too much light drizzle, a known ERA5 bias), so rainy-day statements are left out.")
    return " ".join(sents), notes


def main():
    facts_path = Path(sys.argv[1]) if len(sys.argv) > 1 else C.PROCESSED / "city_facts.json"
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else C.DOCS / "city_paragraphs_DRAFT.md"
    facts = json.load(open(facts_path, encoding="utf-8"))
    by_city = {}
    for e in facts:
        by_city.setdefault(e["city"], {})[e["season"]] = e
    lines = ["# City paragraphs — DRAFT for review",
             "",
             f"Written by `code/06_write_paragraphs.py` from `{facts_path.name}` following `docs/translation_guide.md`,",
             "with the October 2026 station-check decisions applied. *Italic lines are reviewer notes and do not appear on the website.*",
             ""]
    n = 0
    for name, *_ in C.C40_CITIES:
        if name not in by_city:
            continue
        lines += ["---", "", f"## {name}", ""]
        for s in ("DJF", "MAM"):
            e = by_city[name].get(s)
            if not e:
                continue
            text, notes = paragraph(e)
            text = text.replace(" °C", "\u00a0°C").replace(" mm", "\u00a0mm")   # keep numbers with their units
            lines += [f"**{e['season_name']}.** {text}", ""]
            for nt in notes:
                lines += [f"*Reviewer: {nt}*", ""]
            n += 1
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {n} paragraphs to {out_path}")


if __name__ == "__main__":
    main()

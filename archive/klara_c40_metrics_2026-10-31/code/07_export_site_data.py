"""
Step 7 - Export the small data files the website reads.

Run after steps 5 and 6 (needs city_facts.json and the paragraphs). Writes into site/data/:
  cities.json            one row per city: name, slug, region, lat, lon, and per season the
                         temperature ENSO confidence, direction and size (used to color the map)
  city/<slug>.json       everything one city page draws: per season the yearly series
                         (RONI lead, seasonal values, yearly 5th/50th/95th percentiles),
                         fitted-line coefficients, the numbers from city_facts.json and the paragraph
  meta.json              run settings (SON 2026 RONI, forecast year, fit years, label tables)

Paragraphs come from docs/city_paragraphs.md if it exists, else docs/city_paragraphs_DRAFT.md.
Reviewer notes (italic lines) are left out.
"""
import json
import re
import numpy as np
import pandas as pd
import config as C

SITE = C.ROOT / "site"
OUT = SITE / "data"
QCOL = {"temperature": "tmean", "precipitation": "precip", "rel_humidity": "rh"}


def slug(name):
    s = name.lower()
    for a, b in [("ã", "a"), ("á", "a"), ("â", "a"), ("é", "e"), ("ó", "o"), ("ô", "o"), ("í", "i"), ("ú", "u"), ("ç", "c"), ("ñ", "n")]:
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def r(v, n=3):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return None if not np.isfinite(f) else round(f, n)


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [clean(v) for v in o]
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (float, np.floating, np.integer)) and not isinstance(o, int):
        return r(o, 4)
    return o


def read_paragraphs():
    path = C.DOCS / "city_paragraphs.md"
    if not path.exists():
        path = C.DOCS / "city_paragraphs_DRAFT.md"
    out = {}
    if not path.exists():
        return out, None
    city = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            city = m.group(1)
            continue
        m = re.match(r"^\*\*(Dec|Mar)[^*]*\*\*\s*(.+)$", line)
        if city and m:
            season = "DJF" if m.group(1) == "Dec" else "MAM"
            out[(city, season)] = m.group(2).strip()
    return out, path.name


def main():
    facts = json.load(open(C.PROCESSED / "city_facts.json", encoding="utf-8"))
    facts = {(f["city"], f["season"]): f for f in facts}
    seasonal = pd.read_parquet(C.PROCESSED / "seasonal_panel.parquet")
    daily = pd.read_parquet(C.PROCESSED / "daily_panel.parquet")
    lin = pd.read_parquet(C.PROCESSED / "linear_results.parquet")
    qr = pd.read_parquet(C.PROCESSED / "quantile_results.parquet")
    qr = qr[qr["quantile"] != "95th-5th"].copy()
    paragraphs, para_file = read_paragraphs()
    (OUT / "city").mkdir(parents=True, exist_ok=True)

    cities = []
    for name, region, lat, lon in C.C40_CITIES:
        s_city = seasonal[seasonal["city"] == name]
        if s_city.empty:
            continue
        d_city = daily[daily["city"] == name]
        row = {"name": name, "slug": slug(name), "region": region, "lat": lat, "lon": lon, "seasons": {}}
        page = {"name": name, "slug": row["slug"], "region": region, "lat": lat, "lon": lon, "seasons": {}}
        for season in C.SEASONS:
            s = s_city[s_city["season"] == season].sort_values("year")
            f = facts.get((name, season))
            if s.empty or f is None:
                continue
            years = s["year"].astype(int).tolist()
            out = {"season_name": f["season_name"], "years": years,
                   "roni_lead": [r(v) for v in s["roni_lead"]],
                   "paragraph": paragraphs.get((name, season)), "variables": {}}
            for var, v in f["variables"].items():
                L = lin[(lin["city"] == name) & (lin["season"] == season) & (lin["variable"] == var)]
                entry = {k: (r(x, 4) if isinstance(x, (int, float)) and not isinstance(x, bool) else x)
                         for k, x in v.items() if k != "percentiles"}
                entry["values"] = [r(x) for x in s[var]]
                if not L.empty:
                    L = L.iloc[0]
                    # fitted mean line: a2027 + b*lead + c*(year - 2027)
                    x, sx = C.SON_2026_RONI, C.SON_2026_RONI_SD
                    entry["forecast_mean"] = r(L["a2027"] + L["enso_effect"] * x, 4)
                    entry["forecast_sd"] = r(np.sqrt(L["sd_residual"] ** 2 + L["var_a2027"] + x ** 2 * L["var_b"]
                                                     + 2 * x * L["cov_a2027_b"] + L["enso_effect"] ** 2 * sx ** 2), 4)
                    entry["fit"] = {"a2027": r(L["a2027"], 4), "b": r(L["enso_effect"], 4),
                                    "c": r(L["trend_per_decade"] / 10, 5),
                                    "tercile_low": r(L["tercile_low"], 4), "tercile_high": r(L["tercile_high"], 4)}
                if "percentiles" in v:
                    entry["percentiles"] = v["percentiles"]
                if var in QCOL:
                    d = d_city[d_city["season"] == season]
                    col = QCOL[var]
                    if var == "precipitation":
                        d = d[d[col] >= C.WET_DAY_MM]
                    emp = d.groupby("year")[col].quantile(C.QUANTILES).unstack().reindex(years)
                    q = qr[(qr["city"] == name) & (qr["season"] == season) & (qr["variable"] == var)]
                    lines = {}
                    for qv, key in zip(C.QUANTILES, ["p05", "p50", "p95"]):
                        entry.setdefault("yearly", {})[key] = [r(x) for x in emp[qv]] if qv in emp.columns else None
                        qq = q[q["quantile"].astype(float) == qv]
                        if not qq.empty:
                            qq = qq.iloc[0]
                            lines[key] = {"intercept": r(qq["intercept"], 4), "b": r(qq["enso_effect"], 4),
                                          "c": r(qq["trend_per_decade"] / 10, 5), "tbar": r(qq["tbar"], 3)}
                    entry["quantile_fit"] = lines or None
                out["variables"][var] = entry
            page["seasons"][season] = out
            t = f["variables"].get("temperature", {})
            row["seasons"][season] = {"confidence": t.get("confidence"), "survives_fdr": t.get("survives_fdr"),
                                      "effect": r(t.get("effect_this_season")), "size": t.get("size"),
                                      "p_above": r(t.get("p_above")), "has_paragraph": out["paragraph"] is not None}
        cities.append(row)
        with open(OUT / "city" / f"{row['slug']}.json", "w", encoding="utf-8") as fh:
            json.dump(clean(page), fh, ensure_ascii=False, separators=(",", ":"))

    with open(OUT / "cities.json", "w", encoding="utf-8") as fh:
        json.dump(cities, fh, ensure_ascii=False, separators=(",", ":"))
    meta = {"son_2026_roni": C.SON_2026_RONI, "son_2026_roni_sd": C.SON_2026_RONI_SD,
            "son_2026_estimated": C.SON_2026_RONI_SD > 0, "forecast_year": C.FORECAST_YEAR,
            "fit_years": [C.FIT_START, C.FIT_END], "baseline": list(C.BASELINE),
            "typical_el_nino": C.TYPICAL_EL_NINO, "wet_day_mm": C.WET_DAY_MM,
            "confidence": C.CONFIDENCE, "size": C.SIZE, "paragraph_source": para_file,
            "exported": pd.Timestamp.now().strftime("%Y-%m-%d")}
    with open(OUT / "meta.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=1)
    n_par = sum(1 for c in cities for s in c["seasons"].values() if s["has_paragraph"])
    print(f"Wrote {len(cities)} city files, cities.json and meta.json to {OUT} ({n_par} city-season paragraphs)")


if __name__ == "__main__":
    main()

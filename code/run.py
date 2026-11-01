"""Run the C40 El Niño outlook pipeline end to end.

    python code/run.py [--rules new|legacy] [--roni X --roni-sd Y --roni-source TEXT | --roni-cpc FILE]
                       [--skip-quantiles] [--reps 100] [--workers N] [--exported YYYY-MM-DD]

Steps, each a script in code/ that can also be run on its own:
    01_seasonal_panel.py   daily panel -> seasonal panel
    02_fit_linear.py       seasonal panel -> linear_results (trend, El Niño effect, FDR)
    03_fit_quantiles.py    daily panel -> quantile_results (5th/50th/95th, bootstrap); ~20 min on 7 cores
    04_build_facts.py      tables -> city_facts.json + facts_meta.json (labels, outlook)
    05_write_paragraphs.py facts -> docs/city_paragraphs.md + city_paragraphs.json
    06_export_site.py      everything -> site/data/
    07_build_workbook.py   tables + facts_meta -> C40_ENSO_outlook.xlsx (derived columns as live formulas)
    validate_workbook.py   evaluates the workbook's formulas in Python against city_facts.json
    08_plots.py            daily panel + quantile_results -> figures/<City>.png

The Sep-Nov RONI that drives the outlook is estimated from data/raw/RONI.ascii.txt
unless --roni is given: the latest three-month value of the lead year is regressed
on Sep-Nov across 1950-2025 and the fitted value and residual spread are used.
With --roni-cpc FILE the estimate is instead CPC's central estimate, derived by
cpc_roni.py from the chance CPC's ENSO discussion gives for the season to reach a
threshold (data/raw/cpc_enso_discussion_<date>.json); --roni-sd is then the spread
of that distribution. Once CPC publishes the Sep-Nov value itself (early December)
the estimate flag switches off and the observed value is used. Refresh the RONI file first:

    curl -o data/raw/RONI.ascii.txt https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "code"
SEASONS = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]


def estimate_roni(path: Path, lead_year: int, fit_years=(1950, 2025)) -> dict:
    """Sep-Nov RONI of the lead year: observed if published, else regressed on the latest season."""
    rows = [l.split() for l in path.read_text().strip().splitlines()[1:]]
    table: dict[int, dict[str, float]] = {}
    for season, year, anom in rows:
        table.setdefault(int(year), {})[season] = float(anom)
    have = table.get(lead_year, {})
    if "SON" in have:
        return {"roni": have["SON"], "sd": 0.0, "estimated": False,
                "source": f"CPC's observed Sep–Nov {lead_year} RONI of {have['SON']:+.2f} °C."}
    latest = max(have, key=SEASONS.index)
    x_latest = have[latest]
    pairs = [(table[y][latest], table[y]["SON"]) for y in range(fit_years[0], fit_years[1] + 1)
             if latest in table.get(y, {}) and "SON" in table.get(y, {})]
    n = len(pairs)
    mx = sum(x for x, _ in pairs) / n
    my = sum(y for _, y in pairs) / n
    sxx = sum((x - mx) ** 2 for x, _ in pairs)
    b = sum((x - mx) * (y - my) for x, y in pairs) / sxx
    a = my - b * mx
    resid = [y - (a + b * x) for x, y in pairs]
    sd = math.sqrt(sum(r * r for r in resid) / (n - 2))
    center = a + b * x_latest
    source = (f"Sep–Nov {lead_year} RONI is not yet published. The outlook uses {center:+.2f} ± {sd:.2f} °C, "
              f"the value a regression of Sep–Nov on {latest} RONI over {fit_years[0]}–{fit_years[1]} "
              f"(slope {b:.2f}, residual spread {sd:.2f} °C) gives for the observed {latest} {lead_year} value of {x_latest:+.2f} °C. "
              f"The estimate is refreshed as each later season is published and replaced by the observed value in early December.")
    return {"roni": round(center, 2), "sd": round(sd, 2), "estimated": True, "source": source, "season": latest}


def run(script: str, *args: str) -> None:
    cmd = [sys.executable, str(CODE / script), *map(str, args)]
    print("\n$", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--rules", choices=["new", "legacy"], default="new")
    ap.add_argument("--forecast-year", type=int, default=2027)
    ap.add_argument("--roni", type=float, help="override the Sep-Nov RONI estimate")
    ap.add_argument("--roni-sd", type=float, default=0.25)
    ap.add_argument("--roni-source", default="")
    ap.add_argument("--roni-file", default=ROOT / "data/raw/RONI.ascii.txt")
    ap.add_argument("--roni-cpc", help="CPC discussion file: use CPC's central estimate for the Sep-Nov RONI (see cpc_roni.py)")
    ap.add_argument("--skip-quantiles", action="store_true", help="reuse data/processed/quantile_results.csv")
    ap.add_argument("--reps", type=int, default=100)
    ap.add_argument("--workers", type=int)
    ap.add_argument("--exported", default=dt.date.today().isoformat())
    args = ap.parse_args()

    if args.roni is None and args.roni_cpc:
        sys.path.insert(0, str(CODE))
        from cpc_roni import cpc_central
        est = cpc_central(Path(args.roni_cpc), spread=args.roni_sd)
        roni, roni_sd, estimated, source = est["roni"], est["sd"], est["estimated"], est["source"]
    elif args.roni is None:
        est = estimate_roni(Path(args.roni_file), args.forecast_year - 1)
        roni, roni_sd, estimated, source = est["roni"], est["sd"], est["estimated"], est["source"]
    else:
        roni, roni_sd, estimated = args.roni, args.roni_sd, True
        source = args.roni_source or f"Sep–Nov {args.forecast_year - 1} RONI set by hand to {roni:+.2f} ± {roni_sd:.2f} °C."
    print(f"RONI for the outlook: {roni:+.2f} ± {roni_sd:.2f} ({'estimate' if estimated else 'observed'})")
    print(source)

    run("01_seasonal_panel.py")
    run("02_fit_linear.py", "--forecast-year", args.forecast_year)
    if not args.skip_quantiles:
        extra = ["--workers", args.workers] if args.workers else []
        run("03_fit_quantiles.py", "--reps", args.reps, "--forecast-year", args.forecast_year, *extra)
    run("04_build_facts.py", "--rules", args.rules, "--forecast-year", args.forecast_year,
        "--roni", roni, "--roni-sd", roni_sd, "--roni-source", source,
        *(["--roni-estimated"] if estimated else ["--roni-observed"]))
    run("05_write_paragraphs.py", "--facts", ROOT / "data/processed/city_facts.json", "--rules", args.rules,
        "--out", ROOT / "docs/city_paragraphs.md", "--json-out", ROOT / "data/processed/city_paragraphs.json")
    run("06_export_site.py", "--exported", args.exported, "--paragraph-source", "docs/city_paragraphs.md")
    run("07_build_workbook.py")
    run("validate_workbook.py")
    run("08_plots.py")


if __name__ == "__main__":
    main()

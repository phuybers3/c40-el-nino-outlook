# C40 cities: ENSO and trend metrics

For all 96 C40 cities, for Dec–Feb and Mar–May, and for temperature, rainfall (plus wet-day share) and relative humidity:
the long-term trend, the El Niño effect (from Sep–Nov RONI 3 and 6 months ahead), quantile regressions for the
coldest, typical and hottest days, labels for confidence and size, and a forecast for Dec 2026–Feb 2027 and Mar–May 2027.

## Folder layout

```
C40_ENSO_metrics.xlsx      the spreadsheet (start with the README and Summary tabs)
code/                      Python, run in order (see below)
  config.py                every setting: paths, years, seasons, thresholds, Sep–Nov 2026 RONI, city list
  01_prepare_data.py       ERA5 city files + RONI -> seasonal and daily tables
  02_fit_models.py         linear models + joint quantile regressions with bootstrap
  03_build_workbook.py     the spreadsheet (labels and forecasts are live formulas)
  04_plots.py              one figure per city
  05_city_facts.py         per-city facts (JSON) for writing the paragraphs
  06_write_paragraphs.py   the city paragraphs (docs/city_paragraphs_DRAFT.md), with station-check decisions
  07_export_site_data.py   small JSON files the website reads (site/data/)
  run_all.sh               runs 01-07
data/raw/                  INPUTS: c40_daily/*.parquet (ERA5, one file per city) and RONI.ascii.txt (CPC)
data/processed/            tables written by the pipeline (parquet + CSV)
figures/                   <City>.png
docs/
  methods_and_assumptions.md   what each step does, the math, every assumption
  translation_guide.md         how numbers become sentences in the city paragraphs
  city_paragraphs.md           the paragraphs (written after review)
```

## Running it

Requires Python 3.10+ with numpy, pandas, scipy, matplotlib, openpyxl, pyarrow.

```
cd code
bash run_all.sh
```

About 20 minutes on a laptop (the quantile bootstrap is the slow part; set `N_BOOT` in `config.py` lower for a quick test).

## Updating when CPC publishes Sep–Nov 2026 RONI (early December 2026)

Either change `SON_2026_RONI` (and set `SON_2026_RONI_SD = 0`) in `code/config.py` and re-run, or change
**Settings!B4** (and B5 to 0) in the spreadsheet; every forecast, size label and probability updates by formula.
The figures, per-city facts, paragraphs and website need the re-run (steps 4-7).

## Sources

- ERA5 hourly reanalysis (ECMWF/Copernicus Climate Change Service), point time series per city.
- RONI: NOAA Climate Prediction Center, https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt
- CPC ENSO Diagnostic Discussion, 8 October 2026 (basis for the Sep–Nov 2026 estimate).

## Website (site/)

`site/index.html` is the whole site (cover map, city pages, Data & methods). It reads `site/data/`,
which `code/07_export_site_data.py` fills. To look at it on your Mac: `cd site && python3 -m http.server`,
then open http://localhost:8000. To publish: push the project to GitHub and turn on GitHub Pages; the site
is then at `https://<user>.github.io/<repo>/site/`. City descriptions come from `docs/city_paragraphs.md` if it exists
(a hand-edited final version), otherwise from `docs/city_paragraphs_DRAFT.md`, which step 6 rewrites every run.
To hand-edit paragraphs, copy the DRAFT to `city_paragraphs.md` and edit that; step 6 never overwrites it.

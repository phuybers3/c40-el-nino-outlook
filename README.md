# C40 El Niño outlook

A static site and the pipeline behind it: how temperature, rainfall, rainy days and relative humidity in Dec–Feb and Mar–May have responded to El Niño in each of the 96 C40 cities since 1951, separately from the long-term trend, and what that implies for the 2027 seasons. Weather is ERA5 at one grid point per city; the El Niño index is NOAA CPC's Relative Oceanic Niño Index (RONI) for the Sep–Nov before each season.

The folder holds `data/` (the daily ERA5 panel, the RONI file, the city list and the processed tables), `code/` (the pipeline), `docs/` (the generated city descriptions and the generator's notes), `site/` (the page and the data files it reads), `C40_ENSO_outlook.xlsx` (the fitted statistics with the labels and the outlook as live formulas), `figures/` (one figure per city) and `archive/original_2026-10-31/` (the tables and site data as first shipped, used to validate the rebuild). The pipeline was rebuilt on 31 October 2026 from the shipped tables; `REVIEW_2026-10-31.md` records the review that prompted it. The original pipeline, Klara Kuemmerle's `c40_metrics` project, reached us the same evening; its code, documents, notebook and workbook are kept in `archive/klara_c40_metrics_2026-10-31/`, and `COMPARISON_KLARA_2026-10-31.md` compares the two. Her tables and site files are byte-identical to `archive/original_2026-10-31/`.

## Running

The environment is a virtual environment inside the folder with numpy, pandas, pyarrow, scipy, statsmodels, matplotlib and openpyxl. The generator script needs only the standard library.

```bash
python3 -m venv .venv && .venv/bin/pip install numpy pandas pyarrow scipy statsmodels matplotlib openpyxl
```

Refresh the RONI index, then run everything. The quantile step takes about twenty minutes on seven cores; pass `--skip-quantiles` to reuse the stored quantile table when only the outlook or the text changed.

```bash
curl -o data/raw/RONI.ascii.txt https://www.cpc.ncep.noaa.gov/data/indices/RONI.ascii.txt
```

```bash
.venv/bin/python code/run.py
```

The Sep–Nov RONI that drives the outlook is not observed until early December, and `run.py` offers three ways to set it. With `--roni-cpc FILE` it uses CPC's central estimate: `code/cpc_roni.py` reads the chance that CPC's ENSO discussion gives for the season to reach a threshold (stored with its issue date in `data/raw/cpc_enso_discussion_2026-10-08.json`, a 54% chance of +2.5 °C or more) and, with `--roni-sd` as the spread, returns the middle of that distribution, +2.53 ± 0.25 °C. This is the setting of the current release. With no option it regresses Sep–Nov on the latest season in the RONI file over 1950–2025 and uses the fitted value with its residual spread, a climatological estimate that sits below CPC's view in a historic event. With `--roni X --roni-sd Y --roni-source "..."` it takes the value given. In every case the value and a source sentence go to `data/processed/facts_meta.json`, from where the site's Methods page quotes them, and once the observed Sep–Nov value is in the RONI file the no-option run switches the estimate flag off and uses it. The current estimate exceeds the largest Sep–Nov value in the fit (+2.22 °C in 1997), and the paragraphs, the outlook notes and the chart caption say so.

```bash
.venv/bin/python code/run.py --roni-cpc data/raw/cpc_enso_discussion_2026-10-08.json --skip-quantiles
```

The site is served from `site/` by any static server, for example `python3 -m http.server --directory site`. Its cover map has a season switch and a variable switch (temperature, rainfall, rainy days, humidity); the export writes all four into `site/data/cities.json`, and `--index-only` rewrites that index and `meta.json` without the city files.

## Steps

`01_seasonal_panel.py` collapses `data/processed/daily_panel.parquet` to one row per city, season and year. `02_fit_linear.py` fits y = a + b·RONI + c·(year − t̄) to each of the 768 city-season-variable series and flags the El Niño effects that survive Benjamini–Hochberg at 5% as one family. `03_fit_quantiles.py` fits the same model to the daily values at the 5th, 50th and 95th percentiles with statsmodels QuantReg and takes uncertainty from a 100-replicate year-block bootstrap. `04_build_facts.py` turns the tables into `data/processed/city_facts.json`: labels, sizes, return periods and the 2027 outlook. `05_write_paragraphs.py` writes the city descriptions from the facts; its rules and every threshold are in a dictionary at the top of the file and `docs/PARAGRAPH_GENERATOR_NOTES.md` explains them. `06_export_site.py` writes `site/data/`.

`07_build_workbook.py` writes `C40_ENSO_outlook.xlsx`, a port of the workbook in Klara Kuemmerle's `c40_metrics` to our tables and our rules. The fitted statistics are values from `linear_results.csv` and `quantile_results.csv`. The confidence and size labels, the shrinkage factor and the shrunk effect, the 2027 centre and spread, the tercile chances, the return period and the forecast words are formulas. They read a Settings tab that holds the RONI estimate, its spread, the shrinkage switch and the eight τ² values behind the factors, and a Lookup tab that holds the tiers, the wording with its even-odds band and the direction words. Entering the observed Sep–Nov RONI in Settings!B4 updates every outlook in the file. The Summary tab pulls one row per city and season from the Linear tab, and the Definitions tab explains each column. openpyxl writes the formulas as text and nothing calculates them on disk, so `validate_workbook.py` parses them with openpyxl's tokenizer, evaluates them in Python with Excel's semantics for the dozen functions the builder uses, and compares the 44,319 derived and copied cells of the Linear, Quantiles, Tails and Summary tabs with `city_facts.json`. `run.py` runs the check after the build and stops on any mismatch.

`08_plots.py` writes `figures/<City>.png`, the figure from Klara's step 4 drawn from our quantile table. The top row shows the Sep–Nov RONI of the previous year as bars, with the estimate for the forecast year hatched and its spread as an error bar. The next three rows show daily mean temperature, wet-day rainfall and relative humidity: dots are each year's observed 5th, 50th and 95th percentile, lines are the fitted quantile regressions, which move with RONI, and a diamond marks the fit for 2027 at the RONI estimate. Each panel's subtitle gives the trend per decade and the El Niño confidence at each percentile under the current rules. Both scripts read the RONI and the rule tables from `facts_meta.json`, so they follow whatever `run.py` estimated or was told, and both run after the site export.

## Rule sets

`--rules legacy` reproduces the site as shipped on 2026-10-31. `--rules new`, the default, differs in five ways. Confidence has four tiers: Strong survives the FDR correction, Clear is p < 0.05, Suggestive is p < 0.10, and everything else has no identifiable effect. The El Niño effect is shrunk toward zero by an empirical-Bayes factor τ²/(τ² + se²), with τ² the spread of true effects across the 96 cities for that season and variable, before it enters the outlook, the size label and the text; the confidence label still uses the unshrunk test. The forecast anomaly is split into its trend and El Niño parts and the text attributes it to the larger one. Rainfall seasons with a 1991–2020 normal under 25 mm get no El Niño statement and no rainfall outlook. Chances between 45% and 55% are written as about even odds.

## Validation

The legacy mode is the acceptance test for the rebuild. Each step reproduces the archived table from the same inputs:

```bash
.venv/bin/python code/validate.py archive/original_2026-10-31/data_processed/linear_results.csv data/processed/linear_results.csv --key city season variable
```

```bash
.venv/bin/python code/04_build_facts.py --rules legacy --out /tmp/facts_legacy.json --meta-out /tmp/facts_meta_legacy.json --quantiles archive/original_2026-10-31/data_processed/quantile_results.csv && .venv/bin/python code/validate_json.py archive/original_2026-10-31/data_processed/city_facts.json /tmp/facts_legacy.json --ignore-extra
```

The seasonal panel, the linear table and the facts reproduce to floating-point precision. Quantile point estimates reproduce to three or four significant digits (the shipped solver stopped slightly short of the optimum) and bootstrap standard errors agree within Monte Carlo noise. `05_write_paragraphs.py --check site/data/city` compares generated paragraphs with the ones in a site data folder.

#!/usr/bin/env bash
# Runs the full C40 ENSO metrics pipeline. Run from the code/ folder.
set -euo pipefail
cd "$(dirname "$0")"
python3 01_prepare_data.py
python3 02_fit_models.py
python3 03_build_workbook.py
python3 04_plots.py
python3 05_city_facts.py
python3 06_write_paragraphs.py
python3 07_export_site_data.py
echo "Done. Open ../C40_ENSO_metrics.xlsx (README and Summary tabs first)."

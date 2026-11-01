"""
C40 ENSO metrics: every setting in one place.

Edit this file, not the other scripts, to change a choice. The spreadsheet's
Settings and Lookup tabs repeat the values marked (SHEET) so they can also be
changed there without re-running Python.
"""
from pathlib import Path

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"                 # c40_daily/*.parquet + RONI.ascii.txt go here
PROCESSED = ROOT / "data" / "processed"     # tables written by the pipeline
FIGURES = ROOT / "figures"
DOCS = ROOT / "docs"
ERA5_DIR = RAW / "c40_daily"
if not ERA5_DIR.exists():                   # fallback: c40_daily sitting next to this project folder (e.g. in ENSO/)
    for cand in (ROOT.parent / "c40_daily", ROOT.parent / "c40_daily 2"):
        if cand.exists():
            ERA5_DIR = cand
            break
RONI_FILE = RAW / "RONI.ascii.txt"
WORKBOOK = ROOT / "C40_ENSO_metrics.xlsx"

# ---------------------------------------------------------------- analysis window
FIT_START, FIT_END = 1951, 2025            # season-years used in every fit (SON 1950 -> DJF/MAM 1951)
BASELINE = (1991, 2020)                    # WMO normal: anomalies, terciles
FORECAST_YEAR = 2027                       # DJF 2027 = Dec 2026-Feb 2027; MAM 2027 = Mar-May 2027

# ---------------------------------------------------------------- seasons and ENSO predictor
# Each target season is predicted from Sep-Nov RONI of the PREVIOUS calendar year:
#   DJF(t) <- SON(t-1)  (3 months ahead)      MAM(t) <- SON(t-1)  (6 months ahead)
SEASONS = {"DJF": [12, 1, 2], "MAM": [3, 4, 5]}
PREDICTOR_SEASON = "SON"

# (SHEET) Sep-Nov 2026 RONI is not published until early December 2026. Until then we use an
# estimate: RONI rose from +1.36 (JJA) to +1.69 (JAS 2026); CPC's 8 Oct 2026 outlook gives an
# 83% chance of RONI >= +2.5 in OND. Replace with the published SON value when available.
SON_2026_RONI = 2.2
SON_2026_RONI_SD = 0.25                    # spread of that estimate (0 once SON is observed)
TYPICAL_EL_NINO = 1.5                      # (SHEET) RONI of a "typical strong" El Nino, for framing

# ---------------------------------------------------------------- variables
# key: (label, unit, seasonal aggregation for the linear model, daily column for quantiles)
VARIABLES = {
    "temperature": ("Mean temperature", "°C", "mean", "tmean"),
    "precipitation": ("Rainfall", "mm", "sum", "precip"),
    "wet_day_share": ("Share of wet days (≥1 mm)", "%", "wetshare", None),
    "rel_humidity": ("Relative humidity", "%", "mean", "rh"),
}
WET_DAY_MM = 1.0                           # precipitation quantiles use wet days only
QUANTILES = [0.05, 0.50, 0.95]
N_BOOT = 30                               # year-block bootstrap draws for quantile uncertainty (30 = quick test)
MIN_SEASON_COVERAGE = 0.97                 # share of a season's days that must exist

# ---------------------------------------------------------------- lookup tables (SHEET)
# Confidence that an ENSO effect exists, from the p-value of the ENSO term (lower bound inclusive).
CONFIDENCE = [  # (p lower bound, label)
    (0.00, "Strong"),
    (0.01, "Clear"),
    (0.05, "Modest"),
    (0.10, "Detectable"),
    (0.20, "Weak"),
    (0.50, "No identifiable effect"),
]
# Size of the effect relative to natural variability: |ENSO effect this season| / residual SD.
SIZE = [  # (ratio lower bound, label)
    (0.00, "Negligible"),
    (0.25, "Noticeable"),
    (0.50, "Substantial"),
    (1.00, "Dominant"),
]
FDR_ALPHA = 0.05

# ---------------------------------------------------------------- cities (C40 membership, May 2026)
C40_CITIES = [
    ("Abidjan", "Africa", 5.36, -4.01), ("Accra", "Africa", 5.60, -0.19), ("Addis Ababa", "Africa", 9.03, 38.74),
    ("Cape Town", "Africa", -33.92, 18.42), ("Casablanca", "Africa", 33.57, -7.59), ("Dakar", "Africa", 14.72, -17.47),
    ("Dar es Salaam", "Africa", -6.79, 39.21), ("Durban", "Africa", -29.86, 31.02), ("Ekurhuleni", "Africa", -26.20, 28.25),
    ("Freetown", "Africa", 8.48, -13.23), ("Johannesburg", "Africa", -26.20, 28.05), ("Lagos", "Africa", 6.52, 3.38),
    ("Nairobi", "Africa", -1.29, 36.82), ("Tshwane", "Africa", -25.75, 28.19),
    ("Ahmedabad", "South & West Asia", 23.02, 72.57), ("Amman", "South & West Asia", 31.95, 35.93),
    ("Bengaluru", "South & West Asia", 12.97, 77.59), ("Chennai", "South & West Asia", 13.08, 80.27),
    ("Delhi", "South & West Asia", 28.61, 77.21), ("Dhaka", "South & West Asia", 23.81, 90.41),
    ("Dubai", "South & West Asia", 25.20, 55.27), ("Istanbul", "South & West Asia", 41.01, 28.98),
    ("Karachi", "South & West Asia", 24.86, 67.01), ("Mumbai", "South & West Asia", 19.08, 72.88),
    ("Tel Aviv-Yafo", "South & West Asia", 32.09, 34.78),
    ("Bangkok", "Southeast Asia & Oceania", 13.76, 100.50), ("Hanoi", "Southeast Asia & Oceania", 21.03, 105.85),
    ("Ho Chi Minh City", "Southeast Asia & Oceania", 10.82, 106.63), ("Jakarta", "Southeast Asia & Oceania", -6.21, 106.85),
    ("Kuala Lumpur", "Southeast Asia & Oceania", 3.14, 101.69), ("Quezon City", "Southeast Asia & Oceania", 14.68, 121.04),
    ("Singapore", "Southeast Asia & Oceania", 1.35, 103.82), ("Auckland", "Southeast Asia & Oceania", -36.85, 174.76),
    ("Melbourne", "Southeast Asia & Oceania", -37.81, 144.96), ("Sydney", "Southeast Asia & Oceania", -33.87, 151.21),
    ("Beijing", "East Asia", 39.90, 116.41), ("Chengdu", "East Asia", 30.57, 104.07), ("Dalian", "East Asia", 38.91, 121.61),
    ("Fuzhou", "East Asia", 26.07, 119.30), ("Guangzhou", "East Asia", 23.13, 113.26), ("Hangzhou", "East Asia", 30.27, 120.16),
    ("Hong Kong", "East Asia", 22.32, 114.17), ("Nanjing", "East Asia", 32.06, 118.80), ("Qingdao", "East Asia", 36.07, 120.38),
    ("Seoul", "East Asia", 37.57, 126.98), ("Shanghai", "East Asia", 31.23, 121.47), ("Shenzhen", "East Asia", 22.54, 114.06),
    ("Tokyo", "East Asia", 35.68, 139.69), ("Wuhan", "East Asia", 30.59, 114.31), ("Yokohama", "East Asia", 35.44, 139.64),
    ("Zhenjiang", "East Asia", 32.19, 119.43),
    ("Amsterdam", "Europe", 52.37, 4.90), ("Athens", "Europe", 37.98, 23.73), ("Barcelona", "Europe", 41.39, 2.17),
    ("Berlin", "Europe", 52.52, 13.40), ("Copenhagen", "Europe", 55.68, 12.57), ("Heidelberg", "Europe", 49.40, 8.67),
    ("Lisbon", "Europe", 38.72, -9.14), ("London", "Europe", 51.51, -0.13), ("Madrid", "Europe", 40.42, -3.70),
    ("Milan", "Europe", 45.46, 9.19), ("Oslo", "Europe", 59.91, 10.75), ("Paris", "Europe", 48.86, 2.35),
    ("Rome", "Europe", 41.90, 12.50), ("Rotterdam", "Europe", 51.92, 4.48), ("Stockholm", "Europe", 59.33, 18.07),
    ("Warsaw", "Europe", 52.23, 21.01),
    ("Austin", "North America", 30.27, -97.74), ("Boston", "North America", 42.36, -71.06),
    ("Chicago", "North America", 41.88, -87.63), ("Los Angeles", "North America", 34.05, -118.24),
    ("Miami", "North America", 25.76, -80.19), ("Montréal", "North America", 45.50, -73.57),
    ("New Orleans", "North America", 29.95, -90.07), ("New York City", "North America", 40.71, -74.01),
    ("Philadelphia", "North America", 39.95, -75.17), ("Phoenix", "North America", 33.45, -112.07),
    ("Portland", "North America", 45.52, -122.68), ("San Francisco", "North America", 37.77, -122.42),
    ("Seattle", "North America", 47.61, -122.33), ("Toronto", "North America", 43.65, -79.38),
    ("Vancouver", "North America", 49.28, -123.12), ("Washington, DC", "North America", 38.91, -77.04),
    ("Ciudad de México", "Latin America", 19.43, -99.13), ("Guadalajara", "Latin America", 20.67, -103.35),
    ("Bogotá", "Latin America", 4.71, -74.07), ("Medellín", "Latin America", 6.24, -75.58),
    ("Quito", "Latin America", -0.18, -78.47), ("Lima", "Latin America", -12.05, -77.04),
    ("Santiago", "Latin America", -33.45, -70.67), ("Buenos Aires", "Latin America", -34.60, -58.38),
    ("São Paulo", "Latin America", -23.55, -46.63), ("Rio de Janeiro", "Latin America", -22.91, -43.17),
    ("Curitiba", "Latin America", -25.43, -49.27), ("Salvador", "Latin America", -12.97, -38.50),
    ("Fortaleza", "Latin America", -3.73, -38.52),
]
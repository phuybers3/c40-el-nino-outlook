# Methods and assumptions, step by step

Each step lists what the code does, the math, and every assumption it makes. Script names refer to `code/`.

---

## Step 1 — Data (`01_prepare_data.py`)

**What it does.** Reads each city's daily ERA5 file and CPC's RONI table, and builds one value per city × season × year plus a daily table for the quantile regressions.

- **Weather:** ERA5 reanalysis, hourly, at one grid point per city (moved to the nearest mostly-land point), aggregated to local days. Columns used: daily mean temperature, daily rainfall total, daily mean relative humidity.
- **Seasons:** Dec–Feb (December counted with the following Jan–Feb) and Mar–May. Fit years 1951–2025 (75 seasons).
- **Seasonal values:** mean temperature; rainfall total; share of days with ≥ 1 mm (wet-day share); mean relative humidity.
- **Predictor:** Sep–Nov RONI of the previous year, x. Dec–Feb(t) and Mar–May(t) both use Sep–Nov(t − 1): 3 and 6 months ahead.

**Assumptions**
1. One ERA5 grid point represents the city (≈ 25 km box; smooths coastal and urban effects).
2. ERA5 rainfall is adequate (model-generated; agrees with stations at r ≈ 0.66–0.85 for seasonal anomalies).
3. A season counts only if ≥ 97% of its days exist.
4. RONI is the right ENSO index: Niño 3.4 with the tropical-mean warming removed, CPC's official index since 2025, used by the ENSO crop atlas and CPC outlooks.
5. **Sep–Nov 2026 RONI is not observed yet.** It is set to +2.2 ± 0.25 (from JJA +1.36 and JAS +1.69 in the CPC file and CPC's 8 Oct 2026 outlook). Replace in `config.py` or the spreadsheet's Settings tab when CPC publishes it.

---

## Step 2a — Linear model (`02_fit_models.py`)

**Model**, fit separately for each city × season × variable on the 75 seasonal values:

```
y_t = a + b · x_t + c · (t − t̄) + e_t
```

| Quantity | Meaning |
|---|---|
| c × 10 | **Trend per decade**, holding ENSO fixed |
| b | **ENSO effect**: change per +1 °C of Sep–Nov RONI |
| p (for b) | t-test, n − 3 degrees of freedom → **Confidence** label |
| partial R² = (SSE_trend − SSE_full) / SSE_trend | **Fraction of variability explained by ENSO** after removing the trend |
| residual SD = √(SSE_full / (n − 3)) | **Intrinsic variability**: what is left after trend and ENSO |
| \|b · x_2026\| / residual SD | **Size**: this season's ENSO push relative to normal year-to-year swings |
| BH q-value | **Survives FDR**: Benjamini–Hochberg across all 768 linear ENSO tests (α = 0.05) |

**Assumptions**
6. ENSO's effect is a straight line in x (twice the El Niño, twice the effect).
7. Warming is a straight line over 1951–2025 (no acceleration term).
8. The relationship is stable over 75 years and still holds in 2027.
9. Years are independent (multi-year ENSO events make neighboring years similar, so p-values may be slightly too small).
10. ENSO is the only climate driver in the model; the Indian Ocean Dipole and Atlantic patterns are not included.
11. Rainfall totals are treated like the other variables, although they are skewed.

---

## Step 2b — Quantile regressions (`02_fit_models.py`)

**Model**, fit on daily values (every day of the season, each carrying its season's x and year):

```
Q_τ(y_d) = a_τ + b_τ · x_t(d) + c_τ · (t(d) − t̄),   τ = 0.05, 0.50, 0.95
```

Three separate fits, one per percentile, each minimising the asymmetric "check" loss Σ ρ_τ(y − ŷ), with ρ_τ(u) = u · (τ − 1[u < 0]). Solver: iteratively reweighted least squares, the same as the main notebook.

- **Temperature and humidity:** all days. **Rainfall:** wet days (≥ 1 mm) only, because dry days pile up at zero. The wet-day share is modeled separately in Step 2a.
- **Uncertainty:** year-block bootstrap with 200 draws. Whole years are resampled, so days within a season are never treated as independent. The same draws are used for all three percentiles ("joint" estimation), which gives a valid interval for the 95th − 5th difference (Tails tab). p-values come from the bootstrap standard error (normal approximation). FDR is applied across all 1,728 quantile ENSO tests.
- **Crossing check:** flags any city where the fitted 5th/50th/95th lines change order within the observed range.

**Assumptions**
12. Each percentile moves linearly with x and with time.
13. Daily values within a season share one ENSO value (the season's predictor).
14. 200 bootstrap draws are enough for standard errors (not for very small p-values; the confidence label uses the normal approximation).
15. Non-crossing is checked, not enforced.

---

## Step 3 — Forecast (`03_build_workbook.py`, live formulas)

For Dec 2026–Feb 2027 and Mar–May 2027:

```
expected value = a + c · (2027 − t̄) + b · x_2026
spread (SD)    = √( residual² + Var(a + c·(2027 − t̄)) + x² · Var(b) + 2x · Cov + b² · SD(x)² )
P(below normal) = Φ((tercile_low − expected) / spread)
P(above normal) = 1 − Φ((tercile_high − expected) / spread)
```

Terciles are the 1991–2020 one-third and two-thirds values of the seasonal variable.

**Assumptions**
16. Forecast errors are normally distributed with constant spread (crudest for rainfall). The bell-curve tails overstate certainty far from the center, so probabilities above 95% are written as "very likely (>95%)", never as 99–100% ("Forecast in words" column; translation guide §6).
17. The forecast includes the trend, so warming cities lean "above normal" even in a neutral year.
18. If x_2026 lies outside the fitted range of x, the forecast is an extrapolation (flagged).

---

## Step 4 — Labels (Lookup tab)

19. Confidence thresholds (p): Strong < 0.01, Clear < 0.05, Modest < 0.10, Detectable < 0.20, Weak < 0.50, otherwise No identifiable effect.
20. Size thresholds (effect ÷ intrinsic variability): Negligible < 0.25, Noticeable < 0.5, Substantial < 1, otherwise Dominant.

**Notes from the October 2026 run**

- **"Survives FDR" ≈ "Strong".** With 768 linear tests, the Benjamini–Hochberg correction effectively moves the bar to p ≈ 0.01: all 173 Strong effects survive, 2 of 93 Clear effects do, none weaker. Read "Clear but not surviving FDR" as *probably real*: a few of those 93 could be chance. The translation guide softens their wording by one step.
- **Confidence and Size move together in the linear model.** Every city has the same 75 seasons, so for a given El Niño strength the Size ratio is close to a rescaled t-statistic: ratio ≈ |t| × x ÷ (SD of x × √n). In the run, no Strong/Clear effect was smaller than Substantial and no Weak/None effect larger than Noticeable. Consequence: the "statistically clear but too small to notice" case cannot arise from 75 seasonal values. Size still adds information: it states the effect in human terms and changes with El Niño strength.
- **Size is reported two ways.** "Size" uses this year's Sep–Nov RONI (the forecast question); "Size in a typical strong El Niño" uses RONI +1.5 (the city's general sensitivity). With +2.2, 90 rows are Dominant; with +1.5, 37.
- **"Once every N years."** The same ratio as a return period: without El Niño, a season this far from the trend would happen about once every 1 ÷ (1 − Φ(ratio)) years (one-sided normal tail; blank below a ratio of 0.5; ">100" beyond a century). Example: Freetown Mar–May, ratio 1.39 → about once every 12 years.

---

## What this does NOT do

- It does not measure vulnerability (population, housing, health), only the weather shift (hazard).
- It does not use station data; the earlier station check (Section 36 of the notebook) supports ERA5 for these questions.
- It does not include uncertainty about the timing of El Niño's decay after the peak.

---

## Station check of the trends (October 2026, notebook Section 39)

ERA5's long-term trends were compared with the nearest weather station over the same years for the results that looked unusual.
Humidity was computed the same way for both (from daily-mean temperature and dew point).

| Result | Station check | How the paragraphs treat it |
|---|---|---|
| Delhi humidity rise, Dec–Feb and Mar–May | Confirmed (station +3.4 and +2.6 points/decade) | Quoted, noted as station-confirmed |
| Hangzhou, Shanghai spring humidity decline | Confirmed (stations decline even faster) | Quoted |
| Beijing spring humidity decline | Smaller at the station (about −1 point/decade) | Station value quoted |
| Oslo winter, Beijing spring warming | Confirmed (ERA5 about 1.4× the station rate) | Quoted |
| Ahmedabad humidity rise (both seasons) | Not seen at the station | "No clear trend" |
| Dhaka winter humidity rise | Not seen at the station (record only from 1997) | "Not confirmed" |
| Vancouver winter rainfall decline (−10%/decade) | Station shows about −2%/decade, unclear | "Slight decline, unclear in station records" |
| Freetown, Lagos, Accra dry-season rainfall decline | No usable station record | Direction only, flagged as unconfirmed |
| Santiago autumn cooling | No usable station record | "No clear trend" |

ERA5 does not systematically overstate trends (Delhi, Hangzhou and Shanghai are stronger at the station), so the 1951–2025
period is kept. The ENSO effects themselves were checked earlier (Section 36): stations and ERA5 agree on the direction of
ENSO links in most cases. The decisions are coded in `STATION_CHECK` in `code/06_write_paragraphs.py`.

# Translation guide: from the C40 metrics to plain-language city paragraphs

This guide turns the numbers in `C40_ENSO_metrics.xlsx` into consistent sentences, so that every city paragraph says the same thing in the same way. When Claude (or anyone) writes the paragraphs, it follows these rules exactly and uses only numbers from the workbook.

Audience: city climate officers and C40 staff. Assume no statistics background. Never print p-values, R², "RONI" or "quantile regression" in a paragraph; this guide says what to write instead.

---

## 1. What goes into one city paragraph

Write **one paragraph per city per season** (Dec–Feb and Mar–May), 5–7 sentences, in this order:

1. **Trend** — how the season has been changing since 1951.
2. **ENSO link** — whether El Niño conditions in the preceding Sep–Nov shift the season, how confidently, and how big that shift is next to normal year-to-year swings.
3. **Extremes** — whether the hottest/coldest (or heaviest-rain, most/least humid) days are changing differently from typical days, and whether El Niño moves them differently.
4. **This season** — what this El Niño implies for Dec 2026–Feb 2027 (or Mar–May 2027), as odds.
5. **Caveat** — only when one of the flags in §8 applies.

Cover temperature first, then rainfall, then humidity. If a variable has no trend and no ENSO link, give it half a sentence ("Rainfall shows no clear trend or El Niño link."), never a full sentence of nothing.

---

## 2. Where each number lives

| Need | Tab | Column |
|---|---|---|
| Trend per decade (seasonal mean) | Linear | Trend per decade, Trend p |
| ENSO effect per +1 °C | Linear | ENSO effect per +1 °C RONI |
| Confidence label | Linear | Confidence (+ Survives FDR) |
| Share of variation explained | Linear | Fraction of variability explained by ENSO |
| This season's push, size label | Linear | ENSO effect this season, Effect ÷ intrinsic variability, Size |
| Years-of-warming equivalent | Linear | Equivalent years of warming trend |
| 2027 expectation and odds | Linear | Expected anomaly vs 1991–2020, P(below/near/above), Most likely tercile |
| Extrapolation flag | Linear | RONI within historical range? |
| Hottest / typical / coldest days | Quantiles | Percentile, Trend per decade, ENSO effect, Confidence, Shift this season |
| Do the tails move differently? | Tails | What ENSO does to the tails, What the trend does to the tails (with the 5th and 95th slopes beside them) |
| Wet days vs heavier rain | Linear (Wet-day share rows) and Quantiles (wet-day rainfall rows) | |

---

## 3. Trend sentences

**Temperature.** Report the seasonal-mean trend per decade and the total change since 1951 (trend per decade × 7.5, rounded to 0.1 °C).

| Trend p | Write |
|---|---|
| < 0.05 and trend > 0 | "Dec–Feb in {city} has warmed by about {x} °C per decade since 1951, roughly {total} °C in all." |
| < 0.05 and trend < 0 | "…has cooled by about {x} °C per decade…" (rare; double-check before writing) |
| ≥ 0.05 | "Dec–Feb temperatures show no clear long-term trend." |

**Rainfall.** Express the trend as a percentage of the 1991–2020 normal per decade: trend ÷ normal × 100. Under ±2% per decade, or p ≥ 0.05: "no clear trend". Otherwise: "Dec–Feb rainfall has risen/fallen by about {x}% per decade."

**Humidity.** Report in percentage points of relative humidity per decade. Add this note whenever humidity falls while temperature rises: "warmer air can hold more moisture, so relative humidity can fall even when the air is not drier in absolute terms."

Round temperature changes to 0.1 °C (trends per decade to the nearest 0.05 °C), rainfall to the nearest 5% (or 5 mm when the normal is below 50 mm), humidity to 0.5 points (0.1 for trends under 1 point per decade).

---

## 4. ENSO sentences: confidence × size

Every ENSO statement combines two labels: **confidence** (is there an effect at all?) and **size** (would anyone notice it?). Use both.

### 4a. Confidence (from the p-value; Lookup tab)

| Label | p-value | Phrase |
|---|---|---|
| Strong | < 0.01 | "a strong, well-established El Niño effect" |
| Clear | 0.01–0.05 | "a clear El Niño effect" |
| Modest | 0.05–0.10 | "a modest but consistent El Niño signal" |
| Detectable | 0.10–0.20 | "an El Niño effect that is detectable but uncertain" |
| Weak | 0.20–0.50 | "weak hints of an El Niño effect, not distinguishable from chance" |
| No identifiable effect | ≥ 0.50 | "no identifiable El Niño effect" |

If **Survives FDR = No** and the label is Strong or Clear, downgrade the wording by one step in the paragraph ("clear" → "modest but consistent") and keep the label unchanged in the workbook. Reason: with 768 tests, a few "clear" results are expected by chance.

### 4b. Direction

Translate the sign of the ENSO effect: "El Niño years tend to bring a **warmer/cooler**, **wetter/drier**, **more/less humid** Dec–Feb." The predictor is the preceding Sep–Nov, so write "after an El Niño fall" or "when El Niño is under way in Sep–Nov".

### 4c. Size (Effect ÷ intrinsic variability; Lookup tab)

This is the relative framing: how big this year's El Niño push is compared with the season-to-season swings that happen anyway.

| Label | Ratio | Phrase |
|---|---|---|
| Negligible | < 0.25 | "small next to normal year-to-year swings — unlikely to be noticed" |
| Noticeable | 0.25–0.5 | "a noticeable tilt, though ordinary variability can easily outweigh it" |
| Substantial | 0.5–1 | "a substantial shift that people would likely notice" |
| Dominant | ≥ 1 | "larger than a typical year-to-year swing — likely to dominate the season" |

Always give the ratio as a percentage once: "this year's El Niño push is about {ratio × 100, rounded to 10}% of a normal year-to-year swing."

When the "once every N years" column is filled (ratio ≥ 0.5), add the rarity framing, which is the easiest version to grasp: "Without El Niño, a season this warm would come about once every {N} years; this year it is the expected outcome." For ">100", write "less than once a century".

When "Size in a typical strong El Niño" differs from "Size", say which applies: "This is a strong El Niño; in a more typical one the effect would be {typical size, lower case}."

### 4d. Share of variation explained (optional, one clause)

"Over the record, El Niño accounts for about {fraction × 100, rounded to 5}% of the year-to-year ups and downs." Skip this when the confidence is Weak or No identifiable effect.

### 4e. Years-of-warming equivalent (temperature only, when filled in)

"This year's El Niño adds roughly as much warmth as {n, rounded} years of the long-term warming trend." Use it only when n ≥ 3; below that, skip it.

### Combined templates

- **Strong/Clear + Substantial/Dominant**: "There is a clear El Niño effect: after an El Niño fall, Dec–Feb tends to be warmer, by about {effect per °C} °C for each degree of El Niño. With this year's strong El Niño, that push is about {ratio}% of a normal year-to-year swing — a substantial shift people would likely notice."
- **Strong/Clear + Negligible/Noticeable** (the "statistically clear but small" case, e.g. parts of Indonesia): "El Niño has a clear but small effect: Dec–Feb runs about {x} °C warmer after El Niño falls, which is only about {ratio}% of a normal year-to-year swing, so most residents would not notice it."
- **Modest/Detectable**: "There is a modest but uncertain El Niño signal toward a warmer Dec–Feb; treat it as a tilt, not a forecast."
- **Weak/None**: "El Niño has no identifiable effect on Dec–Feb temperatures in {city}."

---

## 5. Extremes sentences (Quantiles and Tails tabs)

Use the 5th, 50th and 95th percentile rows. Say "the coldest days" (5th), "typical days" (50th) and "the hottest days" (95th). For rainfall: "light rain days", "typical rain days", "heavy-rain days" (wet days only). For humidity: "the driest-air days", "typical days", "the most humid days".

**Trend in the tails.** Use the Tails tab, "What the trend does to the tails". It names the tail that changes most, its direction, and what happens to the spread (only when p < 0.1):
- "The trend changes the hottest days most (upward); spread widens" → "The hottest days have warmed faster than the coldest days ({95th} vs {5th} °C per decade)."
- "The trend changes the coldest days most (upward); spread narrows" → "The coldest days have warmed fastest, so cold extremes are becoming rarer."
- "The trend changes the heavy-rain days most (downward); spread narrows" → "Heavy-rain days have become less intense ({95th} mm/day per decade), while light rain days have hardly changed."
- "Both tails move alike" → "The whole range of days has changed by a similar amount."

**ENSO in the tails.** Use "What ENSO does to the tails", only when at least one percentile's confidence is Clear or Strong:
- "El Niño moves the hottest days most (upward)…" → "El Niño pushes the hottest days up more than the coldest: this season, the hottest days are expected to shift by about {shift 95th} °C."
- "El Niño moves the driest-air days most (upward)…" → "El Niño mainly makes the driest days less dry."
- "Both tails move alike" → "El Niño shifts the whole range of days together."

Always read the direction in brackets: "most (downward)" means that tail falls, not rises.

For rainfall, combine the wet-day share row (Linear) with the heavy-rain row (Quantiles) to say whether El Niño changes **how often** it rains, **how hard** it rains, or both.

---

## 6. This-season sentences (forecast)

Use "Expected anomaly vs 1991–2020" and the three probabilities. Name the season with its months and years ("Dec 2026–Feb 2027").

Use the "Forecast in words" column; it applies this table:

| Highest probability | Phrase |
|---|---|
| > 0.95 | "{category} is very likely (more than 95% chance)." Never write 99% or 100%. |
| ≥ 0.66 | "{category} is likely ({p}% chance)." |
| 0.50–0.66 | "{category} is more likely than not ({p}%)." |
| 0.40–0.50 | "{category} is slightly favored ({p}%)." |
| < 0.40 | "The odds are close to even across below, near and above normal." |

Categories: "a warmer-than-normal season", "a cooler-than-normal season", "a near-normal season"; for rainfall "a wetter/drier-than-normal season"; for humidity "a more/less humid season than normal".

Always say what drives the tilt. If the ENSO confidence is Weak or None but "above normal" is favored, the trend is doing the work: "mostly because of the long-term warming trend rather than El Niño." Probabilities include the trend, so warming cities lean toward "above normal" even without El Niño.

Round probabilities to the nearest 5%. Give the expected anomaly with its unit: "about {x} °C above the 1991–2020 average".

---

## 7. Words to use and avoid

| Use | Avoid |
|---|---|
| "El Niño conditions in Sep–Nov", "after an El Niño fall" | "RONI", "Niño 3.4", "lead index" |
| "clear", "modest", "uncertain" | "significant", "p = 0.03" |
| "about", "roughly" | numbers to more than 2 significant figures |
| "tends to", "is likely to" | "will", "causes" |
| "the hottest days (the warmest 5% of days)" | "95th percentile" without explanation |
| "normal year-to-year swing" | "standard deviation", "residual SD" |

"Fall" means Sep–Nov in the Northern Hemisphere; for Southern Hemisphere cities, write "Sep–Nov" instead.

---

## 8. Caveat flags (add one sentence only when they apply)

| Flag | Condition | Sentence |
|---|---|---|
| Extrapolation | RONI within historical range? = "Beyond record — extrapolated" | "This El Niño is stronger than any in the record used here, so the estimate extends the historical relationship beyond what has been observed." |
| Crossing lines | Quantiles: Fitted lines cross? = Yes | Do not discuss that variable's extremes; say "the extremes do not follow a simple pattern". |
| Chance | Confidence Strong/Clear but Survives FDR = No | Downgrade the wording one step (§4a). |
| Dry season | Rainfall normal < 30 mm | "This is the dry season, so rainfall changes are small in absolute terms." |
| Forecast input | Settings!B5 > 0 (Sep–Nov RONI still estimated) | In any shared version: "Based on the El Niño strength expected for Sep–Nov 2026; to be updated when it is observed in early December." |

---

## 9. Worked example (illustrative numbers, not real results)

*Inputs:* City X, Dec–Feb. Temperature: trend +0.22 °C/decade (p < 0.001); ENSO effect +0.35 °C per °C (p = 0.004, Strong, survives FDR); fraction explained 0.31; this season +0.77 °C; ratio 0.9 (Substantial); years of warming 35; expected anomaly +1.2 °C; P(above) 0.78. Tails: "Hottest days rising faster" (95th +0.30, 50th +0.21). Rainfall: no trend, ENSO Weak. Humidity: no trend, ENSO None. RONI within range: Yes.

*Paragraph:* "Dec–Feb in City X has warmed by about 0.2 °C per decade since 1951, roughly 1.7 °C in all, and the hottest days have warmed faster than typical days (0.3 vs 0.2 °C per decade). There is a strong, well-established El Niño effect: after an El Niño fall, Dec–Feb tends to run warmer, and El Niño accounts for about 30% of the year-to-year ups and downs. With this year's strong El Niño, that push is about 90% of a normal year-to-year swing — a substantial shift people would likely notice, adding roughly as much warmth as 35 years of the long-term trend. For Dec 2026–Feb 2027, a warmer-than-normal season is likely (about an 80% chance), about 1.2 °C above the 1991–2020 average. Rainfall and humidity show no clear trend or El Niño link."

---

## 10. Checklist before a paragraph is final

- [ ] Every number appears in the workbook row for that city and season.
- [ ] Confidence and size are both stated for any ENSO claim.
- [ ] Units and rounding follow §3 and §6.
- [ ] No banned words from §7.
- [ ] Every flag in §8 that applies has its sentence.
- [ ] The season is named with months and years.

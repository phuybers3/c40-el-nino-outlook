# The paragraph generator

31 October 2026. `code/05_write_paragraphs.py` writes the 192 city-season
paragraphs shipped in `site/data/city/*.json`. We first rebuilt it blind, by
reading all 192 paragraphs against `data/processed/city_facts.json` and
diffing the regenerated text against the shipped text until the two agreed;
the same evening the original writer, Klara Kuemmerle's
`06_write_paragraphs.py`, reached us, and the script now follows its general
rules (the section "The original generator" below says what was ported).
Under `--rules legacy` all 192 paragraphs match byte for byte, non-breaking
spaces included. There are no residual mismatches.

## Running it

The acceptance run regenerates the shipped paragraphs and compares them:

    python3 code/05_write_paragraphs.py --facts data/processed/city_facts.json --rules legacy \
        --out docs/city_paragraphs_legacy.md --json-out /tmp/paras.json
    python3 code/05_write_paragraphs.py --facts data/processed/city_facts.json --rules legacy \
        --check site/data/city

`--check` prints the number of exact matches and, for each mismatch, the city,
the season and the first differing sentence with the differing span in
brackets. It exits 1 when anything differs. Non-breaking spaces are treated as
ordinary spaces in the comparison; the shipped text has U+00A0 before every
"°C" (631 places) and before "mm" (11 places), and the generator writes the
same characters.

The new rule set runs the same way with `--rules new`; `code/run.py` runs it
on the new-rules facts and `docs/PARAGRAPH_DIFF.md` lists what changed
against the shipped text. A trial against legacy facts (labels mapped on the
fly, effects unshrunk) is

    python3 code/05_write_paragraphs.py --facts data/processed/city_facts.json --rules new \
        --out docs/city_paragraphs_new_trial.md

The script needs only the standard library (json, re, math, argparse, os,
sys). Besides the facts it reads `data/cities.csv` for latitudes,
because the phrase "after El Niño conditions in the preceding fall" is written
north of the equator and "in the preceding Sep–Nov" south of it; `--cities`
points elsewhere if needed (a site `cities.json` also works). Per-city hand edits are read from
`code/paragraph_overrides.json` (`--overrides`).

`--json-out` writes a JSON object keyed `"<city>|<season>"`, for example
`"Nairobi|DJF"`, whose value is the paragraph string, so
`code/06_export_site.py` can look paragraphs up directly. `--out` writes a
markdown file with one `## City SEASON` heading per paragraph.

## How the code is laid out

Every threshold and every phrase lives in the `RULES` dictionary at the top
of the file, one entry per rule set. `LEGACY` is written out in full and
`_new_rules()` derives the new set from a copy of it, changing only the
entries the revision asks for, so the legacy output cannot drift. A `Cell`
object wraps one city-season record and answers the questions the builders
ask: the stored confidence label after the rule set's mapping, the effective
label (Strong or Clear read one step lower when the effect fails the FDR
correction, under the legacy rules only), the group that label falls in
(established, hint or none), the size tier, the station-check entry for a
variable, whether the fitted quantile lines cross, and the trend part of the
forecast anomaly. The builders follow the original script: `temp_sentences`,
`rain_sentence`, `rh_sentence` and `outlook`, each returning text the
paragraph assembler joins, with the original's rounding helpers (`r05`,
`num`, `pct`, `amount`, Python's half-to-even `round`). Reviewer notes
(station checks, the drizzle bias) collect on the cell and go into the
markdown output as italic lines.

## The recovered rule set

This section records the rules as we recovered them from the shipped text
before the original script arrived. They describe the text correctly, and
the counts still hold, but where the original's rule is wider or narrower
the generator now follows the original; the section "The original
generator" lists those places.

The paragraph is assembled in a fixed order: the temperature trend sentence,
the temperature El Niño sentence, the push sentence, the return period, the
El Niño tail sentence, the rainfall sentences, the humidity sentences, any
"no clear trend or El Niño link" sentence that was deferred, the outlook, and
the fixed closing sentence. Three labels are grouped: Strong, Clear and
Modest form the established group that gets a full effect sentence; Detectable
is the hint group; Weak and "No identifiable effect" are the none group.

Temperature. The trend sentence reads "has warmed by about X °C per decade
since 1951, roughly Y °C in all" when the trend p is below 0.05 and the slope
is positive (182 paragraphs); X is rounded to 0.05 and Y to 0.1, with
trailing zeros dropped ("roughly 2 °C"). Otherwise it reads "temperatures in
City show no clear long-term trend" (10 paragraphs: Ahmedabad, Delhi, Dhaka
and Santiago in both seasons, Buenos Aires MAM, New Orleans DJF; Santiago MAM
cools at p = 0.005 and falls here because of the sign test). When the
95th–5th percentile trend difference has p below 0.10 the sentence continues
", and the hottest days have warmed faster than the coldest (about A vs B °C
per decade)" if the difference is positive (23) or ", with the coldest days
warming fastest, so cold extremes are becoming rarer" if negative (30); the
next p in the data is 0.1026. The El Niño sentence follows the label: Strong
(61) quotes the fraction explained rounded to 5; Clear (16) and Modest (15)
share "a modest but consistent El Niño signal"; Detectable (14) reads
"detectable but uncertain, a slight tilt toward a warmer season"; Weak (32)
and none (54) read "El Niño has no identifiable effect on Season temperature",
which merges into the no-trend sentence as "and no identifiable El Niño link"
(6). The direction "warmer" or "cooler" is the sign of the effect.

For the 92 established cells the push sentence quotes the effect ratio
(effect this season over the year-to-year spread). Below 0.5 it is a percent
rounded to 10 followed by "a noticeable tilt, though ordinary variability can
easily outweigh it" (9); from 0.5 to 0.95 the percent alone (37); from 0.95
the ratio is rounded to 0.5 and written "as large as a normal year-to-year
swing" when that is 1 (13) or "X times a normal year-to-year swing" (33). The
clause "roughly as much warmth as N years of the long-term trend" is added
when the years-of-warming equivalent is positive and at most 60 (74); the
values 62.3, 65.0, 65.9, 70.5, 72.4, 102.6 and 108.9 are omitted, as are the
cooling cases and the cells without a clear trend. The return period "Without
El Niño, a Season this warm would come about once every N years" is written
for Strong labels only, 55 with a number and 6 "less than once a century" for
the stored value ">100"; 5 Strong cells have no stored value and no sentence.
The El Niño tail sentence appears for established labels when the 95th–5th
difference in the El Niño shift has p below 0.10 (33: 29 "hottest days most",
4 "coldest days most", decided by the larger absolute shift; values rounded to
0.1, and -0.02 is written "0").

Rainfall. Below a 1991–2020 normal of 30 mm the sentence opens "Very little
rain falls in Season in City (about N mm in a normal season)" with N rounded
to 5 and "<5" when that rounds to 0 (11 paragraphs; the largest dry normal is
23.5 mm, the smallest non-dry 32.2 mm, so a cut anywhere between gives the
same text). Otherwise the trend is quoted as "has risen/fallen by about N%
per decade" when p is below 0.05 and the percent of normal per decade rounds
to at least 5 (43); three cells with p below 0.05 but a percent under 2.5
(Jakarta DJF, Medellín MAM, Quito DJF) read "no clear long-term trend". What
follows depends on the group. Established (81): "El Niño has {adjective}
toward a wetter/drier season{ with more rainy days}{ and more intense
heavy-rain days}, and this year's shift is {size}", joined to a no-trend
opening with ", but" or written as its own sentence after a trend or dry
opening. The adjective is "a strong, well-established effect" for Strong, "a
modest but consistent effect" for Clear and Modest, and "a clear effect" for
the one Clear label that survives the FDR correction (San Francisco DJF). The
rainy-days clause follows the wet-day-share label being established (61) and
the heavy-rain clause follows the 95th-percentile label being Strong or Clear
(15), each with its own sign. The size phrase is the size tier of the effect
ratio: "a noticeable tilt" below 0.5, "substantial" below 1, "larger than a
normal year-to-year swing" from 1. Hint (28): "shows no clear long-term
trend, and only an uncertain hint of an El Niño effect" or, after an opening
clause, "El Niño's effect is uncertain, with a slight tilt toward a wetter
season." None (83): ", with no clear El Niño link" after an opening clause
(29), or a deferred sentence when there is none.

Humidity. The trend sentence is written when p is below 0.05 (121: 100
falling, 21 rising). The slope is rounded to 0.1 below 1 point per decade and
to 0.5 above, with "point" singular when it rounds to 1 (10); the total is
rounded to a whole number and always takes "points" (Lagos MAM reads "roughly
1 points", which we reproduce). Falling humidity closes with "; because
warmer air holds more moisture, this does not necessarily mean the air is
drier." and any El Niño sentence stands alone; rising humidity joins its El
Niño clause with ", and". Without a clear trend the established group (82)
reads "Humidity shows no clear long-term trend, but El Niño has {adjective}
toward a more/less humid Season, and this year's shift is {size}", the hint
group (19) "and only an uncertain hint of an El Niño effect", and the none
group (91) is deferred. The deferred sentences are "Rainfall and humidity show
no clear trend or El Niño link." (18), "Rainfall shows no clear trend or El
Niño link." (36, written after the humidity sentences) and "Humidity shows no
clear trend or El Niño link." (15).

Outlook. The wording is chosen on the largest of the three tercile chances:
above 0.95 "very likely (more than 95% chance)" (33), from 0.66 "likely (about
N% chance)" (73), from 0.5 "more likely than not (about N%)" (56), from 0.4
"slightly favored (about N%)" (23, six of them "near-normal temperatures are
slightly favored"), and below 0.4 "the temperature odds are close to even"
(7). The percent is rounded to 5 while the band is chosen on the unrounded
value, which is why "more likely than not (about 50%)" and "slightly favored
(about 50%)" both occur. The two band edges we had to locate are 0.66 (0.6598
is "more likely than not", 0.6612 "likely") and 0.95 (no value falls between
0.95 and 0.96; 0.937 reads "likely (about 95% chance)"). The temperature
anomaly ", about X °C above/below the 1991–2020 average" is quoted, rounded
to 0.1, when it rounds away from zero and its sign agrees with the favored
side (178; Melbourne DJF, +0.02 °C with cooler favored, has none). Rainfall
and humidity clauses are written only for a directional favorite, from a
chance of 0.55 for established labels and from 0.66 for the others (65
rainfall, 61 humidity clauses; 0.5469 is omitted and 0.555 written for the
first, 0.6588 omitted and 0.6644 written for the second). The attribution
clause ", mostly because of the long-term warming trend rather than El Niño"
is added to the temperature statement when the label is outside the
established group, a warmer season is favored and the slope is positive (88;
Ahmedabad MAM with trend p = 0.96 has it, Dhaka DJF with a negative slope does
not). For rainfall and humidity ", mostly because of the long-term trend
rather than El Niño" needs a label outside the established group and trend p
below 0.05 (15; Mumbai DJF rain at p = 0.95 has none). Three rainfall clauses
", partly because of an uncertain long-term drying trend" belong to the
dry-season overrides below.

| Rule | Threshold | Paragraphs governed |
|---|---|---|
| Temperature trend clear | trend p < 0.05 and slope > 0 | 182 warmed, 10 no clear trend |
| Hot/cold trend clause | tail trend p < 0.10 | 23 hottest, 30 coldest |
| Temperature El Niño wording | label | 61 / 16 / 15 / 14 / 32 / 54 |
| Push sentence | established label | 92 (9 tilt, 37 percent, 13 as large, 33 times) |
| Years-of-trend clause | 0 < years ≤ 60 | 74 |
| Return period | Strong label, value stored | 55 + 6 "less than once a century" |
| El Niño tail sentence | established, tail El Niño p < 0.10 | 33 |
| Hemisphere phrase | latitude ≥ 0 "fall" | 60 "fall", 32 "Sep–Nov" among established |
| Dry season | normal < 30 mm | 11 |
| Rainfall trend | p < 0.05 and percent of normal per decade ≥ 2.5 | 43 |
| Rainy-days clause | wet-day label established, normal < 90% | 61 |
| Heavy-rain clause | p95 label Strong or Clear | 15 |
| Size phrase | effect ratio 0.5, 1 | 21 tilt, 108 substantial, 34 larger |
| Humidity trend | p < 0.05 | 100 fallen, 21 risen |
| Outlook bands | 0.95, 0.66, 0.5, 0.4 | 33 / 73 / 56 / 23 / 7 even |
| Rain and humidity outlook | 0.55 established, 0.66 others | 65 rain, 61 humidity |
| Temperature attribution | non-established, warmer, slope > 0 | 88 |
| Rain/humidity attribution | non-established, trend p < 0.05 | 15 (+3 from overrides) |

## Station checks

`code/paragraph_overrides.json` holds the original's `STATION_CHECK` and
`CONFIRMED` tables, the decisions of the October 2026 station check
(`archive/klara_c40_metrics_2026-10-31/docs/methods_and_assumptions.md`,
last section). Each entry is keyed `City|SEASON|variable` and has a kind:
`none` (no trend is quoted: Ahmedabad humidity in both seasons, Santiago
Mar–May temperature), `uncertain` (Dhaka Dec–Feb humidity: "may have risen,
but station records do not confirm it"), `value` (Beijing Mar–May humidity:
the station's 1 point per decade is quoted instead of ERA5's 1.5),
`slight_decline` (Vancouver Dec–Feb rainfall) and `unverified` (Accra,
Freetown and Lagos Dec–Feb rainfall, quoted with "a trend that station
records cannot yet confirm"; their wet-day entries are recorded but no
sentence reads them). A humidity entry of kind `none` or `uncertain` also
drops the humidity outlook clause, and a rainfall entry of kind `unverified`
or `slight_decline` adds "partly because of an uncertain long-term drying
trend" when a drier season is favored. `confirmed` lists the four humidity
trends (Delhi both seasons, Hangzhou and Shanghai Mar–May) that get "(a
change weather-station records confirm)". The `shared` block applies to both
rule sets; the `new` block adds Dhaka Mar–May humidity (kind `uncertain`, as
in Dec–Feb) and gives Santiago Mar–May temperature a sentence of its own,
"Mar–May temperatures in Santiago have cooled by about 0.1 °C per decade in
ERA5, a trend that no usable station record can confirm." Every entry
carries the reviewer note the markdown output prints under the paragraph.

The rule we had recovered from a single case, dropping the rainy-days clause
where more than 90% of days are already wet (Medellín Mar–May, 95.1%), is a
general rule in the original, `wet_day_max_normal`, with a reviewer note
behind it.

## The new rule set

`--rules new` changes the following, each a `RULES` entry so the legacy text
is untouched. The effective-label drop is off, because Strong already means
"survives FDR" and Clear is defined as p < 0.05 without it; the fraction
clause and the return period follow Strong alone for the same reason. A
humidity total of one point reads "1 point" (the shipped text has "1
points" for Lagos Mar–May, which the legacy rules keep). While the RONI is an
estimate whose upper end lies beyond the fitted record, the closing sentence
reads "This outlook is based on the El Niño strength expected for Sep–Nov
2026, whose upper range exceeds any in the record used here, and will be
updated when it is observed in early December."; once the center itself
exceeds the record (CPC's central estimate of +2.53 does, against +2.22 in
1997) the beyond-record sentence is written once before the plain closing
sentence, as "The El Niño expected for Sep–Nov 2026 is stronger than any in
the record used here, so the outlook extends the historical relationship
beyond what has been observed." while the value is an estimate and in the
original's wording ("This El Niño is stronger than any ...") once it is
observed; the legacy rules always use the original's wording. Once the value
is observed and within the record neither sentence appears. We tested the
beyond-record case on facts built with `--roni 2.53 --roni-sd 0.25` under
both rule sets: one such sentence and one closing sentence in each of the
192 paragraphs. The labels are Strong (survives the FDR correction), Clear
(p < 0.05), Suggestive (p < 0.10) and "No identifiable effect"; Suggestive
joins the established group and the hint group is empty. Strong keeps
"strong, well-established"; Clear reads "There is a clear El Niño signal on
temperature" and "El Niño has a clear effect toward ..."; Suggestive reads
"There is a suggestive but uncertain El Niño signal on temperature" and "El
Niño may have an effect toward ..., though the evidence is thin, and this
year's shift is ..."; "consistent" no longer appears. The attribution clause
compares the trend part of the forecast anomaly (`trend_part_2027` when the
facts carry it, else `expected_anomaly_2027 − effect_this_season`) with the El
Niño part: when the trend part is larger and pushes toward the favored side
we write "mostly because of the long-term warming trend rather than El Niño"
(temperature) or "mostly because of the long-term trend rather than El Niño"
(rainfall, humidity); when the El Niño part is larger and the label is below
Clear we write "mostly because of an uncertain El Niño term"; when both parts
are below a quarter of the year-to-year spread we write nothing. Rainfall
normals under 25 mm (or the `dry_season` flag when the facts carry it) get
only "Very little rain falls in Season in City (about N mm in a normal
season)." with no effect sentence, no rainy-day clause and no rainfall
outlook. Chances from 0.45 to 0.55 read "has about even odds (about N%)"; the
other bands stand. Two hand corrections sit in the `new` block of the
overrides file: Santiago MAM's temperature sentence becomes "Mar–May
temperatures in Santiago have cooled by about 0.1 °C per decade in ERA5, a
trend that no usable station record can confirm." followed by the El Niño
sentence on its own, and Dhaka MAM's humidity sentence becomes the DJF
wording "Relative humidity may have risen, but station records do not confirm
it." with the humidity outlook dropped as in DJF. The facts fields
`effect_this_season_raw` and `shrink_factor` are not used by the text.

The trial in `docs/city_paragraphs_new_trial.md` runs the new rules on the
current legacy facts. The labels are mapped for the run (Modest to
Suggestive, Detectable and Weak to "No identifiable effect", Clear to Strong
where `survives_fdr` is true) through `label_map` and `fdr_means_strong`;
when the facts builder writes the new labels the map is a no-op. 145 of the
192 paragraphs change. The trial text contains 27 "about even odds", 17
"mostly because of an uncertain El Niño term", 35 "though the evidence is
thin", 46 "a clear effect" and no "modest but consistent", "uncertain hint" or
"detectable but uncertain". Because the trial facts carry the unshrunk El
Niño effect, a few paragraphs say "Rainfall shows no clear trend or El Niño
link" and then attribute a likely wetter season to "an uncertain El Niño
term" (Fuzhou MAM, for example); the shrinkage in the new facts is what
removes that tension, and the generator does not try to.

## The original generator

Added the evening of 31 October 2026. Klara Kuemmerle's own writer,
`code/06_write_paragraphs.py` in her `c40_metrics` project, reached us after
this reconstruction was finished; it is kept in
`archive/klara_c40_metrics_2026-10-31/code/` with its rule document
`docs/translation_guide.md`. On the current facts the two scripts write the
same 192 paragraphs. Read rule by rule they differ in about twenty places,
all of them bars that no current cell sits on: her effective confidence label
(Strong or Clear dropped one step when the effect fails FDR), the 10% floor
on the fraction clause, the rounded-slope guard and "cooled" wording on the
trend sentence, crossing and own-tail-confidence checks on the extremes
sentences, same-sign checks on the rainy-days and heavy-rain clauses, the
humidity trend floor and the warm-air condition, the extrapolation sentence,
the conditional closing sentence, and half-to-even rounding. The single-case
rule noted above (the 90% wet-day cutoff) is a general rule in her code.
`COMPARISON_KLARA_2026-10-31.md` in the project root lists every difference
and her script's own faults.

Later that evening we ported her general rules into this script, keeping our
command line, the two rule sets and the new set's features. Ported: the
effective confidence label and its use by every clause; the fraction clause
for effective Strong and Clear from 10%; the return period on the effective
label; the trend sentence's rounded-slope guard, its "cooled" wording and
its total of |slope| × 7.5; the no-crossing and p05-present guards on the
tail-trend clause; the no-crossing and own-tail-confidence guards on the
extremes sentence; her `ratio_text`, size phrases and the 3-to-60-year window
with a warming effect on the push sentence; "risen/fallen slightly" for
rainfall trends between 2 and 2.5% of normal; the same-sign tests on the
rainy-days and heavy-rain clauses and the non-crossing test on the latter;
the 0.1-point floor and the warming condition on the humidity sentence and
its ", and" join; "very likely" strictly above 95%; the anomaly from 0.05 °C;
the station-check table with its outlook clauses; trend attribution only
when the trend points to the favored side; the extrapolation sentence; the
closing sentence only while the RONI is estimated; and her rounding. Not
ported, on purpose: the dead `if True` branch, the precedence slip that
would drop every outlook clause, "1 points" outside the legacy rules, the
half-to-even rounding of swing ratios (1.25 prints "1.5 times", not "1
times"), a tail-difference p of exactly zero read as missing, and the
anomaly printed against the favored side. Kept as hers, as a limitation: the
tail-trend clause is written only for warming trends. Two joins of ours go
beyond hers: a humidity station note that holds ", but", or an El Niño
clause that holds ", though", closes its sentence before the other clause
instead of joining with ", and", and after "though the evidence is thin" the
small-size clause joins with "and". The legacy output is unchanged at 192 of
192; the new-rules output changes in five paragraphs besides the closing
sentence (Lagos Mar–May's "1 point", Austin Dec–Feb's and Guangzhou and
Fortaleza Mar–May's small-size phrases, Miami Dec–Feb's split humidity
sentence).

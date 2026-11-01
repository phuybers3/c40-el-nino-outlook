"""Compare a rebuilt quantile table with the archived one.

    python code/validate_quantiles.py ORIGINAL REBUILT

Point estimates (intercept, El Niño effect, trend) should agree to a few parts
in a thousand of the cell's bootstrap standard error; bootstrap standard
errors agree only within Monte Carlo noise, so the script reports the
distribution of their ratios rather than a pass/fail. Counts (rows, days,
years, FDR survivors) must match exactly.
"""
import sys
import numpy as np, pandas as pd

KEY = ["city", "season", "variable", "quantile"]


def main(orig: str, rebuilt: str) -> int:
    a, b = pd.read_csv(orig), pd.read_csv(rebuilt)
    a["quantile"] = a["quantile"].astype(str); b["quantile"] = b["quantile"].astype(str)
    ok = True
    print(f"rows {len(a)} vs {len(b)}")
    qa, qb = a[a["quantile"] != "95th-5th"], b[b["quantile"] != "95th-5th"]
    m = qa.merge(qb, on=KEY, suffixes=("_a", "_b"))
    print(f"quantile rows matched {len(m)} of {len(qa)}")
    ok &= len(m) == len(qa) == len(qb)
    for c in ["n_days", "n_years"]:
        n = int((m[c + "_a"] != m[c + "_b"]).sum()); print(f"{c:22s} rows differing {n}"); ok &= n == 0
    for c, se in [("enso_effect", "enso_se"), ("trend_per_decade", "trend_se_per_decade"), ("intercept", None)]:
        d = (m[c + "_a"] - m[c + "_b"]).abs()
        scale = m[se + "_a"] if se else m["intercept_a"].abs().clip(lower=1e-6)
        z = (d / scale)
        print(f"{c:22s} |diff| / {'SE' if se else '|value|'}: median {z.median():.4f}  95th {z.quantile(0.95):.4f}  max {z.max():.4f}")
        ok &= bool(z.quantile(0.95) < 0.05)
    for c in ["enso_se", "trend_se_per_decade"]:
        r = m[c + "_b"] / m[c + "_a"]
        print(f"{c:22s} rebuilt/original SE ratio: 5th {r.quantile(0.05):.2f} median {r.median():.2f} 95th {r.quantile(0.95):.2f}")
    sa, sb = int(a["enso_survives_fdr"].sum()), int(b["enso_survives_fdr"].sum())
    print(f"FDR survivors {sa} vs {sb}; label flips {int((m['enso_survives_fdr_a'] != m['enso_survives_fdr_b']).sum())}")
    for col in ["enso_difference", "trend_difference"]:
        da = a[a[col].notna()][["city", "season", "variable", col, col + "_p"]]
        db = b[b[col].notna()][["city", "season", "variable", col, col + "_p"]]
        mm = da.merge(db, on=["city", "season", "variable"], suffixes=("_a", "_b"))
        flips = int(((mm[col + "_p_a"] < 0.1) != (mm[col + "_p_b"] < 0.1)).sum())
        print(f"{col:22s} rows {len(mm)}; max |diff| {(mm[col + '_a'] - mm[col + '_b']).abs().max():.4f}; p<0.1 flips {flips} of {len(mm)}")
    cap_a = a.loc[a["quantile"] == "0.5", "fits_hit_iteration_cap"].sum() / a.loc[a["quantile"] == "0.5", "fits"].sum()
    cap_b = b.loc[b["quantile"] == "0.5", "fits_hit_iteration_cap"].sum() / b.loc[b["quantile"] == "0.5", "fits"].sum()
    print(f"share of fits at the iteration cap: original {cap_a:.3f}, rebuilt {cap_b:.3f}")
    print("OK" if ok else "DIFFERS beyond tolerance")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))

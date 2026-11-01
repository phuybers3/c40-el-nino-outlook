"""Compare a rebuilt table with the archived original, column by column.

    python code/validate.py ORIGINAL REBUILT --key city season variable [--rtol 1e-9]

Numeric columns report the largest relative difference; text and boolean
columns report the number of rows that differ. Exit status 1 when any column
exceeds the tolerance, so run.py can stop on a regression.
"""
import argparse, sys
import numpy as np, pandas as pd


def compare(a: pd.DataFrame, b: pd.DataFrame, key: list[str], rtol: float, atol: float) -> bool:
    ok = True
    if list(a.columns) != list(b.columns):
        print("column order differs:", [c for c in a.columns if c not in b.columns], [c for c in b.columns if c not in a.columns]); ok = False
    m = a.merge(b, on=key, suffixes=("_a", "_b"), how="outer", indicator=True)
    if (m["_merge"] != "both").any():
        print("unmatched rows:", int((m["_merge"] != "both").sum())); ok = False
    for c in a.columns:
        if c in key or c not in b.columns: continue
        x, y = m[c + "_a"], m[c + "_b"]
        if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y) and not pd.api.types.is_bool_dtype(x):
            both_nan = x.isna() & y.isna(); diff = np.abs(x - y); scale = np.maximum(np.abs(x), atol / rtol if rtol else 1)
            worst = float((diff / scale).fillna(0).max()); nanmis = int((x.isna() != y.isna()).sum())
            flag = "" if worst <= rtol and nanmis == 0 else "  <-- DIFFERS"
            print(f"{c:28s} max rel diff {worst:.2e}  nan mismatches {nanmis}{flag}")
            ok = ok and not flag
        else:
            n = int((x.astype(str) != y.astype(str)).sum()); flag = "" if n == 0 else "  <-- DIFFERS"
            print(f"{c:28s} rows differing {n}{flag}"); ok = ok and n == 0
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("original"); ap.add_argument("rebuilt")
    ap.add_argument("--key", nargs="+", required=True)
    ap.add_argument("--rtol", type=float, default=1e-9); ap.add_argument("--atol", type=float, default=1e-9)
    a = ap.parse_args()
    read = lambda p: pd.read_parquet(p) if p.endswith(".parquet") else pd.read_csv(p)
    sys.exit(0 if compare(read(a.original), read(a.rebuilt), a.key, a.rtol, a.atol) else 1)

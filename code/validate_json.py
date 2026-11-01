"""Compare two JSON trees (facts files or site data files) with a numeric tolerance.

    python code/validate_json.py ORIGINAL REBUILT [--rtol 1e-9] [--ignore-extra] [--show 20]

Every key in the original must exist in the rebuilt file with the same type
of value: numbers within the relative tolerance, strings, booleans and nulls
equal, lists of the same length compared element by element. Keys present only
in the rebuilt file are listed as extras (allowed with --ignore-extra). The
facts list is aligned on (city, season) so row order does not matter.
"""
import argparse, json, math, sys
from collections import Counter


def walk(a, b, path, rtol, atol, errs, extras):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in a:
            if k not in b: errs[path + "." + k + " [missing]"] += 1; continue
            walk(a[k], b[k], path + "." + k, rtol, atol, errs, extras)
        for k in b:
            if k not in a: extras[path + "." + k] += 1
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b): errs[path + " [length]"] += 1; return
        for i, (x, y) in enumerate(zip(a, b)): walk(x, y, path + "[]", rtol, atol, errs, extras)
    elif isinstance(a, bool) or isinstance(b, bool) or a is None or b is None or isinstance(a, str) or isinstance(b, str):
        if a != b: errs[path] += 1
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if math.isnan(a) and math.isnan(b): return
        if abs(a - b) > atol + rtol * abs(a): errs[path] += 1
    else:
        errs[path + " [type]"] += 1


def align(a, b):
    if isinstance(a, list) and a and isinstance(a[0], dict) and "city" in a[0] and "season" in a[0]:
        key = lambda r: (r["city"], r["season"])
        bb = {key(r): r for r in b}
        return a, [bb.get(key(r), {}) for r in a]
    return a, b


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("original"); ap.add_argument("rebuilt")
    ap.add_argument("--rtol", type=float, default=1e-9); ap.add_argument("--atol", type=float, default=1e-9)
    ap.add_argument("--ignore-extra", action="store_true"); ap.add_argument("--show", type=int, default=20)
    args = ap.parse_args()
    a = json.load(open(args.original)); b = json.load(open(args.rebuilt))
    a, b = align(a, b)
    errs, extras = Counter(), Counter()
    walk(a, b, "", args.rtol, args.atol, errs, extras)
    for k, n in errs.most_common(args.show): print(f"DIFF {n:5d}  {k}")
    if extras: print("extra keys in rebuilt:", dict(extras.most_common(args.show)))
    print(f"{sum(errs.values())} differing values in {len(errs)} paths; {sum(extras.values())} extra values")
    sys.exit(1 if errs or (extras and not args.ignore_extra) else 0)

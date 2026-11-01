"""Write a reviewable diff between two sets of city paragraphs.

    python code/diff_paragraphs.py OLD.json NEW.json --out docs/PARAGRAPH_DIFF.md [--facts-old F1 --facts-new F2]

Each JSON maps "City|SEASON" to a paragraph. The output lists, per city and
season, the sentences removed and added, so the text changes brought by a new
rule set or a new RONI estimate can be read in one pass. With the two facts
files it opens with a summary of label changes.
"""
import argparse, json, re, difflib
from collections import Counter

VARS = ["temperature", "precipitation", "wet_day_share", "rel_humidity"]


def sentences(p):
    return [s.strip() for s in re.split(r"(?<=\.)\s+", p.replace("\xa0", " ")) if s.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old"); ap.add_argument("new"); ap.add_argument("--out", required=True)
    ap.add_argument("--facts-old"); ap.add_argument("--facts-new")
    a = ap.parse_args()
    old = json.load(open(a.old)); new = json.load(open(a.new))
    lines = ["# Paragraph changes\n"]
    if a.facts_old and a.facts_new:
        fo = {(r["city"], r["season"]): r for r in json.load(open(a.facts_old))}
        fn = {(r["city"], r["season"]): r for r in json.load(open(a.facts_new))}
        lines.append("## Label changes\n")
        for v in VARS:
            moves = Counter((fo[k]["variables"][v]["confidence"], fn[k]["variables"][v]["confidence"]) for k in fo if k in fn)
            lines.append(f"**{v}**, confidence old → new: " + "; ".join(f"{o} → {n}: {c}" for (o, n), c in sorted(moves.items(), key=lambda t: -t[1])) + "\n")
            sizes = Counter((fo[k]["variables"][v]["size"], fn[k]["variables"][v]["size"]) for k in fo if k in fn)
            changed = {kv: c for kv, c in sizes.items() if kv[0] != kv[1]}
            if changed:
                lines.append(f"**{v}**, size changed: " + "; ".join(f"{o} → {n}: {c}" for (o, n), c in sorted(changed.items(), key=lambda t: -t[1])) + "\n")
            words = sum(fo[k]["variables"][v]["forecast_words"] != fn[k]["variables"][v]["forecast_words"] for k in fo if k in fn)
            lines.append(f"**{v}**, outlook wording changed in {words} of {len(fo)} cells\n")
    n_same = n_diff = 0
    lines.append("## Text changes, by city\n")
    for key in sorted(old):
        o, n = sentences(old[key]), sentences(new.get(key, ""))
        if o == n:
            n_same += 1; continue
        n_diff += 1
        city, season = key.split("|")
        lines.append(f"### {city} {season}\n")
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, o, n).get_opcodes():
            if tag == "equal": continue
            for s in o[i1:i2]: lines.append(f"- removed: {s}")
            for s in n[j1:j2]: lines.append(f"- added: {s}")
        lines.append("")
    lines.insert(1, f"{n_diff} of {n_same + n_diff} paragraphs changed; unchanged ones are not listed.\n")
    open(a.out, "w").write("\n".join(lines))
    print(f"{n_diff} changed, {n_same} unchanged -> {a.out}")


if __name__ == "__main__":
    main()

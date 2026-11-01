"""Evaluate the workbook's formulas in Python and compare every derived cell with city_facts.json.

    python code/validate_workbook.py [--workbook PATH] [--facts PATH] [--meta PATH]

openpyxl writes formulas as text and nothing calculates them on disk, so the
workbook cannot be checked by reading cached values. This script parses each
formula with openpyxl's tokenizer, evaluates it with Excel's semantics for the
functions the builder uses (IF, AND, OR, NOT, IFERROR, INDEX, MATCH, ABS, SQRT,
MAX, MIN, ROUND, NORMDIST, NORMSDIST, SUM, AVERAGE), follows references across
tabs, and compares the Linear, Quantiles, Tails and Summary tabs with
data/processed/city_facts.json cell by cell. It also checks the row counts and
that the Settings tab carries the RONI of facts_meta.json. Exits 1 on any
mismatch.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.formula.tokenizer import Token, Tokenizer
from openpyxl.utils.cell import range_boundaries
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
REL_TOL, ABS_TOL = 1e-9, 1e-9
EXPECTED_ROWS = {"Linear": 768, "Quantiles": 1701, "Tails": 567, "Summary": 192}

# Linear tab: facts key -> column header (the builder's header text).
LINEAR_FIELDS = {
    "normal_1991_2020": "Normal 1991–2020", "trend_per_decade": "Trend per decade", "trend_p": "Trend p",
    "trend_total_since_1951": "Trend since the first year (per decade × years ÷ 10)",
    "enso_effect_per_degC": "El Niño effect per +1 °C RONI (fitted)", "enso_p": "El Niño p",
    "confidence": "Confidence", "survives_fdr": "Survives FDR",
    "fraction_explained": "Fraction of variability explained by El Niño", "intrinsic_sd": "Intrinsic variability (residual SD)",
    "shrink_factor": "Shrinkage factor τ²/(τ²+se²)", "enso_effect_shrunk_per_degC": "Shrunk El Niño effect per +1 °C RONI",
    "effect_this_season": "El Niño effect this season (shrunk × RONI)", "effect_this_season_raw": "El Niño effect this season, unshrunk",
    "effect_ratio": "Effect ÷ intrinsic variability", "size": "Size", "size_typical_el_nino": "Size in a typical El Niño",
    "once_every_n_years_without_el_nino": "Without El Niño, a season this far from the trend: about once every N years",
    "years_of_warming_equivalent": "Equivalent years of warming trend", "trend_part_2027": "Trend part of the 2027 anomaly",
    "forecast_mean": "Expected 2027 value", "expected_anomaly_2027": "Expected anomaly vs 1991–2020", "forecast_sd": "Forecast spread (SD)",
    "p_below": "P(below normal)", "p_near": "P(near normal)", "p_above": "P(above normal)", "forecast_words": "Forecast in words",
    "within_record": "RONI within the fitted range?", "roni_upper_within_record": "RONI + 1 SD within the fitted range?",
    "dry_season": "Dry season (rain only)", "trend_pct_of_normal_per_decade": "Trend as % of normal per decade (rain only)",
}
# Keys that exist only for some variables; elsewhere the cell must be empty.
OPTIONAL = {"years_of_warming_equivalent": ["temperature"], "dry_season": ["precipitation"],
            "trend_pct_of_normal_per_decade": ["precipitation"]}
QUANTILE_FIELDS = {"trend_per_decade": "Trend per decade", "trend_p": "Trend p", "enso_effect_per_degC": "El Niño effect per +1 °C RONI",
                   "enso_p": "El Niño p", "confidence": "Confidence", "shift_this_season": "Shift this season (effect × RONI)",
                   "lines_cross": "Fitted lines cross?"}
TAIL_FIELDS = {"enso_difference": "El Niño: 95th − 5th", "enso_difference_p": ("p", 1), "trend_difference": "Trend: 95th − 5th",
               "trend_difference_p": ("p", 2)}
SUMMARY_PULLS = {"Trend/decade": "trend_per_decade", "Confidence": "confidence", "Effect this season": "effect_this_season",
                 "Size": "size", "Expected anomaly 2027": "expected_anomaly_2027", "P(below)": "p_below", "P(above)": "p_above",
                 "Outlook": "forecast_words", "Dry season": "dry_season"}
SUMMARY_VARS = {"Temp": "temperature", "Rain": "precipitation", "Rainy days": "wet_day_share", "RH": "rel_humidity"}
PCT_KEYS = {"5th": "p05", "50th": "p50", "95th": "p95"}


class XLError(Exception):
    """An Excel error value such as #N/A or #VALUE!."""


# ----------------------------------------------------------------------------- parser
class Parser:
    """Recursive descent over openpyxl tokens, Excel precedence: comparison < & < +- < */ < ^ < unary."""

    def __init__(self, tokens):
        self.t = tokens
        self.i = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def take(self):
        tok = self.t[self.i]
        self.i += 1
        return tok

    def parse(self):
        node = self.comparison()
        if self.peek() is not None:
            raise ValueError(f"unexpected token {self.peek().value!r}")
        return node

    def comparison(self):
        node = self.concat()
        while self.peek() and self.peek().type == Token.OP_IN and self.peek().value in ("=", "<>", "<", ">", "<=", ">="):
            op = self.take().value
            node = ("bin", op, node, self.concat())
        return node

    def concat(self):
        node = self.additive()
        while self.peek() and self.peek().type == Token.OP_IN and self.peek().value == "&":
            self.take()
            node = ("bin", "&", node, self.additive())
        return node

    def additive(self):
        node = self.multiplicative()
        while self.peek() and self.peek().type == Token.OP_IN and self.peek().value in ("+", "-"):
            op = self.take().value
            node = ("bin", op, node, self.multiplicative())
        return node

    def multiplicative(self):
        node = self.power()
        while self.peek() and self.peek().type == Token.OP_IN and self.peek().value in ("*", "/"):
            op = self.take().value
            node = ("bin", op, node, self.power())
        return node

    def power(self):
        node = self.unary()
        while self.peek() and self.peek().type == Token.OP_IN and self.peek().value == "^":
            self.take()
            node = ("bin", "^", node, self.unary())
        return node

    def unary(self):
        tok = self.peek()
        if tok and tok.type == Token.OP_PRE:
            self.take()
            inner = self.unary()
            return ("neg", inner) if tok.value == "-" else inner
        return self.primary()

    def primary(self):
        tok = self.take()
        if tok.type == Token.OPERAND:
            if tok.subtype == Token.NUMBER:
                return ("num", float(tok.value))
            if tok.subtype == Token.TEXT:
                return ("str", tok.value[1:-1].replace('""', '"'))
            if tok.subtype == Token.LOGICAL:
                return ("bool", tok.value.upper() == "TRUE")
            if tok.subtype == Token.RANGE:
                return ("ref", tok.value)
            raise XLError(tok.value)
        if tok.type == Token.FUNC and tok.subtype == Token.OPEN:
            name = tok.value[:-1].upper()
            args = []
            if self.peek().type == Token.FUNC and self.peek().subtype == Token.CLOSE:
                self.take()
                return ("call", name, args)
            while True:
                args.append(self.comparison())
                nxt = self.take()
                if nxt.type == Token.SEP:
                    continue
                if nxt.type == Token.FUNC and nxt.subtype == Token.CLOSE:
                    return ("call", name, args)
                raise ValueError(f"bad token in call {name}: {nxt.value!r}")
        if tok.type == Token.PAREN and tok.subtype == Token.OPEN:
            node = self.comparison()
            close = self.take()
            if not (close.type == Token.PAREN and close.subtype == Token.CLOSE):
                raise ValueError("expected )")
            return node
        raise ValueError(f"unexpected token {tok.value!r} ({tok.type}/{tok.subtype})")


# ----------------------------------------------------------------------------- evaluator
def to_number(v):
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            raise XLError("#VALUE!")
    raise XLError("#VALUE!")


def to_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        if float(v).is_integer():
            return str(int(v))
        return f"{v:.10g}"
    return str(v)


def to_bool(v) -> bool:
    if isinstance(v, str):
        if v.upper() == "TRUE":
            return True
        if v.upper() == "FALSE":
            return False
        raise XLError("#VALUE!")
    return bool(to_number(v))


def compare(op: str, a, b) -> bool:
    """Excel ordering: numbers < text < logicals; an empty cell equals "" and 0; text ignores case."""
    if a is None:
        a = "" if isinstance(b, str) else (False if isinstance(b, bool) else 0.0)
    if b is None:
        b = "" if isinstance(a, str) else (False if isinstance(a, bool) else 0.0)
    rank = lambda v: 2 if isinstance(v, bool) else (1 if isinstance(v, str) else 0)
    if rank(a) != rank(b):
        c = (rank(a) > rank(b)) - (rank(a) < rank(b))
    elif isinstance(a, str):
        c = (a.lower() > b.lower()) - (a.lower() < b.lower())
    else:
        c = (float(a) > float(b)) - (float(a) < float(b))
    return {"=": c == 0, "<>": c != 0, "<": c < 0, ">": c > 0, "<=": c <= 0, ">=": c >= 0}[op]


def excel_round(x: float, n: int) -> float:
    scale = 10 ** n
    return math.copysign(math.floor(abs(x) * scale + 0.5) / scale, x)


class Evaluator:
    def __init__(self, wb):
        self.wb = wb
        self.cells = {}
        self.ranges = {}
        self.asts = {}

    def cell(self, sheet: str, col: int, row: int):
        key = (sheet, col, row)
        if key in self.cells:
            return self.cells[key]
        v = self.wb[sheet].cell(row=row, column=col).value
        if isinstance(v, str) and v.startswith("="):
            self.cells[key] = XLError("#CYCLE")
            v = self.evaluate(v, sheet)
        self.cells[key] = v
        return v

    def evaluate(self, formula: str, sheet: str):
        if formula not in self.asts:
            tokens = [t for t in Tokenizer(formula).items if t.type != Token.WSPACE]
            self.asts[formula] = Parser(tokens).parse()
        return self.ev(self.asts[formula], sheet)

    def ref(self, text: str, sheet: str):
        """A single cell gives a scalar; anything larger gives a list of rows."""
        if "!" in text:
            sheet, text = text.rsplit("!", 1)
            sheet = sheet.strip("'")
        key = (sheet, text)
        if key in self.ranges:
            return self.ranges[key]
        c0, r0, c1, r1 = range_boundaries(text)
        ws = self.wb[sheet]
        r0, r1 = r0 or 1, r1 or ws.max_row
        if c0 == c1 and r0 == r1:
            out = self.cell(sheet, c0, r0)
        else:
            out = [[self.cell(sheet, c, r) for c in range(c0, c1 + 1)] for r in range(r0, r1 + 1)]
        self.ranges[key] = out
        return out

    def ev(self, node, sheet):
        kind = node[0]
        if kind in ("num", "str", "bool"):
            return node[1]
        if kind == "ref":
            v = self.ref(node[1], sheet)
            if isinstance(v, XLError):
                raise v
            return v
        if kind == "neg":
            return -to_number(self.ev(node[1], sheet))
        if kind == "bin":
            _, op, l, r = node
            a = self.ev(l, sheet)
            b = self.ev(r, sheet)
            if op == "&":
                return to_text(a) + to_text(b)
            if op in ("=", "<>", "<", ">", "<=", ">="):
                return compare(op, a, b)
            x, y = to_number(a), to_number(b)
            if op == "+":
                return x + y
            if op == "-":
                return x - y
            if op == "*":
                return x * y
            if op == "/":
                if y == 0:
                    raise XLError("#DIV/0!")
                return x / y
            if op == "^":
                return x ** y
        if kind == "call":
            return self.call(node[1], node[2], sheet)
        raise ValueError(f"bad node {node}")

    def call(self, name, args, sheet):
        ev = lambda a: self.ev(a, sheet)
        if name == "IF":
            cond = to_bool(ev(args[0]))
            if cond:
                return ev(args[1])
            return ev(args[2]) if len(args) > 2 else False
        if name == "IFERROR":
            try:
                return ev(args[0])
            except XLError:
                return ev(args[1])
        if name == "AND":
            return all(to_bool(ev(a)) for a in args)
        if name == "OR":
            return any(to_bool(ev(a)) for a in args)
        if name == "NOT":
            return not to_bool(ev(args[0]))
        vals = [ev(a) for a in args]
        if name == "INDEX":
            table, row = vals[0], int(to_number(vals[1]))
            col = int(to_number(vals[2])) if len(vals) > 2 else None
            if col is None:
                if len(table) == 1:
                    return table[0][row - 1]
                if len(table[0]) == 1:
                    return table[row - 1][0]
                raise XLError("#REF!")
            return table[row - 1][col - 1]
        if name == "MATCH":
            x, table = vals[0], vals[1]
            mode = int(to_number(vals[2])) if len(vals) > 2 else 1
            flat = [v for row in table for v in row]
            if mode == 0:
                for i, v in enumerate(flat, 1):
                    if type(v) is type(x) or (isinstance(v, (int, float)) and isinstance(x, (int, float))):
                        if compare("=", x, v):
                            return i
                raise XLError("#N/A")
            best = None
            for i, v in enumerate(flat, 1):
                if isinstance(x, (int, float)) and not isinstance(x, bool) and isinstance(v, (int, float)) and not isinstance(v, bool):
                    if v <= x:
                        best = i
                elif isinstance(x, str) and isinstance(v, str) and compare("<=", v, x):
                    best = i
            if best is None:
                raise XLError("#N/A")
            return best
        nums = lambda: [to_number(v) for v in vals]
        if name == "ABS":
            return abs(to_number(vals[0]))
        if name == "SQRT":
            x = to_number(vals[0])
            if x < 0:
                raise XLError("#NUM!")
            return math.sqrt(x)
        if name == "MAX":
            return max(nums())
        if name == "MIN":
            return min(nums())
        if name == "SUM":
            return sum(nums())
        if name == "AVERAGE":
            return sum(nums()) / len(vals)
        if name == "ROUND":
            return excel_round(to_number(vals[0]), int(to_number(vals[1])))
        if name == "NORMSDIST":
            return float(stats.norm.cdf(to_number(vals[0])))
        if name == "NORMDIST":
            x, mu, sd, cum = to_number(vals[0]), to_number(vals[1]), to_number(vals[2]), to_bool(vals[3])
            if sd <= 0:
                raise XLError("#NUM!")
            return float(stats.norm.cdf(x, mu, sd)) if cum else float(stats.norm.pdf(x, mu, sd))
        raise ValueError(f"function {name} is not implemented")


# ----------------------------------------------------------------------------- comparison
def same(expected, got) -> bool:
    if expected is None:
        return got is None or got == ""
    if isinstance(expected, bool):
        return got == ("Yes" if expected else "No")
    if isinstance(expected, str):
        return got == expected
    if isinstance(got, str) or got is None:
        return False
    return math.isclose(float(expected), float(got), rel_tol=REL_TOL, abs_tol=ABS_TOL)


def columns(ws) -> dict[str, int]:
    """Header text -> column index; duplicate headers are keyed with a running suffix."""
    out, seen = {}, {}
    for j in range(1, ws.max_column + 1):
        h = ws.cell(row=1, column=j).value
        seen[h] = seen.get(h, 0) + 1
        out[(h, seen[h]) if seen[h] > 1 or h == "p" else h] = j
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--workbook", default=ROOT / "C40_ENSO_outlook.xlsx")
    ap.add_argument("--facts", default=ROOT / "data/processed/city_facts.json")
    ap.add_argument("--meta", default=ROOT / "data/processed/facts_meta.json")
    ap.add_argument("--show", type=int, default=20, help="mismatches to print")
    args = ap.parse_args()

    wb = load_workbook(args.workbook)
    facts = {(f["city"], f["season"]): f["variables"] for f in json.load(open(args.facts))}
    meta = json.load(open(args.meta))
    ev = Evaluator(wb)
    problems: list[str] = []
    counts = {}

    for name, n in EXPECTED_ROWS.items():
        if wb[name].max_row - 1 != n:
            problems.append(f"{name}: {wb[name].max_row - 1} rows, expected {n}")
    for addr, key in [("B4", "son_2026_roni"), ("B5", "son_2026_roni_sd")]:
        if not math.isclose(float(wb["Settings"][addr].value), meta[key]):
            problems.append(f"Settings!{addr} = {wb['Settings'][addr].value}, facts_meta {key} = {meta[key]}")

    def check(sheet, k, col, expected, label):
        # With shrinkage off the facts omit these three fields; the workbook then holds a factor
        # of 1 and the unshrunk effect, which is what the switch means, so there is nothing to compare.
        if expected is None and label.split()[-1] in ("shrink_factor", "enso_effect_shrunk_per_degC", "effect_this_season_raw"):
            return
        try:
            got = ev.cell(sheet, col, k)
        except XLError as e:
            got = str(e)
        counts[sheet] = counts.get(sheet, 0) + 1
        if not same(expected, got):
            problems.append(f"{sheet}!{wb[sheet].cell(row=k, column=col).coordinate} {label}: expected {expected!r}, got {got!r}")

    ws = wb["Linear"]
    cols = columns(ws)
    for k in range(2, ws.max_row + 1):
        city, season, var = ws.cell(row=k, column=1).value.split("|")
        f = facts[(city, season)][var]
        for key, head in LINEAR_FIELDS.items():
            if key in OPTIONAL and var not in OPTIONAL[key]:
                check("Linear", k, cols[head], None, f"{city}|{season}|{var} {key}")
                continue
            check("Linear", k, cols[head], f.get(key), f"{city}|{season}|{var} {key}")

    ws = wb["Quantiles"]
    cols = columns(ws)
    seen = 0
    for k in range(2, ws.max_row + 1):
        city, season, var, pct = ws.cell(row=k, column=cols["Key"]).value.split("|")
        f = facts[(city, season)][var]["percentiles"][PCT_KEYS[pct]]
        seen += 1
        for key, head in QUANTILE_FIELDS.items():
            check("Quantiles", k, cols[head], f.get(key), f"{city}|{season}|{var}|{pct} {key}")
    expected_blocks = sum(3 for v in facts.values() for d in v.values() if "percentiles" in d)
    if seen != expected_blocks:
        problems.append(f"Quantiles: {seen} rows against {expected_blocks} percentile fits in the facts")

    ws = wb["Tails"]
    cols = columns(ws)
    for k in range(2, ws.max_row + 1):
        city, season, var = ws.cell(row=k, column=cols["Key"]).value.split("|")
        f = facts[(city, season)][var]["percentiles"]["tails"]
        for key, head in TAIL_FIELDS.items():
            check("Tails", k, cols[head], f.get(key), f"{city}|{season}|{var} {key}")

    ws = wb["Summary"]
    cols = columns(ws)
    for k in range(2, ws.max_row + 1):
        city, season = ws.cell(row=k, column=1).value, ws.cell(row=k, column=3).value
        for head, j in cols.items():
            if not isinstance(head, str) or ": " not in head:
                continue
            short, lab = head.split(": ", 1)
            var, key = SUMMARY_VARS[short], SUMMARY_PULLS[lab]
            check("Summary", k, j, facts[(city, season)][var].get(key), f"{city}|{season}|{var} {key}")

    for sheet, n in counts.items():
        print(f"{sheet}: {n} cells compared")
    if problems:
        print(f"{len(problems)} mismatches")
        for p in problems[: args.show]:
            print("  " + p)
        return 1
    print("0 mismatches: the workbook's formulas reproduce city_facts.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""The Sep-Nov RONI implied by a CPC ENSO Diagnostic Discussion.

CPC states no point value for the coming season. It gives the chance that the
three-month RONI reaches a threshold, for example "54% for September-November"
at +2.5 °C. With a normal distribution of the given spread, that chance fixes
the median: median = threshold + spread * z(chance). The spread is ours; the
regression of Sep-Nov on the latest published season in run.py leaves a
residual spread of about 0.24 °C, and 0.25 is used unless another is given.

    python code/cpc_roni.py [data/raw/cpc_enso_discussion_2026-10-08.json] [--spread 0.25]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import NormalDist

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "data/raw/cpc_enso_discussion_2026-10-08.json"


def cpc_central(path: Path = DEFAULT, season: str = "SON", spread: float = 0.25) -> dict:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    p = d["chance_at_or_above_threshold"][season]
    thr = float(d["threshold"])
    center = thr + spread * NormalDist().inv_cdf(p)
    issued = d["issued"]
    source = (f"Sep–Nov 2026 RONI is not yet published. The outlook uses CPC's central estimate, "
              f"{center:+.2f} ± {spread:.2f} °C: CPC's ENSO discussion of {issued} gives a {p:.0%} chance of a "
              f"Sep–Nov RONI of {thr:+.1f} °C or more, which with a spread of {spread:.2f} °C puts the middle of "
              f"its distribution at {center:+.2f} °C. The estimate is refreshed with each CPC discussion and "
              f"replaced by the observed value in early December.")
    return {"roni": round(center, 2), "sd": round(spread, 2), "estimated": True, "source": source,
            "issued": issued, "chance": p, "threshold": thr}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("path", nargs="?", default=DEFAULT)
    ap.add_argument("--season", default="SON")
    ap.add_argument("--spread", type=float, default=0.25)
    a = ap.parse_args()
    r = cpc_central(Path(a.path), a.season, a.spread)
    print(f"{r['roni']:+.2f} ± {r['sd']:.2f}")
    print(r["source"])

"""Replay Sunday's switch on live purchases and compare ways of weighting the history (docs/experiments.md).

Each policy ranks every category by live purchases since the start of the replay plus a prior weight times
the history's share; "tuned" picks the weight every minute as `tati-terminator-category-viewed-live` does.
The score is the share of each category's purchases in the next 30 min that lands in its top 10.

    uv run python scripts/evaluate_category_ranking.py --start "2026-11-14 09:00:00"
"""

import argparse
import time

from dades_huzz.data import RawTree
from dades_huzz.evaluation import TREND_CHANGES, simulate_switch
from dades_huzz.features import (
    CATALOG_CATEGORY,
    HISTORY_PURCHASES,
    PRACTICE_ROUND_START,
    utc_ms,
)

PURCHASES = """
SELECT product_id::String AS product_id,
       intDiv(toUnixTimestamp64Milli(ts::DateTime64(3)) - {start_ms}, 60000) AS minute
FROM shop.events
WHERE event_type = 'purchase'
  AND ts::DateTime64(3) >= fromUnixTimestamp64Milli(toInt64({start_ms}))
  AND ts::DateTime64(3) < fromUnixTimestamp64Milli(toInt64({end_ms}))"""

POLICIES = {
    "fixed 500": 500,
    "fixed 2000": 2000,
    "history only": 1e9,
    "tuned (live version)": None,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--start", default=PRACTICE_ROUND_START, help="UTC start of the replay"
    )
    parser.add_argument("--minutes", type=int, default=120, help="final round length")
    parser.add_argument("--seeds", type=int, default=3)
    args = parser.parse_args()

    rawtree = RawTree.from_env()
    start_ms = utc_ms(args.start)
    end_ms = start_ms + (args.minutes + 30) * 60_000
    purchases = [
        (row["product_id"], int(row["minute"]))
        for row in rawtree.query(
            PURCHASES.format(start_ms=start_ms, end_ms=end_ms), timeout=120
        )
    ]
    history = {
        row["product_id"]: int(row["n"])
        for row in rawtree.query(HISTORY_PURCHASES, timeout=60)
    }
    category_of = {
        row["product_id"]: row["category"]
        for row in rawtree.query(CATALOG_CATEGORY, timeout=30)
    }
    print(
        f"replay from {args.start} UTC, {args.minutes} min: {len(purchases)} live purchases, "
        f"{len(category_of)} products, {args.seeds} seeds"
    )
    started = time.perf_counter()
    results = simulate_switch(
        purchases,
        history,
        category_of,
        POLICIES,
        seeds=args.seeds,
        minutes=args.minutes,
    )
    best = {c: max(r[c] for r in results.values()) for c in TREND_CHANGES}
    header = " ".join(f"{int(c * 100):>5}%" for c in TREND_CHANGES)
    print(f"{'trend change':>22} {header}  worst loss")
    for name, scores in results.items():
        cells = " ".join(f"{scores[c]:6.3f}" for c in TREND_CHANGES)
        loss = max(best[c] - scores[c] for c in TREND_CHANGES)
        print(f"{name:>22} {cells}  {loss:.4f}")
    print(f"({time.perf_counter() - started:.0f} s)")


if __name__ == "__main__":
    main()

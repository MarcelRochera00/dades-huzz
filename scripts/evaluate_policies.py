"""Score the recommenders offline on the last week of the old carousel log (docs/experiments.md).

Signals are built only from purchases before the cut, and the cases are the impressions after it.

    uv run python scripts/evaluate_policies.py --sample 10
"""

import argparse
import time

from dades_huzz.data import RawTree, State
from dades_huzz.evaluation import evaluate, history_cases
from dades_huzz.features import best_sellers_until, category_signals
from dades_huzz.model import best_sellers, category_best_sellers

CUT = "2026-11-07 07:00:00"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--cut", default=CUT, help="UTC time that splits signals from evaluation"
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=10,
        help="evaluate N tenths of the week (10 = all)",
    )
    args = parser.parse_args()

    started = time.monotonic()
    rawtree = RawTree.from_env()
    ranking = best_sellers_until(rawtree, args.cut)
    signals = category_signals(rawtree, args.cut)
    cases = history_cases(rawtree, args.cut, every=10, parts=range(args.sample))
    # the history catalogue has no stock changes: every product the log knows is available
    available = frozenset(signals.category_of) | frozenset(ranking)
    state = State(
        available=available, price={}, new_products=frozenset(), fallback=tuple(ranking)
    )
    print(
        f"cut {args.cut} | cases {len(cases)} | loaded in {time.monotonic() - started:.0f} s"
    )

    policies = {
        "tati-0-bestsellers": best_sellers,
        "tati-destroyer-category": category_best_sellers(
            signals.category_of, signals.ranked_by_category
        ),
    }
    print(
        "policy                   | slate IPS x100 (cap 20) | matched buys | weighted hit x100 | slot-1 SNIPS"
    )
    for name, recommend in policies.items():
        report = evaluate(recommend, cases, state)
        print(
            f"{name:24} | {report.slate.ips * 100:23.3f} | {report.slate.matched_purchases:12d} |"
            f" {report.weighted_hit * 100:17.3f} | {report.slot1.snips:.4f} ({report.slot1.matches} matches)"
        )


if __name__ == "__main__":
    main()

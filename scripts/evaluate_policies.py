"""Score the recommenders offline on the last week of the old carousel log (docs/experiments.md).

Signals are built only from purchases before the cut, and the cases are the impressions after it.
Every policy is compared with the first one (the baseline) on the same requests: the paired difference
in purchases per 100 requests with a 95 % bootstrap interval over shoppers, at caps 20, 50 and 100.

    uv run python scripts/evaluate_policies.py --sample 10
"""

import argparse
import time

from dades_huzz.data import RawTree, State
from dades_huzz.evaluation import (
    evaluate,
    history_cases,
    paired_difference,
    slate_ips_by_request,
)
from dades_huzz.features import best_sellers_until, category_signals
from dades_huzz.model import best_sellers, category_best_sellers

CUT = "2026-11-07 07:00:00"
CAPS = (20, 50, 100)


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
    parser.add_argument(
        "--draws", type=int, default=1000, help="bootstrap redraws of the shoppers"
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
    reports = {
        name: evaluate(recommend, cases, state) for name, recommend in policies.items()
    }
    print(
        "policy                   | slate IPS x100 (cap 20) | matched buys | weighted hit x100 | slot-1 SNIPS"
    )
    for name, report in reports.items():
        print(
            f"{name:24} | {report.slate.ips * 100:23.3f} | {report.slate.matched_purchases:12d} |"
            f" {report.weighted_hit * 100:17.3f} | {report.slot1.snips:.4f} ({report.slot1.matches} matches)"
        )

    logged = [case["logged"] for case in cases]
    baseline_name, *challengers = reports
    for cap in CAPS:
        values = {
            name: slate_ips_by_request(report.answers, logged, cap)
            for name, report in reports.items()
        }
        print(
            f"\ncap {cap} | vs {baseline_name}, purchases/100 requests, 95 % interval over shoppers"
        )
        for name in challengers:
            result = paired_difference(
                values[baseline_name], values[name], cases, draws=args.draws
            )
            print(
                f"{name:24} | IPS {sum(values[name]) / len(cases) * 100:.3f}"
                f" | diff {result.diff * 100:+.3f} [{result.low * 100:+.3f}, {result.high * 100:+.3f}]"
                f" | ratio {result.ratio:.2f} [{result.ratio_low:.2f}, {result.ratio_high:.2f}]"
            )


if __name__ == "__main__":
    main()

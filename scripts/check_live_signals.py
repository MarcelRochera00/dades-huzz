"""Which kinds of product our live answers sold, by slot: trust a signal only once it holds live.

uv run python scripts/check_live_signals.py                  # last 2 hours, every version
uv run python scripts/check_live_signals.py --minutes 20     # Sunday 10:20: do the signals hold on new data?
uv run python scripts/check_live_signals.py --version tati-terminator-category-viewed
"""

import argparse
from datetime import UTC, datetime

from dades_huzz.data import RawTree
from dades_huzz.evaluation import live_answers, signal_rates
from dades_huzz.features import category_signals, shopper_profiles


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--minutes", type=float, default=120)
    parser.add_argument("--version", help="only the answers of this model_version")
    args = parser.parse_args()
    rawtree = RawTree.from_env()
    now = f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S}"
    answers = live_answers(rawtree, args.minutes, args.version)
    rows = signal_rates(
        answers,
        category_signals(rawtree, until=now).category_of,
        shopper_profiles(rawtree, until=now),
    )
    print(
        f"{len(answers)} accepted answers in the last {args.minutes:g} min"
        f"{f' from {args.version}' if args.version else ''}; purchase rate of each product we showed"
    )
    columns = list(rows[0]) if rows else []
    widths = [max(len(c), *(len(str(r[c])) for r in rows)) for c in columns]
    print("  ".join(c.ljust(w) for c, w in zip(columns, widths)))
    for row in rows:
        print("  ".join(str(row[c]).ljust(w) for c, w in zip(columns, widths)))


if __name__ == "__main__":
    main()

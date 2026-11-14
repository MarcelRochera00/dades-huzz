"""How our live answers did in the last minutes: what escaped and why, speed, clicks, purchases, products.

uv run python scripts/check_serving.py            # last 10 minutes
uv run python scripts/check_serving.py --minutes 60
"""

import argparse

from dades_huzz.data import RawTree
from dades_huzz.serving import FEEDBACK_LAG_S, serving_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--minutes", type=float, default=10)
    args = parser.parse_args()
    print(
        f"Requests from {args.minutes:g} min ago up to {FEEDBACK_LAG_S} s ago (feedback arrives a few seconds late)"
    )
    for name, rows in serving_report(RawTree.from_env(), args.minutes).items():
        print(f"\n## {name}")
        if not rows:
            print("(none)")
            continue
        columns = list(rows[0])
        widths = [max(len(c), *(len(str(r[c])) for r in rows)) for c in columns]
        print("  ".join(c.ljust(w) for c, w in zip(columns, widths)))
        for row in rows:
            print("  ".join(str(row[c]).ljust(w) for c, w in zip(columns, widths)))


if __name__ == "__main__":
    main()

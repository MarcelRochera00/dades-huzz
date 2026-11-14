"""Answer every live request until stopped (Ctrl-C). Reads TEAM_ID and RAWTREE_API_KEY from .env.

    uv run python scripts/run_recommender.py

Run it on as many laptops as you like: one answers, the others wait and take over if it stops (handover).
With --no-handover it always answers: then never run two at once, each request would get two answers.
"""

import argparse
from pathlib import Path

from dades_huzz.data import RawTree
from dades_huzz.model import best_sellers
from dades_huzz.serving import serve


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--log",
        type=Path,
        default=Path("outputs/serve_log.jsonl"),
        help="one JSON line per answer",
    )
    parser.add_argument(
        "--no-handover",
        action="store_true",
        help="always answer: no heartbeat, no waiting for another loop (only if you are sure no other runs)",
    )
    args = parser.parse_args()
    serve(
        RawTree.from_env(),
        best_sellers,
        "best-sellers",
        log_path=args.log,
        handover=not args.no_handover,
    )


if __name__ == "__main__":
    main()

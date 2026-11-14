"""Answer every live request until stopped (Ctrl-C). Reads TEAM_ID and RAWTREE_API_KEY from .env.

    uv run python scripts/run_recommender.py

Never run two of these at once: each request would get two answers.
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
    args = parser.parse_args()
    serve(RawTree.from_env(), best_sellers, "best-sellers", log_path=args.log)


if __name__ == "__main__":
    main()

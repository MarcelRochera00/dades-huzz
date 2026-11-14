"""Measure versions before they go live: load time and memory, validity and speed on real requests, and the
cost of their background work to the answering loop. Reads TEAM_ID and RAWTREE_API_KEY from .env.

    uv run python scripts/check_versions.py tati-ultimatum-viewed-first tati-apocalypse-profile

Paste the output into the PR that adds a version (AGENTS.md / issue #5: needed to skip lane A's box).
"""

import argparse
import threading
import time

from dades_huzz.data import REQUESTS_SINCE, RawTree, as_request
from dades_huzz.serving.loop import LiveState
from dades_huzz.serving.split import main_thread_wait_ms, measure_version
from dades_huzz.serving.versions import VERSIONS

REFERENCE = "tati-terminator-category-viewed"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("versions", nargs="+", help=f"known: {', '.join(VERSIONS)}")
    parser.add_argument(
        "--minutes", type=float, default=2, help="real requests from the last N minutes"
    )
    parser.add_argument(
        "--watch", type=float, default=75, help="seconds to watch the background cost"
    )
    args = parser.parse_args()
    if unknown := set(args.versions) - set(VERSIONS):
        parser.error(
            f"unknown versions {sorted(unknown)}; known: {', '.join(VERSIONS)}"
        )
    rawtree = RawTree.from_env()
    started = time.monotonic()
    live = LiveState(rawtree)
    # Measure with the whole shoppers' day in State, as a running loop has it; its backfill is a start-up cost.
    startup = main_thread_wait_ms(180, until=live.shoppers_ready)
    print(
        f"shoppers' day in State after {time.monotonic() - started:.0f} s"
        f" ({len(live.state.shopper_categories)} shoppers); worst extra wait of the main thread meanwhile"
        f" {startup:.0f} ms (once per loop start)",
        flush=True,
    )
    since_ms = int(time.time() * 1000 - args.minutes * 60_000)
    requests = [
        as_request(row)
        for row in rawtree.query(REQUESTS_SINCE.format(since_ms=since_ms), timeout=10)
    ]
    reference = VERSIONS[REFERENCE](rawtree)
    for name in args.versions:
        m = measure_version(
            lambda name=name: VERSIONS[name](rawtree), requests, live.state, reference
        )
        print(
            f"{name}: load {m['load_s']:.1f} s, +{m['load_mb']:.0f} MB; {m['requests']} requests, invalid {m['invalid']},"
            f" differs from {REFERENCE} {m['differs_pct']:.0f} %; per call p50 {m['p50_ms']:.2f} ms,"
            f" p99 {m['p99_ms']:.2f} ms, max {m['max_ms']:.2f} ms",
            flush=True,
        )
    worst = main_thread_wait_ms(args.watch)
    print(
        f"{args.watch:.0f} s with {', '.join(args.versions)} loaded, after the backfill: worst extra wait of the main"
        f" thread {worst:.0f} ms"
        f" (about 6 ms with no extra version); threads {threading.active_count()}",
        flush=True,
    )


if __name__ == "__main__":
    main()

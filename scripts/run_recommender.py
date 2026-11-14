"""Answer every live request until stopped (Ctrl-C). Reads TEAM_ID and RAWTREE_API_KEY from .env.

    uv run python scripts/run_recommender.py

Run it on as many laptops as you like: one answers, the others wait and take over if it stops (handover).
By default a watchdog keeps the laptop awake and restarts the loop if it exits or hangs; its log is
outputs/watchdog.log. Keep the lid open and the laptop plugged in.

--no-watchdog runs the bare loop. --no-handover always answers: then never run two at once, each request
would get two answers.
"""

import argparse
import os
import sys
from pathlib import Path

from dades_huzz.data import RawTree
from dades_huzz.model import best_sellers
from dades_huzz.serving import serve
from dades_huzz.serving.watchdog import KeepAwake, exit_when_watchdog_dies, supervise

ALIVE_FILE = Path(f"outputs/loop_alive_{os.getpid()}")
"""One per watchdog: two watchdogs on one laptop must not see each other's loop as alive."""
WATCHDOG_LOG = Path("outputs/watchdog.log")


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
    parser.add_argument(
        "--no-watchdog",
        action="store_true",
        help="run the loop bare: no keep-awake, no restart when it exits or hangs",
    )
    parser.add_argument(
        "--alive-file", type=Path, help=argparse.SUPPRESS
    )  # set by the watchdog for its child
    args = parser.parse_args()
    if args.no_watchdog:
        if args.alive_file:  # started by the watchdog: stop if it dies
            exit_when_watchdog_dies()
        serve(
            RawTree.from_env(),
            best_sellers,
            "best-sellers",
            log_path=args.log,
            handover=not args.no_handover,
            alive_path=args.alive_file,
        )
        return
    child = [
        sys.executable,
        "-u",
        __file__,
        *sys.argv[1:],
        "--no-watchdog",
        "--alive-file",
        str(ALIVE_FILE),
    ]
    with KeepAwake("dades-huzz serving loop") as awake:
        print(f"watchdog: keep-awake: {awake.how}", flush=True)
        try:
            supervise(child, ALIVE_FILE, WATCHDOG_LOG)
        except KeyboardInterrupt:
            pass
        finally:
            ALIVE_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()

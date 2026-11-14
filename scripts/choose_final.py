"""Apply row 61's final selection rule from the live leaderboard (`by=model`), one command per step.

    uv run python scripts/choose_final.py choose                    # 07:00: best arm or cold/warm pair, 01:45-07:00 CET
    uv run python scripts/choose_final.py confirm --choice NAME     # 09:15: NAME vs Titan+, 07:15-09:15 CET

Times are CET on the day the command runs; --start/--end (HH:MM, CET) override them. Reads TEAM_ID from .env.
"""

import argparse
from datetime import date, datetime, time, timedelta, timezone

from dades_huzz.dashboard_leaderboard import (
    _practice_windows,
    _version_rows,
    leaderboard_state,
)
from dades_huzz.data import RawTree
from dades_huzz.evaluation.selection import (
    MIN_LEAD,
    MIN_WINDOWS_WON,
    arm_results,
    choose,
    confirm,
)

CET = timezone(timedelta(hours=1))
TITAN_PLUS = "lauri-titan-plus"
PHASES = {"choose": ("01:45", "07:00", 2), "confirm": ("07:15", "09:15", 4)}
"""Window in CET, and how many leaderboard reads cover it (choose: at most 3 h a read; confirm: 30-min windows)."""


def at(day: date, hhmm: str) -> datetime:
    return datetime.combine(day, time.fromisoformat(hhmm), CET)


def clock(ts: float) -> str:
    return datetime.fromtimestamp(ts, CET).strftime("%H:%M")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("phase", choices=PHASES)
    parser.add_argument(
        "--choice", help="confirm: the chosen model_version serving next to Titan+"
    )
    parser.add_argument("--start", help="HH:MM CET")
    parser.add_argument("--end", help="HH:MM CET")
    args = parser.parse_args()
    if args.phase == "confirm" and not args.choice:
        parser.error("confirm needs --choice")
    start, end, reads = PHASES[args.phase]
    today = datetime.now(CET).date()
    team = RawTree.from_env().team
    state = leaderboard_state()
    windows = _practice_windows(
        state, at(today, args.start or start), at(today, args.end or end), reads
    )
    if not windows:
        raise SystemExit("The leaderboard has no complete window there yet.")
    per_window = [_version_rows(team, window) for window in windows]
    print(
        f"Leaderboard by=model, team {team}, {clock(windows[0][0])}-{clock(windows[-1][1])} CET "
        f"in {len(windows)} reads"
    )
    arms = arm_results([row for rows in per_window for row in rows.values()])
    print(f"\n{'arm':<28}{'cold req':>9}{'cold':>7}{'warm req':>9}{'warm':>7}")
    for a in sorted(arms, key=lambda a: a.name):
        print(
            f"{a.name:<28}{a.cold_requests:>9}{a.cold_conversion:>7.2f}"
            f"{a.warm_requests:>9}{a.warm_conversion:>7.2f}"
        )

    if args.phase == "choose":
        best = choose(arms)
        print(
            f"\nCHOICE: cold requests -> {best.cold_arm}, the rest -> {best.warm_arm}, "
            f"expected conversion {best.expected_conversion:.2f}"
        )
        if best.cold_arm == best.warm_arm == TITAN_PLUS:
            print("Titan+ goes to the final; no confirmation runs (row 61).")
        else:
            print(
                f"Next (row 61): serve it at 50 % against {TITAN_PLUS} at 50 % from 07:15 on both machines."
            )
        return

    by_name = {a.name: a for a in arms}
    for name in (args.choice, TITAN_PLUS):
        if name not in by_name:
            raise SystemExit(f"{name} has no requests in this window.")

    def total(name: str) -> float:
        a = by_name[name]
        requests = a.cold_requests + a.warm_requests
        return (
            a.cold_conversion * a.cold_requests + a.warm_conversion * a.warm_requests
        ) / requests

    paired = [
        (rows[args.choice]["conversion"], rows[TITAN_PLUS]["conversion"])
        for rows in per_window
        if args.choice in rows and TITAN_PLUS in rows
    ]
    print(f"\n{'window':<14}{args.choice:>28}{TITAN_PLUS:>20}")
    for (first, last), (c, t) in zip(windows, paired, strict=False):
        print(f"{clock(first)}-{clock(last):<8}{c:>28.2f}{t:>20.2f}")
    choice, titan = total(args.choice), total(TITAN_PLUS)
    won = sum(c > t for c, t in paired)
    print(
        f"\nWhole window: {args.choice} {choice:.2f}, {TITAN_PLUS} {titan:.2f}, lead {choice - titan:+.2f} "
        f"(bar +{MIN_LEAD:.2f}); windows won {won} of {len(paired)} (bar {MIN_WINDOWS_WON})"
    )
    final = args.choice if confirm(choice, titan, paired) else TITAN_PLUS
    print(f"FINAL: {final}")


if __name__ == "__main__":
    main()

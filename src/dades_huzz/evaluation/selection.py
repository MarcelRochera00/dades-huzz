"""Row 61's final selection rule: which model serves the scored final.

The live leaderboard splits every arm's conversion into cold requests (new shoppers) and warm requests.
An arm can be best on one and not the other, so at 07:00 we may combine two arms: `cold_first(A, B)`
answers cold requests with A and the rest with B. `choose` picks the best such pair from the night's
numbers; `confirm` checks the pick on fresh data against the arm that has led all night.
"""

from dataclasses import dataclass
from itertools import product

from dades_huzz.serving.split import pair_name


@dataclass(frozen=True)
class ArmResult:
    """One live arm's numbers over a window, from the leaderboard (`by=model`). Conversion in %."""

    name: str
    cold_requests: int
    cold_conversion: float
    warm_requests: int
    warm_conversion: float

    @property
    def conversion(self) -> float:
        """Over all its requests, cold and warm."""
        requests = self.cold_requests + self.warm_requests
        return (
            self.cold_conversion * self.cold_requests
            + self.warm_conversion * self.warm_requests
        ) / requests


@dataclass(frozen=True)
class Choice:
    """The arm that answers cold requests and the arm that answers the rest (the same arm if one wins
    both), with the conversion the night's numbers expect from it."""

    cold_arm: str
    warm_arm: str
    expected_conversion: float


def choose(arms: list[ArmResult]) -> Choice:
    """Score every pair (cold arm, warm arm), a single arm being the pair with itself, as
    cold share x the cold arm's cold conversion + warm share x the warm arm's warm conversion,
    with the cold share pooled over all arms, and return the best."""
    cold = sum(a.cold_requests for a in arms)
    cold_share = cold / (cold + sum(a.warm_requests for a in arms))
    return max(
        (
            Choice(
                c.name,
                w.name,
                cold_share * c.cold_conversion + (1 - cold_share) * w.warm_conversion,
            )
            for c, w in product(arms, arms)
        ),
        key=lambda choice: choice.expected_conversion,
    )


def confirmation_split(
    choice: Choice, titan_plus: str, candidate: str | None = None
) -> str | None:
    """The `--versions` to serve from 07:15 while the 07:00 choice is confirmed: Titan+ stays the champion and
    the choice, under one name (a pair as `pair:<cold>+<warm>`), gets the other half. None when the choice is
    Titan+ itself and nothing else needs confirming. A `candidate` built during the night joins as one more
    arm at an equal share (row 63's provision)."""
    chosen = (
        choice.cold_arm
        if choice.cold_arm == choice.warm_arm
        else pair_name(choice.cold_arm, choice.warm_arm)
    )
    challengers = [name for name in (chosen, candidate) if name and name != titan_plus]
    if not challengers:
        return None
    share = 100 // (len(challengers) + 1)
    shares = [(titan_plus, 100 - share * len(challengers))] + [
        (name, share) for name in challengers
    ]
    return ",".join(f"{name}={share}" for name, share in shares)


MIN_LEAD = 0.10
"""Row 61: the choice must convert at least this much more than Titan+ over the 2 h of confirmation."""
MIN_WINDOWS_WON = 3
"""Row 61: and convert more than Titan+ in at least this many of the four paired 30-min windows."""
WINDOWS = 4
"""Row 61: the 2 h of confirmation are read as four paired 30-min windows."""


def confirm(
    choice: float, titan_plus: float, windows: list[tuple[float, float]]
) -> bool:
    """Whether the 07:00 choice replaces Titan+ in the final: conversion over the whole confirmation for
    each, and (choice, Titan+) conversion for each paired window. A tied window is not won. Fewer than
    four windows is an error, not a smaller bar."""
    if len(windows) != WINDOWS:
        raise ValueError(
            f"row 61 confirms on {WINDOWS} paired windows, got {len(windows)}"
        )
    lead = round(choice - titan_plus, 6)
    won = sum(c > t for c, t in windows)
    return lead >= MIN_LEAD and won >= MIN_WINDOWS_WON


def arm_results(versions: list[dict]) -> list[ArmResult]:
    """Our arms from our team's `versions` in the leaderboard (`by=model`), one row per arm and read,
    added up per arm. The leaderboard gives all requests and the cold ones; the warm numbers are what
    remains. Conversion is purchases per 100 requests, so purchases add up across reads."""
    totals: dict[
        str, list[float]
    ] = {}  # name -> [cold requests, cold purchases, requests, purchases]
    for row in versions:
        cold = row.get("cold_requests") or 0
        t = totals.setdefault(row["model_version"], [0, 0.0, 0, 0.0])
        t[0] += cold
        t[1] += (row.get("cold_conversion") or 0.0) * cold
        t[2] += row["requests"]
        t[3] += row["conversion"] * row["requests"]
    arms = []
    for name, (cold, cold_purchases, requests, purchases) in totals.items():
        warm = requests - cold
        arms.append(
            ArmResult(
                name,
                cold_requests=cold,
                cold_conversion=cold_purchases / cold if cold else 0.0,
                warm_requests=warm,
                warm_conversion=(purchases - cold_purchases) / warm if warm else 0.0,
            )
        )
    return arms


def live_arms(reads: list[dict[str, dict]]) -> list[ArmResult]:
    """`arm_results` over all reads (each read: model_version -> leaderboard row, oldest first), keeping
    only the arms still serving in the last read: an arm retired during the night is not a candidate."""
    serving = set(reads[-1])
    return [
        a
        for a in arm_results([row for read in reads for row in read.values()])
        if a.name in serving
    ]


def paired_windows(
    reads: list[dict[str, dict]], choice: str, titan_plus: str
) -> list[tuple[float, float]]:
    """(choice, Titan+) conversion in each read, in order. An arm with no row in a window converted
    nothing there, so a window the choice did not serve counts as lost, never as skipped."""
    return [
        (
            read[choice]["conversion"] if choice in read else 0.0,
            read[titan_plus]["conversion"] if titan_plus in read else 0.0,
        )
        for read in reads
    ]

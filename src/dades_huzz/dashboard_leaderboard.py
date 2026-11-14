"""Public leaderboard results for the Team and Jury dashboard views."""

import math
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from itertools import combinations, pairwise
from typing import Any, TypedDict

import requests

LEADERBOARD_URL = "https://datathon.rawtree.dev/api/state"


class PracticePoint(TypedDict):
    bucket_start: datetime
    bucket_end: datetime
    model_version: str
    expected_purchases_per_100: float | None
    requests: int | None
    overlap: bool


def _read_state(params: dict[str, str | int] | None = None) -> dict[str, Any]:
    response = requests.get(LEADERBOARD_URL, params=params, timeout=(3, 8))
    response.raise_for_status()
    state = response.json()
    if not isinstance(state, dict) or not isinstance(state.get("mode"), str):
        raise TypeError("Unexpected public leaderboard response.")
    return state


def leaderboard_state() -> dict[str, Any]:
    """Read the public leaderboard's current state without team credentials."""
    return _read_state()


def _team_row(state: dict[str, Any], team: str) -> dict[str, Any]:
    return next(
        (row for row in state.get("teams", []) if row.get("team_id") == team), {}
    )


def official_team_score(state: dict[str, Any], team: str) -> float | None:
    """Return the published official score out of 100 once the final ranking is visible."""
    if state.get("mode") != "final" or state.get("hidden") is not False:
        return None
    score = _team_row(state, team).get("score")
    if type(score) in (int, float) and math.isfinite(score) and 0 <= score <= 100:
        return float(score)
    return None


def _practice_windows(
    state: dict[str, Any], start: datetime, end: datetime, max_points: int
) -> list[tuple[int, int]]:
    """Build disjoint, closed windows that the API will accept without rounding or clipping."""
    limits = state["limits"]
    step = int(limits["step"])
    earliest = max(start.timestamp(), limits["earliest"])
    latest = min(end.timestamp(), state["updated_at"], state["final_start"])
    start_seconds = math.ceil(earliest / step) * step
    steps = math.floor((latest - start_seconds) / step)
    min_steps = math.ceil(limits["min"] / step)
    max_steps = math.floor(limits["max"] / step)

    # If the requested range cannot fit, cover the latest complete windows.
    if steps > max_points * max_steps:
        start_seconds += (steps - max_points * max_steps) * step
        steps = max_points * max_steps
    count = min(max_points, steps // min_steps)
    if count <= 0:
        return []
    boundaries = [start_seconds + (steps * i // count) * step for i in range(count + 1)]
    return list(pairwise(boundaries))


def _version_rows(team: str, window: tuple[int, int]) -> dict[str, dict[str, Any]]:
    start, end = window
    state = _read_state({"by": "model", "from": start, "to": end})
    if state.get("mode") != "practice" or state.get("window") != [start, end]:
        raise ValueError(
            "The leaderboard did not return the requested practice window."
        )
    return {
        row["model_version"]: row
        for row in _team_row(state, team).get("versions", [])
        if row.get("model_version") and row.get("requests", 0) > 0
    }


def _overlapping_traffic(versions: dict[str, dict[str, Any]]) -> bool:
    """Check reported first/last times. Configured shares and split boundaries are separate."""
    spans = [
        (row["first"], row["last"])
        for row in versions.values()
        if isinstance(row.get("first"), (int, float))
        and isinstance(row.get("last"), (int, float))
    ]
    return any(max(a, c) < min(b, d) for (a, b), (c, d) in combinations(spans, 2))


def practice_series(
    team: str, start: datetime, end: datetime, *, max_points: int = 12
) -> list[PracticePoint]:
    """Return reported per-version conversion by window and null values for gaps.

    A point covers the whole interval from bucket_start to bucket_end. A gap means the public
    leaderboard has no row for that version in the interval. Its counts can differ from the
    dashboard's assigned-request counts.
    """
    if start.utcoffset() is None or end.utcoffset() is None:
        raise ValueError("Leaderboard windows require time zone aware timestamps.")
    if not 1 <= max_points <= 24:
        raise ValueError("Request between 1 and 24 leaderboard points.")
    state = leaderboard_state()
    if state["mode"] != "practice":
        raise ValueError("Custom leaderboard windows are available during practice.")
    if not state.get("limits"):
        raise ValueError("The leaderboard has not published its practice time windows.")
    windows = _practice_windows(state, start, end, max_points)
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(lambda window: _version_rows(team, window), windows))
    versions = sorted({version for bucket in rows for version in bucket})
    series: list[PracticePoint] = []
    for (first, last), bucket in zip(windows, rows, strict=True):
        overlap = _overlapping_traffic(bucket)
        for version in versions:
            row = bucket.get(version, {})
            series.append(
                {
                    "bucket_start": datetime.fromtimestamp(first, UTC),
                    "bucket_end": datetime.fromtimestamp(last, UTC),
                    "model_version": version,
                    "expected_purchases_per_100": row.get("conversion"),
                    "requests": row.get("requests"),
                    "overlap": overlap,
                }
            )
    return series

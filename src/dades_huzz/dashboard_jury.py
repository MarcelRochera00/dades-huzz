"""Read confirmed recommendation sales for the Jury view."""

from dataclasses import dataclass
from datetime import UTC, datetime

from dades_huzz.data import CATALOG_UPDATES_SINCE, RawTree, current_state
from dades_huzz.serving.trends import SubcategoryHeat, read_heat_backfill

# The organizers publish the schedule in Barcelona time (CET for this event).
PRACTICE_START_MS = int(datetime(2026, 11, 14, 9, tzinfo=UTC).timestamp() * 1000)
FINAL_START_MS = int(datetime(2026, 11, 15, 9, tzinfo=UTC).timestamp() * 1000)
FINAL_END_MS = int(datetime(2026, 11, 15, 11, tzinfo=UTC).timestamp() * 1000)
JURY_BUCKET_MS = 10 * 60 * 1000


@dataclass(frozen=True)
class PracticeArm:
    version: str
    label: str
    expected_per_100: float
    requests: int


# RawTree practice leaderboard, 14 Nov 14:30–14:50 UTC (docs/experiments.md, #17).
# Practice windows are no longer available from the leaderboard during the final.
PRACTICE_DESTROYER = PracticeArm(
    "tati-destroyer-category", "Tati Destroyer", 1.037, 1843
)
PRACTICE_BEST_SELLERS = PracticeArm(
    "tati-0-bestsellers", "In-stock best sellers", 0.747, 1757
)
PRACTICE_LIFT_PCT = 100 * (
    PRACTICE_DESTROYER.expected_per_100 / PRACTICE_BEST_SELLERS.expected_per_100 - 1
)


JURY_RESULTS = """
WITH request_times AS (
    SELECT request_id::String AS id,
           min(toUnixTimestamp64Milli(ts::DateTime64(3))) AS request_ms
    FROM shop.requests
    WHERE toUnixTimestamp64Milli(ts::DateTime64(3)) >= {practice_start_ms}
      AND toUnixTimestamp64Milli(ts::DateTime64(3)) < {final_end_ms}
    GROUP BY id
), latest_feedback AS (
    SELECT request_id::String AS id,
           argMax(tuple(served_by::String, shown::Array(String), purchased::String,
                        revenue_eur::Float64), ts::DateTime64(9)) AS outcome
    FROM {team}.feedback
    WHERE request_id::String != '__init__'
    GROUP BY id
), matching_versions AS (
    SELECT request_id::String AS id, items::Array(String) AS items_shown,
           any(model_version::String) AS version_name
    FROM {team}.submissions
    GROUP BY id, items_shown
    HAVING uniqExact(model_version::String) = 1 AND version_name != ''
)
SELECT
    if(r.request_ms < {final_start_ms}, 'Practice', 'Final') AS period_name,
    intDiv(r.request_ms, {bucket_ms}) * {bucket_ms} AS start_ms,
    if(f.outcome.1 = 'team', s.version_name, '') AS version,
    max(r.request_ms) AS feedback_through_ms, count() AS shown,
    countIf(f.outcome.3 != '') AS purchases, sum(f.outcome.4) AS revenue_eur
FROM request_times AS r
INNER JOIN latest_feedback AS f ON r.id = f.id
LEFT JOIN matching_versions AS s ON r.id = s.id AND f.outcome.2 = s.items_shown
GROUP BY period_name, start_ms, version
ORDER BY start_ms, version
"""


@dataclass(frozen=True)
class JuryBucket:
    """Results for one version within a ten-minute bucket."""

    version: str
    start_ms: int
    shown: int
    purchases: int
    revenue_eur: float


@dataclass(frozen=True)
class JuryPeriod:
    name: str
    start_ms: int
    end_ms: int
    feedback_through_ms: int | None
    rows: tuple[JuryBucket, ...]


@dataclass(frozen=True)
class JuryData:
    periods: tuple[JuryPeriod, ...]


def load_jury_data(rawtree: RawTree) -> JuryData:
    """Credit completed feedback only when its shown list matches one submitted version."""
    rows = rawtree.query(
        JURY_RESULTS.format(
            team=rawtree.team,
            practice_start_ms=PRACTICE_START_MS,
            final_start_ms=FINAL_START_MS,
            final_end_ms=FINAL_END_MS,
            bucket_ms=JURY_BUCKET_MS,
        )
    )
    periods = []
    for name, start_ms, end_ms in (
        ("Practice", PRACTICE_START_MS, FINAL_START_MS),
        ("Final", FINAL_START_MS, FINAL_END_MS),
    ):
        period_rows = [row for row in rows if row["period_name"] == name]
        feedback_through_ms = max(
            (int(row["feedback_through_ms"]) for row in period_rows), default=None
        )
        buckets = tuple(
            JuryBucket(
                version=row["version"],
                start_ms=int(row["start_ms"]),
                shown=int(row["shown"]),
                purchases=int(row["purchases"]),
                revenue_eur=float(row["revenue_eur"]),
            )
            for row in period_rows
            if row["version"]
        )
        periods.append(JuryPeriod(name, start_ms, end_ms, feedback_through_ms, buckets))
    return JuryData(tuple(periods))


def read_demand_trends(rawtree: RawTree, end: datetime) -> list[tuple[str, float]]:
    """Replay Marcel's store demand detector at the end of the displayed 15-minute window."""
    if end.utcoffset() is None:
        raise ValueError("Demand trends require a timestamp with a time zone")
    end_ms = int(end.timestamp() * 1000)
    catalog = rawtree.catalog()
    updates = rawtree.query(
        CATALOG_UPDATES_SINCE.format(since_ms=0)
        + f" AND ts::DateTime64(3) < fromUnixTimestamp64Milli(toInt64({end_ms}))"
    )
    subcategories = current_state(catalog, updates, ()).subcategory
    counts, recent = read_heat_backfill(rawtree, end_ms)
    heat = SubcategoryHeat()
    heat.add_day(counts)
    heat.add(
        ((row["t"], name) for row in recent if (name := subcategories.get(row["p"]))),
        count_in_day=False,
    )
    return sorted(heat.hot(end_ms).items(), key=lambda trend: (-trend[1], trend[0]))

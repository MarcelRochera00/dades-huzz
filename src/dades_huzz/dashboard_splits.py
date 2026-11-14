"""Read practice split history and measure backup use by original assignment."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from itertools import accumulate
from math import hypot

from dades_huzz.dashboard_jury import FINAL_END_MS
from dades_huzz.data import RawTree
from dades_huzz.serving.handover import SILENT_MS
from dades_huzz.serving.report import conversion_interval_pct
from dades_huzz.serving.versions import parse_split

# Marcel verified these UTC boundaries from submissions/feedback in the Lane D discussion:
# https://github.com/ProGabo/dades-huzz/issues/9#issuecomment-6880413427
HISTORICAL_SPLITS = (
    ("11:11:52", "baseline=100"),
    ("11:24:41", "best-sellers=100"),
    ("13:29:29", "best-sellers=50,tati-destroyer-category=50"),
    ("13:35:10", "tati-0-bestsellers=50,tati-destroyer-category=50"),
    ("14:56:31", "tati-destroyer-category=50,tati-terminator-category-viewed=50"),
    ("15:06:06", "tati-terminator-category-viewed=100"),
)
HISTORICAL_VERIFIED_THROUGH = datetime(2026, 11, 14, 16, 12, 3, tzinfo=UTC)


# Compress consecutive heartbeats into intervals on the server. A gap or a blank
# split from an older serving loop means coverage is unknown.
HEARTBEAT_PERIODS = """
WITH beats AS (
    SELECT ts_ms::Int64 AS at_ms, loop_id::String AS host_loop,
           versions::String AS configured, out::String AS paused
    FROM {team}.scratch
    WHERE kind::String = 'heartbeat' AND role::String = 'active'
      AND ts_ms::Int64 >= {start_ms} AND ts_ms::Int64 < {end_ms}
), changes AS (
    SELECT *,
           (at_ms - lagInFrame(at_ms) OVER w > {silence_ms}
             OR host_loop != lagInFrame(host_loop) OVER w
             OR configured != lagInFrame(configured) OVER w
             OR paused != lagInFrame(paused) OVER w) AS changed
    FROM beats
    WINDOW w AS (ORDER BY at_ms, host_loop ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
), runs AS (
    SELECT *,
           sum(changed) OVER (ORDER BY at_ms, host_loop
                               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS run_number
    FROM changes
)
SELECT min(at_ms) AS start_ms, max(at_ms) AS last_ms,
       any(configured) AS configuration, any(paused) AS unavailable
FROM runs
GROUP BY run_number
ORDER BY start_ms
"""

# The official cold definition (docs/contracts.md): a new shopper, or a request that viewed a product with a
# `new_product` update before `end`. One row per request; `start` and `end` are SQL time expressions.
COLD_FLAGS = """
SELECT request_id::String AS id,
       max(coalesce(is_new_user::Nullable(Bool), false)) AS new_shopper,
       max(arrayExists(
           view -> JSONExtractString(toJSONString(view), 'product_id') IN (
               SELECT product_id::String FROM shop.catalog_updates
               WHERE change::String = 'new_product' AND ts::DateTime64(3) < {end}
           ),
           recent_views::Array(Dynamic)
       )) AS viewed_new_product
FROM shop.requests
WHERE ts::DateTime64(3) >= {start} AND ts::DateTime64(3) < {end}
GROUP BY id
"""

# Use the same hash as Lane A A/B assignment but stop before paused versions are rerouted.
# Reversing the first eight digest bytes makes ClickHouse's little-endian byte cast match Python.
SPLIT_STATS = """
WITH active_requests AS (
    SELECT request_id::String AS id
    FROM shop.requests
    WHERE ts::DateTime64(3) >= fromUnixTimestamp64Milli({start_ms}, 'UTC')
      AND ts::DateTime64(3) < fromUnixTimestamp64Milli({end_ms}, 'UTC')
    GROUP BY id
), cold_requests AS ({cold_flags}), latest_feedback AS (
    SELECT request_id::String AS id,
           argMax(tuple(served_by::String, shown::Array(String), purchased::String,
                        revenue_eur::Float64), ts::DateTime64(9)) AS outcome,
           1 AS has_feedback
    FROM {team}.feedback
    WHERE request_id::String IN (SELECT id FROM active_requests)
      AND request_id::String != '__init__'
    GROUP BY id
), submitted AS (
    SELECT request_id::String AS id, items::Array(String) AS items_shown,
           any(model_version::String) AS version_name
    FROM {team}.submissions
    WHERE request_id::String IN (SELECT id FROM active_requests)
    GROUP BY id, items_shown
    HAVING uniqExact(model_version::String) = 1 AND version_name != ''
), outcomes AS (
    SELECT arrayFirstIndex(
               share_end -> reinterpretAsUInt64(reverse(substring(SHA256(r.id), 1, 8)))
                            % {total_share} < share_end,
               {cumulative_shares}
           ) AS assigned_index,
           coalesce(f.has_feedback, 0) AS finished, f.outcome.1 AS shown_by,
           s.version_name AS actual, f.outcome.3 AS purchased, f.outcome.4 AS amount,
           c.new_shopper OR c.viewed_new_product AS cold
    FROM active_requests AS r
    LEFT JOIN cold_requests AS c ON r.id = c.id
    LEFT JOIN latest_feedback AS f ON r.id = f.id
    LEFT JOIN submitted AS s ON r.id = s.id AND f.outcome.2 = s.items_shown
)
SELECT assigned_index, actual, shown_by, finished,
       count() AS requests, countIf(purchased != '') AS purchases, sum(amount) AS revenue_eur,
       countIf(cold) AS cold_requests, countIf(cold AND purchased != '') AS cold_purchases
FROM outcomes
GROUP BY assigned_index, actual, shown_by, finished
"""


@dataclass(frozen=True)
class SplitPeriod:
    start: datetime
    end: datetime
    configuration: str
    out: tuple[str, ...]
    source: str

    @property
    def shares(self) -> dict[str, int]:
        return parse_split(self.configuration)


@dataclass
class VersionStats:
    version: str
    assigned: int = 0
    pending: int = 0
    champion_backups: int = 0
    organizer_fallbacks: int = 0
    unknown_actual: int = 0
    purchases: int = 0
    revenue_eur: float = 0.0
    cold_completed: int = 0
    """Cold requests (new shopper, or viewed a product added during the event) with feedback."""
    cold_purchases: int = 0

    @property
    def completed(self) -> int:
        return self.assigned - self.pending


@dataclass(frozen=True)
class SplitStats:
    rows: tuple[VersionStats, ...]


@dataclass(frozen=True)
class PurchaseDifference:
    estimate: float
    lower: float
    upper: float


def purchase_difference(
    challenger: VersionStats, main: VersionStats
) -> PurchaseDifference | None:
    """Challenger minus main, in purchases per 100 requests with feedback."""
    if not challenger.completed or not main.completed:
        return None

    challenger_rate = 100 * challenger.purchases / challenger.completed
    main_rate = 100 * main.purchases / main.completed
    challenger_low, challenger_high = conversion_interval_pct(
        challenger.purchases, challenger.completed
    )
    main_low, main_high = conversion_interval_pct(main.purchases, main.completed)

    # Newcombe's method 10 combines the two Wilson intervals for independent proportions.
    estimate = challenger_rate - main_rate
    return PurchaseDifference(
        estimate,
        estimate - hypot(challenger_rate - challenger_low, main_high - main_rate),
        estimate + hypot(challenger_high - challenger_rate, main_rate - main_low),
    )


def _ms(value: datetime) -> int:
    if value.utcoffset() is None:
        raise ValueError("Dashboard split windows require timezone-aware timestamps.")
    return int(value.timestamp() * 1000)


def _from_ms(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, UTC)


def load_splits(rawtree: RawTree, end: datetime) -> list[SplitPeriod]:
    """Return the documented practice periods and intervals covered by active heartbeats.

    Heartbeat boundaries are approximate to the polling interval. Time outside recorded
    coverage is omitted, including silence longer than the handover threshold.
    """
    end_ms = min(_ms(end), FINAL_END_MS)
    end = _from_ms(end_ms)
    historical_end = min(end, HISTORICAL_VERIFIED_THROUGH)
    historical = [
        (datetime.fromisoformat(f"2026-11-14T{start}+00:00"), config)
        for start, config in HISTORICAL_SPLITS
    ]
    boundaries = [start for start, _ in historical[1:]] + [historical_end]
    periods = [
        SplitPeriod(start, min(stop, historical_end), config, (), "historical")
        for (start, config), stop in zip(historical, boundaries, strict=True)
        if start < historical_end
    ]
    telemetry_start_ms = _ms(HISTORICAL_VERIFIED_THROUGH)
    if end_ms <= telemetry_start_ms:
        return periods
    rows = rawtree.query(
        HEARTBEAT_PERIODS.format(
            team=rawtree.team,
            start_ms=telemetry_start_ms,
            end_ms=end_ms,
            silence_ms=SILENT_MS,
        )
    )
    for index, row in enumerate(rows):
        configuration = row["configuration"]
        if not configuration:
            continue
        start_ms = int(row["start_ms"])
        stop_ms = int(row["last_ms"]) + 1
        if index + 1 < len(rows):
            next_start_ms = int(rows[index + 1]["start_ms"])
            if next_start_ms - stop_ms < SILENT_MS:
                stop_ms = next_start_ms
        if start_ms >= stop_ms:
            continue
        period = SplitPeriod(
            _from_ms(start_ms),
            _from_ms(stop_ms),
            configuration,
            tuple(name for name in (row["unavailable"] or "").split(",") if name),
            "heartbeat",
        )
        previous = periods[-1] if periods else None
        if (
            previous
            and previous.end == period.start
            and replace(period, start=previous.start, end=previous.end) == previous
        ):
            periods[-1] = replace(previous, end=period.end)
        else:
            periods.append(period)
    return periods


def read_split_stats(rawtree: RawTree, period: SplitPeriod) -> SplitStats:
    """Assign every request in the period even if it has no answer or feedback."""
    shares = period.shares
    champion = next(iter(shares))
    stats = tuple(VersionStats(version) for version in shares)
    rows = rawtree.query(
        SPLIT_STATS.format(
            team=rawtree.team,
            start_ms=_ms(period.start),
            end_ms=_ms(period.end),
            cold_flags=COLD_FLAGS.format(
                start=f"fromUnixTimestamp64Milli({_ms(period.start)}, 'UTC')",
                end=f"fromUnixTimestamp64Milli({_ms(period.end)}, 'UTC')",
            ),
            total_share=sum(shares.values()),
            cumulative_shares=list(accumulate(shares.values())),
        )
    )
    for row in rows:
        result = stats[row["assigned_index"] - 1]
        count = row["requests"]
        result.assigned += count
        if not row["finished"]:
            result.pending += count
            continue
        result.purchases += row["purchases"]
        result.revenue_eur += row["revenue_eur"] or 0.0
        result.cold_completed += row["cold_requests"]
        result.cold_purchases += row["cold_purchases"]
        if row["shown_by"] == "fallback":
            result.organizer_fallbacks += count
        elif row["shown_by"] == "team" and row["actual"] == result.version:
            continue
        elif row["shown_by"] == "team" and row["actual"] == champion:
            result.champion_backups += count
        else:
            result.unknown_actual += count
    return SplitStats(stats)

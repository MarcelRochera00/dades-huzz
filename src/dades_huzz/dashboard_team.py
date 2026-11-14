"""Team-wide dashboard measurements that are independent of version assignment."""

from datetime import datetime, timedelta

from dades_huzz.data import RawTree, Record
from dades_huzz.features import CATALOG_CATEGORY

COLD_LABELS = ("New shopper only", "Viewed a new product only", "Both")

# Keep the newest feedback if a request has more than one feedback row.
FEEDBACK = """
SELECT request_id::String AS id,
       argMax(tuple(served_by::String, fallback_reason::String,
                    latency_ms::Nullable(Float64), purchased::String), ts::DateTime64(3)) AS outcome,
       max(ts::DateTime64(3)) AS feedback_at,
       1 AS has_feedback
FROM {team}.feedback
WHERE request_id::String IN (SELECT id FROM active_requests)
  AND request_id::String != '__init__'
GROUP BY id
"""

HEALTH = """
WITH active_requests AS (
    SELECT request_id::String AS id
    FROM shop.requests
    WHERE ts::DateTime64(3) >= {start} AND ts::DateTime64(3) < {end}
), feedback AS ({feedback})
SELECT count() AS requests,
       countIf(f.has_feedback = 1) AS completed,
       countIf(coalesce(f.has_feedback, 0) = 0) AS pending,
       countIf(f.outcome.1 = 'team') AS on_time,
       countIf(f.outcome.1 = 'fallback') AS organizer_fallbacks,
       countIf(f.outcome.1 = 'fallback' AND f.outcome.2 = 'missing') AS missing,
       countIf(f.outcome.1 = 'fallback' AND f.outcome.2 = 'late') AS late,
       countIf(f.outcome.1 = 'fallback' AND f.outcome.2 = 'invalid') AS invalid,
       quantileExactOrNullIf(0.5)(f.outcome.3, f.outcome.1 = 'team') AS p50_ms,
       quantileExactOrNullIf(0.95)(f.outcome.3, f.outcome.1 = 'team') AS p95_ms,
       maxOrNullIf(toUnixTimestamp(f.feedback_at), f.has_feedback = 1) AS feedback_through
FROM active_requests AS r
LEFT JOIN feedback AS f ON r.id = f.id
"""

COLD_GROUPS = """
WITH launches AS (
    SELECT DISTINCT product_id::String AS product
    FROM shop.catalog_updates
    WHERE change::String = 'new_product' AND ts::DateTime64(3) < {end}
), active_requests AS (
    SELECT request_id::String AS id,
           coalesce(is_new_user::Nullable(Bool), false) AS new_shopper,
           arrayExists(
               view -> JSONExtractString(toJSONString(view), 'product_id') IN (SELECT product FROM launches),
               recent_views::Array(Dynamic)
           ) AS viewed_new_product
    FROM shop.requests
    WHERE ts::DateTime64(3) >= {start} AND ts::DateTime64(3) < {end}
), feedback AS ({feedback})
SELECT multiIf(r.new_shopper AND r.viewed_new_product, 'Both',
               r.new_shopper, 'New shopper only', 'Viewed a new product only') AS group_name,
       count() AS requests,
       countIf(f.has_feedback = 1) AS completed,
       countIf(coalesce(f.has_feedback, 0) = 0) AS pending,
       countIf(f.has_feedback = 1 AND f.outcome.4 != '') AS purchases
FROM active_requests AS r
LEFT JOIN feedback AS f ON r.id = f.id
WHERE r.new_shopper OR r.viewed_new_product
GROUP BY group_name
"""

TRENDS = """
WITH recent_events AS (
    SELECT product_id::String AS product, event_type::String AS event,
           ts::DateTime64(3) >= {middle} AS recent
    FROM shop.events
    WHERE ts::DateTime64(3) >= {start} AND ts::DateTime64(3) < {end}
      AND event_type::String IN ('view', 'add_to_cart', 'purchase')
)
SELECT coalesce(nullIf(c.category, ''), 'Uncategorised') AS category,
       countIf(e.recent AND e.event = 'view') AS views,
       countIf(NOT e.recent AND e.event = 'view') AS earlier_views,
       countIf(e.recent AND e.event = 'add_to_cart') AS carts,
       countIf(NOT e.recent AND e.event = 'add_to_cart') AS earlier_carts,
       countIf(e.recent AND e.event = 'purchase') AS purchases,
       countIf(NOT e.recent AND e.event = 'purchase') AS earlier_purchases
FROM recent_events AS e
LEFT ANY JOIN ({catalog}) AS c ON e.product = c.product_id
GROUP BY category
ORDER BY views DESC, category
"""


def _sql_time(value: datetime) -> str:
    if value.utcoffset() is None:
        raise ValueError("Dashboard windows require a timestamp with a time zone")
    return f"fromUnixTimestamp64Milli({int(value.timestamp() * 1000)}, 'UTC')"


def read_health(rawtree: RawTree, end: datetime) -> Record:
    """Return last-30-minute counts, valid-answer latency, and latest feedback time."""
    sql = HEALTH.format(
        start=_sql_time(end - timedelta(minutes=30)),
        end=_sql_time(end),
        feedback=FEEDBACK.format(team=rawtree.team),
    )
    return rawtree.query(sql)[0]


def read_cold_groups(rawtree: RawTree, end: datetime) -> list[Record]:
    """Return mutually exclusive official cold groups for the last 30 minutes."""
    sql = COLD_GROUPS.format(
        start=_sql_time(end - timedelta(minutes=30)),
        end=_sql_time(end),
        feedback=FEEDBACK.format(team=rawtree.team),
    )
    by_label = {row["group_name"]: row for row in rawtree.query(sql)}
    counts = ("requests", "completed", "pending", "purchases")
    return [
        {"group": label, **{key: by_label.get(label, {}).get(key, 0) for key in counts}}
        for label in COLD_LABELS
    ]


def read_trends(rawtree: RawTree, end: datetime) -> list[Record]:
    """Compare regular shopping activity over the latest and preceding 15 minutes."""
    sql = TRENDS.format(
        start=_sql_time(end - timedelta(minutes=30)),
        middle=_sql_time(end - timedelta(minutes=15)),
        end=_sql_time(end),
        catalog=CATALOG_CATEGORY,
    )
    return rawtree.query(sql)

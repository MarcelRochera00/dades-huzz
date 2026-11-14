"""How our live answers did, as the organisers see it: what escaped and why, speed, what shoppers did."""

import requests

from dades_huzz.data import RawTree, Record
from dades_huzz.serving.handover import HEARTBEAT_S

FEEDBACK_LAG_S = 20
"""Feedback is written a few seconds after the deadline: the report leaves out the most recent requests."""

OUTCOMES = """
SELECT multiIf(f.request_id = '', 'no_feedback_yet', f.served_by = 'team', 'answered', f.fallback_reason) AS outcome,
       count() AS requests, countIf(s.request_id != '') AS we_sent
FROM (SELECT request_id::String AS request_id FROM shop.requests WHERE {window}) AS r
LEFT JOIN (SELECT request_id::String AS request_id, served_by::String AS served_by,
                  fallback_reason::String AS fallback_reason FROM {team}.feedback
           WHERE request_id::String != '__init__') AS f ON f.request_id = r.request_id
LEFT JOIN (SELECT DISTINCT request_id::String AS request_id FROM {team}.submissions) AS s ON s.request_id = r.request_id
GROUP BY outcome
ORDER BY requests DESC"""
"""Every request in the window by what happened to it: answered, or escaped as missing / late / invalid.
`we_sent` counts the ones we did write an answer for (a 'missing' we sent arrived too late to be read)."""

BY_RECOMMENDER = """
SELECT if(f.served_by = 'team', s.model_version, 'fallback') AS served_by, count() AS requests,
       quantile(0.5)(f.latency_ms) AS p50_ms, quantile(0.95)(f.latency_ms) AS p95_ms, max(f.latency_ms) AS max_ms,
       round(100 * countIf(f.clicked != '') / requests, 2) AS ctr_pct,
       round(100 * countIf(f.purchased != '') / requests, 2) AS conversion_pct,
       round(sum(f.revenue_eur) / requests, 3) AS revenue_per_request
FROM (SELECT request_id::String AS request_id FROM shop.requests WHERE {window}) AS r
INNER JOIN (SELECT request_id::String AS request_id, served_by::String AS served_by,
                   latency_ms::Nullable(Float64) AS latency_ms, clicked::String AS clicked,
                   purchased::String AS purchased, revenue_eur::Float64 AS revenue_eur
            FROM {team}.feedback WHERE request_id::String != '__init__') AS f ON f.request_id = r.request_id
LEFT JOIN (SELECT request_id::String AS request_id, any(model_version::String) AS model_version
           FROM {team}.submissions GROUP BY request_id) AS s ON s.request_id = r.request_id
GROUP BY served_by
ORDER BY requests DESC"""
"""Speed and what shoppers did, per recommender (our model_version) and for the fallback."""

SENT = """
SELECT r.request_id AS request_id, r.ts AS ts, a.items AS items
FROM (SELECT request_id::String AS request_id, ts::DateTime64(3) AS ts FROM shop.requests WHERE {window}) AS r
INNER JOIN (SELECT request_id::String AS request_id, any(items::Array(String)) AS items
            FROM {team}.submissions GROUP BY request_id) AS a ON a.request_id = r.request_id"""
"""Our answers to the requests in the window, whether or not the organisers accepted them."""

DISTINCT_PRODUCTS = """
SELECT uniqExact(request_id) AS answers, uniqExact(product) AS distinct_products
FROM (SELECT request_id, arrayJoin(items) AS product FROM ({sent}))"""

PRODUCTS_SENT = """
SELECT product, count() AS answers_with_it, countIf(slot = 1) AS in_slot_1
FROM (SELECT arrayJoin(arrayEnumerate(items)) AS slot, items[slot] AS product FROM ({sent}))
GROUP BY product
ORDER BY answers_with_it DESC
LIMIT 10"""

UNAVAILABLE_SENT = """
SELECT product, count() AS answers_with_it
FROM (
    SELECT s.request_id AS request_id, s.product AS product
    FROM (SELECT request_id, ts, arrayJoin(items) AS product FROM ({sent})) AS s
    INNER JOIN (SELECT product_id::String AS product, ts::DateTime64(3) AS changed_at, is_active::Bool AS active
                FROM shop.catalog_updates) AS u ON u.product = s.product
    WHERE u.changed_at <= s.ts
    GROUP BY request_id, product
    HAVING argMax(u.active, u.changed_at) = false
)
GROUP BY product
ORDER BY answers_with_it DESC"""
"""Products we sent while they were inactive or out of stock at the request's time: each one made an answer
invalid. Empty is the goal."""


LOOPS = """
SELECT host::String AS host, loop_id::String AS loop_id,
       countIf(role::String = 'active') * {beat_s} AS approx_active_s, countIf(role::String = 'standby') * {beat_s} AS approx_standby_s,
       toDateTime(intDiv(max(ts_ms::Int64), 1000)) AS last_seen_utc
FROM {team}.scratch
WHERE kind::String = 'heartbeat'
  AND ts_ms::Int64 BETWEEN toUnixTimestamp64Milli(now64(3)) - {window_ms} AND toUnixTimestamp64Milli(now64(3)) - {lag_ms}
GROUP BY host, loop_id
ORDER BY last_seen_utc DESC"""
"""Which serving loops ran in the window (from their heartbeats), and roughly how long in each role
(heartbeats seen x 2 s: missed beats are not counted)."""

ANSWERED_TWICE = """
SELECT count() AS requests_answered_twice
FROM (SELECT a.request_id AS request_id
      FROM (SELECT request_id::String AS request_id FROM shop.requests WHERE {window}) AS r
      INNER JOIN (SELECT request_id::String AS request_id FROM {team}.submissions) AS a ON a.request_id = r.request_id
      GROUP BY request_id
      HAVING count() > 1)"""
"""Should always be 0: two answers for one request means two loops answered at once."""


def serving_report(rawtree: RawTree, minutes: float) -> dict[str, list[Record]]:
    """How the last `minutes` of live requests went, as the organisers see it, one table per section."""
    window = (
        f"ts::DateTime64(3) BETWEEN now64(3) - INTERVAL {int(minutes * 60) + FEEDBACK_LAG_S} SECOND"
        f" AND now64(3) - INTERVAL {FEEDBACK_LAG_S} SECOND"
    )
    sections = {
        "requests by outcome": OUTCOMES,
        "by recommender": BY_RECOMMENDER,
        "products we sent": DISTINCT_PRODUCTS,
        "most sent products": PRODUCTS_SENT,
        "unavailable products we sent": UNAVAILABLE_SENT,
        "answered twice": ANSWERED_TWICE,
        "serving loops": LOOPS,
    }
    sent = SENT.format(window=window, team=rawtree.team)
    window_ms = int((minutes * 60 + FEEDBACK_LAG_S) * 1000)
    report = {}
    for name, sql in sections.items():
        query = sql.format(
            window=window,
            team=rawtree.team,
            sent=sent,
            window_ms=window_ms,
            lag_ms=FEEDBACK_LAG_S * 1000,
            beat_s=HEARTBEAT_S,
        )
        try:
            report[name] = rawtree.query(query, timeout=30)
        except requests.HTTPError as e:
            # e.g. no heartbeat written yet: report the other sections anyway
            report[name] = [{"error": e.response.json().get("message", str(e))[:160]}]
    return report

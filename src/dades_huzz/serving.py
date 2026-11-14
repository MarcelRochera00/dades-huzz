"""The live loop: read new requests, answer each within 3 seconds, log what was sent, report what escaped.

Nothing here may stop the loop: shoppers keep arriving while we sleep, and a request we do not answer gets
the fallback. Every failure is logged and the loop carries on.
"""

import json
import threading
import time
import traceback
from collections.abc import Callable, Iterable
from collections.abc import Set as AbstractSet
from pathlib import Path

from dades_huzz.data import RawTree, Record, RequestCursor, State, current_state

Recommend = Callable[[Record, State], list[str]]
"""`recommend(request, state) -> list[str]`, the shared signature in docs/contracts.md."""

POLL_S = 0.3
MAX_AGE_MS = 2400
"""Requests older than this are skipped: our answer would reach RawTree after the 3 s deadline."""
STATE_REFRESH_S = 2.0

ANSWER_SIZE = 10


def validate(items: list[str], available: AbstractSet[str]) -> list[str]:
    """Why an answer would be rejected: 'duplicate', 'unavailable', 'wrong_size'. Empty means valid."""
    reasons = []
    if len(set(items)) != len(items):
        reasons.append("duplicate")
    if any(item not in available for item in items):
        reasons.append("unavailable")
    if len(items) != ANSWER_SIZE:
        reasons.append("wrong_size")
    return reasons


def repair(
    items: Iterable[str], available: AbstractSet[str], fallback: Iterable[str]
) -> list[str]:
    """Drop duplicates and unavailable products, keep the order, pad from `fallback` up to ten."""
    answer: list[str] = []
    for item in [*items, *fallback]:
        if len(answer) == ANSWER_SIZE:
            break
        if item in available and item not in answer:
            answer.append(item)
    return answer


def now_ms() -> int:
    return int(time.time() * 1000)


def until_ok[T](load: Callable[[], T], what: str) -> T:
    """Retry a start-up load until it works: a network blip at start must not stop the loop for good."""
    while True:
        try:
            return load()
        except Exception as e:  # noqa: BLE001  retried, never fatal
            print(f"loading {what} failed, retrying in 2 s: {e}", flush=True)
            time.sleep(2)


class LiveState:
    """Keeps the state fresh in a background thread, so answering never waits for it."""

    def __init__(self, rawtree: RawTree) -> None:
        self.rawtree = rawtree
        self.catalog = until_ok(rawtree.catalog, "catalogue")
        self.best_sellers = until_ok(rawtree.best_sellers, "best sellers")
        updates = until_ok(rawtree.catalog_updates, "catalogue updates")
        self.state = current_state(self.catalog, updates, self.best_sellers)
        self.refreshed_ms = now_ms()
        threading.Thread(target=self._refresh_forever, daemon=True).start()

    def _refresh_forever(self) -> None:
        while True:
            time.sleep(STATE_REFRESH_S)
            try:
                updates = self.rawtree.catalog_updates()
                self.state = current_state(self.catalog, updates, self.best_sellers)
                self.refreshed_ms = now_ms()
            except Exception as e:  # noqa: BLE001  keep answering with the last known state
                print(f"state refresh failed: {e}", flush=True)


def answer(
    requests: list[Record], recommend: Recommend, model_version: str, state: State
) -> list[Record]:
    """One valid answer per request, plus the problems that had to be repaired. The model may fail; the answer
    may not."""
    answers = []
    for request in requests:
        try:
            items = recommend(request, state)
            problems = validate(items, state.available)
        except Exception:  # noqa: BLE001  a model bug must not cost the answer
            traceback.print_exc()
            items, problems = [], ["model_error"]
        if problems:
            items = repair(items, state.available, state.fallback)
        answers.append(
            {
                "request_id": request["request_id"],
                "items": items,
                "model_version": model_version,
                "problems": problems,
            }
        )
    return answers


def serve(
    rawtree: RawTree, recommend: Recommend, model_version: str, log_path: Path
) -> None:
    """Answer requests forever with `recommend`, tagging every answer with `model_version`."""
    live = LiveState(rawtree)
    cursor = RequestCursor(MAX_AGE_MS)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    answered = errors = 0
    status_at = time.time()
    with log_path.open("a") as log:
        while True:
            started = time.time()
            try:
                fresh = cursor.accept(
                    rawtree.requests_since(cursor.since_ms(now_ms())), now_ms()
                )
                if fresh:
                    answers = answer(fresh, recommend, model_version, live.state)
                    rawtree.insert(
                        "submissions",
                        [
                            {k: a[k] for k in ("request_id", "items", "model_version")}
                            for a in answers
                        ],
                    )
                    sent_ms = now_ms()
                    for request, a in zip(fresh, answers):
                        log.write(
                            json.dumps(
                                {
                                    **a,
                                    "ts_ms": request["ts_ms"],
                                    "sent_ms": sent_ms,
                                    "latency_ms": sent_ms - request["ts_ms"],
                                }
                            )
                            + "\n"
                        )
                    log.flush()
                    answered += len(answers)
            except Exception as e:  # noqa: BLE001  the loop never stops
                errors += 1
                print(f"error: {e}", flush=True)
            if time.time() - status_at >= 10:
                print(
                    f"answered {answered}, skipped {cursor.skipped}, errors {errors}, "
                    f"state {(now_ms() - live.refreshed_ms) / 1000:.0f}s old",
                    flush=True,
                )
                status_at = time.time()
            time.sleep(max(0.0, POLL_S - (time.time() - started)))


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
    }
    sent = SENT.format(window=window, team=rawtree.team)
    return {
        name: rawtree.query(
            sql.format(window=window, team=rawtree.team, sent=sent), timeout=30
        )
        for name, sql in sections.items()
    }

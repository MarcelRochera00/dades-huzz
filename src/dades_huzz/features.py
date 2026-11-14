"""Signals for ranking.

Lane B precomputes history signals in RawTree SQL and loads them once at start.
Lane C scores the live stream: a trend is the weighted count of `shop.events` over the last 15 minutes.
"""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from dades_huzz.data import RawTree, Record, State

CATEGORY_RANKING = """
SELECT e.product_id AS product_id, c.category AS category, count() AS n
FROM (
    SELECT product_id::String AS product_id
    FROM shop.history_events
    WHERE event_type = 'purchase' AND ts::DateTime64(3) < '{until}'
) AS e
INNER JOIN (
    SELECT product_id::String AS product_id, category::String AS category FROM shop.catalog
) AS c ON e.product_id = c.product_id
GROUP BY product_id, category
ORDER BY category, n DESC, product_id DESC
LIMIT {per_category} BY category"""
"""The best sellers of each category, bought before `until`."""

CATALOG_CATEGORY = """
SELECT product_id::String AS product_id, category::String AS category FROM shop.catalog
UNION ALL
SELECT product_id::String AS product_id, category::String AS category FROM shop.catalog_updates
WHERE change::String = 'new_product'"""
"""Each product's category, including the products added during the event, which `shop.catalog` lacks."""

OVERALL_RANKING = """
SELECT product_id::String AS product_id, count() AS n
FROM shop.history_events
WHERE event_type = 'purchase' AND ts::DateTime64(3) < '{until}'
GROUP BY product_id
ORDER BY n DESC, product_id DESC"""
"""The all-time best sellers as they stood at `until`: the baseline ranking without looking ahead."""


@dataclass(frozen=True)
class CategorySignals:
    """What Tati Destroyer needs: each product's category and each category's best sellers."""

    category_of: dict[str, str]
    ranked_by_category: dict[str, list[str]]


def category_signals(
    rawtree: RawTree, until: str, per_category: int = 50
) -> CategorySignals:
    """Build the category signals from purchases before `until` (UTC, 'YYYY-MM-DD HH:MM:SS')."""
    category_of = {
        row["product_id"]: row["category"]
        for row in rawtree.query(CATALOG_CATEGORY, timeout=30)
    }
    ranked: dict[str, list[str]] = {}
    for row in rawtree.query(
        CATEGORY_RANKING.format(until=until, per_category=per_category), timeout=60
    ):
        ranked.setdefault(row["category"], []).append(row["product_id"])
    return CategorySignals(category_of=category_of, ranked_by_category=ranked)


TREND_WINDOW = timedelta(minutes=15)
"""How far back a trend looks. The window itself is the detector for this slice."""

TREND_WEIGHT = {"purchase": 4, "add_to_cart": 3, "view": 1}
"""What one organic event adds to a product's trend score."""


def _as_utc(ts: datetime | str) -> datetime:
    if isinstance(ts, datetime):
        return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)
    text = str(ts).replace("T", " ").removesuffix("Z")
    if "." in text:
        parsed = datetime.strptime(text[:26], "%Y-%m-%d %H:%M:%S.%f")
    else:
        parsed = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
    return parsed.replace(tzinfo=UTC)


def trend_scores(events: Iterable[Record], now: datetime) -> dict[str, int]:
    """Each product's weight in `shop.events` over the last 15 minutes, ending at `now`.

    A purchase counts 4, an add-to-cart 3 and a view 1. An event at or before `now` minus 15 minutes,
    or after `now`, does not count.
    """
    end = _as_utc(now)
    start = end - TREND_WINDOW
    scores: dict[str, int] = {}
    for event in events:
        when = _as_utc(event["ts"])
        if when <= start or when > end:
            continue
        weight = TREND_WEIGHT.get(str(event["event_type"]))
        if weight is None:
            continue
        product_id = str(event["product_id"])
        scores[product_id] = scores.get(product_id, 0) + weight
    return scores


def purchases_in_window(
    events: Iterable[Record], now: datetime
) -> dict[str, frozenset[str]]:
    """Each shopper's organic purchases in the last 15 minutes."""
    end = _as_utc(now)
    start = end - TREND_WINDOW
    bought: dict[str, set[str]] = {}
    for event in events:
        if str(event.get("event_type")) != "purchase":
            continue
        when = _as_utc(event["ts"])
        if when <= start or when > end:
            continue
        bought.setdefault(str(event.get("user_id")), set()).add(
            str(event["product_id"])
        )
    return {user_id: frozenset(products) for user_id, products in bought.items()}


def bought_in_window(
    events: Iterable[Record], user_id: str, now: datetime
) -> frozenset[str]:
    """Products this shopper purchased in the same 15-minute window (organic events only)."""
    return purchases_in_window(events, now).get(user_id, frozenset())


def apply_live_signals(state: State, events: Iterable[Record], now: datetime) -> State:
    """A state whose trend and recent purchases come from these organic events."""
    return replace(
        state,
        trend=trend_scores(events, now),
        recent_purchases=purchases_in_window(events, now),
    )


def best_sellers_until(rawtree: RawTree, until: str) -> list[str]:
    """Every product bought before `until`, best-selling first."""
    return [
        row["product_id"]
        for row in rawtree.query(OVERALL_RANKING.format(until=until), timeout=60)
    ]

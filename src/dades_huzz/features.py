"""Signals precomputed from the history (lane B), built in RawTree SQL and loaded once at start."""

from dataclasses import dataclass

from dades_huzz.data import RawTree

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


SHOPPER_PROFILES = """
SELECT e.user_id AS user_id, c.category AS category,
       sum(multiIf(e.event_type = 'purchase', 5, e.event_type = 'add_to_cart', 2, 1)) AS weight
FROM (
    SELECT user_id::String AS user_id, product_id::String AS product_id, event_type::String AS event_type
    FROM shop.history_events
    WHERE ts::DateTime64(3) < '{until}'
) AS e
INNER JOIN ({catalog}) AS c ON e.product_id = c.product_id
GROUP BY user_id, category"""
"""Each shopper's activity per category before `until`: a purchase counts 5, an add-to-cart 2, a view 1."""


SHOPPER_PURCHASES = """
SELECT user_id, groupUniqArray(product_id) AS products
FROM (
    SELECT user_id::String AS user_id, product_id::String AS product_id
    FROM shop.history_events
    WHERE event_type = 'purchase' AND ts::DateTime64(3) < '{until}'
    UNION ALL
    SELECT user_id::String AS user_id, product_id::String AS product_id
    FROM shop.events
    WHERE event_type = 'purchase' AND ts::DateTime64(3) < '{until}'
)
GROUP BY user_id"""
"""Every product each shopper bought before `until`: in the history, a snapshot from before the event, and live
in shop.events, which keeps growing through Sunday (organisers, Sat 17:30)."""


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


def best_sellers_until(rawtree: RawTree, until: str) -> list[str]:
    """Every product bought before `until`, best-selling first."""
    return [
        row["product_id"]
        for row in rawtree.query(OVERALL_RANKING.format(until=until), timeout=60)
    ]


def shopper_profiles(rawtree: RawTree, until: str) -> dict[str, dict[str, float]]:
    """Tati Apocalypse's signal: each shopper's share of their history per category, from events before
    `until` (UTC, 'YYYY-MM-DD HH:MM:SS'). About 60,000 shoppers x 10 categories, in about 3 s."""
    weights: dict[str, dict[str, float]] = {}
    for row in rawtree.query(
        SHOPPER_PROFILES.format(until=until, catalog=CATALOG_CATEGORY), timeout=120
    ):
        weights.setdefault(row["user_id"], {})[row["category"]] = float(row["weight"])
    return {
        user: {
            category: weight / sum(categories.values())
            for category, weight in categories.items()
        }
        for user, categories in weights.items()
    }


def shopper_purchases(rawtree: RawTree, until: str) -> dict[str, frozenset[str]]:
    """What each shopper already bought before `until`: the products not to show them again."""
    return {
        row["user_id"]: frozenset(row["products"])
        for row in rawtree.query(SHOPPER_PURCHASES.format(until=until), timeout=120)
    }

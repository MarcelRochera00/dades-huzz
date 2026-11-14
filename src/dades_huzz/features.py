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

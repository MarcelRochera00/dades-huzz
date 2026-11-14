"""Each shopper's day in shop.events: the categories and brands they viewed, what they carted and did not buy,
what they viewed and how many times.

The serving loop keeps it for `State` (docs/contracts.md): `shopper_categories`, `shopper_carted`,
`shopper_viewed`, `shopper_brands` and `shopper_view_counts`. A shopper's day predicts their purchase far better than the request's short `recent_views`
(issue #5): the day's main category 50 % of purchases against 26 % for the last view.

The day starts at the stream's start. At start-up it is backfilled from RawTree with already-aggregated SQL, up
to a cut; after that only new rows are read, every few seconds, and counted here.
"""

import gc
import sys
from collections.abc import Callable, Iterable
from typing import NamedTuple

from dades_huzz.data import RawTree, Record

CART_WEIGHT = 3
"""An add-to-cart says more than a view: it counts this many views of its category."""
VIEWED_MAX = 20
"""How many of a shopper's latest viewed products are kept."""
OVERLAP_MS = 30_000
"""Each read of new events goes back this far, so a row that lands in RawTree late is still read once."""
SHARDS = 8
"""The backfill is read in this many slices of shoppers, so no single query is large."""


class Snapshot(NamedTuple):
    """Per shopper, read-only: what `State` carries of their day."""

    categories: dict[str, dict[str, int]]
    carted: dict[str, frozenset[str]]
    viewed: dict[str, tuple[str, ...]]
    brands: dict[str, dict[str, int]]
    view_counts: dict[str, dict[str, int]]


EMPTY = Snapshot({}, {}, {}, {}, {})

EVENTS_SINCE = """
SELECT user_id::String AS u, product_id::String AS p, event_type::String AS e,
       toUnixTimestamp64Milli(ts::DateTime64(3)) AS t, region::String AS g
FROM shop.events
WHERE ts::DateTime64(3) >= fromUnixTimestamp64Milli(toInt64({since_ms}))"""

_BEFORE = "ts::DateTime64(3) < fromUnixTimestamp64Milli(toInt64({until_ms}))"
_SHARD = "cityHash64(user_id::String) % {shards} = {shard}"
_CATEGORY = """(SELECT product_id::String AS product_id, category::String AS category FROM shop.catalog
  UNION ALL SELECT product_id::String, category::String FROM shop.catalog_updates
  WHERE change::String = 'new_product')"""

BACKFILL_CATEGORIES = f"""
SELECT e.u AS u, c.category AS c, sum(e.w) AS n
FROM (SELECT user_id::String AS u, product_id::String AS product_id,
             if(event_type::String = 'add_to_cart', {CART_WEIGHT}, 1) AS w
      FROM shop.events
      WHERE event_type::String IN ('view', 'add_to_cart') AND {_BEFORE} AND {_SHARD}) AS e
INNER JOIN {_CATEGORY} AS c USING product_id
GROUP BY u, c"""

_BRAND = """(SELECT product_id::String AS product_id, brand::String AS brand FROM shop.catalog
  UNION ALL SELECT product_id::String, brand::String FROM shop.catalog_updates
  WHERE change::String = 'new_product')"""

BACKFILL_BRANDS = f"""
SELECT e.u AS u, c.brand AS b, sum(e.w) AS n
FROM (SELECT user_id::String AS u, product_id::String AS product_id,
             if(event_type::String = 'add_to_cart', {CART_WEIGHT}, 1) AS w
      FROM shop.events
      WHERE event_type::String IN ('view', 'add_to_cart') AND {_BEFORE} AND {_SHARD}) AS e
INNER JOIN {_BRAND} AS c USING product_id
GROUP BY u, b"""

BACKFILL_CARTED = f"""
SELECT user_id::String AS u, product_id::String AS p
FROM shop.events
WHERE event_type::String IN ('add_to_cart', 'purchase') AND {_BEFORE} AND {_SHARD}
GROUP BY u, p
HAVING maxIf(ts::DateTime64(3), event_type::String = 'add_to_cart')
     > maxIf(ts::DateTime64(3), event_type::String = 'purchase')"""

BACKFILL_VIEWED = f"""
SELECT u, arraySlice(arrayMap(x -> x.2, arrayReverseSort(groupArray((t, p, n)))), 1, {VIEWED_MAX}) AS v,
       arraySlice(arrayMap(x -> x.3, arrayReverseSort(groupArray((t, p, n)))), 1, {VIEWED_MAX}) AS c
FROM (SELECT user_id::String AS u, product_id::String AS p, max(ts::DateTime64(3)) AS t, count() AS n
      FROM shop.events
      WHERE event_type::String = 'view' AND {_BEFORE} AND {_SHARD}
      GROUP BY u, p)
GROUP BY u"""


def read_events_since(rawtree: RawTree, since_ms: int) -> list[Record]:
    """New views, add-to-carts and purchases since `since_ms`: a few hundred rows every few seconds."""
    return rawtree.query(EVENTS_SINCE.format(since_ms=int(since_ms)), timeout=2)


def read_backfill(
    rawtree: RawTree,
    until_ms: int,
    after_each: Callable[[], object] = gc.freeze,
) -> tuple[list[Record], list[Record], list[Record], list[Record]]:
    """The day before `until_ms`, aggregated in RawTree: (categories, carted, viewed, brands) rows for
    `add_backfill`.

    Read in SHARDS slices of shoppers. After each query `after_each` freezes what is loaded so far
    (`gc.freeze`): a full garbage-collector pass over hundreds of thousands of fresh rows stops every thread,
    the answering loop included, for 80-150 ms (#59). Frozen objects are still freed as usual when unused."""
    categories: list[Record] = []
    carted: list[Record] = []
    viewed: list[Record] = []
    brands: list[Record] = []
    for shard in range(SHARDS):
        cut = {"until_ms": int(until_ms), "shards": SHARDS, "shard": shard}
        for rows, sql in (
            (categories, BACKFILL_CATEGORIES),
            (carted, BACKFILL_CARTED),
            (viewed, BACKFILL_VIEWED),
            (brands, BACKFILL_BRANDS),
        ):
            rows += rawtree.query(sql.format(**cut), timeout=30)
            after_each()
    return categories, carted, viewed, brands


class ShopperDay:
    """Counts each shopper's events as they arrive, and hands out read-only snapshots for `State`.

    Only the thread that reads events calls `add`, `add_backfill` and `snapshot`. Every per-shopper value is
    replaced, never changed in place, so a snapshot shares them with no copy and stays valid while new events
    are counted. Product and category names are interned: 72k shoppers point at the same ~5k strings.
    """

    def __init__(
        self, viewed_max: int = VIEWED_MAX, overlap_ms: int = OVERLAP_MS
    ) -> None:
        self.viewed_max = viewed_max
        self.overlap_ms = overlap_ms
        self.newest_ms = 0
        self._categories: dict[str, dict[str, int]] = {}
        self._carted: dict[str, frozenset[str]] = {}
        self._bought: dict[str, frozenset[str]] = {}
        """Bought since live reading began: a cart from the backfill never brings these back."""
        self._viewed: dict[str, tuple[str, ...]] = {}
        self._brands: dict[str, dict[str, int]] = {}
        self._view_counts: dict[str, dict[str, int]] = {}
        """Views today of each product in `_viewed`; a product that falls out of the latest drops its count."""
        self._keys: dict[tuple[str, str, str, int], int] = {}
        self._changed: set[str] = set()
        self._snapshot: Snapshot = EMPTY

    def since_ms(self, floor_ms: int) -> int:
        """Where the next read of new events starts: a little before the newest row seen, never before `floor_ms`."""
        return max(self.newest_ms - self.overlap_ms, floor_ms)

    @staticmethod
    def _count(
        store: dict[str, dict[str, int]], user: str, key: str, weight: int
    ) -> None:
        counts = dict(store.get(user, {}))
        counts[key] = counts.get(key, 0) + weight
        store[user] = counts

    def add(
        self,
        rows: Iterable[Record],
        category_of: Callable[[str], str | None],
        brand_of: Callable[[str], str | None] = lambda product: None,
    ) -> list[Record]:
        """Count new event rows, in time order, and return them. A row already counted (read again in the
        overlap) is skipped and not returned."""
        new: list[Record] = []
        for row in sorted(rows, key=lambda r: r["t"]):
            key = (row["u"], row["p"], row["e"], row["t"])
            if key in self._keys:
                continue
            self._keys[key] = row["t"]
            new.append(row)
            self.newest_ms = max(self.newest_ms, row["t"])
            user, product, kind = row["u"], sys.intern(row["p"]), row["e"]
            weight = CART_WEIGHT if kind == "add_to_cart" else 1
            if kind in ("view", "add_to_cart"):
                if category := category_of(product):
                    self._count(self._categories, user, sys.intern(category), weight)
                if brand := brand_of(product):
                    self._count(self._brands, user, sys.intern(brand), weight)
            if kind == "view":
                latest = (
                    product,
                    *(p for p in self._viewed.get(user, ()) if p != product),
                )[: self.viewed_max]
                counts = self._view_counts.get(user, {})
                self._view_counts[user] = {
                    p: counts.get(p, 0) + (p == product) for p in latest
                }
                self._viewed[user] = latest
            elif kind == "add_to_cart":
                self._carted[user] = self._carted.get(user, frozenset()) | {product}
            elif kind == "purchase":
                self._carted[user] = self._carted.get(user, frozenset()) - {product}
                self._bought[user] = self._bought.get(user, frozenset()) | {product}
            self._changed.add(user)
        oldest_kept = self.newest_ms - 2 * self.overlap_ms
        self._keys = {k: t for k, t in self._keys.items() if t >= oldest_kept}
        return new

    def add_backfill(
        self,
        categories: Iterable[Record],
        carted: Iterable[Record],
        viewed: Iterable[Record],
        brands: Iterable[Record] = (),
    ) -> None:
        """Add the day before live reading began (rows from `read_backfill`), under what live reading counted."""
        for row in categories:
            self._count(self._categories, row["u"], sys.intern(row["c"]), row["n"])
            self._changed.add(row["u"])
        for row in brands:
            self._count(self._brands, row["u"], sys.intern(row["b"]), row["n"])
            self._changed.add(row["u"])
        for row in carted:
            if row["p"] not in self._bought.get(row["u"], ()):
                product = sys.intern(row["p"])
                self._carted[row["u"]] = self._carted.get(row["u"], frozenset()) | {
                    product
                }
                self._changed.add(row["u"])
        for row in viewed:
            latest = self._viewed.get(row["u"], ())
            earlier = dict(
                zip(row["v"], row.get("c") or [0] * len(row["v"]), strict=True)
            )
            older = (sys.intern(p) for p in row["v"] if p not in latest)
            kept = (*latest, *older)[: self.viewed_max]
            counts = self._view_counts.get(row["u"], {})
            self._view_counts[row["u"]] = {
                p: counts.get(p, 0) + earlier.get(p, 0) for p in kept
            }
            self._viewed[row["u"]] = kept
            self._changed.add(row["u"])

    def snapshot(self) -> Snapshot:
        """Each shopper's day (`Snapshot`). The values are shared, never changed: only the outer dicts are
        copied, and only shoppers with new events are looked up again."""
        frozen = Snapshot(*(dict(part) for part in self._snapshot))
        live_parts = (
            self._categories,
            self._carted,
            self._viewed,
            self._brands,
            self._view_counts,
        )
        for user in self._changed:
            for part, live in zip(frozen, live_parts, strict=True):
                if live.get(user):
                    part[user] = live[user]
                else:
                    part.pop(user, None)
        self._changed.clear()
        self._snapshot = frozen
        return self._snapshot

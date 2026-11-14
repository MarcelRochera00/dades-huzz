"""Each shopper's day in shop.events: the categories they viewed, what they carted and did not buy, what they viewed.

The serving loop keeps it for `State` (docs/contracts.md): `shopper_categories`, `shopper_carted` and
`shopper_viewed`. A shopper's day predicts their purchase far better than the request's short `recent_views`
(issue #5): the day's main category 50 % of purchases against 26 % for the last view.

The day starts at the stream's start. At start-up it is backfilled from RawTree with already-aggregated SQL, up
to a cut; after that only new rows are read, every few seconds, and counted here.
"""

import gc
import sys
from collections.abc import Callable, Iterable

from dades_huzz.data import RawTree, Record

CART_WEIGHT = 3
"""An add-to-cart says more than a view: it counts this many views of its category."""
VIEWED_MAX = 20
"""How many of a shopper's latest viewed products are kept."""
OVERLAP_MS = 30_000
"""Each read of new events goes back this far, so a row that lands in RawTree late is still read once."""
SHARDS = 8
"""The backfill is read in this many slices of shoppers, so no single query is large."""

Snapshot = tuple[
    dict[str, dict[str, int]], dict[str, frozenset[str]], dict[str, tuple[str, ...]]
]

EVENTS_SINCE = """
SELECT user_id::String AS u, product_id::String AS p, event_type::String AS e,
       toUnixTimestamp64Milli(ts::DateTime64(3)) AS t
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

BACKFILL_CARTED = f"""
SELECT user_id::String AS u, product_id::String AS p
FROM shop.events
WHERE event_type::String IN ('add_to_cart', 'purchase') AND {_BEFORE} AND {_SHARD}
GROUP BY u, p
HAVING maxIf(ts::DateTime64(3), event_type::String = 'add_to_cart')
     > maxIf(ts::DateTime64(3), event_type::String = 'purchase')"""

BACKFILL_VIEWED = f"""
SELECT u, arraySlice(arrayMap(x -> x.2, arrayReverseSort(groupArray((t, p)))), 1, {VIEWED_MAX}) AS v
FROM (SELECT user_id::String AS u, product_id::String AS p, max(ts::DateTime64(3)) AS t
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
) -> tuple[list[Record], list[Record], list[Record]]:
    """The day before `until_ms`, aggregated in RawTree: (categories, carted, viewed) rows for `add_backfill`.

    Read in SHARDS slices of shoppers. After each query `after_each` freezes what is loaded so far
    (`gc.freeze`): a full garbage-collector pass over hundreds of thousands of fresh rows stops every thread,
    the answering loop included, for 80-150 ms (#59). Frozen objects are still freed as usual when unused."""
    categories: list[Record] = []
    carted: list[Record] = []
    viewed: list[Record] = []
    for shard in range(SHARDS):
        cut = {"until_ms": int(until_ms), "shards": SHARDS, "shard": shard}
        for rows, sql in (
            (categories, BACKFILL_CATEGORIES),
            (carted, BACKFILL_CARTED),
            (viewed, BACKFILL_VIEWED),
        ):
            rows += rawtree.query(sql.format(**cut), timeout=30)
            after_each()
    return categories, carted, viewed


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
        self._keys: dict[tuple[str, str, str, int], int] = {}
        self._changed: set[str] = set()
        self._snapshot: Snapshot = ({}, {}, {})

    def since_ms(self, floor_ms: int) -> int:
        """Where the next read of new events starts: a little before the newest row seen, never before `floor_ms`."""
        return max(self.newest_ms - self.overlap_ms, floor_ms)

    def _count(self, user: str, category: str, weight: int) -> None:
        counts = dict(self._categories.get(user, {}))
        counts[category] = counts.get(category, 0) + weight
        self._categories[user] = counts

    def add(
        self, rows: Iterable[Record], category_of: Callable[[str], str | None]
    ) -> None:
        """Count new event rows, in time order. A row already counted (read again in the overlap) is skipped."""
        for row in sorted(rows, key=lambda r: r["t"]):
            key = (row["u"], row["p"], row["e"], row["t"])
            if key in self._keys:
                continue
            self._keys[key] = row["t"]
            self.newest_ms = max(self.newest_ms, row["t"])
            user, product, kind = row["u"], sys.intern(row["p"]), row["e"]
            if kind in ("view", "add_to_cart") and (category := category_of(product)):
                self._count(
                    user,
                    sys.intern(category),
                    CART_WEIGHT if kind == "add_to_cart" else 1,
                )
            if kind == "view":
                latest = (
                    product,
                    *(p for p in self._viewed.get(user, ()) if p != product),
                )
                self._viewed[user] = latest[: self.viewed_max]
            elif kind == "add_to_cart":
                self._carted[user] = self._carted.get(user, frozenset()) | {product}
            elif kind == "purchase":
                self._carted[user] = self._carted.get(user, frozenset()) - {product}
                self._bought[user] = self._bought.get(user, frozenset()) | {product}
            self._changed.add(user)
        oldest_kept = self.newest_ms - 2 * self.overlap_ms
        self._keys = {k: t for k, t in self._keys.items() if t >= oldest_kept}

    def add_backfill(
        self,
        categories: Iterable[Record],
        carted: Iterable[Record],
        viewed: Iterable[Record],
    ) -> None:
        """Add the day before live reading began (rows from `read_backfill`), under what live reading counted."""
        for row in categories:
            self._count(row["u"], sys.intern(row["c"]), row["n"])
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
            older = (sys.intern(p) for p in row["v"] if p not in latest)
            self._viewed[row["u"]] = (*latest, *older)[: self.viewed_max]
            self._changed.add(row["u"])

    def snapshot(self) -> Snapshot:
        """(categories, carted, viewed) per shopper. The values are shared, never changed: only the outer dicts
        are copied, and only shoppers with new events are looked up again."""
        frozen = tuple(dict(part) for part in self._snapshot)
        for user in self._changed:
            for part, live in zip(
                frozen, (self._categories, self._carted, self._viewed), strict=True
            ):
                if live.get(user):
                    part[user] = live[user]
                else:
                    part.pop(user, None)
        self._changed.clear()
        self._snapshot = frozen  # type: ignore[assignment]
        return self._snapshot

"""Hot subcategories: what is selling far above its normal level right now.

The stream injects trends as bursts of about an hour in one subcategory (Saturday: Aquariums 09:41, Kettles
11:32, Cutting Boards 13:40, Bike Helmets 15:33, Game Consoles 19:31 UTC, about every two hours). Replayed
minute by minute over Saturday, the thresholds below flag exactly those five, 2–3 minutes after each starts,
and nothing else (issue #5). The serving loop keeps the result in `State.hot_subcategories`; each version
decides how much to push it.
"""

from collections import Counter, deque
from collections.abc import Iterable

from dades_huzz.data import RawTree, Record

WINDOW_MS = 15 * 60_000
"""Purchases in this window are compared with the day's."""
MIN_RATIO = 2.0
"""A subcategory is hot when its share of the window's purchases is at least this many times its day share..."""
MIN_EXTRA = 25
"""...and it sold at least this many more than that day share predicts: a rare subcategory's spike of two
purchases is noise, not a trend."""

DAY_PURCHASES = """
SELECT c.subcategory AS s, count() AS n
FROM (SELECT product_id::String AS product_id FROM shop.events
      WHERE event_type::String = 'purchase'
        AND ts::DateTime64(3) < fromUnixTimestamp64Milli(toInt64({until_ms}))) AS e
INNER JOIN (SELECT product_id::String AS product_id, subcategory::String AS subcategory FROM shop.catalog
            UNION ALL SELECT product_id::String, subcategory::String FROM shop.catalog_updates
            WHERE change::String = 'new_product') AS c USING product_id
GROUP BY s"""

RECENT_PURCHASES = """
SELECT product_id::String AS p, toUnixTimestamp64Milli(ts::DateTime64(3)) AS t
FROM shop.events
WHERE event_type::String = 'purchase'
  AND ts::DateTime64(3) >= fromUnixTimestamp64Milli(toInt64({since_ms}))
  AND ts::DateTime64(3) < fromUnixTimestamp64Milli(toInt64({until_ms}))"""


def read_heat_backfill(
    rawtree: RawTree, until_ms: int
) -> tuple[dict[str, int], list[Record]]:
    """The day's purchases per subcategory before `until_ms`, and the purchase rows of the window before it."""
    day = {
        row["s"]: row["n"]
        for row in rawtree.query(
            DAY_PURCHASES.format(until_ms=int(until_ms)), timeout=30
        )
    }
    recent = rawtree.query(
        RECENT_PURCHASES.format(
            since_ms=int(until_ms) - WINDOW_MS, until_ms=int(until_ms)
        ),
        timeout=30,
    )
    return day, recent


class SubcategoryHeat:
    """Counts purchases per subcategory over the day and over the last WINDOW_MS, and says which are hot."""

    def __init__(
        self,
        window_ms: int = WINDOW_MS,
        min_ratio: float = MIN_RATIO,
        min_extra: int = MIN_EXTRA,
    ) -> None:
        self.window_ms = window_ms
        self.min_ratio = min_ratio
        self.min_extra = min_extra
        self.day: Counter[str] = Counter()
        self.window: deque[tuple[int, str]] = deque()

    def add_day(self, counts: dict[str, int]) -> None:
        """The day's purchases per subcategory before live counting began (the backfill)."""
        self.day.update(counts)

    def add(
        self, purchases: Iterable[tuple[int, str]], count_in_day: bool = True
    ) -> None:
        """New purchases as (time in ms, subcategory), each counted once by the caller. `count_in_day=False`
        for backfilled window rows that `add_day` already counted."""
        for t, subcategory in sorted(purchases):
            self.window.append((t, subcategory))
            if count_in_day:
                self.day[subcategory] += 1

    def hot(self, now_ms: int) -> dict[str, float]:
        """Hot subcategories at `now_ms`, each with how many times its day share it sells in the window."""
        while self.window and self.window[0][0] < now_ms - self.window_ms:
            self.window.popleft()
        in_window = Counter(subcategory for _, subcategory in self.window)
        window_total, day_total = len(self.window), sum(self.day.values())
        hot = {}
        for subcategory, n in in_window.items():
            expected = (
                window_total * self.day[subcategory] / day_total if day_total else 0.0
            )
            ratio = n / expected if expected else float(n)
            if n - expected >= self.min_extra and ratio >= self.min_ratio:
                hot[subcategory] = round(ratio, 2)
        return hot

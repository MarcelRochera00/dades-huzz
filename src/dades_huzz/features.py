"""Signals for ranking.

Lane B precomputes history signals in RawTree SQL and loads them once at start, and rebuilds the live
category ranking every minute from the purchases since the switch.
Lane C scores the live stream: a trend is the weighted count of `shop.events` over the last 15 minutes.
"""

import threading
import time
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from dades_huzz.data import RawTree, Record

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

    category_of: Mapping[str, str]
    ranked_by_category: Mapping[str, list[str]]


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


def best_sellers_until(rawtree: RawTree, until: str) -> list[str]:
    """Every product bought before `until`, best-selling first."""
    return [
        row["product_id"]
        for row in rawtree.query(OVERALL_RANKING.format(until=until), timeout=60)
    ]


PRACTICE_ROUND_START = "2026-11-14 09:00:00"
"""When the live stream opened (UTC): live sales count from here until the switch."""
FINAL_ROUND_START = "2026-11-15 09:00:00"
"""The switch (GLOSSARY.md), Sunday 10:00 CET in UTC: from here only the new data counts."""
PRIOR_WEIGHTS = (0, 250, 500, 1000, 2000, 5000, 20000)
"""How many live purchases the history is worth, the candidates the category ranking tunes over."""
START_PRIOR_WEIGHT = 500
"""The weight used until there is enough live data to tune it (docs/experiments.md)."""
TUNE_FROM_MS = 4 * 60_000
TUNE_WINDOW_MS = 10 * 60_000
"""The weight is the one that best predicted the last 10 minutes (half the elapsed time, at the start)."""
TOP = 10
"""What a tuning window scores: the share of each category's purchases that landed in its top 10."""
REFRESH_S = 60

LIVE_PURCHASES = """
SELECT product_id::String AS product_id,
       countIf(ts::DateTime64(3) < fromUnixTimestamp64Milli(toInt64({cut_ms}))) AS before,
       countIf(ts::DateTime64(3) >= fromUnixTimestamp64Milli(toInt64({cut_ms}))) AS recent
FROM shop.events
WHERE event_type = 'purchase'
  AND ts::DateTime64(3) >= fromUnixTimestamp64Milli(toInt64({since_ms}))
  AND ts::DateTime64(3) < fromUnixTimestamp64Milli(toInt64({now_ms}))
GROUP BY product_id"""
"""Each product's live purchases since `since_ms`, split at `cut_ms` (before the tuning window, in it)."""

HISTORY_PURCHASES = """
SELECT product_id::String AS product_id, count() AS n
FROM shop.history_events
WHERE event_type = 'purchase'
GROUP BY product_id"""


def utc_ms(text: str) -> int:
    """'YYYY-MM-DD HH:MM:SS' in UTC -> Unix milliseconds."""
    moment = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    return int(moment.timestamp() * 1000)


def live_sales_since_ms(now_ms: int) -> int:
    """Where live sales start counting: the switch once it has come, before it the practice round."""
    final = utc_ms(FINAL_ROUND_START)
    return final if now_ms >= final else utc_ms(PRACTICE_ROUND_START)


def category_ranking(
    live: Mapping[str, int],
    history_share: Mapping[str, float],
    category_of: Mapping[str, str],
    prior_weight: float,
    per_category: int = 200,
) -> dict[str, list[str]]:
    """The category ranking (GLOSSARY.md): each category's products by live purchases plus
    `prior_weight` times their share of the history's purchases, best first. A new product enters as soon
    as it sells; one without a known category or without any score is left out."""
    scored: dict[str, list[tuple[float, str]]] = {}
    for product in live.keys() | history_share.keys():
        category = category_of.get(product)
        score = live.get(product, 0) + prior_weight * history_share.get(product, 0.0)
        if category is not None and score > 0:
            scored.setdefault(category, []).append((score, product))
    return {
        category: [product for _, product in sorted(products, reverse=True)][
            :per_category
        ]
        for category, products in scored.items()
    }


def captured(
    ranked: Mapping[str, list[str]],
    purchases: Mapping[str, int],
    category_of: Mapping[str, str],
    top: int = TOP,
) -> float:
    """The share of each category's `purchases` that landed in its top `top`, averaged over categories."""
    tops = {category: set(products[:top]) for category, products in ranked.items()}
    total: dict[str, int] = {}
    hit: dict[str, int] = {}
    for product, n in purchases.items():
        category = category_of.get(product)
        if category is None:
            continue
        total[category] = total.get(category, 0) + n
        if product in tops.get(category, ()):
            hit[category] = hit.get(category, 0) + n
    if not total:
        return 0.0
    return sum(hit.get(c, 0) / n for c, n in total.items()) / len(total)


def pick_prior_weight(
    before: Mapping[str, int],
    recent: Mapping[str, int],
    history_share: Mapping[str, float],
    category_of: Mapping[str, str],
    weights: tuple[float, ...] = PRIOR_WEIGHTS,
) -> tuple[float, dict[float, float]]:
    """A backtest: rank with the purchases `before` the tuning window under each weight, and keep the one
    whose top 10 caught most of the `recent` purchases. Ties go to the smaller weight."""
    scores = {
        weight: captured(
            category_ranking(before, history_share, category_of, weight, TOP),
            recent,
            category_of,
        )
        for weight in weights
    }
    return max(weights, key=lambda weight: scores[weight]), scores


class _LiveMapping(Mapping):
    """A read-only view of whatever mapping `read` returns now, so a version keeps one object for its life."""

    def __init__(self, read):
        self._read = read

    def __getitem__(self, key):
        return self._read()[key]

    def __iter__(self) -> Iterator:
        return iter(self._read())

    def __len__(self) -> int:
        return len(self._read())


class LiveCategoryRanking:
    """The category ranking, rebuilt from RawTree: the categories of every product (new ones included), the
    live purchases since the switch, and the history prior with its weight tuned on the last minutes."""

    def __init__(
        self,
        rawtree: RawTree,
        prior_weight: float | None = None,
        since_ms: int | None = None,
        now_ms=None,
    ) -> None:
        self.rawtree = rawtree
        self.fixed_weight = prior_weight
        """A weight to use always, instead of tuning one (None: tune)."""
        self.since_ms = since_ms
        self.now_ms = now_ms or rawtree.server_now_ms
        history = {
            row["product_id"]: int(row["n"])
            for row in rawtree.query(HISTORY_PURCHASES, timeout=60)
        }
        total = sum(history.values()) or 1
        self.history_share = {product: n / total for product, n in history.items()}
        self.prior_weight: float = START_PRIOR_WEIGHT
        self._snapshot: tuple[dict[str, str], dict[str, list[str]]] = ({}, {})
        self.refresh()

    def refresh(self) -> None:
        now = self.now_ms()
        since = self.since_ms if self.since_ms is not None else live_sales_since_ms(now)
        elapsed = max(now - since, 0)
        cut = now - min(TUNE_WINDOW_MS, elapsed // 2)
        category_of = {
            row["product_id"]: row["category"]
            for row in self.rawtree.query(CATALOG_CATEGORY, timeout=30)
        }
        rows = self.rawtree.query(
            LIVE_PURCHASES.format(since_ms=since, cut_ms=cut, now_ms=now), timeout=30
        )
        before = {row["product_id"]: int(row["before"]) for row in rows}
        recent = {row["product_id"]: int(row["recent"]) for row in rows}
        live = {product: before[product] + recent[product] for product in before}
        scores: dict[float, float] = {}
        if self.fixed_weight is not None:
            weight = self.fixed_weight
        elif elapsed < TUNE_FROM_MS or not any(recent.values()):
            weight = START_PRIOR_WEIGHT
        else:
            weight, scores = pick_prior_weight(
                before, recent, self.history_share, category_of
            )
        self.prior_weight = weight
        self._snapshot = (
            category_of,
            category_ranking(live, self.history_share, category_of, weight),
        )
        tuned = " ".join(f"{w:g}={s:.3f}" for w, s in scores.items()) or "not tuned"
        print(
            f"category ranking refreshed: prior weight {weight:g} ({tuned}), "
            f"{sum(live.values())} live purchases in {elapsed // 60_000} min",
            flush=True,
        )

    def signals(self) -> CategorySignals:
        """What `category_best_sellers` takes, like `category_signals`, but always the latest refresh."""
        return CategorySignals(
            category_of=_LiveMapping(lambda: self._snapshot[0]),
            ranked_by_category=_LiveMapping(lambda: self._snapshot[1]),
        )

    def start(self, every_s: float = REFRESH_S) -> "LiveCategoryRanking":
        """Refresh every `every_s` in a background thread, never on the answering path."""

        def run() -> None:
            while True:
                time.sleep(every_s)
                try:
                    self.refresh()
                except Exception as e:  # noqa: BLE001  keep the last ranking, try again next time
                    print(
                        f"category ranking refresh failed, keeping the last one: {str(e)[:160]}",
                        flush=True,
                    )

        threading.Thread(target=run, daemon=True).start()
        return self


def live_category_signals(
    rawtree: RawTree, prior_weight: float | None = None
) -> CategorySignals:
    """The live category ranking for any version, passed like `category_signals`:
    `category_best_sellers(**vars(live_category_signals(rawtree)), ...)`."""
    return LiveCategoryRanking(rawtree, prior_weight=prior_weight).start().signals()


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

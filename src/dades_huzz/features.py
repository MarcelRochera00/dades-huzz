"""Signals for ranking.

Lane B precomputes history signals in RawTree SQL and loads them once at start, and rebuilds the live
category ranking every minute from the purchases since the switch.
Lane C scores the live stream: a trend is the weighted count of `shop.events` over the last 15 minutes.
"""

import math
import threading
import time
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

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
        self.history_sales = history
        """Each product's purchases in the history (Lauri reads it)."""
        self.live_sales: dict[str, int] = {}
        """Each product's live purchases as of the last refresh (Lauri reads it)."""
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
        self.live_sales = live
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

    def live_sales_now(self) -> Mapping[str, int]:
        """Each product's live purchases, always as of the latest refresh."""
        return _LiveMapping(lambda: self.live_sales)

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


LAURI_FEATURES = (
    "viewed",
    "view_recency",
    "same_category",
    "same_subcategory",
    "session_category_share",
    "profile_share",
    "favourite_category",
    "log_history_sales",
    "session_history_sales",
    "viewed_history_sales",
    "log_live_sales",
    "log_price",
    "relative_price",
    "day_category_share",
    "day_carted",
    "day_viewed",
    "day_history_sales",
)
"""What Lauri knows about one candidate for one request, in the order of the columns of `lauri_features`.
`session_history_sales` and `viewed_history_sales` are the history sales counted only as far as the product is
in a category of the session, or was viewed: in our own carousels a best seller is bought far more often than
a slow seller, and most of all when the shopper viewed it (docs/experiments.md row 44).

New features go at the end, never in between: weights stored earlier (Lauri Titan's thirteen) stay valid and
count the later features as zero."""

LAURI_DAY_FEATURES = LAURI_FEATURES[-4:]
"""What Lauri Colossus adds, from the shopper's day (`LauriDay`): the category's share of today's views, the
product is in today's cart, the product was viewed today, and the history sales counted as far as that share."""
DAY_CART_WEIGHT = 3
DAY_VIEWED_MAX = 20
"""As the serving loop keeps a shopper's day in `State` (docs/contracts.md): an add-to-cart counts three views
of its category, and the last twenty distinct products viewed are kept."""
DAY_LAG_MS = 10_000
"""Training sees a shopper's day only up to this long before the request: live, `State` runs a few seconds
behind `shop.events`, so a training row must not know more than a live one would."""


@dataclass(frozen=True)
class LauriDay:
    """One shopper's day so far in `shop.events`, as `State` keeps it (`shopper_categories`, `shopper_carted`,
    `shopper_viewed`)."""

    categories: Mapping[str, int]
    """Category to views today; an add-to-cart counts DAY_CART_WEIGHT."""
    carted: AbstractSet[str]
    """Products carted today and not bought since."""
    viewed: Sequence[str]
    """The last DAY_VIEWED_MAX distinct products viewed today, latest first."""


@dataclass(frozen=True)
class LauriSignals:
    """What `lauri_features` reads about products. Training passes them as they stood before each request;
    serving passes the live ones."""

    category: Mapping[str, str]
    subcategory: Mapping[str, str]
    price: Mapping[str, float]
    history_sales: Mapping[str, int]
    live_sales: Mapping[str, int]
    median_log_price: Mapping[str, float]
    """Each category's median log price, so a product can be cheap or dear for its category."""


def median_log_prices(
    category: Mapping[str, str], price: Mapping[str, float]
) -> dict[str, float]:
    logs: dict[str, list[float]] = {}
    for product, name in category.items():
        if price.get(product, 0) > 0:
            logs.setdefault(name, []).append(math.log(price[product]))
    return {name: float(np.median(values)) for name, values in logs.items()}


def lauri_features(
    products: Sequence[str],
    viewed: Sequence[str],
    profile: Mapping[str, float] | None,
    signals: LauriSignals,
    day: LauriDay | None = None,
) -> np.ndarray:
    """One row of LAURI_FEATURES per product, for a shopper who viewed `viewed` (oldest first), whose
    shopper profile is `profile` and whose day so far is `day` (without it the day's features are zero).
    The same function builds the training rows and the live ones."""
    day_views = sum(day.categories.values()) if day else 0
    day_viewed = frozenset(day.viewed) if day else frozenset()
    category, subcategory = signals.category, signals.subcategory
    recency = {product: len(viewed) - i for i, product in enumerate(viewed)}
    last_category = category.get(viewed[-1]) if viewed else None
    last_subcategory = subcategory.get(viewed[-1]) if viewed else None
    session = Counter(category[p] for p in viewed if p in category)
    views = sum(session.values())
    profile = profile or {}
    favourite = (
        max(profile, key=lambda name: (profile[name], name)) if profile else None
    )
    rows = np.zeros((len(products), len(LAURI_FEATURES)))
    for row, product in zip(rows, products, strict=True):
        name = category.get(product)
        if name is None:
            continue
        price = signals.price.get(product, 0.0)
        log_price = (
            math.log(price) if price > 0 else signals.median_log_price.get(name, 0.0)
        )
        sales = math.log1p(signals.history_sales.get(product, 0))
        share = session[name] / views if views else 0.0
        day_share = day.categories.get(name, 0) / day_views if day_views else 0.0
        row[:] = (
            product in recency,
            1 / recency[product] if product in recency else 0.0,
            name == last_category,
            last_subcategory is not None
            and subcategory.get(product) == last_subcategory,
            share,
            profile.get(name, 0.0),
            name == favourite,
            sales,
            sales * share,
            sales * (product in recency),
            math.log1p(signals.live_sales.get(product, 0)),
            log_price,
            log_price - signals.median_log_price.get(name, log_price),
            day_share,
            day is not None and product in day.carted,
            product in day_viewed,
            sales * day_share,
        )
    return rows


LAURI_FEEDBACK = """
SELECT f.request_id::String AS request_id, toUnixTimestamp64Milli(f.ts::DateTime64(3)) AS ts_ms,
       f.shown AS shown, f.purchased::String AS purchased, f.clicked::String AS clicked,
       r.user_id::String AS user_id, r.is_new_user::Bool AS is_new_user, r.recent_views AS recent_views,
       toUnixTimestamp64Milli(r.ts::DateTime64(3)) AS request_ms
FROM {team}.feedback AS f
INNER JOIN shop.requests AS r ON f.request_id::String = r.request_id::String
WHERE f.served_by::String = 'team' AND f.request_id::String != '__init__'
  AND cityHash64(f.request_id::String) % {parts} = {part}"""
"""Our own answers with what happened and who saw them, one part at a time (the whole is a large reply)."""

LIVE_PURCHASE_TIMES = """
SELECT product_id::String AS product_id, user_id::String AS user_id,
       toUnixTimestamp64Milli(ts::DateTime64(3)) AS ts_ms
FROM shop.events
WHERE event_type::String = 'purchase' AND ts::DateTime64(3) >= '{since}'
ORDER BY ts_ms"""

DAY_EVENTS = """
SELECT user_id::String AS u, product_id::String AS p, event_type::String AS e,
       toUnixTimestamp64Milli(ts::DateTime64(3)) AS t
FROM shop.events
WHERE cityHash64(user_id::String) % {parts} = {part}
  AND user_id::String IN (
      SELECT r.user_id::String FROM {team}.feedback AS f
      INNER JOIN shop.requests AS r ON f.request_id::String = r.request_id::String
      WHERE f.served_by::String = 'team')"""
"""Every event of the shoppers we answered, one part at a time, to rebuild their day before each request."""

LIVE_SALES_STEP_MS = 10 * 60_000
"""Training counts a product's live sales up to the last ten-minute mark before the request: serving
refreshes them every minute, so a training row must not know more than a live one would."""


class _SalesBefore(Mapping):
    """Each product's live purchases before `cut_ms`, read from its sorted purchase times."""

    def __init__(self, times: Mapping[str, np.ndarray], cut_ms: int) -> None:
        self.times, self.cut_ms = times, cut_ms

    def __getitem__(self, product: str) -> int:
        return int(np.searchsorted(self.times[product], self.cut_ms))

    def __iter__(self) -> Iterator:
        return iter(self.times)

    def __len__(self) -> int:
        return len(self.times)


class DayReplay:
    """One shopper's events (time, kind, product), replayed up to each of their requests into a `LauriDay`,
    counted as the serving loop counts them."""

    def __init__(self, events: Iterable[tuple[int, str, str]]) -> None:
        self.events = sorted(events)
        self._restart()

    def _restart(self) -> None:
        self.next, self.cut_ms = 0, 0
        self.categories: dict[str, int] = {}
        self.carted: set[str] = set()
        self.viewed: list[str] = []

    def until(self, cut_ms: int, category: Mapping[str, str]) -> LauriDay:
        """The day before `cut_ms`. The result is only valid until the next call."""
        if cut_ms < self.cut_ms:
            self._restart()
        self.cut_ms = cut_ms
        while self.next < len(self.events) and self.events[self.next][0] < cut_ms:
            _, kind, product = self.events[self.next]
            self.next += 1
            if kind != "purchase" and (name := category.get(product)):
                weight = DAY_CART_WEIGHT if kind == "add_to_cart" else 1
                self.categories[name] = self.categories.get(name, 0) + weight
            if kind == "view":
                if product in self.viewed:
                    self.viewed.remove(product)
                self.viewed.insert(0, product)
                del self.viewed[DAY_VIEWED_MAX:]
            elif kind == "add_to_cart":
                self.carted.add(product)
            elif kind == "purchase":
                self.carted.discard(product)
        return LauriDay(self.categories, self.carted, self.viewed)


def shopper_day_replays(rawtree: RawTree, parts: int = 16) -> dict[str, DayReplay]:
    """A replay of the day of every shopper we answered, read from `shop.events`."""
    events: dict[str, list[tuple[int, str, str]]] = {}
    for part in range(parts):
        sql = DAY_EVENTS.format(team=rawtree.team, parts=parts, part=part)
        for row in rawtree.query(sql, timeout=120):
            events.setdefault(row["u"], []).append((row["t"], row["e"], row["p"]))
    return {user: DayReplay(rows) for user, rows in events.items()}


@dataclass(frozen=True)
class LauriTrainingRows:
    """Our own carousels as training rows: ten per answered request, in the order shown."""

    features: np.ndarray
    slot: np.ndarray
    owned: np.ndarray
    """The shopper had already bought the product: known only to explain the past, never served."""
    purchased: np.ndarray
    clicked: np.ndarray
    request: np.ndarray
    ts_ms: np.ndarray
    is_new_user: np.ndarray


def lauri_training_rows(rawtree: RawTree, parts: int = 8) -> LauriTrainingRows:
    """Every product we showed, with LAURI_FEATURES as they stood before its request, and what happened."""
    feedback = [
        row
        for part in range(parts)
        for row in rawtree.query(
            LAURI_FEEDBACK.format(team=rawtree.team, parts=parts, part=part),
            timeout=120,
        )
    ]
    feedback.sort(key=lambda row: row["ts_ms"])
    catalog = rawtree.catalog()
    category = {row["product_id"]: row["category"] for row in catalog}
    subcategory = {row["product_id"]: row["subcategory"] for row in catalog}
    price = {row["product_id"]: float(row["price_eur"]) for row in catalog}
    history = {
        row["product_id"]: int(row["n"])
        for row in rawtree.query(HISTORY_PURCHASES, timeout=60)
    }
    times: dict[str, list[int]] = {}
    bought_live: dict[str, list[tuple[int, str]]] = {}
    for row in rawtree.query(
        LIVE_PURCHASE_TIMES.format(since=PRACTICE_ROUND_START), timeout=120
    ):
        times.setdefault(row["product_id"], []).append(row["ts_ms"])
        bought_live.setdefault(row["user_id"], []).append(
            (row["ts_ms"], row["product_id"])
        )
    sale_times = {product: np.array(moments) for product, moments in times.items()}
    profiles = shopper_profiles(rawtree, until=PRACTICE_ROUND_START)
    bought = shopper_purchases(rawtree, until=PRACTICE_ROUND_START)
    medians = median_log_prices(category, price)
    days = shopper_day_replays(rawtree)
    features, owned = [], []
    for row in feedback:
        cut = row["ts_ms"] - row["ts_ms"] % LIVE_SALES_STEP_MS
        signals = LauriSignals(
            category,
            subcategory,
            price,
            history,
            _SalesBefore(sale_times, cut),
            medians,
        )
        viewed = [view["product_id"] for view in row["recent_views"] or []]
        user = row["user_id"]
        day = (
            days[user].until(row["request_ms"] - DAY_LAG_MS, category)
            if user in days
            else None
        )
        features.append(
            lauri_features(row["shown"], viewed, profiles.get(user), signals, day)
        )
        mine = set(bought.get(user, ())) | {
            product
            for moment, product in bought_live.get(user, ())
            if moment < row["ts_ms"]
        }
        owned.append([product in mine for product in row["shown"]])
    shown = [row["shown"] for row in feedback]
    return LauriTrainingRows(
        features=np.concatenate(features),
        slot=np.concatenate([np.arange(len(items)) for items in shown]),
        owned=np.concatenate(owned).astype(float),
        purchased=np.array(
            [
                p == row["purchased"]
                for row, items in zip(feedback, shown, strict=True)
                for p in items
            ],
            dtype=float,
        ),
        clicked=np.array(
            [
                p == row["clicked"]
                for row, items in zip(feedback, shown, strict=True)
                for p in items
            ],
            dtype=float,
        ),
        request=np.concatenate(
            [np.full(len(items), i) for i, items in enumerate(shown)]
        ),
        ts_ms=np.concatenate(
            [
                np.full(len(items), row["ts_ms"])
                for row, items in zip(feedback, shown, strict=True)
            ]
        ),
        is_new_user=np.concatenate(
            [
                np.full(len(items), bool(row["is_new_user"]))
                for row, items in zip(feedback, shown, strict=True)
            ]
        ),
    )

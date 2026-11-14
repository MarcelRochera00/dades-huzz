"""Reading and writing RawTree: the live stream, the current catalogue and our answers."""

import os
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

Record = dict[str, Any]
"""RawTree returns rows as JSON objects: {"column": value, ...}"""


@dataclass(frozen=True)
class State:
    """What the serving loop keeps fresh and passes, read-only, to every `recommend` (docs/contracts.md).

    The catalogue right now is shop.catalog with every shop.catalog_updates record applied in time order.
    """

    available: frozenset[str]
    """Products an answer may contain: active and not out of stock."""
    price: dict[str, float]
    new_products: frozenset[str]
    """Products added during the event: a request that viewed one is a cold request."""
    fallback: tuple[str, ...]
    """The all-time best sellers that are available, best first, then every other available product: the
    baseline, and what pads a short answer, even with a catalogue of products that never sold."""
    category: dict[str, str] = field(default_factory=dict)
    """Every product's category, including the products added during the event, as soon as the loop sees them."""
    subcategory: dict[str, str] = field(default_factory=dict)
    """Every product's subcategory, like `category`."""
    trend: dict[str, int] = field(default_factory=dict)
    """Product weight in `shop.events` over the last 15 minutes: purchase 4, add-to-cart 3, view 1."""
    recent_purchases: dict[str, frozenset[str]] = field(default_factory=dict)
    """Shopper to the products they purchased in that same window. An answer leaves those out."""


def current_state(
    catalog: Iterable[Record], updates: Iterable[Record], best_sellers: Iterable[str]
) -> State:
    active: dict[str, bool] = {}
    price: dict[str, float] = {}
    out_of_stock: set[str] = set()
    new: set[str] = set()
    category: dict[str, str] = {}
    subcategory: dict[str, str] = {}

    def classify(row: Record) -> None:
        if row.get("category"):
            category[row["product_id"]] = row["category"]
        if row.get("subcategory"):
            subcategory[row["product_id"]] = row["subcategory"]

    for row in catalog:
        active[row["product_id"]] = bool(row["is_active"])
        price[row["product_id"]] = float(row["price_eur"])
        classify(row)
    for row in sorted(updates, key=lambda r: str(r["ts"])):
        product = row["product_id"]
        classify(row)
        if row.get("is_active") is not None:
            active[product] = bool(row["is_active"])
        if (
            row.get("price_eur") is not None
        ):  # one malformed update must not stop every later refresh
            price[product] = float(row["price_eur"])
        if row["change"] == "out_of_stock":
            out_of_stock.add(product)
        elif row["change"] == "back_in_stock":
            out_of_stock.discard(product)
        elif row["change"] == "new_product":
            new.add(product)
    available = frozenset(
        p for p, is_active in active.items() if is_active and p not in out_of_stock
    )
    ranked = [p for p in dict.fromkeys(best_sellers) if p in available]
    fallback = (*ranked, *sorted(available - set(ranked)))
    return State(available, price, frozenset(new), fallback, category, subcategory)


STOCK_CHANGES = ("out_of_stock", "back_in_stock")


def recently_changed(
    updates: Iterable[Record], now_ms: int, window_ms: int
) -> frozenset[str]:
    """Products whose stock changed (out or back) in the last `window_ms`.

    The organisers judge an answer against the stock at the request's own time, and we answer about a second
    later. Around a change, a product is valid for some requests and not for others, so the loop does not
    recommend it at all for `window_ms`. A product that came back just now was still out of stock for a
    request made a moment earlier. Changes stamped after `now_ms` count too: our clock may be a little
    behind RawTree's. Why 10 s and when to revisit it: issue #14.
    """
    return frozenset(
        row["product_id"]
        for row in updates
        if row["change"] in STOCK_CHANGES and row["ts_ms"] > now_ms - window_ms
    )


class UpdateLog:
    """Every shop.catalog_updates record seen so far, read incrementally: each read asks only for updates
    from a little before the newest one we have, so the reads stay small as the table grows all weekend."""

    def __init__(self, overlap_ms: int) -> None:
        self.overlap_ms = overlap_ms
        """Read again this far back, in case an update lands in the table after a newer one."""
        self.rows: list[Record] = []
        self._keys: set[tuple[str, int, str, float | None]] = set()

    def since_ms(self, now_ms: int) -> int:
        """Where the next read starts: `overlap_ms` before the newest update, but never later than `now_ms`
        minus `overlap_ms`, so an update stamped in the future cannot hide older ones that land late."""
        newest = max((row["ts_ms"] for row in self.rows), default=None)
        return 0 if newest is None else min(newest, now_ms) - self.overlap_ms

    def add(self, rows: Iterable[Record]) -> list[Record]:
        """Keep the rows not seen before and return them."""
        new = []
        for row in rows:
            key = (row["product_id"], row["ts_ms"], row["change"], row.get("price_eur"))
            if key not in self._keys:
                self._keys.add(key)
                self.rows.append(row)
                new.append(row)
        return new


def as_request(row: Record) -> Record:
    """A shop.requests row in the contract's shape: `context` nested, as the brief shows it.

    RawTree returns the context as flat `context.device`-style columns; `ts_ms` is added for the deadline.
    """
    return {
        "request_id": row["request_id"],
        "ts": row["ts"],
        "ts_ms": row["ts_ms"],
        "user_id": row["user_id"],
        "is_new_user": row["is_new_user"],
        "context": {
            "device": row["device"],
            "region": row["region"],
            "page": row["page"],
        },
        "recent_views": row["recent_views"] or [],
    }


class RequestCursor:
    """Which polled requests are new and still answerable in time.

    Every poll asks for all requests younger than `max_age_ms`, so one that lands in the table late or out of
    order is still seen; the cursor remembers what it already returned so each request is answered once.
    """

    def __init__(self, max_age_ms: int) -> None:
        self.max_age_ms = max_age_ms
        self.skipped = 0
        """Requests seen too late to answer in time."""
        self._seen: dict[str, int] = {}

    def since_ms(self, now_ms: int) -> int:
        return now_ms - self.max_age_ms

    def mark_answered(self, request_ids: Iterable[str], now_ms: int) -> None:
        """Requests another loop already answered: never answer them again."""
        for request_id in request_ids:
            self._seen.setdefault(request_id, now_ms)

    def accept(self, rows: Iterable[Record], now_ms: int) -> list[Record]:
        fresh = []
        for row in sorted(rows, key=lambda r: r["ts_ms"]):
            if row["request_id"] in self._seen:
                continue
            self._seen[row["request_id"]] = row["ts_ms"]
            if now_ms - row["ts_ms"] > self.max_age_ms:
                self.skipped += 1
            else:
                fresh.append(row)
        horizon = now_ms - 10 * self.max_age_ms
        self._seen = {r: ts for r, ts in self._seen.items() if ts >= horizon}
        return fresh


REQUESTS_SINCE = """
SELECT request_id::String AS request_id, toString(ts::DateTime64(3)) AS ts,
       toUnixTimestamp64Milli(ts::DateTime64(3)) AS ts_ms,
       user_id::String AS user_id, is_new_user::Bool AS is_new_user, `context.device`::String AS device,
       `context.region`::String AS region, `context.page`::String AS page, recent_views
FROM shop.requests
WHERE ts::DateTime64(3) > fromUnixTimestamp64Milli(toInt64({since_ms}))"""

CATALOG = """
SELECT product_id::String AS product_id, price_eur::Float64 AS price_eur, is_active::Bool AS is_active,
       category::String AS category, subcategory::String AS subcategory
FROM shop.catalog"""

CATALOG_UPDATES_SINCE = """
SELECT product_id::String AS product_id, change::String AS change, toString(ts) AS ts,
       toUnixTimestamp64Milli(ts::DateTime64(3)) AS ts_ms, price_eur::Float64 AS price_eur,
       is_active::Bool AS is_active, category::String AS category, subcategory::String AS subcategory
FROM shop.catalog_updates
WHERE ts::DateTime64(3) >= fromUnixTimestamp64Milli(toInt64({since_ms}))"""

HEARTBEATS_SINCE = """
SELECT loop_id::String AS loop_id, host::String AS host, role::String AS role,
       started_ms::Int64 AS started_ms, ts_ms::Int64 AS ts_ms
FROM {team}.scratch
WHERE kind::String = 'heartbeat' AND ts_ms::Int64 > {since_ms}"""

ANSWERED_SINCE = """
SELECT DISTINCT s.request_id::String AS request_id
FROM {team}.submissions AS s
INNER JOIN (SELECT request_id::String AS request_id FROM shop.requests
            WHERE ts::DateTime64(3) > fromUnixTimestamp64Milli(toInt64({since_ms}))) AS r
    ON r.request_id = s.request_id::String"""
"""Requests since `since_ms` that some loop of ours already answered."""

BEST_SELLERS = """
SELECT product_id::String AS product_id, count() AS n
FROM shop.history_events
WHERE event_type = 'purchase'
GROUP BY product_id
ORDER BY n DESC, product_id DESC"""
"""Every product ever bought in the history, best-selling first: the organisers' baseline ranking."""

RECENT_EVENTS = """
SELECT
    ts::DateTime64(3) AS ts,
    event_type::String AS event_type,
    product_id::String AS product_id,
    user_id::String AS user_id
FROM shop.events
WHERE ts::DateTime64(3) > now() - INTERVAL 15 MINUTE"""
"""Organic events in the trend window: views, add-to-cart and purchases."""


class RawTree:
    """The RawTree HTTP API for one team: read anything the key can see, write into our own database."""

    def __init__(
        self, team: str, api_key: str, url: str = "https://api.rawtree.com"
    ) -> None:
        self.team = team
        self.url = url
        self.http = requests.Session()
        self.http.headers["Authorization"] = f"Bearer {api_key}"

    @classmethod
    def from_env(cls, env_file: Path = Path(".env")) -> "RawTree":
        """Credentials from the environment, or from `.env` (never committed)."""
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())
        return cls(
            os.environ["TEAM_ID"],
            os.environ["RAWTREE_API_KEY"],
            os.environ.get("RAWTREE_API_URL", "https://api.rawtree.com"),
        )

    def query(self, sql: str, timeout: float = 10) -> list[Record]:
        response = self.http.post(
            f"{self.url}/v1/query", json={"sql": sql}, timeout=timeout
        )
        response.raise_for_status()
        return response.json()["data"]

    def insert(self, table: str, rows: list[Record], timeout: float = 2) -> None:
        """Insert into our own database. Retried only when rate limited: the rows were then surely not written,
        while retrying after a timeout could answer the same request twice."""
        for attempt in range(2):
            response = self.http.post(
                f"{self.url}/v1/tables/{table}",
                params={"database": self.team},
                json=rows,
                timeout=timeout,
            )
            if response.status_code == 429 and attempt == 0:
                time.sleep(min(float(response.headers.get("retry-after", 0.2)), 0.5))
                continue
            response.raise_for_status()
            return

    def requests_since(self, since_ms: int) -> list[Record]:
        # A stuck read is dropped after 1 s and retried at the next poll, while its requests can still be
        # answered in time; waiting 2 s let them age past MAX_AGE_MS.
        rows = self.query(REQUESTS_SINCE.format(since_ms=int(since_ms)), timeout=1)
        return [as_request(row) for row in rows]

    def catalog(self) -> list[Record]:
        return self.query(CATALOG)

    def catalog_updates_since(self, since_ms: int) -> list[Record]:
        return self.query(
            # Like request reads: give up after 1 s and retry, rather than freeze stock tracking for 5 s.
            CATALOG_UPDATES_SINCE.format(since_ms=int(since_ms)),
            timeout=1,
        )

    def heartbeats_since(self, since_ms: int) -> list[Record]:
        return self.query(
            HEARTBEATS_SINCE.format(team=self.team, since_ms=int(since_ms)), timeout=2
        )

    def answered_since(self, since_ms: int) -> set[str]:
        rows = self.query(
            ANSWERED_SINCE.format(team=self.team, since_ms=int(since_ms)), timeout=2
        )
        return {row["request_id"] for row in rows}

    def server_now_ms(self) -> int:
        return int(
            self.query("SELECT toUnixTimestamp64Milli(now64(3)) AS now_ms")[0]["now_ms"]
        )

    def recent_events(self) -> list[Record]:
        """Organic events in the last 15 minutes. Empty until the live stream has rows."""
        return self.query(RECENT_EVENTS, timeout=2)

    def best_sellers(self) -> list[str]:
        return [row["product_id"] for row in self.query(BEST_SELLERS, timeout=30)]

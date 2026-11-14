"""The version split: which recommenders answer live, and which requests each one gets.

Every request goes to one version, chosen from a fingerprint of its `request_id`, so the same request gets
the same version on any laptop and after any restart. The answer carries the version that produced it as
`model_version`, so the serving report compares versions on the same stream, side by side.

The first version listed is the champion (GLOSSARY.md): it answers in the loop itself. Every other version is
a challenger, with a time limit per request. A challenger that misses it or raises gives way to the champion
for that shopper. A challenger slow on average is taken out for OUT_FOR_MS, also across restarts and
laptops. One that cannot load is left out, and the champion answers its share.

To add a version, add one line to VERSIONS (a lane A file: open a PR, lane A confirms). Choose which run and
their shares with `run_recommender.py --versions name=share,...`, champion first.
"""

import hashlib
import math
import threading
import time
import tracemalloc
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime

from dades_huzz.data import RawTree, Record, State
from dades_huzz.features import (
    LiveCategoryRanking,
    category_signals,
    live_category_signals,
    median_log_prices,
    shopper_profiles,
    shopper_purchases,
)
from dades_huzz.model import (
    best_sellers,
    category_best_sellers,
    lauri,
    load_lauri_weights,
    subcategory_first,
)
from dades_huzz.serving.loop import Recommend


def _apocalypse(rawtree: RawTree, viewed_first: int = 0) -> Recommend:
    """Tati Apocalypse: Terminator plus each returning shopper's favourite categories from their history,
    never showing what they already bought.
    With `viewed_first=3`, Tati Armageddon: Ultimatum's viewed products on top of Apocalypse."""
    until = f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S}"
    return category_best_sellers(
        **vars(category_signals(rawtree, until=until)),
        keep_viewed=True,
        viewed_first=viewed_first,
        profiles=shopper_profiles(rawtree, until=until),
        bought=shopper_purchases(rawtree, until=until),
    )


def _subcategory_first_live(rawtree: RawTree) -> Recommend:
    """Terminator with the live category ranking (#38), and for a new shopper with views the two best sellers
    of the subcategory they viewed last on top."""
    signals = live_category_signals(rawtree)
    return subcategory_first(
        category_best_sellers(**vars(signals), keep_viewed=True),
        signals.ranked_by_category,
        signals.category_of,
    )


def _omega(rawtree: RawTree) -> Recommend:
    """Tati Omega: Apocalypse (favourite categories, never what was bought) on the live category ranking
    (#38), and for a new shopper with views the subcategory viewed last first (#46)."""
    until = f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S}"
    signals = live_category_signals(rawtree)
    return subcategory_first(
        category_best_sellers(
            **vars(signals),
            keep_viewed=True,
            profiles=shopper_profiles(rawtree, until=until),
            bought=shopper_purchases(rawtree, until=until),
        ),
        signals.ranked_by_category,
        signals.category_of,
    )


def _lauri(rawtree: RawTree, name: str) -> Recommend:
    """Lauri Titan: the weights last trained under `name` (scripts/train_lauri.py), scoring the live category
    ranking's products with each shopper's profile, and never showing what they bought."""
    weights = load_lauri_weights(rawtree, name)
    until = f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S}"
    ranking = LiveCategoryRanking(rawtree).start()
    catalog = rawtree.catalog()
    return lauri(
        weights,
        ranked_by_category=ranking.signals().ranked_by_category,
        history_sales=ranking.history_sales,
        live_sales=ranking.live_sales_now(),
        median_log_price=median_log_prices(
            {row["product_id"]: row["category"] for row in catalog},
            {row["product_id"]: float(row["price_eur"]) for row in catalog},
        ),
        profiles=shopper_profiles(rawtree, until=until),
        bought=shopper_purchases(rawtree, until=until),
    )


VERSIONS: dict[str, Callable[[RawTree], Recommend]] = {
    "tati-0-bestsellers": lambda rawtree: best_sellers,
    "tati-destroyer-category": lambda rawtree: category_best_sellers(
        **vars(
            category_signals(rawtree, until=f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S}")
        )
    ),
    "tati-terminator-category-viewed": lambda rawtree: category_best_sellers(
        **vars(
            category_signals(rawtree, until=f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S}")
        ),
        keep_viewed=True,
    ),
    "tati-ultimatum-viewed-first": lambda rawtree: category_best_sellers(
        **vars(
            category_signals(rawtree, until=f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S}")
        ),
        keep_viewed=True,
        viewed_first=3,
    ),
    "tati-ultimatum-cold": lambda rawtree: category_best_sellers(
        **vars(
            category_signals(rawtree, until=f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S}")
        ),
        keep_viewed=True,
        viewed_first=3,
        cold_start=True,
    ),
    "tati-terminator-category-viewed-live": lambda rawtree: category_best_sellers(
        **vars(live_category_signals(rawtree)), keep_viewed=True
    ),
    "tati-terminator-live-subcat": lambda rawtree: _subcategory_first_live(rawtree),
    "tati-terminator-live-cold": lambda rawtree: category_best_sellers(
        **vars(live_category_signals(rawtree)), keep_viewed=True, cold_start=True
    ),
    "tati-omega-live-profile": lambda rawtree: _omega(rawtree),
    "tati-apocalypse-profile": lambda rawtree: _apocalypse(rawtree),
    "tati-armageddon-viewed-profile": lambda rawtree: _apocalypse(
        rawtree, viewed_first=3
    ),
    "lauri-titan-feedback": lambda rawtree: _lauri(rawtree, "lauri-titan-feedback"),
}
"""Every version that can run live, by name: a function that loads what it needs and returns its recommend."""

DEFAULT_SPLIT = "tati-terminator-category-viewed=100"
BUDGET_MS = 200.0
"""docs/contracts.md: about 200 ms per request. A challenger gets this long per request."""
WINDOW = 20
"""A challenger whose last WINDOW requests average over budget is taken out."""
OUT_FOR_MS = 30 * 60_000
"""How long a take-out lasts; then the version gets another chance (the time limit caps what it costs)."""
MAX_PENDING = 20
"""A challenger with this many calls still running (hung) is not called again: it times out at once."""
LOAD_ATTEMPTS = 3

TAKE_OUTS = """
SELECT version::String AS version, max(until_ms::Int64) AS until_ms
FROM {team}.scratch
WHERE kind::String = 'version_out' AND until_ms::Int64 > {now_ms}
GROUP BY version"""


def wall_ms() -> int:
    return int(time.time() * 1000)


def parse_split(text: str) -> dict[str, int]:
    """'a=50,b=50' -> {'a': 50, 'b': 50}. Shares are positive whole numbers; their total need not be 100."""
    shares: dict[str, int] = {}
    for part in text.split(","):
        name, sep, share = part.partition("=")
        name = name.strip()
        if not sep or not name or not share.strip().isdigit() or int(share) <= 0:
            raise ValueError(f"expected name=positive_share, got {part!r} in {text!r}")
        if name in shares:
            raise ValueError(f"{name!r} appears twice in {text!r}")
        shares[name] = int(share)
    return shares


class Split:
    """Assigns requests to versions by share, runs challengers under a time limit, and takes out a slow one."""

    def __init__(
        self,
        recommenders: dict[str, Recommend],
        shares: dict[str, int],
        budget_ms: float = BUDGET_MS,
        out_until_ms: dict[str, float] | None = None,
        on_take_out: Callable[[str, int], None] = lambda name, until_ms: None,
    ) -> None:
        self.recommenders = recommenders
        self.shares = shares
        self.champion = next(iter(shares))
        self.budget_ms = budget_ms
        self.out_until_ms: dict[str, float] = dict(out_until_ms or {})
        self.on_take_out = on_take_out
        self._times: dict[str, deque[float]] = {
            name: deque(maxlen=WINDOW) for name in shares
        }
        self._pending: dict[str, list[threading.Thread]] = {name: [] for name in shares}

    def taken_out(self, now_ms: int | None = None) -> set[str]:
        now = now_ms if now_ms is not None else wall_ms()
        return {name for name, until in self.out_until_ms.items() if until > now}

    def describe(self) -> str:
        """The split as `--versions` takes it, champion first: 'a=50,b=50'."""
        return ",".join(f"{name}={share}" for name, share in self.shares.items())

    def version_for(self, request_id: str, now_ms: int | None = None) -> str:
        """Deterministic: a sha256 fingerprint of the id, not Python's hash(), which changes per process."""
        point = int.from_bytes(
            hashlib.sha256(request_id.encode()).digest()[:8], "big"
        ) % sum(self.shares.values())
        for name, share in self.shares.items():
            if point < share:
                return self.champion if name in self.taken_out(now_ms) else name
            point -= share
        raise AssertionError("unreachable: point < total share")

    def recommend(
        self, request: Record, state: State
    ) -> tuple[str, list[str], str | None]:
        """(version that answered, its items, problem). A challenger that times out or raises gives way to the
        champion, and the problem says so ('timeout:name', 'model_error:name')."""
        version = self.version_for(request["request_id"])
        if version == self.champion:
            started = time.perf_counter()
            items = self.recommenders[version](request, state)
            self.record(version, (time.perf_counter() - started) * 1000)
            return version, items, None
        items, problem = self._call_with_limit(version, request, state)
        if problem:
            return (
                self.champion,
                self.recommenders[self.champion](request, state),
                f"{problem}:{version}",
            )
        return version, items, None

    def _call_with_limit(
        self, version: str, request: Record, state: State
    ) -> tuple[list[str], str | None]:
        pending = self._pending[version] = [
            t for t in self._pending[version] if t.is_alive()
        ]
        if len(pending) >= MAX_PENDING:
            self.record(version, self.budget_ms * 2)
            return [], "timeout"
        box: dict[str, object] = {}

        def run() -> None:
            try:
                box["items"] = self.recommenders[version](request, state)
            except Exception as e:  # noqa: BLE001  reported to the caller as model_error
                box["error"] = e

        started = time.perf_counter()
        thread = threading.Thread(
            target=run, daemon=True
        )  # daemon: a hung model never blocks exit
        thread.start()
        thread.join(self.budget_ms / 1000)
        self.record(version, (time.perf_counter() - started) * 1000)
        if thread.is_alive():
            pending.append(thread)
            return [], "timeout"
        if "error" in box:
            print(f"version {version} raised: {box['error']!r}", flush=True)
            return [], "model_error"
        return box["items"], None  # type: ignore[return-value]

    def record(self, name: str, elapsed_ms: float, now_ms: int | None = None) -> None:
        """Note how long `name` took for one request; take it out if its recent average is over budget."""
        now = now_ms if now_ms is not None else wall_ms()
        times = self._times[name]
        times.append(elapsed_ms)
        average = sum(times) / len(times)
        if name == self.champion or len(times) < WINDOW or average <= self.budget_ms:
            return
        if name not in self.taken_out(now):
            until = now + OUT_FOR_MS
            self.out_until_ms[name] = until
            times.clear()
            print(
                f"version {name} taken out for {OUT_FOR_MS // 60_000} min: {average:.0f} ms per request on average"
                f" (budget {self.budget_ms:.0f}); the champion {self.champion} answers its share",
                flush=True,
            )
            self.on_take_out(name, until)


def load_split(rawtree: RawTree, shares: dict[str, int], load: Callable) -> Split:
    """Load every version in `shares`. The champion is retried until it loads (`load(fn, what)`); a challenger
    gets LOAD_ATTEMPTS tries and is otherwise left out. Take-outs still running from before are kept."""
    unknown = set(shares) - set(VERSIONS)
    if unknown:
        raise ValueError(
            f"unknown versions {sorted(unknown)}; known: {sorted(VERSIONS)}"
        )
    champion = next(iter(shares))
    recommenders = {
        champion: load(lambda: VERSIONS[champion](rawtree), f"champion {champion}")
    }
    out_until_ms: dict[str, float] = {}
    for name in list(shares)[1:]:
        for attempt in range(1, LOAD_ATTEMPTS + 1):
            try:
                recommenders[name] = VERSIONS[name](rawtree)
                break
            except Exception as e:  # noqa: BLE001  a broken challenger must not stop the champion serving
                print(
                    f"loading version {name} failed ({attempt}/{LOAD_ATTEMPTS}): {e}",
                    flush=True,
                )
                time.sleep(2)
        else:
            print(
                f"version {name} left out: it did not load; the champion {champion} answers its share",
                flush=True,
            )
            out_until_ms[name] = math.inf
    try:
        for row in rawtree.query(
            TAKE_OUTS.format(team=rawtree.team, now_ms=wall_ms()), timeout=5
        ):
            if row["version"] in shares and row["version"] != champion:
                out_until_ms.setdefault(row["version"], row["until_ms"])
                print(
                    f"version {row['version']} still taken out from before, until {row['until_ms']}",
                    flush=True,
                )
    except Exception as e:  # noqa: BLE001  none recorded yet (the columns do not exist) or RawTree is slow
        print(f"could not read earlier take-outs: {str(e)[:120]}", flush=True)

    def remember(
        name: str, until_ms: int
    ) -> None:  # in the background: never on the answering path
        row = {
            "kind": "version_out",
            "version": name,
            "until_ms": until_ms,
            "ts_ms": wall_ms(),
        }
        threading.Thread(
            target=lambda: _try(lambda: rawtree.insert("scratch", [row])), daemon=True
        ).start()

    return Split(recommenders, shares, out_until_ms=out_until_ms, on_take_out=remember)


def _try(action: Callable[[], object]) -> None:
    try:
        action()
    except Exception as e:  # noqa: BLE001  remembering a take-out is best effort
        print(f"could not record a take-out: {e}", flush=True)


def measure_version(
    load: Callable[[], Recommend],
    requests: list[Record],
    state: State,
    reference: Recommend,
) -> dict[str, float]:
    """What a version costs before it goes live: load time and memory, then on `requests` how many answers
    are invalid (not 10 distinct available products), how many differ from `reference`, and time per call.

    Memory is what Python allocates while loading (tracemalloc), so it reads the same on every system."""
    tracemalloc.start()
    started = time.perf_counter()
    recommend = load()
    load_s = time.perf_counter() - started
    load_mb = tracemalloc.get_traced_memory()[0] / 2**20
    tracemalloc.stop()
    times, invalid, differs = [], 0, 0
    for request in requests:
        started = time.perf_counter()
        items = recommend(request, state)
        times.append((time.perf_counter() - started) * 1000)
        invalid += not (
            len(items) == 10 == len(set(items)) and set(items) <= state.available
        )
        differs += items != reference(request, state)
    times.sort()
    n = max(len(times), 1)
    return {
        "load_s": load_s,
        "load_mb": load_mb,
        "requests": len(requests),
        "invalid": invalid,
        "differs_pct": 100 * differs / n,
        "p50_ms": times[len(times) // 2] if times else 0.0,
        "p99_ms": times[int(len(times) * 0.99)] if times else 0.0,
        "max_ms": times[-1] if times else 0.0,
    }


def main_thread_wait_ms(seconds: float, step_s: float = 0.05) -> float:
    """The longest extra wait of a 50 ms sleep in this thread over `seconds`: what background work started by
    the loaded versions (refresh threads) would add to the answering loop."""
    worst, end = 0.0, time.monotonic() + seconds
    while time.monotonic() < end:
        started = time.perf_counter()
        time.sleep(step_s)
        worst = max(worst, (time.perf_counter() - started - step_s) * 1000)
    return worst

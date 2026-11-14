"""Every version that can answer live, and how a split of them is loaded.

To add a version, add one line to VERSIONS: a function that loads what the version needs and returns its
`recommend(request, state)`. A PR that adds one shows `scripts/check_versions.py` output for it (issue #5).
Choose which versions run and their shares with `run_recommender.py --versions name=share,...`, champion
first. How requests are shared and timed is in `split.py`.
"""

import math
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

import requests

from dades_huzz.data import RawTree
from dades_huzz.features import (
    LiveCategoryRanking,
    category_signals,
    live_category_signals,
    median_log_prices,
    shopper_carts,
    shopper_history_views,
    shopper_profiles,
    shopper_purchases,
)
from dades_huzz.model import (
    LAURI_PER_CATEGORY,
    best_sellers,
    cart_first,
    category_best_sellers,
    cold_first,
    hot_first,
    lauri,
    load_lauri_weights,
    subcategory_first,
)
from dades_huzz.serving.handover import now_ms
from dades_huzz.serving.loop import Recommend
from dades_huzz.serving.split import Split


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


def _cart_profile(rawtree: RawTree) -> Recommend:
    """Tati Cart: Apocalypse, with up to three products each returning shopper carted in the history and never
    bought on top (docs/experiments.md row 46)."""
    until = f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S}"
    signals = category_signals(rawtree, until=until)
    return cart_first(
        category_best_sellers(
            **vars(signals),
            keep_viewed=True,
            profiles=shopper_profiles(rawtree, until=until),
            bought=shopper_purchases(rawtree, until=until),
        ),
        shopper_carts(rawtree, until=until),
        signals.category_of,
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


def _omega(rawtree: RawTree, day_weight: float = 0.0) -> Recommend:
    """Tati Omega: Apocalypse (favourite categories, never what was bought) on the live category ranking
    (#38), and for a new shopper with views the subcategory viewed last first (#46).
    With `day_weight`, Tati Omega+: the categories viewed today (#54) count too, also for new shoppers."""
    until = f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S}"
    signals = live_category_signals(rawtree)
    return subcategory_first(
        category_best_sellers(
            **vars(signals),
            keep_viewed=True,
            profiles=shopper_profiles(rawtree, until=until),
            bought=shopper_purchases(rawtree, until=until),
            day_weight=day_weight,
        ),
        signals.ranked_by_category,
        signals.category_of,
    )


def _lauri(
    rawtree: RawTree,
    name: str,
    day: bool = False,
    history_carts: bool = False,
    per_category: int = LAURI_PER_CATEGORY,
) -> Recommend:
    """Lauri Titan: the weights last trained under `name` (scripts/train_lauri.py), scoring the live category
    ranking's products with each shopper's profile, and never showing what they bought.
    With `day`, Lauri Colossus: the shopper's day so far in `State` counts too.
    With `history_carts`, Lauri Titan+: what each shopper carted in the history and never bought joins.
    `per_category`: how deep each category's ranking reaches (Titan pool-100 takes 100)."""
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
        day=day,
        carts=shopper_carts(rawtree, until=until) if history_carts else None,
        per_category=per_category,
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
        seen_in_history=shopper_history_views(
            rawtree, until=f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S}"
        ),
    ),
    "tati-terminator-category-viewed-live": lambda rawtree: category_best_sellers(
        **vars(live_category_signals(rawtree)), keep_viewed=True
    ),
    "tati-terminator-live-subcat": lambda rawtree: _subcategory_first_live(rawtree),
    "tati-terminator-live-cold": lambda rawtree: category_best_sellers(
        **vars(live_category_signals(rawtree)),
        keep_viewed=True,
        cold_start=True,
        seen_in_history=shopper_history_views(
            rawtree, until=f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S}"
        ),
    ),
    "tati-omega-live-profile": lambda rawtree: _omega(rawtree),
    "tati-omega-plus-day": lambda rawtree: _omega(rawtree, day_weight=3.0),
    "tati-apocalypse-profile": lambda rawtree: _apocalypse(rawtree),
    "tati-armageddon-viewed-profile": lambda rawtree: _apocalypse(
        rawtree, viewed_first=3
    ),
    "tati-cart-profile": lambda rawtree: _cart_profile(rawtree),
    "lauri-titan-feedback": lambda rawtree: _lauri(rawtree, "lauri-titan-feedback"),
    "lauri-colossus-feedback": lambda rawtree: _lauri(
        rawtree, "lauri-colossus-feedback", day=True
    ),
    "lauri-titan-plus": lambda rawtree: _lauri(
        rawtree, "lauri-titan-plus", history_carts=True
    ),
    "lauri-titan-pool100": lambda rawtree: _lauri(
        rawtree, "lauri-titan-feedback", per_category=100
    ),
    "lauri-titan-cold60": lambda rawtree: cold_first(
        _lauri(rawtree, "lauri-titan-feedback"),
        category_best_sellers(
            **vars(live_category_signals(rawtree)),
            keep_viewed=True,
            cold_start=True,
            bought=shopper_purchases(
                rawtree, until=f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S}"
            ),
            seen_in_history=shopper_history_views(
                rawtree, until=f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S}"
            ),
        ),
    ),
    "lauri-titan-plus-hot": lambda rawtree: hot_first(
        _lauri(rawtree, "lauri-titan-plus", history_carts=True),
        live_category_signals(rawtree).ranked_by_category,
        bought=shopper_purchases(
            rawtree, until=f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S}"
        ),
    ),
}
"""Every version that can run live, by name: a function that loads what it needs and returns its recommend."""

DEFAULT_SPLIT = "tati-terminator-category-viewed=100"
LOAD_ATTEMPTS = 3

TAKE_OUTS = """
SELECT version::String AS version, max(until_ms::Int64) AS until_ms
FROM {team}.scratch
WHERE kind::String = 'version_out' AND until_ms::Int64 > {now_ms}
GROUP BY version"""


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
            TAKE_OUTS.format(team=rawtree.team, now_ms=now_ms()), timeout=5
        ):
            if row["version"] in shares and row["version"] != champion:
                out_until_ms.setdefault(row["version"], row["until_ms"])
                print(
                    f"version {row['version']} still taken out from before, until {row['until_ms']}",
                    flush=True,
                )
    except (
        requests.HTTPError
    ) as e:  # no version_out row yet: RawTree has no `until_ms` column to read
        print(
            "no take-outs recorded yet"
            if e.response is not None and e.response.status_code == 400
            else f"could not read earlier take-outs: {str(e)[:120]}",
            flush=True,
        )
    except Exception as e:  # noqa: BLE001  RawTree is slow or down: start without them
        print(f"could not read earlier take-outs: {str(e)[:120]}", flush=True)

    def remember(
        name: str, until_ms: int
    ) -> None:  # in the background: never on the answering path
        row = {
            "kind": "version_out",
            "version": name,
            "until_ms": until_ms,
            "ts_ms": now_ms(),
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

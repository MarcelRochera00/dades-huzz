"""Recommenders: each is a `recommend(request, state) -> list[str]` function (docs/contracts.md)."""

import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from collections.abc import Set as AbstractSet

import numpy as np

from dades_huzz.data import RawTree, Record, State
from dades_huzz.features import (
    LAURI_FEATURES,
    LauriDay,
    LauriSignals,
    LauriTrainingRows,
    lauri_features,
)
from dades_huzz.serving.loop import ANSWER_SIZE, Recommend

COLD_VIEWED_MAX = 3
"""A cold answer opens at most this many category blocks with the product viewed in them."""
PROFILE_WEIGHT = 3.0
"""How much a shopper's history counts next to the category they viewed last (which counts 1). Live, a
returning shopper's favourite category sold ~4x the category viewed last (docs/experiments.md row 27), so
at 3 a favourite holding a typical 30-40 % share comes first. Offline preferred 0.5 (row 22), but the old
carousel always showed the last viewed category, which biases that test. Tune per version with
`profile_weight`."""
PROFILE_TOP = 3
"""Only a shopper's three favourite categories take part: they hold 84 % of returning shoppers' live purchases."""


def best_sellers(request: Record, state: State) -> list[str]:
    """The organisers' baseline: the all-time best sellers that are available, the same for every shopper."""
    return list(state.fallback[:ANSWER_SIZE])


def category_best_sellers(
    category_of: Mapping[str, str],
    ranked_by_category: Mapping[str, Sequence[str]],
    keep_viewed: bool = False,
    viewed_first: int = 0,
    profiles: Mapping[str, Mapping[str, float]] | None = None,
    profile_weight: float = PROFILE_WEIGHT,
    bought: Mapping[str, AbstractSet[str]] | None = None,
    cold_start: bool = False,
) -> Recommend:
    """Tati Destroyer: the best sellers of the category the shopper viewed last, then the overall ones.

    `category_of` maps a product to its category; `ranked_by_category` lists each category's products,
    best seller first. Both are precomputed from the history. A product added after they were built takes
    its category from the live `state.category`. Only available products are shown.

    Products the shopper already viewed in this session are left out, unless `keep_viewed` (Tati
    Terminator): then they stay where they rank, because in the old log a viewed product shown in the top
    three slots was bought about 9x more often than the other products shown in the same requests.

    `viewed_first` (Tati Ultimatum) puts up to that many viewed products on top, the latest first. Slate
    IPS cannot reward this reordering (it counts only slots that match the old carousel), so only the live
    A/B can judge it.

    `profiles` (Tati Apocalypse) maps a shopper to their share of history per category. Their favourite
    categories join the one viewed last, at `profile_weight`, and the categories' best sellers are merged by
    rank divided by score. A shopper without views gets their favourites instead of the overall best
    sellers; a shopper without a profile gets exactly what they would get without `profiles`.

    `bought` maps a shopper to the products they already bought; those are never shown. The organisers
    (Discord, Sat 17:09): a shopper who bought a product is much less likely to buy it again, although the
    history was generated without that effect.

    `cold_start` answers a cold request (a new shopper, or a view of a new product) from the live trend
    instead: see `cold_start_answer`. What the shopper bought is left out there too.
    """
    trend_cache: list[tuple[Mapping[str, int], list[str]]] = [({}, [])]

    def category(product_id: str, state: State) -> str | None:
        return category_of.get(product_id) or state.category.get(product_id)

    def trending(state: State) -> list[str]:
        trend, ranked = trend_cache[0]
        if trend is not state.trend:
            trend = state.trend
            ranked = sorted(
                (p for p, n in trend.items() if n > 0), key=lambda p: (-trend[p], p)
            )
            trend_cache[0] = (trend, ranked)
        return ranked

    def candidates(category: str | None, user_id: str | None) -> Sequence[str]:
        profile = (profiles or {}).get(user_id or "")
        if not profile:
            return ranked_by_category.get(category, ()) if category else ()
        score: dict[str, float] = {category: 1.0} if category else {}
        favourites = sorted(profile.items(), key=lambda item: (-item[1], item[0]))
        for name, share in favourites[:PROFILE_TOP]:
            score[name] = score.get(name, 0.0) + profile_weight * share
        merged = [
            ((rank + 1) / value, -value, name, rank, product_id)
            for name, value in score.items()
            if value > 0
            for rank, product_id in enumerate(ranked_by_category.get(name, ()))
        ]
        return [entry[-1] for entry in sorted(merged)]

    def recommend(request: Record, state: State) -> list[str]:
        viewed = [view["product_id"] for view in request.get("recent_views") or []]
        owned = (bought or {}).get(request.get("user_id") or "", frozenset())
        if cold_start and (
            request.get("is_new_user") or any(p in state.new_products for p in viewed)
        ):
            return cold_start_answer(
                viewed,
                request,
                state,
                trending(state),
                lambda p: category(p, state),
                owned,
            )
        last_category = category(viewed[-1], state) if viewed else None
        ranked = candidates(last_category, request.get("user_id"))
        answer: list[str] = []
        for product_id in reversed(viewed):
            if len(answer) == viewed_first:
                break
            if (
                product_id in state.available
                and product_id not in answer
                and product_id not in owned
            ):
                answer.append(product_id)
        seen = set(answer) | set(owned)
        if not keep_viewed:
            seen |= set(viewed)
        for product_id in (*ranked, *state.fallback):
            if product_id in seen or product_id not in state.available:
                continue
            seen.add(product_id)
            answer.append(product_id)
            if len(answer) == ANSWER_SIZE:
                break
        return answer

    return recommend


def cold_start_answer(
    viewed: Sequence[str],
    request: Record,
    state: State,
    trending: Sequence[str],
    category_of: Callable[[str], str | None],
    owned: AbstractSet[str] = frozenset(),
) -> list[str]:
    """The answer to a cold request, built from the live trend (`trending`: products, highest first).

    Each category the shopper viewed gets a share of the ANSWER_SIZE slots in proportion to its views
    (largest remainder; a tie goes to the category viewed last). Blocks follow by share, ties again to the
    latest view. A block opens with the product last viewed in it (only in the COLD_VIEWED_MAX categories
    viewed last), then that category's trending products. Slots left over take the global trend, then the
    fallback. Without a view of a known category this is just the global trend. Unavailable products, the
    shopper's recent purchases and what they `owned` from the history are never shown.
    """
    bought = owned | state.recent_purchases.get(
        str(request.get("user_id")), frozenset()
    )
    answer: list[str] = []

    def add(product_id: str) -> None:
        if (
            product_id in state.available
            and product_id not in bought
            and product_id not in answer
        ):
            answer.append(product_id)

    views: Counter[str] = Counter()
    last_view: dict[str, tuple[int, str]] = {}
    for position, product_id in enumerate(viewed):
        if (category := category_of(product_id)) is not None:
            views[category] += 1
            last_view[category] = (position, product_id)
    if views:
        total = views.total()
        quota = {c: ANSWER_SIZE * n // total for c, n in views.items()}
        leftover = ANSWER_SIZE - sum(quota.values())
        by_remainder = sorted(
            views,
            key=lambda c: (ANSWER_SIZE * views[c] % total, last_view[c][0]),
            reverse=True,
        )
        for c in by_remainder[:leftover]:
            quota[c] += 1
        by_recency = sorted(views, key=lambda c: last_view[c][0], reverse=True)
        opens_with_view = set(by_recency[:COLD_VIEWED_MAX])
        in_category: dict[str, list[str]] = {c: [] for c in views}
        for product_id in trending:
            if (c := category_of(product_id)) in in_category:
                in_category[c].append(product_id)
        for c in sorted(views, key=lambda c: (views[c], last_view[c][0]), reverse=True):
            block_end = len(answer) + quota[c]
            opening = [last_view[c][1]] if c in opens_with_view else []
            for product_id in (*opening, *in_category[c]):
                if len(answer) >= block_end:
                    break
                add(product_id)
    for product_id in (*trending, *state.fallback):
        if len(answer) >= ANSWER_SIZE:
            break
        add(product_id)
    return answer


SUBCATEGORY_TOP = 2
"""Live, a new shopper with views bought an unviewed product of the subcategory viewed last 0.88 % of the time
in slots 1-2 against 0.32 % for another subcategory of the same category; slot 3 showed no effect
(docs/experiments.md row 35)."""


def subcategory_first(
    base: Recommend,
    ranked_by_category: Mapping[str, Sequence[str]],
    category_of: Mapping[str, str] | None = None,
    top: int = SUBCATEGORY_TOP,
) -> Recommend:
    """For a new shopper with views: the `top` best sellers of the subcategory they viewed last (not viewed,
    available) go first, then `base`'s answer without them. Everyone else gets `base`'s answer unchanged.

    The subcategory's order comes from its category's list in `ranked_by_category` (live with #38's
    ranking), each product's subcategory from the live `state.subcategory`."""

    def recommend(request: Record, state: State) -> list[str]:
        answer = base(request, state)
        viewed = [view["product_id"] for view in request.get("recent_views") or []]
        if not request.get("is_new_user") or not viewed:
            return answer
        last = viewed[-1]
        category = state.category.get(last) or (category_of or {}).get(last)
        subcategory = state.subcategory.get(last)
        if not category or not subcategory:
            return answer
        picks: list[str] = []
        for product_id in ranked_by_category.get(category, ()):
            if len(picks) == top:
                break
            if (
                product_id not in viewed
                and product_id in state.available
                and state.subcategory.get(product_id) == subcategory
            ):
                picks.append(product_id)
        rest = [product_id for product_id in answer if product_id not in picks]
        return (picks + rest)[:ANSWER_SIZE]

    return recommend


CART_TOP = 3
"""Carted products only lift slots 1-3 much: 70 vs 6.6 purchases per 10,000 shows there, 23 vs 2.9 in slots
4-10 (docs/experiments.md row 46)."""


def cart_first(
    base: Recommend,
    carts: Mapping[str, Sequence[str]],
    category_of: Mapping[str, str] | None = None,
    top: int = CART_TOP,
) -> Recommend:
    """For a returning shopper: up to `top` products they carted in the history and never bought go first,
    those of the category they viewed last before the others, then by latest cart. Then `base`'s answer
    without them. Unavailable products and what the shopper bought in the last minutes
    (`state.recent_purchases`) are never shown, in the picks or in `base`'s answer; a short answer is padded
    from `state.fallback`. Everyone else gets `base`'s answer unchanged."""

    def recommend(request: Record, state: State) -> list[str]:
        answer = base(request, state)
        user = request.get("user_id") or ""
        carted = carts.get(user)
        if request.get("is_new_user") or not carted:
            return answer
        recent = state.recent_purchases.get(user, frozenset())
        viewed = [view["product_id"] for view in request.get("recent_views") or []]
        last = viewed[-1] if viewed else None
        last_category = (
            state.category.get(last) or (category_of or {}).get(last) if last else None
        )

        def category(product_id: str) -> str | None:
            return state.category.get(product_id) or (category_of or {}).get(product_id)

        usable = [p for p in carted if p in state.available and p not in recent]
        picks = sorted(
            usable, key=lambda p: last_category is None or category(p) != last_category
        )[:top]
        result = list(picks)
        for product_id in (*answer, *state.fallback):
            if len(result) == ANSWER_SIZE:
                break
            if (
                product_id not in result
                and product_id not in recent
                and product_id in state.available
            ):
                result.append(product_id)
        return result

    return recommend


LAURI_SEGMENTS = ("new", "returning")
"""Lauri keeps one set of weights per kind of shopper: a new one has no history, so other signals carry them."""
LAURI_PER_CATEGORY = 30
LAURI_PER_SUBCATEGORY = 15
LAURI_PER_LIST = 20
"""How many candidates each source gives Lauri: a category's ranking, the subcategory viewed last, and the
trend and the fallback."""
LAURI_DAY_CATEGORIES = 3
"""Lauri Colossus also takes the ranking of this many of the shopper's most viewed categories of the day."""
SLOTS = 10

LauriWeights = Mapping[str, Mapping[str, object]]
"""Per segment: `weights` (one per LAURI_FEATURES, on the feature's own scale), and what only training
knows: `bias`, `slot` (one per slot after the first) and `owned`."""

LATEST_LAURI_WEIGHTS = """
SELECT weights::String AS weights
FROM {team}.scratch
WHERE kind::String = 'lauri_weights' AND name::String = '{name}'
ORDER BY ts_ms::Int64 DESC
LIMIT 1"""


def fit_logistic(
    features: np.ndarray, target: np.ndarray, l2: float = 10.0, steps: int = 50
) -> tuple[float, np.ndarray]:
    """L2 logistic regression by Newton steps on standardised columns: (bias, weights), both back on the
    columns' own scale. The bias is not penalised."""
    mean, std = features.mean(0), features.std(0)
    std[std == 0] = 1.0
    columns = np.c_[np.ones(len(features)), (features - mean) / std]
    penalty = np.eye(columns.shape[1]) * l2
    penalty[0, 0] = 0
    beta = np.zeros(columns.shape[1])
    for _ in range(steps):
        chance = 1 / (1 + np.exp(-columns @ beta))
        gradient = columns.T @ (chance - target) + penalty @ beta
        hessian = (columns * (chance * (1 - chance))[:, None]).T @ columns + penalty
        step = np.linalg.solve(hessian, gradient)
        beta -= step
        if np.abs(step).max() < 1e-8:
            break
    weights = beta[1:] / std
    return float(beta[0] - mean @ weights), weights


def _training_columns(rows: LauriTrainingRows) -> np.ndarray:
    """LAURI_FEATURES, then what only training knows: the slot after the first, and `owned`."""
    return np.c_[rows.features, np.eye(SLOTS)[rows.slot][:, 1:], rows.owned]


def _feature_weights(segment: Mapping[str, object]) -> np.ndarray:
    """A segment's weights, one per LAURI_FEATURES: weights stored before a feature existed count it as zero."""
    weights = np.zeros(len(LAURI_FEATURES))
    stored = np.array(segment["weights"], dtype=float)
    weights[: len(stored)] = stored
    return weights


def fit_lauri(
    rows: LauriTrainingRows,
    keep: np.ndarray,
    target: np.ndarray,
    l2: float = 10.0,
    features: Sequence[str] = LAURI_FEATURES,
) -> dict[str, dict[str, object]]:
    """Lauri's weights from the training rows in `keep`. The slot a product was shown in and whether the
    shopper already owned it are fitted next to the features, so they do not leak into the features'
    weights, and are then left out when serving: we choose the slot, and never show an owned product.

    Only `features` are fitted; the other LAURI_FEATURES get weight zero."""
    columns, n = _training_columns(rows), len(LAURI_FEATURES)
    used = [i for i, name in enumerate(LAURI_FEATURES) if name in features]
    chosen = [*used, *range(n, columns.shape[1])]
    fitted = {}
    for segment, mask in zip(
        LAURI_SEGMENTS, (rows.is_new_user, ~rows.is_new_user), strict=True
    ):
        bias, weights = fit_logistic(
            columns[keep & mask][:, chosen], target[keep & mask], l2
        )
        full = np.zeros(n)
        full[used] = weights[: len(used)]
        fitted[segment] = {
            "bias": bias,
            "weights": full.tolist(),
            "slot": weights[len(used) : -1].tolist(),
            "owned": float(weights[-1]),
        }
    return fitted


def lauri_scores(
    weights: LauriWeights, rows: LauriTrainingRows
) -> tuple[np.ndarray, np.ndarray]:
    """For every training row: the logit as it was shown (with slot and owned), and the score Lauri would
    rank it by live (features only)."""
    columns = _training_columns(rows)
    shown, served = np.zeros(len(columns)), np.zeros(len(columns))
    for segment, mask in zip(
        LAURI_SEGMENTS, (rows.is_new_user, ~rows.is_new_user), strict=True
    ):
        w = weights[segment]
        features = _feature_weights(w)
        full = np.r_[features, w["slot"], w["owned"]]
        shown[mask] = w["bias"] + columns[mask] @ full
        served[mask] = rows.features[mask] @ features
    return shown, served


def save_lauri_weights(
    rawtree: RawTree, name: str, weights: LauriWeights, ts_ms: int
) -> None:
    """Store the weights in our scratch table, so the serving loop loads them on any laptop."""
    row = {
        "kind": "lauri_weights",
        "name": name,
        "ts_ms": ts_ms,
        "features": list(LAURI_FEATURES),
        "weights": json.dumps(weights),
    }
    rawtree.insert("scratch", [row], timeout=10)


def load_lauri_weights(rawtree: RawTree, name: str) -> LauriWeights:
    """The latest weights stored under `name`. Raises if there are none: the version is then left out."""
    rows = rawtree.query(
        LATEST_LAURI_WEIGHTS.format(team=rawtree.team, name=name), timeout=10
    )
    if not rows:
        raise LookupError(
            f"no lauri_weights named {name!r} in scratch: run scripts/train_lauri.py"
        )
    return json.loads(rows[0]["weights"])


def lauri(
    weights: LauriWeights,
    ranked_by_category: Mapping[str, Sequence[str]],
    history_sales: Mapping[str, int],
    live_sales: Mapping[str, int],
    median_log_price: Mapping[str, float],
    profiles: Mapping[str, Mapping[str, float]] | None = None,
    bought: Mapping[str, AbstractSet[str]] | None = None,
    day: bool = False,
) -> Recommend:
    """Lauri Titan: scores every candidate with weights learned from our own carousels and shows the ten
    most likely to be bought.

    Candidates are what the Tati versions would consider, together: the products viewed in the session,
    the category ranking of every category viewed and of the shopper's favourite categories, the
    subcategory viewed last, the trend and the fallback. A shopper's purchases, from the history (`bought`)
    or recent (`state.recent_purchases`), are never shown. A new shopper and a returning one have their own
    weights. On any error the answer is the fallback.

    With `day` (Lauri Colossus) the shopper's day so far in `State` counts too: what they carted and viewed
    today and the ranking of their three most viewed categories of the day join the candidates, and the
    day's features are scored.
    """
    by_segment = {
        segment: _feature_weights(weights[segment]) for segment in LAURI_SEGMENTS
    }

    def day_of(user: str, state: State) -> LauriDay:
        return LauriDay(
            state.shopper_categories.get(user, {}),
            state.shopper_carted.get(user, frozenset()),
            state.shopper_viewed.get(user, ()),
        )

    trend_cache: list[tuple[Mapping[str, int], list[str]]] = [({}, [])]

    def trending(state: State) -> list[str]:
        trend, ranked = trend_cache[0]
        if trend is not state.trend:
            trend = state.trend
            ranked = sorted(
                (p for p, n in trend.items() if n > 0), key=lambda p: (-trend[p], p)
            )[:LAURI_PER_LIST]
            trend_cache[0] = (trend, ranked)
        return ranked

    def answer(request: Record, state: State) -> list[str]:
        user = str(request.get("user_id") or "")
        viewed = [view["product_id"] for view in request.get("recent_views") or []]
        profile = (profiles or {}).get(user)
        owned = (bought or {}).get(user, frozenset()) | state.recent_purchases.get(
            user, frozenset()
        )
        categories = [
            state.category[p] for p in reversed(viewed) if p in state.category
        ]
        if profile:
            favourites = sorted(profile, key=lambda name: (-profile[name], name))
            categories += favourites[:PROFILE_TOP]
        pool: dict[str, None] = dict.fromkeys(reversed(viewed))
        today = day_of(user, state) if day else None
        if today:
            pool.update(dict.fromkeys(sorted(today.carted)))
            pool.update(dict.fromkeys(today.viewed))
            counts = today.categories
            categories += sorted(counts, key=lambda name: (-counts[name], name))[
                :LAURI_DAY_CATEGORIES
            ]
        for name in dict.fromkeys(categories):
            pool.update(
                dict.fromkeys(ranked_by_category.get(name, ())[:LAURI_PER_CATEGORY])
            )
        if viewed and (last := state.subcategory.get(viewed[-1])) is not None:
            same = (
                p
                for p in ranked_by_category.get(state.category.get(viewed[-1], ""), ())
                if state.subcategory.get(p) == last
            )
            pool.update(dict.fromkeys(list(same)[:LAURI_PER_SUBCATEGORY]))
        pool.update(dict.fromkeys(trending(state)))
        pool.update(dict.fromkeys(state.fallback[:LAURI_PER_LIST]))
        candidates = [p for p in pool if p in state.available and p not in owned]
        signals = LauriSignals(
            state.category,
            state.subcategory,
            state.price,
            history_sales,
            live_sales,
            median_log_price,
        )
        segment = "new" if request.get("is_new_user") else "returning"
        scores = (
            lauri_features(candidates, viewed, profile, signals, today)
            @ by_segment[segment]
        )
        best = [candidates[i] for i in np.argsort(-scores, kind="stable")[:ANSWER_SIZE]]
        for product in state.fallback:
            if len(best) == ANSWER_SIZE:
                break
            if (
                product in state.available
                and product not in best
                and product not in owned
            ):
                best.append(product)
        return best

    def recommend(request: Record, state: State) -> list[str]:
        try:
            return answer(request, state)
        except Exception as e:  # noqa: BLE001  the contract: never raise, answer the fallback
            print(f"lauri failed, answering the fallback: {e!r}", flush=True)
            return list(state.fallback[:ANSWER_SIZE])

    return recommend

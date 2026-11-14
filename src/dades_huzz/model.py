"""Recommenders: each is a `recommend(request, state) -> list[str]` function (docs/contracts.md)."""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence

from dades_huzz.data import Record, State
from dades_huzz.serving.loop import ANSWER_SIZE

Recommend = Callable[[Record, State], list[str]]

COLD_VIEWED_MAX = 3
"""A cold answer opens at most this many category blocks with the product viewed in them."""


def best_sellers(request: Record, state: State) -> list[str]:
    """The organisers' baseline: the all-time best sellers that are available, the same for every shopper."""
    return list(state.fallback[:ANSWER_SIZE])


def category_best_sellers(
    category_of: Mapping[str, str],
    ranked_by_category: Mapping[str, Sequence[str]],
    keep_viewed: bool = False,
    viewed_first: int = 0,
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

    `cold_start` answers a cold request (a new shopper, or a view of a new product) from the live trend
    instead: see `cold_start_answer`.
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

    def recommend(request: Record, state: State) -> list[str]:
        viewed = [view["product_id"] for view in request.get("recent_views") or []]
        if cold_start and (
            request.get("is_new_user") or any(p in state.new_products for p in viewed)
        ):
            return cold_start_answer(
                viewed, request, state, trending(state), lambda p: category(p, state)
            )
        last_category = category(viewed[-1], state) if viewed else None
        ranked = ranked_by_category.get(last_category, ()) if last_category else ()
        answer: list[str] = []
        for product_id in reversed(viewed):
            if len(answer) == viewed_first:
                break
            if product_id in state.available and product_id not in answer:
                answer.append(product_id)
        seen = set(answer) if keep_viewed else set(viewed)
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
) -> list[str]:
    """The answer to a cold request, built from the live trend (`trending`: products, highest first).

    Each category the shopper viewed gets a share of the ANSWER_SIZE slots in proportion to its views
    (largest remainder; a tie goes to the category viewed last). Blocks follow by share, ties again to the
    latest view. A block opens with the product last viewed in it (only in the COLD_VIEWED_MAX categories
    viewed last), then that category's trending products. Slots left over take the global trend, then the
    fallback. Without a view of a known category this is just the global trend. Unavailable products and
    the shopper's recent purchases are never shown.
    """
    bought = state.recent_purchases.get(str(request.get("user_id")), frozenset())
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

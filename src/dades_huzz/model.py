"""Recommenders: each is a `recommend(request, state) -> list[str]` function (docs/contracts.md)."""

from collections.abc import Callable, Collection, Mapping, Sequence

from dades_huzz.data import Record, State
from dades_huzz.serving.loop import ANSWER_SIZE

Recommend = Callable[[Record, State], list[str]]


def best_sellers(request: Record, state: State) -> list[str]:
    """The organisers' baseline: the all-time best sellers that are available, the same for every shopper."""
    return list(state.fallback[:ANSWER_SIZE])


def category_best_sellers(
    category_of: Mapping[str, str],
    ranked_by_category: Mapping[str, Sequence[str]],
    keep_viewed: bool = False,
    viewed_first: int = 0,
) -> Recommend:
    """Tati Destroyer: the best sellers of the category the shopper viewed last, then the overall ones.

    `category_of` maps a product to its category; `ranked_by_category` lists each category's products,
    best seller first. Both are precomputed from the history. Only available products are shown.

    Products the shopper already viewed in this session are left out, unless `keep_viewed` (Tati
    Terminator): then they stay where they rank, because in the old log a viewed product shown in the top
    three slots was bought about 9x more often than the other products shown in the same requests.

    `viewed_first` (Tati Ultimatum) puts up to that many viewed products on top, the latest first. Slate
    IPS cannot reward this reordering (it counts only slots that match the old carousel), so only the live
    A/B can judge it.
    """

    def recommend(request: Record, state: State) -> list[str]:
        viewed = [view["product_id"] for view in request.get("recent_views") or []]
        category = category_of.get(viewed[-1]) if viewed else None
        ranked = ranked_by_category.get(category, ()) if category else ()
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


def order_by_trend(
    candidates: Sequence[str],
    scores: Mapping[str, int],
    state: State,
    bought: Collection[str] = (),
) -> list[str]:
    """Ten available products for any request: Tati's list plus whatever is trending.

    `candidates` is Tati's ranking before it is cut to ten. Products with a positive trend score
    join that list. Higher score goes first; a tie keeps Tati's order, then the fallback order.
    A product this shopper bought in the trend window is left out. A short answer is padded with
    the fallback, which is also what fills a request that has no category list.
    """
    blocked = set(bought)
    tie: dict[str, int] = {}
    for product_id in candidates:
        tie.setdefault(product_id, len(tie))
    for product_id in state.fallback:
        tie.setdefault(product_id, len(tie))
    pool = list(candidates)
    seen_in_pool = set(pool)
    for product_id, score in scores.items():
        if score > 0 and product_id not in seen_in_pool:
            pool.append(product_id)
            seen_in_pool.add(product_id)
    after = len(tie)

    def sort_key(product_id: str) -> tuple[int, int, str]:
        return (-scores.get(product_id, 0), tie.get(product_id, after), product_id)

    answer: list[str] = []
    seen: set[str] = set()
    eligible = [
        product_id
        for product_id in pool
        if product_id in state.available and product_id not in blocked
    ]
    for product_id in sorted(eligible, key=sort_key):
        seen.add(product_id)
        answer.append(product_id)
        if len(answer) == ANSWER_SIZE:
            return answer
    for product_id in state.fallback:
        if (
            product_id in seen
            or product_id in blocked
            or product_id not in state.available
        ):
            continue
        seen.add(product_id)
        answer.append(product_id)
        if len(answer) == ANSWER_SIZE:
            break
    return answer


def with_trend(
    category_of: Mapping[str, str],
    ranked_by_category: Mapping[str, Sequence[str]],
) -> Recommend:
    """Tati's category list, reordered by the trend on `state`, except for a new shopper.

    A new shopper (`is_new_user`) has no history we can use, so the answer is the global trend:
    the highest scores in `state.trend` (purchase 4, add-to-cart 3, view 1, last 15 minutes),
    then the fallback. Their views are ignored.

    Everyone else gets Tati's category list before it is cut to ten, plus any product with a
    positive trend score. A shopper's recent purchases, also on `state`, are left out.
    """

    def recommend(request: Record, state: State) -> list[str]:
        viewed = [view["product_id"] for view in request.get("recent_views") or []]
        bought = state.recent_purchases.get(str(request.get("user_id")), ())
        if request.get("is_new_user"):
            return order_by_trend([], state.trend, state, bought)
        category = category_of.get(viewed[-1]) if viewed else None
        ranked = ranked_by_category.get(category, ()) if category else ()
        candidates = list(ranked) if ranked else list(state.fallback)
        return order_by_trend(candidates, state.trend, state, bought)

    return recommend

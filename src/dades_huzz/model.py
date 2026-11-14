"""Recommenders: each is a `recommend(request, state) -> list[str]` function (docs/contracts.md)."""

from collections.abc import Callable, Mapping, Sequence

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

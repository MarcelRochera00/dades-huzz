"""Recommenders: each is a `recommend(request, state) -> list[str]` function (docs/contracts.md)."""

from collections.abc import Callable, Mapping, Sequence

from dades_huzz.data import Record, State
from dades_huzz.serving.loop import ANSWER_SIZE

Recommend = Callable[[Record, State], list[str]]

PROFILE_WEIGHT = 0.5
"""How much a shopper's history counts next to the category they viewed last (which counts 1). Offline,
0.5 tied with Terminator, while 1 tied lower and 2 lost (docs/experiments.md)."""
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
    categories join the one viewed last, at PROFILE_WEIGHT, and the categories' best sellers are merged by
    rank divided by score. A shopper without views gets their favourites instead of the overall best
    sellers; a shopper without a profile gets exactly what they would get without `profiles`.
    """

    def candidates(category: str | None, user_id: str | None) -> Sequence[str]:
        profile = (profiles or {}).get(user_id or "")
        if not profile:
            return ranked_by_category.get(category, ()) if category else ()
        score: dict[str, float] = {category: 1.0} if category else {}
        favourites = sorted(profile.items(), key=lambda item: (-item[1], item[0]))
        for name, share in favourites[:PROFILE_TOP]:
            score[name] = score.get(name, 0.0) + PROFILE_WEIGHT * share
        merged = [
            ((rank + 1) / value, -value, name, rank, product_id)
            for name, value in score.items()
            if value > 0
            for rank, product_id in enumerate(ranked_by_category.get(name, ()))
        ]
        return [entry[-1] for entry in sorted(merged)]

    def recommend(request: Record, state: State) -> list[str]:
        viewed = [view["product_id"] for view in request.get("recent_views") or []]
        category = (
            category_of.get(viewed[-1]) or state.category.get(viewed[-1])
            if viewed
            else None
        )
        ranked = candidates(category, request.get("user_id"))
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

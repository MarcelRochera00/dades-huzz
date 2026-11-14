"""Recommenders: each is a `recommend(request, state) -> list[str]` function (docs/contracts.md)."""

from dades_huzz.data import Record, State
from dades_huzz.serving.loop import ANSWER_SIZE


def best_sellers(request: Record, state: State) -> list[str]:
    """The organisers' baseline: the all-time best sellers that are available, the same for every shopper."""
    return list(state.fallback[:ANSWER_SIZE])

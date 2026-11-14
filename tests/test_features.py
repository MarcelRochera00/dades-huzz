from datetime import datetime

from dades_huzz.features import (
    apply_live_signals,
    bought_in_window,
    category_signals,
    trend_scores,
)


class FakeRawTree:
    """Answers the catalogue query with a known product and a new one, and the ranking with nothing."""

    def __init__(self):
        self.queries = []

    def query(self, sql, timeout=10):
        self.queries.append(sql)
        if "catalog_updates" in sql:
            return [
                {"product_id": "p_old", "category": "Toys"},
                {"product_id": "p_new", "category": "Fashion"},
            ]
        return []


def test_trend_scores_weight_the_last_fifteen_minutes():
    # purchase 4, add_to_cart 3, view 1; an event just outside the window does not count
    now = datetime(2026, 11, 14, 13, 33, tzinfo=None)
    events = [
        {"ts": "2026-11-14 13:17:00", "event_type": "view", "product_id": "p_a"},
        {"ts": "2026-11-14 13:20:00", "event_type": "purchase", "product_id": "p_a"},
        {"ts": "2026-11-14 13:25:00", "event_type": "view", "product_id": "p_a"},
        {"ts": "2026-11-14 13:30:00", "event_type": "add_to_cart", "product_id": "p_b"},
    ]
    assert trend_scores(events, now) == {"p_a": 5, "p_b": 3}


def test_bought_in_window_is_this_shoppers_purchases_in_the_same_fifteen_minutes():
    now = datetime(2026, 11, 14, 13, 33)
    events = [
        {
            "ts": "2026-11-14 13:30:00",
            "event_type": "purchase",
            "product_id": "p_a",
            "user_id": "u1",
        },
        {
            "ts": "2026-11-14 13:30:00",
            "event_type": "purchase",
            "product_id": "p_b",
            "user_id": "u2",
        },
        {
            "ts": "2026-11-14 13:31:00",
            "event_type": "view",
            "product_id": "p_c",
            "user_id": "u1",
        },
        {
            "ts": "2026-11-14 13:00:00",
            "event_type": "purchase",
            "product_id": "p_old",
            "user_id": "u1",
        },
    ]
    assert bought_in_window(events, "u1", now) == frozenset({"p_a"})


def test_apply_live_signals_puts_the_trend_and_purchases_on_the_state():
    from dades_huzz.data import State

    now = datetime(2026, 11, 14, 13, 33)
    events = [
        {
            "ts": "2026-11-14 13:20:00",
            "event_type": "purchase",
            "product_id": "p_a",
            "user_id": "u1",
        },
        {
            "ts": "2026-11-14 13:25:00",
            "event_type": "view",
            "product_id": "p_a",
            "user_id": "u1",
        },
    ]
    state = State(
        available=frozenset({"p_a"}),
        price={},
        new_products=frozenset(),
        fallback=("p_a",),
    )
    live = apply_live_signals(state, events, now)
    assert live.trend == {"p_a": 5}
    assert live.recent_purchases == {"u1": frozenset({"p_a"})}
    assert live.available == state.available


def test_category_signals_know_the_category_of_products_added_during_the_event():
    # a cold request is one whose last view is a new product: Destroyer needs its category
    signals = category_signals(FakeRawTree(), until="2026-11-14 12:00:00")
    assert signals.category_of == {"p_old": "Toys", "p_new": "Fashion"}

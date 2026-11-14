from dades_huzz.data import State
from dades_huzz.features import (
    FINAL_ROUND_START,
    PRACTICE_ROUND_START,
    LiveCategoryRanking,
    category_ranking,
    category_signals,
    live_sales_since_ms,
    pick_prior_weight,
    utc_ms,
)
from dades_huzz.model import category_best_sellers


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


def test_category_signals_know_the_category_of_products_added_during_the_event():
    # a cold request is one whose last view is a new product: Destroyer needs its category
    signals = category_signals(FakeRawTree(), until="2026-11-14 12:00:00")
    assert signals.category_of == {"p_old": "Toys", "p_new": "Fashion"}


TOYS = {f"t_{i:02d}": "toys" for i in range(20)}
HISTORY_LOVES_THE_FIRST_TEN = {f"t_{i:02d}": 0.1 for i in range(10)}


def test_category_ranking_adds_live_sales_to_the_history_prior_and_lets_a_new_product_in():
    ranked = category_ranking(
        live={"n_new": 5, "b": 3},
        history_share={"a": 0.6, "b": 0.4},
        category_of={"a": "toys", "b": "toys", "n_new": "toys", "x": "food"},
        prior_weight=10,
    )
    # a = 0 + 10 * 0.6 = 6, b = 3 + 10 * 0.4 = 7, n_new = 5 (no history, it sells live)
    assert ranked == {"toys": ["b", "a", "n_new"]}


def test_category_ranking_leaves_out_products_without_a_category_or_a_score():
    ranked = category_ranking(
        live={"unknown": 9, "a": 0},
        history_share={"b": 0.5},
        category_of={"a": "toys", "b": "toys"},
        prior_weight=0,
    )
    assert ranked == {}


def test_the_tuned_weight_trusts_the_history_while_it_predicts_live_sales():
    weight, _ = pick_prior_weight(
        before={},
        recent={f"t_{i:02d}": 3 for i in range(10)},
        history_share=HISTORY_LOVES_THE_FIRST_TEN,
        category_of=TOYS,
        weights=(0, 1000),
    )
    assert weight == 1000


def test_the_tuned_weight_drops_the_history_when_the_trend_changes():
    # live shoppers buy the other ten products: the history now points the wrong way
    other_ten = {f"t_{i:02d}": 3 for i in range(10, 20)}
    weight, scores = pick_prior_weight(
        before=other_ten,
        recent=other_ten,
        history_share=HISTORY_LOVES_THE_FIRST_TEN,
        category_of=TOYS,
        weights=(0, 1000),
    )
    assert weight == 0
    assert scores == {0: 1.0, 1000: 0.0}


def test_live_sales_count_from_the_switch_once_it_has_come():
    switch = utc_ms(FINAL_ROUND_START)
    assert live_sales_since_ms(switch - 1) == utc_ms(PRACTICE_ROUND_START)
    assert live_sales_since_ms(switch) == switch


class LiveRawTree:
    """A catalogue, its live purchases and the history, all changeable by the test."""

    def __init__(self, catalogue, sales, history):
        self.catalogue, self.sales, self.history = catalogue, sales, history
        self.live_queries = []

    def query(self, sql, timeout=10):
        if "history_events" in sql:
            return [{"product_id": p, "n": n} for p, n in self.history.items()]
        if "shop.events" in sql:
            self.live_queries.append(sql)
            return [
                {"product_id": p, "before": n, "recent": 0}
                for p, n in self.sales.items()
            ]
        return [{"product_id": p, "category": c} for p, c in self.catalogue.items()]


def test_the_live_ranking_follows_an_all_new_catalogue_without_a_restart():
    rawtree = LiveRawTree(
        catalogue={"old_1": "toys", "old_2": "toys"},
        sales={},
        history={"old_1": 50, "old_2": 10},
    )
    ranking = LiveCategoryRanking(rawtree, since_ms=0, now_ms=lambda: 60 * 60_000)
    signals = ranking.signals()  # a version keeps these two objects for its whole life
    assert signals.ranked_by_category["toys"] == ["old_1", "old_2"]

    # the switch: every product is new, none has history, and some start selling
    rawtree.catalogue = {"new_1": "toys", "new_2": "toys", "new_3": "food"}
    rawtree.sales = {"new_2": 4, "new_1": 1, "new_3": 2}
    ranking.refresh()

    assert signals.ranked_by_category["toys"] == ["new_2", "new_1"]
    assert signals.ranked_by_category["food"] == ["new_3"]
    assert signals.category_of.get("new_1") == "toys"
    assert "fromUnixTimestamp64Milli(toInt64(0))" in rawtree.live_queries[-1]


def test_a_version_answers_from_the_live_ranking():
    rawtree = LiveRawTree(
        catalogue={"new_1": "toys", "new_2": "toys"},
        sales={"new_2": 4, "new_1": 1},
        history={},
    )
    signals = LiveCategoryRanking(rawtree, since_ms=0, now_ms=lambda: 0).signals()
    recommend = category_best_sellers(**vars(signals), keep_viewed=True)
    fallback = tuple(f"p_{i:02d}" for i in range(10))
    state = State(
        available=frozenset({"new_1", "new_2", *fallback}),
        price={},
        new_products=frozenset({"new_1", "new_2"}),
        fallback=fallback,
    )
    answer = recommend({"recent_views": [{"product_id": "new_1"}]}, state)
    assert answer[:3] == ["new_2", "new_1", "p_00"]

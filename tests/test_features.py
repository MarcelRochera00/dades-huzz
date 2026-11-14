from datetime import datetime

from dades_huzz.data import State
from dades_huzz.features import (
    FINAL_ROUND_START,
    PRACTICE_ROUND_START,
    LiveCategoryRanking,
    category_ranking,
    category_signals,
    live_sales_since_ms,
    pick_prior_weight,
    purchases_in_window,
    trend_scores,
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


def test_purchases_in_window_are_each_shoppers_purchases_in_the_same_fifteen_minutes():
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
    assert purchases_in_window(events, now) == {
        "u1": frozenset({"p_a"}),
        "u2": frozenset({"p_b"}),
    }


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


class ProfileRawTree:
    """Answers the profile query with per-category weights for two shoppers."""

    def query(self, sql, timeout=10):
        assert "history_events" in sql and "2026-11-07 07:00:00" in sql
        return [
            {"user_id": "u_1", "category": "Toys", "weight": 30},
            {"user_id": "u_1", "category": "Books", "weight": 10},
            {"user_id": "u_2", "category": "Pets", "weight": 5},
        ]


def test_shopper_profiles_are_each_shoppers_share_of_weight_per_category():
    from dades_huzz.features import shopper_profiles

    profiles = shopper_profiles(ProfileRawTree(), until="2026-11-07 07:00:00")
    assert profiles == {"u_1": {"Toys": 0.75, "Books": 0.25}, "u_2": {"Pets": 1.0}}


class PurchasesRawTree:
    def query(self, sql, timeout=10):
        # the history is a snapshot from before the event; live purchases are in shop.events
        assert (
            "purchase" in sql and "shop.history_events" in sql and "shop.events" in sql
        )
        return [{"user_id": "u_1", "products": ["p_a", "p_b"]}]


def test_shopper_purchases_are_each_shoppers_bought_products():
    from dades_huzz.features import shopper_purchases

    assert shopper_purchases(PurchasesRawTree(), until="2026-11-14 12:00:00") == {
        "u_1": frozenset({"p_a", "p_b"})
    }


def test_lauri_features_describe_a_candidate_for_this_shopper():
    import math

    from dades_huzz.features import LAURI_FEATURES, LauriSignals, lauri_features

    signals = LauriSignals(
        category={"p1": "toys", "p2": "toys", "p3": "books"},
        subcategory={"p1": "lego", "p2": "dolls", "p3": "novels"},
        price={"p1": 20.0, "p2": 10.0, "p3": 5.0},
        history_sales={"p2": 9},
        live_sales={"p3": 3},
        median_log_price={"toys": math.log(10.0), "books": math.log(5.0)},
    )
    rows = lauri_features(
        ["p1", "p2", "p3", "unknown"],
        ["p3", "p1"],
        {"books": 0.8, "toys": 0.2},
        signals,
    )
    by_name = [dict(zip(LAURI_FEATURES, row, strict=True)) for row in rows]
    assert by_name[0]["viewed"] == 1 and by_name[0]["view_recency"] == 1
    assert by_name[2]["viewed"] == 1 and by_name[2]["view_recency"] == 0.5
    assert by_name[1]["viewed"] == 0
    assert by_name[1]["same_category"] == 1 and by_name[1]["same_subcategory"] == 0
    assert by_name[0]["same_subcategory"] == 1
    assert by_name[1]["session_category_share"] == 0.5
    assert by_name[2]["profile_share"] == 0.8 and by_name[2]["favourite_category"] == 1
    assert by_name[1]["log_history_sales"] == math.log(10)
    assert by_name[2]["log_live_sales"] == math.log(4)
    assert math.isclose(by_name[0]["relative_price"], math.log(2))
    assert not rows[3].any()


def test_lauri_features_know_the_shoppers_day():
    import math

    from dades_huzz.features import (
        LAURI_FEATURES,
        LauriDay,
        LauriSignals,
        lauri_features,
    )

    signals = LauriSignals(
        category={"p1": "toys", "p2": "toys", "p3": "books"},
        subcategory={},
        price={},
        history_sales={"p2": 9},
        live_sales={},
        median_log_price={},
    )
    day = LauriDay({"toys": 3, "books": 1}, frozenset({"p2"}), ("p3",))
    rows = lauri_features(["p1", "p2", "p3"], [], None, signals, day)
    by_name = [dict(zip(LAURI_FEATURES, row, strict=True)) for row in rows]
    assert by_name[0]["day_category_share"] == 0.75
    assert by_name[2]["day_category_share"] == 0.25
    assert [row["day_carted"] for row in by_name] == [0, 1, 0]
    assert [row["day_viewed"] for row in by_name] == [0, 0, 1]
    assert math.isclose(by_name[1]["day_history_sales"], 0.75 * math.log(10))
    without = lauri_features(["p1", "p2", "p3"], [], None, signals)
    assert not without[:, -4:].any()
    assert (without[:, :-4] == rows[:, :-4]).all()


def test_a_day_replay_never_sees_what_came_after_the_cut():
    from dades_huzz.features import DayReplay

    category = {"p1": "toys", "p2": "toys", "p3": "books"}
    replay = DayReplay(
        [
            (10, "view", "p1"),
            (20, "add_to_cart", "p1"),
            (30, "view", "p3"),
            (40, "purchase", "p1"),
            (50, "view", "p2"),
        ]
    )
    day = replay.until(35, category)
    assert day.categories == {"toys": 4, "books": 1}
    assert day.carted == {"p1"} and list(day.viewed) == ["p3", "p1"]
    day = replay.until(45, category)
    assert day.carted == set() and list(day.viewed) == ["p3", "p1"]
    day = replay.until(15, category)  # an earlier cut starts the day again
    assert day.categories == {"toys": 1} and list(day.viewed) == ["p1"]

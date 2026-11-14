from dades_huzz.data import State
from dades_huzz.model import best_sellers, order_by_trend, with_trend


def test_best_sellers_shows_the_first_ten_of_the_fallback():
    fallback = tuple(f"p_{i:02d}" for i in range(15))
    state = State(
        available=frozenset(fallback),
        price={},
        new_products=frozenset(),
        fallback=fallback,
    )
    request = {"request_id": "r1", "recent_views": [{"product_id": "p_14"}]}
    assert best_sellers(request, state) == [
        "p_00",
        "p_01",
        "p_02",
        "p_03",
        "p_04",
        "p_05",
        "p_06",
        "p_07",
        "p_08",
        "p_09",
    ]


def _state(extra=()):
    fallback = tuple(f"p_{i:02d}" for i in range(15))
    return State(
        available=frozenset(fallback) | frozenset(extra),
        price={},
        new_products=frozenset(),
        fallback=fallback,
    )


def test_category_best_sellers_shows_the_top_of_the_category_viewed_last():
    from dades_huzz.model import category_best_sellers

    recommend = category_best_sellers(
        category_of={"v_old": "toys", "v_last": "electronics"},
        ranked_by_category={
            "toys": ["t_1"],
            # "v_last" is the product being viewed: not shown again; "e_gone" is out of stock
            "electronics": ["e_1", "v_last", "e_gone", "e_2"],
        },
    )
    state = _state(extra={"e_1", "e_2", "v_last", "t_1"})
    request = {"recent_views": [{"product_id": "v_old"}, {"product_id": "v_last"}]}
    answer = recommend(request, state)
    assert answer[:3] == ["e_1", "e_2", "p_00"]
    assert len(answer) == 10
    assert len(set(answer)) == 10


def test_category_best_sellers_falls_back_without_recent_views():
    from dades_huzz.model import category_best_sellers

    recommend = category_best_sellers(category_of={}, ranked_by_category={})
    state = _state()
    assert recommend({"recent_views": []}, state) == list(state.fallback[:10])


def test_category_best_sellers_can_keep_viewed_products_where_they_rank():
    from dades_huzz.model import category_best_sellers

    # shoppers buy products they already viewed far more often: Tati Terminator keeps them in place
    recommend = category_best_sellers(
        category_of={"v_last": "electronics"},
        ranked_by_category={"electronics": ["e_1", "v_last", "e_gone", "e_2"]},
        keep_viewed=True,
    )
    state = _state(extra={"e_1", "e_2", "v_last"})
    request = {"recent_views": [{"product_id": "v_last"}]}
    answer = recommend(request, state)
    assert answer[:4] == ["e_1", "v_last", "e_2", "p_00"]
    assert len(set(answer)) == 10


def test_category_best_sellers_can_put_the_latest_viewed_products_first():
    from dades_huzz.model import category_best_sellers

    # Tati Ultimatum: up to three viewed products on top, the latest first; an unavailable one is
    # skipped, an older fourth stays where it ranks, and nothing is shown twice
    recommend = category_best_sellers(
        category_of={"v_4": "electronics"},
        ranked_by_category={"electronics": ["e_1", "v_1", "v_3", "e_2"]},
        keep_viewed=True,
        viewed_first=3,
    )
    state = _state(extra={"e_1", "e_2", "v_1", "v_2", "v_3", "v_4"})
    request = {
        "recent_views": [
            {"product_id": "v_1"},
            {"product_id": "v_2"},
            {"product_id": "v_gone"},
            {"product_id": "v_3"},
            {"product_id": "v_4"},
        ]
    }
    answer = recommend(request, state)
    assert answer[:6] == ["v_4", "v_3", "v_2", "e_1", "v_1", "e_2"]
    assert len(answer) == 10
    assert len(set(answer)) == 10


def test_order_by_trend_puts_a_live_product_ahead_of_tati_and_drops_a_recent_purchase():
    # p_hot is not a historical best seller; p_bought ranks first for Tati but was just purchased
    state = _state(extra={"p_hot", "p_mid", "p_bought"})
    answer = order_by_trend(
        candidates=["p_bought", "p_mid", "p_00"],
        scores={"p_hot": 4, "p_mid": 3, "p_bought": 8},
        state=state,
        bought=["p_bought"],
    )
    assert answer[:3] == ["p_hot", "p_mid", "p_00"]
    assert "p_bought" not in answer
    assert len(answer) == 10
    assert len(set(answer)) == 10


def test_with_trend_reorders_every_request_from_the_state():
    from dataclasses import replace

    recommend = with_trend(
        category_of={"v": "electronics"},
        ranked_by_category={"electronics": ["p_bought", "p_mid"]},
    )
    state = replace(
        _state(extra={"p_hot", "p_mid", "p_bought"}),
        trend={"p_hot": 4, "p_mid": 3, "p_bought": 8},
        recent_purchases={"u1": frozenset({"p_bought"})},
    )
    request = {"user_id": "u1", "recent_views": [{"product_id": "v"}]}
    answer = recommend(request, state)
    assert answer[:3] == ["p_hot", "p_mid", "p_00"]
    assert "p_bought" not in answer


def test_a_new_shopper_gets_the_global_trend():
    # views are all toys; the answer still follows the whole-shop score, not that category
    from dataclasses import replace

    recommend = with_trend(
        category_of={"toy_a": "toys", "elec": "electronics"},
        ranked_by_category={"toys": ["toy_hist"], "electronics": ["elec"]},
    )
    state = replace(
        _state(extra={"toy_a", "toy_hist", "elec", "p_hot"}),
        trend={"elec": 9, "toy_a": 4, "p_hot": 20},
    )
    request = {
        "user_id": "u_new",
        "is_new_user": True,
        "recent_views": [{"product_id": "toy_a"}, {"product_id": "toy_a"}],
    }
    answer = recommend(request, state)
    assert answer[:3] == ["p_hot", "elec", "toy_a"]
    assert "toy_hist" not in answer[:3]

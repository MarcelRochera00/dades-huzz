from dades_huzz.data import State
from dades_huzz.model import best_sellers


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


def test_category_best_sellers_finds_the_category_of_a_product_added_after_loading():
    from dades_huzz.model import category_best_sellers

    # "n_new" arrived after the version loaded: only the live State knows its category
    recommend = category_best_sellers(
        category_of={}, ranked_by_category={"toys": ["t_1", "t_2"]}
    )
    state = _state(extra={"t_1", "t_2", "n_new"})
    state = State(**{**vars(state), "category": {"n_new": "toys"}})
    answer = recommend({"recent_views": [{"product_id": "n_new"}]}, state)
    assert answer[:3] == ["t_1", "t_2", "p_00"]


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


def _cold_state(trend, extra=(), recent_purchases=None, new_products=()):
    state = _state(extra={*trend, *extra})
    return State(
        **{
            **vars(state),
            "new_products": frozenset(new_products),
            "trend": trend,
            "recent_purchases": recent_purchases or {},
        }
    )


def _cold_recommend(category_of):
    from dades_huzz.model import category_best_sellers

    return category_best_sellers(
        category_of=category_of,
        ranked_by_category={},
        keep_viewed=True,
        viewed_first=3,
        cold_start=True,
    )


def test_cold_start_without_views_shows_the_global_trend_minus_recent_purchases():
    recommend = _cold_recommend({})
    state = _cold_state(
        trend={"hot": 9, "bought": 8, "warm": 4, "mild": 1},
        recent_purchases={"u1": frozenset({"bought"})},
    )
    answer = recommend(
        {"user_id": "u1", "is_new_user": True, "recent_views": []}, state
    )
    assert answer[:4] == ["hot", "warm", "mild", "p_00"]
    assert len(set(answer)) == 10


def test_cold_start_splits_the_list_by_the_share_of_views_per_category():
    # 3 of 5 views are toys and 2 electronics: 6 toys slots, then 4 electronics slots. Each block opens
    # with its last viewed product, then that category's trend; a short block is filled at the end
    recommend = _cold_recommend(
        {"t_v1": "toys", "t_v2": "toys", "e_v1": "electronics", "e_v2": "electronics"}
    )
    trend = {"t_1": 9, "e_1": 8, "t_2": 7, "e_2": 6, "e_3": 5, "t_3": 4, "t_4": 3}
    category = {p: "toys" if p.startswith("t") else "electronics" for p in trend}
    state = _cold_state(trend, extra={"t_v1", "t_v2", "e_v1", "e_v2"})
    state = State(**{**vars(state), "category": category})
    views = ["t_v1", "e_v1", "t_v1", "e_v2", "t_v2"]
    request = {"is_new_user": True, "recent_views": [{"product_id": p} for p in views]}
    assert recommend(request, state) == [
        *["t_v2", "t_1", "t_2", "t_3", "t_4"],  # toys block: 5 of its 6 slots found
        *["e_v2", "e_1", "e_2", "e_3"],
        "p_00",
    ]


def test_cold_start_breaks_ties_by_the_most_recent_view_and_shows_at_most_three_viewed():
    # one view in each of four categories: 2.5 slots each, the two leftover slots go to the categories
    # viewed last; only the three most recently viewed categories open with their viewed product
    recommend = _cold_recommend({"a_v": "a", "b_v": "b", "c_v": "c", "d_v": "d"})
    trend = {f"{c}_{i}": 10 - i for c in "abcd" for i in range(3)}
    state = _cold_state(trend, extra={"a_v", "b_v", "c_v", "d_v"})
    state = State(**{**vars(state), "category": {p: p[0] for p in trend}})
    views = ["a_v", "b_v", "c_v", "d_v"]
    request = {"is_new_user": True, "recent_views": [{"product_id": p} for p in views]}
    assert recommend(request, state) == [
        *["d_v", "d_0", "d_1"],
        *["c_v", "c_0", "c_1"],
        *["b_v", "b_0"],
        *["a_0", "a_1"],
    ]


def test_a_returning_shopper_who_views_a_new_product_is_cold_too():
    recommend = _cold_recommend({})
    state = _cold_state({"n_1": 5, "hot": 9}, extra={"n_new"}, new_products={"n_new"})
    state = State(**{**vars(state), "category": {"n_new": "toys", "n_1": "toys"}})
    request = {"is_new_user": False, "recent_views": [{"product_id": "n_new"}]}
    assert recommend(request, state)[:3] == ["n_new", "n_1", "hot"]


def test_a_cold_answer_leaves_out_what_the_shopper_bought_in_the_history():
    from dades_huzz.model import category_best_sellers

    recommend = category_best_sellers(
        category_of={},
        ranked_by_category={},
        keep_viewed=True,
        viewed_first=3,
        bought={"u1": {"hot"}},
        cold_start=True,
    )
    state = _cold_state({"hot": 9, "warm": 4})
    answer = recommend(
        {"user_id": "u1", "is_new_user": True, "recent_views": []}, state
    )
    assert answer[:2] == ["warm", "p_00"]


def test_cold_start_leaves_returning_shoppers_to_the_usual_ranking():
    from dades_huzz.model import category_best_sellers

    kwargs = {
        "category_of": {"v_last": "electronics"},
        "ranked_by_category": {"electronics": ["e_1", "e_2"]},
        "keep_viewed": True,
        "viewed_first": 3,
    }
    state = _cold_state({"hot": 9}, extra={"e_1", "e_2", "v_last"})
    request = {"is_new_user": False, "recent_views": [{"product_id": "v_last"}]}
    with_rule = category_best_sellers(**kwargs, cold_start=True)(request, state)
    assert with_rule == category_best_sellers(**kwargs)(request, state)


def test_a_returning_shopper_without_views_gets_their_favourite_categories():
    from dades_huzz.model import category_best_sellers

    # Tati Apocalypse: returning shoppers without views convert at 0.1 % on the overall best sellers;
    # their history says which categories they like
    recommend = category_best_sellers(
        category_of={},
        ranked_by_category={"toys": ["t_1", "t_2"], "books": ["b_1"]},
        keep_viewed=True,
        profiles={"u_1": {"toys": 0.75, "books": 0.25}},
    )
    state = _state(extra={"t_1", "t_2", "b_1"})
    answer = recommend({"user_id": "u_1", "recent_views": []}, state)
    # toys rank k costs (k+1)/(0.75 w), books (k+1)/(0.25 w): t_1 1.3/w, t_2 2.7/w, b_1 4/w
    assert answer[:4] == ["t_1", "t_2", "b_1", "p_00"]
    assert len(set(answer)) == 10


def test_the_profile_blends_with_the_category_viewed_last_at_half_weight():
    from dades_huzz.model import category_best_sellers

    recommend = category_best_sellers(
        category_of={"v_last": "electronics"},
        ranked_by_category={
            "electronics": ["e_1", "e_2", "e_3"],
            "toys": ["t_1", "t_2"],
        },
        keep_viewed=True,
        profiles={"u_1": {"toys": 1.0}},
        profile_weight=0.5,
    )
    state = _state(extra={"e_1", "e_2", "e_3", "t_1", "t_2", "v_last"})
    request = {"user_id": "u_1", "recent_views": [{"product_id": "v_last"}]}
    # electronics scores 1 (viewed last), toys 0.5: rank k costs k+1 and 2(k+1); a tie goes to the
    # higher-scoring category
    assert recommend(request, state)[:5] == ["e_1", "e_2", "t_1", "e_3", "t_2"]


def test_a_shopper_without_a_profile_gets_exactly_terminator():
    from dades_huzz.model import category_best_sellers

    signals = {
        "category_of": {"v_last": "electronics"},
        "ranked_by_category": {"electronics": ["e_1", "v_last", "e_2"]},
    }
    terminator = category_best_sellers(**signals, keep_viewed=True)
    apocalypse = category_best_sellers(
        **signals, keep_viewed=True, profiles={"u_other": {"toys": 1.0}}
    )
    state = _state(extra={"e_1", "e_2", "v_last"})
    for request in (
        {"user_id": "u_new", "recent_views": [{"product_id": "v_last"}]},
        {"user_id": "u_new", "recent_views": []},
    ):
        assert apocalypse(request, state) == terminator(request, state)


def test_armageddon_puts_viewed_products_on_top_of_the_profile_blend():
    from dades_huzz.model import category_best_sellers

    # Tati Armageddon = Ultimatum + Apocalypse: live, a viewed product in slots 1-3 sold 2.2 % against
    # 0.09 % for the rest, and a returning shopper's favourite category sold ~4x the one viewed last
    recommend = category_best_sellers(
        category_of={"v_last": "electronics"},
        ranked_by_category={"electronics": ["e_1", "v_last", "e_2"], "toys": ["t_1"]},
        keep_viewed=True,
        viewed_first=3,
        profiles={"u_1": {"toys": 1.0}},
    )
    state = _state(extra={"e_1", "e_2", "t_1", "v_last"})
    request = {"user_id": "u_1", "recent_views": [{"product_id": "v_last"}]}
    # after v_last: at the default weight 3 the favourite toys go first (t_1 costs 1/3), then
    # electronics e_1 costs 1, e_2 costs 3 (v_last, rank 2, is already on top)
    assert recommend(request, state)[:5] == ["v_last", "t_1", "e_1", "e_2", "p_00"]


def test_products_the_shopper_already_bought_are_left_out():
    from dades_huzz.model import category_best_sellers

    # the organisers (Discord, Sat 17:09): a shopper who already bought a product is much less likely to
    # buy it again; live, 31 % of our answers showed one, 10 % in slot 1
    recommend = category_best_sellers(
        category_of={"v_last": "electronics"},
        ranked_by_category={"electronics": ["e_bought", "e_1", "v_last", "e_2"]},
        keep_viewed=True,
        viewed_first=3,
        bought={"u_1": {"e_bought", "v_last", "p_00"}},
    )
    state = _state(extra={"e_bought", "e_1", "e_2", "v_last"})
    request = {"user_id": "u_1", "recent_views": [{"product_id": "v_last"}]}
    answer = recommend(request, state)
    assert answer[:3] == ["e_1", "e_2", "p_01"]
    assert not {"e_bought", "v_last", "p_00"} & set(answer)
    assert len(set(answer)) == 10

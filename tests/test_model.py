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

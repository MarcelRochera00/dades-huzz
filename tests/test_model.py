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


def _blank_profile_state():
    # five books and five toys per price step of 10; the trend ranks the dearer ones higher
    books = {f"b{i}": 10.0 * i for i in range(1, 6)}
    toys = {f"t{i}": 10.0 * i for i in range(1, 6)}
    trend = {
        "b5": 9,
        "b4": 8,
        "b3": 7,
        "b2": 6,
        "b1": 5,
        "t5": 4,
        "t4": 3,
        "t3": 2,
        "t2": 1,
    }
    state = _cold_state(trend, extra={*books, *toys})
    category = {p: "Books & Media" for p in books} | {p: "Toys & Baby" for p in toys}
    return State(**{**vars(state), "category": category, "price": books | toys})


def _blank_request(device):
    return {
        "is_new_user": True,
        "recent_views": [],
        "context": {"device": device, "page": "home"},
    }


def _sold(**per_category):
    # one shopper per purchase in the last 15 minutes, cycling through products 1-5: _sold(b=3) buys b1, b2, b3
    return {
        f"x_{prefix}_{i}": frozenset({f"{prefix}{(i - 1) % 5 + 1}"})
        for prefix, n in per_category.items()
        for i in range(1, n + 1)
    }


def test_a_blank_android_shopper_without_a_leading_category_gets_no_product_from_the_dearest_fifth():
    # books and toys sell the same: no category leads, so all 10 slots follow what android buys
    # (2 books, 1 toy). Android leaves out each category's dearest 20 %: b5 and t5 never show
    state = _blank_profile_state()
    state = State(**{**vars(state), "recent_purchases": _sold(b=4, t=4)})
    answer = _cold_recommend({})(_blank_request("android"), state)
    assert answer == ["b4", "b3", "t4", "b2", "b1", "t3", "t2", "p_00", "p_01", "p_02"]


def test_a_blank_shopper_gives_the_leading_category_its_slots_first():
    # toys sell 70 % and lead books by 40 points: toys take 5 slots on top. On ios only the dearest
    # 40 % of each category shows, so the toys block holds t5 and t4, then books by what ios buys
    state = _blank_profile_state()
    state = State(**{**vars(state), "recent_purchases": _sold(t=7, b=3)})
    for device in ("ios", "web"):
        answer = _cold_recommend({})(_blank_request(device), state)
        assert answer[:5] == ["t5", "t4", "b5", "b4", "p_00"], device
        assert len(set(answer)) == 10


def test_the_leading_category_gets_slots_by_its_share_of_the_last_15_minutes_sales():
    from dades_huzz.model import best_selling_category

    def leader(**sold):
        return best_selling_category(_sold(**sold), lambda p: p[0])

    assert leader(a=50, b=45, c=5) is None  # leads by 5 points only
    assert leader(a=35, b=20, c=15, d=15, e=15) == ("a", 3)
    assert leader(a=45, b=25, c=30) == ("a", 4)
    assert leader(a=65, b=35) == ("a", 5)
    assert leader(a=85, b=15) == ("a", 8)
    assert (
        leader(a=14, w=2, **{k: 4 for k in "bcdefghijklmnopqrstuv"}) is None
    )  # under 15 %
    assert leader() is None


def test_cold_start_splits_the_list_by_the_share_of_views_per_category():
    # 3 of 5 views are toys and 2 electronics: 6 toys slots, then 4 electronics slots. Each block lists
    # the products viewed in it, latest first, then that category's trend; a short block is filled at the end
    recommend = _cold_recommend(
        {"t_v1": "toys", "t_v2": "toys", "e_v1": "electronics", "e_v2": "electronics"}
    )
    trend = {"t_1": 9, "e_1": 8, "t_2": 7, "e_2": 6, "e_3": 5, "t_3": 4}
    category = {p: "toys" if p.startswith("t") else "electronics" for p in trend}
    state = _cold_state(trend, extra={"t_v1", "t_v2", "e_v1", "e_v2"})
    state = State(**{**vars(state), "category": category})
    views = ["t_v1", "e_v1", "t_v1", "e_v2", "t_v2"]
    request = {"is_new_user": True, "recent_views": [{"product_id": p} for p in views]}
    assert recommend(request, state) == [
        *["t_v2", "t_v1", "t_1", "t_2", "t_3"],  # toys block: 5 of its 6 slots found
        *["e_v2", "e_v1", "e_1", "e_2"],
        "e_3",
    ]


def test_cold_start_breaks_ties_by_the_most_recent_view():
    # one view in each of four categories: 2.5 slots each, the two leftover slots go to the categories
    # viewed last
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
        *["a_v", "a_0"],
    ]


def test_a_cold_shopper_always_sees_what_they_carted_first():
    # e_c is carted in a viewed category: it opens the electronics block. z_c is carted in a category
    # they did not view: it still shows, on top
    recommend = _cold_recommend({"t_v": "toys", "e_v": "electronics"})
    trend = {"t_1": 9, "e_1": 8, "t_2": 7, "e_2": 6}
    category = {p: "toys" if p.startswith("t") else "electronics" for p in trend}
    category |= {"e_c": "electronics", "z_c": "garden"}
    state = _cold_state(trend, extra={"t_v", "e_v", "e_c", "z_c"})
    state = State(
        **{
            **vars(state),
            "category": category,
            "shopper_carted": {"u1": frozenset({"e_c", "z_c"})},
        }
    )
    views = ["t_v", "e_v"]
    request = {
        "user_id": "u1",
        "is_new_user": True,
        "recent_views": [{"product_id": p} for p in views],
    }
    assert recommend(request, state)[:7] == [
        "z_c",
        *["e_c", "e_v", "e_1", "e_2", "t_v", "t_1"],
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


def _subcategory_state():
    products = [f"t_{i}" for i in range(12)] + ["v_0"]
    return State(
        available=frozenset(products) | {"x_0", "x_1"},
        price={},
        new_products=frozenset(),
        fallback=("x_0", "x_1"),
        category={p: "Toys" for p in products},
        subcategory={
            **{f"t_{i}": "Dolls" if i % 3 == 0 else "Cars" for i in range(12)},
            "v_0": "Dolls",
        },
    )


def _terminator_like(request, state):
    """Stands in for any version: the category's products by rank, viewed ones kept."""
    return [f"t_{i}" for i in range(10)]


def test_a_new_shopper_gets_two_best_sellers_of_the_subcategory_viewed_last_on_top():
    from dades_huzz.model import subcategory_first

    ranked = {"Toys": [f"t_{i}" for i in range(12)]}
    recommend = subcategory_first(_terminator_like, ranked)
    request = {"is_new_user": True, "recent_views": [{"product_id": "v_0"}]}
    answer = recommend(request, _subcategory_state())
    # t_0, t_3 are the category's two best Dolls; the rest keep the base order
    assert answer == [
        "t_0",
        "t_3",
        "t_1",
        "t_2",
        "t_4",
        "t_5",
        "t_6",
        "t_7",
        "t_8",
        "t_9",
    ]


def test_returning_shoppers_and_shoppers_without_views_keep_the_base_answer():
    from dades_huzz.model import subcategory_first

    ranked = {"Toys": [f"t_{i}" for i in range(12)]}
    recommend = subcategory_first(_terminator_like, ranked)
    base = _terminator_like({}, _subcategory_state())
    returning = {"is_new_user": False, "recent_views": [{"product_id": "v_0"}]}
    no_views = {"is_new_user": True, "recent_views": []}
    assert recommend(returning, _subcategory_state()) == base
    assert recommend(no_views, _subcategory_state()) == base


def test_the_subcategory_picks_skip_viewed_and_unavailable_products():
    from dades_huzz.model import subcategory_first

    ranked = {"Toys": ["v_0", "t_0", "t_3", "t_6", "t_1"]}
    state = _subcategory_state()
    state = State(
        available=state.available - {"t_0"},
        price={},
        new_products=frozenset(),
        fallback=state.fallback,
        category=state.category,
        subcategory=state.subcategory,
    )
    recommend = subcategory_first(_terminator_like, ranked)
    request = {"is_new_user": True, "recent_views": [{"product_id": "v_0"}]}
    assert recommend(request, state)[:2] == ["t_3", "t_6"]
    assert len(recommend(request, state)) == 10


def _lauri_state(**changes):
    products = [f"a_{i}" for i in range(12)] + [f"b_{i}" for i in range(12)]
    fields = {
        "available": frozenset(products),
        "price": dict.fromkeys(products, 10.0),
        "new_products": frozenset(),
        "fallback": tuple(products),
        "category": {p: p[0] for p in products},
        "subcategory": {p: p[0] for p in products},
    }
    return State(**{**fields, **changes})


def _lauri(weights=None, **signals):
    from dades_huzz.features import LAURI_FEATURES
    from dades_huzz.model import lauri

    chosen = {name: 0.0 for name in LAURI_FEATURES} | (weights or {})
    segment = {"weights": [chosen[name] for name in LAURI_FEATURES]}
    ranked = {
        "a": [f"a_{i}" for i in range(12)],
        "b": [f"b_{i}" for i in range(12)],
    }
    return lauri(
        {"new": segment, "returning": segment},
        ranked_by_category=signals.pop("ranked_by_category", ranked),
        history_sales=signals.pop("history_sales", {}),
        live_sales=signals.pop("live_sales", {}),
        median_log_price={},
        **signals,
    )


def test_lauri_answers_ten_distinct_available_products():
    state = _lauri_state(available=frozenset(f"a_{i}" for i in range(11)))
    answer = _lauri()({"request_id": "r", "user_id": "u", "recent_views": []}, state)
    assert len(answer) == 10 == len(set(answer))
    assert set(answer) <= state.available


def test_lauri_ranks_by_its_weights():
    request = {
        "request_id": "r",
        "user_id": "u",
        "recent_views": [{"product_id": "b_7"}],
    }
    answer = _lauri({"same_category": 1.0, "viewed": 5.0})(request, _lauri_state())
    assert answer[0] == "b_7"
    assert all(product.startswith("b_") for product in answer)


def test_lauri_prefers_what_sells_live_when_that_weighs():
    request = {"request_id": "r", "user_id": "u", "recent_views": []}
    answer = _lauri({"log_live_sales": 1.0}, live_sales={"b_5": 50, "a_4": 5})(
        request, _lauri_state()
    )
    assert answer[:2] == ["b_5", "a_4"]


def test_lauri_never_shows_what_the_shopper_bought_before_or_just_now():
    state = _lauri_state(recent_purchases={"u": frozenset({"a_1"})})
    request = {
        "request_id": "r",
        "user_id": "u",
        "recent_views": [{"product_id": "a_0"}],
    }
    answer = _lauri({"viewed": 5.0}, bought={"u": frozenset({"a_0"})})(request, state)
    assert "a_0" not in answer and "a_1" not in answer
    assert len(answer) == 10


def test_lauri_uses_the_segment_of_the_shopper():
    from dades_huzz.features import LAURI_FEATURES
    from dades_huzz.model import lauri

    def only(name):
        return {"weights": [float(feature == name) for feature in LAURI_FEATURES]}

    recommend = lauri(
        {"new": only("log_live_sales"), "returning": only("log_history_sales")},
        ranked_by_category={},
        history_sales={"a_3": 9},
        live_sales={"b_3": 9},
        median_log_price={},
    )
    request = {"request_id": "r", "user_id": "u", "recent_views": []}
    assert recommend({**request, "is_new_user": True}, _lauri_state())[0] == "b_3"
    assert recommend({**request, "is_new_user": False}, _lauri_state())[0] == "a_3"


def test_lauri_answers_the_fallback_when_it_fails():
    state = _lauri_state()
    recommend = _lauri(ranked_by_category=None)  # reading the ranking raises
    answer = recommend(
        {"request_id": "r", "recent_views": [{"product_id": "a_0"}]}, state
    )
    assert answer == list(state.fallback[:10])


def test_fit_lauri_keeps_the_slot_out_of_the_feature_weights():
    import numpy as np

    from dades_huzz.features import LAURI_FEATURES, LauriTrainingRows
    from dades_huzz.model import fit_lauri, lauri_scores

    rng = np.random.default_rng(0)
    n = 4000
    slot = np.tile(np.arange(10), n)
    features = np.zeros((n * 10, len(LAURI_FEATURES)))
    features[:, 0] = rng.random(n * 10) < 0.3  # viewed: truly raises purchases
    features[:, 7] = (
        10 - slot + rng.normal(0, 0.5, n * 10)
    )  # popularity: only follows the slot
    chance = 1 / (1 + np.exp(-(-1.0 + 2.0 * features[:, 0] - 0.4 * slot)))
    rows = LauriTrainingRows(
        features=features,
        slot=slot,
        owned=np.zeros(n * 10),
        purchased=(rng.random(n * 10) < chance).astype(float),
        clicked=np.zeros(n * 10),
        request=np.repeat(np.arange(n), 10),
        ts_ms=np.zeros(n * 10),
        is_new_user=np.repeat(rng.random(n) < 0.5, 10),
    )
    fitted = fit_lauri(rows, np.ones(n * 10, dtype=bool), rows.purchased, l2=1.0)
    for segment in ("new", "returning"):
        weights = dict(zip(LAURI_FEATURES, fitted[segment]["weights"], strict=True))
        assert 1.5 < weights["viewed"] < 2.5
        assert abs(weights["log_history_sales"]) < 0.2
        assert fitted[segment]["slot"][-1] < -2
    shown, served = lauri_scores(fitted, rows)
    assert shown.shape == served.shape == (n * 10,)


def test_lauri_weights_round_trip_through_the_scratch_table():
    from dades_huzz.model import load_lauri_weights, save_lauri_weights

    class FakeRawTree:
        team = "team_xx"

        def __init__(self):
            self.rows = []

        def insert(self, table, rows, timeout=2):
            assert table == "scratch"
            self.rows += rows

        def query(self, sql, timeout=10):
            assert "kind::String = 'lauri_weights'" in sql and "'lauri-test'" in sql
            return [{"weights": self.rows[-1]["weights"]}] if self.rows else []

    fake = FakeRawTree()
    try:
        load_lauri_weights(fake, "lauri-test")
        raise AssertionError("expected LookupError")
    except LookupError:
        pass
    weights = {"new": {"weights": [1.0, 2.0]}, "returning": {"weights": [3.0, 4.0]}}
    save_lauri_weights(fake, "lauri-test", weights, ts_ms=1)
    assert (
        fake.rows[0]["kind"] == "lauri_weights" and fake.rows[0]["name"] == "lauri-test"
    )
    assert load_lauri_weights(fake, "lauri-test") == weights


def test_lauri_never_pads_with_an_unavailable_product():
    # Only 3 products are available, so the answer is padded from the fallback, which here still lists
    # products that just went out of stock (the fallback and the stock refresh at different moments).
    available = frozenset({"a_0", "a_1", "b_0"})
    state = _lauri_state(available=available)
    answer = _lauri()({"request_id": "r", "user_id": "u", "recent_views": []}, state)
    assert set(answer) <= available


def test_todays_views_count_as_a_profile_for_a_shopper_without_history():
    from dataclasses import replace

    from dades_huzz.model import category_best_sellers

    # Tati Omega+: a new shopper has no history, but #54's State counts the categories they viewed today
    # (an add-to-cart counts 3): those join the category viewed last like a history profile
    kwargs = {
        "category_of": {"v_last": "electronics"},
        "ranked_by_category": {"electronics": ["e_1", "e_2"], "toys": ["t_1", "t_2"]},
        "keep_viewed": True,
    }
    state = replace(
        _state(extra={"e_1", "e_2", "t_1", "t_2", "v_last"}),
        shopper_categories={"u_new": {"toys": 3, "electronics": 1}},
    )
    request = {"user_id": "u_new", "recent_views": [{"product_id": "v_last"}]}
    # today's shares: toys 0.75, electronics 0.25; at w = 3, toys 2.25 and electronics 1 + 0.75 = 1.75
    answer = category_best_sellers(**kwargs, day_weight=3.0)(request, state)
    assert answer[:4] == ["t_1", "e_1", "t_2", "e_2"]
    # without day_weight, exactly Terminator
    assert category_best_sellers(**kwargs)(request, state)[:3] == ["e_1", "e_2", "p_00"]


def test_todays_views_add_to_the_history_profile():
    from dataclasses import replace

    from dades_huzz.model import category_best_sellers

    recommend = category_best_sellers(
        category_of={},
        ranked_by_category={"toys": ["t_1"], "books": ["b_1"]},
        keep_viewed=True,
        profiles={"u_1": {"toys": 1.0}},
        profile_weight=1.0,
        day_weight=3.0,
    )
    state = replace(
        _state(extra={"t_1", "b_1"}), shopper_categories={"u_1": {"books": 2}}
    )
    # toys 1 (history), books 3 (today): books first
    assert recommend({"user_id": "u_1", "recent_views": []}, state)[:2] == [
        "b_1",
        "t_1",
    ]


def test_lauri_colossus_brings_in_and_ranks_the_shoppers_day():
    products = [f"a_{i}" for i in range(12)] + [f"b_{i}" for i in range(12)]
    state = _lauri_state(
        available=frozenset(products) | {"c_cart", "c_seen"},
        category={p: p[0] for p in [*products, "c_cart", "c_seen"]},
        shopper_categories={"u": {"b": 5, "a": 1}},
        shopper_carted={"u": frozenset({"c_cart"})},
        shopper_viewed={"u": ("c_seen",)},
    )
    request = {"request_id": "r", "user_id": "u", "recent_views": []}
    weights = {"day_carted": 5.0, "day_viewed": 3.0, "day_category_share": 1.0}
    answer = _lauri(weights, day=True)(request, state)
    assert answer[:2] == ["c_cart", "c_seen"]
    assert all(product.startswith("b_") for product in answer[2:])
    assert _lauri(weights, day=True)({**request, "user_id": "other"}, state) == _lauri(
        weights
    )(request, state)


def test_lauri_titan_plus_brings_in_the_shoppers_unbought_history_carts():
    products = [f"a_{i}" for i in range(12)] + [f"b_{i}" for i in range(12)]
    state = _lauri_state(
        available=frozenset(products) | {"c_cart", "c_bought"},
        category={p: p[0] for p in [*products, "c_cart", "c_bought"]},
    )
    request = {"request_id": "r", "user_id": "u", "recent_views": []}
    carts = {"u": ("c_bought", "c_cart")}
    recommend = _lauri(
        {"history_carted": 5.0}, carts=carts, bought={"u": frozenset({"c_bought"})}
    )
    answer = recommend(request, state)
    assert answer[0] == "c_cart"
    assert "c_bought" not in answer
    # without carts, the cart never reaches the pool
    assert "c_cart" not in _lauri({"history_carted": 5.0})(request, state)


def test_lauri_takes_deeper_into_each_category_with_a_larger_cap():
    deep = [f"a_{i}" for i in range(40)]
    state = _lauri_state(
        available=frozenset(deep), category=dict.fromkeys(deep, "a"), fallback=()
    )
    request = {"request_id": "r", "user_id": "u", "recent_views": []}
    signals = {
        "ranked_by_category": {"a": deep},
        "history_sales": {"a_35": 99},
        "profiles": {"u": {"a": 1.0}},
    }
    weights = {"log_history_sales": 1.0}
    assert "a_35" not in _lauri(weights, **signals)(request, state)
    assert _lauri(weights, per_category=100, **signals)(request, state)[0] == "a_35"


def test_lauri_titan_ignores_the_day_and_keeps_its_thirteen_weights():
    from dades_huzz.model import lauri

    state = _lauri_state(
        shopper_categories={"u": {"b": 5}},
        shopper_carted={"u": frozenset({"b_9"})},
        shopper_viewed={"u": ("b_8",)},
    )
    request = {"request_id": "r", "user_id": "u", "recent_views": []}
    thirteen = {"weights": [0.0] * 7 + [1.0] + [0.0] * 5}  # log_history_sales only
    recommend = lauri(
        {"new": thirteen, "returning": thirteen},
        ranked_by_category={},
        history_sales={"a_3": 9, "b_3": 1},
        live_sales={},
        median_log_price={},
    )
    assert recommend(request, state)[:2] == ["a_3", "b_3"]
    assert not {"b_8", "b_9"} & set(recommend(request, state))
    assert recommend(request, state) == recommend(request, _lauri_state())


def test_fit_lauri_on_some_features_leaves_the_others_at_zero():
    import numpy as np

    from dades_huzz.features import (
        LAURI_CART_FEATURES,
        LAURI_DAY_FEATURES,
        LAURI_FEATURES,
        LauriTrainingRows,
    )
    from dades_huzz.model import fit_lauri, lauri_scores

    rng = np.random.default_rng(1)
    n = 2000
    features = rng.random((n * 10, len(LAURI_FEATURES)))
    carted = LAURI_FEATURES.index("day_carted")
    chance = 1 / (1 + np.exp(-(-2.0 + 2.0 * features[:, carted])))  # day_carted matters
    rows = LauriTrainingRows(
        features=features,
        slot=np.tile(np.arange(10), n),
        owned=np.zeros(n * 10),
        purchased=(rng.random(n * 10) < chance).astype(float),
        clicked=np.zeros(n * 10),
        request=np.repeat(np.arange(n), 10),
        ts_ms=np.zeros(n * 10),
        is_new_user=np.repeat(rng.random(n) < 0.5, 10),
    )
    everything = np.ones(n * 10, dtype=bool)
    titan = [
        f for f in LAURI_FEATURES if f not in LAURI_DAY_FEATURES + LAURI_CART_FEATURES
    ]
    without = fit_lauri(rows, everything, rows.purchased, l2=1.0, features=titan)
    full = fit_lauri(rows, everything, rows.purchased, l2=1.0)
    for segment in ("new", "returning"):
        assert len(without[segment]["weights"]) == len(LAURI_FEATURES)
        for name in LAURI_DAY_FEATURES:
            assert without[segment]["weights"][LAURI_FEATURES.index(name)] == 0.0
        assert len(without[segment]["slot"]) == 9
        assert 1.5 < full[segment]["weights"][carted] < 2.5
    old = {s: {**w, "weights": w["weights"][:13]} for s, w in without.items()}
    assert np.allclose(lauri_scores(old, rows)[0], lauri_scores(without, rows)[0])


def _cart_state(**changes):
    base = {
        "available": frozenset(
            [f"t_{i}" for i in range(12)] + ["c_toy", "c_book", "c_old", "x_0"]
        ),
        "price": {},
        "new_products": frozenset(),
        "fallback": ("x_0",),
        "category": {
            "c_toy": "Toys",
            "v_0": "Toys",
            "c_book": "Books",
            "c_old": "Books",
        },
    }
    return State(**{**base, **changes})


def test_a_returning_shopper_gets_their_carted_products_on_top():
    from dades_huzz.model import cart_first

    recommend = cart_first(_terminator_like, {"u_1": ["c_book", "c_old"]})
    answer = recommend({"user_id": "u_1", "is_new_user": False}, _cart_state())
    assert answer == ["c_book", "c_old", *[f"t_{i}" for i in range(8)]]


def test_carted_products_of_the_category_viewed_last_go_first_and_at_most_three():
    from dades_huzz.model import cart_first

    carts = {"u_1": ["c_book", "c_old", "t_11", "c_toy"]}
    recommend = cart_first(_terminator_like, carts)
    request = {
        "user_id": "u_1",
        "is_new_user": False,
        "recent_views": [{"product_id": "v_0"}],
    }
    assert recommend(request, _cart_state())[:4] == ["c_toy", "c_book", "c_old", "t_0"]


def test_carted_picks_skip_unavailable_and_just_bought_and_the_answer_drops_just_bought():
    from dades_huzz.model import cart_first

    state = _cart_state(
        available=_cart_state().available - {"c_old"},
        recent_purchases={"u_1": frozenset({"c_book", "t_0"})},
    )
    recommend = cart_first(_terminator_like, {"u_1": ["c_book", "c_old", "c_toy"]})
    answer = recommend({"user_id": "u_1", "is_new_user": False}, state)
    assert answer == ["c_toy", *[f"t_{i}" for i in range(1, 10)]]
    # a short base answer is padded from the fallback
    short = cart_first(lambda r, s: ["t_0", "t_1"], {"u_1": ["c_toy"]})
    assert short({"user_id": "u_1", "is_new_user": False}, state) == [
        "c_toy",
        "t_1",
        "x_0",
    ]


def test_new_shoppers_and_shoppers_without_carts_keep_the_base_answer():
    from dades_huzz.model import cart_first

    recommend = cart_first(_terminator_like, {"u_1": ["c_book"]})
    base = _terminator_like({}, _cart_state())
    assert recommend({"user_id": "u_1", "is_new_user": True}, _cart_state()) == base
    assert recommend({"user_id": "u_2", "is_new_user": False}, _cart_state()) == base


def test_cold_first_sends_cold_requests_to_the_cold_answer_and_the_rest_to_the_base():
    from dataclasses import replace

    from dades_huzz.model import cold_first

    def base(request, state):
        return ["base"]

    def cold(request, state):
        return ["cold"]

    recommend = cold_first(base, cold)
    state = replace(_lauri_state(), new_products=frozenset({"a_new"}))
    returning = {"user_id": "u", "is_new_user": False, "recent_views": []}
    assert recommend({**returning, "is_new_user": True}, state) == ["cold"]
    assert recommend(
        {**returning, "recent_views": [{"product_id": "a_new"}]}, state
    ) == ["cold"]
    assert recommend(returning, state) == ["base"]


def test_hot_first_puts_the_hottest_subcategorys_live_best_sellers_in_slots_2_and_3():
    from dataclasses import replace

    from dades_huzz.model import hot_first

    products = [f"a_{i}" for i in range(12)] + [f"b_{i}" for i in range(12)]
    state = replace(
        _lauri_state(
            subcategory={
                p: "kettles" if p in ("b_7", "b_9", "b_3") else p[0] for p in products
            }
        ),
        hot_subcategories={"kettles": 6.3, "a": 2.1},
        recent_purchases={"u": frozenset({"b_3"})},
    )
    ranked = {"a": [f"a_{i}" for i in range(12)], "b": ["b_3", "b_9", "b_0", "b_7"]}

    def base(request, state):
        return [f"a_{i}" for i in range(10)]

    recommend = hot_first(base, ranked, bought={"u": frozenset({"b_9"})})
    answer = recommend({"user_id": "u", "recent_views": []}, state)
    # b_3 bought just now and b_9 in the history are skipped; only b_7 is left of the hottest
    assert answer[:3] == ["a_0", "b_7", "a_1"]
    assert len(answer) == 10 == len(set(answer))
    calm = replace(state, hot_subcategories={})
    assert recommend({"user_id": "u", "recent_views": []}, calm) == base(None, None)


def test_titan_max_shape_cold_goes_to_the_cold_rule_and_returning_gets_the_trend():
    """lauri-titan-max is cold_first(hot_first(Titan+ 100 deep, ...), cold rule): a cold request never sees
    the trend injection, a returning one does."""
    from dataclasses import replace

    from dades_huzz.model import cold_first, hot_first

    products = [f"a_{i}" for i in range(12)] + ["b_0", "b_1"]
    state = replace(
        _lauri_state(
            subcategory={p: "kettles" if p[0] == "b" else "a" for p in products}
        ),
        hot_subcategories={"kettles": 4.0},
    )

    def titan_plus_100(request, state):
        return [f"a_{i}" for i in range(10)]

    def cold_rule(request, state):
        return [f"a_{i}" for i in range(11, 1, -1)]

    recommend = cold_first(hot_first(titan_plus_100, {"b": ["b_0", "b_1"]}), cold_rule)
    returning = {"user_id": "u", "is_new_user": False, "recent_views": []}
    assert recommend({**returning, "is_new_user": True}, state) == cold_rule(None, None)
    assert recommend(returning, state)[:3] == ["a_0", "b_0", "b_1"]


def _with(state, **fields):
    return State(**{**vars(state), **fields})


def test_a_blank_shopper_with_a_day_gets_their_days_categories_not_the_devices():
    # nothing in recent_views, but today they viewed toys 6 times and books twice: toys take 8 slots,
    # books 2, instead of what ios buys (books first). Took over from lane C (#60); measured in #5:
    # the day's top 3 categories hold 72 % of blank new shoppers' purchases
    state = _with(
        _blank_profile_state(),
        shopper_categories={"u1": {"Toys & Baby": 6, "Books & Media": 2}},
    )
    answer = _cold_recommend({})({**_blank_request("ios"), "user_id": "u1"}, state)
    assert answer[:6] == ["t5", "t4", "t3", "t2", "b5", "b4"]
    assert len(set(answer)) == 10


def test_a_blank_shopper_sees_their_cart_then_their_day_views_first_in_each_block():
    state = _with(
        _blank_profile_state(),
        shopper_categories={"u1": {"Toys & Baby": 6, "Books & Media": 2}},
        shopper_carted={"u1": frozenset({"t1"})},
        shopper_viewed={"u1": ("t3", "b2")},
    )
    answer = _cold_recommend({})({**_blank_request("ios"), "user_id": "u1"}, state)
    assert answer[:3] == ["t1", "t3", "t5"]
    assert "b2" in answer


def test_a_hot_subcategory_leads_its_category_block():
    # t2 belongs to a subcategory selling 4x its day share right now (State.hot_subcategories, #64)
    state = _with(
        _blank_profile_state(),
        shopper_categories={"u1": {"Toys & Baby": 6}},
        subcategory={"t2": "Plushies"},
        hot_subcategories={"Plushies": 4.0},
    )
    answer = _cold_recommend({})({**_blank_request("ios"), "user_id": "u1"}, state)
    assert answer[:3] == ["t2", "t5", "t4"]


def test_a_blank_shopper_without_a_day_keeps_the_device_answer():
    state = _with(
        _blank_profile_state(), recent_purchases=_sold(t=7, b=3), shopper_categories={}
    )
    answer = _cold_recommend({})({**_blank_request("ios"), "user_id": "u1"}, state)
    assert answer[:5] == ["t5", "t4", "b5", "b4", "p_00"]


def test_a_cold_answer_has_ten_products_however_many_the_shopper_carted():
    # a shopper with 12 unbought carts: the cart goes first but the answer still has ANSWER_SIZE products
    # (on main it grew to the whole cart, and the loop had to cut it; #60)
    state = _with(
        _blank_profile_state(),
        shopper_categories={"u1": {"Toys & Baby": 6}},
        shopper_carted={
            "u1": frozenset(
                {*(f"b{i}" for i in range(1, 6)), *(f"t{i}" for i in range(1, 6))}
            )
            | {"p_01", "p_02"}
        },
    )
    answer = _cold_recommend({})({**_blank_request("ios"), "user_id": "u1"}, state)
    assert len(answer) == 10 == len(set(answer))

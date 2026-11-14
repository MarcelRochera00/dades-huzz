import math

import pytest

from dades_huzz.evaluation import slot1_ips, weighted_hit

ANSWER = [f"p_{i}" for i in range(10)]


def test_a_purchase_in_the_first_slot_is_worth_one():
    assert weighted_hit(ANSWER, {"p_0"}) == 1.0


def test_a_purchase_lower_down_is_worth_less():
    # slot 4 (rank 3): 1 / log2(3 + 2)
    assert weighted_hit(ANSWER, {"p_3"}) == pytest.approx(1 / math.log2(5))


def test_a_purchase_we_did_not_show_is_worth_nothing():
    assert weighted_hit(ANSWER, {"p_99"}) == 0.0


def test_several_purchases_count_the_best_placed_one():
    assert weighted_hit(ANSWER, {"p_5", "p_1"}) == pytest.approx(1 / math.log2(3))


def test_slot1_ips_reweights_the_matches_by_the_old_system_propensity():
    logged = [
        # our first pick matches the old slot 1 (shown with p=0.5) and was clicked: weight 2, reward 1
        {"shown": ["a", "x"], "propensity": [0.5, 0.1], "clicked": "a"},
        # matches (p=0.25), nothing clicked: weight 4, reward 0
        {"shown": ["b", "x"], "propensity": [0.25, 0.1], "clicked": None},
        # no match: we put "d" first, so this row tells us nothing
        {"shown": ["c", "x"], "propensity": [0.1, 0.1], "clicked": "c"},
    ]
    firsts = ["a", "b", "d"]
    result = slot1_ips(firsts, logged)
    assert result.ips == pytest.approx(2 / 3)
    assert result.snips == pytest.approx(2 / 6)
    assert result.matches == 2


def test_evaluate_runs_recommend_like_the_live_loop_and_averages_the_hits():
    from dades_huzz.data import State
    from dades_huzz.evaluation import evaluate

    fallback = tuple(f"p_{i}" for i in range(12))
    state = State(
        available=frozenset(fallback),
        price={},
        new_products=frozenset(),
        fallback=fallback,
    )

    def last_viewed_first(request, state):
        last = request["recent_views"][-1]["product_id"]
        return [last] + [p for p in state.fallback if p != last][:9]

    logged = {
        "shown": fallback[:10],
        "propensity": [0.5] * 10,
        "clicked": None,
        "purchased": "p_1",
    }
    cases = [
        # bought the product viewed last, which we put first: hit worth 1
        {
            "request": {"recent_views": [{"product_id": "p_11"}]},
            "bought": {"p_11"},
            "logged": logged,
        },
        # bought something we never showed: 0
        {
            "request": {"recent_views": [{"product_id": "p_11"}]},
            "bought": {"p_99"},
            "logged": logged,
        },
    ]
    report = evaluate(last_viewed_first, cases, state)
    assert report.cases == 2
    assert report.weighted_hit == pytest.approx(0.5)
    assert report.hit_rate == pytest.approx(0.5)
    # putting "p_11" first shifts every fallback product one slot down: no slot matches the log
    assert report.slate.matches == 0
    assert report.slate.ips == 0.0


def test_slate_ips_credits_purchases_where_our_slot_matches_the_logged_one():
    from dades_huzz.evaluation import slate_ips

    logged = [
        # we match both slots; the shopper bought "b" (p=0.04 -> weight 25, capped at 20)
        {"shown": ["a", "b"], "propensity": [0.5, 0.04], "purchased": "b"},
        # we only match "d", which was not bought; the purchase of "c" is not ours to claim
        {"shown": ["c", "d"], "propensity": [0.25, 0.1], "purchased": "c"},
    ]
    answers = [["a", "b"], ["x", "d"]]
    result = slate_ips(answers, logged, cap=20)
    assert result.ips == pytest.approx(10.0)
    assert result.matches == 3
    assert result.matched_purchases == 1
    assert slate_ips(answers, logged, cap=100).ips == pytest.approx(12.5)

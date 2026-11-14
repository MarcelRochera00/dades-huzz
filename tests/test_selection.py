import pytest

from dades_huzz.evaluation.selection import ArmResult, arm_results, choose, confirm


def test_choose_picks_the_cold_and_the_warm_arm_separately():
    # Worked example: cold share 40 %. A alone 1.40, B alone 1.44,
    # A on cold requests + B on the rest 0.4 * 2.0 + 0.6 * 1.4 = 1.64.
    arms = [
        ArmResult(
            "A",
            cold_requests=400,
            cold_conversion=2.0,
            warm_requests=600,
            warm_conversion=1.0,
        ),
        ArmResult(
            "B",
            cold_requests=400,
            cold_conversion=1.5,
            warm_requests=600,
            warm_conversion=1.4,
        ),
    ]
    choice = choose(arms)
    assert (choice.cold_arm, choice.warm_arm) == ("A", "B")
    assert choice.expected_conversion == pytest.approx(1.64)


def test_confirm_needs_a_lead_of_a_tenth_and_three_of_four_windows():
    three_of_four = [(2.0, 1.8), (1.9, 1.7), (1.6, 1.7), (2.1, 1.9)]
    assert confirm(choice=1.90, titan_plus=1.78, windows=three_of_four)
    assert not confirm(choice=1.87, titan_plus=1.78, windows=three_of_four)  # +0.09
    two_of_four = [(2.0, 1.8), (1.5, 1.7), (1.6, 1.7), (2.1, 1.9)]
    assert not confirm(choice=1.90, titan_plus=1.78, windows=two_of_four)


def test_confirm_counts_a_lead_of_exactly_a_tenth():
    # 2.3 - 2.2 is 0.0999... in floating point
    assert confirm(choice=2.3, titan_plus=2.2, windows=[(2.3, 2.2)] * 4)


def test_confirm_does_not_count_a_tied_window_as_won():
    tied = [(2.0, 2.0), (2.0, 2.0), (2.4, 2.0), (2.4, 2.0)]
    assert not confirm(choice=2.2, titan_plus=2.0, windows=tied)


def test_arm_results_derive_the_warm_requests_from_a_leaderboard_row():
    # Shape of one entry of `teams[i].versions` in /api/state?by=model.
    row = {
        "model_version": "lauri-titan-plus",
        "requests": 1000,
        "conversion": 1.6,
        "cold_requests": 400,
        "cold_conversion": 2.5,
        "revenue_per_request": 0.6,
        "first": 1794695100.0,
        "last": 1794698700.0,
    }
    (arm,) = arm_results([row])
    assert arm == ArmResult(
        "lauri-titan-plus",
        cold_requests=400,
        cold_conversion=2.5,
        warm_requests=600,
        warm_conversion=1.0,
    )


def test_arm_results_add_up_one_arm_over_several_windows():
    # The API serves at most 3 h per read, so 01:45-07:00 comes in two reads.
    first = {
        "model_version": "A",
        "requests": 1000,
        "conversion": 1.0,
        "cold_requests": 500,
        "cold_conversion": 1.0,
    }
    second = {
        "model_version": "A",
        "requests": 1000,
        "conversion": 2.0,
        "cold_requests": 500,
        "cold_conversion": 3.0,
    }
    (arm,) = arm_results([first, second])
    assert arm == ArmResult(
        "A",
        cold_requests=1000,
        cold_conversion=2.0,
        warm_requests=1000,
        warm_conversion=1.0,
    )

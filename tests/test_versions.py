import time

import pytest

from dades_huzz.data import State
from dades_huzz.serving.report import conversion_interval_pct
from dades_huzz.serving.versions import DEFAULT_SPLIT, VERSIONS, Split, parse_split

FALLBACK = tuple(f"p_{i:02d}" for i in range(20))
STATE = State(
    available=frozenset(FALLBACK), price={}, new_products=frozenset(), fallback=FALLBACK
)


def champion(request, state):
    return list(state.fallback[:10])


def challenger(request, state):
    return list(state.fallback[10:])


def split_of(**recommenders):
    return Split(recommenders, {name: 50 for name in recommenders})


def test_the_same_request_always_gets_the_same_version():
    for i in range(200):
        assert split_of(a=champion, b=challenger).version_for(f"r_{i}") == split_of(
            a=champion, b=challenger
        ).version_for(f"r_{i}")


def test_requests_are_shared_in_the_requested_proportions():
    split = Split({"a": champion, "b": challenger}, {"a": 70, "b": 30})
    share_a = (
        sum(split.version_for(f"r_{i:06d}") == "a" for i in range(20_000)) / 20_000
    )
    assert 0.68 < share_a < 0.72


def test_a_split_is_read_from_name_equals_share_pairs():
    assert parse_split("tati-0-bestsellers=50,tati=50") == {
        "tati-0-bestsellers": 50,
        "tati": 50,
    }


@pytest.mark.parametrize("text", ["tati", "a=0", "a=-5", "a=x", "", "a=50,a=50"])
def test_a_malformed_split_is_refused(text):
    with pytest.raises(ValueError):
        parse_split(text)


def test_a_challenger_that_misses_its_time_limit_gives_way_to_the_champion_for_that_shopper():
    def slow(request, state):
        time.sleep(1)
        return challenger(request, state)

    split = Split(
        {"champ": champion, "slow": slow},
        {"champ": 0 + 1, "slow": 1_000_000},
        budget_ms=50,
    )
    started = time.perf_counter()
    version, items, problem = split.recommend({"request_id": "r1"}, STATE)
    assert time.perf_counter() - started < 0.5
    assert (version, items, problem) == ("champ", champion(None, STATE), "timeout:slow")


def test_a_challenger_that_raises_gives_way_to_the_champion():
    def broken(request, state):
        raise ValueError("bug")

    split = Split(
        {"champ": champion, "broken": broken}, {"champ": 1, "broken": 1_000_000}
    )
    assert split.recommend({"request_id": "r1"}, STATE) == (
        "champ",
        champion(None, STATE),
        "model_error:broken",
    )


def test_a_version_slower_than_its_budget_on_average_is_taken_out_for_a_while():
    split = Split(
        {"champ": champion, "slow": challenger},
        {"champ": 50, "slow": 50},
        budget_ms=200,
    )
    slow_ids = [f"r_{i}" for i in range(500) if split.version_for(f"r_{i}") == "slow"]
    for _ in range(20):
        split.record("slow", elapsed_ms=350, now_ms=1_000)
    assert split.taken_out(now_ms=1_000) == {"slow"}
    assert all(
        split.version_for(request_id, now_ms=1_000) == "champ"
        for request_id in slow_ids
    )
    assert split.taken_out(now_ms=1_000 + 31 * 60_000) == set()


def test_a_few_slow_calls_do_not_take_a_version_out():
    split = Split(
        {"champ": champion, "b": challenger}, {"champ": 50, "b": 50}, budget_ms=200
    )
    for _ in range(18):
        split.record("b", elapsed_ms=20, now_ms=0)
    for _ in range(2):
        split.record("b", elapsed_ms=900, now_ms=0)
    assert split.taken_out(now_ms=0) == set()


def test_the_champion_is_never_taken_out():
    split = Split(
        {"champ": champion, "b": challenger}, {"champ": 50, "b": 50}, budget_ms=200
    )
    for _ in range(20):
        split.record("champ", elapsed_ms=500, now_ms=0)
    assert split.taken_out(now_ms=0) == set()


def test_a_take_out_made_before_a_restart_still_holds():
    split = Split(
        {"champ": champion, "b": challenger},
        {"champ": 50, "b": 50},
        out_until_ms={"b": 5_000},
    )
    assert split.taken_out(now_ms=4_000) == {"b"}
    assert split.taken_out(now_ms=6_000) == set()


def test_conversion_interval_matches_a_worked_example():
    low, high = conversion_interval_pct(purchases=10, requests=1000)
    assert round(low, 2) == 0.54
    assert round(high, 2) == 1.83


def test_the_default_split_names_only_known_versions():
    assert set(parse_split(DEFAULT_SPLIT)) <= set(VERSIONS)


def test_the_split_reads_back_as_written_champion_first():
    split = Split({"a": champion, "b": challenger}, {"a": 70, "b": 30})
    assert split.describe() == "a=70,b=30"
    assert parse_split(split.describe()) == {"a": 70, "b": 30}

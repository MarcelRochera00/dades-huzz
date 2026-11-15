from dades_huzz.serving.split import parse_split
from dades_huzz.serving.versions import DEFAULT_SPLIT, VERSIONS


def test_the_default_split_names_only_known_versions():
    assert set(parse_split(DEFAULT_SPLIT)) <= set(VERSIONS)


def _fake_versions(monkeypatch, loads):
    """Two versions that answer with their own name, counting how often each is loaded."""
    from dades_huzz.serving import versions

    def version(name):
        def load(rawtree):
            loads.append(name)
            return lambda request, state: [name]

        return load

    monkeypatch.setattr(
        versions,
        "VERSIONS",
        {"cold-arm": version("cold-arm"), "warm-arm": version("warm-arm")},
    )
    return versions


class _State:
    new_products = frozenset({"p_new"})


def test_a_pair_answers_cold_requests_with_its_first_arm_and_the_rest_with_its_second(
    monkeypatch,
):
    versions = _fake_versions(monkeypatch, [])
    pair = versions.load_version(None, "pair:cold-arm+warm-arm", {})
    new_shopper = {"is_new_user": True, "recent_views": []}
    viewed_new_product = {
        "is_new_user": False,
        "recent_views": [{"product_id": "p_new"}],
    }
    returning = {"is_new_user": False, "recent_views": [{"product_id": "p_old"}]}
    assert pair(new_shopper, _State) == ["cold-arm"]
    assert pair(viewed_new_product, _State) == ["cold-arm"]
    assert pair(returning, _State) == ["warm-arm"]


def test_a_pair_is_known_only_when_both_its_arms_are(monkeypatch):
    versions = _fake_versions(monkeypatch, [])
    assert versions.is_known("warm-arm")
    assert versions.is_known("pair:cold-arm+warm-arm")
    assert not versions.is_known("pair:cold-arm+nobody")
    assert not versions.is_known("pair:cold-arm")
    assert not versions.is_known("nobody")


class _NoTakeOuts:
    team = "team_x"

    def query(self, sql, timeout=None):
        return []


def test_a_split_loads_each_arm_once_even_when_a_pair_shares_one_with_the_champion(
    monkeypatch,
):
    loads = []
    versions = _fake_versions(monkeypatch, loads)
    split = versions.load_split(
        _NoTakeOuts(),
        {"warm-arm": 50, "pair:cold-arm+warm-arm": 50},
        lambda fn, what: fn(),
    )
    assert sorted(loads) == ["cold-arm", "warm-arm"]
    returning = {"is_new_user": False, "recent_views": []}
    pair = split.recommenders["pair:cold-arm+warm-arm"]
    assert pair(returning, _State) == split.recommenders["warm-arm"](returning, _State)


def test_a_split_refuses_a_pair_with_an_unknown_arm(monkeypatch):
    import pytest

    versions = _fake_versions(monkeypatch, [])
    with pytest.raises(ValueError, match="nobody"):
        versions.load_split(
            _NoTakeOuts(),
            {"warm-arm": 50, "pair:nobody+warm-arm": 50},
            lambda fn, what: fn(),
        )

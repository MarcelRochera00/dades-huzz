from dades_huzz.serving.split import parse_split
from dades_huzz.serving.versions import DEFAULT_SPLIT, VERSIONS


def test_the_default_split_names_only_known_versions():
    assert set(parse_split(DEFAULT_SPLIT)) <= set(VERSIONS)

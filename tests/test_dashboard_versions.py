from dades_huzz.dashboard_splits import HISTORICAL_SPLITS, parse_split
from dades_huzz.dashboard_versions import (
    SPARE_COLOURS,
    UNDESCRIBED,
    VERSION_STYLES,
    version_style,
)
from dades_huzz.serving.versions import VERSIONS


def test_every_live_and_historical_version_has_a_description():
    historical = {name for _, split in HISTORICAL_SPLITS for name in parse_split(split)}
    missing = sorted(
        name
        for name in set(VERSIONS) | historical
        if version_style(name).description == UNDESCRIBED
    )
    assert not missing, f"add these to VERSION_STYLES: {missing}"


def test_no_two_described_versions_share_a_colour():
    colours = [style.colour for style in VERSION_STYLES.values()]
    assert len(set(colours)) == len(colours)


def test_an_undescribed_version_keeps_the_same_spare_colour_and_is_not_grey():
    first = version_style("some-new-version")
    assert first == version_style("some-new-version")
    assert first.description == UNDESCRIBED
    assert first.colour not in {style.colour for style in VERSION_STYLES.values()}


def test_spare_colours_are_never_a_described_version_colour():
    described = {style.colour for style in VERSION_STYLES.values()}
    assert set(SPARE_COLOURS).isdisjoint(described)

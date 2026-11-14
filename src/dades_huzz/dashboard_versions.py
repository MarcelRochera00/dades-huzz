"""How the dashboard shows each version: one colour, the same in every chart, and one line on what it does."""

import hashlib
from typing import NamedTuple


class VersionStyle(NamedTuple):
    colour: str
    description: str


VERSION_STYLES: dict[str, VersionStyle] = {
    "baseline": VersionStyle(
        "#c3cad2",
        "Our first loop: all-time best sellers in stock, the same answer as the baseline.",
    ),
    "best-sellers": VersionStyle(
        "#a3adb8",
        "All-time best sellers in stock, the same answer as the baseline.",
    ),
    "tati-0-bestsellers": VersionStyle(
        "#6b7785",
        "Our best-sellers arm: all-time best sellers in stock, the same answer as the baseline.",
    ),
    "tati-destroyer-category": VersionStyle(
        "#606d34",
        "Best sellers of the category viewed last, leaving out what the shopper viewed; then overall best sellers.",
    ),
    "tati-terminator-category-viewed": VersionStyle(
        "#2e7d32",
        "Destroyer, but keeps the products viewed in the session where they rank.",
    ),
    "tati-terminator-category-viewed-live": VersionStyle(
        "#7cb342",
        "Terminator, ranked by live sales since the switch with a tuned history prior.",
    ),
    "tati-terminator-live-subcat": VersionStyle(
        "#8c6d1f",
        "Terminator-live; a new shopper gets two best sellers of the subcategory viewed last on top.",
    ),
    "tati-terminator-live-cold": VersionStyle(
        "#4a90c8",
        "Terminator-live; cold requests are answered from the live trend.",
    ),
    "tati-ultimatum-viewed-first": VersionStyle(
        "#a04e29",
        "Terminator with up to 3 viewed products on top, latest first.",
    ),
    "tati-ultimatum-cold": VersionStyle(
        "#c99a3a",
        "Ultimatum; cold requests are answered from the live trend.",
    ),
    "tati-apocalypse-profile": VersionStyle(
        "#1f3f7a",
        "Terminator plus the shopper's favourite history categories; never shows what they bought.",
    ),
    "tati-armageddon-viewed-profile": VersionStyle(
        "#814d88",
        "Apocalypse with Ultimatum's viewed products on top.",
    ),
    "tati-omega-live-profile": VersionStyle(
        "#ad4659",
        "Apocalypse on the live ranking, with the subcategory first for new shoppers.",
    ),
    "tati-omega-plus-day": VersionStyle(
        "#6b4fa3",
        "Omega plus the categories each shopper viewed today, so new shoppers get a profile too.",
    ),
    "tati-cart-profile": VersionStyle(
        "#2a9d8f",
        "Apocalypse with up to 3 products the shopper carted in the history and never bought on top.",
    ),
    "lauri-titan-feedback": VersionStyle(
        "#e07b00",
        "Learned ranking: weights trained on our own carousels score each product for the shopper.",
    ),
    "lauri-colossus-feedback": VersionStyle(
        "#7a3d00",
        "Titan retrained on more carousels, plus the shopper's day: today's categories, cart and views.",
    ),
    "lauri-titan-plus": VersionStyle(
        "#b5179e",
        "Titan plus what the shopper carted in the history and never bought, as a candidate and a weight.",
    ),
    "lauri-titan-pool100": VersionStyle(
        "#f2b134",
        "Titan's weights, reaching 100 deep into each category's ranking instead of 30.",
    ),
    "lauri-titan-cold60": VersionStyle(
        "#3a7d44",
        "Titan, with cold requests answered by #60's rule: the 15-min leading category, then device shares.",
    ),
    "lauri-titan-plus-hot": VersionStyle(
        "#5c2a9d",
        "Titan+, and while a subcategory trends (#64) its two live best sellers take slots 2 and 3.",
    ),
    "lauri-titan-max": VersionStyle(
        "#0b6e99",
        "Tournament 4's pieces together: Titan+ 100 deep, trending subcategory in slots 2-3, #60 for cold.",
    ),
    "lauri-titan-als": VersionStyle(
        "#9c2f2f",
        "Titan max plus each returning shopper's taste from the history (ALS): new candidates and a weight.",
    ),
}
"""Add a line here when a version is added to serving/versions.py VERSIONS."""

SPARE_COLOURS = ("#17becf", "#bcbd22", "#9467bd", "#8c564b", "#e377c2", "#d62728")
UNDESCRIBED = "No description yet: add it to VERSION_STYLES in dashboard_versions.py."


def version_style(name: str) -> VersionStyle:
    """The version's style; a version not described yet gets a spare colour that depends only on its name."""
    if name in VERSION_STYLES:
        return VERSION_STYLES[name]
    index = hashlib.sha256(name.encode()).digest()[0] % len(SPARE_COLOURS)
    return VersionStyle(SPARE_COLOURS[index], UNDESCRIBED)

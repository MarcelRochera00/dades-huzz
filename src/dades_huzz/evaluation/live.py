"""Live evaluation: which kinds of product our answers sold, by slot (docs/experiments.md rows 24-25).

The old carousel log can mislead: a shopper's own history products sold 16x more there and not at all
more live. This reads what our own live answers sold, so a signal is trusted only once it holds live,
and on Sunday it tells within minutes which signals still hold on the new data.
"""

import math
from collections import Counter
from collections.abc import Iterable, Mapping

from dades_huzz.data import RawTree, Record

TOP_SLOTS = 3
"""Slots 1-3 are read apart from 4-10: shoppers look at the first slots much more."""

LIVE_ANSWERS = """
SELECT r.user_id AS user_id, r.is_new_user AS is_new_user, r.recent_views AS recent_views,
       a.items AS items, a.model_version AS model_version, f.purchased AS purchased
FROM (SELECT request_id::String AS request_id, user_id::String AS user_id,
             is_new_user::String = 'true' AS is_new_user, recent_views
      FROM shop.requests
      WHERE ts::DateTime64(3) BETWEEN now64(3) - INTERVAL {seconds} SECOND AND now64(3) - INTERVAL 20 SECOND) AS r
INNER JOIN (SELECT request_id::String AS request_id, any(items::Array(String)) AS items,
                   any(model_version::String) AS model_version
            FROM {team}.submissions GROUP BY request_id) AS a ON a.request_id = r.request_id
INNER JOIN (SELECT request_id::String AS request_id, purchased::String AS purchased
            FROM {team}.feedback
            WHERE request_id::String != '__init__' AND served_by::String = 'team') AS f
  ON f.request_id = r.request_id"""
"""Our answers that the organisers accepted in the last `seconds`, with the request and what was bought."""


def live_answers(
    rawtree: RawTree, minutes: float, version: str | None = None
) -> list[Record]:
    """Our accepted live answers from the last `minutes`, as `signal_rates` reads them; only `version`'s
    when given."""
    rows = rawtree.query(
        LIVE_ANSWERS.format(seconds=int(minutes * 60), team=rawtree.team), timeout=120
    )
    return [
        {
            "request": {
                "user_id": row["user_id"],
                "is_new_user": bool(row["is_new_user"]),
                "recent_views": row["recent_views"] or [],
            },
            "items": row["items"],
            "purchased": row["purchased"] or "",
        }
        for row in rows
        if version is None or row["model_version"] == version
    ]


def _kind(
    product_id: str,
    viewed: set[str],
    category: str | None,
    last: str | None,
    favourites: list[str],
) -> str:
    if product_id in viewed:
        return "viewed this session"
    if category is not None and favourites and category == favourites[0]:
        return "favourite category"
    if category is not None and category == last:
        return "category viewed last"
    if category is not None and category in favourites[1:3]:
        return "2nd-3rd favourite category"
    return "other"


def signal_rates(
    answers: Iterable[Record],
    category_of: Mapping[str, str],
    profiles: Mapping[str, Mapping[str, float]],
) -> list[Record]:
    """Shows and purchases of every product we showed, by shopper (returning / new), kind and slots.

    The kinds are exclusive, checked in order: viewed this session, the shopper's favourite category, the
    category viewed last, their 2nd-3rd favourite, other. Each row carries the rate and its 95 % interval.
    """
    shows: Counter[tuple[str, str, str]] = Counter()
    purchases: Counter[tuple[str, str, str]] = Counter()
    for answer in answers:
        request = answer["request"]
        views = [view["product_id"] for view in request.get("recent_views") or []]
        last = category_of.get(views[-1]) if views else None
        profile = profiles.get(request.get("user_id") or "", {})
        favourites = [
            name for name, _ in sorted(profile.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        shopper = "new" if request.get("is_new_user") else "returning"
        for slot, product_id in enumerate(answer["items"]):
            key = (
                shopper,
                _kind(
                    product_id,
                    set(views),
                    category_of.get(product_id),
                    last,
                    favourites,
                ),
                "1-3" if slot < TOP_SLOTS else "4-10",
            )
            shows[key] += 1
            purchases[key] += answer["purchased"] == product_id
    rows = []
    for key in sorted(shows):
        low, high = wilson(purchases[key], shows[key])
        rows.append(
            {
                "shopper": key[0],
                "kind": key[1],
                "slots": key[2],
                "shows": shows[key],
                "purchases": purchases[key],
                "rate_pct": round(100 * purchases[key] / shows[key], 3),
                "interval_95_pct": f"{100 * low:.3f}-{100 * high:.3f}",
            }
        )
    return rows


def wilson(purchases: int, shows: int, z: float = 1.96) -> tuple[float, float]:
    """95 % Wilson interval of a rate: it stays sensible with few purchases, unlike rate +- 2 sd."""
    if shows == 0:
        return 0.0, 1.0
    rate = purchases / shows
    centre = rate + z * z / (2 * shows)
    spread = z * math.sqrt(rate * (1 - rate) / shows + z * z / (4 * shows * shows))
    scale = 1 + z * z / shows
    return max(0.0, (centre - spread) / scale), min(1.0, (centre + spread) / scale)

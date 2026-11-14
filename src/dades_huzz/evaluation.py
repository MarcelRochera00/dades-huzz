"""Offline evaluation of a `recommend(request, state)` on the history (lane B, docs/experiments.md)."""

import math
import random
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from dades_huzz.data import RawTree, Record, State
from dades_huzz.features import (
    START_PRIOR_WEIGHT,
    TOP,
    TUNE_FROM_MS,
    TUNE_WINDOW_MS,
    captured,
    category_ranking,
    pick_prior_weight,
)

TREND_CHANGES = (0.0, 0.3, 0.6, 1.0)
"""Shares of each category's products whose history popularity is shuffled to simulate the switch."""


def simulate_switch(
    purchases: Iterable[tuple[str, int]],
    history: Mapping[str, int],
    category_of: Mapping[str, str],
    policies: Mapping[str, float | None],
    trend_changes: Sequence[float] = TREND_CHANGES,
    seeds: int = 3,
    minutes: int = 120,
    step: int = 2,
    horizon: int = 30,
) -> dict[str, dict[float, float]]:
    """Replay a final round on a stretch of live purchases, `(product, minute since its start)`, and score
    each way of weighting the history: a fixed prior weight, or None to tune it as the live version does.

    New trends are simulated by shuffling the history's purchase counts among a share of each category's
    products (1.0: the history says nothing, as with an all-new catalogue). Score: `captured` of the next
    `horizon` minutes' purchases by each category's top 10, averaged over a decision every `step` minutes.
    """
    products = sorted(category_of)
    index = {product: i for i, product in enumerate(products)}
    counts = np.zeros((len(products), minutes + horizon))
    for product, minute in purchases:
        if product in index and 0 <= minute < counts.shape[1]:
            counts[index[product], minute] += 1
    cumulative = np.concatenate([np.zeros((len(products), 1)), counts.cumsum(1)], 1)

    def sales(start: int, end: int) -> dict[str, int]:
        window = cumulative[:, end] - cumulative[:, start]
        return {products[i]: int(window[i]) for i in np.flatnonzero(window)}

    members: dict[str, list[str]] = {}
    for product in products:
        members.setdefault(category_of[product], []).append(product)
    results: dict[str, dict[float, float]] = {name: {} for name in policies}
    for change in trend_changes:
        scores: dict[str, list[float]] = {name: [] for name in policies}
        for seed in range(seeds):
            rng = random.Random(seed)
            shuffled = dict(history)
            for group in members.values():
                picked = [p for p in group if rng.random() < change]
                values = [history.get(p, 0) for p in picked]
                rng.shuffle(values)
                shuffled.update(zip(picked, values, strict=True))
            total = sum(shuffled.values()) or 1
            share = {p: n / total for p, n in shuffled.items() if n}
            for t in range(step, minutes, step):
                live, target = sales(0, t), sales(t, t + horizon)
                for name, weight in policies.items():
                    if weight is None:
                        weight = START_PRIOR_WEIGHT
                        if t * 60_000 >= TUNE_FROM_MS:
                            cut = t - min(TUNE_WINDOW_MS // 60_000, t // 2)
                            weight, _ = pick_prior_weight(
                                sales(0, cut), sales(cut, t), share, category_of
                            )
                    ranked = category_ranking(live, share, category_of, weight, TOP)
                    scores[name].append(captured(ranked, target, category_of))
        for name in policies:
            results[name][change] = float(np.mean(scores[name]))
    return results


def weighted_hit(answer: Sequence[str], bought: Collection[str]) -> float:
    """How well an answer placed what the shopper bought: 1 in the first slot, 1/log2(rank+2) lower down.

    Shoppers look at the first slots much more than the last ones, so a hit counts more the higher it is.
    With several purchases, the best placed one counts. Nothing bought in the answer scores 0.
    """
    for rank, product_id in enumerate(answer):
        if product_id in bought:
            return 1 / math.log2(rank + 2)
    return 0.0


@dataclass(frozen=True)
class SlotOneIps:
    """Estimated slot-1 click rate of a policy on the old carousel log, and how much evidence it rests on."""

    ips: float
    snips: float
    matches: int


def slot1_ips(
    firsts: Sequence[str | None], logged: Sequence[Mapping[str, Any]]
) -> SlotOneIps:
    """Inverse-propensity estimate of the click rate of our first slot, as in the starter `offline_eval`.

    Only the impressions where our first pick equals what the old system put first tell us anything; each
    is weighted by 1 / the old system's propensity for that slot, which undoes its bias towards popular
    products. Few `matches` means a noisy estimate: report it next to the number.
    """
    weighted_clicks = 0.0
    total_weight = 0.0
    matches = 0
    for first, row in zip(firsts, logged, strict=True):
        # a zero propensity cannot be reweighted (and slot 1 has no cap): the row tells us nothing
        if first != row["shown"][0] or row["propensity"][0] <= 0:
            continue
        weight = 1 / row["propensity"][0]
        matches += 1
        total_weight += weight
        if row["clicked"] == first:
            weighted_clicks += weight
    n = len(logged)
    return SlotOneIps(
        ips=weighted_clicks / n if n else 0.0,
        snips=weighted_clicks / total_weight if total_weight else 0.0,
        matches=matches,
    )


@dataclass(frozen=True)
class SlateIps:
    """Estimated carousel purchases per request of a policy, from all ten slots of the old log."""

    ips: float
    matches: int
    matched_purchases: int


def _slot_weight(propensity: float, cap: float) -> float:
    """min(1 / propensity, cap); a logged propensity of 0 counts as the cap instead of dividing by 0."""
    return cap if propensity <= 0 else min(1 / propensity, cap)


def slate_ips_by_request(
    answers: Sequence[Sequence[str]],
    logged: Sequence[Mapping[str, Any]],
    cap: float = 20,
) -> list[float]:
    """Each request's share of `slate_ips`: the capped weight of the purchase we would have shown in
    the same slot as the old system, or 0. Their mean is the policy's estimate; pairing two policies'
    lists request by request is what `paired_difference` needs.
    """
    values = []
    for answer, row in zip(answers, logged, strict=True):
        value = 0.0
        for ours, shown, propensity in zip(
            answer, row["shown"], row["propensity"], strict=False
        ):
            if ours == shown and row["purchased"] == shown:
                value += _slot_weight(propensity, cap)
        values.append(value)
    return values


def slate_ips(
    answers: Sequence[Sequence[str]],
    logged: Sequence[Mapping[str, Any]],
    cap: float = 20,
) -> SlateIps:
    """Item-position inverse-propensity estimate of carousel purchases per request.

    For every slot where our product equals the one the old system showed there, a purchase of it counts
    with weight min(1 / propensity, cap). The cap trades a little bias for a lot less noise: uncapped,
    a single purchase of a rarely shown product can outweigh thousands of others.
    """
    matches = 0
    matched_purchases = 0
    for answer, row in zip(answers, logged, strict=True):
        for ours, shown in zip(answer, row["shown"], strict=False):
            if ours != shown:
                continue
            matches += 1
            matched_purchases += row["purchased"] == shown
    values = slate_ips_by_request(answers, logged, cap)
    n = len(logged)
    return SlateIps(
        ips=sum(values) / n if n else 0.0,
        matches=matches,
        matched_purchases=matched_purchases,
    )


@dataclass(frozen=True)
class PairedDifference:
    """How much a challenger beats a baseline on the same requests, with 95 % bootstrap intervals.

    `diff` is challenger minus baseline per request (what the score rewards: the score is normalised
    from the baseline up); `ratio` is challenger over baseline, for telling the story.
    """

    diff: float
    low: float
    high: float
    ratio: float
    ratio_low: float
    ratio_high: float


def paired_difference(
    baseline: Sequence[float],
    challenger: Sequence[float],
    cases: Sequence[Mapping[str, Any]],
    draws: int = 1000,
    seed: int = 0,
) -> PairedDifference:
    """Paired difference of two policies' per-request values, with a bootstrap over shoppers.

    One shopper's requests are not independent (the same taste, the same rare purchase seen again), so
    each redrawn week draws whole shoppers (`request.user_id`) with replacement, never single requests;
    a request without a user_id is its own shopper. The intervals are the 2.5 and 97.5 percentiles.
    """
    if not cases:
        return PairedDifference(0.0, 0.0, 0.0, math.nan, math.nan, math.nan)
    # shoppers are numbered in sorted order, so the same seed gives the same interval whatever order
    # RawTree returned the requests in
    users = [
        str(case["request"].get("user_id") or f"__request__{index}")
        for index, case in enumerate(cases)
    ]
    groups = {user: code for code, user in enumerate(sorted(set(users)))}
    codes_array = np.asarray([groups[user] for user in users])
    base_sum = np.bincount(codes_array, weights=np.asarray(baseline, dtype=float))
    chal_sum = np.bincount(codes_array, weights=np.asarray(challenger, dtype=float))
    size = np.bincount(codes_array).astype(float)
    shoppers = len(groups)

    rng = np.random.default_rng(seed)
    diffs = np.empty(draws)
    ratios = np.empty(draws)
    for draw in range(draws):
        picked = rng.integers(0, shoppers, size=shoppers)
        base, chal = base_sum[picked].sum(), chal_sum[picked].sum()
        diffs[draw] = (chal - base) / size[picked].sum()
        ratios[draw] = chal / base if base else np.nan

    total_base, total_chal = base_sum.sum(), chal_sum.sum()
    ratios = ratios[~np.isnan(ratios)]
    no_ratio = (math.nan, math.nan)
    ratio_low, ratio_high = (
        tuple(float(x) for x in np.percentile(ratios, [2.5, 97.5]))
        if ratios.size
        else no_ratio
    )
    low, high = (float(x) for x in np.percentile(diffs, [2.5, 97.5]))
    return PairedDifference(
        diff=float((total_chal - total_base) / size.sum()),
        low=low,
        high=high,
        ratio=float(total_chal / total_base) if total_base else math.nan,
        ratio_low=ratio_low,
        ratio_high=ratio_high,
    )


HISTORY_CASES = """
SELECT request_id::String AS request_id, user_id::String AS user_id,
       `context.device`::String AS device, `context.region`::String AS region,
       `context.page`::String AS page, recent_views,
       shown::Array(String) AS shown, propensity::Array(Float64) AS propensity,
       clicked::String AS clicked, purchased::String AS purchased
FROM shop.history_sessions
WHERE ts::DateTime64(3) >= '{since}' AND cityHash64(request_id::String) % {every} = {part}"""
"""Old carousel impressions from `since` on, slice `part` of `every` (stable slices by request_id)."""


def history_cases(
    rawtree: RawTree, since: str, every: int = 1, parts: Sequence[int] | None = None
) -> list[dict[str, Any]]:
    """The old carousel log from `since` on, as cases for `evaluate`: the request in the contract's shape,
    what was bought from the carousel, and the logged row.

    The log is read in `every` stable slices by request_id (one query each, so no answer is too big for
    RawTree); `parts` picks which slices, all of them by default.
    """
    rows = []
    for part in range(every) if parts is None else parts:
        query = HISTORY_CASES.format(since=since, every=every, part=part)
        rows.extend(rawtree.query(query, timeout=120))
    cases = []
    for row in rows:
        purchased = row["purchased"] or None
        cases.append(
            {
                "request": {
                    "request_id": row["request_id"],
                    "user_id": row["user_id"],
                    "context": {
                        "device": row["device"],
                        "region": row["region"],
                        "page": row["page"],
                    },
                    "recent_views": row["recent_views"] or [],
                },
                "bought": {purchased} if purchased else set(),
                "logged": {
                    "shown": row["shown"],
                    "propensity": row["propensity"],
                    "clicked": row["clicked"] or None,
                    "purchased": purchased,
                },
            }
        )
    return cases


@dataclass(frozen=True)
class Report:
    """One policy scored on a set of history cases."""

    cases: int
    weighted_hit: float
    hit_rate: float
    slot1: SlotOneIps
    slate: SlateIps
    answers: list[list[str]] = field(repr=False, compare=False, default_factory=list)


def evaluate(
    recommend: Callable[[Record, State], list[str]],
    cases: Sequence[Mapping[str, Any]],
    state: State,
) -> Report:
    """Score `recommend` on history cases, calling it exactly as the serving loop does.

    Each case is `{"request": <request in the contract shape>, "bought": <products the shopper went on
    to buy>, "logged": <the old carousel row: shown, propensity, clicked, purchased>}`.
    """
    answers = [recommend(case["request"], state) for case in cases]
    logged = [case["logged"] for case in cases]
    hits = [
        weighted_hit(answer, case["bought"])
        for answer, case in zip(answers, cases, strict=True)
    ]
    n = len(cases)
    return Report(
        cases=n,
        weighted_hit=sum(hits) / n if n else 0.0,
        hit_rate=sum(hit > 0 for hit in hits) / n if n else 0.0,
        # an empty answer has no first slot: None never matches what the old system showed
        slot1=slot1_ips([answer[0] if answer else None for answer in answers], logged),
        slate=slate_ips(answers, logged),
        answers=answers,
    )

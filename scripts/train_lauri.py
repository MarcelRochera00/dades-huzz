"""Train Lauri on our own carousels, check it on the latest ones, and store its weights for the loop.

    uv run python scripts/train_lauri.py                 # validate only
    uv run python scripts/train_lauri.py --save          # validate, refit on everything, store the weights
    uv run python scripts/train_lauri.py --no-day --save # Colossus without the shopper's day
    uv run python scripts/train_lauri.py --name lauri-titan-feedback --no-day --save   # retrain Titan
    uv run python scripts/train_lauri.py --name lauri-titan-plus --history-carts --save  # Titan+
    uv run python scripts/train_lauri.py --name lauri-titan-als --als --save  # Titan+ with the shopper's taste

Validation: train on the feedback before the last `--holdout-minutes`, score on those minutes, next to a
reference that knows only the slot and whether the product was viewed, to Lauri Titan's stored weights
(fitted on every row up to their training time, so they may have seen part of the held-out minutes) and to
Titan's features refitted on the same training rows. The rule: the new weights go live only if their
held-out log-likelihood beats the refitted Titan's. For Titan+ (`--history-carts`, fixed before its first
run): its held-out log-likelihood is not below the refitted Titan's, its returning weight on `history_carted`
is positive, and at least MIN_CART_PURCHASES purchases of carted products back it. For Titan ALS (`--als`,
fixed before its first run, #62): against Titan+ refitted on the same rows, the held-out log-likelihood gains at
least MIN_TASTE_GAIN, new shoppers' does not drop, and the returning weight on `als_score` is positive. Reads TEAM_ID and
RAWTREE_API_KEY from .env.
"""

import argparse
import time

import numpy as np

from dades_huzz.data import RawTree
from dades_huzz.evaluation import carousel_report
from dades_huzz.features import (
    LAURI_CART_FEATURES,
    LAURI_DAY_FEATURES,
    LAURI_FEATURES,
    LAURI_TASTE_FEATURES,
    lauri_training_rows,
    shopper_taste,
)
from dades_huzz.model import (
    LAURI_SEGMENTS,
    SLOTS,
    fit_lauri,
    fit_logistic,
    lauri_scores,
    load_lauri_weights,
    save_lauri_weights,
)

TITAN = "lauri-titan-feedback"
TITAN_FEATURES = tuple(
    f
    for f in LAURI_FEATURES
    if f not in LAURI_DAY_FEATURES + LAURI_CART_FEATURES + LAURI_TASTE_FEATURES
)
COLOSSUS_FEATURES = TITAN_FEATURES + LAURI_DAY_FEATURES
TITAN_PLUS_FEATURES = TITAN_FEATURES + LAURI_CART_FEATURES
TITAN_ALS_FEATURES = TITAN_PLUS_FEATURES + LAURI_TASTE_FEATURES
MIN_CART_PURCHASES = 40
MIN_TASTE_GAIN = 35.0
"""What Colossus gained over Titan (-1044.1 vs -1081.8): the bar #62 set for a new source."""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--name",
        default="lauri-colossus-feedback",
        help="the version these weights are for",
    )
    parser.add_argument("--holdout-minutes", type=float, default=90)
    parser.add_argument("--l2", type=float, default=10.0)
    parser.add_argument("--target", choices=("purchase", "click"), default="purchase")
    parser.add_argument(
        "--no-day",
        action="store_true",
        help="leave the shopper's day out: Titan's features only",
    )
    parser.add_argument(
        "--history-carts",
        action="store_true",
        help="Titan+: Titan's features plus history_carted (no day)",
    )
    parser.add_argument(
        "--als",
        action="store_true",
        help="Titan ALS: Titan+'s features plus als_score (the shopper's taste, #62)",
    )
    parser.add_argument(
        "--save", action="store_true", help="refit on every row and store the weights"
    )
    args = parser.parse_args()
    if args.als:
        features = TITAN_ALS_FEATURES
    elif args.history_carts:
        features = TITAN_PLUS_FEATURES
    else:
        features = TITAN_FEATURES if args.no_day else COLOSSUS_FEATURES
    rawtree = RawTree.from_env()
    rows = lauri_training_rows(
        rawtree, taste=shopper_taste(rawtree) if args.als else None
    )
    target = (
        rows.purchased
        if args.target == "purchase"
        else np.maximum(rows.purchased, rows.clicked)
    )
    cut = rows.ts_ms.max() - args.holdout_minutes * 60_000
    train, test = rows.ts_ms < cut, rows.ts_ms >= cut
    print(
        f"{len(np.unique(rows.request))} answered requests, {int(rows.purchased.sum())} purchases,"
        f" {int(rows.clicked.sum())} clicks; held out: the last {args.holdout_minutes:g} min"
    )
    reference = np.c_[np.eye(SLOTS)[rows.slot][:, 1:], rows.features[:, 0]]
    bias, weights = fit_logistic(reference[train], rows.purchased[train], args.l2)
    report("slot + viewed", bias + reference @ weights, rows.features[:, 0], rows, test)
    try:
        stored = load_lauri_weights(rawtree, TITAN)
        report("titan stored", *lauri_scores(stored, rows), rows, test)
    except LookupError as e:
        print(f"titan stored: {e}")
    titan = fit_lauri(rows, train, target, args.l2, TITAN_FEATURES)
    titan_ll = report("titan refitted", *lauri_scores(titan, rows), rows, test)["all"]
    if args.als:
        plus = fit_lauri(rows, train, target, args.l2, TITAN_PLUS_FEATURES)
        plus_ll = report("titan+ refitted", *lauri_scores(plus, rows), rows, test)
    fitted = fit_lauri(rows, train, target, args.l2, features)
    if args.als:
        name = "with taste (als)"
    elif args.history_carts:
        name = "history carts"
    else:
        name = "titan features" if args.no_day else "with the day"
    fitted_lls = report(name, *lauri_scores(fitted, rows), rows, test)
    fitted_ll = fitted_lls["all"]
    for segment in LAURI_SEGMENTS:
        pairs = zip(LAURI_FEATURES, fitted[segment]["weights"], strict=True)
        print(
            f"  {segment}: "
            + ", ".join(
                f"{name} {weight:+.2f}" for name, weight in pairs if name in features
            )
        )
    if args.als:
        column = LAURI_FEATURES.index("als_score")
        weight = fitted["returning"]["weights"][column]
        gain = fitted_ll - plus_ll["all"]
        passes = (
            gain >= MIN_TASTE_GAIN
            and fitted_lls["new"] >= plus_ll["new"]
            and weight > 0
        )
        print(
            f"rule: held-out log-likelihood {fitted_ll:.1f} against the refitted Titan+'s {plus_ll['all']:.1f}"
            f" (gain {gain:+.1f}, needs {MIN_TASTE_GAIN:+.0f}); new shoppers {fitted_lls['new']:.1f} vs"
            f" {plus_ll['new']:.1f}; returning weight on als_score {weight:+.3f}: {'PASSES' if passes else 'FAILS'}"
        )
    elif args.history_carts:
        column = LAURI_FEATURES.index("history_carted")
        carted = rows.features[:, column] > 0
        support = int(rows.purchased[carted].sum())
        weight = fitted["returning"]["weights"][column]
        passes = fitted_ll >= titan_ll and weight > 0 and support >= MIN_CART_PURCHASES
        print(
            f"history carts shown {int(carted.sum())} times, bought {support}; returning weight {weight:+.2f}"
        )
        print(
            f"rule: held-out log-likelihood {fitted_ll:.1f} against the refitted Titan's {titan_ll:.1f},"
            f" weight > 0, support >= {MIN_CART_PURCHASES}: {'PASSES' if passes else 'FAILS'}"
        )
    elif not args.no_day:
        verdict = "PASSES" if fitted_ll > titan_ll else "FAILS"
        print(
            f"rule: held-out log-likelihood {fitted_ll:.1f} against the refitted Titan's {titan_ll:.1f}: {verdict}"
        )
    if args.save:
        everything = np.ones(len(target), dtype=bool)
        save_lauri_weights(
            rawtree,
            args.name,
            fit_lauri(rows, everything, target, args.l2, features),
            int(time.time() * 1000),
        )
        print(
            f"stored the weights of {args.name}, fitted on every row, in {rawtree.team}.scratch"
        )


def report(
    name: str, shown_logit: np.ndarray, served_score: np.ndarray, rows, test: np.ndarray
) -> dict[str, float]:
    """Print the held-out scores per kind of shopper; returns the log-likelihood of each ("all", "new",
    "returning")."""
    lls = {}
    for segment, keep in (
        ("all", test),
        ("new", test & rows.is_new_user),
        ("returning", test & ~rows.is_new_user),
    ):
        m = carousel_report(
            shown_logit, served_score, rows.purchased, rows.slot, rows.request, keep
        )
        lls[segment] = m["log_likelihood"]
        print(
            f"{name:18s} {segment:9s} log-likelihood {m['log_likelihood']:8.1f}  AUC slots 1-3 {m['auc_top_slots']:.3f}"
            f"  top 3 {m['top3']:.3f} (as shown {m['top3_shown']:.3f})  MRR {m['mrr']:.3f} (as shown {m['mrr_shown']:.3f})"
            f"  purchases {m['purchases']}"
        )
    return lls


if __name__ == "__main__":
    main()

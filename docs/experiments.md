# Experiments

One row per attempt, including the ones that got worse. State the validation scheme: a score without
it cannot be compared.

| # | When | Who | Data / features | Model | Validation scheme | Local score | Leaderboard | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | Sat 12:15 | Marcel | none (history purchase counts) | Organisers' starter `recommender.py`, as is | Live practice stream, 5 min, `check_serving.py` | 900/900 answered, p95 1.75 s, max 2.99 s, CTR 3.11 %, conv 0.89 % | | Baseline reference; max latency 6 ms from the deadline |
| 2 | Sat 12:25 | Marcel | none (history purchase counts) | `best_sellers` in our loop (`serve_recommender.py`, now `run_recommender.py`) | Live practice stream, 2 min, `check_serving.py` | 360/360 answered, p95 1.29 s, max 1.65 s, CTR 2.78 % | | Same answers as #1, faster; conversion not comparable on 2 min |
| 3 | Sat 13:45 | Gabriel | purchases before 2026-11-07 07:00 UTC | `tati-0-bestsellers` (`best_sellers`, ranking at the cut) | Offline, `scripts/evaluate_policies.py`: all 232,860 carousel impressions after the cut; item-position IPS on carousel purchases, weight min(1/propensity, 20) | slate IPS 0.601 purchases/100 req (386 matched buys); weighted hit 0.462 %; slot-1 SNIPS 0.046 (9,229 matches) | | Offline reference for lane B |
| 4 | Sat 13:45 | Gabriel | same + `shop.catalog` category | `tati-destroyer-category` (`category_best_sellers`: top 50 sellers of the category viewed last, then overall) | Same as #3 | slate IPS 1.548 (658 matched buys), 2.6x #3; weighted hit 0.719 %; slot-1 SNIPS 0.020 (49,057 matches) | | Wins on the full-list metrics; slot-1 SNIPS disagrees (known weak: 1 slot, clicks). No confidence interval or cap sensitivity yet. Organic-purchase metric dropped (1.7 % coverage at 1 h) |

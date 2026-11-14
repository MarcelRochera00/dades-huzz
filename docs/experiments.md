# Experiments

One row per attempt, including the ones that got worse. State the validation scheme: a score without
it cannot be compared.

| # | When | Who | Data / features | Model | Validation scheme | Local score | Leaderboard | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | Sat 12:15 | Marcel | none (history purchase counts) | Organisers' starter `recommender.py`, as is | Live practice stream, 5 min, `check_serving.py` | 900/900 answered, p95 1.75 s, max 2.99 s, CTR 3.11 %, conv 0.89 % | | Baseline reference; max latency 6 ms from the deadline |
| 2 | Sat 12:25 | Marcel | none (history purchase counts) | `best_sellers` in our loop (`serve_recommender.py`, now `run_recommender.py`) | Live practice stream, 2 min, `check_serving.py` | 360/360 answered, p95 1.29 s, max 1.65 s, CTR 2.78 % | | Same answers as #1, faster; conversion not comparable on 2 min |

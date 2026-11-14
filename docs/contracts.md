# Contracts

What the lanes agreed to depend on. Changing anything here needs its own PR, confirmed by every lane
that uses it. Agreed on Saturday 14 November at the team alignment (grill-with-docs session).

## Lanes

Lanes are flexible: each owner explores their area in depth and may reshape it, and we rebalance at
every sync. Each lane has one GitHub issue (label `area:*`) that tracks its slices; the index issue
(label `wayfinder:map`) links all four.

| Lane | Owner | GitHub | Owns | Main folders |
|---|---|---|---|---|
| A · Live system and reliability | Marcel | `MarcelRochera00` | serving loop, live `state`, version split, latency, fallback, unattended runner | `src/dades_huzz/serving/`, `src/dades_huzz/data.py`, `scripts/run_recommender.py`, `scripts/check_serving.py` |
| B · History model and offline evaluation | Gabriel | `ProGabo` | candidates from history (co-views, description similarity, user profiles), IPS offline evaluation, `docs/experiments.md`; integrator (watches that `main` is shippable) | `src/dades_huzz/features.py`, `src/dades_huzz/model.py`, `src/dades_huzz/evaluation.py` |
| C · Live learning | Eudald | `dwakevy` | trends from `shop.events`, feedback, exploration (bandit), price changes, cold start | `src/dades_huzz/model.py` (live re-rank), `src/dades_huzz/features.py` (live signals) |
| D · Decisions and story | Miles | `milesgloekler` | history EDA that feeds B and C, RawTree SQL features, live A/B readout, the dashboard (Tukey side challenge), pitch and demo | `app/`, `notebooks/`, `docs/pitch.md`, `docs/assets/` |

Two lanes touching the same module (B and C in `model.py`, `features.py`) keep to separate functions
and agree on the shared signature below; neither rewrites the other's function.

## Data schema

All data lives in RawTree (schemaless: every column is `Dynamic`; cast join keys and timestamps, e.g.
`product_id::String`, `ts::DateTime64(3)`). Full description in `docs/challenge/brief.md`.

| Dataset | Column | Type | Meaning |
|---|---|---|---|
| `shop.requests` | `request_id` | string | One shopper arriving at the carousel; what we answer |
| | `ts` | timestamp (UTC) | Request time; the 3 s deadline counts from here |
| | `user_id`, `is_new_user` | string, bool | Cold request = `is_new_user`, or `recent_views` contains a product with a `new_product` update in `shop.catalog_updates` |
| | `context.device`, `context.region`, `context.page` | string | `SELECT *` returns them as flat columns named `context.device` etc. (checked live, Saturday); the brief shows them nested |
| | `recent_views` | array of `{product_id, ts}` | Products viewed earlier in the session |
| `shop.catalog` + `shop.catalog_updates` | `product_id`, `category`, `subcategory`, `brand`, `price_eur`, `description`, `is_active` | | Current catalogue = catalog with the latest update per product on top; updates carry `change` (`new_product`, `price_change`, `out_of_stock`, `back_in_stock`) |
| `shop.events` / `shop.history_events` | `ts`, `event_type`, `user_id`, `session_id`, `product_id`, `price_eur`, `device`, `region` | | Organic activity (live / 60 days) |
| `shop.history_sessions` | `shown`, `propensity`, `clicked`, `purchased`, `revenue_eur`, `context`, `recent_views` | | Old carousel log; `propensity` for IPS |
| `team_02.feedback` | `request_id`, `shown`, `served_by`, `fallback_reason`, `latency_ms`, `clicked`, `purchased`, `revenue_eur` | | What happened with each answer; skip `request_id = '__init__'` |
| `team_02.scratch` | `kind` + any | JSON | Our own rows (signals, embeddings, model outputs). Every row has a `kind` naming what it is, and readers filter on it. `kind = 'heartbeat'` rows (`loop_id`, `host`, `role`, `started_ms`, `ts_ms`, plus `versions`: the split in force, champion first, and `out`: versions left out right now) belong to the serving loop's handover; the `active` loop's rows over time are the history of splits. `kind = 'version_out'` rows (`version`, `until_ms`) record a version taken out for being slow |

## Shared signatures

```python
def recommend(request: Request, state: State) -> list[str]:
    """10 distinct product IDs that are active and in stock, best first.

    Never raises (on any internal error, return the fallback list from `state`).
    Budget: about 200 ms per request, so the loop stays well inside 3 s.
    """
```

- `Request`: one `shop.requests` record as a dict: `request_id`, `ts` (UTC string), `ts_ms` (int, ms),
  `user_id`, `is_new_user`, `context`, `recent_views` (always a list, possibly empty). The serving loop
  normalises the context to a nested dict, so `recommend` reads `request["context"]["device"]`, whatever
  shape RawTree returns.
- `State` (`dades_huzz.data.State`): everything the serving loop keeps fresh (every 0.25 s), read-only for
  `recommend`. Lane A owns its shape; a lane that needs a new field (live trends, precomputed signals)
  adds it in a PR that lane A confirms. Today:

  | Field | Type | Meaning |
  |---|---|---|
  | `available` | `frozenset[str]` | Products an answer may contain: active and not out of stock |
  | `price` | `dict[str, float]` | Current price of every product, after `price_change` updates |
  | `new_products` | `frozenset[str]` | Products added during the event (`new_product`); a request that viewed one is cold |
  | `fallback` | `tuple[str, ...]` | All-time best sellers that are available, best first, then every other available product; the baseline answer is its first 10, and it pads a short answer |
  | `category` | `dict[str, str]` | Every product's category, including products added during the event, from the next refresh after their `new_product` update |
  | `subcategory` | `dict[str, str]` | Every product's subcategory, like `category` |
  | `trend` | `dict[str, int]` | Lane C. Each product's weight in `shop.events` over the last 15 minutes: purchase 4, add-to-cart 3, view 1. Refreshed every 30 s in the background |
  | `recent_purchases` | `dict[str, frozenset[str]]` | Lane C. Shopper to the products they purchased in that same window; an answer leaves them out |
  | `shopper_categories` | `dict[str, dict[str, int]]` | Shopper (`user_id`) to category to views in `shop.events` since the stream started; an add-to-cart counts 3. Backfilled at start, then new events every 5 s |
  | `shopper_carted` | `dict[str, frozenset[str]]` | Shopper to the products they carted since the stream started and have not bought since |
  | `shopper_viewed` | `dict[str, tuple[str, ...]]` | Shopper to their last 20 distinct products viewed since the stream started, latest first |
- **Precomputed signals** (co-views, similarities, profiles) are built offline and stored as rows in
  `team_02.scratch` (with a `kind`), not only as files in `outputs/`, which exists on one laptop; the
  serving loop loads them into `State`, on whichever laptop runs it.
- **`model_version`**: every answer carries the version string of the policy that produced it, so
  feedback can be split by version. Requests are assigned to versions by a hash of `request_id`.

## Submission format

One record per request into `team_02.submissions`, batched (one HTTP call per poll, not per request):

```json
{"request_id": "r_...", "items": ["p_...", "... 10 distinct active IDs"], "model_version": "v1-coviews"}
```

It must reach RawTree within 3 s of the request `ts`; one answer per request. **Only one serving loop
answers at a time for the team**: two would send two answers for the same request. The handover enforces
it: start `scripts/run_recommender.py` on any number of laptops; one is active and answers, the others
wait on standby and take over within about 6 s if it stops. Never start one with `--no-handover` while
another loop runs: that flag skips the handover and always answers.

How we check we comply: `uv run python scripts/check_serving.py --minutes 30`: requests by outcome
(`answered` above 99%), requests answered twice (0), and the serving loops seen.

## Metric and validation

- **Scored**: only Sunday 10:00–12:00 CET. Conversion (expected purchases per 100 requests, 50 pts),
  the same on cold requests (10), share answered validly and on time (10); each normalised between the
  baseline (all-time best sellers in stock) and the oracle. Tie-breaker: expected revenue per request.
- **Offline**: replay on `shop.history_sessions` with inverse-propensity weighting (starter
  `offline_eval.ipynb`), with a time split (train on earlier days, evaluate on the last days).
- **Live**: compare versions running side by side on the same stream (hash split of `request_id`),
  reading purchases and revenue per request from `team_02.feedback`. The live comparison decides what
  becomes the main version.
- Every attempt is a row in `docs/experiments.md` stating which of the two schemes produced the score.

# Contracts

What the lanes agreed to depend on. Changing anything here needs its own PR, confirmed by every lane
that uses it. Agreed on Saturday 14 November at the team alignment (grill-with-docs session).

## Lanes

Lanes are flexible: each owner explores their area in depth and may reshape it, and we rebalance at
every sync. Each lane has one GitHub issue (label `area:*`) that tracks its slices; the index issue
(label `wayfinder:map`) links all four.

| Lane | Owner | GitHub | Owns | Main folders |
|---|---|---|---|---|
| A · Live system and reliability | Marcel | `MarcelRochera00` | serving loop, live `state`, version split, latency, fallback, unattended runner | `src/dades_huzz/serving.py`, `src/dades_huzz/data.py`, `scripts/run_recommender.py` |
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
| `team_02.scratch` | any | JSON | Our own signals (features, embeddings, model outputs) |

## Shared signatures

```python
def recommend(request: Request, state: State) -> list[str]:
    """10 distinct product IDs that are active and in stock, best first.

    Never raises (on any internal error, return the fallback list from `state`).
    Budget: about 200 ms per request, so the loop stays well inside 3 s.
    """
```

- `Request`: one `shop.requests` record as a dict (`request_id`, `ts`, `user_id`, `is_new_user`,
  `context`, `recent_views`). The serving loop normalises the context to a nested dict, so `recommend`
  reads `request["context"]["device"]`, whatever shape RawTree returns.
- `State`: everything the serving loop keeps fresh, read-only for `recommend`: the current catalogue
  (active, in stock, prices), the fallback list (best sellers in stock), live trends, and the precomputed
  signals. Lane A owns its shape; a lane that needs a new field adds it in a PR that lane A confirms.
- **Precomputed signals** (co-views, similarities, profiles) are built offline and stored as files in
  `outputs/` or rows in `team_02.scratch`; the serving loop loads them into `State`.
- **`model_version`**: every answer carries the version string of the policy that produced it, so
  feedback can be split by version. Requests are assigned to versions by a hash of `request_id`.

## Submission format

One record per request into `team_02.submissions`, batched (one HTTP call per poll, not per request):

```json
{"request_id": "r_...", "items": ["p_...", "... 10 distinct active IDs"], "model_version": "v1-coviews"}
```

It must reach RawTree within 3 s of the request `ts`; one answer per request. **Only one serving loop
runs at a time for the team**: two loops would send two answers for the same request. Before starting a
loop, check the latest `model_version` rows in `team_02.submissions` and tell the team.

How we check we comply: `team_02.feedback` grouped by `served_by` and `fallback_reason` (query 6 in the
starter `queries.sql`); `served_by = 'team'` above 99%.

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

# The challenge

Everything the company told us, so every agent plans from the same source.

**RawTree · Real-Time Recommendation.** Shoppers arrive about 3 per second; for each one we have 3 seconds
to write 10 product IDs to RawTree. Only Sunday 10:00–12:00 CET is scored. Start with `brief.md`.

| File | What | Reliability |
|---|---|---|
| `brief.md` | The written brief: the `README.md` of the organisers' repo | Primary source |
| `datathon-fme-2026-main.zip` | The organisers' repo ([rawtreedb/datathon-fme-2026](https://github.com/rawtreedb/datathon-fme-2026)): brief, `.env.example` and the starter kit (`starter/recommender.py`, `starter/queries.sql`, `starter/offline_eval.ipynb`) | Primary source |
| `challenge-page.html` (+ `challenge-page_files/`) | Saved copy of the challenge page, [datathon.rawtree.dev](https://datathon.rawtree.dev), with the FAQ | Primary source |
| `notes.md` | Notes taken during the presentation | Good |
| `qa.md` | Questions we asked the company, with their answers and the time | Primary source |

If two sources disagree, the written brief wins; then ask the company and log the answer in `qa.md`.

## Known disagreements

- **What the baseline is.** `brief.md`: the all-time best sellers that are in stock, ranked once at the
  start (this is what `starter/recommender.py` does). The web page: the best sellers of the category of the
  last product viewed. The brief wins until the RawTree team answers; log it in `qa.md`.

## How to obtain the data

Nothing is downloaded: all data lives in RawTree and is read with SQL over its API.

1. Get the team credentials (`TEAM_ID`, `RAWTREE_API_KEY`) from whoever registered the team at the RawTree
   stand. One key per team; never share it outside the team.
2. Put them in a `.env` at the repo root, following `.env.example` in the zip. `.env` is git-ignored: never
   commit it.
3. Query with `POST https://api.rawtree.com/v1/query` (header `Authorization: Bearer $RAWTREE_API_KEY`) or the
   `rtree` CLI. Agent docs: <https://rawtree.com/llms.txt>.

Shared tables (read only): `shop.catalog`, `shop.history_sessions`, `shop.history_events`, and the live
`shop.requests`, `shop.events`, `shop.catalog_updates`. Ours (read and write): `team_NN.submissions`,
`team_NN.feedback`, `team_NN.scratch`. Local extracts go in `data/raw/` and are never committed.

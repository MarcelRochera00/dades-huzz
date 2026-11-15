# dades-huzz

Team 2's entry for the Datathon FME 2026, **RawTree · Real-Time Recommendation**. About three shoppers
a second reach a shop's product carousel. For each one we have 3 seconds to write 10 products they are
likely to buy into RawTree, or the shopper sees a generic list. Only Sunday 10:00–12:00 CET is scored.

- **How we work (Catalan, one page):** [docs/COM-TREBALLEM.md](docs/COM-TREBALLEM.md)
- **Rules for coding agents:** [AGENTS.md](AGENTS.md)
- **The challenge:** [docs/challenge/](docs/challenge/)

## What we built

**Tati**, a recommender that answers every live shopper and keeps improving while it runs:

- **Answers every request on time.** About 1.1 s from the shopper's arrival to our answer (p50), with
  about 99 % on time. Every answer is checked: 10 distinct products, all active and in stock.
- **Survives the night.** It moves between laptops without answering any request twice, restarts itself if it
  crashes or hangs, and keeps the laptop awake.
- **Tests ideas on real shoppers.** Each idea is scored first on the shop's history. Only the winner goes
  live, as a challenger against the current best on a share of shoppers.
- **Keeps up with the shop.** It sees stock, prices and new products within about 2 s, and re-reads
  the whole catalogue every minute as a safety net.

Every attempt, including the ones that lost, is in [docs/experiments.md](docs/experiments.md).

### The final model and how we got there

In the final round every request is answered by a pair of learned rankers, `pair:lauri-omni-plain+lauri-titan-plus-als`:

- **Cold requests** (a new shopper, or a view of a product added during the event) go to **Lauri Omni plain**,
  which also reads what the shopper did today.
- **Every other request** goes to **Lauri Titan+ ALS**, which adds each returning shopper's taste from the history.

Over Sunday 01:45–07:00 CET four versions each served 25 % of the requests. No version won both kinds of
request, so the final serves the best one for each:

| Version | Cold requests | Other requests |
|---|---|---|
| `lauri-omni-plain` | **1.90** (5,931) | 1.26 (8,259) |
| `lauri-titan-plus-als` | 1.55 (5,820) | **1.32** (8,156) |
| `lauri-titan-plus` (the champion until then) | 1.39 (6,034) | 1.13 (8,286) |
| `lauri-omni` | 1.25 (5,936) | 1.22 (8,235) |

Expected conversion from the leaderboard by version (`uv run python scripts/choose_final.py choose`), requests
in brackets. With that mix of requests the pair is expected at 1.57, against 1.24 for Titan+ alone.

The path, one step at a time:

| Step | What we did | Evidence | Rows |
|---|---|---|---|
| 1. Baseline | The organisers' best sellers, the same 10 products for everyone | About 0.7 expected conversion (0.69–0.79 by time of day) | 1, 2, 17 |
| 2. Rules ("Tati") | Best sellers of the category the shopper is viewing. Scored offline first with a pass rule fixed before the run, then live at 50/50 | Offline 2.57x best sellers (95 % 2.25 to 2.93); live 0.92 vs 0.76 in the same hour | 5, 17, 20 |
| 3. Diagnosis | Read our own feedback: what is bought of what we show | A third of returning shoppers' carousel purchases were history carts, shown in 6 % of the slots; every rule sat at 2–2.6x the baseline | 35, 37, 53 |
| 4. Learned ranker ("Lauri") | A logistic regression scores each candidate; its weights come from our own carousels and are refitted as feedback grows | Held-out log-likelihood −958.9 vs −1302.2; live 1.03 vs 0.85 for the best rule | 40, 45, 37 |
| 5. Live tournaments | Several versions at once, split by a hash of the request and compared in the same minutes | The pair above: 1.57 vs 1.24 | 52, 60, 61, 66 |

What is not proven:

- **The choice was not confirmed.** Row 61 planned two more hours of the choice against Titan+ at 50/50. There
  was no time left for it, so the pair was chosen on the 01:45–07:00 read alone.
- **New shoppers in the final start without a day.** Omni plain's lead on cold requests comes from what the
  shopper did earlier in the day, and overnight every new shopper had some. With the day cut short its order is
  level with Titan+'s, not worse (row 67).
- **Five more ideas failed their own pass rule overnight** and did not go live: co-viewing candidates (62),
  other cold orders (63), a ranker trained on organic purchases (64), forcing new products into the answer (65)
  and three more feature families (67).

### Versions at a glance

What each model version does, in one line. Live conversion is the leaderboard's expected purchases per 100
requests; compare versions only inside the same window, because conversion moves with the time of day.

| Model version | What it shows | Signals | Live conversion (Sat, CET) |
|---|---|---|---|
| `tati-0-bestsellers` | The all-time best sellers, the same for everyone (the baseline) | History sales | 0.73 (15:25–15:56) |
| `tati-destroyer-category` | Best sellers of the category viewed last, without the products already viewed | + category viewed last | 0.95 (15:25–16:06) |
| `tati-terminator-category-viewed` | Destroyer, keeping the viewed products where they rank. **Champion, default split** | same | 1.05 (17:45–18:25) |
| `tati-ultimatum-viewed-first` | Terminator with up to 3 viewed products on top | + viewed products first | 0.86 (17:45–18:25) |
| `tati-ultimatum-cold` | Ultimatum; a cold request gets the trend of the categories viewed | + trend, recent purchases | not served yet |
| `tati-terminator-category-viewed-live` | Terminator, each category ranked by live sales since the switch plus a tuned share of the history | + live sales | 1.01 (17:50–18:25) |
| `tati-apocalypse-profile` | Terminator blended with the returning shopper's 3 favourite categories; never what they bought | + shopper profile, purchases | **1.26** (17:50–18:25) |
| `tati-armageddon-viewed-profile` | Apocalypse with up to 3 viewed products on top | same | 1.00 (17:50–18:25) |
| `tati-cart-profile` | Apocalypse with up to 3 products the returning shopper carted in the history and never bought on top (those of the category viewed last first) | + history carts | 1.23 (20:05–20:50) |
| `lauri-titan-feedback` | Scores every candidate of the versions above with weights learned from our own carousels, and shows the 10 most likely to be bought | all of the above, weighed by `scripts/train_lauri.py` | 1.45 (20:05–20:50) |
| `lauri-colossus-feedback` | Titan retrained on one more hour of our carousels, which also knows the shopper's day: the categories they viewed today, what is in their cart and what they viewed | + shopper's day | 1.38 (20:05–20:50) |
| `lauri-titan-plus` | Titan plus the products a returning shopper carted in the history and never bought, as candidates | + history carts | 1.50 (22:30–23:05) |
| `lauri-titan-plus-als` | Titan+ plus each returning shopper's taste, from a factorisation of the history. **Final: every request that is not cold** | + ALS taste | see the final model above |
| `lauri-omni-plain` | Colossus' signals plus history carts, refitted on more feedback. **Final: cold requests** | + shopper's day, history carts | see the final model above |

Which versions ran when is in the heartbeats (`scripts/check_serving.py`, the dashboard's splits view); why
each one exists is in [docs/experiments.md](docs/experiments.md).

## How it works

```text
shop.requests ──► serving loop (src/dades_huzz/serving/loop.py), every 0.3 s
                    │  new requests, skipped if too old to answer within 3 s
                    ▼
                  version split ── sha256(request_id) picks the model version
                    │  (challengers get 200 ms, else the champion answers)
                    ▼
                  recommend(request, state) ── 10 products (src/dades_huzz/model.py)
                    │                ▲
                    │                └── State: available products, prices, categories,
                    │                    new products; refreshed every 0.25 s
                    │                    from shop.catalog_updates (src/dades_huzz/data.py)
                    ▼
                  check + repair ── 10 distinct, in stock, padded from the fallback
                    ▼
                  team_02.submissions (one insert per poll) ──► team_02.feedback

alongside: handover (one loop answers, others wait), watchdog (restart on crash or hang)
```

The pieces and who owns them are in [docs/contracts.md](docs/contracts.md). The words we use are in
[GLOSSARY.md](GLOSSARY.md).

## Setup

```
./scripts/setup.ps1      # Windows
sh scripts/setup.sh      # macOS / Linux
```

Requires [git](https://git-scm.com), [uv](https://docs.astral.sh/uv/) and the
[GitHub CLI](https://cli.github.com).

## Run it live

Needs `.env` with `TEAM_ID` and `RAWTREE_API_KEY` (names in `.env.example`; never commit the key).

```text
uv run python scripts/run_recommender.py
```

It serves the default split in `src/dades_huzz/serving/versions.py` (today Tati Terminator alone). Keep
the terminal open and the laptop plugged in. Stop it with Ctrl-C.

- **Another laptop takes over** with the same command: it waits (`standby`) and starts answering about 6 s
  after the active loop stops. Never pass `--no-handover` while another loop runs: every request would get
  two answers.
- **Change versions without losing answers:** start a second loop with the new split, then Ctrl-C the
  old one once the new one says `standby`. A switch costs about 10–17 requests.

  ```text
  uv run python scripts/run_recommender.py --versions tati-terminator-category-viewed=50,tati-ultimatum-viewed-first=50
  ```

- **Check it:** `uv run python scripts/check_serving.py --minutes 30` lists answered, missing, late and
  invalid requests, latency, and answers per version. On the practice round, compare versions with the
  leaderboard API in the same window: `https://datathon.rawtree.dev/api/state?by=model&from=<unix s>&to=<unix s>`.
- **Before leaving it unattended:** `uv run python scripts/check_unattended.py` checks keep-awake and
  the restarts without touching RawTree. Set the laptop to never sleep while plugged in.

### Sunday, final round

1. Before 09:45: `git pull`, `uv sync`, then start the loop on one laptop with the **best version alone**.
   The team's score counts every answer, so a split costs points. Check `standby -> active` and a clean
   `check_serving.py`.
2. 10:00: the stream switches to new shoppers, products and trends, with no reset: `shop.catalog` stays,
   new products arrive as `new_product` updates, and `State` gives them their category within seconds
   ([docs/challenge/qa.md](docs/challenge/qa.md)). Nothing to restart. If the loop ever logs
   `catalogue changed: ...`, restart through the handover above, because models load their lists only at start.
3. 10:00–12:00: the leaderboard is hidden. Run `check_serving.py --minutes 15` every 15 minutes, and keep
   one teammate's loop in `standby` as a spare, started with the same `--versions`. More spares are safe:
   if the active loop stops, only the one that started first takes over.

## Lane D dashboard

With the team credentials in your local `.env`, run from the repository root:

```text
uv run --with "streamlit>=1.67,<2" streamlit run app/dashboard.py --server.address 127.0.0.1
```

Choose **Team** to monitor practice and serving, or **Jury** to present one version's confirmed
sales. The app reads RawTree and the public competition leaderboard.

### Private online dashboard

A GitHub repository admin can connect [Streamlit Community Cloud](https://share.streamlit.io/)
to the private repository and deploy `main` with `app/dashboard.py` as the
entrypoint. Select Python 3.12. Community Cloud installs the app dependencies
from `app/requirements.txt`.

Keep the app private. To load results, the host needs `TEAM_ID` and an
authorized server-side `RAWTREE_API_KEY` as top-level secrets. Confirm with
the team which credential can be used for hosting. The local team key stays
in its git-ignored `.env`. After launch, open **Jury** and check that results
show a feedback timestamp.

## Layout

| Path | What |
|---|---|
| `src/dades_huzz/` | All shared logic: data, features, model, evaluation |
| `tests/` | Pass/fail checks, one file per module |
| `scripts/` | Commands you run: setup, train, predict, submit |
| `app/` | Streamlit dashboard for the team and jury demo |
| `notebooks/` | Exploration only; nothing imports from here |
| `docs/challenge/` | Brief, slides, notes, Q&A with the company |
| `docs/contracts.md` | Data schema and shared signatures agreed between lanes |
| `docs/experiments.md` | Every modelling attempt and its score |
| `docs/pitch.md` | The story, updated at every sync |
| `.agents/skills/` | Agent skills (source of truth; `.claude/` and `.github/` hold copies) |

`data/`, `outputs/` and `scratch/` are local only. The full map, with naming rules, is in
[AGENTS.md](AGENTS.md#where-things-go).

## Credits

Skills in `.agents/skills/` are adapted from [mattpocock/skills](https://github.com/mattpocock/skills)
(MIT, see `.agents/skills/LICENSE-mattpocock-skills`).

# Dades-huzz · A recommender that answers in under 3 seconds and never sleeps

Our Team 2's entry for the **Datathon FME 2026 · RawTree Real-Time Recommendation** challenge. About three
shoppers a second reach an online shop's carousel. For each one we have **3 seconds** to choose the **10
products** they see, and a hidden simulator decides whether they buy. Only Sunday 10:00–12:00 CET is scored.

**Short answer:** our final model is expected to sell **1.57 products per 100 shoppers**, against **0.7**
for the shop's best-seller list and **1.24** for our best single model. It ran from Saturday midday to Sunday noon,
with a spare laptop ready and **99.3 % of answers valid and on time**, and a timing problem we measured changed the rules for every
team.

| | |
|---|---|
| **Final model** | `pair:lauri-omni-plain+lauri-titan-plus-als`: one learned ranker for cold shoppers, another for the rest |
| **Reliability** | 127,940 answers from Saturday 13:00 to Sunday 01:45 CET, 99.3 % valid and on time (p50 about 1.1 s) |
| **Live testing** | 24 model versions, several on real shoppers at once, without losing reliability |
| **Rule change** | We found stock-outs arriving up to 2 s late. The organisers added a 5 s grace for all teams and credited us ([challenge page, "What's new", Sat 16:45](https://datathon.rawtree.dev)) |
| **Evidence** | 65 experiments logged, wins and losses ([docs/experiments.md](docs/experiments.md)), 74 merged PRs, 225 tests |

---

## How it works

**request → version split → ranker → check → submission → feedback**

Each request is **read**, sent to one **model version**, **scored**, **checked** (10 distinct products, all in
stock, padded from the best sellers if short) and **written** back. Feedback arrives seconds later, and the
rankers are retrained on it.

## Why the model looks like this

We went one step at a time, and each step answered the question the previous one left open:

| Step | What we did | Why | Result |
|---|---|---|---|
| 1. Baseline | The shop's all-time best sellers for everyone | A floor to beat, and the fallback if we are late | about 0.7 |
| 2. Rules ("Tati") | Best sellers of the category the shopper is looking at | The simplest use of what the shopper is doing. Scored offline first, with a pass rule fixed before the run | 0.92 vs 0.76 live, same hour |
| 3. Diagnosis | Read what sells in our own carousels | Every rule hit the same ceiling, so we needed to know which signals matter | favourite-category products sell 24x more in the same slot |
| 4. Learning ("Lauri") | A ranker learns each signal's weight | We had several strong signals and no way to weigh them by hand | 1.03 vs 0.85 for the best rule |
| 5. Tournaments | Four versions live at once, on the same minutes | Conversion moves with the time of day, so only same-minute comparisons are fair | **1.57** vs 1.24 |

No version won on both kinds of shopper, so the final serves the best one for each (expected purchases per
100 requests, leaderboard, Sunday 01:45–07:00 CET, `scripts/choose_final.py`):

| Version | Cold shoppers¹ | Everyone else |
|---|---|---|
| **`lauri-omni-plain`**: also reads what the shopper did today | **1.90** | 1.26 |
| **`lauri-titan-plus-als`**: adds each returning shopper's taste from 60 days of history | 1.55 | **1.32** |
| `lauri-titan-plus` (champion until then) | 1.39 | 1.13 |

¹ A new shopper, or one who viewed a product added during the event.

### How we trained the rankers

- **Data:** every product we showed live is one row: the shopper, the product, its slot, and whether it was
  bought. Training only on our own carousels means the model learns from the real simulator's reactions.
- **Model:** a logistic regression with one set of weights for new shoppers and one for returning ones.
  Gradient-boosted trees tied with it (log-likelihood −952.6 vs −958.9, row 43), so we kept the model we can
  read and explain.
- **Signals:**
  - **The session:** whether the shopper viewed the product, how recently, and whether it shares the
    category or subcategory of what they are looking at.
  - **The history:** their favourite categories and unbought carts from 60 days, and for Titan+ ALS a taste
    score from a matrix factorisation.
  - **Today and the shop:** what they did today, history and live sales, and price against the category.
- **Validation:** train on everything before the last 90 minutes, score those 90 minutes. A new set of
  weights goes live only if its held-out log-likelihood beats the previous model refitted on the same rows: a
  rule written before each run, so a result cannot be argued into a win afterwards (`scripts/train_lauri.py`).
- **Live:** the weights are stored in RawTree (`team_02.scratch`) and loaded by the serving loop. A new
  version then competes on a share of real shoppers before it can become the champion.

## Why the system survives the night

It has to answer three shoppers a second for a day and a night, on laptops, while we keep changing models. Four pieces
make that safe:

| Piece | How it works | Why we built it |
|---|---|---|
| **Watchdog** (`serving/watchdog.py`) | Runs the loop as a child process. It restarts it if it exits or goes 15 s without a sign of life, waits longer between restarts if it keeps failing, and keeps the laptop awake | An unanswered shopper gets the fallback and costs reliability points. A crash at 04:00 should cost seconds, not hours |
| **Handover** (`serving/handover.py`) | Every loop writes a heartbeat every 2 s. If the active one is silent for 6 s, the oldest spare takes over. A loop that cannot write steps down | A laptop can die or lose Wi-Fi without losing shoppers, and two loops never answer the same request |
| **Version split** (`serving/split.py`) | Each request goes to a version by a hash of its id. A challenger gets 200 ms per request and is taken out for 30 min if it is slow | To test new models on real shoppers while the champion keeps the score safe |
| **Fresh stock** (`serving/loop.py`) | Re-reads stock every 0.25 s and the whole catalogue every minute | An answer with a sold-out product is invalid and replaced by the fallback |

**The rule we changed.** Measuring that last piece, we found stock-outs reaching `shop.catalog_updates` up to
about 2 s after they happened: a correct answer could be judged invalid for a product nobody could know was
gone. We reported it with the measurements, and the organisers added a 5-second grace for every team,
crediting Dades Huzz on the challenge page. Our questions and their answers are in
[docs/challenge/qa.md](docs/challenge/qa.md).

## How we worked

Four people, three coding agents, one repository, one weekend. The rules that kept us from breaking each other's
work are in [AGENTS.md](AGENTS.md), which every agent reads first.

- **Four lanes with written contracts.** Each person owned one part. What the parts promise each other (the
  `State` the models receive, the `recommend` signature) is in [docs/contracts.md](docs/contracts.md), and a
  change to it needs its own PR.
- **Coding agents as teammates, with guardrails.** We used Claude Code (Marcel, Gabriel), Cursor (Eudald)
  and Codex (Miles). Shared skills in
  `.agents/skills/` gave every agent the same workflow: `grill-with-docs` to agree on the task before any
  code, `tdd` to write the test first, `pr-final` to review the branch and attach executed evidence to the PR.
- **`main` always shippable.** Short branches, squash PRs, tests in CI, and every modelling attempt logged
  as a row in [docs/experiments.md](docs/experiments.md) with its validation scheme, including the ones that
  got worse.
- **One vocabulary.** [GLOSSARY.md](GLOSSARY.md) fixes the words (candidate, cold request, handover...), so
  people and agents mean the same thing.

| Who | Lane | What they did |
|---|---|---|
| **Marcel** (`MarcelRochera00`) | A · Live system | The serving loop, the live `State` the models read (stock, categories, each shopper's day, trends), the version split, handover and watchdog. Found and reported the stock delay |
| **Gabriel** (`ProGabo`) | B · Models | The Tati rules and the Lauri rankers, the offline evaluation, the live tournaments and the final choice. Kept `main` shippable |
| **Eudald** (`dwakevy`) | C · Live learning | Live trends and recent purchases, and the cold-start rules for new shoppers |
| **Miles** (`milesgloekler`) | D · Decisions | The dashboard (Team and Jury views), the live A/B readout with confidence intervals, the pitch |

## What we learned, and what we'd do next

- **Short tests lie.** Fifteen-minute comparisons had as much noise as the differences we were measuring. Two
  versions at 50/50 for hours, with a confidence interval, settle what many short tests cannot.
- **Layers on top of a model hurt.** The same weights sold more alone than with extra rules on top, which is
  why the final model has none.
- **Next: train on the old carousel log.** `shop.history_sessions` holds 2 million past displays with 28,000
  purchases, about 20x our live feedback, with the probabilities needed to correct its bias towards best
  sellers. Its repeat purchases behave differently from the live shop, so they would be left out.
- **Not proven:** the final pair was chosen on one overnight read, and part of its lead on cold shoppers came
  from what they had done earlier in the day, which Sunday's new shoppers do not have.

## Run it yourself

Requires [git](https://git-scm.com), [uv](https://docs.astral.sh/uv/) and a `.env` with `TEAM_ID` and
`RAWTREE_API_KEY` (names in `.env.example`, never commit the key).

```bash
sh scripts/setup.sh                                   # or ./scripts/setup.ps1 on Windows
uv run python scripts/run_recommender.py              # answer live shoppers, with watchdog and handover
uv run python scripts/check_serving.py --minutes 30   # answered, late, invalid, latency per version
uv run pytest                                         # tests
```

Run the same command on a second laptop and it waits as a spare. Choose versions and shares with
`--versions name=share,...`. The list is in `src/dades_huzz/serving/versions.py`.

**Dashboard** (Tukey side challenge): the Team view compares versions and watches serving, and the Jury view
shows the final round's sales and where demand is rising.

```bash
uv run --with "streamlit>=1.67,<2" streamlit run app/dashboard.py --server.address 127.0.0.1
```

## Repository map

| Path | What |
|---|---|
| `src/dades_huzz/serving/` | The live loop: split, handover, watchdog, shoppers' day, trends |
| `src/dades_huzz/model.py`, `features.py` | The rankers and their signals |
| `src/dades_huzz/evaluation/` | Offline evaluation on the shop's history |
| `scripts/` | Commands: run, check, train, choose the final |
| `app/` | The dashboard |
| `docs/` | The challenge, our contracts, experiments and pitch |

How the team works, for us: [docs/COM-TREBALLEM.md](docs/COM-TREBALLEM.md) (Catalan). Skills in
`.agents/skills/` are adapted from [mattpocock/skills](https://github.com/mattpocock/skills) (MIT, see
`.agents/skills/LICENSE-mattpocock-skills`).

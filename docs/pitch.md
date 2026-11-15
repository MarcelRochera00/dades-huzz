# Jury pitch and demo

Use Barcelona time throughout. The team's Final version pairs Lauri Omni Plain with
Lauri Titan+ ALS. Confirm the spoken language with the team.

## Initial pitch · 3–5 minutes

**Question for the jury.** Would you test Tati on your store's recommendation carousel?

Start the dashboard from the [README launch command](../README.md#lane-d-dashboard) on the
presentation laptop. Prepare the following views.

- **Jury → Round → Final → Recommendation version → Lauri Omni Plain + Lauri Titan+ ALS.**
  Start at the top. Leave **Purchases per 100 displays** selected under **Sales activity over
  time**. Confirm the model heading and **Feedback through** timestamp. **Show latest round**
  opens Final automatically once feedback is available.
- Keep a second **Jury → Practice** tab with the same pair selected as a backup. Use it if
  Final results are pending. If you have five minutes, also prepare **Team → Active serving
  split** for the status check.

### Three-minute rehearsal and backup script

**0:00–0:45 · Jury, Final model**

> “A shopper opens the store carousel. Tati has three seconds to choose ten in-stock products.
> In the Final we use two rankers. Lauri Omni Plain handles shoppers who are new to the store
> or who just viewed a newly added product. Lauri Titan+ ALS handles the rest. It uses past
> shopping behaviour to surface products that are more likely to suit that shopper.”

Point to **Final · Lauri Omni Plain + Lauri Titan+ ALS**. If using the Practice backup, say
“This is a Practice recording of the same two rankers” and point to the **Practice** label.

**0:45–1:25 · Jury, confirmed results**

> “The simulator recorded [purchases] purchases and [sales] in simulated sales across [displays]
> confirmed recommendation displays. That's [rate] purchases per 100 displays. Each display is
> one list the shopper saw. The chart shows the purchase rate in ten-minute windows.”

Read the three cards, display count, and **Feedback through** timestamp from the screen.
Use **Results so far** while the round is running. If the organizers have published it,
open **Official competition score** separately. The score also uses purchase probabilities,
cold-start performance, and reliability.

**1:25–2:30 · Jury, Where store demand is rising**

> “RawTree SQL counts past purchases by product for the best-seller list. It joins live purchases
> to the catalogue so we can track demand by subcategory. The multiplier divides the last
> 15 minutes' share of store purchases by the share since the simulation began. Six percent
> versus one percent would be six times the usual share. When a category rises, the store
> can check stock and test featuring those products.
>
> “Tati reads each request and writes ten ranked IDs back to RawTree. The same request ID
> connects what we recommended with what the shopper saw and what sold.”

Read one current subcategory, multiplier, and window if a bar is visible. If the page shows the
Game Consoles replay, introduce it as a Saturday Practice example. The [RawTree showcase](#rawtree-showcase)
below gives you a fixed replay and the pipeline explanation.

**2:30–3:00 · Jury, controlled store pilot**

> “In your store, split eligible traffic between Tati and your current best-seller list. Track
> purchases and sales per 100 eligible visits, and check that recommendations arrive on time.
> That gives you the evidence to decide whether to expand.”

### RawTree showcase

For the three-minute take, show the demand chart while you speak. If you have another minute after
the multiplier, show this read-and-write path. Use an illustrative request and aggregate results
for the recording.

| On screen | What to say |
| --- | --- |
| `shop.history_events` → purchases by product | “In SQL we filter to purchases, group by product ID, and count. That gives us the historical popularity used to rank best sellers.” |
| `shop.events` + `shop.catalog` / `shop.catalog_updates` → purchases by subcategory | “SQL joins purchases to the catalogue, including products added during the event, and aggregates by subcategory. The app compares the last 15 minutes with the period since the simulation began. A demand flag needs at least twice the usual share and at least 25 purchases above what that share predicts.” |
| `shop.requests` → ranked list → `team_02.submissions` | “The serving loop reads a new request and its recent views, checks availability against catalogue updates, and ranks the candidates. It writes the request ID, ten ordered product IDs, and the model version to RawTree within the three-second deadline.” |
| `team_02.feedback` → Jury totals | “The simulator reports the list it showed and the purchase outcome. The dashboard matches the request ID and the exact list shown to credit purchases and sales to the right version.” |

For a stable cutaway, run the read-only replay from the repository root before recording. Capture
only the result and label it **Saturday Practice · 14 Nov · 20:42 CET**. It uses the same demand
calculation as Jury and returns **Game Consoles 6.01×** for that window. Use **6.01×** when showing
this replay. The Jury panel's fallback copy refers to the Saturday peak of **6.98×**.

```text
uv run python -c "from datetime import UTC, datetime; from dades_huzz.data import RawTree; from dades_huzz.dashboard_jury import read_demand_trends; print(read_demand_trends(RawTree.from_env(), datetime(2026, 11, 14, 19, 42, tzinfo=UTC)))"
```

[Historical purchase SQL](../src/dades_huzz/features.py) ·
[Demand SQL and thresholds](../src/dades_huzz/serving/trends.py) ·
[Serving contract](contracts.md#submission-format) ·
[Jury results query](../src/dades_huzz/dashboard_jury.py)

### If the slot is four or five minutes

- **Four minutes.** Expand the RawTree showcase to trace the illustrative request through the
  SQL signals, ordered answer, and feedback. Use the saved replay output.
- **Five minutes.** Show **Active serving split** at the top of Team. Point to the planned share
  and the last active heartbeat. If the loop has stopped, use a captured Final-round view with
  the time visible. For the selection rationale, use the overnight practice evidence in
  Experiment 68. [Final model notes](../README.md#the-final-model-and-how-we-got-there) ·
  [Experiment 68](experiments.md)

### Recording the backup

1. Rehearse the three-minute script with both Jury tabs ready. Open **Final** if the pair has
   confirmed displays. Keep the round label, model name, feedback timestamp, and demand window
   visible.
2. Capture only the presentation window. Read the cards as they appear when recording. Keep
   credentials, raw shopper IDs, and notifications outside the recording. Use the saved
   demand replay output if you include the extended RawTree cutaway.
3. Save the Final take to `outputs/jury-final-demo.mp4` or the Practice take to
   `outputs/jury-practice-demo.mp4`. Check audio, chart legibility, and offline playback.
   Introduce the backup as a recording and name the round it shows.

## Finalist presentation · three slides and one live interaction

Confirm the finalist slot length with the organizers. Use the slides to explain the recommendation
and the evidence behind it. Reserve the live interaction for the result the jury can check.

| Slide | What to show | What the jury should understand |
| --- | --- | --- |
| **1. One shopper, ten products, three seconds** | Follow an illustrative shopper who just viewed a newly added product. Show the RawTree request, SQL-derived purchase counts, catalogue updates, the ordered answer, and the feedback match. | How shopper context and current stock shape the list. |
| **2. Why the Final uses two rankers** | Show the overnight practice selection from **01:45–07:00 CET**. Omni Plain led on cold requests and Titan+ ALS led on the rest. The combined **1.57 vs. 1.24 purchases per 100 requests** against Titan+ alone is an expected rate calculated from the separate practice arms. The planned confirmation window did not run. | Why the team chose the pair and how much certainty the practice data provides. |
| **3. What shoppers bought in the Final** | Show the pair's confirmed simulated sales, purchases, and purchase rate. Read the display count and feedback timestamp. If available, label the official team score separately. | What the simulator observed and what a controlled store pilot could establish. |

**One live interaction after slide 3.** Open the prepared **Jury → Final** tab on the pair.
Point to the confirmed results. Hover over one bar in **Sales activity over time** to show
its display count, purchase count, and rate. If the dashboard is unavailable, use a prepared
still with the round and timestamp visible.

### Evidence for rehearsal and jury questions

- **History and method.** The history notebook used 60 days of data, including two million old
  carousel requests. The model team built lists using earlier days and checked them on later
  days, accounting for how often the old carousel showed each product in each slot.
  [History findings](https://github.com/ProGabo/dades-huzz/issues/5#issuecomment-6877885738)
- **Why this Final version.** The team selected the pair from the overnight practice window.
  New shoppers in the Final start with little activity, so the overnight cold result may
  overstate Omni Plain's advantage. [Final model notes](../README.md#the-final-model-and-how-we-got-there) ·
  [Experiments 67–68](experiments.md)
- **What to test next.** Run larger same-window comparisons for new shoppers and for shoppers
  who viewed a newly added product. The catalogue continues receiving updates during the final.
  [Sunday data](challenge/qa.md) · [Dashboard plan](challenge/side-challenge.md) ·
  [Judging brief](challenge/brief.md)

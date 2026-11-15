# Jury pitch and demo

Use Barcelona time throughout. The team's Final version pairs Lauri Omni Plain with
Lauri Titan+ ALS. Confirm the spoken language with the team.

## Initial pitch · 3–5 minutes

**Question for the jury.** How did we choose what to serve in the Final, and what did shoppers buy?

Start the dashboard from the [README launch command](../README.md#run-it-yourself) on the
presentation laptop. Prepare the following views.

- **Team → Compare versions from → 15 Nov 00:22:45 CET → Purchase results.** Start here.
  The recorded split ran until about **08:46 CET** and shows four versions with a planned
  25% of traffic each. Keep **Backup use** ready if asked about fallbacks.
- **Jury → Round → Final → Recommendation version → Lauri Omni Plain + Lauri Titan+ ALS.**
  Start at the top. Leave **Purchases per 100 displays** selected under **Sales activity over
  time**. Confirm the model heading and **Feedback through** timestamp. **Show latest round**
  opens Final automatically once feedback is available.
- Keep a **Jury → Practice** tab with the same pair selected as a backup if Final results
  are pending.

### Three-minute rehearsal and backup script

**0:00–0:35 · Team, overnight comparison**

> “Overnight, we ran four versions side by side so they faced the same conditions. The Team
> view shows how much traffic each version got and how often its assigned requests led to a
> purchase. We could see whether a version did well on cold requests as well as looking at
> its overall rate.”

Point to the recorded window, **With feedback**, and **Cold purchases / 100**. Cold means a
new shopper or a shopper who viewed a newly added product.

**0:35–1:15 · Team, what we chose**

> “To choose the Final version, we used the organizers’ Practice estimates from 01:45 to
> 07:00. Omni Plain led on cold requests at 1.90 expected purchases per 100 requests.
> Titan+ ALS led on the other requests at 1.32. We paired them so each ranker handles the
> group where it led. Now let’s see what shoppers bought when we served that pair.”

The visible Team table covers a longer period and reports recorded outcomes. Read the two
selection rates from the overnight leaderboard evidence. If asked about confirmation, say
the planned follow-up split did not run. [Experiment 68](experiments.md)

**1:15–2:20 · Switch to Jury, confirmed results**

> “Trained on past carousel results, Lauri uses browsing and cart activity to rank in-stock
> products and recommend the top ten. Here’s the Final pair. The simulator recorded [purchases]
> purchases and [sales] in simulated sales across [displays] confirmed displays. That’s [rate]
> purchases per 100 lists shown.”

Point to **Final · Lauri Omni Plain + Lauri Titan+ ALS** and read the cards and **Feedback through**
timestamp. Use **Results so far** while the round is running. If using the backup, introduce it as
Practice and point to the round label. Open **Official competition score** separately if published.

**2:20–3:00 · Jury, Store trends and RawTree**

> “Store trends compares a subcategory’s share of store purchases in the last 15 minutes with
> its share since the simulation began. The dashboard reads RawTree through its SQL API and
> matches feedback to our answer by request ID and the exact list shown.”

If the panel has a red outline, read one subcategory, multiplier, and window. In a quiet window,
point to **No trends detected** and the timestamp. Return to the confirmed results.

### RawTree showcase

Use this read-and-write path for questions or the optional fourth minute. Use an illustrative
request and aggregate results for the recording.

| On screen | What to say |
| --- | --- |
| `shop.history_events` → purchases by product | “In SQL we filter to purchases, group by product ID, and count. That gives us the historical popularity used to rank best sellers.” |
| `shop.events` + `shop.catalog` / `shop.catalog_updates` → purchases by subcategory | “SQL joins purchases to the catalogue, including products added during the event, and aggregates by subcategory. The app compares the last 15 minutes with the period since the simulation began. A demand flag needs at least twice the usual share and at least 25 purchases above what that share predicts.” |
| `shop.requests` → ranked list → `team_02.submissions` | “The serving loop reads a new request and its recent views, checks availability against catalogue updates, and ranks the candidates. It writes the request ID, ten ordered product IDs, and the model version to RawTree within the three-second deadline.” |
| `team_02.feedback` → Jury totals | “The simulator reports the list it showed and the purchase outcome. The dashboard matches the request ID and the exact list shown to credit purchases and sales to the right version.” |

For a stable cutaway, run the read-only replay from the repository root before recording. Capture
only the result and label it **Saturday Practice · 14 Nov · 20:42 CET**. It uses the same demand
calculation as Jury and returns **Game Consoles 6.01×** for that window. Use **6.01×** when showing
this replay in the extended cutaway.

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
  Experiment 68. [Final model notes](../README.md#why-the-model-looks-like-this) ·
  [Experiment 68](experiments.md)

### Recording the backup

1. Rehearse the switch from the overnight Team comparison to the Final Jury tab. Keep the
   Practice backup ready. Show the round label, model name, feedback timestamp, and demand
   window while recording the Jury view.
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
| **3. What shoppers bought in the Final** | Show the pair's confirmed simulated sales, purchases, and purchase rate. Read the display count and feedback timestamp. If available, label the official team score separately. | What the simulator recorded for the selected model version. |

**One live walkthrough between slides 2 and 3.** Start on the recorded overnight split in
**Team → Purchase results**. Then switch to the prepared **Jury → Final** tab on the pair.
Point to the confirmed results and hover over a bar in **Sales activity over time** to show
its display count, purchase count, and rate. If the dashboard is unavailable, use prepared
stills of the Team comparison and the Jury results with the round and timestamps visible.

### Evidence for rehearsal and jury questions

- **History and method.** The history notebook used 60 days of data, including two million old
  carousel requests. The model team built lists using earlier days and checked them on later
  days, accounting for how often the old carousel showed each product in each slot.
  [History findings](https://github.com/ProGabo/dades-huzz/issues/5#issuecomment-6877885738)
- **Why this Final version.** The team selected the pair from the overnight practice window.
  New shoppers in the Final start with little activity, so the overnight cold result may
  overstate Omni Plain's advantage. [Final model notes](../README.md#why-the-model-looks-like-this) ·
  [Experiments 67–68](experiments.md)
- **Data and judging.** The catalogue continues receiving updates during the Final.
  [Sunday data](challenge/qa.md) · [Dashboard plan](challenge/side-challenge.md) ·
  [Judging brief](challenge/brief.md)

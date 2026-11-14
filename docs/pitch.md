# Jury pitch and demo

The team will choose the final model version and spoken demo language. Use Barcelona time
throughout. The three-minute core is also the script for the Saturday Practice backup video.

## Initial pitch · 3–5 minutes

**Question for the jury.** Would you test personalized recommendations in your store?

Start the dashboard from the [README launch command](../README.md#lane-d-dashboard) on the
presentation laptop. Prepare two tabs before you start.

- **Jury → Round → Practice → Recommendation version → `tati-terminator-category-viewed`.**
  Start at the top and keep **Purchases per 100 displays** selected under **Sales activity over
  time**. For the live presentation, use **Final** and the team's selected version once that
  version has confirmed displays. Keep the Practice tab ready for rehearsal or pending Final
  feedback. The best-seller comparison stays the same recorded Practice experiment in either round.
- **Team → Compare versions from → 14 Nov 15:56:31 CET → Purchase results.** Check that the
  comparison ends at **16:06:06 CET** and the table shows Destroyer and Terminator. Keep
  **Backup use** ready in the same tab.

### Three-minute rehearsal and backup script

**0:00–0:45 · Jury, Personalized recommendations vs. best sellers**

> “This store starts with the same in-stock best sellers for every carousel. Tati has three seconds
> to choose ten in-stock products using what the shopper was browsing. In this 20-minute
> Saturday practice test, Destroyer used best sellers from the category the shopper last
> browsed. It reached 1.037 expected purchases per 100 requests, compared with 0.747 for the
> storewide best sellers. That's 39% higher in this window. These are RawTree's simulator
> estimates from two versions running side by side.”

Point to the two bars and the date. The test ran **14 Nov, 15:30–15:50 CET**, with **1,843**
Destroyer requests and **1,757** best-seller requests. [Experiment 17](experiments.md)

**0:45–1:25 · Jury, What shoppers bought in the simulation**

> “Here are the purchases the simulator actually recorded when shoppers saw Terminator's
> recommendations during Practice. We recorded [purchases] purchases and [sales] in simulated
> sales from [displays] confirmed displays. That's [rate] purchases per 100 displays. Each bar
> covers ten minutes, so we can see when the purchase rate changes as traffic varies.”

Read **Simulated purchases**, **Simulated sales**, **Purchases per 100 displays**, and the display
count from the screen. Point to **Feedback through** and mention that the latest window may still
be filling. Each display is one recommendation list shown. For Final, replace the first sentence
with “Here are the purchases the simulator recorded when shoppers saw [version]'s recommendations
during Sunday's Final.” Open **Official competition score** if the organizers have published it.
That score uses the simulator's purchase probabilities and credits cold-start performance and
reliability as well.

**1:25–2:05 · Jury, Where store demand is rising**

> “RawTree SQL counts past purchases by product for the best-seller list. It joins live purchases
> to the catalogue so we can track demand by subcategory. This multiplier divides the last
> 15 minutes' purchase share by the share since the simulation began. Six percent versus one
> percent would be six times the usual share. A store could check stock and feature those products.
> Tati reads each request and writes ten ranked IDs back to RawTree. Feedback tells us what sold.”

If a bar is visible, read its subcategory, multiplier, and window. If the page shows the Saturday
replay instead, read the displayed Game Consoles example as a historical Practice result. The
multiplier describes **storewide purchase share**. The best-seller comparison measures the
recommendation's expected purchase rate. The [RawTree showcase](#rawtree-showcase) below gives you
a fixed replay and the pipeline explanation.

**2:05–2:40 · Team, Purchase results → Backup use**

> “How did we decide what to give more traffic? Here's a different practice test. Destroyer
> recorded nine purchases and Terminator eight. The uncertainty range crosses zero, so we'd keep
> testing before calling a winner. On reliability, the organizers' fallback covered 22 requests
> assigned to Destroyer and nine assigned to Terminator. That gives us a concrete issue to
> investigate before giving either version more traffic.”

Point to the difference and its 95% interval (Terminator versus Destroyer, **−1.23 to +0.83
purchases per 100 assigned requests with feedback**). Then click **Backup use** and point to
**Organizer fallback**. [Experiments 17–20](experiments.md)

**2:40–3:00 · Back to Jury, controlled store pilot**

> “In your store, split traffic between Tati and your current best-seller list. Compare purchases
> and sales per 100 eligible visits, and check that recommendations arrive on time before expanding.”

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
- **Five minutes.** Also use **Which cold requests need help?** in Team. Explain that a new
  shopper has little browse history, and a newly added product has little sales history. Use the
  visible time window when discussing the chart or table.

### Recording the backup

1. Rehearse the three-minute **Practice** script with both tabs ready. Keep the date on the
   benchmark, the **Practice** label and feedback timestamp, and the demand window visible.
2. Capture only the presentation window. Use the numbers visible on Jury as you record. Keep
   credentials, raw shopper IDs, and notifications outside the recording. Use the saved
   demand replay output if you include the extended RawTree cutaway.
3. Save the video to `outputs/jury-practice-demo.mp4`. Check the audio, chart legibility, and
   playback with the network off. If the live dashboard fails, introduce the clip as Saturday
   Practice. If only Final feedback is pending, use the prepared Practice view and say which
   results are pending.

## Finalist presentation · three slides and one live interaction

Confirm the finalist slot length with the organizers. Use the slides to explain the recommendation
and the evidence behind it. Reserve the live interaction for the decision the jury can check.

| Slide | What to show | What the jury should understand |
| --- | --- | --- |
| **1. One shopper, ten products, three seconds** | Follow an illustrative shopper who just viewed a product added during the event. Show the RawTree request, SQL-derived purchase counts and catalogue updates, the ordered answer, and the feedback match. Use the ranking rules of the team's selected version. | How shopper context, current stock, and live store activity shape the list. |
| **2. What made us change the recommendation** | Show the historical slot observation (0.45 purchases per 100 displays in slot 1 versus 0.10 in slot 5). Explain that we built lists on earlier days and evaluated on later days, accounting for what the old carousel tended to show. Use the Jury benchmark for the same-window Destroyer versus in-stock best sellers result, labeled as simulator estimates. | How the team used history to form a hypothesis and then tested it on the practice stream. |
| **3. What we chose and how we know** | State the team's final choice when available, the evidence used to choose it, and one limitation. Use a still of the Jury results with the round and timestamp visible. If available, label the official team score separately from the confirmed simulated purchases and sales. | What the system delivered and what a controlled store pilot could establish. |

**One live interaction between slides 2 and 3.** Prepare **Team → Backup use** on the agreed
comparison window. Click **Purchase results** to reveal the difference and its range. Give
the decision in one sentence. For rehearsal with the Destroyer–Terminator window, say the
observed purchase gap leaves the lead uncertain and the backup counts give the team a reliability
question to investigate. For the finalist session, use the team's chosen evidence and verified
numbers. If the dashboard is unavailable, show a prepared still of the same comparison.

### Evidence for rehearsal and jury questions

- **History and method.** The history notebook used 60 days of data, including two million old
  carousel requests. The model team built lists using earlier days and checked them on later
  days, accounting for how often the old carousel showed each product in each slot.
  [History findings](https://github.com/ProGabo/dades-huzz/issues/5#issuecomment-6877885738) ·
  [Experiments 3–5, 14 and 17](experiments.md)
- **Practice comparison.** The rehearsal window uses the team's recorded split. Newer splits
  come from the active loop's records in `team_02.scratch`. [Team query](../src/dades_huzz/dashboard_splits.py)
- **What to test next.** Run larger same-window comparisons for new shoppers and for shoppers who
  viewed a newly added product. The catalogue continues receiving updates during the final.
  [Sunday data](challenge/qa.md) · [Dashboard plan](challenge/side-challenge.md) ·
  [Judging brief](challenge/brief.md)

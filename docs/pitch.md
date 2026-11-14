# Jury pitch and demo

The team will choose the final model version and spoken demo language. Destroyer and Terminator are
the examples for Saturday practice. Use Barcelona time throughout.

## Initial pitch · 3–5 minutes, led by the dashboard

**Question for the jury.** Would you give a challenger more traffic based on this test? The demo
answers it with one recorded comparison, then shows what the shopper-facing results look like.

Start from the [README launch command](../README.md#lane-d-dashboard) on the presentation laptop.
In **Team**, preselect **Compare versions from → 14 Nov 15:56:31 CET** and leave **Backup use** ready
for the opening. Check that the comparison ends at **16:06:06 CET** and the table shows Destroyer and
Terminator. In a second local tab, prepare **Jury → Practice → `tati-terminator-category-viewed`**.
Using two prepared tabs saves time and preserves each view's selections.

### Three-minute rehearsal and backup script

**0:00–0:40 · Team, Backup use**

> “A simulated shopper opens the carousel. We have three seconds to pick ten available products.
> Destroyer recommends best sellers from the last category they viewed. Terminator can also
> include products they already viewed. We built the lists on earlier days and checked them on
> later days, accounting for what the old carousel tended to show. Then we ran both versions at
> the same time with a planned 50/50 split.”

**0:40–1:40 · Click Purchase results, then return to Backup use**

> “Would you give Terminator more traffic on this evidence? Destroyer recorded nine purchases
> from 837 assigned requests. Terminator recorded eight from 888. The observed gap is small.
> Look at the range. It spans from about 1.2 fewer to 0.8 more purchases per 100 requests for
> Terminator. Either version could be ahead, so this purchase sample alone calls for more traffic
> in the test before choosing a winner.”
>
> “Now check how reliably each version answered. The organizers' fallback covered 22 Destroyer
> requests and nine Terminator requests. I'd check why those fallbacks happened before giving
> either version more traffic.”

Point to the range and say that it crosses zero. Point to the **Organizer fallback** column when you
switch back. Treat the traffic decision as what this sample supports. The team also used the
organizers' expected purchase rates to make practice decisions. [Experiments 17–20](experiments.md)

**1:40–2:30 · Switch to the prepared Jury tab**

> “So far we've compared every request we assigned, even if it needed a backup. Here I'm asking
> a shopper-facing question. What happened when the simulator showed Terminator's list? This is
> the broader Practice run. These cards show simulated purchases and sales from confirmed displays. You
> can see when those purchases happened and how far the feedback has arrived.”

Read **Purchases**, **Sales**, and the **Feedback through** timestamp from the screen. Point once to
**Purchases over time**. In the checked snapshot at **18:43 CET on 14 November**, the cards showed
**167 simulated purchases**, **€6,490.33 in simulated sales**, and **0.92 purchases per 100 times
shown** across **18,249 confirmed displays**. Use the current cards when recording. If final
feedback is available for the presentation, prepare **Jury → Final** and the team's selected
model version. Replace the Practice narration with “Here's what the simulator recorded when it
showed [selected version] during Sunday's final.” Read the **Official team score** when published.
It also reflects cold requests and reliability, and it uses the simulator's purchase probabilities.

**2:30–3:00 · Stay on Jury**

> “RawTree gives us the store activity to build recommendations, the requests to answer, and
> the feedback to check what sold. When a product is added during the event, it has no past
> sales. One version we built uses live sales to move it up the list as it starts selling.”

### If the slot is four or five minutes

- **One extra minute for what we learned.** Before switching to Jury, use **Which cold requests need help?** to
  distinguish a new shopper from someone who viewed a newly added product. Explain why both can
  have little history and where recent store activity may help. Use the visible time window when
  discussing the chart or table.
- **One extra minute for how the team iterated.** Before the Destroyer–Terminator walkthrough,
  say that Destroyer reached **1.04 expected purchases per 100 requests** versus **0.75** for our
  best-seller version from **15:30 to 15:50 CET** (1,843 and 1,757 requests). Those are organizers'
  estimates from a different test. That result supported taking the last-viewed category forward
  as the next starting point. Explain why the time window matters. Morning and afternoon shoppers
  can behave differently, so a version's rate from another hour would mix those changes with the
  effect of the recommendations. Keep the on-screen comparison on Destroyer–Terminator.
  [Experiment 17](experiments.md)

### Recording the backup

Record the three-minute Practice walkthrough on the presentation laptop. Keep the round label and
feedback timestamp visible in Jury. Save it locally as `outputs/jury-practice-demo.mp4` and check the
audio and playback with the network off. If the browser or live data fails, introduce the clip as
Saturday practice and play it. If only final feedback is pending, switch to the prepared Practice
tab and say which results are pending. Rehearsal timing, recording and offline playback are pending.

## Finalist presentation · three slides and one live interaction

Confirm the finalist slot length with the organizers. Use the slides to explain the recommendation
and the evidence behind it. Reserve the live interaction for the decision the jury can check.

| Slide | What to show | What the jury should understand |
| --- | --- | --- |
| **1. One shopper, ten products, three seconds** | Follow a shopper who just viewed a product added during the event. Show the RawTree request and catalogue updates, how the recommender checks availability and ranks candidates, and the ordered list written back to RawTree. Use an illustrative request and the rules of the team's selected version. | Why shopper context, current stock and live store activity matter. |
| **2. What made us change the recommendation** | Show the historical slot observation (0.45 purchases per 100 displays in slot 1 versus 0.10 in slot 5). Explain that we built lists on earlier days and evaluated on later days, accounting for how often the old carousel showed each product in each slot. Then show the Destroyer versus our best-seller version practice result, labeled as organizers' expected purchase rates from the same window. | How the team used history to form and test a hypothesis, then tried it on the live stream. |
| **3. What we chose and how we know** | State the team's final choice when available, the evidence used to choose it, and one limitation. Use a still of the Jury results with the round and timestamp visible. If available, label the official team score separately from the confirmed purchases and sales. | What the system delivered and where the evidence is still uncertain. |

**One live interaction between slides 2 and 3.** Prepare **Team → Backup use** on the agreed
comparison window. Click **Purchase results** once to reveal the difference and its range. Give
the decision in one sentence. For rehearsal with the Destroyer–Terminator window, say the observed
purchase gap leaves the lead uncertain and the backup counts give the team a reliability question
to investigate. For the finalist session, use the team's chosen evidence and verified numbers.
If the dashboard is unavailable, show a prepared still of the same comparison while delivering
the same sentence.

### Evidence for rehearsal and jury questions

- **History and method.** The history notebook used 60 days of data, including two million old
  carousel requests. The model team built lists using earlier days and checked them on later
  days, accounting for how often the old carousel showed each product in each slot.
  [History findings](https://github.com/ProGabo/dades-huzz/issues/5#issuecomment-6877885738) ·
  [Experiments 3–5, 14 and 17](experiments.md)
- **RawTree inputs and outputs.** SQL counts purchases by product and joins store activity with
  the catalogue. The serving loop reads `shop.requests` and catalogue updates, then writes ten
  ordered IDs and a version name to `team_02.submissions`. The dashboard joins feedback by request
  ID. The rehearsal window uses the team's recorded split, and newer splits come from the active
  loop's records in `team_02.scratch`.
  [Feature queries](../src/dades_huzz/features.py) · [Serving contract](contracts.md) ·
  [Team query](../src/dades_huzz/dashboard_splits.py) · [Jury query](../src/dades_huzz/dashboard_jury.py)
- **What to test next.** Run larger same-window comparisons for new shoppers and for shoppers
  who viewed a newly added product, so the team can see which use of live store activity helps
  each group. The catalogue continues receiving updates during the final.
  [Sunday data](challenge/qa.md) · [Dashboard plan](challenge/side-challenge.md) · [Judging brief](challenge/brief.md)

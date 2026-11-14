# Pitch

Practice draft for the Sunday jury. The team will choose the final model version, presenter and
demo language. Refresh the results at each sync.

## Opening

“When a shopper opens the product carousel, we have three seconds to choose and order ten available
products. We want more of those visits to turn into purchases, even when a shopper has just arrived
or has looked at a product that was just added to the store.” [Challenge brief](challenge/brief.md)

## How we built Tati

1. **Start with the products that already sell.** The old carousel showed best sellers often.
   Across two million historical carousel requests, the first slot recorded about **0.45 purchases
   per 100 times shown**, and the fifth recorded **0.10**. That gave us a reason to test which
   products should go first. We used earlier history to build the lists, then checked them on later
   history, accounting for how often the old system showed each product in each slot.
   [History findings](https://github.com/ProGabo/dades-huzz/issues/5#issuecomment-6877885738) ·
   [Offline experiments 3–5](experiments.md)
2. **Use what the shopper just did and what is selling now.** Destroyer ranks best sellers in the
   shopper's last-viewed category. Terminator also lets recently viewed products appear. Other
   candidates give those products higher positions, use recent store activity for shoppers and
   products with little history, or update category rankings as products sell. The organizers
   confirmed that stock changes and new products keep arriving on Sunday.
   [Experiments 4, 14, 16 and 30](experiments.md) · [Sunday data](challenge/qa.md)
3. **Compare versions on the same traffic.** The serving loop gives each request one assigned
   version. The Team view compares what happened to those requests, including any that needed a
   backup. The team also checks whether a purchase lead is clear enough to act on and whether the
   version can keep answering on time. [Dashboard plan](challenge/side-challenge.md)

## Practice results to present

**Headline.** In a Saturday practice window from **15:30 to 15:50 Barcelona time**, Destroyer reached
**1.04 expected purchases per 100 requests** on the organizers' practice leaderboard, compared with
**0.75** for best sellers in the same window. The organizers reported 1,843 and 1,757 requests,
respectively. That supported using the shopper's last-viewed category as the next starting point.
Use this window as the spoken example. [Experiment 17](experiments.md)

| Show | Practice evidence | What to say |
| --- | --- | --- |
| Team · Purchase results | In the 15:56:31–16:06:06 split, Terminator got 8 purchases from 888 assigned requests and Destroyer got 9 from 837. Terminator's difference was **−0.17 per 100**, with a **95% range of −1.23 to +0.83**. | The range crosses zero, so either version could have the higher purchase rate. |
| Team · Backup use | In the same split, the organizers' backup answered **22 of 837 Destroyer requests (2.63%)** and **9 of 888 Terminator requests (1.01%)**. There were no confirmed takeovers by our own backup. | Check whether a version can serve its share of traffic before giving it more. |
| Jury · Terminator, Practice | With practice feedback through **18:09 Barcelona time on Saturday 14 November**, the list was shown **17,059 times**, with **154 confirmed simulated purchases**, **€5,812.46 in simulated sales** and **0.90 purchases per 100 times shown**. | These cards describe the selected version's confirmed displays. The official team score uses the simulator's purchase probabilities and also considers cold requests and reliability. |

The practice leaderboard headline comes from the organizers' expected purchase rates. The Team
example counts confirmed purchases by original assignment. The Jury example counts confirmed
purchases when feedback identifies the selected version's list as the one shown. The table gives
fixed rehearsal figures. Read the round and feedback timestamp aloud if the live totals differ.
The final results line is for the team to fill in once the organizers publish the score.

## RawTree in one minute

- **Learn.** SQL counts past purchases by product and joins store activity with the catalogue to
  learn which categories a returning shopper has used. Live sales counts come from `shop.events`.
  [Feature queries](../src/dades_huzz/features.py)
- **Serve.** The loop reads `shop.requests`, applies stock and catalogue updates, then writes ten
  ordered product IDs and the version name to `team_02.submissions` within three seconds.
  [Serving contract](contracts.md)
- **Measure.** RawTree joins each request to submissions and feedback by request ID. The Team view
  uses the request ID and the split settings to count backup answers under the originally assigned
  version. For this rehearsal window it uses the team's recorded settings. For new splits it reads
  the serving loop's updates in `team_02.scratch`. [Team query](../src/dades_huzz/dashboard_splits.py) ·
  [Jury query](../src/dades_huzz/dashboard_jury.py)

## What we would do with more time

Run larger same-window comparisons for new shoppers and for shoppers who viewed a newly added
product. That would help us tell which use of live store activity helps each group.

## Demo plan

Rehearse a three-minute version and confirm the slot length with the team. Use the local dashboard
on the presentation laptop. Run the [README command](../README.md#lane-d-dashboard) from the repo
root before the session and have both views ready.

| Time | On screen | What to do |
| --- | --- | --- |
| 0:00–0:35 | Team · Recommendation monitor | Explain the ten-product and three-second goal. Give the practice headline, then point to valid and on-time answers. |
| 0:35–1:30 | Team · Compare versions from **14 Nov 15:56:31 CET** | Open **Purchase results**, read the difference and range, and say why the purchase lead is uncertain. Open **Backup use** to show how often each side needed help. |
| 1:30–2:20 | Jury · Recommendation results | In rehearsal choose **Practice**, then `tati-terminator-category-viewed`. Read purchases, sales and purchases per 100 displays, then point to purchases over time. At the jury, choose **Final** and the team's selected version when its feedback is ready. Read the official team score when it is published. |
| 2:20–3:00 | Jury view stays on screen | Close with the three RawTree steps and explain how the team chose the final version from same-window practice evidence and reliability. |

**Backup.** Record a local screen capture of the rehearsal with **Practice** visible. Include the
Team comparison, the Jury cards and the feedback timestamp. Save it as `outputs/jury-practice-demo.mp4`
on the presentation laptop and test playback with the network off. If the live data or browser fails,
play the recording and introduce it as Saturday practice. If Final feedback or the official score is
still pending, say which result is pending and use the labeled practice example. Recording and
playback check are pending.

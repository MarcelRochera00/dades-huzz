# Side challenge: Tukey (FME)

Source: `SideChallenge_TukeyFME2026.pptx.pdf`, shared on the organisers' Google Drive
(<https://drive.google.com/file/d/1VRXre1uuOZajtbISL0Fwv_RxkU5CM8JD/view>). Original in Catalan; this
is a faithful English summary.

## Crux

Design a dashboard that helps your team make decisions about its main challenge. Select relevant
information and show what conclusions it yields and what decisions it helps to substantiate. Choose
whichever format best communicates your results, such as Power BI, Shiny, Tableau, or a web app.

## Judging criteria

1. **Usefulness to decision-making.** Does your dashboard help answer the questions your challenge
   poses? Does it provide a useful basis for decisions?
2. **Adequateness.** Are the representations in your dashboard appropriate for the data and the
   comparisons?
3. **Coherence.** Do the indicators, charts, and conclusions align with one another? Do they align
   with the data?

## Prize

The best dashboard from each main challenge advances. Only one of the three finalists wins the
Tukey Prize.

## Our plan

Lane D will build one Streamlit app in `app/` for the Tukey entry, with a Team view for day-to-day
decisions and a Jury view for the in-person demo. The README will give one command to launch the app.
Each chart will state the decision it supports.

### Team view

| Decision | What the view shows |
| --- | --- |
| What is serving now? | Show the planned version shares from a recent active serving heartbeat and flag any paused version. |
| Which version should we run? | Compare purchases per 100 assigned requests, euros per assigned request, request counts, and a confidence interval for the difference. Default to the full current A/B test. Start a new comparison period when the versions or their shares change. |
| How has each version performed over time? | Plot the organizers' expected purchases per 100 requests during Practice. From the start of Final, plot recorded purchases per 100 confirmed Practice displays. Mark split changes and highlight side-by-side tests. Show the count behind each point and leave gaps without traffic. |
| Does the recommender need attention? | Over the last 30 minutes, show the share of valid answers within three seconds, typical and slower response times, the organizer fallback rate, and counts of missing, late, and invalid answers. For a recorded side-by-side test, show how many of each version's assigned requests used the team's backup version or the organizers' fallback, with a separate rate for each. |
| Which cold requests need better recommendations? | Show request counts and purchase rates for new shoppers only, shoppers who recently viewed a newly added product only, and requests that meet both conditions. |
| What is changing in the store? | Compare recent product or category views, add-to-carts, and purchases with an earlier period of the same length. |

The A/B comparison uses purchases recorded in feedback. Credit each request and its outcome to
the version that was supposed to answer it, including when another version steps in or the
organizers show their fallback list. The **Purchase results** tab shows each challenger's purchases
per 100 requests with feedback minus the main version's rate, with a 95% confidence interval using
Newcombe's method for two independent proportions. A range that includes zero leaves the purchase
lead uncertain. Treat live snapshots as provisional and assess the difference at the end of the test.
A challenger pause or resume keeps the same comparison while the planned split and serving records
are continuous. The backup table counts confirmed takeovers across the whole comparison.
The chart labels its source and denominator. During Final, the organizers' API stops returning
Practice version windows. The chart then uses the simulator's recorded purchases for displays
matched to a submitted version by request ID and exact shown list, with all ranges ending at
the start of Final.

### Jury view

Briefly explain how Lauri selects recommendations, then show the model version and its confirmed
simulated sales, purchases, and purchases per 100 displays. Default to the Sunday final,
10:00–12:00 Barcelona time, once final-round feedback is available. During the final, use the
active serving split to choose the version automatically.
With no recent heartbeat, use the version with the most confirmed displays in that round. The
presenter can choose another version or open the results labeled **Practice**.

The chart defaults to purchase rate over time and can show raw purchase counts. Each window
shows its display count.

Show which store subcategories are gaining purchase share using the serving detector’s
15-minute multiplier. Label the store activity window and explain how the multiplier is calculated.

Keep the official team score available separately once the organizers publish it. It uses the
simulator’s purchase probabilities and other scoring components.

### Data and refresh

Match RawTree requests, submissions, and feedback by request ID. Use the version named in the
submission and the confirmed display for the Jury view. For the Team view, recover the original
assignment from the request ID and the version shares in effect. Use Lane A's active serving
records to find split changes, and use its documented practice history for earlier periods.
Show only periods with a known split and label approximate times. Fallback rates use assigned
requests with feedback. Show team-served requests with unknown version attribution separately.

Show **Feedback through [time]** and **Results so far** while feedback is arriving. Count requests
awaiting feedback as pending in the Team view. Until their outcomes arrive, exclude them from
completed-outcome rates and missed-answer counts. If a refresh fails, keep the last successful
results visible with their timestamp.

See [the team contract](../contracts.md) and [Lane D issue #9](https://github.com/ProGabo/dades-huzz/issues/9).

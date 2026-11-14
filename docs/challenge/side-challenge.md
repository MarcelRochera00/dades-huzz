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
| Which version should we run? | Compare purchases per 100 assigned requests, euros per assigned request, request counts, and a confidence interval for the difference. Default to the full current A/B test. Start a new comparison period when the versions or their shares change. |
| How has each version performed over time? | Plot expected purchases per 100 requests from the organizers' public practice leaderboard by version. Mark split changes and highlight periods when versions ran side by side. Show the request count behind each point and leave gaps when a version has no reported traffic. |
| Does the recommender need attention? | Over the last 30 minutes, show the share of valid answers within three seconds, typical and slower response times, and counts of missing, late, and invalid answers. |
| Which cold requests need better recommendations? | Show request counts and purchase rates for new shoppers only, shoppers who recently viewed a newly added product only, and requests that meet both conditions. |
| What is changing in the store? | Compare recent product or category views, add-to-carts, and purchases with an earlier period of the same length. |

The A/B comparison uses purchases recorded in feedback. Credit each request and its outcome to
the version that was supposed to answer it, including when another version steps in or the
organizers show their fallback list. The practice leaderboard chart uses the organizers' expected
purchase rates and labels them as such.

### Jury view

The presenter explicitly selects a version. Show its name, the date and time range, total
purchases, total sales in euros, purchases per 100 times shoppers saw that version's recommendations,
and one chart of purchases over time. The sales figures and purchase rate use feedback that
confirms shoppers saw the selected version's list. Default to the Sunday final, 10:00–12:00
Barcelona time, once final-round feedback is available. Until then, show results labeled **Practice**.

Display the official team score separately once the organizers publish it. The sales cards show
purchases that happened in the simulation. The official score uses the simulator's purchase
probabilities and other scoring components.

### Data and refresh

Match RawTree requests, submissions, and feedback by request ID. Use the version named in the
submission and the confirmed display for the Jury view. For the Team view, agree with Lane A on
how to recover the original assignment, the version shares, and when each split took effect.
That record also supports marking split changes on the practice chart.

Show **Feedback through [time]** and **Results so far** while feedback is arriving. Count requests
awaiting feedback as pending in the Team view. Until their outcomes arrive, exclude them from
completed-outcome rates and missed-answer counts. If a refresh fails, keep the last successful
results visible with their timestamp.

See [the team contract](../contracts.md) and [Lane D issue #9](https://github.com/ProGabo/dades-huzz/issues/9).

# Side challenge: Tukey (FME)

Source: `SideChallenge_TukeyFME2026.pptx.pdf`, shared on the organisers' Google Drive
(<https://drive.google.com/file/d/1VRXre1uuOZajtbISL0Fwv_RxkU5CM8JD/view>). Original in Catalan; this
is a faithful English summary.

**What is asked.** A dashboard that helps make decisions about our main challenge (RawTree real-time
recommendation). Select the relevant information and show which conclusions it brings and which
decisions it supports. Format and tool are free (Power BI, Shiny, Tableau, a web app...).

**How it is judged.**

1. **Usefulness for deciding**: does it help answer the challenge's questions and ground decisions?
2. **Suitability of the charts**: are the visualisations right for the data and the comparisons?
3. **Coherence of the results**: do indicators, charts and conclusions agree with each other and with
   the data?

**Prize.** Three finalists (the best dashboard of each main challenge), and one Tukey Prize for the best
of the three.

**Our plan** (lane D, see `docs/contracts.md`): one Streamlit app in `app/` that is at once our
monitoring tool (which version sells more, reliability and latency, live trends, cold start), the Tukey
entry, and the demo for the jury.

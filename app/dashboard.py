"""Private Streamlit dashboard for the RawTree team and jury demo."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st
from requests import RequestException

from dades_huzz.dashboard_jury import (
    FINAL_START_MS,
    PRACTICE_START_MS,
    JuryData,
    JuryPeriod,
    load_jury_data,
)
from dades_huzz.dashboard_leaderboard import (
    leaderboard_state,
    official_team_score,
    practice_series,
)
from dades_huzz.dashboard_splits import (
    SplitPeriod,
    SplitStats,
    load_splits,
    purchase_difference,
    read_split_stats,
)
from dades_huzz.dashboard_team import (
    comparison_periods,
    read_cold_groups,
    read_health,
    read_trends,
)
from dades_huzz.data import RawTree

BARCELONA = ZoneInfo("Europe/Madrid")
PRACTICE_START = datetime.fromtimestamp(PRACTICE_START_MS / 1000, UTC)
PRACTICE_END = datetime.fromtimestamp(FINAL_START_MS / 1000, UTC)

st.set_page_config(page_title="Tati · Recommendation dashboard", layout="wide")
st.html(Path(__file__).with_name("dashboard.css"))

TEAL = "#126e65"
BLUE = "#2b5a8e"
VERSION_COLORS = [TEAL, BLUE, "#a04e29", "#814d88", "#606d34", "#687484", "#ad4659"]


def chart_style(chart):
    return (
        chart.configure(background="white", font="Inter, Segoe UI, sans-serif")
        .configure_view(stroke=None)
        .configure_axis(
            domain=False,
            gridColor="#e9eff2",
            labelColor="#506676",
            tickColor="#dce6ea",
            titleColor="#365362",
            labelPadding=7,
            titlePadding=10,
        )
        .configure_legend(labelColor="#365362", titleColor="#172735")
    )


def local_time(epoch_seconds: float) -> str:
    return datetime.fromtimestamp(epoch_seconds, BARCELONA).strftime("%d %b %H:%M %Z")


def rate(count: int, total: int) -> str:
    return f"{100 * count / total:.2f}%" if total else "—"


def chart_time(value: datetime) -> str:
    return value.astimezone(BARCELONA).strftime("%d %b %H:%M")


def barcelona_chart_time(value: datetime) -> str:
    # Plot Barcelona wall time on a fixed axis regardless of the browser's time zone.
    return value.astimezone(BARCELONA).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def fetch_latest[T](key: str, load: Callable[[], T]) -> T | None:
    """Keep the last successful response for each section in this browser session."""
    try:
        result = load()
    except (RequestException, KeyError, TypeError, ValueError):
        if key in st.session_state:
            result, saved_at = st.session_state[key]
            st.warning(
                f"Refresh failed. Showing the last results available at {local_time(saved_at)}."
            )
            return result
        st.warning(
            "Data could not be loaded. Check the connection and the local .env file."
        )
        return None
    st.session_state[key] = (result, datetime.now(UTC).timestamp())
    return result


@st.cache_data(ttl=25, show_spinner=False)
def health_data(end: datetime) -> dict:
    return read_health(RawTree.from_env(), end)


@st.cache_data(ttl=50, show_spinner=False)
def cold_data(end: datetime) -> list[dict]:
    return read_cold_groups(RawTree.from_env(), end)


@st.cache_data(ttl=50, show_spinner=False)
def trend_data(end: datetime) -> list[dict]:
    return read_trends(RawTree.from_env(), end)


@st.cache_data(ttl=25, show_spinner=False)
def jury_data() -> JuryData:
    return load_jury_data(RawTree.from_env())


@st.cache_data(ttl=55, show_spinner=False)
def scoreboard() -> dict:
    return leaderboard_state()


@st.cache_data(ttl=280, show_spinner=False)
def leaderboard_history(team: str, start: datetime, end: datetime) -> list[dict]:
    return practice_series(team, start, end)


@st.cache_data(ttl=50, show_spinner=False)
def split_history(end: datetime) -> list[SplitPeriod]:
    return load_splits(RawTree.from_env(), end)


@st.cache_data(ttl=50, show_spinner=False)
def split_stats(period: SplitPeriod) -> SplitStats:
    return read_split_stats(RawTree.from_env(), period)


def clock_slot(minutes: int = 1) -> datetime:
    now = datetime.now(UTC)
    timestamp = int(now.timestamp())
    interval = 60 * minutes
    return datetime.fromtimestamp(timestamp - timestamp % interval, UTC)


def serving_health(end: datetime) -> None:
    st.subheader("Is the recommender keeping up?")
    snapshot = fetch_latest("health", lambda: (end, health_data(end)))
    if snapshot is None:
        return
    end, health = snapshot
    st.caption(
        f"Requests from {chart_time(end - timedelta(minutes=30))} to {chart_time(end)} Barcelona time."
    )
    if health["completed"] == 0:
        st.info("No feedback has arrived for this window yet.")
    latest = health["feedback_through"]
    if latest is not None:
        st.caption(f"Feedback through {local_time(latest)}")
    columns = st.columns(4)
    columns[0].metric(
        "Valid and on time", rate(health["on_time"], health["completed"]), border=True
    )
    columns[1].metric(
        "Organizer fallback",
        rate(health["organizer_fallbacks"], health["completed"]),
        help="Share of requests with feedback where organizers showed their backup list.",
        border=True,
    )
    columns[2].metric("Awaiting feedback", f"{health['pending']:,}", border=True)
    slow = health["p95_ms"]
    columns[3].metric(
        "95% answered within",
        f"{slow / 1000:.2f} s" if slow is not None else "—",
        help="Time within which 95% of valid, on-time answers were delivered.",
        border=True,
    )
    median = health["p50_ms"]
    outcomes = " · ".join(
        f"{name.title()}: {health[name]:,}" for name in ("missing", "late", "invalid")
    )
    if median is not None:
        outcomes += f" · Typical on-time answer: {median / 1000:.2f} s"
    st.caption(
        f"{health['organizer_fallbacks']:,} organizer fallbacks out of "
        f"{health['completed']:,} requests with feedback · {outcomes}"
    )


def expected_performance(periods: list[SplitPeriod]) -> None:
    st.subheader("Which versions sold more in practice?")
    st.caption(
        "Use periods with side-by-side traffic to compare versions under similar conditions. "
        "These figures are the organizers’ expected purchases, based on the simulator’s probabilities."
    )
    team = RawTree.from_env().team
    hours = st.selectbox(
        "Practice history",
        [2, 6, 12, 24],
        index=1,
        format_func=lambda h: f"Last {h} hours",
    )
    end = min(clock_slot(5), PRACTICE_END)
    start = max(PRACTICE_START, end - timedelta(hours=hours))
    if end <= start:
        st.info("Practice has yet to produce a complete time window.")
        return
    key = f"practice:{hours}"
    if datetime.now(UTC) >= PRACTICE_END:
        previous = st.session_state.get(key)
        st.caption("Practice history stops updating when the final round starts.")
        rows = previous[0] if previous else None
    else:
        rows = fetch_latest(key, lambda: leaderboard_history(team, start, end))
    if not rows:
        st.info("No per-version results are available for this practice window.")
        return
    frame = pd.DataFrame(rows)
    frame["Start"] = frame["bucket_start"].map(barcelona_chart_time)
    frame["End"] = frame["bucket_end"].map(barcelona_chart_time)
    frame["Time (Barcelona)"] = frame["bucket_start"].map(chart_time)
    frame["Window end (Barcelona)"] = frame["bucket_end"].map(chart_time)
    axis = alt.X(
        "Start:T",
        scale=alt.Scale(type="utc", nice=False),
        title="Barcelona time",
        axis=alt.Axis(format="%H:%M"),
    )
    shading = (
        alt.Chart(frame[frame["overlap"]].drop_duplicates("bucket_start"))
        .mark_rect(color="#95b8da", opacity=0.24)
        .encode(x=axis, x2="End:T")
    )
    line = (
        alt.Chart(frame)
        .mark_line(point=True, invalid="break-paths-filter-domains")
        .encode(
            x=axis,
            y=alt.Y(
                "expected_purchases_per_100:Q",
                title="Expected purchases per 100 requests",
            ),
            color=alt.Color(
                "model_version:N",
                title="Model version",
                scale=alt.Scale(range=VERSION_COLORS),
            ),
            tooltip=[
                alt.Tooltip("Time (Barcelona):O", title="From"),
                alt.Tooltip("Window end (Barcelona):O", title="To"),
                alt.Tooltip("model_version:N", title="Version"),
                alt.Tooltip(
                    "expected_purchases_per_100:Q",
                    title="Expected purchases / 100",
                    format=".3f",
                ),
                alt.Tooltip("requests:Q", title="Requests in window"),
            ],
        )
    )
    chart = shading + line
    changes = []
    previous = None
    for period in periods:
        if (
            period.configuration != previous
            and frame["bucket_start"].min() <= period.start < frame["bucket_end"].max()
        ):
            changes.append(
                {
                    "Start": barcelona_chart_time(period.start),
                    "Change at": local_time(period.start.timestamp()),
                    "Split": period.configuration,
                    "Source": "Serving heartbeat (approximate)"
                    if period.source == "heartbeat"
                    else "Team log",
                }
            )
        previous = period.configuration
    if changes:
        chart += (
            alt.Chart(pd.DataFrame(changes))
            .mark_rule(color="#657589", strokeDash=[5, 4], strokeWidth=1.3)
            .encode(x=axis, tooltip=["Change at:N", "Split:N", "Source:N"])
        )
    st.altair_chart(
        chart_style(chart.properties(height=330)), theme=None, width="stretch"
    )
    st.caption(
        "Shaded windows show overlapping traffic. Dashed lines mark recorded split changes."
        if changes
        else "Shaded windows show overlapping traffic. No split changes are recorded in this range."
    )


def split_reliability(periods: list[SplitPeriod], end: datetime) -> None:
    st.subheader("How often did a backup answer?")
    tests = comparison_periods(periods)
    if not tests:
        st.info("No recorded side-by-side test is available yet.")
        return
    chosen = st.selectbox(
        "Compare versions from",
        [period.start for period in reversed(tests)],
        format_func=lambda key: key.astimezone(BARCELONA).strftime("%d %b %H:%M:%S %Z"),
    )
    period = next(period for period in tests if period.start == chosen)
    snapshot = fetch_latest(
        f"split-results:{chosen.isoformat()}", lambda: (period, split_stats(period))
    )
    if snapshot is None:
        return
    period, stats = snapshot
    source = (
        "Serving records · approximate boundaries"
        if period.source == "heartbeat"
        else "Recorded by the team"
    )
    st.caption(
        f"{period.start.astimezone(BARCELONA):%d %b %H:%M:%S} to "
        f"{period.end.astimezone(BARCELONA):%d %b %H:%M:%S %Z} · {source}"
    )
    if end - periods[-1].end > timedelta(seconds=10):
        st.caption(
            "The table covers the recorded test period. More recent traffic awaits split records."
        )
    if period.out:
        st.caption(
            f"Paused at some point in this test: {', '.join(period.out)}. "
            "Their assigned requests still count in this comparison."
        )
    st.caption(
        "Confirmed team backup counts requests where our main version covered a challenger. "
        "Organizer fallback means the organizers showed their own backup list. "
        "Rates use assigned requests with feedback. Pending requests are counted separately."
    )
    backups = []
    sales = []
    shares = period.shares
    for row in stats.rows:
        complete = row.completed
        backups.append(
            {
                "Assigned version": row.version,
                "Planned share": rate(shares[row.version], sum(shares.values())),
                "Assigned": row.assigned,
                "Pending": row.pending,
                "Unclear": row.unknown_actual,
                "Team backup": f"{row.champion_backups:,} ({rate(row.champion_backups, complete)})"
                if complete
                else "—",
                "Organizer fallback": f"{row.organizer_fallbacks:,} ({rate(row.organizer_fallbacks, complete)})"
                if complete
                else "—",
            }
        )
        sales.append(
            {
                "Assigned version": row.version,
                "With feedback": complete,
                "Purchases / 100": f"{100 * row.purchases / complete:.2f}"
                if complete
                else "—",
                "Revenue / request": f"€{row.revenue_eur / complete:.3f}"
                if complete
                else "—",
            }
        )
    backups_tab, sales_tab = st.tabs(["Backup use", "Purchase results"])
    with backups_tab:
        st.dataframe(backups, hide_index=True, width="stretch")
        unknown = sum(row.unknown_actual for row in stats.rows)
        if unknown:
            st.caption(
                f"{unknown:,} requests lack a confirmed answering version and could include more team backups."
            )
    with sales_tab:
        st.dataframe(sales, hide_index=True, width="stretch")
        st.caption(
            "Purchase results include what happened after either backup was shown."
        )
        show_purchase_differences(stats)


def show_purchase_differences(stats: SplitStats) -> None:
    main, *challengers = stats.rows
    st.markdown("**Difference in purchases per 100 requests**")
    st.caption(f"Comparing each challenger with the main version, {main.version}.")
    comparisons = []
    for challenger in challengers:
        difference = purchase_difference(challenger, main)
        comparisons.append(
            {
                "Challenger": challenger.version,
                "Observed difference": f"{difference.estimate:+.2f}"
                if difference
                else "—",
                "95% confidence interval": (
                    f"{difference.lower:+.2f} to {difference.upper:+.2f}"
                    if difference
                    else "Waiting for feedback from both versions"
                ),
            }
        )
    st.dataframe(comparisons, hide_index=True, width="stretch")
    st.caption(
        "Positive values favor the challenger. Negative values favor the main version. "
        "If the range includes zero, either version could be ahead. "
        "Use live results as a snapshot and judge the difference at the end of the test."
    )


def shopper_groups(end: datetime) -> None:
    st.subheader("Which cold requests need help?")
    snapshot = fetch_latest("cold", lambda: (end, cold_data(end)))
    if snapshot is None:
        return
    end, groups = snapshot
    st.caption(
        f"Last 30 minutes through {chart_time(end)} Barcelona time. Use this to decide which group to improve first."
    )
    st.dataframe(
        [
            {
                "Group": row["group"],
                "Requests": row["requests"],
                "Awaiting feedback": row["pending"],
                "Purchases": row["purchases"],
                "Purchases per 100 with feedback": rate(
                    row["purchases"], row["completed"]
                ),
            }
            for row in groups
        ],
        hide_index=True,
        width="stretch",
    )


def store_trends(end: datetime) -> None:
    st.subheader("Where is store demand changing?")
    snapshot = fetch_latest("trends", lambda: (end, trend_data(end)))
    if snapshot is None:
        return
    end, trends = snapshot
    st.caption(
        f"Latest 15 minutes through {chart_time(end)} Barcelona time versus the previous 15. Use this to decide which categories to investigate."
    )
    if not trends:
        st.info("No store activity is available for these windows.")
        return
    metric = st.selectbox(
        "Store activity",
        ["views", "carts", "purchases"],
        format_func=lambda key: {
            "views": "Views",
            "carts": "Add-to-carts",
            "purchases": "Purchases",
        }[key],
    )
    ranked = sorted(
        trends, key=lambda row: row[metric] - row[f"earlier_{metric}"], reverse=True
    )
    chart_rows = []
    for row in ranked:
        chart_rows.extend(
            [
                {
                    "Category": row["category"],
                    "Window": "Latest 15 minutes",
                    "Events": row[metric],
                },
                {
                    "Category": row["category"],
                    "Window": "Previous 15 minutes",
                    "Events": row[f"earlier_{metric}"],
                },
            ]
        )
    comparison = (
        alt.Chart(pd.DataFrame(chart_rows))
        .mark_bar()
        .encode(
            x=alt.X("Events:Q", title=None),
            y=alt.Y("Category:N", sort=[row["category"] for row in ranked], title=None),
            yOffset="Window:N",
            color=alt.Color(
                "Window:N", scale=alt.Scale(range=[TEAL, "#a8bac9"]), title=None
            ),
            tooltip=["Category:N", "Window:N", "Events:Q"],
        )
    )
    st.altair_chart(chart_style(comparison), theme=None, width="stretch")


def jury_score() -> None:
    st.divider()
    st.subheader("Official team score")
    state = fetch_latest("official_score", scoreboard)
    score = official_team_score(state, RawTree.from_env().team) if state else None
    if score is None:
        st.caption(
            "The official team score will appear here once the organizers publish it."
        )
    else:
        st.metric("Official team score", f"{score:.2f} / 100", border=True)


def jury_view() -> None:
    st.title("Recommendation results")
    data = fetch_latest("jury", jury_data)
    if not data:
        jury_score()
        return
    periods = {period.name: period for period in data.periods}
    available = [
        name
        for name, period in periods.items()
        if period.feedback_through_ms is not None
    ]
    if not available:
        st.info("No confirmed shopping results are available yet.")
        jury_score()
        return
    # Follow the final automatically when it first has feedback, unless the presenter picked a period.
    period_column, version_column = st.columns([1, 2])
    chosen_period = period_column.selectbox("Round", ["Show latest round", *available])
    period: JuryPeriod = periods[
        available[-1] if chosen_period == "Show latest round" else chosen_period
    ]
    st.caption(
        f"{period.name} · {local_time(period.start_ms / 1000)} to {local_time(period.end_ms / 1000)}"
    )
    st.caption(f"Feedback through {local_time(period.feedback_through_ms / 1000)}")
    versions = sorted({row.version for row in period.rows})
    if not versions:
        st.info("No team recommendations have a confirmed display in this round yet.")
        jury_score()
        return
    version = version_column.selectbox(
        "Model version",
        versions,
        index=None,
        placeholder="Choose a version",
        key=f"version:{period.name}",
    )
    if version:
        rows = [row for row in period.rows if row.version == version]
        displays = sum(row.shown for row in rows)
        purchases = sum(row.purchases for row in rows)
        revenue = sum(row.revenue_eur for row in rows)
        columns = st.columns(3)
        columns[0].metric("Purchases", f"{purchases:,}", border=True)
        columns[1].metric("Sales", f"€{revenue:,.2f}", border=True)
        columns[2].metric(
            "Purchases per 100 times shown",
            f"{100 * purchases / displays:.2f}" if displays else "—",
            border=True,
        )
        status = (
            "Simulator results so far"
            if datetime.now(UTC).timestamp() * 1000 < period.end_ms
            else "Simulator results"
        )
        st.caption(f"{status} · {displays:,} confirmed displays of {version}")
        st.subheader("Purchases over time")
        frame = pd.DataFrame(
            [
                {
                    "Time (Barcelona)": local_time(r.start_ms / 1000),
                    "Purchases": r.purchases,
                }
                for r in sorted(rows, key=lambda r: r.start_ms)
            ]
        )
        chart = (
            alt.Chart(frame)
            .mark_bar(color=TEAL, cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X(
                    "Time (Barcelona):O",
                    sort=frame["Time (Barcelona)"].tolist(),
                    title=None,
                    axis=alt.Axis(labelAngle=-35),
                ),
                y=alt.Y("Purchases:Q", title=None),
                tooltip=["Time (Barcelona):O", "Purchases:Q"],
            )
        )
        st.altair_chart(
            chart_style(chart.properties(height=285)), theme=None, width="stretch"
        )
        st.caption(
            "Shows when shoppers bought after seeing this version’s recommendations."
        )
    jury_score()


st.sidebar.title("Tati")
view = st.sidebar.radio("Dashboard view", ["Team", "Jury"])
try:
    RawTree.from_env()
except KeyError:
    st.error(
        "Set TEAM_ID and RAWTREE_API_KEY in the local .env file, then reload the dashboard."
    )
    st.stop()


@st.fragment(run_every="30s")
def show_view() -> None:
    if view == "Jury":
        with st.container(key="dashboard-panel-jury", border=True):
            jury_view()
        return
    st.title("Recommendation monitor")
    end = clock_slot()
    with st.container(key="dashboard-panel-health", border=True):
        serving_health(end)
    periods = fetch_latest("split_history", lambda: split_history(end)) or []
    with st.container(key="dashboard-panel-splits", border=True):
        split_reliability(periods, end)
    with st.container(key="dashboard-panel-performance", border=True):
        expected_performance(periods)
    with st.container(key="dashboard-panel-cold", border=True):
        shopper_groups(end)
    with st.container(key="dashboard-panel-trends", border=True):
        store_trends(end)


show_view()

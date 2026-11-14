"""Private Streamlit dashboard for the RawTree team and jury demo."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
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
from dades_huzz.dashboard_team import read_cold_groups, read_health, read_trends
from dades_huzz.data import RawTree

BARCELONA = ZoneInfo("Europe/Madrid")
PRACTICE_START = datetime.fromtimestamp(PRACTICE_START_MS / 1000, UTC)
PRACTICE_END = datetime.fromtimestamp(FINAL_START_MS / 1000, UTC)

st.set_page_config(page_title="Tati · Recommendation dashboard", layout="wide")


def local_time(epoch_seconds: float) -> str:
    return datetime.fromtimestamp(epoch_seconds, BARCELONA).strftime("%d %b %H:%M %Z")


def rate(count: int, total: int) -> str:
    return f"{100 * count / total:.2f}%" if total else "—"


def chart_time(value: datetime) -> str:
    return value.astimezone(BARCELONA).strftime("%d %b %H:%M")


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
    columns[0].metric("Valid and on time", rate(health["on_time"], health["completed"]))
    columns[1].metric("Requests with feedback", f"{health['completed']:,}")
    columns[2].metric("Awaiting feedback", f"{health['pending']:,}")
    slow = health["p95_ms"]
    columns[3].metric(
        "95% of valid answers within",
        f"{slow / 1000:.2f} s" if slow is not None else "—",
    )
    median = health["p50_ms"]
    outcomes = " · ".join(
        f"{name.title()}: {health[name]:,}" for name in ("missing", "late", "invalid")
    )
    if median is not None:
        outcomes += f" · Typical on-time answer: {median / 1000:.2f} s"
    st.caption(outcomes)


def expected_performance() -> None:
    st.subheader("Which versions sold more in practice?")
    st.info(
        "Exact split changes and outcomes by assigned version are awaiting serving split records."
    )
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
    frame["Time (Barcelona)"] = frame["bucket_start"].map(chart_time)
    frame["Window end (Barcelona)"] = frame["bucket_end"].map(chart_time)
    order = (
        frame.sort_values("bucket_start")["Time (Barcelona)"].drop_duplicates().tolist()
    )
    shading = (
        alt.Chart(frame[frame["overlap"]].drop_duplicates("bucket_start"))
        .mark_rect(color="#95b8da", opacity=0.24)
        .encode(
            x=alt.X(
                "Time (Barcelona):O",
                sort=order,
                title=None,
                axis=alt.Axis(labelAngle=-35),
            )
        )
    )
    line = (
        alt.Chart(frame)
        .mark_line(point=True, invalid="break-paths-filter-domains")
        .encode(
            x=alt.X(
                "Time (Barcelona):O",
                sort=order,
                title=None,
                axis=alt.Axis(labelAngle=-35),
            ),
            y=alt.Y(
                "expected_purchases_per_100:Q",
                title="Expected purchases per 100 requests",
            ),
            color=alt.Color("model_version:N", title="Model version"),
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
    st.altair_chart((shading + line).properties(height=330), width="stretch")
    st.caption("Shaded windows show overlapping traffic reported by the leaderboard.")


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
                "Purchases per 100 requests": rate(row["purchases"], row["completed"]),
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
                "Window:N", scale=alt.Scale(range=["#117d72", "#92a8bf"]), title=None
            ),
            tooltip=["Category:N", "Window:N", "Events:Q"],
        )
    )
    st.altair_chart(comparison, width="stretch")


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
        st.metric("Official team score", f"{score:.2f} / 100")


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
    chosen_period = st.selectbox("Round", ["Show latest round", *available])
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
    version = st.selectbox(
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
        columns[0].metric("Purchases", f"{purchases:,}")
        columns[1].metric("Sales", f"€{revenue:,.2f}")
        columns[2].metric(
            "Purchases per 100 times shown",
            f"{100 * purchases / displays:.2f}" if displays else "—",
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
            .mark_bar(color="#117d72")
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
        st.altair_chart(chart.properties(height=285), width="stretch")
        st.caption(
            "Shows when shoppers bought after seeing this version’s recommendations."
        )
    jury_score()


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
        jury_view()
        return
    st.title("Recommendation monitor")
    end = clock_slot()
    serving_health(end)
    st.divider()
    expected_performance()
    st.divider()
    shopper_groups(end)
    store_trends(end)


show_view()

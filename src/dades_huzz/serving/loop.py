"""The live loop: read new requests, answer each within 3 seconds, log what was sent.

Nothing here may stop the loop: shoppers keep arriving while we sleep, and a request we do not answer gets
the fallback. Every failure is logged and the loop carries on.
"""

import json
import threading
import time
import traceback
from collections.abc import Callable, Iterable
from collections.abc import Set as AbstractSet
from pathlib import Path
from typing import TYPE_CHECKING

from dades_huzz.data import (
    STOCK_CHANGES,
    RawTree,
    Record,
    RequestCursor,
    State,
    UpdateLog,
    current_state,
    recently_changed,
)
from dades_huzz.serving.handover import Handover, now_ms
from dades_huzz.serving.watchdog import mark_alive

if TYPE_CHECKING:  # versions.py imports the models, which import this module
    from dades_huzz.serving.versions import Split

Recommend = Callable[[Record, State], list[str]]
"""`recommend(request, state) -> list[str]`, the shared signature in docs/contracts.md."""

POLL_S = 0.3
MAX_AGE_MS = 2400
"""Requests older than this are skipped: our answer would reach RawTree after the 3 s deadline."""
STATE_REFRESH_S = 0.25
"""Stock can change at any moment: start a read of new catalogue updates this often (each read is small,
about 0.2 s), so a change reaches the loop well under a second after it lands in RawTree."""
LATE_UPDATE_MS = 120_000
"""Each read of catalogue updates goes back this far, so an update that lands in RawTree up to 2 minutes
after a newer one is still read (about 30 rows per read)."""
RELOAD_S = 60.0
"""The whole catalogue, every catalogue update and the best sellers are read again this often, in their own
thread: the final round switches to new data, which may replace the catalogue rather than update it."""
RELOAD_MARGIN_MS = 5_000
"""Updates the loop read up to this long before a reload started are kept through it, in case the reload
missed them (RawTree shows an update up to about 2 s after its time)."""
RECENT_CHANGE_MS = 10_000
"""Products whose stock changed this recently are never recommended (see `recently_changed`, issue #14)."""

ANSWER_SIZE = 10


def validate(items: list[str], available: AbstractSet[str]) -> list[str]:
    """Why an answer would be rejected: 'duplicate', 'unavailable', 'wrong_size'. Empty means valid."""
    reasons = []
    if len(set(items)) != len(items):
        reasons.append("duplicate")
    if any(item not in available for item in items):
        reasons.append("unavailable")
    if len(items) != ANSWER_SIZE:
        reasons.append("wrong_size")
    return reasons


def repair(
    items: Iterable[str], available: AbstractSet[str], fallback: Iterable[str]
) -> list[str]:
    """Drop duplicates and unavailable products, keep the order, pad from `fallback` up to ten."""
    answer: list[str] = []
    for item in [*items, *fallback]:
        if len(answer) == ANSWER_SIZE:
            break
        if item in available and item not in answer:
            answer.append(item)
    return answer


def until_ok[T](
    load: Callable[[], T], what: str, on_retry: Callable[[], None] = lambda: None
) -> T:
    """Retry a start-up load until it works: a network blip at start must not stop the loop for good.
    `on_retry` runs on every retry (the loop marks itself alive, so the watchdog knows it is only waiting)."""
    while True:
        try:
            return load()
        except Exception as e:  # noqa: BLE001  retried, never fatal
            print(f"loading {what} failed, retrying in 2 s: {e}", flush=True)
            on_retry()
            time.sleep(2)


class LiveState:
    """Keeps the state fresh in a background thread, so answering never waits for it.

    `allowed` is what an answer may contain right now: `state.available` minus the products whose stock
    changed in the last RECENT_CHANGE_MS.
    """

    def __init__(
        self,
        rawtree: RawTree,
        on_retry: Callable[[], None] = lambda: None,
        reload_s: float = RELOAD_S,
    ) -> None:
        self.rawtree = rawtree
        self.catalog = until_ok(rawtree.catalog, "catalogue", on_retry)
        self.best_sellers = until_ok(rawtree.best_sellers, "best sellers", on_retry)
        self.updates = UpdateLog(overlap_ms=LATE_UPDATE_MS)
        self.updates.add(
            until_ok(
                lambda: rawtree.catalog_updates_since(0), "catalogue updates", on_retry
            )
        )
        self._reloaded: tuple[int, list[Record], list[str], list[Record]] | None = None
        self._rebuild()
        threading.Thread(target=self._refresh_forever, daemon=True).start()
        threading.Thread(
            target=self._reload_forever, args=(reload_s,), daemon=True
        ).start()

    def _reload_forever(self, every_s: float) -> None:
        """Read everything again; the refresh thread swaps it in, so only that thread changes the state."""
        while True:
            time.sleep(every_s)
            try:
                self._reloaded = (
                    now_ms(),
                    self.rawtree.catalog(),
                    self.rawtree.best_sellers(),
                    self.rawtree.catalog_updates_since(0),
                )
            except Exception as e:  # noqa: BLE001  keep the last full read; try again next time
                print(f"catalogue reload failed: {e}", flush=True)

    def _swap_in_reload(self) -> None:
        started_ms, catalog, best_sellers, all_updates = self._reloaded  # type: ignore[misc]
        self._reloaded = None
        before = {row["product_id"] for row in self.catalog}
        after = {row["product_id"] for row in catalog}
        if before != after:
            print(
                f"catalogue changed: {len(after)} products"
                f" ({len(after - before)} added, {len(before - after)} gone)",
                flush=True,
            )
        updates = UpdateLog(overlap_ms=LATE_UPDATE_MS)
        updates.add(all_updates)
        # Only the rows read around and after the reload: anything older that RawTree no longer has is dropped.
        updates.add(
            row
            for row in self.updates.rows
            if row["ts_ms"] >= started_ms - RELOAD_MARGIN_MS
        )
        self.catalog, self.best_sellers, self.updates = catalog, best_sellers, updates

    def _rebuild(self) -> None:
        state = current_state(self.catalog, self.updates.rows, self.best_sellers)
        self.allowed = state.available - recently_changed(
            self.updates.rows, now_ms(), RECENT_CHANGE_MS
        )
        self.state = state
        self.refreshed_ms = now_ms()

    def _refresh_forever(self) -> None:
        while True:
            time.sleep(
                max(0.0, STATE_REFRESH_S - (now_ms() - self.refreshed_ms) / 1000)
            )
            if self._reloaded is not None:
                self._swap_in_reload()
            try:
                rows = self.rawtree.catalog_updates_since(
                    self.updates.since_ms(now_ms())
                )
            except Exception as e:  # noqa: BLE001  keep answering with the last known state
                print(f"catalogue update read failed: {e}", flush=True)
                # refreshed_ms did not move: pause briefly so a failing read is not retried in a tight loop
                time.sleep(STATE_REFRESH_S)
                continue
            new = self.updates.add(rows)
            seen_ms = now_ms()
            for row in (
                new
            ):  # logged before the rebuild, so a rebuild failure cannot hide them
                if row["change"] in STOCK_CHANGES:
                    print(
                        f"stock {row['change']} {row['product_id']} at {row['ts']}"
                        f" seen after {(seen_ms - row['ts_ms']) / 1000:.1f} s",
                        flush=True,
                    )
            try:
                self._rebuild()
            except Exception as e:  # noqa: BLE001  keep answering with the last known state
                print(f"state rebuild failed: {e}", flush=True)
                time.sleep(STATE_REFRESH_S)


def answer(
    requests: list[Record], split: "Split", state: State, allowed: AbstractSet[str]
) -> list[Record]:
    """One valid answer per request from the version the split gives it, plus the problems found. The model
    may fail or be slow; the answer may not. `allowed` is stricter than `state.available` (see LiveState)."""
    answers = []
    for request in requests:
        try:
            version, items, problem = split.recommend(request, state)
            problems = ([problem] if problem else []) + validate(items, allowed)
        except Exception:  # noqa: BLE001  a champion bug must not cost the answer
            traceback.print_exc()
            version, items, problems = split.champion, [], ["model_error"]
        if problems:
            items = repair(items, allowed, state.fallback)
        answers.append(
            {
                "request_id": request["request_id"],
                "items": items,
                "model_version": version,
                "problems": problems,
            }
        )
    return answers


class Waiting(Exception):
    """This loop is on standby: skip answering this round."""


def serve(
    rawtree: RawTree,
    load_versions: Callable[[Callable], "Split"],
    log_path: Path,
    handover: bool = True,
    alive_path: Path | None = None,
) -> None:
    """Answer requests forever, each with the version the split gives it (`model_version` in the answer).

    `load_versions(load)` loads the split, with `load(fn, what)` retrying each load the way start-up loads
    are retried. With `handover`, the loop answers only while it is the team's active loop (see handover.py).
    With `alive_path`, every round touches that file so the watchdog can tell the loop is not hung.
    """

    def alive(phase: str = "running") -> None:
        if alive_path:
            mark_alive(alive_path, phase)

    def starting() -> None:
        alive("starting")

    starting()
    live = LiveState(rawtree, on_retry=starting)
    split = load_versions(lambda load, what: until_ok(load, what, starting))
    print(f"versions: {split.shares} (champion: {split.champion})", flush=True)
    cursor = RequestCursor(MAX_AGE_MS)
    turn = Handover(
        rawtree,
        enabled=handover,
        details=lambda: {
            "versions": split.describe(),
            "out": ",".join(sorted(split.taken_out())),
        },
    )
    was_active = not handover
    log_path.parent.mkdir(parents=True, exist_ok=True)
    answered = errors = 0
    status_at = time.time()
    with log_path.open("a") as log:
        while True:
            started = time.time()
            alive()
            try:
                if not turn.active:
                    was_active = False
                    raise Waiting
                if not was_active:
                    # Taking over: skip what the previous loop already answered. Set first, so a failed
                    # check is not retried forever: a few double answers beat no answers.
                    was_active = True
                    cursor.mark_answered(
                        rawtree.answered_since(cursor.since_ms(now_ms())), now_ms()
                    )
                fresh = cursor.accept(
                    rawtree.requests_since(cursor.since_ms(now_ms())), now_ms()
                )
                if fresh:
                    answers = answer(fresh, split, live.state, live.allowed)
                    rawtree.insert(
                        "submissions",
                        [
                            {k: a[k] for k in ("request_id", "items", "model_version")}
                            for a in answers
                        ],
                    )
                    sent_ms = now_ms()
                    for request, a in zip(fresh, answers):
                        log.write(
                            json.dumps(
                                {
                                    **a,
                                    "ts_ms": request["ts_ms"],
                                    "sent_ms": sent_ms,
                                    "latency_ms": sent_ms - request["ts_ms"],
                                }
                            )
                            + "\n"
                        )
                    log.flush()
                    answered += len(answers)
            except Waiting:
                pass
            except Exception as e:  # noqa: BLE001  the loop never stops
                errors += 1
                print(f"error: {e}", flush=True)
            if time.time() - status_at >= 10:
                print(
                    f"{turn.role}: answered {answered}, skipped {cursor.skipped}, errors {errors}, "
                    f"state {(now_ms() - live.refreshed_ms) / 1000:.0f}s old",
                    flush=True,
                )
                status_at = time.time()
            time.sleep(max(0.0, POLL_S - (time.time() - started)))

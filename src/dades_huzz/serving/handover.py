"""Handover: at most one serving loop answers for the team, and a waiting loop takes over when it stops.

Every loop writes a heartbeat to `team_02.scratch` (`kind = "heartbeat"`) every couple of seconds, from a
background thread: answering never waits for it. A loop is `active` (answers) or `standby` (only watches).
Switch it off with `run_recommender.py --no-handover`: the loop is then always active and writes nothing.
"""

import socket
import threading
import time
import uuid
from collections.abc import Iterable

from dades_huzz.data import RawTree, Record

HEARTBEAT_S = 2.0
SILENT_MS = 6000
"""A loop whose latest heartbeat is older than this is considered stopped."""


def decide_role(
    me: str,
    role: str,
    started_ms: int,
    last_write_ms: int,
    heartbeats: Iterable[Record] | None,
    now_ms: int,
) -> str:
    """'active' or 'standby' for loop `me`, from the latest heartbeat of every loop.

    A loop that could not write its own heartbeat lately steps down: the others cannot see it is alive.
    One that could not read the heartbeats (`None`) keeps its role: it cannot know whether another is active.
    Nobody else active and alive: become active. Several active: only the one that started first stays.
    """
    if now_ms - last_write_ms > SILENT_MS:
        return "standby"
    if heartbeats is None:
        return role
    latest: dict[str, Record] = {}
    for beat in heartbeats:
        if (
            beat["loop_id"] not in latest
            or beat["ts_ms"] > latest[beat["loop_id"]]["ts_ms"]
        ):
            latest[beat["loop_id"]] = beat
    others = [
        beat
        for loop_id, beat in latest.items()
        if loop_id != me
        and beat["role"] == "active"
        and now_ms - beat["ts_ms"] <= SILENT_MS
    ]
    if not others:
        return "active"
    if role == "standby":
        return "standby"
    oldest = min((beat["started_ms"], beat["loop_id"]) for beat in others)
    return "active" if (started_ms, me) < oldest else "standby"


def now_ms() -> int:
    return int(time.time() * 1000)


class Handover:
    """Writes this loop's heartbeat and decides its role in a background thread; `active` is all the answering
    loop reads. With `enabled=False` the loop is always active and nothing is written."""

    def __init__(self, rawtree: RawTree, enabled: bool = True) -> None:
        self.rawtree = rawtree
        self.loop_id = uuid.uuid4().hex[:8]
        self.host = socket.gethostname()
        self.started_ms = now_ms()
        self.role = "active" if not enabled else "standby"
        self.last_write_ms = 0
        if enabled:
            self._check_clock()
            self._tick()
            threading.Thread(target=self._beat_forever, daemon=True).start()

    @property
    def active(self) -> bool:
        return self.role == "active"

    def _check_clock(self) -> None:
        try:
            skew = now_ms() - self.rawtree.server_now_ms()
        except Exception as e:  # noqa: BLE001  the check is advice, never fatal
            print(f"clock check failed: {e}", flush=True)
            return
        if abs(skew) > 1000:
            print(
                f"WARNING: this clock is {skew / 1000:+.1f} s off RawTree; handover timing will be wrong",
                flush=True,
            )

    def _tick(self) -> None:
        beat = {
            "kind": "heartbeat",
            "loop_id": self.loop_id,
            "host": self.host,
            "role": self.role,
            "started_ms": self.started_ms,
            "ts_ms": now_ms(),
        }
        heartbeats = None
        try:
            self.rawtree.insert("scratch", [beat])
            self.last_write_ms = beat["ts_ms"]
            heartbeats = self.rawtree.heartbeats_since(now_ms() - 2 * SILENT_MS)
        except Exception as e:  # noqa: BLE001  a missed beat only matters if it lasts; decide_role handles that
            print(f"heartbeat failed: {e}", flush=True)
        role = decide_role(
            self.loop_id,
            self.role,
            self.started_ms,
            self.last_write_ms,
            heartbeats,
            now_ms(),
        )
        if role != self.role:
            print(
                f"loop {self.loop_id} on {self.host}: {self.role} -> {role}", flush=True
            )
            self.role = role

    def _beat_forever(self) -> None:
        while True:
            time.sleep(HEARTBEAT_S)
            self._tick()

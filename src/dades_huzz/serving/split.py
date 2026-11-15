"""The version split: which version answers each request, under what time limit.

Every request goes to one version, chosen from a fingerprint of its `request_id`, so the same request gets
the same version on any laptop and after any restart. The answer carries the version that produced it as
`model_version`, so the serving report compares versions on the same stream, side by side.

The first version listed is the champion (GLOSSARY.md): it answers in the loop itself. Every other version is
a challenger, with a time limit per request. A challenger that misses it or raises gives way to the champion
for that shopper. A challenger slow on average is taken out for OUT_FOR_MS, also across restarts and
laptops (`versions.load_split` records it). One that cannot load is left out, and the champion answers its
share. The versions themselves are listed in `versions.py`; two of them can serve as one pair,
`pair:<cold>+<warm>`.
"""

import gc
import hashlib
import threading
import time
import tracemalloc
from collections import deque
from collections.abc import Callable

from dades_huzz.data import Record, State
from dades_huzz.serving.handover import (
    now_ms as wall_ms,
)  # `now_ms` is a parameter name here
from dades_huzz.serving.loop import Recommend

BUDGET_MS = 200.0
"""docs/contracts.md: about 200 ms per request. A challenger gets this long per request."""
WINDOW = 20
"""A challenger whose last WINDOW requests average over budget is taken out."""
OUT_FOR_MS = 30 * 60_000
"""How long a take-out lasts; then the version gets another chance (the time limit caps what it costs)."""
MAX_PENDING = 20
"""A challenger with this many calls still running (hung) is not called again: it times out at once."""


def parse_split(text: str) -> dict[str, int]:
    """'a=50,b=50' -> {'a': 50, 'b': 50}. Shares are positive whole numbers; their total need not be 100."""
    shares: dict[str, int] = {}
    for part in text.split(","):
        name, sep, share = part.partition("=")
        name = name.strip()
        if not sep or not name or not share.strip().isdigit() or int(share) <= 0:
            raise ValueError(f"expected name=positive_share, got {part!r} in {text!r}")
        if name in shares:
            raise ValueError(f"{name!r} appears twice in {text!r}")
        shares[name] = int(share)
    return shares


PAIR = "pair:"
"""`pair:<cold>+<warm>` names a pair (GLOSSARY.md): two versions serving as one, the first answering
cold requests and the second the rest (docs/experiments.md row 61's 07:00 choice)."""


def pair_name(cold: str, warm: str) -> str:
    """The name under which `cold` (for cold requests) and `warm` (for the rest) serve as one version."""
    return f"{PAIR}{cold}+{warm}"


def pair_arms(name: str) -> tuple[str, str] | None:
    """(cold version, warm version) if `name` is written as a pair, else None."""
    if not name.startswith(PAIR):
        return None
    cold, _, warm = name[len(PAIR) :].partition("+")
    return cold, warm


class Split:
    """Assigns requests to versions by share, runs challengers under a time limit, and takes out a slow one."""

    def __init__(
        self,
        recommenders: dict[str, Recommend],
        shares: dict[str, int],
        budget_ms: float = BUDGET_MS,
        out_until_ms: dict[str, float] | None = None,
        on_take_out: Callable[[str, int], None] = lambda name, until_ms: None,
    ) -> None:
        self.recommenders = recommenders
        self.shares = shares
        self.champion = next(iter(shares))
        self.budget_ms = budget_ms
        self.out_until_ms: dict[str, float] = dict(out_until_ms or {})
        self.on_take_out = on_take_out
        self._times: dict[str, deque[float]] = {
            name: deque(maxlen=WINDOW) for name in shares
        }
        self._pending: dict[str, list[threading.Thread]] = {name: [] for name in shares}

    def taken_out(self, now_ms: int | None = None) -> set[str]:
        now = now_ms if now_ms is not None else wall_ms()
        return {name for name, until in self.out_until_ms.items() if until > now}

    def describe(self) -> str:
        """The split as `--versions` takes it, champion first: 'a=50,b=50'."""
        return ",".join(f"{name}={share}" for name, share in self.shares.items())

    def version_for(self, request_id: str, now_ms: int | None = None) -> str:
        """Deterministic: a sha256 fingerprint of the id, not Python's hash(), which changes per process."""
        point = int.from_bytes(
            hashlib.sha256(request_id.encode()).digest()[:8], "big"
        ) % sum(self.shares.values())
        for name, share in self.shares.items():
            if point < share:
                return self.champion if name in self.taken_out(now_ms) else name
            point -= share
        raise AssertionError("unreachable: point < total share")

    def recommend(
        self, request: Record, state: State
    ) -> tuple[str, list[str], str | None]:
        """(version that answered, its items, problem). A challenger that times out or raises gives way to the
        champion, and the problem says so ('timeout:name', 'model_error:name')."""
        version = self.version_for(request["request_id"])
        if version == self.champion:
            started = time.perf_counter()
            items = self.recommenders[version](request, state)
            self.record(version, (time.perf_counter() - started) * 1000)
            return version, items, None
        items, problem = self._call_with_limit(version, request, state)
        if problem:
            return (
                self.champion,
                self.recommenders[self.champion](request, state),
                f"{problem}:{version}",
            )
        return version, items, None

    def _call_with_limit(
        self, version: str, request: Record, state: State
    ) -> tuple[list[str], str | None]:
        pending = self._pending[version] = [
            t for t in self._pending[version] if t.is_alive()
        ]
        if len(pending) >= MAX_PENDING:
            self.record(version, self.budget_ms * 2)
            return [], "timeout"
        box: dict[str, object] = {}

        def run() -> None:
            try:
                box["items"] = self.recommenders[version](request, state)
            except Exception as e:  # noqa: BLE001  reported to the caller as model_error
                box["error"] = e

        started = time.perf_counter()
        thread = threading.Thread(
            target=run, daemon=True
        )  # daemon: a hung model never blocks exit
        thread.start()
        thread.join(self.budget_ms / 1000)
        self.record(version, (time.perf_counter() - started) * 1000)
        if thread.is_alive():
            pending.append(thread)
            return [], "timeout"
        if "error" in box:
            print(f"version {version} raised: {box['error']!r}", flush=True)
            return [], "model_error"
        return box["items"], None  # type: ignore[return-value]

    def record(self, name: str, elapsed_ms: float, now_ms: int | None = None) -> None:
        """Note how long `name` took for one request; take it out if its recent average is over budget."""
        now = now_ms if now_ms is not None else wall_ms()
        times = self._times[name]
        times.append(elapsed_ms)
        average = sum(times) / len(times)
        if name == self.champion or len(times) < WINDOW or average <= self.budget_ms:
            return
        if name not in self.taken_out(now):
            until = now + OUT_FOR_MS
            self.out_until_ms[name] = until
            times.clear()
            print(
                f"version {name} taken out for {OUT_FOR_MS // 60_000} min: {average:.0f} ms per request on average"
                f" (budget {self.budget_ms:.0f}); the champion {self.champion} answers its share",
                flush=True,
            )
            self.on_take_out(name, until)


def measure_version(
    load: Callable[[], Recommend],
    requests: list[Record],
    state: State,
    reference: Recommend,
) -> dict[str, float]:
    """What a version costs before it goes live: load time and memory, then on `requests` how many answers
    are invalid (not 10 distinct available products), how many differ from `reference`, and time per call.

    Memory is what Python allocates while loading (tracemalloc), so it reads the same on every system."""
    tracemalloc.start()
    started = time.perf_counter()
    recommend = load()
    load_s = time.perf_counter() - started
    load_mb = tracemalloc.get_traced_memory()[0] / 2**20
    tracemalloc.stop()
    gc.freeze()  # as serve() does once the versions are loaded (#59)
    if requests:  # untimed: the first call after tracemalloc costs ~190 ms that a serving loop never sees (#59)
        recommend(requests[0], state)
    times, invalid, differs = [], 0, 0
    for request in requests:
        started = time.perf_counter()
        items = recommend(request, state)
        times.append((time.perf_counter() - started) * 1000)
        invalid += not (
            len(items) == 10 == len(set(items)) and set(items) <= state.available
        )
        differs += items != reference(request, state)
    times.sort()
    n = max(len(times), 1)
    return {
        "load_s": load_s,
        "load_mb": load_mb,
        "requests": len(requests),
        "invalid": invalid,
        "differs_pct": 100 * differs / n,
        "p50_ms": times[len(times) // 2] if times else 0.0,
        "p99_ms": times[int(len(times) * 0.99)] if times else 0.0,
        "max_ms": times[-1] if times else 0.0,
    }


def main_thread_wait_ms(
    seconds: float, step_s: float = 0.05, until: threading.Event | None = None
) -> float:
    """The longest extra wait of a 50 ms sleep in this thread over `seconds` (or until `until` is set): what
    background work started by the loop or the loaded versions would add to the answering loop."""
    worst, end = 0.0, time.monotonic() + seconds
    while time.monotonic() < end and not (until and until.is_set()):
        started = time.perf_counter()
        time.sleep(step_s)
        worst = max(worst, (time.perf_counter() - started - step_s) * 1000)
    return worst

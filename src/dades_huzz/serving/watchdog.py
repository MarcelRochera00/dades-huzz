"""Unattended running: keep the laptop awake, and restart the serving loop when it exits or hangs.

The watchdog is a separate process that starts the loop as a child and checks on it once a second. The loop
touches an "alive" file on every round; a loop that exited, or whose alive file has not changed for
`HANG_AFTER_S`, is stopped and started again. Nothing here runs inside the answering loop except that touch.
If the watchdog itself dies, its loop stops too, and so does the keep-awake. Switch it all off with
`run_recommender.py --no-watchdog`.
"""

import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

HANG_AFTER_S = 15.0
"""A loop whose alive file has not changed for this long is hung. Its slowest step (a RawTree read) gives up
after 1 s, so a healthy loop marks itself several times a second."""
STARTUP_GRACE_S = 120.0
"""Before its first mark the loop is starting up; while RawTree is down it marks itself on every retry."""
STABLE_AFTER_S = 300.0
"""A loop that ran this long before failing is not failing quickly: the next restart waits the minimum."""


def restart_reason(
    exited: bool, seconds_since_alive: float, limit_s: float
) -> str | None:
    """Why the loop must be restarted ('exited' or 'hung'), or None while it is healthy."""
    if exited:
        return "exited"
    if seconds_since_alive > limit_s:
        return "hung"
    return None


def restart_delay_s(quick_failures_before: int) -> float:
    """Seconds to wait before a restart: 5 s, doubling while the loop keeps failing quickly, at most a minute,
    so a loop that crashes at start (a broken model, say) does not hammer RawTree."""
    return min(5 * 2**quick_failures_before, 60)


def quick_failures_after(previous: int, ran_s: float) -> int:
    """How many quick failures in a row, counting the one that just happened; a long healthy run resets it."""
    return 0 if ran_s >= STABLE_AFTER_S else previous + 1


class AliveClock:
    """How long since the loop last marked itself alive, measured with the watchdog's own monotonic clock.

    The watchdog only compares the alive file's mark with the previous one it saw, never with the wall clock,
    so a clock adjustment cannot make a healthy loop look hung or hide a real hang.
    """

    def __init__(self, start: float) -> None:
        self._mark: object = None
        self._changed_at = start
        self.marked = False

    def observe(self, mark: object, now: float) -> None:
        if mark is not None and mark != self._mark:
            self.marked = True
            self._mark = mark
            self._changed_at = now

    def seconds_since_alive(self, now: float) -> float:
        return now - self._changed_at


def mark_alive(path: Path) -> None:
    """Touch the alive file. Never raises: a missing folder is recreated, and any other error is ignored,
    because a failed mark must not take the answering loop down (at worst the watchdog restarts it)."""
    try:
        path.touch()
    except OSError:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        except OSError:
            pass


def exit_when_watchdog_dies() -> None:
    """In the loop started by the watchdog: stop when the watchdog stops, however it stopped.

    The watchdog holds the loop's stdin open; when the watchdog process ends, the operating system closes it
    and the read below returns. Works the same on Linux, Windows and macOS.
    """

    def watch() -> None:
        sys.stdin.read()
        print("watchdog gone: stopping the loop", flush=True)
        os._exit(0)

    threading.Thread(target=watch, daemon=True).start()


class KeepAwake:
    """Asks the operating system not to sleep while this process runs (Linux, Windows, macOS).

    On Linux it also asks that closing the lid does not suspend, when the system allows it. Elsewhere a closed
    lid may still suspend: keep the lid open, the laptop plugged in, and sleep set to "never".
    """

    def __init__(self, why: str) -> None:
        self.why = why
        self.how = "not available on this system"
        self._child: subprocess.Popen | None = None

    def __enter__(self) -> Self:
        system = platform.system()
        if system == "Windows":
            import ctypes

            # ES_CONTINUOUS | ES_SYSTEM_REQUIRED: no sleep while this thread lives, until reset in __exit__
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # type: ignore[attr-defined]
            self.how = "Windows SetThreadExecutionState (system required)"
        elif system == "Darwin" and shutil.which("caffeinate"):
            # -w: caffeinate ends by itself when this process ends, however it ends
            self._child = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])
            time.sleep(0.5)
            self.how = "macOS caffeinate -i"
        elif system == "Linux" and shutil.which("systemd-inhibit"):
            self._child = self._inhibit(
                "sleep:idle:handle-lid-switch"
            ) or self._inhibit("sleep:idle")
            if self._child:
                self.how = f"systemd-inhibit {self._child.args[1]}"
                if not self.active():
                    self.how += (
                        " (started, but not listed by systemd: probably not in effect)"
                    )
        return self

    def _inhibit(self, what: str) -> subprocess.Popen | None:
        # The held command ends when this process ends, so the block never outlives the watchdog.
        hold = f"while kill -0 {os.getpid()} 2>/dev/null; do sleep 5; done"
        child = subprocess.Popen(
            [
                "systemd-inhibit",
                f"--what={what}",
                "--who=dades-huzz",
                f"--why={self.why}",
                "--mode=block",
                "sh",
                "-c",
                hold,
            ],
            stderr=subprocess.DEVNULL,
        )
        time.sleep(0.5)
        if child.poll() is None:
            return child
        return None  # not allowed (e.g. the lid switch needs more rights): let the caller try less

    def active(self) -> bool | None:
        """Whether the system confirms the request; None when it cannot be asked (Windows needs an
        administrator for `powercfg /requests`)."""
        system = platform.system()
        if system == "Linux" and self._child:
            listing = subprocess.run(
                ["systemd-inhibit", "--list"],
                check=False,
                capture_output=True,
                text=True,
            ).stdout
            return "dades-huzz" in listing
        if system == "Darwin" and self._child:
            listing = subprocess.run(
                ["pmset", "-g", "assertions"],
                check=False,
                capture_output=True,
                text=True,
            ).stdout
            return "caffeinate" in listing
        return None

    def __exit__(self, *exc: object) -> None:
        if self._child:
            self._child.terminate()
            self._child.wait()
        if platform.system() == "Windows":
            import ctypes

            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)  # type: ignore[attr-defined]


def _stop(child: subprocess.Popen, hung: bool = False) -> None:
    """Ask the loop to stop, then force it after 5 s. A hung loop is forced at once: it would not answer."""
    if child.poll() is None and hung:
        child.kill()
        child.wait()
    elif child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def _alive_mark(path: Path) -> float | None:
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return None


def supervise(
    command: list[str],
    alive_path: Path,
    log_path: Path,
    hang_after_s: float = HANG_AFTER_S,
    startup_grace_s: float = STARTUP_GRACE_S,
    check_s: float = 1.0,
    max_restarts: int | None = None,
) -> int:
    """Run `command` forever, restarting it when it exits or hangs. Every start and restart goes to `log_path`.
    Returns the number of restarts once `max_restarts` is reached (used by the self-check); otherwise never.
    The child's stdin stays open for its whole life: see `exit_when_watchdog_dies`."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    restarts = quick_failures = 0
    with log_path.open("a") as log:

        def note(message: str) -> None:
            line = f"{datetime.now(UTC):%Y-%m-%d %H:%M:%S} UTC watchdog: {message}"
            print(line, flush=True)
            log.write(line + "\n")
            log.flush()

        while True:
            alive_path.unlink(missing_ok=True)
            started = time.monotonic()
            clock = AliveClock(start=started)
            child = subprocess.Popen(command, stdin=subprocess.PIPE)
            note(f"started the loop (pid {child.pid})")
            try:
                while True:
                    time.sleep(check_s)
                    now = time.monotonic()
                    clock.observe(_alive_mark(alive_path), now)
                    limit = hang_after_s if clock.marked else startup_grace_s
                    reason = restart_reason(
                        child.poll() is not None, clock.seconds_since_alive(now), limit
                    )
                    if reason:
                        break
            except BaseException:
                _stop(child)
                note("stopped")
                raise
            _stop(child, hung=reason == "hung")
            ran_s = time.monotonic() - started
            restarts += 1
            quick_failures = quick_failures_after(quick_failures, ran_s)
            wait_s = restart_delay_s(max(quick_failures - 1, 0))
            note(
                f"the loop {reason} after {ran_s:.0f} s (exit code {child.returncode});"
                f" restart #{restarts} in {wait_s:.0f} s"
            )
            if max_restarts is not None and restarts >= max_restarts:
                return restarts
            time.sleep(wait_s)


def self_check() -> bool:
    """Check, on this laptop and without touching RawTree, that the watchdog can keep it awake and restart a
    loop that exits or hangs. Prints one line per check; True when every check passed."""
    import tempfile

    results = []
    with KeepAwake("dades-huzz self-check") as awake:
        confirmed = awake.active()
        ok = awake.how != "not available on this system" and confirmed is not False
        detail = {
            True: "confirmed by the system",
            False: "NOT confirmed by the system",
        }.get(
            confirmed, "applied; this system cannot confirm it without an administrator"
        )
        results.append(ok)
        print(
            f"{'PASS' if ok else 'FAIL'}  keep-awake: {awake.how} ({detail})",
            flush=True,
        )
    with tempfile.TemporaryDirectory() as folder:
        for then, expected in (("exit", "exited"), ("hang", "hung")):
            alive, log = Path(folder) / f"alive_{then}", Path(folder) / f"log_{then}"
            action = "sys.exit(3)" if then == "exit" else "time.sleep(60)"
            fake = [
                sys.executable,
                "-c",
                f"import pathlib, sys, time; pathlib.Path({str(alive)!r}).touch(); {action}",
            ]
            started = time.monotonic()
            supervise(fake, alive, log, hang_after_s=2, check_s=0.2, max_restarts=1)
            ok = f"the loop {expected}" in log.read_text()
            results.append(ok)
            print(
                f"{'PASS' if ok else 'FAIL'}  a loop that {'exits' if then == 'exit' else 'hangs'} is restarted"
                f" ({time.monotonic() - started:.1f} s)",
                flush=True,
            )
    return all(results)

import os
import sys
import time

from dades_huzz.serving.watchdog import (
    AliveClock,
    mark_alive,
    quick_failures_after,
    remove_stale_alive_files,
    restart_delay_s,
    restart_reason,
    supervise,
)


def test_a_running_loop_that_marked_itself_alive_recently_is_left_alone():
    assert restart_reason(exited=False, seconds_since_alive=3.0, limit_s=15) is None


def test_a_loop_that_exited_is_restarted():
    assert restart_reason(exited=True, seconds_since_alive=1.0, limit_s=15) == "exited"


def test_a_loop_that_stopped_marking_itself_alive_is_restarted_as_hung():
    assert restart_reason(exited=False, seconds_since_alive=16.0, limit_s=15) == "hung"


def test_restarts_wait_longer_each_time_the_loop_fails_quickly_up_to_a_minute():
    assert [restart_delay_s(n) for n in range(6)] == [5, 10, 20, 40, 60, 60]


def fake_loop(alive, then):
    """A command that marks itself alive once, then either exits with code 3 or hangs."""
    action = "sys.exit(3)" if then == "exit" else "time.sleep(60)"
    return [
        sys.executable,
        "-c",
        f"import pathlib, sys, time; pathlib.Path({str(alive)!r}).touch(); {action}",
    ]


def test_the_watchdog_restarts_a_loop_that_exits(tmp_path):
    alive, log = tmp_path / "alive", tmp_path / "watchdog.log"
    assert (
        supervise(
            fake_loop(alive, "exit"),
            alive,
            log,
            hang_after_s=5,
            check_s=0.1,
            max_restarts=1,
        )
        == 1
    )
    assert "the loop exited" in log.read_text()
    assert "exit code 3" in log.read_text()


def test_the_watchdog_restarts_a_loop_that_hangs(tmp_path):
    alive, log = tmp_path / "alive", tmp_path / "watchdog.log"
    assert (
        supervise(
            fake_loop(alive, "hang"),
            alive,
            log,
            hang_after_s=1,
            check_s=0.1,
            max_restarts=1,
        )
        == 1
    )
    assert "the loop hung" in log.read_text()


def test_after_a_long_healthy_run_the_restart_waits_the_minimum():
    assert quick_failures_after(previous=3, ran_s=600) == 0
    assert restart_delay_s(0) == 5


def test_quick_failures_add_up():
    assert quick_failures_after(previous=0, ran_s=10) == 1
    assert quick_failures_after(previous=1, ran_s=10) == 2


def test_alive_age_is_measured_from_when_the_mark_last_changed_not_from_the_wall_clock():
    clock = AliveClock(start=100.0)
    clock.observe(mark="t1", now=101.0)
    assert clock.seconds_since_alive(now=110.0) == 9.0
    clock.observe(mark="t1", now=120.0)  # same mark: the loop did not move
    assert clock.seconds_since_alive(now=120.0) == 19.0
    clock.observe(mark="t2", now=121.0)
    assert clock.seconds_since_alive(now=122.0) == 1.0


def test_marking_alive_never_raises_even_if_the_folder_is_gone(tmp_path):
    mark_alive(tmp_path / "gone" / "alive")
    assert (tmp_path / "gone" / "alive").exists()


def test_a_loop_still_starting_up_gets_the_startup_grace_not_the_hang_limit(tmp_path):
    alive, log = tmp_path / "alive", tmp_path / "watchdog.log"
    starting = [
        sys.executable,
        "-c",
        f"import pathlib, time; pathlib.Path({str(alive)!r}).write_text('starting'); time.sleep(60)",
    ]
    started = time.monotonic()
    supervise(
        starting,
        alive,
        log,
        hang_after_s=0.3,
        startup_grace_s=2,
        check_s=0.1,
        max_restarts=1,
    )
    assert time.monotonic() - started > 1.8
    assert "the loop hung" in log.read_text()


def test_alive_files_left_by_killed_watchdogs_are_removed_after_an_hour(tmp_path):
    old, recent, other = (
        tmp_path / "loop_alive_1",
        tmp_path / "loop_alive_2",
        tmp_path / "serve_log.jsonl",
    )
    for path in (old, recent, other):
        path.write_text("running")
    two_hours_ago = time.time() - 7200
    os.utime(old, (two_hours_ago, two_hours_ago))
    os.utime(other, (two_hours_ago, two_hours_ago))
    assert remove_stale_alive_files(tmp_path) == [old]
    assert not old.exists() and recent.exists() and other.exists()

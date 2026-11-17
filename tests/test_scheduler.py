"""Tests for the built-in daily scheduler (py/scheduler.py).

The scheduling logic is tested without GPIO hardware: the Scheduler takes
a fake "runner" that records the actions instead of running the bin/
scripts, and a fixed clock.  A few tests also run the real
py/hardware_controller.py commands through the default runner with the
simulated GPIO backend, and exercise the microweb Schedule page.
"""
import datetime
import json
import os
import shutil
import subprocess
import sys
import urllib.parse

import pytest

import scheduler
from scheduler import (Schedule, Scheduler, due_events, format_days,
                       format_time, load_schedule, next_events, parse_days,
                       parse_time, validate_schedule)

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_home(tmp_path, overrides=""):
    """A throw-away LightShow Pi home with the real defaults.cfg."""
    home = tmp_path / "lsp"
    (home / "config").mkdir(parents=True)
    shutil.copy(os.path.join(REPO, "config", "defaults.cfg"),
                str(home / "config" / "defaults.cfg"))
    if overrides:
        (home / "config" / "overrides.cfg").write_text(overrides)
    (home / "logs").mkdir()
    return home


def at_time(day, hhmm):
    hour, minute = (int(part) for part in hhmm.split(":"))
    return datetime.datetime.combine(day, datetime.time(hour, minute))


# a Monday, so weekday math is easy to follow
MONDAY = datetime.date(2026, 11, 16)


def full_schedule(**kwargs):
    values = dict(enabled=True, days=frozenset(range(7)),
                  lights_on=datetime.time(16, 45),
                  show_start=datetime.time(18, 30),
                  show_stop=datetime.time(22, 15),
                  lights_off=datetime.time(23, 59))
    values.update(kwargs)
    return Schedule(**values)


class FakeRunner:
    """Records the actions it is asked to run (and can be made to fail)."""

    def __init__(self, fail=None):
        self.calls = []
        self.fail = set(fail or [])

    def __call__(self, name):
        self.calls.append(name)
        if name in self.fail:
            raise RuntimeError("simulated failure running %s" % name)


# ---------------------------------------------------------------- times/days


def test_parse_time():
    assert parse_time("18:30") == datetime.time(18, 30)
    assert parse_time("06:05") == datetime.time(6, 5)
    assert parse_time("  9:05 ") == datetime.time(9, 5)
    assert parse_time("") is None
    assert parse_time("   ") is None
    assert parse_time(None) is None


@pytest.mark.parametrize("bad", ["24:00", "18:60", "18", "18:30:00", "six",
                                 "18-30", "-1:00"])
def test_parse_time_rejects_bad_values(bad):
    with pytest.raises(ValueError):
        parse_time(bad)


def test_parse_days():
    assert parse_days("daily") == frozenset(range(7))
    assert parse_days("") == frozenset(range(7))
    assert parse_days("mon") == frozenset([0])
    assert parse_days("mon,wed,fri") == frozenset([0, 2, 4])
    assert parse_days("MON,Tue") == frozenset([0, 1])
    assert parse_days("sat,sun") == frozenset([5, 6])


@pytest.mark.parametrize("bad", ["monday", "mon,,tue", "xyz", "mon-fri"])
def test_parse_days_rejects_bad_values(bad):
    with pytest.raises(ValueError):
        parse_days(bad)


def test_format_days_round_trip():
    assert format_days(frozenset(range(7))) == "daily"
    assert format_days(frozenset([0, 2, 4])) == "mon,wed,fri"
    assert parse_days(format_days(frozenset([5, 6]))) == frozenset([5, 6])


# ---------------------------------------------------------------- config


def test_load_schedule_defaults_are_disabled(tmp_path):
    home = make_home(tmp_path)
    schedule = load_schedule(str(home))
    assert schedule.enabled is False
    assert schedule.days == frozenset(range(7))
    assert schedule.lights_on == datetime.time(16, 45)
    assert schedule.show_start == datetime.time(18, 30)
    assert schedule.show_stop == datetime.time(22, 15)
    assert schedule.lights_off == datetime.time(23, 59)


def test_load_schedule_overrides_win(tmp_path):
    home = make_home(tmp_path, "[schedule]\nenabled = True\ndays = sat,sun\n"
                                "lights_on = 17:00\nshow_start =\n"
                                "show_stop =\nlights_off = 23:00\n")
    schedule = load_schedule(str(home))
    assert schedule.enabled is True
    assert schedule.days == frozenset([5, 6])
    assert schedule.lights_on == datetime.time(17, 0)
    assert schedule.show_start is None
    assert schedule.show_stop is None
    assert schedule.lights_off == datetime.time(23, 0)


def test_load_schedule_bad_time_raises(tmp_path):
    home = make_home(tmp_path, "[schedule]\nshow_start = 25:00\n")
    with pytest.raises(ValueError):
        load_schedule(str(home))


def test_validate_schedule():
    assert validate_schedule(full_schedule()) == []
    assert validate_schedule(full_schedule(enabled=False)) == []
    assert validate_schedule(full_schedule(
        show_start=datetime.time(22, 15),
        show_stop=datetime.time(18, 30))) != []
    assert validate_schedule(full_schedule(
        lights_on=datetime.time(23, 59),
        lights_off=datetime.time(16, 45))) != []
    assert validate_schedule(Schedule(enabled=True)) != []  # no times set
    assert validate_schedule(Schedule(enabled=False)) == []


# ---------------------------------------------------------------- due/next


def test_due_events_fires_within_grace():
    schedule = full_schedule()
    now = at_time(MONDAY, "18:30") + datetime.timedelta(seconds=20)
    assert due_events(schedule, now, set()) == ["show_start"]


def test_due_events_not_before_time():
    schedule = full_schedule()
    assert due_events(schedule, at_time(MONDAY, "18:29"), set()) == []


def test_due_events_missed_after_grace():
    # the daemon was not running when the time arrived: no retroactive fire
    schedule = full_schedule()
    now = at_time(MONDAY, "18:30") + datetime.timedelta(minutes=5)
    assert due_events(schedule, now, set()) == []


def test_due_events_only_once_per_day():
    schedule = full_schedule()
    now = at_time(MONDAY, "18:30")
    assert due_events(schedule, now, {"show_start"}) == []
    assert due_events(schedule, now, set()) == ["show_start"]


def test_due_events_day_matching():
    schedule = full_schedule(days=frozenset([5, 6]))  # weekends only
    assert due_events(schedule, at_time(MONDAY, "18:30"), set()) == []
    saturday = MONDAY + datetime.timedelta(days=5)
    assert due_events(schedule, at_time(saturday, "18:30"), set()) == [
        "show_start"]


def test_due_events_disabled_is_noop():
    schedule = full_schedule(enabled=False)
    assert due_events(schedule, at_time(MONDAY, "18:30"), set()) == []


def test_due_events_not_fired_when_daemon_started_late():
    # started at 18:31, after the 18:30 show start: it must not fire
    schedule = full_schedule()
    now = at_time(MONDAY, "18:31")
    started_at = at_time(MONDAY, "18:31")
    assert due_events(schedule, now, set(), started_at=started_at) == []
    # ... but the 22:15 stop later the same evening still fires
    now = at_time(MONDAY, "22:15")
    assert due_events(schedule, now, set(),
                      started_at=started_at) == ["show_stop"]


def test_next_events_today_and_rollover():
    schedule = full_schedule(days=frozenset([0]))  # Mondays only
    upcoming = next_events(schedule, at_time(MONDAY, "17:00"), count=4)
    assert [(at.strftime("%H:%M"), name) for at, name in upcoming] == [
        ("18:30", "show_start"), ("22:15", "show_stop"),
        ("23:59", "lights_off"), ("16:45", "lights_on")]
    assert upcoming[0][0].date() == MONDAY
    assert upcoming[3][0].date() == MONDAY + datetime.timedelta(days=7)


def test_next_events_disabled_is_empty():
    assert next_events(full_schedule(enabled=False),
                       at_time(MONDAY, "17:00")) == []


# ---------------------------------------------------------------- daemon


def _scheduler(tmp_path, runner, **kwargs):
    home = make_home(tmp_path, "[schedule]\nenabled = True\n")
    kwargs.setdefault("started_at", at_time(MONDAY, "12:00"))
    return home, Scheduler(str(home), runner=runner, **kwargs)


def test_tick_fires_once_and_state_survives_restart(tmp_path):
    runner = FakeRunner()
    home, sched = _scheduler(tmp_path, runner)
    assert sched.tick(at_time(MONDAY, "18:30")) == ["show_start"]
    assert runner.calls == ["show_start"]
    assert sched.tick(at_time(MONDAY, "18:30")) == []  # same tick: no refire

    # a fresh Scheduler (daemon restarted) with the same state file
    restarted = Scheduler(str(home), runner=runner,
                          started_at=at_time(MONDAY, "12:00"))
    assert restarted.tick(at_time(MONDAY, "18:30")) == []
    assert runner.calls == ["show_start"]

    # the next day it fires again
    tuesday = MONDAY + datetime.timedelta(days=1)
    assert restarted.tick(at_time(tuesday, "18:30")) == ["show_start"]
    assert runner.calls == ["show_start", "show_start"]


def test_tick_state_file_records_fired_actions(tmp_path):
    runner = FakeRunner()
    home, sched = _scheduler(tmp_path, runner)
    sched.tick(at_time(MONDAY, "18:30"))
    state = json.loads((home / "logs" / "scheduler-state.json").read_text())
    assert state["date"] == MONDAY.isoformat()
    assert state["fired"] == ["show_start"]


def test_tick_disabled_schedule_is_noop(tmp_path):
    home = make_home(tmp_path)  # defaults: enabled = False
    runner = FakeRunner()
    sched = Scheduler(str(home), runner=runner,
                      started_at=at_time(MONDAY, "12:00"))
    assert sched.tick(at_time(MONDAY, "18:30")) == []
    assert runner.calls == []
    assert not (home / "logs" / "scheduler-state.json").exists()


def test_tick_failed_action_is_not_marked_fired(tmp_path):
    runner = FakeRunner(fail={"show_start"})
    home, sched = _scheduler(tmp_path, runner)
    assert sched.tick(at_time(MONDAY, "18:30")) == []
    # still within the grace window a minute later: it retries
    runner.fail = set()
    assert sched.tick(at_time(MONDAY, "18:30")
                      + datetime.timedelta(seconds=45)) == ["show_start"]


def test_show_stop_restores_steady_lights(tmp_path):
    runner = FakeRunner()
    home, sched = _scheduler(tmp_path, runner)
    assert sched.tick(at_time(MONDAY, "22:15")) == ["show_stop"]
    # the show stopped at 22:15 but the lights stay on until 23:59
    assert runner.calls == ["show_stop", "lights_on"]


def test_show_stop_does_not_restore_after_lights_off(tmp_path):
    runner = FakeRunner()
    home = make_home(tmp_path, "[schedule]\nenabled = True\n"
                                "lights_off = 21:00\n")
    sched = Scheduler(str(home), runner=runner,
                      started_at=at_time(MONDAY, "12:00"))
    assert sched.tick(at_time(MONDAY, "22:15")) == ["show_stop"]
    assert runner.calls == ["show_stop"]


def test_default_runner_builds_the_right_commands(tmp_path, monkeypatch):
    home = make_home(tmp_path, "[schedule]\nenabled = True\n")
    seen = []
    monkeypatch.setattr(Scheduler, "_run_command",
                        lambda self, argv: seen.append(argv))
    sched = Scheduler(str(home), started_at=at_time(MONDAY, "12:00"))
    sched._default_runner("lights_on")
    assert seen[-1][-1] == "--state=on"
    assert seen[-1][-2].endswith("py/hardware_controller.py")
    sched._default_runner("lights_off")
    assert seen[-1][-1] == "--state=off"
    sched._default_runner("show_start")
    assert seen[-1][-1].endswith("bin/start_music_and_lights")
    sched._default_runner("show_stop")
    assert seen[-1][-2].endswith("bin/stop_music_and_lights")
    assert seen[-1][-1] == str(os.getpid())  # the daemon spares itself


def test_status_output(tmp_path, capsys):
    home = make_home(tmp_path, "[schedule]\nenabled = True\n")
    assert scheduler.show_status(str(home)) == 0
    out = capsys.readouterr().out
    assert "Scheduler: enabled" in out
    assert "Days:      daily" in out
    assert "16:45" in out and "18:30" in out
    assert "Status:    not running" in out
    assert "Next:" in out


# ---------------------------------------------------------------- CLI


def test_cli_schedule_status(test_home, monkeypatch):
    monkeypatch.setenv("LIGHTSHOWPI_NO_SUDO", "1")
    monkeypatch.setenv("LIGHTSHOWPI_PYTHON", sys.executable)
    env = dict(os.environ, SYNCHRONIZED_LIGHTS_HOME=test_home)
    result = subprocess.run(
        [os.path.join(test_home, "bin", "lightshowpi"), "schedule", "status"],
        capture_output=True, text=True, env=env, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "Scheduler: disabled" in result.stdout
    assert "Status:" in result.stdout


def test_cli_schedule_usage_errors(test_home, monkeypatch):
    monkeypatch.setenv("LIGHTSHOWPI_NO_SUDO", "1")
    monkeypatch.setenv("LIGHTSHOWPI_PYTHON", sys.executable)
    env = dict(os.environ, SYNCHRONIZED_LIGHTS_HOME=test_home)
    for argv in (["schedule"], ["schedule", "bogus"]):
        result = subprocess.run(
            [os.path.join(test_home, "bin", "lightshowpi")] + argv,
            capture_output=True, text=True, env=env, timeout=60)
        assert result.returncode == 2, (argv, result.stdout, result.stderr)


def test_cli_usage_lists_schedule(test_home, monkeypatch):
    monkeypatch.setenv("LIGHTSHOWPI_NO_SUDO", "1")
    monkeypatch.setenv("LIGHTSHOWPI_PYTHON", sys.executable)
    env = dict(os.environ, SYNCHRONIZED_LIGHTS_HOME=test_home)
    result = subprocess.run([os.path.join(test_home, "bin", "lightshowpi")],
                            capture_output=True, text=True, env=env,
                            timeout=60)
    assert result.returncode == 0, result.stderr
    assert "schedule start|stop|status" in result.stdout


# ---------------------------------------------------------------- web UI


@pytest.fixture
def web_home(tmp_path):
    home = tmp_path / "lsp"
    home.mkdir()
    for sub in ("web", "config", "music"):
        shutil.copytree(os.path.join(REPO, sub), str(home / sub),
                        symlinks=True)
    for sub in ("py", "bin", "tools"):
        os.symlink(os.path.join(REPO, sub), str(home / sub))
    (home / "logs").mkdir()
    (home / "config" / "overrides.cfg").write_text(
        "[lightshow]\naudio_out_card = null\n")
    return home


def run_cgi(home, page, post=None):
    body = urllib.parse.urlencode(post or {}).encode()
    env = dict(os.environ,
               SYNCHRONIZED_LIGHTS_HOME=str(home),
               LIGHTSHOWPI_GPIO_BACKEND="simulated",
               LIGHTSHOWPI_PYTHON=sys.executable,
               LIGHTSHOWPI_NO_SUDO="1",
               GATEWAY_INTERFACE="CGI/1.1",
               REQUEST_METHOD="POST" if post else "GET",
               QUERY_STRING="",
               CONTENT_TYPE="application/x-www-form-urlencoded",
               CONTENT_LENGTH=str(len(body)),
               PATH="/usr/bin:/bin")
    script = str(home / "web" / "microweb" / "cgi-bin" / (page + ".cgi"))
    return subprocess.run([sys.executable, script], input=body, env=env,
                          cwd=str(home / "web" / "microweb"),
                          capture_output=True, timeout=60)


def test_schedule_page_loads(web_home):
    result = run_cgi(web_home, "schedule")
    out = result.stdout.decode(errors="replace")
    err = result.stderr.decode(errors="replace")
    assert result.returncode == 0, err
    assert "Traceback" not in err and "cgitb_error" not in out, out + err
    assert "Schedule" in out
    assert "16:45" in out  # the default lights-on time is shown
    assert "Scheduler is not running" in out


def test_schedule_page_save_valid(web_home):
    result = run_cgi(web_home, "schedule", post={
        "message": "Save", "enabled": "on",
        "day_mon": "on", "day_tue": "on", "day_wed": "on",
        "day_thu": "on", "day_fri": "on",
        "lights_on": "16:45", "show_start": "18:30",
        "show_stop": "22:15", "lights_off": "23:59"})
    out = result.stdout.decode(errors="replace")
    assert result.returncode == 0, result.stderr.decode()
    assert "Schedule saved." in out
    saved = (web_home / "config" / "overrides.cfg").read_text()
    assert "enabled = True" in saved
    assert "days = mon,tue,wed,thu,fri" in saved
    assert "show_start = 18:30" in saved
    # the unrelated setting in overrides.cfg is kept
    assert "audio_out_card = null" in saved


def test_schedule_page_save_rejects_bad_time(web_home):
    result = run_cgi(web_home, "schedule", post={
        "message": "Save", "enabled": "on", "day_mon": "on",
        "lights_on": "16:45", "show_start": "25:00",
        "show_stop": "22:15", "lights_off": "23:59"})
    out = result.stdout.decode(errors="replace")
    assert result.returncode == 0, result.stderr.decode()
    assert "Schedule saved." not in out
    assert "show start" in out.lower()
    saved = (web_home / "config" / "overrides.cfg").read_text()
    assert "[schedule]" not in saved


def test_schedule_page_save_rejects_stop_before_start(web_home):
    result = run_cgi(web_home, "schedule", post={
        "message": "Save", "enabled": "on", "day_mon": "on",
        "lights_on": "16:45", "show_start": "22:15",
        "show_stop": "18:30", "lights_off": "23:59"})
    out = result.stdout.decode(errors="replace")
    assert "must be after show_start" in out
    assert "Schedule saved." not in out


def test_main_page_links_to_schedule(web_home):
    result = run_cgi(web_home, "web_controls")
    out = result.stdout.decode(errors="replace")
    assert result.returncode == 0, result.stderr.decode()
    assert 'action="schedule.cgi"' in out
    assert "Schedule" in out

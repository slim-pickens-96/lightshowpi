#!/usr/bin/env python3
#
# Licensed under the BSD license.  See full license in LICENSE file.
# http://www.lightshowpi.org/
#
# Built-in daily scheduler for LightShow Pi.
#
# The scheduler daemon watches the clock and fires the actions from the
# [schedule] section of the config (see config/defaults.cfg and
# docs/SCHEDULER.md): steady lights on, start the music show, stop the
# music show, steady lights off.  It runs without hand-edited cron entries:
#
#   lightshowpi schedule start    run the daemon in the foreground
#   lightshowpi schedule status   show the schedule and the next actions
#   lightshowpi schedule stop     stop the daemon
#
# Or enable the systemd service: sudo systemctl enable --now
# lightshowpi-scheduler
#
# The scheduling logic in this module is deliberately independent of the
# GPIO hardware so it can be tested without a Raspberry Pi: the actions are
# run through a "runner" callable (by default a subprocess call of the
# existing bin/ scripts and py/hardware_controller.py).

"""Built-in daily scheduler: steady lights and the music show on a timetable."""

import argparse
import configparser
import datetime
import json
import logging
import os
import signal
import subprocess
import sys
import time

# The home directory and configuration directory for the application.
HOME_DIR = os.getenv("SYNCHRONIZED_LIGHTS_HOME")

if not HOME_DIR:
    # Default to the folder this file lives in (<home>/py/..) so LightShow Pi
    # works without the environment variable, e.g. when started by systemd.
    HOME_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.environ["SYNCHRONIZED_LIGHTS_HOME"] = HOME_DIR

CONFIG_DIR = HOME_DIR + "/config"
LOG_DIR = HOME_DIR + "/logs"
BIN_DIR = HOME_DIR + "/bin"
PY_DIR = HOME_DIR + "/py"

# How late an action may be before it is skipped instead of fired.  The
# daemon checks the time every 30 seconds, so an action normally fires
# within 30 seconds of its time; the grace covers a delayed check.  Anything
# later than this is treated as missed (for example the daemon was started
# after the time) and is not fired retroactively.
GRACE_SECONDS = 90

# Day names used in the config, in weekday() order (Monday is 0).
DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# The scheduled actions, in the order they are checked each tick.
ACTIONS = ("lights_on", "show_start", "show_stop", "lights_off")

ACTION_DESCRIPTIONS = {
    "lights_on": "lights on (steady)",
    "show_start": "show start",
    "show_stop": "show stop",
    "lights_off": "lights off",
}

log = logging.getLogger("scheduler")


class Schedule(object):
    """One day's worth of scheduling settings, from the [schedule] section."""

    def __init__(self, enabled=False, days=frozenset(range(7)),
                 lights_on=None, show_start=None, show_stop=None,
                 lights_off=None):
        self.enabled = enabled
        self.days = frozenset(days)
        self.lights_on = lights_on
        self.show_start = show_start
        self.show_stop = show_stop
        self.lights_off = lights_off

    def actions(self):
        """The configured actions as (name, time) pairs, in time order."""
        timed = [(name, getattr(self, name)) for name in ACTIONS]
        return sorted([(name, when) for name, when in timed if when is not None],
                      key=lambda item: item[1])

    def __repr__(self):
        return ("Schedule(enabled=%r, days=%r, lights_on=%r, show_start=%r, "
                "show_stop=%r, lights_off=%r)" % (
                    self.enabled, sorted(self.days), self.lights_on,
                    self.show_start, self.show_stop, self.lights_off))


def parse_time(value):
    """Parse an HH:MM 24-hour time, or return None for a blank value.

    :param value: the time string, e.g. "18:30"; blank means "no time set"
    :raises ValueError: if the value is not a valid HH:MM time
    """
    if value is None:
        return None
    value = str(value).strip()
    if value == "":
        return None
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("time %r is not in HH:MM format" % value)
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        raise ValueError("time %r is not in HH:MM format" % value)
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("time %r is not a valid 24-hour time" % value)
    return datetime.time(hour, minute)


def format_time(when):
    """Format a time as HH:MM, or "" when no time is set."""
    if when is None:
        return ""
    return "%02d:%02d" % (when.hour, when.minute)


def parse_days(value):
    """Parse the days setting into a set of weekday numbers (Monday is 0).

    "daily" (or a blank value) means every day, otherwise a comma list of
    three-letter day names, e.g. "mon,wed,fri".

    :raises ValueError: if a day name is not recognised
    """
    if value is None:
        return frozenset(range(7))
    value = str(value).strip().lower()
    if value in ("", "daily", "everyday", "all"):
        return frozenset(range(7))
    days = set()
    for name in value.split(","):
        name = name.strip()
        if name not in DAY_NAMES:
            raise ValueError("unknown day %r (use mon,tue,wed,thu,fri,sat,sun "
                             "or daily)" % name)
        days.add(DAY_NAMES.index(name))
    return frozenset(days)


def format_days(days):
    """Format a set of weekday numbers as "daily" or a comma list."""
    if set(days) == set(range(7)):
        return "daily"
    return ",".join(DAY_NAMES[day] for day in sorted(days))


def load_schedule(home_dir=HOME_DIR, param_config=None):
    """Load the [schedule] section from defaults.cfg plus overrides.

    :param home_dir: the LightShow Pi install folder
    :param param_config: an extra config file, as in configuration_manager
    :raises ValueError: if a schedule setting is not valid
    :rtype: Schedule
    """
    config = configparser.RawConfigParser(allow_no_value=True)
    config.read_file(open(os.path.join(home_dir, "config", "defaults.cfg")))
    if param_config:
        if os.path.isabs(param_config):
            config.read([param_config])
        else:
            config.read([os.path.join(home_dir, "config", param_config)])
    else:
        config.read([os.path.join(home_dir, "config", "overrides.cfg")])

    def _get(option, fallback=""):
        if config.has_section("schedule"):
            return config.get("schedule", option, fallback=fallback)
        return fallback

    enabled = config.getboolean("schedule", "enabled", fallback=False) \
        if config.has_section("schedule") else False
    return Schedule(
        enabled=enabled,
        days=parse_days(_get("days", "daily")),
        lights_on=parse_time(_get("lights_on")),
        show_start=parse_time(_get("show_start")),
        show_stop=parse_time(_get("show_stop")),
        lights_off=parse_time(_get("lights_off")),
    )


def validate_schedule(schedule):
    """Check a schedule for mistakes; return a list of error messages."""
    errors = []
    if schedule.show_start is not None and schedule.show_stop is not None:
        if schedule.show_stop <= schedule.show_start:
            errors.append("show_stop (%s) must be after show_start (%s)" % (
                format_time(schedule.show_stop), format_time(schedule.show_start)))
    if schedule.lights_on is not None and schedule.lights_off is not None:
        if schedule.lights_off <= schedule.lights_on:
            errors.append("lights_off (%s) must be after lights_on (%s)" % (
                format_time(schedule.lights_off), format_time(schedule.lights_on)))
    if schedule.enabled and not schedule.actions():
        errors.append("the schedule is enabled but no times are set")
    if schedule.enabled and not schedule.days:
        errors.append("the schedule is enabled but no days are selected")
    return errors


def due_events(schedule, now, fired, started_at=None):
    """The actions due at `now` that have not fired yet today.

    An action is due when today is a scheduled day, its time has arrived
    within the last GRACE_SECONDS, it has not fired today, and (when
    `started_at` is given) its time arrived while this daemon was running.
    Anything later than the grace window is missed, never fired
    retroactively: starting the daemon after a scheduled time does not
    trigger that action.

    :param schedule: the Schedule to check
    :param now: the current time (datetime)
    :param fired: names of the actions already fired today
    :param started_at: when this daemon started (None: no start-up check)
    :rtype: list of action names, in time order
    """
    if not schedule.enabled:
        return []
    if now.weekday() not in schedule.days:
        return []
    due = []
    for name, when in schedule.actions():
        if name in fired:
            continue
        scheduled = datetime.datetime.combine(now.date(), when)
        if started_at is not None and scheduled < started_at:
            continue
        delta = (now - scheduled).total_seconds()
        if 0 <= delta <= GRACE_SECONDS:
            due.append(name)
    return due


def next_events(schedule, now, count=8):
    """The next scheduled actions from `now`, as (datetime, name) pairs.

    Looks up to 7 days ahead; returns fewer when the schedule has no
    actions.  A disabled schedule has no next events.
    """
    if not schedule.enabled or not schedule.actions():
        return []
    found = []
    day = now.date()
    for _ in range(8):
        if day.weekday() in schedule.days:
            for name, when in schedule.actions():
                at = datetime.datetime.combine(day, when)
                if at >= now:
                    found.append((at, name))
        if len(found) >= count:
            break
        day += datetime.timedelta(days=1)
    found.sort()
    return found[:count]


class Scheduler(object):
    """The daemon: checks the clock, fires due actions once a day."""

    def __init__(self, home_dir=HOME_DIR, runner=None, interval=30,
                 state_file=None, pid_file=None, config_file=None,
                 clock=None, started_at=None):
        self.home_dir = home_dir
        self.interval = interval
        self.config_file = config_file
        self.state_file = state_file or os.path.join(home_dir, "logs",
                                                     "scheduler-state.json")
        self.pid_file = pid_file or os.path.join(home_dir, "logs",
                                                 "scheduler.pid")
        self.runner = runner or self._default_runner
        self.clock = clock or datetime.datetime.now
        self.started_at = started_at or self.clock()
        self.schedule = None
        self._stop = False

    # -- state: what fired today, kept on disk so a restart does not refire --

    def _load_state(self, day):
        """Return the set of actions fired on `day` (empty on a new day)."""
        try:
            with open(self.state_file) as state_fp:
                state = json.load(state_fp)
        except (IOError, ValueError):
            return set()
        if state.get("date") != day.isoformat():
            return set()
        return set(state.get("fired", []))

    def _save_state(self, fired, day):
        state = {"date": day.isoformat(), "fired": sorted(fired)}
        tmp = self.state_file + ".tmp"
        with open(tmp, "w") as state_fp:
            json.dump(state, state_fp)
        os.rename(tmp, self.state_file)

    # -- one check of the clock --

    def tick(self, now=None):
        """Check the time once; fire and return the actions fired."""
        now = now or self.clock()
        try:
            self.schedule = load_schedule(self.home_dir, self.config_file)
        except (IOError, ValueError) as error:
            log.error("Could not load the schedule: %s", error)
            return []
        if not self.schedule.enabled:
            return []
        errors = validate_schedule(self.schedule)
        if errors:
            for error in errors:
                log.error("Schedule problem: %s", error)
            return []
        fired = self._load_state(now.date())
        due = due_events(self.schedule, now, fired, started_at=self.started_at)
        fired_now = []
        for name in due:
            if self._fire(name, now):
                fired.add(name)
                fired_now.append(name)
        if fired_now:
            self._save_state(fired, now.date())
        return fired_now

    def _fire(self, name, now):
        """Run one action; return True when it ran without error."""
        log.info("Firing %s (%s)", name, ACTION_DESCRIPTIONS[name])
        try:
            self.runner(name)
        except Exception as error:
            log.error("Could not fire %s: %s", name, error)
            return False
        if name == "show_stop":
            # The show is off; put the steady lights back on when the
            # steady-lights window has not ended yet.
            schedule = self.schedule
            if (schedule.lights_on is not None
                    and schedule.lights_off is not None
                    and schedule.lights_on <= now.time() < schedule.lights_off):
                log.info("Show stopped; turning the steady lights back on")
                try:
                    self.runner("lights_on")
                except Exception as error:
                    log.error("Could not turn the steady lights back on: %s",
                              error)
        return True

    # -- running the actions through the existing entry points --

    def _run_command(self, argv):
        env = dict(os.environ, SYNCHRONIZED_LIGHTS_HOME=self.home_dir)
        result = subprocess.run(argv, env=env, timeout=120,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise RuntimeError("%s exited with code %d: %s" % (
                " ".join(argv), result.returncode,
                (result.stderr or result.stdout or "").strip()))

    def _default_runner(self, name):
        py_dir = os.path.join(self.home_dir, "py")
        bin_dir = os.path.join(self.home_dir, "bin")
        if name == "lights_on":
            argv = [sys.executable,
                    os.path.join(py_dir, "hardware_controller.py"),
                    "--state=on"]
        elif name == "lights_off":
            argv = [sys.executable,
                    os.path.join(py_dir, "hardware_controller.py"),
                    "--state=off"]
        elif name == "show_start":
            argv = [os.path.join(bin_dir, "start_music_and_lights")]
        elif name == "show_stop":
            # Pass our own pid so stop_music_and_lights does not kill us:
            # it kills every process matching "lightshowpi" except the pid
            # it is given.
            argv = [os.path.join(bin_dir, "stop_music_and_lights"),
                    str(os.getpid())]
        else:
            raise ValueError("unknown scheduled action: %r" % name)
        self._run_command(argv)

    # -- running as a daemon --

    def request_stop(self, signum=None, frame=None):
        self._stop = True

    def run_forever(self):
        """Loop forever (until SIGTERM/SIGINT), checking the clock."""
        if not os.path.isdir(LOG_DIR):
            os.makedirs(LOG_DIR)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            handlers=[logging.FileHandler(os.path.join(LOG_DIR,
                                                       "scheduler.log")),
                      logging.StreamHandler(sys.stdout)])
        try:
            self.schedule = load_schedule(self.home_dir, self.config_file)
        except (IOError, ValueError) as error:
            print("Scheduler configuration error: %s" % error, file=sys.stderr)
            return 2
        if not self.schedule.enabled:
            print("The schedule is disabled (set enabled = True in the "
                  "[schedule] section of config/overrides.cfg).",
                  file=sys.stderr)
            return 2
        errors = validate_schedule(self.schedule)
        if errors:
            for error in errors:
                print("Scheduler configuration error: %s" % error,
                      file=sys.stderr)
            return 2
        with open(self.pid_file, "w") as pid_fp:
            pid_fp.write(str(os.getpid()))
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)
        log.info("Scheduler started (pid %d); next: %s", os.getpid(),
                 ", ".join("%s at %s" % (name, at.strftime("%a %H:%M"))
                           for at, name in next_events(self.schedule,
                                                       self.clock())))
        try:
            while not self._stop:
                self.tick()
                deadline = time.time() + self.interval
                while not self._stop and time.time() < deadline:
                    time.sleep(1)
        finally:
            log.info("Scheduler stopping")
            try:
                os.remove(self.pid_file)
            except OSError:
                pass
        return 0


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_pid(pid_file):
    try:
        with open(pid_file) as pid_fp:
            return int(pid_fp.read().strip())
    except (IOError, ValueError):
        return None


def show_status(home_dir=HOME_DIR, config_file=None):
    """Print the schedule, whether the daemon is running, and next actions."""
    try:
        schedule = load_schedule(home_dir, config_file)
    except (IOError, ValueError) as error:
        print("Scheduler configuration error: %s" % error, file=sys.stderr)
        return 2
    print("Scheduler: %s" % ("enabled" if schedule.enabled else "disabled"))
    print("Days:      %s" % format_days(schedule.days))
    for name in ACTIONS:
        when = getattr(schedule, name)
        print("  %-10s %s" % (ACTION_DESCRIPTIONS[name],
                              format_time(when) if when else "-"))
    for error in validate_schedule(schedule):
        print("Problem:   %s" % error)
    pid_file = os.path.join(home_dir, "logs", "scheduler.pid")
    pid = _read_pid(pid_file)
    if pid is not None and _pid_alive(pid):
        print("Status:    running (pid %d)" % pid)
    else:
        print("Status:    not running")
        if pid is not None:
            print("           (stale pid file %s removed)" % pid_file)
            try:
                os.remove(pid_file)
            except OSError:
                pass
    if schedule.enabled:
        now = datetime.datetime.now()
        upcoming = next_events(schedule, now)
        if upcoming:
            print("Next:")
            for at, name in upcoming:
                print("  %-10s %s" % (at.strftime("%a %H:%M"),
                                      ACTION_DESCRIPTIONS[name]))
    return 0


def stop_daemon(home_dir=HOME_DIR):
    """Stop a running scheduler daemon; return 0 when it stopped."""
    pid_file = os.path.join(home_dir, "logs", "scheduler.pid")
    pid = _read_pid(pid_file)
    if pid is None or not _pid_alive(pid):
        print("Scheduler is not running.")
        if pid is not None:
            try:
                os.remove(pid_file)
            except OSError:
                pass
        return 1
    os.kill(pid, signal.SIGTERM)
    for _ in range(10):
        if not _pid_alive(pid):
            break
        time.sleep(1)
    if _pid_alive(pid):
        print("Scheduler (pid %d) did not stop." % pid)
        return 1
    print("Scheduler stopped.")
    try:
        os.remove(pid_file)
    except OSError:
        pass
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="LightShow Pi built-in scheduler daemon.")
    parser.add_argument("--config", default=None,
                        help="config file override, as in the other tools")
    parser.add_argument("--interval", type=int, default=30,
                        help="seconds between clock checks (default 30)")
    parser.add_argument("--once", action="store_true",
                        help="check the clock once and exit")
    parser.add_argument("--status", action="store_true",
                        help="show the schedule and whether the daemon runs")
    parser.add_argument("--stop", action="store_true",
                        help="stop a running scheduler daemon")
    args = parser.parse_args(argv)

    if args.status:
        return show_status(config_file=args.config)
    if args.stop:
        return stop_daemon()
    if args.once:
        scheduler = Scheduler(config_file=args.config)
        fired = scheduler.tick()
        if fired:
            print("Fired: %s" % ", ".join(fired))
        else:
            print("Nothing due.")
        return 0
    return Scheduler(interval=args.interval,
                     config_file=args.config).run_forever()


if __name__ == "__main__":
    sys.exit(main())

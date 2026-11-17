#!/usr/bin/env python3

#
# Licensed under the BSD license.  See full license in LICENSE file.
# http://www.lightshowpi.org/
#
# Schedule page for the microweb interface: show and edit the built-in
# daily scheduler ([schedule] section, see docs/SCHEDULER.md).  The settings
# are saved to config/overrides.cfg; the scheduler daemon re-reads them
# every 30 seconds, so no restart is needed.
#
# Follows the style of the other microweb pages (settings.cgi): form posts
# back to this script, values are validated on the server, and files the
# web UI writes belong to whoever owns the LightShow Pi folder.

import cgi
import cgitb
import configparser
import datetime
import html
import os
import sys

HOME_DIR = os.getenv("SYNCHRONIZED_LIGHTS_HOME")
sys.path.insert(0, HOME_DIR + '/py')

import scheduler

# Files written by the web UI belong to whoever owns the LightShow Pi folder
# (Raspberry Pi OS no longer has a default "pi" user).
_owner = os.stat(HOME_DIR)
uid, gid = _owner.st_uid, _owner.st_gid

OVERRIDES_PATH = HOME_DIR + '/config/overrides.cfg'

cgitb.enable()  # for troubleshooting
form = cgi.FieldStorage()
message = form.getvalue("message", "")


def _daemon_pid():
    """The pid of a running scheduler daemon, or None."""
    try:
        with open(HOME_DIR + '/logs/scheduler.pid') as pid_fp:
            pid = int(pid_fp.read().strip())
    except (IOError, ValueError):
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return pid


def _read_overrides():
    """The overrides file on its own (missing file: empty parser)."""
    overrides = configparser.RawConfigParser(allow_no_value=True)
    overrides.read([OVERRIDES_PATH])
    return overrides


def _save_schedule(schedule):
    """Write the [schedule] section to overrides.cfg, keeping the rest."""
    overrides = _read_overrides()
    if not overrides.has_section('schedule'):
        overrides.add_section('schedule')
    overrides.set('schedule', 'enabled', 'True' if schedule.enabled else 'False')
    overrides.set('schedule', 'days', scheduler.format_days(schedule.days))
    overrides.set('schedule', 'lights_on', scheduler.format_time(schedule.lights_on))
    overrides.set('schedule', 'show_start', scheduler.format_time(schedule.show_start))
    overrides.set('schedule', 'show_stop', scheduler.format_time(schedule.show_stop))
    overrides.set('schedule', 'lights_off', scheduler.format_time(schedule.lights_off))
    with open(OVERRIDES_PATH, 'w') as overrides_fp:
        overrides.write(overrides_fp)
    os.chown(OVERRIDES_PATH, uid, gid)


def _schedule_from_form():
    """Build a Schedule from the submitted form, collecting errors.

    Returns (schedule, errors).  A time that is blank means "skip that
    action"; a time that is not HH:MM is an error.
    """
    errors = []
    enabled = form.getvalue("enabled") is not None

    days = set()
    for index, name in enumerate(scheduler.DAY_NAMES):
        if form.getvalue("day_" + name) is not None:
            days.add(index)
    if not days:
        errors.append("Select at least one day.")

    times = {}
    for action in scheduler.ACTIONS:
        try:
            times[action] = scheduler.parse_time(form.getvalue(action, ""))
        except ValueError as error:
            errors.append("%s: %s" % (scheduler.ACTION_DESCRIPTIONS[action],
                                      error))
            times[action] = None

    schedule = scheduler.Schedule(
        enabled=enabled, days=frozenset(days),
        lights_on=times.get("lights_on"), show_start=times.get("show_start"),
        show_stop=times.get("show_stop"), lights_off=times.get("lights_off"))
    errors.extend(scheduler.validate_schedule(schedule))
    return schedule, errors


# The schedule currently in effect (defaults plus overrides), or the one
# just submitted when the save had errors, so the form keeps its values.
try:
    current = scheduler.load_schedule(HOME_DIR)
except (IOError, ValueError) as error:
    current = scheduler.Schedule()
    load_error = str(error)
else:
    load_error = None

saved = False
errors = []
if message == "Save":
    submitted, errors = _schedule_from_form()
    if errors:
        current = submitted
    else:
        try:
            _save_schedule(submitted)
        except (IOError, OSError) as error:
            errors.append("Could not save the schedule: %s" % error)
        else:
            current = submitted
            saved = True


print ("Content-type: text/html")
print

print ("""
<!DOCTYPE html>
<html>
    <head>
        <meta charset="utf-8">
        <title>LightShowPi Web Controls</title>
        <meta name="description" content="A very basic web interface for LightShowPi">
        <meta name="author" content="Ken B">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link rel="shortcut icon" href="/favicon.png">
        <meta name="mobile-web-app-capable" content="yes">
        <link rel="icon" sizes="196x196" href="/favicon.png">
        <link rel="apple-touch-icon" sizes="152x152" href="/favicon.png">
        <link rel="stylesheet" href="/css/style.css">
    </head>
    <body>
            <h2> LightShowPi Web Controls </h2>
            <h3> Schedule </h3>

            <form method="post" action="web_controls.cgi">
                <input id="playlist" type="submit" value="Back">
            </form>

            <p>Run the steady lights and the music show on a daily timetable,
            without editing cron.  The scheduler daemon checks the time every
            30 seconds and fires each action once a day.</p>
""")

if load_error:
    print ('<p><h2>Could not read the schedule: %s</h2></p>'
           % html.escape(load_error))

if errors:
    print ('<p><h2>Could not save the schedule:</h2></p>')
    for error in errors:
        print ('<p>%s</p>' % html.escape(error))

if saved:
    print ('<p><h2>Schedule saved.</h2></p>')
    print ('<p>The scheduler daemon picks it up within 30 seconds; '
           'no restart is needed.</p>')

pid = _daemon_pid()
if pid is not None:
    print ('<p>Scheduler is running (pid %d).</p>' % pid)
else:
    print ('<p>Scheduler is not running. Start it with '
           '<b>lightshowpi schedule start</b>, or at boot with '
           '<b>sudo systemctl enable --now lightshowpi-scheduler</b>.</p>')

if current.enabled and not errors:
    upcoming = scheduler.next_events(current, datetime.datetime.now())
    if upcoming:
        print ('<p>Next:</p>')
        for at, name in upcoming:
            print ('<p>%s &mdash; %s</p>' % (
                html.escape(at.strftime("%a %H:%M")),
                html.escape(scheduler.ACTION_DESCRIPTIONS[name])))

print ("""
            <form method="post" action="schedule.cgi">
                <input type="hidden" name="message" value="Save"/>
                <p>
                <input type="checkbox" name="enabled" value="on"%s>
                <b>Schedule enabled</b>
                </p>
                <p>Days:</p>
                <p>
""" % (' checked="checked"' if current.enabled else ''))

for index, name in enumerate(scheduler.DAY_NAMES):
    checked = ' checked="checked"' if index in current.days else ''
    print ('<label><input type="checkbox" name="day_%s" value="on"%s> %s'
           '</label> ' % (name, checked, name.capitalize()))

print ("""
                </p>
                <p>Times (24-hour, blank skips that action):</p>
                <table class="center">
                <tr><td>Lights on (steady)</td>
                    <td><input type="time" name="lights_on" value="%s"></td></tr>
                <tr><td>Show start</td>
                    <td><input type="time" name="show_start" value="%s"></td></tr>
                <tr><td>Show stop</td>
                    <td><input type="time" name="show_stop" value="%s"></td></tr>
                <tr><td>Lights off</td>
                    <td><input type="time" name="lights_off" value="%s"></td></tr>
                </table>
                <p><input id="playlist" type="submit" value="Save Schedule"></p>
            </form>
""" % (html.escape(scheduler.format_time(current.lights_on)),
       html.escape(scheduler.format_time(current.show_start)),
       html.escape(scheduler.format_time(current.show_stop)),
       html.escape(scheduler.format_time(current.lights_off))))

print ("""
            <p>After the show stops, the lights come back on steady when the
            steady-lights window (lights on to lights off) has not ended yet.
            Times are the Pi's local time. See docs/SCHEDULER.md.</p>
""")

print ("</body></html>")

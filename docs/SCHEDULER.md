# Built-in scheduler

Run the steady lights and the music show on a daily timetable, without
hand-editing cron.  The scheduler daemon checks the clock every 30 seconds
and fires each scheduled action once a day:

| Time (default) | Action |
|---|---|
| 16:45 | Lights on, steady (no music, no blinking) |
| 18:30 | Start the music show (the playlist) |
| 22:15 | Stop the music show |
| 23:59 | Lights off |

After the show stops, the lights come back on steady when the
steady-lights window (lights on to lights off) has not ended yet, so the
house stays lit from 16:45 to 23:59 with the show in the middle.

## Turning it on

The schedule is **off by default**.  Edit the `[schedule]` section of
`config/overrides.cfg` (or use the Schedule page of the web interface,
below) and set `enabled = True`:

```ini
[schedule]
enabled = True
days = daily
lights_on = 16:45
show_start = 18:30
show_stop = 22:15
lights_off = 23:59
```

Then start the daemon:

```bash
lightshowpi schedule start    # foreground; Ctrl-C or "schedule stop" stops it
lightshowpi schedule status   # schedule, whether it is running, next actions
lightshowpi schedule stop     # stop a running daemon
```

To run it at boot, install the systemd service (the installer does not add
it yet):

```bash
sudo cp install-scripts/lightshowpi-scheduler.service \
        /etc/systemd/system/lightshowpi-scheduler.service
sudo sed -i "s|@INSTALL_DIR@|$(pwd)|g" \
        /etc/systemd/system/lightshowpi-scheduler.service
sudo systemctl daemon-reload
sudo systemctl enable --now lightshowpi-scheduler

sudo systemctl stop lightshowpi-scheduler     # stop the daemon
sudo systemctl disable lightshowpi-scheduler  # don't start it at boot
journalctl -u lightshowpi-scheduler           # service log
tail -f logs/scheduler.log                    # same log, in the install folder
```

Stopping the scheduler does **not** stop a show that is already playing
and does not turn the lights off; use `lightshowpi stop` for that.

## Settings

All times are 24-hour `HH:MM` in the Pi's local time.  Leave a time blank
to skip that action (for example, no `show_start` means the lights just
come on steady and never play music).

| Setting | Meaning |
|---|---|
| `enabled` | `True` switches the schedule on; `False` (default) is a complete no-op |
| `days` | `daily` for every day, or a comma list like `mon,tue,wed,thu,fri` |
| `lights_on` | Turn the lights on steady |
| `show_start` | Start the music show |
| `show_stop` | Stop the music show |
| `lights_off` | Turn the steady lights off |

The daemon re-reads the settings every 30 seconds, so edits (from the
config file or the web page) take effect without restarting it.  A schedule
with `show_stop` before `show_start`, or `lights_off` before `lights_on`,
is refused: the daemon logs the problem and does nothing until it is fixed.
Times that cross midnight (for example lights off at 00:30) are not
supported; keep `lights_off` after `lights_on` on the same day.

## Web interface

The main controls page has a **Schedule** button (next to the Tools and
Settings icons).  The Schedule page shows whether the daemon is running,
the next scheduled actions, and a form to change the settings: an enabled
checkbox, the days, and the four times.  Saving writes the `[schedule]`
section of `config/overrides.cfg` and keeps every other setting in that
file.  The times are checked on the server (24-hour format, stop after
start, off after on) and a bad value is reported instead of saved.

## How it works

* The daemon is `py/scheduler.py`.  It loops about every 30 seconds,
  reloads the `[schedule]` section, and fires each action whose time has
  arrived.  The actions reuse the existing entry points: steady lights
  through `py/hardware_controller.py --state=on|off`, the show through
  `bin/start_music_and_lights` / `bin/stop_music_and_lights`.
* **Each action fires once a day.**  What fired is recorded in
  `logs/scheduler-state.json`, so restarting the daemon does not fire the
  same action again.
* **Nothing fires retroactively.**  An action fires only when its time
  arrives while the daemon is running (within about 90 seconds of the
  time, to allow for a delayed check).  Starting the daemon after a
  scheduled time skips that action until tomorrow.
* **A failed action is not marked as fired**, so the next check (still
  inside the 90-second window) retries it.  Failures are logged to
  `logs/scheduler.log`.
* `bin/stop_music_and_lights` never kills the scheduler daemon (or the
  web interface) when it stops the show; stop the daemon separately with
  `lightshowpi schedule stop`.  The daemon also passes its own pid to
  `stop_music_and_lights` as a second guard.
* When the schedule is disabled, nothing about the existing behaviour
  changes: the show, the cron examples and the web interface work exactly
  as before.

## Scheduler vs cron

| | Built-in scheduler | cron (`crontab/synchronized_lights`) |
|---|---|---|
| Where the times live | `config/overrides.cfg`, editable on the web Schedule page | root's crontab, edited with `sudo crontab -e` |
| Steady lights + show in one place | Yes, one `[schedule]` section | Separate lines per action |
| Missed times (Pi was off) | Skipped, never fired late | Skipped (cron does not catch up either) |
| Change the times | Saved from the web page, live in 30 seconds | Edit the crontab and wait for the next run |
| What runs it | `lightshowpi-scheduler` service | cron, which is always running |

The cron examples are unchanged and still work.  Use one or the other, not
both, or the two will fight over the lights.

## Troubleshooting

* **"Scheduler: disabled"** from `lightshowpi schedule status`: set
  `enabled = True` in the `[schedule]` section.
* **"Status: not running"**: the daemon is not started.  Run
  `lightshowpi schedule start` (foreground) or enable the service above.
* **The daemon exits at once with a configuration error**: run
  `lightshowpi schedule status`, which prints the problem (a bad time, or
  stop before start).  The service also refuses to restart on a
  configuration error (exit code 2) instead of looping.
* **An action did not fire**: check `logs/scheduler.log` for the reason,
  and that the Pi's clock and time zone are right (`date` should show the
  local time; fix it with `sudo dpkg-reconfigure tzdata`).
* **The show keeps playing after the daemon was stopped**: stopping the
  daemon does not stop the show; run `lightshowpi stop`.

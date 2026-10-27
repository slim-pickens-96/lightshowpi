# Troubleshooting

Start with:

```bash
lightshowpi doctor
```

It checks the operating system, Python packages, ffmpeg, the board, the GPIO
back end and pins, the audio device, the FM transmitter and the playlist, and
prints a fix for each problem. The installer log is in `logs/install.log`;
show logs are in `logs/`.

The sections below cover the problems users reported with the original
LightShow Pi (collected from [r/LightShowPi](https://www.reddit.com/r/LightShowPi/),
the [Raspberry Pi Forums](https://forums.raspberrypi.com/viewtopic.php?t=360006)
and the [lightshowpi.org Getting Started comments](https://www.lightshowpi.org/getting-started/)).
Each one says what changed and what to do if you still see it.

---

## Installation

### "Unknown distribution" / the installer refuses to run

**Before:** `install.sh` accepted only `ID=raspbian` or `ID=archarm` in
`/etc/os-release`. 64-bit Raspberry Pi OS reports `ID=debian`, so it stopped
([report](https://www.reddit.com/r/LightShowPi/comments/17f692t/newbie_needs_help_debian_version_issues/),
[forum thread](https://forums.raspberrypi.com/viewtopic.php?t=360006)).

**Now:** any Debian 12 "bookworm" or 13 "trixie" system is accepted, whether
it reports `debian` or `raspbian`, 32-bit or 64-bit. Copying
`install-scripts/raspbian` to `install-scripts/debian` is no longer needed.

**If you see** `... is too old`: you are on Bullseye or older. Flash a current
Raspberry Pi OS with Raspberry Pi Imager. If you see `... is not supported`,
your system isn't Debian 12/13; `--allow-unsupported` lets you try anyway.

### wiringpi-latest.deb: 404 / "Unable to locate package wiringpi"

**Before:** the installer and docs downloaded
`project-downloads.drogon.net/wiringpi-latest.deb`, which now returns 404
([report](https://www.reddit.com/r/LightShowPi/comments/r5zish/unable_to_locate_package_wiringpi/)).

**Now:** WiringPi isn't needed for normal use. GPIO goes through **lgpio**,
which Raspberry Pi OS provides as `python3-lgpio`. If you use I/O expanders
(MCP23017 etc.) or a PiGlow, run `sudo ./install.sh --with-wiringpi`. That
installs WiringPi 3.20 from the
[maintained WiringPi project](https://github.com/WiringPi/WiringPi) and checks
the file's SHA-256 first.

### "externally-managed-environment" / `--break-system-packages`

**Before:** the installer ran `pip3 install` system-wide, which Debian 12+
blocks ([PEP 668](https://packaging.python.org/en/latest/specifications/externally-managed-environments/);
[report](https://www.reddit.com/r/LightShowPi/comments/qra0tp/latest_install_information_111021/)).

**Now:** almost everything comes from apt. The rest goes into a virtual
environment in `lightshowpi/.venv`. Never use `--break-system-packages` for
LightShow Pi.

**If a pip step fails:** check your internet connection and run
`sudo ./install.sh` again. Details are in `logs/install.log`.

### "Failed building wheel for rpi-audio-levels" / "Unable to enable V3D" / `svn: ... 404`

**Before:** the installer compiled a GPU FFT that needed `/opt/vc` sources
(downloaded with `svn` from GitHub, which no longer works) and the legacy
graphics driver. It also forced a GL driver change with `raspi-config`
([report](https://www.reddit.com/r/LightShowPi/comments/10hyagw/error_installing/),
[report](https://www.reddit.com/r/LightShowPi/comments/ragfpq/start_music_and_lights_not_working/),
[report](https://www.reddit.com/r/LightShowPi/comments/171f391/raspi_4_new_install/)).

**Now:** the CPU FFT (numpy) is the default (`use_gpu = False`). Nothing is
compiled and the graphics driver isn't touched. If an old `overrides.cfg`
still says `use_gpu = True`, LightShow Pi logs a warning and uses the CPU FFT.

### "Unable to locate package python-simplejson / python-serial / python-spidev / libatlas-base-dev"

**Before:** the installer used Python 2 package names and `libatlas-base-dev`,
which Debian 13 doesn't have. Any missing package stopped the install
([report](https://www.reddit.com/r/LightShowPi/comments/171f391/raspi_4_new_install/),
[report](https://www.reddit.com/r/LightShowPi/comments/17aiedb/cannot_properly_install_lightshowpi_on_rasberry/)).

**Now:** only current `python3-*` packages are used. Optional packages that a
release doesn't have are skipped with a message, not treated as fatal. The
installer always runs `apt-get update` first.

**If you see** `These required packages are not available`: run
`sudo apt update`, check your internet connection and `/etc/apt/sources.list`,
then run the installer again.

### `alsa/asoundlib.h: No such file or directory`

**Before:** pip compiled pyalsaaudio, which needs `libasound2-dev`, and that
wasn't installed.

**Now:** pyalsaaudio comes pre-built from apt (`python3-alsaaudio`), so
nothing is compiled. If you install into another environment yourself, run
`sudo apt install libasound2-dev` first.

### The old installer changed `/usr/bin/python` and `/etc/sudoers`

**Before:** it replaced `/usr/bin/python` and `/usr/bin/pip` with symlinks,
appended to `/etc/sudoers` without `visudo` and changed the GL driver. None of
this could be undone.

**Now:** none of these are changed. `sudo ./uninstall.sh` removes everything
the new installer adds and tells you if it finds leftovers from the old one.

---

## Running

### `ModuleNotFoundError: No module named 'audioop'`

**Before:** `synchronized_lights.py` used `audioop`, which was removed in
Python 3.13 (the default on Debian 13 / Raspberry Pi OS Trixie).

**Now:** `audioop` is replaced with numpy (`audio_decoder.peak()`), and the
old decoder with ffmpeg. Tests pass on Python 3.11, 3.13 and 3.14.

### `RuntimeError: Could not determine Raspberry Pi model` (Pi 5, Pi 500, Pi 400) / wrong model

**Before:** board detection used a fixed list of revision codes. Pi 5, 500
and 400 crashed, a CM4 was reported as a "Pi 2", and a Zero 2 W as a
"Pi Zero"
([report](https://www.reddit.com/r/LightShowPi/comments/jal9jm/unable_to_complete_setup_of_lightshowpi/),
[report](https://www.reddit.com/r/LightShowPi/comments/qkg9g1/raspberry_pi_4_issues/)).

**Now:** the model is decoded from the revision code's bit fields, with
`/proc/device-tree/model` as a fallback. New boards that follow the same
scheme are recognised. `lightshowpi doctor` shows what was detected.

### The lights don't turn on and there's no error

**Before:** if the board wasn't recognised, a do-nothing stub was loaded
silently.

**Now:** on a computer that isn't a Pi, LightShow Pi logs
`using SIMULATED GPIO` and the doctor says so. On a Pi, a GPIO problem is a
clear error with exit code 2. Check:

1. `lightshowpi doctor` shows `GPIO back end: lgpio` (or `wiringpi`), not
   `simulated`.
2. `gpio_pins` are the right numbers. They are **WiringPi** numbers unless
   you set `pin_numbering = bcm`; run `lightshowpi pins` for a chart
   ([common confusion](https://www.reddit.com/r/LightShowPi/comments/16wlc8z/clarifying_the_gpios_and_the_rpi_pin_numbers/)).
3. Relay boards that switch on when the pin is LOW need
   `active_low_mode = True`. If all lights are on when they should be off,
   flip this setting.
4. `lightshowpi flash` blinks every channel in turn.

### "No GPIO chip found" / "Could not open a GPIO chip"

`No GPIO chip found` means `/dev/gpiochip*` doesn't exist: you aren't on a Pi,
or the kernel is very old. `Could not open` means a permissions problem: run
through `sudo` (the default) or add your user to the `gpio` group
(`sudo usermod -aG gpio $USER`, then log in again).

### "I/O expanders / PiGlow need WiringPi"

You configured `devices = ...` or a PiGlow. Run
`sudo ./install.sh --with-wiringpi`.

### No sound, or sound out of the wrong socket

([report](https://www.reddit.com/r/LightShowPi/comments/k3l130/audio_output_fails_after_running_lightshow/),
[report](https://www.reddit.com/r/LightShowPi/comments/1h20gy7/help_with_audio/),
[report](https://www.reddit.com/r/LightShowPi/comments/ka21qy/help_35mm_jack/))

1. Run `aplay -L` and pick the device: `sysdefault:CARD=Headphones` for the
   3.5 mm jack (Pi 1–4; **the Pi 5 has no jack**), `plughw:CARD=vc4hdmi0` for
   HDMI, or your USB card's name.
2. Set it as `audio_out_card` in the `[lightshow]` section of `overrides.cfg`.
3. `lightshowpi doctor` opens the device with the same settings the show uses
   (16-bit stereo, 44.1 kHz) and tells you if it fails.
4. If the FM transmitter is enabled (`fm = True`), the sound goes to FM, not
   the speakers.
5. Check the volume with `alsamixer`.

### `TypeError: function takes at most 5 arguments (7 given)` when a song starts

This came from Debian 12's `python3-alsaaudio` 0.8.4, which is older than the
pyalsaaudio that pip used to install. It was found while testing this version
and is fixed: `py/alsa_compat.py` supports both old and new pyalsaaudio.

### `ALSA ... cannot open audio_in_card` (audio-in mode)

Set `audio_in_card` to a capture device from `arecord -L`
([report](https://www.reddit.com/r/LightShowPi/comments/f1uknd/alsa_audio_error/)).
`tools/audio_in_cards.py` lists the cards.

### "Song file not found" / the sample song won't play

Paths in playlists and `--file` can use `$SYNCHRONIZED_LIGHTS_HOME`, which is
now set automatically ([report](https://www.reddit.com/r/LightShowPi/comments/jqwhv5/configurationproblem/)).
Try `lightshowpi play ~/lightshowpi/music/sample/ovenrake_deck-the-halls.mp3`.
A missing file is now reported as `Song file not found: ...` instead of a
Python traceback. Regenerate a playlist with
`lightshowpi playlist-generate <folder>`.

A missing playlist file is reported as `Playlist not found: ...` and counts as
a configuration error (exit code 2), so the service stops instead of
restarting.

### The service stopped: "failed 5 times in a row"

`lightshowpi-service` (used by `lightshowpi.service`) restarts the show after
an error. If the show fails 5 times in a row, each within 10 seconds of
starting, the service stops instead of looping forever. Exit code 2 (a
configuration error) stops it straight away. A known way to trigger this is
WiringPi on a board it can't identify: the WiringPi library prints "Unable to
determine Raspberry Pi board revision" and ends the process itself. Check
`journalctl -u lightshowpi`, then run `lightshowpi doctor`. You can change
the limit with `LIGHTSHOWPI_MAX_QUICK_FAILURES`.

### The first play of a song looks less lively than later plays

That's how LightShow Pi has always worked. On the first play it uses
estimated levels while it analyses the song, then saves the real ones to the
`.sync` file. To analyse songs in advance, run `tools/sync_file_generator.py`.

### The FM transmitter doesn't work

* The bundled FM programs are 32-bit ARM programs that drive the Pi's clock
  hardware. They **do not work on the Pi 5 / 500 / CM5**; LightShow Pi stops
  with an explanation if `fm = True` there.
* On 64-bit Raspberry Pi OS (Pi 1–4), install their 32-bit libraries with
  `sudo ./install.sh --with-fm`.
* FM output hasn't been tested with this version; it needs real hardware.
  Check that FM broadcasting is legal where you live.

### Autostart at boot / crontab confusion

([report](https://www.reddit.com/r/LightShowPi/comments/kf6st9/help_trying_to_complete_set_up/))
Use `sudo ./install.sh --with-service` and `sudo systemctl start|stop lightshowpi`.
`journalctl -u lightshowpi` shows what happened. The cron examples in
`crontab/synchronized_lights` still work.

### The web interface doesn't start on Python 3.13

The `cgi` module was removed in Python 3.13. The installer adds
`python3-legacy-cgi` (or the `legacy-cgi` pip package). `lightshowpi doctor`
reports `Web interface (legacy-cgi)`.

### LED strips: `No module named 'distutils'`

BiblioPixel 3.4.46 (last released 2020) imports `distutils`, which was removed
in Python 3.12. `--with-led` installs `python3-setuptools`, which provides a
replacement. It imports on Python 3.11 and 3.13; driving real LED strips
hasn't been tested.

### SMS / Twitter

These features depend on Google Voice and Twitter APIs that have changed a lot
since they were written. They're optional (`--with-sms`) and untested.

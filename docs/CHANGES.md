# Changes in 3.2.0-modernized

This release is based on upstream LightShow Pi `master` at commit
`f7509014df7bacffa206e56f712680b987c08d20` (2022-02-11) from
<https://bitbucket.org/togiles/lightshowpi>. The light show logic (FFT analysis,
channel mapping, preshow/postshow, cached `.sync` files, config format) is the
same. Most of the changes are to installation, dependencies, hardware
detection and error handling.

Each change below is tied to a problem listed in the Phase 1 report and in
[TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Compatibility decisions

| Decision | Why |
|---|---|
| Supported OS: Raspberry Pi OS / Debian **bookworm (12)** and **trixie (13)**. Older releases are refused. Other distributions are refused unless you pass `--allow-unsupported`. | These are the current releases ([Raspberry Pi OS downloads](https://www.raspberrypi.com/software/operating-systems/), [trixie announcement](https://www.raspberrypi.com/news/trixie-the-new-version-of-raspberry-pi-os/)). Both were tested in clean chroots. Bullseye and older are end of life, and the old installer broke on them anyway ([Reddit](https://www.reddit.com/r/LightShowPi/comments/17f692t/newbie_needs_help_debian_version_issues/)). |
| Python packages come from **apt** where possible (numpy, mutagen, python3-alsaaudio, python3-lgpio), inside a **venv created with `--system-site-packages`**. | Avoids PEP 668 "externally-managed-environment" errors without using `--break-system-packages` ([PEP 668 spec](https://packaging.python.org/en/latest/specifications/externally-managed-environments/)). No compilers are needed on the default path. |
| GPIO through **lgpio** (`/dev/gpiochip*`) by default, with WiringPi as an option. | WiringPi's old `.deb` link is dead ([Reddit](https://www.reddit.com/r/LightShowPi/comments/r5zish/unable_to_locate_package_wiringpi/)), and pigpio doesn't support the Pi 5 ([pigpio #589](https://github.com/joan2937/pigpio/issues/589), [Stack Exchange](https://raspberrypi.stackexchange.com/questions/145013/future-of-gpio-access-on-pi5)). lgpio is packaged by Raspberry Pi for bookworm and trixie. |
| **WiringPi pin numbers are kept** as the config default (`pin_numbering = wiringpi`). BCM is available as an option. | Existing `overrides.cfg` files keep working unchanged. |
| WiringPi (`--with-wiringpi`) is downloaded from the [official GitHub release](https://github.com/WiringPi/WiringPi/releases) 3.20 and **checked against a pinned SHA-256** before it is installed. | Replaces the dead `project-downloads.drogon.net` link. Pinning the checksum stops a changed or tampered file from being installed. |
| **CPU (numpy) FFT by default** (`use_gpu = False`). The GPU module is optional and falls back to the CPU with a warning. | `rpi-audio-levels` needs the removed `/opt/vc` userland and the VideoCore IV GPU, so it can't be built on current OS releases or on the Pi 4/5 ([Reddit](https://www.reddit.com/r/LightShowPi/comments/10hyagw/error_installing/)). |
| Audio decoding uses **ffmpeg** (apt) instead of `decoder.py` + `audioop`. | `audioop` was removed in Python 3.13, so upstream crashes at import on trixie. ffmpeg handles mp3/wav/flac/ogg/m4a. |
| **No system-wide changes**: no `/usr/bin/python` symlink, no `/etc/sudoers` edits, no `/etc/environment` edits. The service is opt-in. | The old installer changed system files, which broke other software and was hard to undo. |
| Arch Linux ARM installer **dropped**. | It was unmaintained and couldn't be tested here. `--allow-unsupported` still lets you try on other systems. |
| No containers. | GPIO, ALSA and the FM hack need direct hardware access, and containers would make installation harder, not easier. |

## Files changed

### New files

| File | Purpose |
|---|---|
| `install.sh` (rewritten) | Checks the OS, installs apt packages, creates `.venv`, writes `/etc/profile.d/lightshowpi.sh`, and links `/usr/local/bin/lightshowpi`. Options: `--with-service`, `--with-led`, `--with-wiringpi`, `--with-fm`, `--with-sms`, `--all`, `--skip-apt`, `--allow-unsupported` and `--dry-run`. It logs to `install.log` and is safe to run again. |
| `uninstall.sh` | Undoes everything `install.sh` did. It keeps `config/overrides.cfg` unless you pass `--purge`. `--dry-run` shows what it would do. |
| `install-scripts/lightshowpi.service` | systemd unit template with `Restart=on-failure`. `RestartPreventExitStatus=2` stops a restart loop when the config is wrong, and `ExecStopPost` turns the lights off. |
| `bin/lightshowpi` | One command for everything: `doctor`, `play`, `playlist`, `loop`, `start`, `stop`, `test`, `on`, `off`, `flash`, `fade`, `cleanup`, `pins`, `playlist-generate`, `web`, `version` and `help`. |
| `bin/lightshowpi-env.sh` | Shared shell setup for all `bin/` scripts: the install folder, the venv Python and `sudo -E` handling. Supports `LIGHTSHOWPI_NO_SUDO` and `LIGHTSHOWPI_PYTHON`. |
| `bin/lightshowpi-service` | Foreground loop used by systemd. Exit code 2 (configuration error) stops it, 5 quick failures in a row stop it (a crash-loop guard), and SIGTERM exits cleanly. |
| `py/gpio_backend.py` | GPIO back ends: lgpio, WiringPi (ctypes, for expanders/PiGlow), legacy wiringpi Python, and simulated. Converts WiringPi pin numbers to BCM. Selected by `[hardware] gpio_backend` or `LIGHTSHOWPI_GPIO_BACKEND`. Errors are explicit, with no silent fallback on a Pi. |
| `py/audio_decoder.py` | ffmpeg/ffprobe streaming decoder with the same interface as the old `decoder.py`. Includes `peak()`, which replaces `audioop.max`. |
| `py/alsa_compat.py` | Opens ALSA PCMs on both old (0.8.x, bookworm) and new (0.10+, trixie) `pyalsaaudio`. Fixes `TypeError: function takes at most 5 arguments (7 given)`, which testing showed also affects upstream on bookworm. |
| `py/doctor.py` | `lightshowpi doctor`: checks the OS, Python, modules, ffmpeg, board, GPIO access, pin numbers, audio device (opened with the show's settings), FM, playlist and optional features. Exits 1 if any check fails. |
| `config/overrides.cfg.example` | Commented starting point for user settings. |
| `requirements/*.txt` | Pip lists for the core packages, the fallback when apt packages are missing, LED, SMS and development/tests. |
| `tools/build_release.sh` | Builds a release tarball and its SHA-256 from committed files (see [PACKAGING.md](PACKAGING.md)). |
| `tests/` | pytest suite with about 140 tests (see [TEST_REPORT.md](TEST_REPORT.md)). |
| `docs/` | Install, troubleshooting, changes, test report, limitations and packaging. |
| `VERSION` | `3.2.0-modernized`. |

### Modified files

| File | Change |
|---|---|
| `py/Platform.py` | Decodes the Raspberry Pi revision code bit fields, with a fallback to `/proc/device-tree/model`. Fixes the `RuntimeError` on Pi 5, Pi 500, Pi 400 and CM5 ([Reddit](https://www.reddit.com/r/LightShowPi/comments/171f391/raspi_4_new_install/)), CM4 detected as a Pi 2, and Zero 2 W detected as a Zero. Also fixes Python 3.12+ invalid-escape `SyntaxWarning`s. `LIGHTSHOWPI_CPUINFO` / `LIGHTSHOWPI_DT_MODEL` overrides are available for testing. |
| `py/hardware_controller.py` | Uses `gpio_backend` and exits with code 2 and a clear message on GPIO errors (it used to show a traceback). Imports the LED module lazily so LED dependencies are optional. `test()` works on non-Pi boards. |
| `py/configuration_manager.py` | New `[hardware] gpio_backend` and `pin_numbering` options. `SYNCHRONIZED_LIGHTS_HOME` defaults to the install folder. Accepts an absolute `--config=` path. |
| `config/defaults.cfg` | `use_gpu = False`, and the new options are documented. |
| `py/fft.py` | `rpi_audio_levels` is optional, with a CPU fallback and warning. |
| `py/synchronized_lights.py` | Uses `audio_decoder` instead of `decoder`/`audioop` and `alsa_compat` for output and audio-in. A missing song gives a clear "Song file not found" error (exit 1). A missing playlist gives "Playlist not found" (exit 2, a configuration error). `now_playing.txt` is written by Python, and `songname_command` arguments are passed through `shlex.quote`, which fixes shell injection through song tags. FM on a Pi 5 or newer stops with a clear explanation (exit 2). |
| `py/light_simulator.py` | Python 3 `tkinter` import. |
| `py/commands.py`, `py/check_sms.py` | `logging.warn` → `logging.warning` (removed in Python 3.13). |
| `tools/sync_file_generator.py` | Imports the new decoder (it used to depend on the `decoder` pip package, which is no longer installed). Uses the same chunk size, channels and FFT settings as the show, and writes the `.cfg` file next to each `.sync`. Without that file the show treated the cache as out of date and analysed the song again, which was an upstream bug. A regression test checks that the output matches `synchronized_lights.py --createcache`. Works without `SYNCHRONIZED_LIGHTS_HOME`. |
| `tools/playlist_generator.py` | Accepts the folder as an argument and matches file extensions case-insensitively. |
| `bin/play`, `bin/play_sms`, `bin/start_music_and_lights` | Quote `"$@"`, which fixes filenames containing spaces. |
| `bin/get_free`, `bin/get_swap` | Updated for the current `free` output format, and quoting fixed. |
| Other `bin/*` scripts | Use `lightshowpi-env.sh` and no longer require `SYNCHRONIZED_LIGHTS_HOME` or `/usr/bin/python`. All pass `shellcheck`. |
| `web/microweb/CGIHTTPServer_root.py` | Runs CGI scripts with the same Python as the server (`sys.executable`). |
| `web/microweb/cgi-bin/*.cgi` | `python3` shebangs; raw-string regex in `dir_play.cgi`. The `cgi` module comes from `python3-legacy-cgi` on Python 3.13+. |
| `.gitignore` | Ignores `.venv`, `dist/`, logs, caches and generated `.sync`/`.cfg` files. |
| `README.md` | Rewritten for this release. Credits and release history are kept. |

### Removed files

| File | Why |
|---|---|
| `install-scripts/raspbian`, `install-scripts/archarm`, `install-scripts/TEMPLATE` | Replaced by the new `install.sh`. They contained the dead URLs, the `/usr/bin/python` change and the sudoers edits. |

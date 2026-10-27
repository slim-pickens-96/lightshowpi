# Test report — 3.2.0-modernized

Every result below comes from a command that was actually run. **No physical
Raspberry Pi, relay board, LED strip or sound card was available**, so
anything that needs real hardware is listed under "Not run" and has not been
verified.

## Test environment

| Item | Value |
|---|---|
| Host | Ubuntu 26.04 x86_64 sandbox, no systemd running, ALSA `null` device only |
| Host Pythons | 3.11.17, 3.13.16 and 3.14.8, each in its own venv (numpy, mutagen, pyalsaaudio, pytest; plus `legacy-cgi` on 3.13+) |
| Clean OS installs | `debootstrap --variant=minbase` chroots: Debian **bookworm** amd64, Debian **trixie** amd64, and **trixie arm64** (qemu-user emulation) with the Raspberry Pi archive (`archive.raspberrypi.com`) added |
| Tools | ffmpeg, shellcheck 0.11.0, `systemd-analyze` |

Hardware can't be fully simulated. Hardware was emulated three ways:

- `LIGHTSHOWPI_GPIO_BACKEND=simulated`, which writes pin changes to a trace file.
- Fake `/proc/cpuinfo` and device-tree model files, used to test board detection.
- An injected fake `lgpio` module.

## Passed

### Automated test suite (pytest)

Command (from the project folder; `LIGHTSHOWPI_PYTHON` makes the shell-script
tests use the same interpreter):

```bash
LIGHTSHOWPI_PYTHON=<venv>/bin/python <venv>/bin/python -m pytest -q tests
```

| Environment | Result |
|---|---|
| Host, Python 3.11.17 | **141 passed** |
| Host, Python 3.13.16 | **140 passed, 1 skipped** (audioop comparison; `audioop` doesn't exist on 3.13+) |
| Host, Python 3.14.8 | **140 passed, 1 skipped** (same) |
| bookworm chroot, apt Python 3.11.2 + the installed `.venv` | **120 passed, 21 skipped** (21 = shellcheck isn't installed in the chroot) |
| trixie chroot, apt Python 3.13.5 + the installed `.venv` | **119 passed, 22 skipped** (shellcheck ×21, audioop ×1) |
| trixie arm64 chroot (qemu), apt Python 3.13 + the installed `.venv` | **119 passed, 22 skipped** (shellcheck ×21, audioop ×1). Before the crash-loop fix, this run had 1 failure (see "Failed during testing"). |

What the suite covers (`tests/`):

| File | What it checks |
|---|---|
| `test_platform.py` | Revision-code decoding for 18 boards from the original Model B through Zero/Zero W, Pi 2, 3, 3B+, 3A+, 4, Zero 2 W, 400, CM4, Pi 5, 500 and CM5. The same codes are tested through a fake `/proc/cpuinfo`. Device-tree-only fallback. Non-Pi boards. Unknown future board types. |
| `test_gpio_backend.py` | Simulated back end and trace file. lgpio back end against a fake lgpio: picks the header chip by label (`pinctrl-rp1` on Pi 5, `pinctrl-bcm2711` on Pi 4), maps WiringPi pins, BCM numbering, software PWM, refuses expanders with a clear message. WiringPi→BCM table. WiringPi Python and ctypes adapters. Back-end selection and environment override. Clear error when there is no `/dev/gpiochip*`. |
| `test_audio.py` | ffmpeg decoder: WAV, mp3, mono→stereo, flac/ogg/m4a, missing file, non-audio file, missing ffmpeg message. `peak()` against its definition and against `audioop.max` (on 3.11 only). `alsa_compat` against old-style (0.8.x) and new-style (0.10+) pyalsaaudio fakes and the real `null` device. |
| `test_config_and_hardware.py` | Config loading, `[hardware]` options, absolute `--config`. Hardware on/off/flash, `active_low_mode`, PWM. Expanders without WiringPi exit 2. CPU FFT finds a 440 Hz tone in the right channel. GPU fallback. |
| `test_end_to_end.py` | Real `synchronized_lights.py` runs against the ALSA `null` device with the simulated GPIO back end. A noise-burst mp3 creates a `.sync` cache. The second, cached run switches all 8 channels and leaves them off and set as inputs. The repository's sample song plays. A missing song gives a clear error. `tools/sync_file_generator.py` output equals `synchronized_lights.py --createcache` output (`.sync` within 1e-5, `.cfg` identical). |
| `test_doctor_and_scripts.py` | `lightshowpi doctor` passes a good config and fails a bad pin, a config syntax error and a missing audio card. `bash -n` and `shellcheck -S warning` on all 21 shell scripts. Installer dry runs: bookworm and trixie accepted, bullseye refused as too old, Ubuntu refused unless `--allow-unsupported` is given, unknown option rejected. `uninstall.sh --dry-run`. CLI help/version/unknown command/pins. `bin/play` with spaces in the filename. Service wrapper: exits 2 on a config error, a missing playlist exits 2 without a traceback, the crash-loop guard stops after repeated quick failures, and SIGTERM exits 0. |

### Clean installs (real installer, real apt, no mocks)

Command inside each fresh chroot, as user `pi`:

```bash
sudo ./install.sh --with-led --with-service
```

| Check | bookworm amd64 | trixie amd64 | trixie arm64 (qemu) |
|---|---|---|---|
| `install.sh` exit code | 0 | 0 | 0 |
| Python / numpy / pyalsaaudio (apt) | 3.11.2 / 1.24.2 / 0.8.4 | 3.13.5 / 2.2.4 / 0.10.0 | 3.13 / apt / apt |
| `python3-lgpio` | not in Debian amd64, expected and reported | same | **installed from the Raspberry Pi archive (0.2.2-1~rpt1+trixie), imports** |
| BiblioPixel (LED, pip in venv) | 3.4.46 imports | 3.4.46 imports | not tested |
| systemd unit written | yes (not enabled; no systemd in a chroot) | yes | yes |
| `systemd-analyze verify` on the unit | — | — | exit 0 |
| `lightshowpi doctor` with no sound card | FAILs audio, correctly | FAILs audio, correctly | — |
| `lightshowpi doctor` with `audio_out_card = null` | pass | pass | pass |
| `lightshowpi play` (sample mp3, simulated GPIO) | exit 0, `.sync` written | exit 0, `.sync` written | exit 0, `.sync` written |
| `lightshowpi playlist` | exit 0 | exit 0 | — |
| Reinstall over an existing install | works | — | — |
| `uninstall.sh`, then reinstall (`--skip-apt`) | — | works: service, symlink, profile and `.venv` removed, `overrides.cfg` kept | — |

Extra arm64 checks:

- `--with-wiringpi --with-fm`: WiringPi 3.20 was downloaded from the GitHub release and passed the pinned SHA-256 check. `gpio -v` reports 3.20 (it can't identify a board under emulation, as expected). The `armhf` architecture plus `libc6:armhf` and `libsndfile1:armhf` were added for the 32-bit FM binaries, and the doctor passes.
- Fake Pi 5 (revision `d04170`): the doctor detects "Raspberry Pi 5" and picks the lgpio back end. It then reports **FAIL: no /dev/gpiochip\***, which is correct inside a chroot. `lightshowpi on` exits 2 with a clear message (before the fix it showed a traceback).

### Other checks that passed

| Command | Result |
|---|---|
| `shellcheck -x -S warning` on all 21 shell scripts | clean. At `info`/`style` level the only notes left are the intentional word splitting of package lists in `install.sh` and style notes in the upstream `bin/vol`. |
| `bash -n` on all shell scripts | clean |
| Copy of the project at `/tmp/lsp copy` (a space in the path): `bin/start_playlist_once "/tmp/pl dir/.playlist"` and `bin/play "/tmp/pl dir/t one.mp3"` | both exit 0, `.sync`/`.cfg` written |
| `tools/sync_file_generator.py` on a folder containing `My Song.mp3` | exit 0; writes `.sync`, `.cfg` and a playlist |
| `tools/build_release.sh`, then extracting the tarball and running tests from it | see [PACKAGING.md](PACKAGING.md) and the release section below |

## Failed during testing (and fixed)

These were real failures found by the tests above. Each one now has a fix and
a test.

| Failure | Cause | Fix |
|---|---|---|
| Upstream `import audioop` → `ModuleNotFoundError` on Python 3.13/3.14 | `audioop` was removed from Python | `py/audio_decoder.py` (ffmpeg) |
| `Platform.py`: `RuntimeError` on Pi 5/500/400; CM4 reported as a Pi 2; Zero 2 W reported as a Zero; `SyntaxWarning` on 3.12+ | Hard-coded revision table | Revision-code bit decoding |
| bookworm: `TypeError: function takes at most 5 arguments (7 given)` when a song starts | bookworm's python3-alsaaudio 0.8.4 has a different `PCM()` signature. **This affects upstream too** on apt packages. | `py/alsa_compat.py` |
| Fake Pi 5 without `/dev/gpiochip*`: traceback | Uncaught back-end error | Clear message, exit 2 |
| `bin/play "a b.mp3"` split the filename into two | Unquoted `$@` | Quoted |
| Song tags containing shell characters were run by `songname_command` | String passed to the shell unescaped | `shlex.quote`; Python writes `now_playing.txt` |
| `tools/sync_file_generator.py`: `ModuleNotFoundError: audio_decoder`. In upstream it also never wrote `.cfg`, so the show re-analysed every song anyway. | Import order; missing `save_config()` | Fixed, with a regression test comparing against `--createcache` |
| arm64 test run: the service test timed out because `lightshowpi-service` restarted forever | With a real WiringPi 3.20 installed on a board it can't identify, the WiringPi library ends the process with exit code 1, so the wrapper kept retrying. A missing playlist also gave a traceback and exit 1. | Crash-loop guard: 5 quick failures in a row → exit 2. A missing playlist is a clear configuration error (exit 2). Both have tests. |
| Old Raspberry Pi archive key `raspberrypi.gpg.key` rejected by apt on trixie ("SHA1 binding not secure since 2026-02-01") | Old key format | Use the `raspberrypi-archive-keyring` 2025.1 package. This only affects the test chroot; real Raspberry Pi OS already ships the keyring. |
| `pip install pyalsaaudio` without headers → `alsa/asoundlib.h: No such file` | Missing `libasound2-dev` | The installer uses `python3-alsaaudio` from apt. `libasound2-dev` is only installed for the pip fallback. |

## Not run

| Item | Why |
|---|---|
| Web UI (microweb) in a browser | Only imports and the `legacy-cgi` dependency check were tested |
| SMS (Twilio) and Twitter | Need accounts and network access, and the APIs have changed since upstream wrote this code |
| The service actually starting at boot | No systemd in the sandbox. Only `systemd-analyze verify` and the wrapper's exit codes were tested. |
| 32-bit (armhf) Raspberry Pi OS as the main OS | No armhf chroot was built. Only armhf libraries for the FM binaries were tested. |
| Raspberry Pi OS **Lite image** itself | Debian chroots plus the Raspberry Pi archive were used instead |
| LED strips on arm64 | BiblioPixel was only tested on amd64 |

## Needs physical hardware (not verified)

- Real GPIO output on any Raspberry Pi model, including Pi 5 through `pinctrl-rp1`.
- Relays and SSRs, `active_low_mode`, and PWM brightness on real lights.
- Whether pins stay set after `lightshowpi on` exits, on lgpio.
- Access through the `gpio` group without sudo (`LIGHTSHOWPI_NO_SUDO=1`) on a real Pi.
- Audio out of the 3.5 mm jack, HDMI or a USB sound card; audio-in mode.
- The FM transmitter on Pi 1–4 (it is deliberately blocked on Pi 5).
- WS281x/APA102 LED strips, I/O expanders (MCP23017/MCP23S17 and others) and PiGlow.
- CPU load and timing of the numpy FFT on a Pi Zero/Zero 2 W.

## Reproducing

```bash
# host tests
python3 -m venv /tmp/v && /tmp/v/bin/pip install -r requirements/dev.txt
LIGHTSHOWPI_PYTHON=/tmp/v/bin/python /tmp/v/bin/python -m pytest -q tests

# clean OS install (needs root, debootstrap; Debian mirror)
sudo debootstrap --variant=minbase trixie /srv/trixie http://deb.debian.org/debian
# bind-mount /proc /sys /dev /dev/pts, copy the project in, add a 'pi' user with sudo, then:
sudo chroot /srv/trixie su - pi -c 'cd lightshowpi && sudo ./install.sh --with-service'
```

# LightShow Pi (modernized)

Synchronize Christmas or holiday lights to music with a Raspberry Pi: GPIO
relays/SSRs, LED strips, and optional FM broadcast.

This is a **community-modernized version** of
[LightShow Pi](https://bitbucket.org/togiles/lightshowpi) by Todd Giles and
contributors ([lightshowpi.org](https://www.lightshowpi.org/)). The light show
itself is unchanged. Changes are listed in [docs/CHANGES.md](docs/CHANGES.md),
and they make it install and run on current systems:

- **Raspberry Pi OS / Debian bookworm and trixie**, Python 3.11–3.14.
- **Pi 5, Pi 500, Pi 400, CM4/CM5 and Zero 2 W** are detected correctly.
- **No compiling, no dead download links, no `--break-system-packages`**: dependencies come from apt plus a local `.venv`.
- **lgpio** GPIO back end (works on the Pi 5); WiringPi is optional.
- **ffmpeg** audio decoding (works without `audioop`, which Python 3.13 removed).
- One `lightshowpi` command, a `lightshowpi doctor` self-check, an optional systemd service, and a clean `uninstall.sh`.

> **Hardware status:** this version has been tested with an automated test
> suite and in clean bookworm/trixie (amd64 and arm64) installs, using
> simulated GPIO and audio. It has **not yet been tested on a physical
> Raspberry Pi with lights attached**. See
> [docs/TEST_REPORT.md](docs/TEST_REPORT.md) and
> [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Quick start

```bash
sudo apt install -y git
git clone https://github.com/slim-pickens-96/lightshowpi.git ~/lightshowpi
cd ~/lightshowpi
sudo ./install.sh                  # add --with-service to start at boot
cp config/overrides.cfg.example config/overrides.cfg
lightshowpi doctor                 # checks OS, GPIO, pins, audio, playlist
lightshowpi test                   # blinks each channel in turn
lightshowpi playlist               # plays the sample songs
```

## Documentation

| Guide | Contents |
|---|---|
| [docs/INSTALL.md](docs/INSTALL.md) | Requirements and supported hardware, installation, first run, pin numbers, audio, configuring a show, commands, autostart, upgrading, uninstalling |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Fixes for common installation and runtime problems |
| [docs/CHANGES.md](docs/CHANGES.md) | What changed and why (compatibility decisions, file-by-file) |
| [docs/TEST_REPORT.md](docs/TEST_REPORT.md) | What was tested, how, and the results |
| [docs/LIMITATIONS.md](docs/LIMITATIONS.md) | Known limitations and remaining work |
| [docs/PACKAGING.md](docs/PACKAGING.md) | Building and publishing a release |

## Directory structure

* `bin/` - the `lightshowpi` command and helper scripts
* `config/` - `defaults.cfg` (documents every option) and your `overrides.cfg`
* `crontab/` - example cron entries (the systemd service is the recommended alternative)
* `docs/` - documentation
* `install.sh`, `uninstall.sh`, `install-scripts/` - installer and systemd unit
* `logs/` - log files
* `music/` - music files (includes samples to get you started)
* `py/` - the Python code
* `tests/` - automated tests (`python -m pytest tests`)
* `tools/` - playlist and sync-file generators, LED test, audio-in card helper
* `web/` - the microweb web interface

## License and community

All files are free to use under the BSD License (see `LICENSE`). The
original authors ask that you send improvements back so everyone can
benefit. Join the community on [Reddit](https://www.reddit.com/r/LightShowPi/)
and [Facebook](https://www.facebook.com/lightshowpi).

Contributors
============

A huge thanks to all those that have contributed to the Lightshow Pi codebase:

* Todd Giles
* Chris Usey
* Ryan Jennings
* Sean Millar
* Scott Driscoll
* Micah Wedemeyer
* Chase Cromwell
* Bruce Goheen
* Paul Dunn
* Stephen Burning
* Eric Higdon
* Tom Enos
* Brandon Lyon
* Ken B
* Paul Barnett
* Anthony Tod
* Brent Reinhard
* Caleb H
* Filippo B

Release Notes
============

2026 :: Version 3.2.0-modernized
-------------------------------

* Modern Raspberry Pi OS (bookworm/trixie) and Python 3.11-3.14 support, new installer, lgpio GPIO, ffmpeg audio, Pi 5 detection, doctor and service. See docs/CHANGES.md.

2021/11/11 :: Version 3.21
-------------------------------

* Caleb H contribution of .csv parsing as import sequence channel data
* Filippo B contribution of add active_low_mode by channel

2021/11/09 :: Version 3.20
-------------------------------

* Fixes for Pi4(B), kernel and Debian 11 based OS
* dir_play support multiple uploads

2019/12/24 :: Version 3.11
-------------------------------

* microweb - Directory Play page under Playlist page

2019/12/20 :: Version 3.10
-------------------------------

* network - support for server/serverjson send to specific IPs
* LED - add tools/led_test.py 
* add Arduino/nodemcu/lspi-gpio-mcp23017-0.ino for nodemcu/MCP23017 combination to allow 16 GPIOs

2019/11/27 :: Version 3.02
-------------------------------

* bin/vol to support USB sound devices
* serverjson fix for hardware_controller.py and sketch v1.5, broadcast bug
* minor bugs and error handling 

2019/11/09 :: Version 3.01
-------------------------------

* Expander chipset bug fixed
* Custom LED strip color maps, allow LEDs to work in network client mode 

2019/10/05 :: Version 3.0
-------------------------------

* Upgrade to python 3.x
* Various bug-fixes and updates to support install on latest Raspbian versions and Pi 4

2018/10/16 :: Version 1.4
-------------------------------

* Microweb V3 with multiple features
* More patterns and features for RGB LED Pixels
* Option to add argument --config=overridesX.cfg to synchronized_lights.py and others
* Networking serverraw option and NodeMCU sketch for client device 
* Various bug-fixes and updates to support install on latest Raspbian versions and Pi 3b+

2017/10/27 :: Version 1.3
-------------------------------

* Added initial support for controlling individually controllable RGB LED lights (thanks to Tom Enos, Ken B, and Chris Usey)
* Addition of the "microweb" UI for controlling your lightshow (thanks to Ken B)
* Twitter support, tweeting current song playing (thanks to Brent Reinhard and Ken B)
* Various bug-fixes and updates to support latest kernel versions (thanks to Ken B)

2016/10/16 :: Version 1.2
-------------------------------

* 3 to 4 times speed improvement by utilizing GPU for fft and other optimizations (thanks to Tom Enos, Colin Guyon, and Ken B)
* support for streaming audio from pandora, airplay, and other online sources (thanks to Tom Enos and Ken B)
* support fm broadcast on the pi2 and pi3 (thanks to Ken B)
* multiple refactors + addition of comments to the code + clean-up (thanks to Tom Enos)
* add the ability to override configuration options on a per-song basis (thanks to Tom Enos)
* support pagination for the SMS 'list' command (thanks to Brandon Lyon)
* support for running lightshow pi on your linux box for debugging (thanks to Micah Wedemeyer)
* addition of new configuration parameters to tweak many facets of the way lights blink / fade (thanks to Ken B)
* addition of new configuration parameters to tweak standard deviation bounds used (thanks to Paul Barnett)
* support a "terminal" mode for better debugging w/out hardware attached (thanks to Anthony Tod)
* many other misc bug fixes (see Issues list for more details)

2014/11/27 :: Version 1.1
-------------------------------

* piFM support (thanks to Stephen Burning)
* audio-in support (thanks to Paul Dunn)
* command line play-list generator (thanks to Eric Higdon)
* enhancements to preshow configuration, including per-channel control  (thanks to Chris Usey)
* support for expansion cards, including mcp23s17,mcp23017 (thanks to Chris Usey)
* updated to support RPi B+ (thanks to Chris Usey)
* clarification on comments and in-code documentation (thanks to Bruce Goheen, Chase Cromwell, and Micah Wedemeyer)
* other misc bug fixes (see Issues list for more details)

2014/02/16 :: Version 1
-------------------------------

* First "stable" release

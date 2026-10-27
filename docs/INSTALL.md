# Installing and running LightShow Pi

This guide covers the modernized LightShow Pi (version in `VERSION`). It
replaces the old `install.sh` / `install-scripts/raspbian` process.

## What you need

### Hardware

| Item | Notes |
|------|-------|
| Raspberry Pi | Any model with a 26- or 40-pin header. The board is detected from its revision code, which covers models up to the Pi 5, Pi 500 and Compute Module 5. **No physical Pi was available while this version was prepared, so no board has been confirmed with real lights yet** (see [Test report](TEST_REPORT.md)). |
| Relay board or SSRs | One channel per light string. Many cheap relay boards are "active low" (they switch ON when the pin is LOW); set `active_low_mode = True` for those. |
| Audio output | 3.5 mm jack (Pi 1–4 only; the Pi 5 has none), HDMI, USB sound card or I2S DAC. |
| microSD card | 8 GB or larger, flashed with Raspberry Pi OS using [Raspberry Pi Imager](https://www.raspberrypi.com/software/). |

### Operating system

| System | Status |
|--------|--------|
| Raspberry Pi OS / Debian 13 "trixie" (64-bit or 32-bit) | Supported. The installer was tested on clean Debian 13 systems (amd64, and arm64 under emulation with the Raspberry Pi package archive). |
| Raspberry Pi OS / Debian 12 "bookworm" (64-bit or 32-bit) | Supported. The installer was tested on a clean Debian 12 system (amd64). |
| Bullseye, Buster or older | Not supported. The installer stops and asks you to flash a current image. `--allow-unsupported` lets you try anyway. |
| Ubuntu, Arch, other distributions | Not supported or tested. Use `--allow-unsupported` at your own risk (Debian-based only). |

Use Raspberry Pi OS **Lite** for a dedicated light show. The desktop version
works too.

## Install

On the Pi, run:

```bash
sudo apt update
sudo apt install -y git
git clone <repository-url> lightshowpi
cd lightshowpi
sudo ./install.sh
```

The `<repository-url>` is wherever this modernized version is published (see
[Packaging](PACKAGING.md)). You can also unpack a release tarball:

```bash
tar xzf lightshowpi-<version>.tar.gz
cd lightshowpi-<version>
sudo ./install.sh
```

The installer:

1. Checks that the system is Raspberry Pi OS / Debian 12 or 13.
2. Installs Debian packages with apt: `python3-numpy`, `python3-alsaaudio`,
   `python3-mutagen`, `ffmpeg`, `alsa-utils`, plus `python3-lgpio` (GPIO, from
   the Raspberry Pi archive) and `python3-legacy-cgi` where they exist.
3. Creates a Python virtual environment in `lightshowpi/.venv` that uses those
   system packages. pip is used only for packages that apt doesn't provide.
4. Writes `/etc/profile.d/lightshowpi.sh` (sets `SYNCHRONIZED_LIGHTS_HOME`) and
   the command `/usr/local/bin/lightshowpi`.
5. Runs `lightshowpi doctor` to check the result.

It does **not** rename `/usr/bin/python`, edit `/etc/sudoers`, change your
graphics driver or compile anything. The old installer did all of these.

A full log is written to `logs/install.log`.

### Installer options

| Option | What it adds |
|--------|--------------|
| `--with-service` | A systemd service (`lightshowpi.service`) that starts the show at boot. |
| `--with-led` | LED strip support (BiblioPixel 3.4.46 plus serial/SPI packages). |
| `--with-wiringpi` | WiringPi 3.20 from the [official WiringPi GitHub releases](https://github.com/WiringPi/WiringPi/releases). The package's SHA-256 is checked before it is installed. Only needed for I/O expanders (MCP23017 etc.) and PiGlow. |
| `--with-fm` | 32-bit libraries for the bundled FM transmitter programs (Pi 1–4 only). |
| `--with-sms` | The legacy SMS/Twitter dependencies (unmaintained, untested). |
| `--all` | All `--with-*` options except `--with-service`. |
| `--skip-apt` | Don't install packages (they must already be installed). |
| `--allow-unsupported` | Continue on an OS that isn't Debian 12/13. |
| `--dry-run` | Show what would be done without changing anything. |

You can run the installer again at any time, for example to add an option.
It is safe to re-run.

## First run

```bash
# 1. Make your own settings file (defaults.cfg documents every option)
cp config/overrides.cfg.example config/overrides.cfg
nano config/overrides.cfg

# 2. Check everything
lightshowpi doctor

# 3. Test each light channel
lightshowpi flash          # or: lightshowpi test  (one channel at a time)

# 4. Play the sample songs
lightshowpi playlist
```

Open a new terminal (or log out and in) after installing. That's only needed
if you want to run the old `bin/` scripts by name; `lightshowpi` works
straight away.

`lightshowpi doctor` reports each item as `OK`, `INFO`, `WARN` or `FAIL`, with
a fix for every problem. It exits with status 1 if anything failed.

### Pins

`gpio_pins` uses **WiringPi numbers** by default, as LightShow Pi always has,
so existing configurations keep working. Run `lightshowpi pins` for a chart.
If you'd rather use the `GPIO17`-style numbers printed on most pinout
diagrams, set `pin_numbering = bcm`.

| WiringPi | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|----------|---|---|---|---|---|---|---|---|
| BCM GPIO | 17 | 18 | 27 | 22 | 23 | 24 | 25 | 4 |
| Header pin | 11 | 12 | 13 | 15 | 16 | 18 | 22 | 7 |

### GPIO back end

`gpio_backend = auto` (the default) picks:

* **lgpio** on any Raspberry Pi, including the Pi 5. It is installed from
  Raspberry Pi OS's own repository and needs no compiling.
* **wiringpi** only when you configure I/O expanders (`devices = ...`) or a
  PiGlow. These need `sudo ./install.sh --with-wiringpi`.
* **simulated** on a computer that isn't a Pi, so you can try things without
  hardware. Nothing is switched.

You can force one with `gpio_backend = lgpio | wiringpi | simulated`, or with
the environment variable `LIGHTSHOWPI_GPIO_BACKEND`.

### Audio output

Set `audio_out_card` in the `[lightshow]` section. Run `aplay -L` to list
devices.

| Output | Typical value |
|--------|---------------|
| Whatever the system uses | `default` |
| 3.5 mm jack (Pi 1–4) | `sysdefault:CARD=Headphones` |
| HDMI | `plughw:CARD=vc4hdmi0` (Pi 4/5: `vc4hdmi0` or `vc4hdmi1`) |
| USB sound card | `plughw:CARD=Device` (name from `aplay -L`) |

`lightshowpi doctor` opens the device the same way the show does, so a wrong
name shows up there, not halfway through a song.

## Configuring and running a show

All settings go in `config/overrides.cfg`. Anything there overrides
`config/defaults.cfg`, which documents every option; don't edit defaults.cfg,
because it is replaced when you upgrade.

### Your own music

```bash
mkdir -p ~/lightshowpi/music/christmas
# copy mp3 / wav / flac / ogg / m4a files into it, then:
lightshowpi playlist-generate ~/lightshowpi/music/christmas
```

Then set `playlist_path = $SYNCHRONIZED_LIGHTS_HOME/music/christmas/.playlist`
in `overrides.cfg`.

The first time a song plays, LightShow Pi analyses it and saves the result
next to it (`.songname.mp3.sync`). Later plays use that file and follow the
music more closely. To prepare all songs in advance, run
`sudo -E .venv/bin/python tools/sync_file_generator.py` and follow the prompts.

### Commands

| Command | Does |
|---------|------|
| `lightshowpi play FILE...` | Play one or more songs. |
| `lightshowpi playlist [FILE]` | Play the playlist once. |
| `lightshowpi loop [FILE]` | Play the playlist forever. |
| `lightshowpi start` / `stop` | Start/stop the show configured in `overrides.cfg` (the same as `bin/start_music_and_lights` / `bin/stop_music_and_lights`). |
| `lightshowpi on` / `off` / `flash` / `fade` / `test` | Light tests. |
| `lightshowpi web` | Start the web interface. |
| `lightshowpi doctor` | Check the installation. |
| `lightshowpi version` | Show the version, folder and Python. |

The old `bin/` scripts still work as before.

### Starting the show automatically

**systemd (recommended):**

```bash
sudo ./install.sh --with-service      # writes and enables lightshowpi.service
sudo systemctl start lightshowpi
sudo systemctl stop lightshowpi
journalctl -u lightshowpi -f          # live log
```

The service restarts the show if it crashes. A configuration or hardware
error (exit code 2) stops the service instead of restarting it over and over;
`journalctl -u lightshowpi` shows the message. The service was written and
checked in the test systems, but those had no systemd running, so starting it
at boot has not been tested.

**cron (like the original):** `crontab/synchronized_lights` has examples that
start the show at 6:30 pm and stop it at 10:15 pm. Add them with
`sudo crontab -e`.

### Running without sudo

The `bin/` scripts run Python through `sudo` as before, because GPIO and the
FM transmitter need it. On Raspberry Pi OS, `/dev/gpiochip*` normally belongs
to the `gpio` group, so its members should be able to use lgpio without root
(not yet confirmed on hardware for this version). To try running as your own
user, set:

```bash
export LIGHTSHOWPI_NO_SUDO=1
```

## Upgrading

```bash
cd ~/lightshowpi
git pull                 # or unpack the new release over the old folder
sudo ./install.sh        # same options as before
lightshowpi doctor
```

Your `config/overrides.cfg`, music and `.sync` files are kept.

### Upgrading from the original LightShow Pi

The old installer changed system files that this version no longer needs.
`uninstall.sh` tells you about them:

* `/usr/bin/python` may have been replaced by a link to Python 2 or 3.
* `/etc/sudoers` may contain an `env_keep += "SYNCHRONIZED_LIGHTS_HOME"` line.

Both are harmless for this version. Remove them only if you know nothing else
needs them. Your old `overrides.cfg` works unchanged. If it has
`use_gpu = True` and the optional GPU FFT module (`rpi_audio_levels`) isn't
installed, which is the normal case now, LightShow Pi logs a warning and uses
the CPU FFT.

## Uninstalling

```bash
sudo ./uninstall.sh --dry-run  # show what would be removed
sudo ./uninstall.sh            # remove the service, command, profile file and .venv
sudo ./uninstall.sh --purge    # ALSO delete the whole LightShow Pi folder
```

Without `--purge`, your music, playlists, `.sync` files and `overrides.cfg`
are kept. `--purge` deletes the LightShow Pi folder, including anything you
stored inside it, so copy out your `overrides.cfg` and music first. Debian packages installed
with apt are left in place; remove them with apt if you want to.

## Problems?

See [Troubleshooting](TROUBLESHOOTING.md) and run `lightshowpi doctor`.

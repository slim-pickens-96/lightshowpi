# Known limitations and remaining work

## Not verified on real hardware

All testing was done in containers/chroots and emulation, without a real Pi
(see [TEST_REPORT.md](TEST_REPORT.md)). In particular:

- **GPIO output through lgpio** has only been tested against a fake lgpio
  module and an arm64 chroot with no GPIO chip. The chip selection by label
  (`pinctrl-rp1` on Pi 5, `pinctrl-bcm*` on earlier boards) is based on
  documented kernel labels and still needs checking on real boards.
- **`lightshowpi on` / `off` persistence**: with lgpio, a pin's state after
  the process exits depends on the kernel GPIO character-device driver. Lights
  switched on with `lightshowpi on` might not stay on. This is unverified.
- **WiringPi back end** (`--with-wiringpi`) through ctypes, **I/O expanders**
  (MCP23017, MCP23S17, MCP23008, PCF8574, ...) and **PiGlow** are untested on
  hardware.
- **Audio** out of the jack, HDMI and USB, and **audio-in** mode, were only
  tested against the ALSA `null` device.
- **FM transmitter**: untested. It is blocked on the Pi 5/500/CM5 because the
  bundled programs can't work there.
- **LED strips** (BiblioPixel): the module imports on Python 3.11 and 3.13 on
  amd64. No strip was driven.
- **Running without sudo** through the `gpio` group is untested.
- **Starting at boot** with systemd is untested. The unit passes
  `systemd-analyze verify`.
- **Performance**: the numpy FFT replaces the GPU FFT. On a Pi 3 or newer this
  should be fine. On a Pi Zero/Zero 2 W you may need a larger `chunk_size` or
  fewer channels. This hasn't been measured.

## Dropped or reduced

- **GPU FFT (`rpi-audio-levels`)** can't be built on current Raspberry Pi OS
  because `/opt/vc` is gone. The code still uses it if it's already
  installed; otherwise it falls back to the CPU.
- **Arch Linux ARM installer** removed. `--allow-unsupported` lets you try
  other Debian-based systems at your own risk.
- **Raspberry Pi OS bullseye and older** are refused by the installer. They
  are end of life.
- The original **Model B Rev 1** board is only recognised through the
  revision table. Its different pin layout hasn't been tested.

## Old parts that still work but aren't maintained upstream

- **BiblioPixel** (LED strips) had its last release in 2020 and depends on
  `distutils`, which is provided by setuptools. Long term it should be
  replaced, for example with `rpi_ws281x` / Adafruit `neopixel` for WS281x.
- **SMS (Twilio / Google Voice) and Twitter** code is unchanged legacy code.
  Those APIs have changed a lot since this code was written, and these
  features aren't expected to work without an update.
- **Web UI (microweb)** uses the `cgi` module. On Python 3.13+ that comes from
  `legacy-cgi`. A move to a small WSGI app would remove that dependency.
- **`decoder.py`/`fileinfo.py`** are no longer needed. ffmpeg replaces them.

## Minor issues

- `lightshowpi doctor` can print a GPIO error twice, once through logging and
  once as its own message.
- Shellcheck still has `info`/`style` notes on the upstream `bin/vol` script.
- The first play of a new song uses preset statistics, so lower channels may
  stay off until the `.sync` cache exists. This is upstream behaviour. You can
  run `tools/sync_file_generator.py` to build the caches in advance.

## Suggested next steps

1. Test on real hardware: Pi 4 and Pi 5 (bookworm and trixie), with an
   8-channel relay board, running `lightshowpi doctor`, `lightshowpi test` and
   a full show.
2. Check lgpio pin state after `lightshowpi on`. If pins don't stay set, keep
   a small holder process running or document that `on` is a foreground
   command.
3. Measure CPU use on a Pi Zero 2 W.
4. Build a `.deb` (see [PACKAGING.md](PACKAGING.md)).
5. Replace BiblioPixel and update or remove the SMS/Twitter features.

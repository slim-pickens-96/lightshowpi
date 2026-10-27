#!/usr/bin/env python3
#
# Licensed under the BSD license.  See full license in LICENSE file.
# http://www.lightshowpi.org/
#
"""LightShow Pi doctor: check the installation and configuration.

Run it with:   lightshowpi doctor          (or: bin/lightshowpi doctor)
               lightshowpi doctor --config=my_show.cfg

Every check prints OK, WARN or FAIL with a suggested fix.  The exit status is
1 if any check failed, otherwise 0.
"""

import argparse
import glob
import os
import platform
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

OK, WARN, FAIL, INFO = "OK", "WARN", "FAIL", "INFO"
SUPPORTED_CODENAMES = ("bookworm", "trixie")


class Report(object):
    def __init__(self, stream=sys.stdout):
        self.results = []
        self.stream = stream

    def add(self, status, check, detail="", fix=""):
        self.results.append((status, check, detail, fix))
        line = "[%-4s] %s" % (status, check)
        if detail:
            line += ": " + detail
        print(line, file=self.stream)
        if fix and status in (WARN, FAIL):
            print("         fix: " + fix, file=self.stream)

    @property
    def failed(self):
        return any(r[0] == FAIL for r in self.results)


def read_os_release(path=None):
    path = path or os.environ.get("LIGHTSHOWPI_OS_RELEASE", "/etc/os-release")
    info = {}
    try:
        with open(path) as handle:
            for line in handle:
                if "=" in line:
                    key, value = line.rstrip("\n").split("=", 1)
                    info[key] = value.strip().strip('"')
    except (IOError, OSError):
        pass
    return info


def check_os(report):
    info = read_os_release()
    name = info.get("PRETTY_NAME", "unknown")
    codename = info.get("VERSION_CODENAME", "")
    like = (info.get("ID", "") + " " + info.get("ID_LIKE", "")).split()
    if codename in SUPPORTED_CODENAMES and ("debian" in like or "raspbian" in like):
        report.add(OK, "Operating system", "%s (%s)" % (name, platform.machine()))
    else:
        report.add(WARN, "Operating system", "%s is not a tested platform" % name,
                   "LightShow Pi is tested on Raspberry Pi OS / Debian 12 (bookworm) and 13 (trixie)")


def check_python(report):
    version = sys.version_info
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    detail = "%d.%d.%d at %s" % (version[0], version[1], version[2], sys.executable)
    if version < (3, 9):
        report.add(FAIL, "Python", detail + " (3.9 or newer is required)",
                   "Use Raspberry Pi OS Bookworm or Trixie")
    elif not in_venv:
        report.add(WARN, "Python", detail + " (not the LightShow Pi virtual environment)",
                   "Run commands through bin/lightshowpi, or re-run: sudo ./install.sh")
    else:
        report.add(OK, "Python", detail)


def check_module(report, module, label, fix, required=True):
    try:
        __import__(module)
    except Exception as error:  # ImportError or a broken native library
        report.add(FAIL if required else WARN, label, "cannot import %s (%s)" % (module, error), fix)
        return False
    report.add(OK, label)
    return True


def check_tools(report):
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool):
            report.add(OK, "Audio decoder (%s)" % tool, shutil.which(tool))
        else:
            report.add(FAIL, "Audio decoder (%s)" % tool, "not found", "sudo apt install ffmpeg")


def check_board(report):
    import Platform
    model = Platform.device_tree_model()
    code = Platform.revision_code()
    decoded = Platform.decode_revision(code)
    if decoded:
        report.add(OK, "Board", "%s (revision %s)" % (model or decoded[0], code))
        return True, decoded[1]
    if model.startswith("Raspberry Pi"):
        report.add(WARN, "Board", "%s, revision code %s is not recognised" % (model, code),
                   "Please report this board so it can be added to Platform.py")
        return True, None
    report.add(INFO, "Board", "not a Raspberry Pi - GPIO will be simulated")
    return False, None


def check_gpio(report, cm, is_pi):
    import gpio_backend
    hw = cm.hardware
    needs_wiringpi = bool(hw.devices) or bool(hw.piglow)
    requested = os.environ.get("LIGHTSHOWPI_GPIO_BACKEND") or hw.gpio_backend
    try:
        if requested in ("auto", "lgpio", "wiringpi", "simulated"):
            pass
        else:
            raise gpio_backend.GPIOBackendError("Unknown gpio_backend '%s'" % requested)
        if requested == "simulated" or (requested == "auto" and not is_pi):
            chosen = "simulated"
        elif requested == "auto":
            if needs_wiringpi:
                chosen = "wiringpi"
            elif gpio_backend.lgpio_available():
                chosen = "lgpio"
            elif gpio_backend.wiringpi_available():
                chosen = "wiringpi"
            else:
                chosen = None
        else:
            chosen = requested
    except gpio_backend.GPIOBackendError as error:
        report.add(FAIL, "GPIO back end", str(error), "Use auto, lgpio, wiringpi or simulated")
        return

    if chosen is None:
        report.add(FAIL, "GPIO back end", "no GPIO library installed",
                   "sudo apt install python3-lgpio, then sudo ./install.sh")
        return
    if chosen == "lgpio" and not gpio_backend.lgpio_available():
        report.add(FAIL, "GPIO back end", "lgpio selected but not installed", "sudo apt install python3-lgpio")
        return
    if chosen == "wiringpi" and not gpio_backend.wiringpi_available():
        report.add(FAIL, "GPIO back end",
                   "WiringPi is needed (I/O expanders / PiGlow / gpio_backend = wiringpi) but not installed",
                   "sudo ./install.sh --with-wiringpi")
        return
    if chosen == "simulated":
        report.add(WARN if is_pi else INFO, "GPIO back end", "simulated - lights will NOT be switched",
                   "Set gpio_backend = auto in the [hardware] section")
    else:
        report.add(OK, "GPIO back end", chosen)

    if chosen in ("lgpio", "wiringpi"):
        chips = sorted(glob.glob("/dev/gpiochip*"))
        if not chips:
            report.add(FAIL, "GPIO device", "no /dev/gpiochip* devices found",
                       "Check you are on Raspberry Pi OS with a current kernel")
        elif os.geteuid() != 0 and not all(os.access(c, os.R_OK | os.W_OK) for c in chips):
            report.add(WARN, "GPIO permissions", "this user cannot open %s" % chips[0],
                       "Run shows with sudo (the bin/ scripts do this) or: sudo adduser $USER gpio")
        else:
            report.add(OK, "GPIO device", ", ".join(chips))

    # pin validation
    numbering = hw.pin_numbering
    if numbering not in ("wiringpi", "bcm"):
        report.add(FAIL, "pin_numbering", "'%s' is not valid" % numbering, "Use wiringpi or bcm")
        return
    if not hw.gpio_pins:
        report.add(WARN, "gpio_pins", "no channels are defined",
                   "Set gpio_pins in the [hardware] section of overrides.cfg")
        return
    bad = []
    for pin in hw.gpio_pins:
        if hw.devices and pin >= 64:
            continue  # expander pins
        if numbering == "wiringpi" and pin not in gpio_backend.WIRINGPI_TO_BCM:
            bad.append(pin)
        if numbering == "bcm" and not 0 <= pin <= 27:
            bad.append(pin)
    if len(set(hw.gpio_pins)) != len(hw.gpio_pins):
        report.add(FAIL, "gpio_pins", "the same pin is listed more than once: %s" % hw.gpio_pins,
                   "Each channel needs its own pin")
    elif bad:
        report.add(FAIL, "gpio_pins", "invalid %s pin number(s): %s" % (numbering, bad),
                   "WiringPi pins are 0-31, BCM pins 0-27 (run: lightshowpi pins)")
    else:
        mapped = ""
        if numbering == "wiringpi" and not hw.devices:
            mapped = " (BCM %s)" % ",".join(str(gpio_backend.WIRINGPI_TO_BCM[p]) for p in hw.gpio_pins)
        report.add(OK, "gpio_pins", "%d channel(s), %s numbering %s%s"
                   % (len(hw.gpio_pins), numbering, hw.gpio_pins, mapped))
    if len(hw.pin_modes) != len(hw.gpio_pins):
        report.add(FAIL, "pin_modes", "%d pin_modes for %d gpio_pins" % (len(hw.pin_modes), len(hw.gpio_pins)),
                   "Give one mode for all pins, or one per pin")
    elif any(m not in ("onoff", "pwm") for m in hw.pin_modes):
        report.add(FAIL, "pin_modes", "only onoff and pwm are valid: %s" % hw.pin_modes, "")


def check_audio(report, cm):
    try:
        import alsaaudio
    except Exception:
        return
    try:
        cards = alsaaudio.cards()
    except Exception:
        cards = []
    report.add(INFO, "Sound cards", ", ".join(cards) if cards else "none found")
    if cm.fm.enabled:
        return
    if cm.lightshow.use_fifo:
        report.add(INFO, "Audio output", "use_fifo = True (audio goes to /tmp/audio)")
        return
    device = cm.lightshow.audio_out_card
    try:
        import alsa_compat
        # open it the way the show does (16-bit stereo, 44.1 kHz) so an old
        # pyalsaaudio or an unusable device shows up here, not mid-show
        with quiet_stderr():
            pcm = alsa_compat.open_pcm(alsaaudio.PCM_PLAYBACK, alsaaudio.PCM_NONBLOCK, device,
                                       2, 44100, alsaaudio.PCM_FORMAT_S16_LE, 2048)
            pcm.close()
        report.add(OK, "Audio output", "audio_out_card = %s opened successfully" % device)
    except Exception as error:
        report.add(FAIL, "Audio output", "cannot open audio_out_card = %s (%s)" % (device, error),
                   "List devices with: aplay -L   then set audio_out_card in [lightshow] "
                   "(e.g. default, sysdefault:CARD=Headphones, plughw:CARD=vc4hdmi0)")


class quiet_stderr(object):
    """Hide libasound's own "ALSA lib ..." messages; the doctor reports the error."""

    def __enter__(self):
        sys.stderr.flush()
        self.saved = os.dup(2)
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 2)
        os.close(devnull)

    def __exit__(self, *exc):
        os.dup2(self.saved, 2)
        os.close(self.saved)
        return False


def elf_is_32bit_arm(path):
    try:
        with open(path, "rb") as handle:
            header = handle.read(20)
    except (IOError, OSError):
        return False
    return header[:4] == b"\x7fELF" and header[4] == 1 and struct.unpack("<H", header[18:20])[0] == 40


def check_fm(report, cm, pi_major, home):
    if not cm.fm.enabled:
        report.add(INFO, "FM transmitter", "disabled")
        return
    if pi_major is not None and pi_major >= 5:
        report.add(FAIL, "FM transmitter", "not supported on the Raspberry Pi 5 or later",
                   "Set fm = False in the [fm] section and use an audio output")
        return
    binary = os.path.join(home, "bin", "pi_fm_rds" if pi_major in (2, 3, 4) else "pifm")
    if not os.path.exists(binary):
        report.add(FAIL, "FM transmitter", "%s is missing" % binary, "")
        return
    if elf_is_32bit_arm(binary) and platform.machine() == "aarch64":
        loader = os.path.exists("/lib/ld-linux-armhf.so.3")
        sndfile = bool(glob.glob("/usr/lib/arm-linux-gnueabihf/libsndfile.so.1*"))
        if not (loader and sndfile):
            report.add(FAIL, "FM transmitter",
                       "the FM programs are 32-bit and this OS is 64-bit; 32-bit libraries are missing",
                       "sudo ./install.sh --with-fm   (adds the armhf libc6 and libsndfile1)")
            return
    report.add(OK, "FM transmitter", "%s, %s MHz" % (os.path.basename(binary), cm.fm.frequency))


def check_playlist(report, cm):
    mode = cm.lightshow.mode
    if mode != "playlist":
        report.add(INFO, "Mode", mode)
        return
    path = cm.lightshow.playlist_path
    if not os.path.isfile(path):
        report.add(WARN, "Playlist", "%s not found" % path,
                   "Create one with: lightshowpi playlist-generate /path/to/music")
        return
    missing = 0
    total = 0
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            total += 1
            parts = line.split("\t")
            song = parts[1] if len(parts) > 1 else parts[0]
            song = song.replace("$SYNCHRONIZED_LIGHTS_HOME", cm.home_dir)
            if not os.path.isfile(song):
                missing += 1
    if total == 0:
        report.add(WARN, "Playlist", "%s is empty" % path, "")
    elif missing:
        report.add(WARN, "Playlist", "%d of %d songs in %s were not found" % (missing, total, path),
                   "Regenerate it with: lightshowpi playlist-generate /path/to/music")
    else:
        report.add(OK, "Playlist", "%d song(s) in %s" % (total, path))


def check_optional(report, cm):
    if cm.audio_processing.use_gpu:
        import fft
        if fft.AudioLevels is None:
            report.add(WARN, "GPU FFT", "use_gpu = True but rpi_audio_levels is not installed (CPU will be used)",
                       "Set use_gpu = False in [audio_processing]")
        else:
            report.add(OK, "GPU FFT", "rpi_audio_levels available")
    if cm.configs.led:
        check_module(report, "bibliopixel", "LED strip support (BiblioPixel)",
                     "sudo ./install.sh --with-led")
    if sys.version_info >= (3, 13):
        check_module(report, "cgitb", "Web interface (legacy-cgi)",
                     "sudo ./install.sh (installs legacy-cgi)", required=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check a LightShow Pi installation.")
    parser.add_argument("--config", default=None,
                        help="configuration file to check instead of overrides.cfg")
    args = parser.parse_args(argv)

    report = Report()
    print("LightShow Pi doctor\n")
    check_os(report)
    check_python(report)
    core_ok = True
    core_ok &= check_module(report, "numpy", "numpy", "sudo apt install python3-numpy")
    core_ok &= check_module(report, "alsaaudio", "pyalsaaudio", "sudo apt install python3-alsaaudio")
    core_ok &= check_module(report, "mutagen", "mutagen", "sudo apt install python3-mutagen")
    check_tools(report)
    is_pi, pi_major = check_board(report)

    try:
        import configuration_manager
        cm = configuration_manager.Configuration(param_config=args.config)
    except SystemExit:
        report.add(FAIL, "Configuration", "could not be loaded (see message above)", "")
        cm = None
    except Exception as error:
        report.add(FAIL, "Configuration", "%s: %s" % (type(error).__name__, error),
                   "Fix the line mentioned above in config/overrides.cfg")
        cm = None

    if cm is not None:
        source = args.config or ("overrides.cfg" if os.path.isfile(
            os.path.join(cm.config_dir, "overrides.cfg")) else "defaults.cfg only")
        report.add(OK, "Configuration", "loaded (%s)" % source)
        check_gpio(report, cm, is_pi)
        check_audio(report, cm)
        check_fm(report, cm, pi_major, cm.home_dir)
        check_playlist(report, cm)
        check_optional(report, cm)

    print()
    if report.failed:
        print("Some checks FAILED. Fix the items marked FAIL above, then run the doctor again.")
        return 1
    print("All required checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
#
# Licensed under the BSD license.  See full license in LICENSE file.
# http://www.lightshowpi.org/
#
"""GPIO back ends for LightShow Pi.

hardware_controller.py historically called a custom WiringPi binding
(``wiringpipy``) through functions with a ``PY`` suffix.  This module keeps
that exact call interface but lets the program run on top of one of:

* ``lgpio``     - the GPIO library shipped with current Raspberry Pi OS.
                  Works on every Raspberry Pi model, including the Pi 5.
* ``wiringpi``  - the legacy WiringPi binding (``wiringpipy`` or the
                  ``wiringpi`` Python module).  Still required for I/O
                  expanders (MCP23xxx, PCF8574, 74HC595) and PiGlow.
* ``simulated`` - no hardware; records pin states.  Used on non-Pi
                  computers and by the automated tests.

Pin numbers in the configuration keep their original meaning (WiringPi
numbering) unless ``pin_numbering = bcm`` is set in the [hardware] section.
"""

import logging
import os

log = logging.getLogger(__name__)

# WiringPi pin number -> BCM GPIO number for all 40-pin boards (and 26-pin
# revision 2 boards).  Source: the WiringPi pin map (``gpio readall``).
WIRINGPI_TO_BCM = {
    0: 17, 1: 18, 2: 27, 3: 22, 4: 23, 5: 24, 6: 25, 7: 4,
    8: 2, 9: 3, 10: 8, 11: 7, 12: 10, 13: 9, 14: 11, 15: 14,
    16: 15, 17: 28, 18: 29, 19: 30, 20: 31, 21: 5, 22: 6, 23: 13,
    24: 19, 25: 26, 26: 12, 27: 16, 28: 20, 29: 21, 30: 0, 31: 1,
}

# Revision 1 Model B boards (2012) differ on three pins.
WIRINGPI_TO_BCM_REV1 = dict(WIRINGPI_TO_BCM)
WIRINGPI_TO_BCM_REV1.update({2: 21, 8: 0, 9: 1})

BACKENDS = ("auto", "lgpio", "wiringpi", "simulated")


class GPIOBackendError(RuntimeError):
    """Raised with a user-readable explanation when GPIO can't be used."""


def wiringpi_to_bcm(pin, revision=2):
    table = WIRINGPI_TO_BCM_REV1 if revision == 1 else WIRINGPI_TO_BCM
    try:
        return table[int(pin)]
    except KeyError:
        raise GPIOBackendError(
            "WiringPi pin %s does not exist on the Raspberry Pi header. "
            "Valid WiringPi pins are 0-31 (pins 64 and above are only valid "
            "with an I/O expander, which needs gpio_backend = wiringpi)." % pin)


class SimulatedGPIO(object):
    """Hardware-free back end.  Keeps a record of every pin's state."""

    name = "simulated"

    # Keep at most this many history entries in memory
    MAX_HISTORY = 100000

    def __init__(self):
        self.modes = {}
        self.values = {}
        self.pwm_range = {}
        self.history = []
        self.devices = []
        self.setup_called = False
        # Optional trace file (used by the end-to-end tests): one
        # "<event> <pin> <value>" line per GPIO call.
        self.trace = None
        trace_path = os.environ.get("LIGHTSHOWPI_SIM_TRACE")
        if trace_path:
            import atexit
            self.trace = open(trace_path, "a")
            atexit.register(self.close)

    def _record(self, event, pin, value):
        if len(self.history) < self.MAX_HISTORY:
            self.history.append((event, pin, value))
        if self.trace is not None:
            self.trace.write("%s %s %s\n" % (event, pin, value))

    def wiringPiSetupPY(self):
        self.setup_called = True
        return 0

    def pinModePY(self, pin, mode):
        self.modes[pin] = mode
        self._record("mode", pin, mode)

    def digitalWritePY(self, pin, value):
        self.values[pin] = int(value)
        self._record("write", pin, int(value))

    def softPwmCreatePY(self, pin, initial, pwm_range):
        self.modes[pin] = "pwm"
        self.pwm_range[pin] = pwm_range
        self.values[pin] = initial
        self._record("pwm_create", pin, pwm_range)
        return 0

    def softPwmWritePY(self, pin, value):
        self.values[pin] = int(value)
        self._record("pwm", pin, int(value))

    def analogWritePY(self, pin, value):
        self.values[pin] = int(value)
        self._record("analog", pin, int(value))

    def _device(self, kind, *args):
        self.devices.append((kind,) + tuple(args))
        return True

    def mcp23008SetupPY(self, *args):
        return self._device("mcp23008", *args)

    def mcp23s08SetupPY(self, *args):
        return self._device("mcp23s08", *args)

    def mcp23016SetupPY(self, *args):
        return self._device("mcp23016", *args)

    def mcp23017SetupPY(self, *args):
        return self._device("mcp23017", *args)

    def mcp23s17SetupPY(self, *args):
        return self._device("mcp23s17", *args)

    def sr595SetupPY(self, *args):
        return self._device("sr595", *args)

    def pcf8574SetupPY(self, *args):
        return self._device("pcf8574", *args)

    def close(self):
        if self.trace is not None:
            try:
                self.trace.close()
            except Exception:
                pass
            self.trace = None


class LgpioGPIO(object):
    """GPIO through lgpio (/dev/gpiochipN).  Works on Pi 1-5."""

    name = "lgpio"

    # Labels of the gpiochip that drives the 40-pin header on each SoC.
    HEADER_CHIP_LABELS = ("pinctrl-rp1", "pinctrl-bcm2712", "pinctrl-bcm2711",
                          "pinctrl-bcm2835", "raspberrypi-exp-gpio")

    def __init__(self, lgpio_module=None, numbering="wiringpi", revision=2):
        if lgpio_module is None:
            import lgpio as lgpio_module
        self.lg = lgpio_module
        self.numbering = numbering
        self.revision = revision
        self.handle = None
        self.claimed = {}
        self.pwm_range = {}

    def _open_chip(self):
        candidates = []
        for chip in range(0, 16):
            if os.path.exists("/dev/gpiochip%d" % chip) or chip in (0, 4):
                candidates.append(chip)
        first_ok = None
        for chip in candidates:
            try:
                handle = self.lg.gpiochip_open(chip)
            except Exception:
                continue
            try:
                info = self.lg.gpiochip_info(handle)
                label = str(info[2]) if len(info) > 2 else ""
            except Exception:
                label = ""
            if label in self.HEADER_CHIP_LABELS and label != "raspberrypi-exp-gpio":
                if first_ok is not None:
                    self.lg.gpiochip_close(first_ok)
                return handle
            if first_ok is None:
                first_ok = handle
            else:
                self.lg.gpiochip_close(handle)
        if first_ok is not None:
            return first_ok
        if not any(os.path.exists("/dev/gpiochip%d" % chip) for chip in range(0, 16)):
            raise GPIOBackendError(
                "No GPIO chip found (/dev/gpiochip* does not exist). Check that this is "
                "a Raspberry Pi running a current Raspberry Pi OS kernel.")
        raise GPIOBackendError(
            "Could not open a GPIO chip (/dev/gpiochip*). Run LightShow Pi with "
            "sudo, or add your user to the 'gpio' group.")

    def _bcm(self, pin):
        if self.numbering == "bcm":
            return int(pin)
        return wiringpi_to_bcm(pin, self.revision)

    def wiringPiSetupPY(self):
        if self.handle is None:
            self.handle = self._open_chip()
        return 0

    def _claim(self, bcm, output):
        if bcm in self.claimed:
            try:
                self.lg.gpio_free(self.handle, bcm)
            except Exception:
                pass
        if output:
            self.lg.gpio_claim_output(self.handle, bcm, 0)
        else:
            self.lg.gpio_claim_input(self.handle, bcm)
        self.claimed[bcm] = "out" if output else "in"

    def pinModePY(self, pin, mode):
        self.wiringPiSetupPY()
        self._claim(self._bcm(pin), int(mode) == 1)

    def digitalWritePY(self, pin, value):
        bcm = self._bcm(pin)
        if self.claimed.get(bcm) != "out":
            self._claim(bcm, True)
        self.lg.gpio_write(self.handle, bcm, 1 if int(value) else 0)

    def softPwmCreatePY(self, pin, initial, pwm_range):
        self.wiringPiSetupPY()
        bcm = self._bcm(pin)
        self._claim(bcm, True)
        self.pwm_range[bcm] = max(1, int(pwm_range))
        self.softPwmWritePY(pin, initial)
        return 0

    def softPwmWritePY(self, pin, value):
        bcm = self._bcm(pin)
        pwm_range = self.pwm_range.get(bcm, 100)
        # WiringPi softPwm uses 100us steps, so the PWM period is
        # range * 100us.  Keep the same frequency so lights behave the same.
        frequency = max(1, int(round(10000.0 / pwm_range)))
        duty = max(0.0, min(100.0, 100.0 * float(value) / pwm_range))
        self.lg.tx_pwm(self.handle, bcm, frequency, duty)

    def analogWritePY(self, pin, value):
        raise GPIOBackendError(
            "PiGlow output needs the WiringPi back end. Install WiringPi "
            "(sudo ./install.sh --with-wiringpi) and set gpio_backend = wiringpi.")

    def _no_expanders(self, *args):
        raise GPIOBackendError(
            "I/O expander chips (MCP23xxx, PCF8574, 74HC595) need the WiringPi "
            "back end. Install WiringPi (sudo ./install.sh --with-wiringpi) and set "
            "gpio_backend = wiringpi in the [hardware] section of overrides.cfg.")

    mcp23008SetupPY = mcp23s08SetupPY = mcp23016SetupPY = _no_expanders
    mcp23017SetupPY = mcp23s17SetupPY = sr595SetupPY = pcf8574SetupPY = _no_expanders

    def close(self):
        if self.handle is not None:
            for bcm in list(self.claimed):
                try:
                    self.lg.gpio_free(self.handle, bcm)
                except Exception:
                    pass
            try:
                self.lg.gpiochip_close(self.handle)
            except Exception:
                pass
            self.handle = None
            self.claimed = {}


class WiringPiLibrary(object):
    """Calls the WiringPi C library (libwiringPi.so) directly with ctypes.

    Installed by ``install.sh --with-wiringpi`` from the official WiringPi
    3.x releases (https://github.com/WiringPi/WiringPi).  No compiled Python
    binding is needed.  Exposes the same *PY function names as wiringpipy."""

    FUNCTIONS = ("wiringPiSetup", "wiringPiSetupGpio", "pinMode", "digitalWrite",
                 "analogWrite", "softPwmCreate", "softPwmWrite", "mcp23008Setup",
                 "mcp23s08Setup", "mcp23016Setup", "mcp23017Setup", "mcp23s17Setup",
                 "sr595Setup", "pcf8574Setup")

    def __init__(self, library=None):
        import ctypes
        import ctypes.util
        if library is None:
            path = ctypes.util.find_library("wiringPi") or "libwiringPi.so"
            library = ctypes.CDLL(path)
        self.lib = library

    def _fn(self, name):
        return getattr(self.lib, name)

    def __getattr__(self, attr):
        if attr.endswith("PY") and attr[:-2] in self.FUNCTIONS:
            fn = self._fn(attr[:-2])
            return lambda *args: fn(*[int(a) for a in args])
        raise AttributeError(attr)


def load_wiringpi_module():
    """Return a WiringPi binding: wiringpipy, libwiringPi via ctypes, or wiringpi."""
    try:
        import wiringpipy
        return wiringpipy
    except ImportError:
        pass
    try:
        return WiringPiLibrary()
    except OSError:
        pass
    import wiringpi
    return wiringpi


class WiringPiGPIO(object):
    """Adapter for WiringPi.

    Accepts the LightShow Pi ``wiringpipy`` module or :class:`WiringPiLibrary`
    (functions end in ``PY``) or the PyPI ``wiringpi`` module (no suffix)."""

    name = "wiringpi"

    def __init__(self, module=None, numbering="wiringpi"):
        self.numbering = numbering
        if module is None:
            module = load_wiringpi_module()
        self.module = module
        self.suffix = "PY" if (isinstance(module, WiringPiLibrary)
                               or hasattr(module, "wiringPiSetupPY")) else ""

    def _call(self, name, *args):
        return getattr(self.module, name + self.suffix)(*args)

    def wiringPiSetupPY(self):
        if self.numbering == "bcm":
            return self._call("wiringPiSetupGpio")
        return self._call("wiringPiSetup")

    def __getattr__(self, attr):
        if attr.endswith("PY"):
            base = attr[:-2]
            return lambda *args: self._call(base, *args)
        raise AttributeError(attr)

    def close(self):
        pass


def _import_ok(name):
    try:
        __import__(name)
        return True
    except Exception:
        return False


def wiringpi_available():
    if _import_ok("wiringpipy"):
        return True
    import ctypes.util
    if ctypes.util.find_library("wiringPi"):
        return True
    return _import_ok("wiringpi")


def lgpio_available():
    return _import_ok("lgpio")


def select_backend(requested="auto", is_pi=False, needs_wiringpi=False,
                   numbering="wiringpi", revision=2):
    """Create the GPIO back end.

    :param requested: auto, lgpio, wiringpi or simulated (may be overridden
                      by the LIGHTSHOWPI_GPIO_BACKEND environment variable)
    :param is_pi: True when running on a Raspberry Pi
    :param needs_wiringpi: True when expanders or PiGlow are configured
    """
    requested = (os.environ.get("LIGHTSHOWPI_GPIO_BACKEND") or requested or "auto").strip().lower()
    numbering = (numbering or "wiringpi").strip().lower()
    if requested not in BACKENDS:
        raise GPIOBackendError("Unknown gpio_backend '%s'. Use one of: %s"
                               % (requested, ", ".join(BACKENDS)))
    if numbering not in ("wiringpi", "bcm"):
        raise GPIOBackendError("Unknown pin_numbering '%s'. Use wiringpi or bcm." % numbering)

    if requested == "simulated":
        return SimulatedGPIO()

    if requested == "auto":
        if not is_pi:
            log.warning("This computer is not a Raspberry Pi: using SIMULATED GPIO. "
                        "No lights will be switched.")
            return SimulatedGPIO()
        if needs_wiringpi:
            requested = "wiringpi"
        elif lgpio_available():
            requested = "lgpio"
        elif wiringpi_available():
            requested = "wiringpi"
        else:
            raise GPIOBackendError(
                "No GPIO library found. Install it with:  sudo apt install python3-lgpio  "
                "(then re-run sudo ./install.sh so the LightShow Pi environment can see it).")

    if requested == "lgpio":
        if not lgpio_available():
            raise GPIOBackendError(
                "gpio_backend = lgpio but the lgpio Python module is not installed. "
                "Fix: sudo apt install python3-lgpio")
        return LgpioGPIO(numbering=numbering, revision=revision)

    if requested == "wiringpi":
        if not wiringpi_available():
            raise GPIOBackendError(
                "The WiringPi back end was selected (needed for I/O expanders and "
                "PiGlow) but WiringPi is not installed. Fix: sudo ./install.sh --with-wiringpi")
        return WiringPiGPIO(numbering=numbering)

    raise GPIOBackendError("Could not select a GPIO back end")

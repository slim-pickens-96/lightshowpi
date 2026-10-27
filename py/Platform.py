# Copyright (c) 2014 Adafruit Industries
# Author: Tony DiCola

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# Modernized for LightShow Pi: board detection now decodes the Raspberry Pi
# revision code bit-fields instead of matching a fixed list, so new boards
# (Pi 400, Pi 5, Pi 500, CM4/CM5, Zero 2 W ...) are recognised.  The public
# functions (platform_detect, pi_version, pi_revision, get_model) keep their
# original signatures.

import os
import platform
import re

# Platform identification constants.
UNKNOWN = 0
RASPBERRY_PI = 1
BEAGLEBONE_BLACK = 2
MINNOWBOARD = 3

# Allow tests (and the doctor tool) to point at fake files.
CPUINFO_PATH = os.environ.get("LIGHTSHOWPI_CPUINFO", "/proc/cpuinfo")
DT_MODEL_PATH = os.environ.get("LIGHTSHOWPI_DT_MODEL", "/proc/device-tree/model")

# New-style revision code "type" field -> (model name, major version)
# https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#raspberry-pi-revision-codes
NEW_STYLE_TYPES = {
    0x00: ("Model A", 1),
    0x01: ("Model B", 1),
    0x02: ("Model A+", 1),
    0x03: ("Model B+", 1),
    0x04: ("Pi 2 Model B", 2),
    0x05: ("Alpha", 1),
    0x06: ("Compute Module 1", 1),
    0x08: ("Pi 3 Model B", 3),
    0x09: ("Pi Zero", 1),
    0x0a: ("Compute Module 3", 3),
    0x0c: ("Pi Zero W", 1),
    0x0d: ("Pi 3 Model B+", 3),
    0x0e: ("Pi 3 Model A+", 3),
    0x10: ("Compute Module 3+", 3),
    0x11: ("Pi 4 Model B", 4),
    0x12: ("Pi Zero 2 W", 3),
    0x13: ("Pi 400", 4),
    0x14: ("Compute Module 4", 4),
    0x15: ("Compute Module 4S", 4),
    0x17: ("Pi 5", 5),
    0x18: ("Compute Module 5", 5),
    0x19: ("Pi 500", 5),
    0x1a: ("Compute Module 5 Lite", 5),
}

# Old-style (pre-2014) revision codes -> model name.  All are Pi 1 boards.
OLD_STYLE = {}
for _code in ("0002", "0003", "0004", "0005", "0006", "000d", "000e", "000f"):
    OLD_STYLE[_code] = "Model B"
for _code in ("0007", "0008", "0009"):
    OLD_STYLE[_code] = "Model A"
for _code in ("0010", "0013"):
    OLD_STYLE[_code] = "Model B+"
for _code in ("0012", "0015"):
    OLD_STYLE[_code] = "Model A+"
for _code in ("0011", "0014"):
    OLD_STYLE[_code] = "Compute Module 1"

# 26-pin header boards
HEADER26_MODELS = ("Model A", "Model B")


def _read(path):
    try:
        with open(path, "r", errors="replace") as infile:
            return infile.read()
    except (IOError, OSError):
        return ""


def revision_code():
    """Return the board revision code as a lowercase hex string, or None."""
    cpuinfo = _read(CPUINFO_PATH)
    match = re.search(r"^Revision\s*:\s*([0-9a-fA-F]+)\s*$", cpuinfo, flags=re.MULTILINE)
    if not match:
        return None
    return match.group(1).lower()


def decode_revision(code):
    """Decode a revision code string into (model name, major version).

    Returns None if the code is not a known Raspberry Pi revision.
    """
    if not code:
        return None
    try:
        value = int(code, 16)
    except ValueError:
        return None

    if value & (1 << 23):
        # New-style revision code
        board_type = (value >> 4) & 0xff
        if board_type in NEW_STYLE_TYPES:
            return NEW_STYLE_TYPES[board_type]
        return ("Unknown Raspberry Pi (type 0x%02x)" % board_type, None)

    # Old-style: last 4 hex digits (leading 1000 means over-volted)
    short = code[-4:]
    if short in OLD_STYLE:
        return (OLD_STYLE[short], 1)
    return None


def device_tree_model():
    """Return the device-tree model string, e.g. 'Raspberry Pi 5 Model B Rev 1.0'."""
    return _read(DT_MODEL_PATH).strip("\x00\n ")


def is_raspberry_pi():
    if device_tree_model().startswith("Raspberry Pi"):
        return True
    return decode_revision(revision_code()) is not None


def platform_detect():
    """Detect if running on the Raspberry Pi or Beaglebone Black and return the
    platform type.  Will return RASPBERRY_PI, BEAGLEBONE_BLACK, or UNKNOWN."""
    if is_raspberry_pi():
        return RASPBERRY_PI

    # Handle Beaglebone Black
    plat = platform.platform().lower()
    if plat.find('armv7l-with-debian') > -1:
        return BEAGLEBONE_BLACK
    elif plat.find('armv7l-with-ubuntu') > -1:
        return BEAGLEBONE_BLACK
    elif plat.find('armv7l-with-glibc2.4') > -1:
        return BEAGLEBONE_BLACK

    # Handle Minnowboard
    # Assumption is that mraa is installed
    try:
        import mraa

        if mraa.getPlatformName() == 'MinnowBoard MAX':
            return MINNOWBOARD
    except ImportError:
        pass

    # Couldn't figure out the platform, just return unknown.
    return UNKNOWN


def pi_revision():
    """Detect the revision number of a Raspberry Pi, useful for changing
    functionality like default I2C bus based on revision.

    Returns 1 for the earliest Model B boards, otherwise 2."""
    code = revision_code()
    if code is None:
        raise RuntimeError('Could not determine Raspberry Pi revision.')
    if code[-4:] in ('0000', '0002', '0003'):
        return 1
    return 2


def pi_version():
    """Return the major Raspberry Pi version (1, 2, 3, 4 or 5), or None if
    this is not a Raspberry Pi (or the board is too new to be known).

    Note: the Pi Zero 2 W reports 3 (same SoC family as the Pi 3).
    """
    decoded = decode_revision(revision_code())
    if decoded is None:
        return None
    return decoded[1]


header40 = """A+, B+ and Pi2 B, and Zero models
                         +=========+
         POWER  3.3VDC   | 1 . . 2 |  5.0VDC   POWER
      I2C SDA1  GPIO  8  | 3 . . 4 |  5.0VDC   POWER
      I2C SCL1  GPIO  9  | 5 . . 6 |  GROUND
      CPCLK0    GPIO  7  | 7 . . 8 |  GPIO 15  TxD UART
                GROUND   | 9 . . 10|  GPIO 16  RxD UART
                GPIO  0  |11 . . 12|  GPIO  1  PCM_CLK/PWM0
                GPIO  2  |13 . . 14|  GROUND
                GPIO  3  |15 . . 16|  GPIO  4
         POWER  3.3VDC   |17 . . 18|  GPIO  5
      SPI MOSI  GPIO 12  |19 .   20|  GROUND
      SPI MISO  GPIO 13  |21 . . 22|  GPIO  6
      SPI SCLK  GPIO 14  |23 . . 24|  GPIO 10  CE0 SPI
                GROUND   |25 . . 26|  GPIO 11  CE1 SPI
 I2C ID EEPROM  SDA0     |27 . . 28|  SCL0     I2C ID EEPROM
        GPCLK1  GPIO 21  |29 . . 30|  GROUND
        CPCLK2  GPIO 22  |31 . . 32|  GPIO 26  PWM0
          PWM1  GPIO 23  |33 . . 34|  GROUND
   PCM_FS/PWM1  GPIO 24  |35 . . 36|  GPIO 27
                GPIO 25  |37 . . 38|  GPIO 28  PCM_DIN
                GROUND   |39 . . 40|  GPIO 29  PCM_DOUT
                         +=========+"""

header26 = """A and B models
                         +=========+
         POWER  3.3VDC   | 1 . . 2 |  5.0VDC   POWER
      I2C SDA0  GPIO  8  | 3 . . 4 |  DNC  
      I2C SCL0  GPIO  9  | 5 . . 6 |  GROUND
                GPIO  7  | 7 . . 8 |  GPIO 15  TxD UART
                DNC      | 9 . . 10|  GPIO 16  RxD UART
                GPIO  0  |11 . . 12|  GPIO  1  PCM_CLK/PWM0
                GPIO  2  |13 . . 14|  DNC
                GPIO  3  |15 . . 16|  GPIO  4
                DNC      |17 . . 18|  GPIO  5
      SPI MOSI  GPIO 12  |19 .   20|  DNC
      SPI MISO  GPIO 13  |21 . . 22|  GPIO  6
      SPI SCLK  GPIO 14  |23 . . 24|  GPIO 10  CE0 SPI
                DNC      |25 . . 26|  GPIO 11  CE1 SPI
                         +=========+"""




def get_model():
    """Return (model name, ascii header diagram) for this board."""
    decoded = decode_revision(revision_code())
    if decoded is None:
        dt_model = device_tree_model()
        if dt_model.startswith("Raspberry Pi"):
            return dt_model, header40
        raise RuntimeError('Could not determine Raspberry Pi model.')
    model = decoded[0]
    if model in HEADER26_MODELS:
        return model, header26
    return model, header40

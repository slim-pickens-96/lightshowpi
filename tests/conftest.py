"""Shared test setup.

The LightShow Pi modules read SYNCHRONIZED_LIGHTS_HOME when they are
imported, so the tests build a throw-away "home" folder (a copy of config/
plus empty logs/ and music/) and point the variable at it before any
LightShow Pi module is imported.  Nothing in the real checkout is modified.
"""
import os
import shutil
import sys
import tempfile
import wave
import math
import struct

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY_DIR = os.path.join(REPO, "py")

TEST_HOME = tempfile.mkdtemp(prefix="lsp-test-home-")
shutil.copytree(os.path.join(REPO, "config"), os.path.join(TEST_HOME, "config"))
for sub in ("logs", "music"):
    os.makedirs(os.path.join(TEST_HOME, sub), exist_ok=True)
# keep the folder layout the bin/ scripts expect
os.symlink(PY_DIR, os.path.join(TEST_HOME, "py"))
os.symlink(os.path.join(REPO, "bin"), os.path.join(TEST_HOME, "bin"))
os.symlink(os.path.join(REPO, "tools"), os.path.join(TEST_HOME, "tools"))

os.environ["SYNCHRONIZED_LIGHTS_HOME"] = TEST_HOME
os.environ["LIGHTSHOWPI_GPIO_BACKEND"] = "simulated"
# never detect the test machine as a Raspberry Pi
os.environ["LIGHTSHOWPI_CPUINFO"] = os.path.join(TEST_HOME, "no-cpuinfo")
os.environ["LIGHTSHOWPI_DT_MODEL"] = os.path.join(TEST_HOME, "no-model")

if PY_DIR not in sys.path:
    sys.path.insert(0, PY_DIR)


def write_tone(path, seconds=2.0, freq=440.0, rate=44100, channels=2, amplitude=0.6):
    """Write a 16-bit PCM sine-wave WAV file."""
    frames = int(seconds * rate)
    with wave.open(path, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        data = bytearray()
        for i in range(frames):
            value = int(amplitude * 32767 * math.sin(2 * math.pi * freq * i / rate))
            data += struct.pack("<h", value) * channels
        w.writeframes(bytes(data))
    return path


@pytest.fixture
def test_home():
    return TEST_HOME


@pytest.fixture
def write_config(tmp_path):
    """Write an overrides file and return its absolute path."""
    def _write(text, name="test.cfg"):
        path = tmp_path / name
        path.write_text(text)
        return str(path)
    return _write

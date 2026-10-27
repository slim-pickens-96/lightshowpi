import os

import numpy as np
import pytest

import configuration_manager
import fft
import gpio_backend
from conftest import TEST_HOME


def test_defaults_load_with_new_options():
    cm = configuration_manager.Configuration()
    assert cm.home_dir == TEST_HOME
    assert cm.hardware.gpio_backend == "auto"
    assert cm.hardware.pin_numbering == "wiringpi"
    assert cm.hardware.gpio_pins == [0, 1, 2, 3, 4, 5, 6, 7]
    assert cm.audio_processing.use_gpu is False


def test_absolute_config_path(write_config):
    path = write_config("[hardware]\ngpio_pins = 3,4\npin_modes = pwm\ngpio_backend = simulated\n")
    cm = configuration_manager.Configuration(param_config=path)
    assert cm.hardware.gpio_pins == [3, 4]
    assert cm.hardware.pin_modes == ["pwm", "pwm"]
    assert cm.hardware.gpio_backend == "simulated"


def test_example_overrides_file_is_valid(tmp_path):
    example = os.path.join(TEST_HOME, "config", "overrides.cfg.example")
    cm = configuration_manager.Configuration(param_config=example)
    assert cm.hardware.gpio_len == 8


def test_home_dir_fallback(monkeypatch):
    # configuration_manager works out the home folder when the variable is unset
    import subprocess, sys
    env = dict(os.environ)
    env.pop("SYNCHRONIZED_LIGHTS_HOME")
    code = "import configuration_manager as c; print(c.HOME_DIR)"
    out = subprocess.run([sys.executable, "-c", code], cwd=os.path.join(TEST_HOME, "py"),
                         env=dict(env, PYTHONPATH=os.path.join(TEST_HOME, "py")),
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    repo = os.path.dirname(os.path.realpath(os.path.join(TEST_HOME, "py")))
    assert os.path.realpath(out.stdout.strip()) == repo


@pytest.fixture
def hardware(write_config):
    import hardware_controller

    def _make(text):
        path = write_config(text)
        hc = hardware_controller.Hardware(param_config=path)
        return hc, hardware_controller.wiringpi
    return _make


def test_hardware_on_off_simulated(hardware):
    hc, gpio = hardware("[hardware]\ngpio_pins = 0,1,2\npin_modes = onoff\n")
    assert isinstance(gpio, gpio_backend.SimulatedGPIO)
    hc.initialize()
    assert gpio.modes == {0: 1, 1: 1, 2: 1}
    hc.turn_on_lights()
    assert gpio.values == {0: 1, 1: 1, 2: 1}
    hc.turn_off_lights()
    assert gpio.values == {0: 0, 1: 0, 2: 0}
    hc.clean_up()
    assert gpio.modes == {0: 0, 1: 0, 2: 0}


def test_active_low_and_pwm(hardware):
    hc, gpio = hardware("[hardware]\ngpio_pins = 0,1\npin_modes = pwm,onoff\n"
                        "active_low_mode = True\npwm_range = 100\n")
    hc.initialize()
    assert gpio.pwm_range == {0: 100}
    hc.set_light(0, False, 0.25)
    hc.set_light(1, False, 1.0)
    assert gpio.values[0] == 75      # inverted for active-low relay boards
    assert gpio.values[1] == 0


def test_expanders_require_wiringpi(hardware, monkeypatch, capsys):
    import hardware_controller
    monkeypatch.delenv("LIGHTSHOWPI_GPIO_BACKEND")
    monkeypatch.setattr(hardware_controller, "is_a_raspberryPI", True)
    monkeypatch.setattr(gpio_backend, "wiringpi_available", lambda: False)
    with pytest.raises(SystemExit) as exit_info:
        hardware("[hardware]\ndevices = {\"mcp23017\": [{\"pinBase\": 65, \"i2cAddress\": \"0x20\"}]}\n"
                 "gpio_pins = 65,66\n")
    assert exit_info.value.code == 2
    assert "--with-wiringpi" in capsys.readouterr().err


def test_fft_cpu_finds_tone():
    chunk, rate = 2048, 44100
    calc = fft.FFT(chunk, rate, 8, 20, 15000, 0, 0, 2, use_gpu=False)
    t = np.arange(chunk) / rate
    tone = (0.5 * 32767 * np.sin(2 * np.pi * 440 * t)).astype("<i2")
    stereo = np.repeat(tone, 2).tobytes()
    levels = calc.calculate_levels(stereo)
    channel = int(np.argmax(levels))
    low, high = calc.frequency_limits[channel]
    assert low <= 440 <= high
    assert calc.calculate_levels(np.zeros(chunk * 2, dtype="<i2").tobytes()).sum() == 0


def test_use_gpu_falls_back_without_module(monkeypatch):
    monkeypatch.setattr(fft, "AudioLevels", None)
    calc = fft.FFT(2048, 44100, 8, 20, 15000, 0, 0, 2, use_gpu=True)
    assert calc.use_gpu is False

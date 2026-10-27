import pytest

import gpio_backend as gb


class FakeLgpio(object):
    """Minimal stand-in for the lgpio module."""

    def __init__(self, chips):
        self.chips = chips          # {chip number: label}
        self.opened = []
        self.closed = []
        self.calls = []

    def gpiochip_open(self, chip):
        if chip not in self.chips:
            raise Exception("no such chip")
        self.opened.append(chip)
        return 100 + chip

    def gpiochip_info(self, handle):
        chip = handle - 100
        return (54, "gpiochip%d" % chip, self.chips[chip])

    def gpiochip_close(self, handle):
        self.closed.append(handle - 100)

    def gpio_claim_output(self, handle, gpio, level=0):
        self.calls.append(("out", handle, gpio))

    def gpio_claim_input(self, handle, gpio):
        self.calls.append(("in", handle, gpio))

    def gpio_free(self, handle, gpio):
        self.calls.append(("free", handle, gpio))

    def gpio_write(self, handle, gpio, value):
        self.calls.append(("write", handle, gpio, value))

    def tx_pwm(self, handle, gpio, freq, duty):
        self.calls.append(("pwm", handle, gpio, freq, duty))


def test_wiringpi_to_bcm_matches_published_map():
    # physical pins 11,12,13,15,16,18,22,7 = the LightShow Pi default channels
    assert [gb.WIRINGPI_TO_BCM[p] for p in range(8)] == [17, 18, 27, 22, 23, 24, 25, 4]
    assert gb.WIRINGPI_TO_BCM[21] == 5 and gb.WIRINGPI_TO_BCM[29] == 21
    assert gb.wiringpi_to_bcm(2, revision=1) == 21


def test_invalid_wiringpi_pin():
    with pytest.raises(gb.GPIOBackendError):
        gb.wiringpi_to_bcm(40)


def test_lgpio_picks_header_chip_on_pi5_layout():
    # Pi 5 (older kernels): gpiochip0 = brcmstb, gpiochip4 = pinctrl-rp1
    lg = FakeLgpio({0: "gpio-brcmstb@107d508500", 4: "pinctrl-rp1"})
    backend = gb.LgpioGPIO(lgpio_module=lg)
    backend.wiringPiSetupPY()
    assert backend.handle == 104
    assert 0 in lg.closed


def test_lgpio_pi4_layout():
    lg = FakeLgpio({0: "pinctrl-bcm2711", 1: "raspberrypi-exp-gpio"})
    backend = gb.LgpioGPIO(lgpio_module=lg)
    backend.wiringPiSetupPY()
    assert backend.handle == 100


def test_lgpio_digital_write_maps_pins():
    lg = FakeLgpio({0: "pinctrl-bcm2835"})
    backend = gb.LgpioGPIO(lgpio_module=lg)
    backend.wiringPiSetupPY()
    backend.pinModePY(0, 1)
    backend.digitalWritePY(0, 1)
    backend.digitalWritePY(7, 0)
    assert ("out", 100, 17) in lg.calls
    assert ("write", 100, 17, 1) in lg.calls
    assert ("write", 100, 4, 0) in lg.calls
    backend.pinModePY(0, 0)
    assert ("in", 100, 17) in lg.calls
    backend.close()
    assert lg.closed == [0]


def test_lgpio_bcm_numbering():
    lg = FakeLgpio({0: "pinctrl-bcm2835"})
    backend = gb.LgpioGPIO(lgpio_module=lg, numbering="bcm")
    backend.wiringPiSetupPY()
    backend.digitalWritePY(17, 1)
    assert ("write", 100, 17, 1) in lg.calls


def test_lgpio_soft_pwm_matches_wiringpi_frequency():
    lg = FakeLgpio({0: "pinctrl-bcm2835"})
    backend = gb.LgpioGPIO(lgpio_module=lg)
    backend.softPwmCreatePY(1, 0, 100)
    backend.softPwmWritePY(1, 50)
    # WiringPi softPwm: 100us steps * range 100 -> 100 Hz
    assert lg.calls[-1] == ("pwm", 100, 18, 100, 50.0)
    backend.softPwmCreatePY(2, 0, 200)
    backend.softPwmWritePY(2, 200)
    assert lg.calls[-1] == ("pwm", 100, 27, 50, 100.0)


def test_lgpio_refuses_expanders_with_clear_message():
    backend = gb.LgpioGPIO(lgpio_module=FakeLgpio({0: "pinctrl-bcm2835"}))
    with pytest.raises(gb.GPIOBackendError, match="wiringpi"):
        backend.mcp23017SetupPY(65, 0x20)
    with pytest.raises(gb.GPIOBackendError, match="PiGlow"):
        backend.analogWritePY(577, 10)


def test_simulated_backend_records_state():
    sim = gb.SimulatedGPIO()
    sim.wiringPiSetupPY()
    sim.pinModePY(3, 1)
    sim.digitalWritePY(3, 1)
    sim.softPwmCreatePY(4, 0, 100)
    sim.softPwmWritePY(4, 42)
    assert sim.values == {3: 1, 4: 42}
    assert sim.mcp23017SetupPY(65, 0x20)
    assert sim.devices == [("mcp23017", 65, 0x20)]


def test_simulated_trace_file(tmp_path, monkeypatch):
    trace = tmp_path / "trace.txt"
    monkeypatch.setenv("LIGHTSHOWPI_SIM_TRACE", str(trace))
    sim = gb.SimulatedGPIO()
    sim.digitalWritePY(1, 1)
    sim.close()
    assert trace.read_text().strip() == "write 1 1"


class FakeWiringPiPy(object):
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a: self.calls.append((name,) + a)


def test_wiringpi_adapter_with_py_suffix_module():
    module = FakeWiringPiPy()
    module.wiringPiSetupPY = lambda: module.calls.append(("wiringPiSetupPY",))
    backend = gb.WiringPiGPIO(module=module)
    backend.wiringPiSetupPY()
    backend.digitalWritePY(0, 1)
    backend.mcp23017SetupPY(65, 32)
    assert module.calls == [("wiringPiSetupPY",), ("digitalWritePY", 0, 1),
                            ("mcp23017SetupPY", 65, 32)]


def test_wiringpi_adapter_with_plain_module():
    class Plain(object):
        def __init__(self):
            self.calls = []

        def wiringPiSetup(self):
            self.calls.append("setup")

        def digitalWrite(self, pin, value):
            self.calls.append(("dw", pin, value))

    module = Plain()
    backend = gb.WiringPiGPIO(module=module)
    backend.wiringPiSetupPY()
    backend.digitalWritePY(5, 0)
    assert module.calls == ["setup", ("dw", 5, 0)]


def test_wiringpi_ctypes_library():
    calls = []

    class FakeLib(object):
        def __getattr__(self, name):
            return lambda *a: calls.append((name,) + a)

    lib = gb.WiringPiLibrary(library=FakeLib())
    backend = gb.WiringPiGPIO(module=lib)
    backend.wiringPiSetupPY()
    backend.softPwmCreatePY(1, 0, 100)
    backend.sr595SetupPY(100, 8, 0, 1, 2)
    assert calls == [("wiringPiSetup",), ("softPwmCreate", 1, 0, 100),
                     ("sr595Setup", 100, 8, 0, 1, 2)]


def test_select_backend(monkeypatch):
    monkeypatch.delenv("LIGHTSHOWPI_GPIO_BACKEND", raising=False)
    assert gb.select_backend("auto", is_pi=False).name == "simulated"
    assert gb.select_backend("simulated", is_pi=True).name == "simulated"
    with pytest.raises(gb.GPIOBackendError, match="Unknown gpio_backend"):
        gb.select_backend("pigpio")
    with pytest.raises(gb.GPIOBackendError, match="pin_numbering"):
        gb.select_backend("simulated", numbering="board")

    monkeypatch.setattr(gb, "lgpio_available", lambda: False)
    monkeypatch.setattr(gb, "wiringpi_available", lambda: False)
    with pytest.raises(gb.GPIOBackendError, match="python3-lgpio"):
        gb.select_backend("auto", is_pi=True)
    with pytest.raises(gb.GPIOBackendError, match="--with-wiringpi"):
        gb.select_backend("auto", is_pi=True, needs_wiringpi=True)
    with pytest.raises(gb.GPIOBackendError, match="python3-lgpio"):
        gb.select_backend("lgpio", is_pi=True)


def test_environment_override(monkeypatch):
    monkeypatch.setenv("LIGHTSHOWPI_GPIO_BACKEND", "simulated")
    monkeypatch.setattr(gb, "lgpio_available", lambda: True)
    assert gb.select_backend("lgpio", is_pi=True).name == "simulated"


def test_lgpio_without_gpiochip_gives_clear_error(monkeypatch):
    """Pi detected, lgpio installed, but no /dev/gpiochip* (container, old kernel)."""
    import gpio_backend

    class FakeLgpio(object):
        def gpiochip_open(self, chip):
            raise Exception("can not open gpiochip")

    backend = gpio_backend.LgpioGPIO(lgpio_module=FakeLgpio())
    monkeypatch.setattr(gpio_backend.os.path, "exists", lambda path: False)
    with pytest.raises(gpio_backend.GPIOBackendError, match="No GPIO chip found"):
        backend.wiringPiSetupPY()

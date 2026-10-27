import pytest

import Platform

# Revision codes from the official Raspberry Pi documentation
BOARDS = [
    ("0002", "Model B", 1),
    ("000e", "Model B", 1),
    ("0010", "Model B+", 1),
    ("900092", "Pi Zero", 1),
    ("9000c1", "Pi Zero W", 1),
    ("a01041", "Pi 2 Model B", 2),
    ("a02082", "Pi 3 Model B", 3),
    ("a020d3", "Pi 3 Model B+", 3),
    ("9020e0", "Pi 3 Model A+", 3),
    ("a03111", "Pi 4 Model B", 4),
    ("d03114", "Pi 4 Model B", 4),
    ("902120", "Pi Zero 2 W", 3),
    ("c03130", "Pi 400", 4),
    ("a03140", "Compute Module 4", 4),
    ("c04170", "Pi 5", 5),
    ("d04170", "Pi 5", 5),
    ("d04190", "Pi 500", 5),
    ("b04180", "Compute Module 5", 5),
]


@pytest.mark.parametrize("code,model,major", BOARDS)
def test_decode_revision(code, model, major):
    assert Platform.decode_revision(code) == (model, major)


@pytest.mark.parametrize("code,model,major", BOARDS)
def test_get_model_and_version_from_cpuinfo(tmp_path, monkeypatch, code, model, major):
    cpuinfo = tmp_path / "cpuinfo"
    # Pi 5 / 64-bit kernels have no "Hardware" line; older ones do.
    cpuinfo.write_text("processor\t: 0\nRevision\t: %s\nSerial\t\t: 00000000\n" % code)
    monkeypatch.setattr(Platform, "CPUINFO_PATH", str(cpuinfo))
    monkeypatch.setattr(Platform, "DT_MODEL_PATH", str(tmp_path / "missing"))
    assert Platform.platform_detect() == Platform.RASPBERRY_PI
    assert Platform.pi_version() == major
    name, header = Platform.get_model()
    assert name == model
    if model in ("Model A", "Model B"):
        assert header is Platform.header26
    else:
        assert header is Platform.header40


def test_device_tree_model_is_enough(tmp_path, monkeypatch):
    model = tmp_path / "model"
    model.write_bytes(b"Raspberry Pi 9 Model Z Rev 1.0\x00")
    monkeypatch.setattr(Platform, "CPUINFO_PATH", str(tmp_path / "missing"))
    monkeypatch.setattr(Platform, "DT_MODEL_PATH", str(model))
    assert Platform.platform_detect() == Platform.RASPBERRY_PI
    assert Platform.get_model()[0] == "Raspberry Pi 9 Model Z Rev 1.0"
    assert Platform.pi_version() is None


def test_not_a_pi(tmp_path, monkeypatch):
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("processor\t: 0\nvendor_id\t: GenuineIntel\n")
    monkeypatch.setattr(Platform, "CPUINFO_PATH", str(cpuinfo))
    monkeypatch.setattr(Platform, "DT_MODEL_PATH", str(tmp_path / "missing"))
    assert Platform.platform_detect() != Platform.RASPBERRY_PI
    assert Platform.pi_version() is None
    with pytest.raises(RuntimeError):
        Platform.get_model()


def test_unknown_future_type_is_still_a_pi():
    # new-style flag set, unknown type 0x7f
    assert Platform.decode_revision("d047f0")[1] is None


def test_pi_revision(tmp_path, monkeypatch):
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("Revision\t: 0002\n")
    monkeypatch.setattr(Platform, "CPUINFO_PATH", str(cpuinfo))
    assert Platform.pi_revision() == 1
    cpuinfo.write_text("Revision\t: c04170\n")
    assert Platform.pi_revision() == 2

"""Doctor command, installer/uninstaller dry runs and shell script checks."""
import glob
import os
import shutil
import subprocess
import sys

import pytest

from conftest import REPO, TEST_HOME

BASH_SCRIPTS = sorted(
    [os.path.join(REPO, "install.sh"), os.path.join(REPO, "uninstall.sh"),
     os.path.join(REPO, "bin", "lightshowpi-env.sh")]
    + [p for p in glob.glob(os.path.join(REPO, "bin", "*"))
       if os.path.isfile(p) and open(p, "rb").read(2) == b"#!"
       and b"bash" in open(p, "rb").readline() or p.endswith("lightshowpi-env.sh")])


def doctor(*args, **env):
    return subprocess.run([sys.executable, os.path.join(REPO, "py", "doctor.py"), *args],
                          env=dict(os.environ, **env), capture_output=True, text=True,
                          timeout=60)


def test_doctor_good_config(write_config):
    cfg = write_config("[lightshow]\naudio_out_card = null\n")
    result = doctor("--config=%s" % cfg)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "All required checks passed." in result.stdout
    assert "GPIO back end: simulated" in result.stdout


def test_doctor_bad_pin(write_config):
    cfg = write_config("[hardware]\ngpio_pins = 0,1,99\n[lightshow]\naudio_out_card = null\n")
    result = doctor("--config=%s" % cfg)
    assert result.returncode == 1
    assert "[FAIL] gpio_pins" in result.stdout


def test_doctor_config_syntax_error(write_config):
    cfg = write_config("[hardware\ngpio_pins = 0\n")
    result = doctor("--config=%s" % cfg)
    assert result.returncode == 1
    assert "[FAIL] Configuration" in result.stdout


def test_doctor_bad_audio_card(write_config):
    cfg = write_config("[lightshow]\naudio_out_card = no-such-card\n")
    result = doctor("--config=%s" % cfg)
    assert result.returncode == 1
    assert "[FAIL] Audio output" in result.stdout


@pytest.mark.parametrize("script", BASH_SCRIPTS, ids=os.path.basename)
def test_bash_syntax(script):
    subprocess.run(["bash", "-n", script], check=True)


@pytest.mark.skipif(not shutil.which("shellcheck"), reason="shellcheck not installed")
@pytest.mark.parametrize("script", BASH_SCRIPTS, ids=os.path.basename)
def test_shellcheck(script):
    result = subprocess.run(["shellcheck", "-x", "-S", "warning", script],
                            cwd=os.path.dirname(script), capture_output=True, text=True)
    assert result.returncode == 0, result.stdout


OS_RELEASES = {
    "bookworm": 'PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"\nID=debian\nVERSION_CODENAME=bookworm\n',
    "trixie": 'PRETTY_NAME="Raspbian GNU/Linux 13 (trixie)"\nID=raspbian\nID_LIKE=debian\nVERSION_CODENAME=trixie\n',
    "bullseye": 'PRETTY_NAME="Raspbian GNU/Linux 11 (bullseye)"\nID=raspbian\nID_LIKE=debian\nVERSION_CODENAME=bullseye\n',
    "ubuntu": 'PRETTY_NAME="Ubuntu 24.04 LTS"\nID=ubuntu\nID_LIKE=debian\nVERSION_CODENAME=noble\n',
}


def dry_run(tmp_path, release, *args):
    os_release = tmp_path / "os-release"
    os_release.write_text(OS_RELEASES[release])
    env = dict(os.environ, LSP_OS_RELEASE=str(os_release),
               LSP_INSTALL_LOG=str(tmp_path / "install.log"))
    return subprocess.run(["bash", os.path.join(REPO, "install.sh"), "--dry-run", *args],
                          env=env, capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("release", ["bookworm", "trixie"])
def test_install_dry_run_supported(tmp_path, release):
    result = dry_run(tmp_path, release, "--all")
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout
    assert "apt-get install" in out
    assert "python3-alsaaudio" in out and "ffmpeg" in out
    # the old installer's risky system changes are gone
    assert "/usr/bin/python" not in out.replace("/usr/bin/python3", "")
    assert "sudoers" not in out


def test_install_dry_run_too_old(tmp_path):
    result = dry_run(tmp_path, "bullseye")
    assert result.returncode != 0
    assert "too old" in result.stdout + result.stderr


def test_install_dry_run_unsupported(tmp_path):
    result = dry_run(tmp_path, "ubuntu")
    assert result.returncode != 0
    assert "not supported" in result.stdout + result.stderr
    allowed = dry_run(tmp_path, "ubuntu", "--allow-unsupported")
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr


def test_install_rejects_unknown_option(tmp_path):
    result = dry_run(tmp_path, "bookworm", "--bogus")
    assert result.returncode != 0


def test_uninstall_dry_run():
    result = subprocess.run(["bash", os.path.join(REPO, "uninstall.sh"), "--dry-run"],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def run_cli(*args):
    env = dict(os.environ, LIGHTSHOWPI_NO_SUDO="1", SYNCHRONIZED_LIGHTS_HOME=REPO)
    return subprocess.run([os.path.join(REPO, "bin", "lightshowpi"), *args], env=env,
                          capture_output=True, text=True, timeout=60)


def test_cli_help_and_version():
    result = run_cli("help")
    assert result.returncode == 0
    for command in ("doctor", "play", "start", "stop", "test"):
        assert command in result.stdout
    version = run_cli("version")
    assert version.returncode == 0
    assert open(os.path.join(REPO, "VERSION")).read().strip() in version.stdout


def test_cli_unknown_command():
    assert run_cli("frobnicate").returncode != 0


def test_cli_pins():
    result = run_cli("pins")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "17" in result.stdout     # wiringPi 0 = BCM 17


def test_play_script_handles_spaces(tmp_path):
    """bin/play used to split file names on spaces."""
    song = tmp_path / "my song.wav"
    from conftest import write_tone
    write_tone(str(song), seconds=0.5)
    cfg = tmp_path / "c.cfg"
    cfg.write_text("[lightshow]\naudio_out_card = null\n")
    fake_py = tmp_path / "fakepy"
    fake_py.write_text("#!/bin/sh\nfor a in \"$@\"; do echo \"ARG<$a>\"; done\n")
    fake_py.chmod(0o755)
    env = dict(os.environ, LIGHTSHOWPI_NO_SUDO="1", LIGHTSHOWPI_PYTHON=str(fake_py))
    result = subprocess.run([os.path.join(REPO, "bin", "play"), str(song)], env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "ARG<--file=%s>" % song in result.stdout


def _fake_pi(tmp_path):
    cpuinfo = tmp_path / "cpuinfo"
    cpuinfo.write_text("Revision\t: c03114\nModel\t\t: Raspberry Pi 4 Model B Rev 1.4\n")
    model = tmp_path / "model"
    model.write_text("Raspberry Pi 4 Model B Rev 1.4\0")
    return {"LIGHTSHOWPI_CPUINFO": str(cpuinfo), "LIGHTSHOWPI_DT_MODEL": str(model)}


def test_service_stops_on_configuration_error(tmp_path, write_config):
    """lightshowpi-service must not loop forever on a fatal error (exit code 2)."""
    cfg = write_config("[hardware]\ngpio_backend = wiringpi\n[lightshow]\naudio_out_card = null\n")
    env = dict(os.environ, LIGHTSHOWPI_NO_SUDO="1", LIGHTSHOWPI_PYTHON=sys.executable,
               **_fake_pi(tmp_path))
    env.pop("LIGHTSHOWPI_GPIO_BACKEND", None)
    env["LD_LIBRARY_PATH"] = str(tmp_path)  # make sure no libwiringPi is found
    result = subprocess.run([os.path.join(REPO, "bin", "lightshowpi-service"),
                             "--config=%s" % cfg], env=env, capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 2, result.stdout + result.stderr
    # either our own clear error, or (if a real WiringPi library is installed on a
    # machine it can't identify) the crash-loop guard
    assert ("configuration error" in result.stderr
            or "failed 5 times in a row" in result.stderr), result.stderr


def test_service_stops_on_crash_loop(tmp_path, write_config):
    """Repeated quick failures (exit code 1) must not restart forever."""
    playlist = tmp_path / ".playlist"
    playlist.write_text("Gone\t%s\n" % (tmp_path / "deleted.mp3"))
    cfg = write_config("[lightshow]\naudio_out_card = null\n"
                       "playlist_path = %s\n" % playlist)
    env = dict(os.environ, LIGHTSHOWPI_NO_SUDO="1", LIGHTSHOWPI_PYTHON=sys.executable,
               LIGHTSHOWPI_MAX_QUICK_FAILURES="2")
    result = subprocess.run([os.path.join(REPO, "bin", "lightshowpi-service"),
                             "--config=%s" % cfg], env=env, capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "failed 2 times in a row" in result.stderr


def test_service_stops_cleanly_on_sigterm(tmp_path, write_config):
    import signal
    import time
    pytest.importorskip("alsaaudio")
    from conftest import write_tone
    song = write_tone(str(tmp_path / "long.wav"), seconds=30)
    playlist = tmp_path / ".playlist"
    playlist.write_text("Long\t%s\n" % song)
    cfg = write_config("[lightshow]\naudio_out_card = null\nplaylist_path = %s\n"
                       "preshow_configuration =\npostshow_configuration =\n" % playlist)
    env = dict(os.environ, LIGHTSHOWPI_NO_SUDO="1", LIGHTSHOWPI_PYTHON=sys.executable)
    proc = subprocess.Popen([os.path.join(REPO, "bin", "lightshowpi-service"),
                             "--config=%s" % cfg], env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    time.sleep(3)
    assert proc.poll() is None, proc.communicate()
    proc.send_signal(signal.SIGTERM)
    out, err = proc.communicate(timeout=30)
    assert proc.returncode == 0, out + err


def test_missing_playlist_is_a_configuration_error(tmp_path, write_config):
    cfg = write_config("[lightshow]\naudio_out_card = null\n"
                       "playlist_path = %s\n" % (tmp_path / "nope" / ".playlist"))
    env = dict(os.environ, LIGHTSHOWPI_NO_SUDO="1", LIGHTSHOWPI_PYTHON=sys.executable)
    result = subprocess.run([os.path.join(REPO, "bin", "lightshowpi-service"),
                             "--config=%s" % cfg], env=env, capture_output=True,
                            text=True, timeout=60)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Playlist not found" in result.stderr
    assert "Traceback" not in result.stderr

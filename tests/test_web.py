"""The microweb CGI pages must load on a modern system.

Regression tests for problems found when the web interface was first run:
  * pages crashed when there was no user called "pi" (Raspberry Pi OS has no
    default "pi" user since 2022)
  * the main page crashed when overrides.cfg only contained a few settings
  * the main page crashed when the volume couldn't be read
  * the buttons ran "python", which doesn't exist on bookworm/trixie
"""
import os
import shutil
import subprocess
import sys
import urllib.parse

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

pytest.importorskip("cgi", reason="cgi / legacy-cgi not installed")
pytest.importorskip("mutagen")


@pytest.fixture
def web_home(tmp_path):
    home = tmp_path / "lsp"
    home.mkdir()
    for sub in ("web", "config", "music"):
        shutil.copytree(os.path.join(REPO, sub), str(home / sub), symlinks=True)
    for sub in ("py", "bin", "tools"):
        os.symlink(os.path.join(REPO, sub), str(home / sub))
    (home / "logs").mkdir()
    # a partial overrides file, as users normally have
    (home / "config" / "overrides.cfg").write_text("[lightshow]\naudio_out_card = null\n")
    return home


def run_cgi(home, page, post=None, query="", extra_env=None):
    body = urllib.parse.urlencode(post or {}).encode()
    env = dict(os.environ,
               SYNCHRONIZED_LIGHTS_HOME=str(home),
               LIGHTSHOWPI_GPIO_BACKEND="simulated",
               LIGHTSHOWPI_PYTHON=sys.executable,
               LIGHTSHOWPI_NO_SUDO="1",
               GATEWAY_INTERFACE="CGI/1.1",
               REQUEST_METHOD="POST" if post else "GET",
               QUERY_STRING=query,
               CONTENT_TYPE="application/x-www-form-urlencoded",
               CONTENT_LENGTH=str(len(body)),
               PATH="/usr/bin:/bin")  # deliberately: no 'python' command
    env.update(extra_env or {})
    script = str(home / "web" / "microweb" / "cgi-bin" / (page + ".cgi"))
    return subprocess.run([sys.executable, script], input=body, env=env,
                          cwd=str(home / "web" / "microweb"),
                          capture_output=True, timeout=60)


@pytest.mark.parametrize("page", ["web_controls", "playlist", "dir_play", "settings", "tools"])
def test_page_loads(web_home, page):
    result = run_cgi(web_home, page)
    out = result.stdout.decode(errors="replace")
    err = result.stderr.decode(errors="replace")
    assert result.returncode == 0, err
    assert "Traceback" not in err and "cgitb_error" not in out, out + err
    assert "LightShowPi Web Controls" in out


def test_playlist_page_lists_sample_songs(web_home):
    out = run_cgi(web_home, "playlist").stdout.decode()
    assert "Deck The Halls" in out


@pytest.mark.parametrize("message,value", [("On", "1"), ("Off", "0")])
def test_lights_buttons_drive_gpio(web_home, tmp_path, message, value):
    trace = tmp_path / "trace"
    result = run_cgi(web_home, "web_controls", post={"message": message},
                     extra_env={"LIGHTSHOWPI_SIM_TRACE": str(trace)})
    assert result.returncode == 0, result.stderr.decode()
    writes = [line.split() for line in trace.read_text().splitlines()
              if line.startswith("write")]
    final = {}
    for _, pin, val in writes:
        final[pin] = val
    assert len(final) == 8 and set(final.values()) == {value}, writes


def test_tools_channel_switch(web_home, tmp_path):
    trace = tmp_path / "trace"
    result = run_cgi(web_home, "tools", query="channelon=3",
                     extra_env={"LIGHTSHOWPI_SIM_TRACE": str(trace)})
    assert result.returncode == 0, result.stderr.decode()
    assert "write 2 1" in trace.read_text()

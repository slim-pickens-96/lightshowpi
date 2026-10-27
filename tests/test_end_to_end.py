"""Play a real song through the full program with simulated GPIO.

Audio goes to the ALSA "null" device, so this needs libasound2 + pyalsaaudio
and ffmpeg, but no sound card and no Raspberry Pi.
"""
import collections
import os
import shutil
import subprocess
import sys

import pytest

import wave

import numpy as np

from conftest import TEST_HOME, REPO, write_tone


def write_bursts(path, seconds=4.0, rate=44100):
    """Alternating 0.25 s bursts of white noise and silence (every band changes)."""
    rng = np.random.default_rng(7)
    n = int(seconds * rate)
    noise = rng.normal(0, 8000, n).clip(-32767, 32767)
    gate = ((np.arange(n) // int(0.25 * rate)) % 2 == 0)
    mono = (noise * gate).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.repeat(mono, 2).tobytes())
    return path

alsaaudio = pytest.importorskip("alsaaudio")
pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def run_show(tmp_path, song, extra_cfg="", timeout=180, trace_name="trace.txt"):
    cfg = tmp_path / "e2e.cfg"
    cfg.write_text("[lightshow]\naudio_out_card = null\npreshow_configuration =\n"
                   "postshow_configuration =\n[audio_processing]\nuse_gpu = False\n" + extra_cfg)
    trace = tmp_path / trace_name
    env = dict(os.environ, LIGHTSHOWPI_SIM_TRACE=str(trace), TERM="dumb")
    proc = subprocess.run([sys.executable, os.path.join(REPO, "py", "synchronized_lights.py"),
                           "--config=%s" % cfg, "--file=%s" % song],
                          env=env, capture_output=True, text=True, timeout=timeout,
                          stdin=subprocess.DEVNULL)
    events = trace.read_text().split("\n") if trace.exists() else []
    return proc, [e.split() for e in events if e]


def test_show_plays_mp3_and_lights_follow_music(tmp_path):
    wav = write_bursts(str(tmp_path / "beeps.wav"))
    song = str(tmp_path / "beeps.mp3")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, song], check=True)

    # first play: FFT is computed and saved to the .sync cache
    proc, events = run_show(tmp_path, song, trace_name="first.txt")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (tmp_path / ".beeps.mp3.sync").exists()
    assert (tmp_path / ".beeps.mp3.cfg").exists()
    assert [e for e in events if e[0] == "write"], "no GPIO writes recorded"

    # second play reads the cache and uses the song's real mean/std, as upstream does;
    # every channel should now follow the noise bursts on and off
    proc, events = run_show(tmp_path, song, trace_name="second.txt")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    per_pin = collections.defaultdict(set)
    last = {}
    for event in events:
        if event[0] == "write":
            per_pin[int(event[1])].add(int(event[2]))
            last[int(event[1])] = int(event[2])
    assert sorted(per_pin) == list(range(8))
    assert all(values == {0, 1} for values in per_pin.values()), dict(per_pin)
    # lights end OFF and pins are released back to inputs
    assert set(last.values()) == {0}
    assert events[-1][0] == "mode" and events[-1][2] == "0"


def test_sample_song_from_repository(tmp_path):
    sample = os.path.join(REPO, "music", "sample", "ovenrake_deck-the-halls.mp3")
    song = str(tmp_path / "deck.mp3")
    shutil.copy(sample, song)
    proc, events = run_show(tmp_path, song, timeout=600)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert len([e for e in events if e[0] == "write"]) > 1000


def test_missing_song_gives_clear_error(tmp_path):
    proc, _ = run_show(tmp_path, str(tmp_path / "nope.mp3"))
    assert proc.returncode != 0
    assert "not found" in (proc.stdout + proc.stderr)


def test_sync_file_generator_matches_show(tmp_path):
    """tools/sync_file_generator.py must write a cache the show accepts as-is."""
    import numpy as np
    tool_dir = tmp_path / "tool"
    show_dir = tmp_path / "show"
    tool_dir.mkdir()
    show_dir.mkdir()
    wav = write_bursts(str(tmp_path / "b.wav"), seconds=3.0)
    for folder in (tool_dir, show_dir):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, str(folder / "song one.mp3")],
                       check=True)
    env = dict(os.environ, TERM="dumb")
    tool = subprocess.run([sys.executable, os.path.join(REPO, "tools", "sync_file_generator.py")],
                          input="y\n%s\n" % tool_dir, env=env, capture_output=True, text=True,
                          timeout=180)
    assert tool.returncode == 0, tool.stdout + tool.stderr
    cfg = tmp_path / "c.cfg"
    cfg.write_text("[lightshow]\naudio_out_card = null\n")
    show = subprocess.run([sys.executable, os.path.join(REPO, "py", "synchronized_lights.py"),
                           "--config=%s" % cfg, "--file=%s" % (show_dir / "song one.mp3"),
                           "--createcache"], env=env, capture_output=True, text=True,
                          timeout=180, stdin=subprocess.DEVNULL)
    assert show.returncode == 0, show.stdout + show.stderr
    a = np.loadtxt(str(tool_dir / ".song one.mp3.sync"))
    b = np.loadtxt(str(show_dir / ".song one.mp3.sync"))
    assert a.shape == b.shape
    assert np.allclose(a, b, atol=1e-5)
    assert (tool_dir / ".song one.mp3.cfg").read_text() == (show_dir / ".song one.mp3.cfg").read_text()

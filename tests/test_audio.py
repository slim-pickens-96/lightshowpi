import os
import shutil
import subprocess
import sys

import numpy as np
import pytest

import audio_decoder
from conftest import write_tone

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def read_all(stream, chunk=2048):
    data = b""
    while True:
        part = stream.readframes(chunk)
        if not part:
            break
        data += part
    return data


def test_plain_wav_uses_wave_module(tmp_path):
    path = write_tone(str(tmp_path / "tone.wav"), seconds=1.0)
    stream = audio_decoder.open(path)
    assert stream.getnchannels() == 2
    assert stream.getframerate() == 44100
    assert stream.getnframes() == 44100
    assert len(read_all(stream)) == 44100 * 4
    stream.close()


@needs_ffmpeg
def test_mp3_decodes_through_ffmpeg(tmp_path):
    wav = write_tone(str(tmp_path / "tone.wav"), seconds=2.0)
    mp3 = str(tmp_path / "tone.mp3")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, mp3], check=True)
    stream = audio_decoder.open(mp3)
    assert isinstance(stream, audio_decoder.FFmpegStream)
    assert stream.getnchannels() == 2 and stream.getsampwidth() == 2
    assert stream.getframerate() == 44100
    assert abs(stream.getnframes() - 88200) < 4410   # mp3 padding
    data = read_all(stream)
    assert abs(len(data) // 4 - 88200) < 4410
    assert audio_decoder.peak(data) > 15000
    stream.close()


@needs_ffmpeg
def test_mono_file_is_converted_to_stereo(tmp_path):
    wav = write_tone(str(tmp_path / "mono.wav"), seconds=1.0, channels=1)
    stream = audio_decoder.open(wav)
    assert stream.getnchannels() == 2
    samples = np.frombuffer(read_all(stream), dtype="<i2")
    assert np.array_equal(samples[0::2], samples[1::2])


@needs_ffmpeg
def test_other_formats(tmp_path):
    wav = write_tone(str(tmp_path / "t.wav"), seconds=1.0)
    for ext in ("ogg", "flac", "m4a"):
        out = str(tmp_path / ("t." + ext))
        result = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, out])
        if result.returncode != 0:
            pytest.skip("this ffmpeg cannot encode " + ext)
        stream = audio_decoder.open(out)
        assert len(read_all(stream)) > 40000 * 4, ext
        stream.close()


def test_missing_file():
    with pytest.raises(audio_decoder.DecoderError, match="not found"):
        audio_decoder.open("/nonexistent/song.mp3")


@needs_ffmpeg
def test_not_audio(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_text("this is not audio")
    with pytest.raises(audio_decoder.DecoderError):
        audio_decoder.open(str(bad))


def test_missing_ffmpeg_message(tmp_path, monkeypatch):
    wav = write_tone(str(tmp_path / "mono.wav"), seconds=0.1, channels=1)
    monkeypatch.setattr(audio_decoder, "find_tool", lambda name: None)
    with pytest.raises(audio_decoder.DecoderError, match="sudo apt install ffmpeg"):
        audio_decoder.open(wav)


def test_peak_matches_definition():
    samples = np.array([0, 5, -32768, 1200, 32767], dtype="<i2")
    assert audio_decoder.peak(samples.tobytes()) == 32768
    assert audio_decoder.peak(b"") == 0


@pytest.mark.skipif(sys.version_info >= (3, 13), reason="audioop removed in Python 3.13")
def test_peak_matches_audioop():
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import audioop
    rng = np.random.default_rng(1)
    data = rng.integers(-32768, 32767, 4096, dtype=np.int16).tobytes()
    assert audio_decoder.peak(data) == audioop.max(data, 2)


class _OldPCM(object):
    """Mimics pyalsaaudio 0.8.4 (Debian bookworm): no keyword settings."""
    calls = []

    def __init__(self, pcm_type, mode, device):
        self.settings = {"device": device}

    def setchannels(self, value):
        self.settings["channels"] = value

    def setrate(self, value):
        self.settings["rate"] = value

    def setformat(self, value):
        self.settings["format"] = value

    def setperiodsize(self, value):
        self.settings["periodsize"] = value


class _NewPCM(object):
    """Mimics pyalsaaudio 0.9+ (Debian trixie)."""

    def __init__(self, pcm_type, mode, device, channels, rate, format, periodsize):
        self.settings = dict(device=device, channels=channels, rate=rate, format=format,
                             periodsize=periodsize)


class _FakeModule(object):
    def __init__(self, cls):
        self.PCM = cls


def test_open_pcm_old_pyalsaaudio():
    import alsa_compat
    pcm = alsa_compat.open_pcm(0, 0, "null", 2, 44100, 2, 2048, module=_FakeModule(_OldPCM))
    assert pcm.settings == dict(device="null", channels=2, rate=44100, format=2, periodsize=2048)


def test_open_pcm_new_pyalsaaudio():
    import alsa_compat
    pcm = alsa_compat.open_pcm(0, 0, "null", 1, 22050, 2, 1024, module=_FakeModule(_NewPCM))
    assert pcm.settings == dict(device="null", channels=1, rate=22050, format=2, periodsize=1024)


def test_open_pcm_real_null_device():
    aa = pytest.importorskip("alsaaudio")
    import alsa_compat
    try:
        pcm = alsa_compat.open_pcm(aa.PCM_PLAYBACK, aa.PCM_NORMAL, "null", 2, 44100,
                                   aa.PCM_FORMAT_S16_LE, 2048)
    except aa.ALSAAudioError as error:
        pytest.skip("ALSA null device not available: %s" % error)
    pcm.write(b"\0" * 2048 * 4)
    pcm.close()

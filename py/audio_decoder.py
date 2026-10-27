#!/usr/bin/env python3
#
# Licensed under the BSD license.  See full license in LICENSE file.
# http://www.lightshowpi.org/
#
"""Decode audio files to 16-bit PCM for LightShow Pi.

Replaces the unmaintained ``decoder.py`` fork (which bundled Windows codecs
and needed a separate command-line decoder per format) with ffmpeg, which is
packaged by Debian / Raspberry Pi OS and handles mp3, ogg, flac, m4a/aac,
wma, wav and more.

The object returned by :func:`open` behaves like :mod:`wave` read objects
(getnchannels, getsampwidth, getframerate, getnframes, readframes, close),
which is the interface synchronized_lights.py has always used.

Output is always signed 16-bit little-endian, 2 channels (mono files are
duplicated to both channels), at the file's original sample rate.
"""

import json
import os
import shutil
import subprocess
import wave

SAMPLE_WIDTH = 2
CHANNELS = 2


class DecoderError(Exception):
    """Raised with a user-readable message when a file can't be decoded."""


def find_tool(name):
    return shutil.which(name)


def probe(filename):
    """Return (sample_rate, duration_seconds) using ffprobe."""
    ffprobe = find_tool("ffprobe")
    if not ffprobe:
        raise DecoderError("ffprobe was not found. Install it with: sudo apt install ffmpeg")
    cmd = [ffprobe, "-v", "error", "-select_streams", "a:0",
           "-show_entries", "stream=sample_rate,duration:format=duration",
           "-of", "json", filename]
    try:
        out = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             check=False, timeout=60)
    except subprocess.TimeoutExpired:
        raise DecoderError("Timed out reading audio information from %s" % filename)
    if out.returncode != 0:
        raise DecoderError("Could not read audio from %s: %s"
                           % (filename, out.stderr.decode(errors="replace").strip()))
    info = json.loads(out.stdout.decode() or "{}")
    streams = info.get("streams") or []
    if not streams:
        raise DecoderError("%s does not contain an audio stream" % filename)
    stream = streams[0]
    sample_rate = int(stream.get("sample_rate") or 44100)
    duration = stream.get("duration") or info.get("format", {}).get("duration")
    try:
        duration = float(duration)
    except (TypeError, ValueError):
        duration = 0.0
    return sample_rate, duration


class FFmpegStream(object):
    """wave-like reader that streams PCM from an ffmpeg subprocess."""

    def __init__(self, filename):
        ffmpeg = find_tool("ffmpeg")
        if not ffmpeg:
            raise DecoderError("ffmpeg was not found. Install it with: sudo apt install ffmpeg")
        self.filename = filename
        self.sample_rate, duration = probe(filename)
        self.nframes = int(round(duration * self.sample_rate))
        cmd = [ffmpeg, "-nostdin", "-v", "error", "-i", filename,
               "-vn", "-f", "s16le", "-acodec", "pcm_s16le",
               "-ac", str(CHANNELS), "-ar", str(self.sample_rate), "pipe:1"]
        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)

    def getnchannels(self):
        return CHANNELS

    def getsampwidth(self):
        return SAMPLE_WIDTH

    def getframerate(self):
        return self.sample_rate

    def getnframes(self):
        return self.nframes

    def readframes(self, nframes):
        if self.process is None:
            return b""
        want = int(nframes) * CHANNELS * SAMPLE_WIDTH
        chunks = []
        remaining = want
        while remaining > 0:
            data = self.process.stdout.read(remaining)
            if not data:
                break
            chunks.append(data)
            remaining -= len(data)
        data = b"".join(chunks)
        # keep whole frames only
        frame_bytes = CHANNELS * SAMPLE_WIDTH
        return data[:len(data) - (len(data) % frame_bytes)]

    def close(self):
        if self.process is not None:
            try:
                self.process.stdout.close()
            except Exception:
                pass
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            self.process = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _is_plain_wav(filename):
    """16-bit stereo PCM WAV can be read directly without ffmpeg."""
    try:
        w = wave.open(filename, "rb")
    except Exception:
        return False
    try:
        return w.getsampwidth() == SAMPLE_WIDTH and w.getnchannels() == CHANNELS
    finally:
        w.close()


def open(filename, force_header=False):  # noqa: A001 - keeps decoder.open() name
    """Open an audio file for reading.  ``force_header`` is accepted for
    compatibility with the old decoder module and ignored."""
    if not os.path.isfile(filename):
        raise DecoderError("Audio file not found: %s" % filename)
    if filename.lower().endswith(".wav") and _is_plain_wav(filename):
        return wave.open(filename, "rb")
    return FFmpegStream(filename)


def peak(data):
    """Maximum absolute sample value of 16-bit PCM data.

    Drop-in replacement for ``audioop.max(data, 2)``; the audioop module was
    removed from Python 3.13."""
    import numpy as np
    if not data:
        return 0
    samples = np.frombuffer(data[:len(data) - (len(data) % 2)], dtype="<i2")
    if samples.size == 0:
        return 0
    return int(np.max(np.abs(samples.astype(np.int32))))

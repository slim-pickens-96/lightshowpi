#
# Licensed under the BSD license.  See full license in LICENSE file.
# http://www.lightshowpi.org/
#
"""Open ALSA PCM devices with any pyalsaaudio version LightShow Pi supports.

pyalsaaudio 0.9+ (Debian 13 "trixie": 0.10.0) accepts the stream settings as
keyword arguments to PCM().  Older releases - including python3-alsaaudio
0.8.4 in Debian 12 "bookworm" / Raspberry Pi OS Bookworm - raise
"TypeError: function takes at most 5 arguments" for that call and need the
setchannels()/setrate()/setformat()/setperiodsize() methods instead
(deprecated, but still present, in newer versions).
"""
import alsaaudio as aa


def open_pcm(pcm_type, mode, device, channels, rate, pcm_format, periodsize, module=aa):
    """Open and configure a PCM device; works with old and new pyalsaaudio."""
    try:
        return module.PCM(pcm_type, mode, device, channels=channels, rate=rate,
                          format=pcm_format, periodsize=periodsize)
    except TypeError:
        pass
    pcm = module.PCM(pcm_type, mode, device)
    pcm.setchannels(channels)
    pcm.setrate(rate)
    pcm.setformat(pcm_format)
    pcm.setperiodsize(periodsize)
    return pcm

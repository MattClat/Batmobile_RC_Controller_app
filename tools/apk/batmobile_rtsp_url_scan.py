#!/usr/bin/env python3
"""
batmobile_rtsp_url_scan.py — pull the app's REAL streaming URL and the ffmpeg
options its native client sets, out of librtspclient.so.

The video path is YETi CGI's RtspClient.cpp (ffmpeg-based). The exact URL and
any AVDictionary options are compiled-in C strings. This finds them and skips
the thousands of ffmpeg-internal symbols.

    python3 batmobile_rtsp_url_scan.py "G:\\path\\to\\extracted_apk"
    (or run inside the extracted-apk folder with no argument)
"""

import os
import re
import sys

PRINTABLE = re.compile(rb"[\x20-\x7e]{3,}")

# App-specific signal. URL pieces, host, ports, and the ffmpeg *option* names a
# custom client sets via av_dict_set before avformat_open_input.
WANT = [
    b"://", b"/live", b"/ch", b"ch00", b"ch01", b"ch0", b":554", b"554",
    b"192.168", b"rtsp", b"%s", b"%d",
    b"stimeout", b"timeout", b"max_delay", b"maxdelay", b"buffer_size",
    b"reorder_queue", b"rtsp_transport", b"rtsp_flags", b"fflags", b"nobuffer",
    b"probesize", b"analyzeduration", b"user-agent", b"user_agent",
    b"framedrop", b"sync", b"prefer_tcp", b"udp", b"tcp",
]

# Noise to drop: ffmpeg/libc++/toolchain internals.
DROP_PREFIX = (b"ff_", b"av", b"sws_", b"swr_", b"_Z", b"RTSP_STATUS",
               b"RTSP_STATE", b"RTSP_TRANSPORT", b"RTSP_LOWER", b"RTSP_SERVER",
               b"RTSP_MODE", b"RTSP_METHOD", b"RTSPStatus", b"RTSPState",
               b"RTSPTransport", b"RTSPMessage", b"RTSPStream", b"RTSPSource",
               b"libav", b"rtsp_read", b"rtsp_write", b"rtsp_parse",
               b"rtsp_send", b"rtsp_listen", b"rtsp_probe", b"rtsp_demuxer",
               b"rtsp_muxer", b"rtsp_src", b"rtsp_hd", b"nb_rtsp",
               b"lower_rtsp", b"prtsp", b"__")
DROP_CONTAINS = (b"XMLSchema", b"dashif", b"adobe.com", b"w3.org", b"iso.org",
                 b"microsoft.com", b"haxx.se", b"curl", b"schema", b"xmlns")


def interesting(s):
    sl = s.lower()
    if not any(w in sl for w in WANT):
        return False
    if s.startswith(DROP_PREFIX):
        return False
    if any(d in s for d in DROP_CONTAINS):
        return False
    # A bare "rtsp"/"tcp"/"udp" token alone isn't useful; want it in context.
    if len(s) < 5 and s.lower() in (b"rtsp", b"tcp", b"udp", b"554", b"%s", b"%d"):
        return False
    return True


def scan(path):
    with open(path, "rb") as f:
        data = f.read()
    seen, out = set(), []
    for m in PRINTABLE.finditer(data):
        s = m.group()
        if interesting(s) and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def find_target(root):
    hits = []
    if os.path.isfile(root):
        return [root]
    for dp, _, files in os.walk(root):
        for fn in files:
            if fn == "librtspclient.so":
                hits.append(os.path.join(dp, fn))
    return hits


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    libs = find_target(root)
    if not libs:
        print("Couldn't find librtspclient.so under", os.path.abspath(root))
        print('Pass the extracted-apk path or the .so directly.')
        return
    # Prefer the arm64 copy if both exist (usually more complete strings).
    libs.sort(key=lambda p: ("arm64" not in p, p))
    lib = libs[0]
    print("Scanning:", lib, "(%.1f MB)\n" % (os.path.getsize(lib) / 1e6))

    results = scan(lib)
    # Surface the most URL-like lines first.
    urlish = [s for s in results if b"://" in s or b"/live" in s or b"/ch" in s
              or b"192.168" in s or (b"%s" in s and b"/" in s)]
    if urlish:
        print("*** URL candidates ***")
        for s in urlish:
            print("   ", s.decode("latin-1"))
        print()
    print("*** other option/host strings ***")
    for s in results:
        if s in urlish:
            continue
        print("   ", s.decode("latin-1"))
    print("\nPaste the URL candidates back to Claude.")


if __name__ == "__main__":
    main()

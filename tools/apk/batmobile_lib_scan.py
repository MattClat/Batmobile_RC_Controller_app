#!/usr/bin/env python3
"""
batmobile_lib_scan.py — pull the camera's real streaming details out of the
app's NATIVE libraries.

The video URL/port/protocol is NOT in the app's C# (we checked the IL2CPP
metadata). That means it's a native camera-SDK .so. This scans every .so in
the extracted APK for streaming-related strings.

Point it at your extracted APK folder (the one containing lib/...):

    python3 batmobile_lib_scan.py "G:\\path\\to\\extracted_apk"

or just run it from inside that folder:

    python3 batmobile_lib_scan.py

Stdlib only.
"""

import os
import re
import sys

KEYWORDS = [
    b"rtsp", b"rtp", b"/live", b"ch00", b"ch0", b"554", b".sdp", b"stream",
    b"http://", b"https://", b"sendto", b"recvfrom", b"connect", b"socket",
    b"preview", b"snapshot", b"livestream", b".cgi", b"cmd=", b"param=",
    b"h264", b"h.264", b"mjpeg", b"avc", b"192.168", b"start", b"stop",
    b"enable", b"port", b"channel", b"session", b"describe", b"play",
    b"getvideo", b"setvideo", b"transport", b"unicast", b"multicast",
]

# The really juicy ones — always surface these first.
PRIORITY = [b"rtsp", b"/live", b"192.168", b"ch0", b"554", b".sdp",
            b"livestream", b"://"]

PRINTABLE = re.compile(rb"[\x20-\x7e]{4,}")


def scan_file(path):
    with open(path, "rb") as f:
        data = f.read()
    hits = []
    for m in PRINTABLE.finditer(data):
        s = m.group()
        sl = s.lower()
        if any(k in sl for k in KEYWORDS):
            hits.append(s)
    return hits


def find_libs(root):
    libs = []
    if os.path.isfile(root) and root.endswith(".so"):
        return [root]
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if fn.endswith(".so"):
                libs.append(os.path.join(dirpath, fn))
    return libs


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    libs = find_libs(root)
    if not libs:
        print("No .so files found under:", os.path.abspath(root))
        print("Point me at your extracted APK folder, e.g.:")
        print('  python3 batmobile_lib_scan.py "C:\\path\\to\\extracted_apk"')
        return

    print("Found %d native library file(s):" % len(libs))
    for l in libs:
        print("  ", l, "(%.1f MB)" % (os.path.getsize(l) / 1e6))
    print()

    for lib in libs:
        hits = scan_file(lib)
        if not hits:
            continue
        name = os.path.basename(lib)
        # de-dupe, keep order
        seen = set()
        uniq = []
        for h in hits:
            if h not in seen:
                seen.add(h)
                uniq.append(h)

        priority = [h for h in uniq if any(p in h.lower() for p in PRIORITY)]
        print("=" * 60)
        print("%s — %d matching strings" % (name, len(uniq)))
        print("=" * 60)
        if priority:
            print("  *** HIGH-VALUE (url/host/path) ***")
            for h in priority:
                print("   >>", h.decode("latin-1"))
            print()
        # show the rest, but cap the noise
        others = [h for h in uniq if h not in priority]
        for h in others[:200]:
            print("     ", h.decode("latin-1"))
        if len(others) > 200:
            print("      ... (%d more)" % (len(others) - 200))
        print()

    print("Paste the HIGH-VALUE lines (and anything with rtsp/live/cmd) back to Claude.")


if __name__ == "__main__":
    main()

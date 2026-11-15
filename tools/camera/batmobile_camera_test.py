#!/usr/bin/env python3
"""
batmobile_camera_test.py — settle whether the car's camera actually pushes
video, with no stuck-session races.

It reproduces the original app's camera startup (the CGI calls it made before
opening RTSP), then makes ONE clean capture attempt and saves a still frame.

    POWER-CYCLE THE CAR FIRST (off, 10s, on) so no stale RTSP session is held.
    Then, joined to E6F4-BATMOBILE:

        python3 batmobile_camera_test.py

Needs: Python 3, and ffmpeg on PATH (ffmpeg + ffprobe).
Only stdlib is used for the HTTP pre-roll.
"""

import shutil
import subprocess
import sys
import time
import urllib.request

CAR = "192.168.201.1"
RTSP = "rtsp://%s/live/ch00_0" % CAR

# The app's camera warm-up, in order. Failures here are non-fatal (we log them).
PREROLL = [
    "http://%s/custom/getDeviceInformation.cgi" % CAR,
    "http://%s/custom/getVideoProfiles.cgi" % CAR,
    "http://%s/custom/setVideoProfiles.cgi?stream0Bitrate=2048" % CAR,
    "http://%s/isp/awb_ctl.cgi?ENABLE=1" % CAR,
]


def http_get(url, timeout=4):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            body = r.read(400).decode("utf-8", "replace").strip()
            return r.status, body
    except Exception as e:
        return None, str(e)


def preroll():
    print("[1] Waking the camera (app's CGI startup sequence)...")
    for url in PREROLL:
        status, body = http_get(url)
        tag = url.split("/")[-1]
        if status == 200:
            print("    OK   %-28s %s" % (tag, body[:80]))
        else:
            print("    ??   %-28s %s" % (tag, body[:80]))
    print()


def grab(transport, out):
    """One capture attempt. Returns True if a real frame was written."""
    ff = shutil.which("ffmpeg")
    if not ff:
        print("ffmpeg not found on PATH. Install it (winget install ffmpeg) and retry.")
        sys.exit(1)
    cmd = [
        ff, "-hide_banner", "-loglevel", "warning",
        "-rtsp_transport", transport,
        "-analyzeduration", "10000000",
        "-probesize", "10000000",
        "-i", RTSP,
        "-frames:v", "1", "-q:v", "2", "-y", out,
    ]
    print("[*] Trying %s (up to ~25s, single client)..." % transport.upper())
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired:
        print("    no frame within 25s (stream negotiated but no video arrived).")
        return False
    dt = time.time() - t0
    import os
    ok = os.path.exists(out) and os.path.getsize(out) > 1000
    if ok:
        print("    GOT A FRAME in %.1fs -> %s (%d bytes)" % (dt, out, os.path.getsize(out)))
    else:
        err = (p.stderr or "").strip().splitlines()
        print("    no frame in %.1fs." % dt)
        for line in err[-6:]:
            print("      | " + line)
    return ok


def main():
    print("=" * 58)
    print("Batmobile camera test — one clean shot, no session races")
    print("=" * 58)
    print("Did you power-cycle the car in the last minute? If not, do it now.\n")

    preroll()

    # TCP first (immune to firewall + UDP fragmentation), then UDP.
    if grab("tcp", "frame_tcp.jpg"):
        done("frame_tcp.jpg", "TCP")
        return
    print("    (waiting 65s for the camera's single session to time out...)")
    time.sleep(65)
    if grab("udp", "frame_udp.jpg"):
        done("frame_udp.jpg", "UDP")
        return

    print("\nRESULT: camera negotiated but delivered no frames on either transport.")
    print("That points away from VLC/player config and toward the camera needing")
    print("something else in its warm-up. Next step is to capture exactly what the")
    print("original app sends — tell Claude and we'll set up a packet capture.")


def done(path, how):
    print("\nRESULT: SUCCESS over %s. The camera streams fine (saved %s)." % (how, path))
    print("It was never a hardware problem — just session/transport handling.")
    print("Tell Claude it worked over %s and we'll wire live video into the" % how)
    print("controller window and lock in this exact startup sequence.")


if __name__ == "__main__":
    main()

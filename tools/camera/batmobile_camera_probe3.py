#!/usr/bin/env python3
"""
batmobile_camera_probe3.py — hunt for whatever starts the encoder.

What we now know:
  * Only ports 80 and 554 are real. No ONVIF, no proprietary video port.
  * /live/<anything> returns 200, so the RTSP path is not the problem.
  * The SDP is a static template (claims 5 Mbps / Baseline 3.0 while the
    encoder reports 2048 kbps / High 4.0). The RTSP server is a thin shim.
  * The app uses a SECOND http api: /?cmd=NNN&param=X&value=Y  (only
    cmd=301 / network_ap is known). That is the best remaining lead.

This script is deliberately GENTLE - one connection at a time with pauses,
because the last port scan wedged the camera's little web server.

    POWER-CYCLE THE CAR FIRST, join E6F4-BATMOBILE, then:

        python3 batmobile_camera_probe3.py

    Optional, read the warning below first:
        python3 batmobile_camera_probe3.py --enumerate-cmd

Stdlib only.
"""

import socket
import re
import sys
import time
import urllib.request

CAR = "192.168.201.1"
BASE = "http://%s" % CAR
PAUSE = 0.25


def get(url, timeout=5):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "batprobe"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read(1500)
    except Exception as e:
        return None, "", str(e)[:70].encode()


def alive():
    """Confirm the web server is actually up before trusting any negatives."""
    print("=" * 60)
    print("[0] Is the HTTP server responding at all?")
    print("=" * 60)
    for attempt in range(3):
        st, ct, body = get(BASE + "/custom/getDeviceInformation.cgi")
        if st == 200:
            print("   OK - known-good CGI answered.")
            print("   " + body.decode("latin-1", "replace")[:150])
            return True
        print("   attempt %d failed: %s" % (attempt + 1,
                                            body.decode("latin-1", "replace")))
        time.sleep(3)
    print("\n   The web server is NOT responding. Power-cycle the car and")
    print("   rerun - every result below would be a false negative otherwise.")
    return False


def cgi_names():
    """Brute a list of plausible CGI names under the two known prefixes."""
    print("\n" + "=" * 60)
    print("[1] CGI name discovery under /custom/ and /isp/")
    print("=" * 60)
    names = [
        # stream / encoder control - what we're actually hunting
        "startStream.cgi", "stopStream.cgi", "setStream.cgi", "getStream.cgi",
        "streamCtrl.cgi", "setStreamCtrl.cgi", "getStreamCtrl.cgi",
        "startPreview.cgi", "stopPreview.cgi", "setPreview.cgi",
        "startRecord.cgi", "stopRecord.cgi", "setRecord.cgi", "getRecord.cgi",
        "setVideoCtrl.cgi", "getVideoCtrl.cgi", "videoCtrl.cgi",
        "setEncode.cgi", "getEncode.cgi", "encodeCtrl.cgi",
        "setRtspCtrl.cgi", "getRtspCtrl.cgi", "rtsp_ctl.cgi",
        "setLiveCtrl.cgi", "getLiveCtrl.cgi", "live_ctl.cgi",
        # snapshots - a fallback video path if one exists
        "getSnapShot.cgi", "snapshot.cgi", "getImage.cgi", "capture.cgi",
        "getJpeg.cgi", "jpeg.cgi",
        # state / info - helps us understand the device
        "getStatus.cgi", "getSystemStatus.cgi", "getDeviceStatus.cgi",
        "getSDInfo.cgi", "getStorageInfo.cgi", "getDiskInfo.cgi",
        "getVideoProfiles.cgi", "getImageSetting.cgi", "getNetworkInfo.cgi",
        "getWifiConfig.cgi", "getParam.cgi", "getAllParam.cgi",
        "reboot.cgi", "getVersion.cgi",
    ]
    hits = []
    for prefix in ("/custom/", "/isp/"):
        for n in names:
            url = BASE + prefix + n
            st, ct, body = get(url, timeout=4)
            if st == 200:
                txt = body.decode("latin-1", "replace").strip()
                flag = ""
                if body[:2] == b"\xff\xd8":
                    flag = "   <<< JPEG IMAGE - a live frame!"
                hits.append((prefix + n, txt))
                print("   200  %-34s %s%s" % (prefix + n, txt[:70], flag))
            time.sleep(PAUSE)
    if not hits:
        print("   (no new endpoints found)")
    return hits


def cmd_known():
    """Poke the numeric API with the one command we know, read-only."""
    print("\n" + "=" * 60)
    print("[2] The numeric ?cmd= API (read-only probes)")
    print("=" * 60)
    # No &value= -> should be a query, not a write.
    probes = [
        "/?cmd=301",
        "/?cmd=301&param=network_ap",
        "/?custom=1&cmd=301",
    ]
    for p in probes:
        st, ct, body = get(BASE + p, timeout=4)
        txt = body.decode("latin-1", "replace").strip()
        print("   %-32s -> %s  %s" % (p, st, txt[:70]))
        time.sleep(PAUSE)
    print("\n   If these return structured data, the API is live and")
    print("   enumeration (--enumerate-cmd) is worth doing.")


def cmd_enumerate(lo=1, hi=999):
    """
    Walk cmd numbers looking for anything that responds.

    !! READ THIS !!  cmd=301 is known to SET the wifi ap config. Other
    numbers may also write settings even without &value=. If the camera's
    wifi password changes, recover with the factory reset: paperclip in the
    hole in the battery bay, hold 10 seconds while powered on. That restores
    SSID E6F4-BATMOBILE / password BATMOBILE1.
    """
    print("\n" + "=" * 60)
    print("[3] Enumerating ?cmd=%d..%d" % (lo, hi))
    print("=" * 60)
    print("   (skipping 301, the known wifi-write command)")
    interesting = []
    for n in range(lo, hi + 1):
        if n == 301:
            continue
        st, ct, body = get(BASE + "/?cmd=%d" % n, timeout=3)
        if st == 200:
            txt = body.decode("latin-1", "replace").strip()
            if txt and "not support" not in txt.lower():
                interesting.append((n, txt))
                print("   cmd=%-4d %s" % (n, txt[:80]))
        if n % 50 == 0:
            print("   ... at %d" % n)
        time.sleep(0.08)
    print("\n   responded: %d commands" % len(interesting))
    return interesting


# ------------------------------------------------------------------ RTSP

def rtsp_session_test():
    """
    Full RTSP session, but this time: try SET_PARAMETER before PLAY, send
    GET_PARAMETER keepalives, and wait much longer. Some minimal servers
    only start pushing once they see the session is being maintained.
    """
    print("\n" + "=" * 60)
    print("[4] RTSP with SET_PARAMETER + keepalive, TCP interleaved, 30s")
    print("=" * 60)
    url = "rtsp://%s/live/ch00_0" % CAR
    try:
        s = socket.create_connection((CAR, 554), timeout=6)
    except OSError as e:
        print("   connect failed:", e)
        return
    cseq = [0]

    def req(method, target, extra=None, read=True):
        cseq[0] += 1
        lines = ["%s %s RTSP/1.0" % (method, target), "CSeq: %d" % cseq[0],
                 "User-Agent: batprobe"]
        for k, v in (extra or {}).items():
            lines.append("%s: %s" % (k, v))
        s.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        if not read:
            return "", ""
        s.settimeout(5)
        data = b""
        try:
            while b"\r\n\r\n" not in data:
                c = s.recv(4096)
                if not c:
                    break
                data += c
        except socket.timeout:
            pass
        head, _, rest = data.partition(b"\r\n\r\n")
        return head.decode("latin-1"), rest

    h, _ = req("DESCRIBE", url, {"Accept": "application/sdp"})
    print("   DESCRIBE:", h.splitlines()[0] if h else "?")
    h, _ = req("SETUP", url + "/trackID=0",
               {"Transport": "RTP/AVP/TCP;unicast;interleaved=0-1"})
    print("   SETUP   :", h.splitlines()[0] if h else "?")
    m = re.search(r"Session:\s*([^;\r\n]+)", h, re.I)
    sess = m.group(1).strip() if m else ""
    print("   Session :", sess or "(none)")

    h, _ = req("SET_PARAMETER", url, {"Session": sess,
                                      "Content-Length": "0"})
    print("   SET_PARAM:", h.splitlines()[0] if h else "?")

    h, leftover = req("PLAY", url, {"Session": sess, "Range": "npt=0.000-"})
    print("   PLAY    :", h.splitlines()[0] if h else "?")
    if leftover:
        print("   (%d bytes arrived with the PLAY response)" % len(leftover))

    print("   listening 30s, sending GET_PARAMETER keepalive every 8s...")
    s.settimeout(1.0)
    total, dollars = len(leftover), leftover.count(b"$")
    end = time.time() + 30
    nextka = time.time() + 8
    while time.time() < end:
        if time.time() > nextka:
            try:
                req("GET_PARAMETER", url, {"Session": sess,
                                           "Content-Length": "0"}, read=False)
            except Exception:
                pass
            nextka = time.time() + 8
        try:
            c = s.recv(8192)
            if not c:
                break
            total += len(c)
            dollars += c.count(b"$")
        except socket.timeout:
            pass
        except Exception:
            break
    try:
        req("TEARDOWN", url, {"Session": sess}, read=False)
    except Exception:
        pass
    s.close()
    print("   received %d bytes total (%d '$' interleave markers)"
          % (total, dollars))
    if total > 2000:
        print("   >>> MEDIA IS FLOWING. The keepalive/SET_PARAMETER did it.")
    else:
        print("   >>> still nothing.")


def main():
    do_enum = "--enumerate-cmd" in sys.argv
    print("Batmobile camera probe 3 —", CAR)
    print("Gentle mode: one connection at a time.\n")
    if not alive():
        return
    cgi_names()
    cmd_known()
    if do_enum:
        cmd_enumerate()
    else:
        print("\n   (skipping cmd enumeration; pass --enumerate-cmd to run it,")
        print("    after reading the warning in this file's source)")
    rtsp_session_test()
    print("\nDone. Paste the whole output back to Claude.")


if __name__ == "__main__":
    main()

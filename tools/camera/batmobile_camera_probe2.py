#!/usr/bin/env python3
"""
batmobile_camera_probe2.py — find the camera's REAL video path.

Four things we never checked:
  1. What ports are actually open on the camera (never scanned).
  2. The full SDP + RTSP response headers (Content-Base reveals the
     canonical URL if we've been asking for the wrong one).
  3. Whether the server validates paths at all. If a deliberately bogus
     path returns a valid SDP, then /live/ch00_0 means nothing and the
     real stream lives somewhere else.
  4. HTTP snapshot / MJPEG endpoints and ONVIF (which will hand us the
     correct stream URI on request).

Power-cycle the car, join E6F4-BATMOBILE, then:
    python3 batmobile_camera_probe2.py

Stdlib only.
"""

import re
import socket
import sys
import time
import urllib.request

CAR = "192.168.201.1"

# ---------------------------------------------------------------- port scan

SCAN_PORTS = sorted(set(
    list(range(1, 1100)) +
    [1935, 2000, 2020, 3702, 4000, 5000, 5050, 6000, 6001, 6002, 7070, 7080,
     8000, 8001, 8080, 8081, 8090, 8181, 8192, 8554, 8800, 8888, 8899, 9000,
     9090, 9527, 9999, 10000, 10554, 11111, 12345, 34567, 34599, 50000]))


def scan_ports():
    print("=" * 60)
    print("[1] TCP port scan of", CAR)
    print("=" * 60)
    import threading
    from queue import Queue
    found, lock, q = [], threading.Lock(), Queue()

    def worker():
        while True:
            p = q.get()
            if p is None:
                return
            s = socket.socket()
            s.settimeout(0.5)
            try:
                if s.connect_ex((CAR, p)) == 0:
                    banner = b""
                    try:
                        s.settimeout(0.8)
                        banner = s.recv(120)
                    except Exception:
                        pass
                    with lock:
                        found.append((p, banner))
                        tag = (" | " + repr(banner[:60])) if banner else ""
                        print("   OPEN %-6d%s" % (p, tag))
            except Exception:
                pass
            finally:
                s.close()
                q.task_done()

    ts = [threading.Thread(target=worker, daemon=True) for _ in range(150)]
    for t in ts:
        t.start()
    for p in SCAN_PORTS:
        q.put(p)
    q.join()
    for _ in ts:
        q.put(None)
    print("   open ports:", [p for p, _ in found] or "none")
    return [p for p, _ in found]


# ---------------------------------------------------------------- RTSP

def rtsp_describe(path, port=554):
    """DESCRIBE one path; return (status_line, headers, sdp)."""
    url = "rtsp://%s%s" % (CAR, path) if port == 554 else \
          "rtsp://%s:%d%s" % (CAR, port, path)
    try:
        s = socket.create_connection((CAR, port), timeout=5)
    except OSError as e:
        return ("connect failed: %s" % e, "", "")
    try:
        req = ("DESCRIBE %s RTSP/1.0\r\nCSeq: 1\r\n"
               "Accept: application/sdp\r\nUser-Agent: batprobe\r\n\r\n" % url)
        s.sendall(req.encode())
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
        head = head.decode("latin-1")
        clen = 0
        m = re.search(r"Content-Length:\s*(\d+)", head, re.I)
        if m:
            clen = int(m.group(1))
        body = rest
        while len(body) < clen:
            try:
                c = s.recv(4096)
            except socket.timeout:
                break
            if not c:
                break
            body += c
        lines = head.splitlines()
        return (lines[0] if lines else "(empty)",
                "\n".join(lines[1:]),
                body.decode("latin-1", "replace"))
    finally:
        s.close()


def rtsp_options(port=554):
    print("\n" + "=" * 60)
    print("[2] RTSP OPTIONS (what methods the server admits to)")
    print("=" * 60)
    try:
        s = socket.create_connection((CAR, port), timeout=5)
    except OSError as e:
        print("   connect failed:", e)
        return
    try:
        s.sendall(("OPTIONS rtsp://%s/ RTSP/1.0\r\nCSeq: 1\r\n\r\n" % CAR).encode())
        s.settimeout(5)
        print("   " + s.recv(2048).decode("latin-1", "replace").strip()
              .replace("\n", "\n   "))
    except Exception as e:
        print("   error:", e)
    finally:
        s.close()


def path_validation_test():
    """The key test: does a garbage path also return a valid SDP?"""
    print("\n" + "=" * 60)
    print("[3] Path validation test")
    print("=" * 60)
    real = "/live/ch00_0"
    bogus = "/this_path_cannot_possibly_exist_9z9z"
    for label, p in (("known", real), ("BOGUS", bogus)):
        st, hd, sdp = rtsp_describe(p)
        print("   %-6s %-40s -> %s" % (label, p, st))
        time.sleep(0.5)
    st_r, _, sdp_r = rtsp_describe(real)
    time.sleep(0.5)
    st_b, _, sdp_b = rtsp_describe(bogus)
    if "200" in st_b:
        print("\n   >>> The server returns 200 + SDP for a path that CANNOT exist.")
        print("   >>> It is not validating paths. /live/ch00_0 is therefore")
        print("   >>> unproven -- the real stream may be at a different URL,")
        print("   >>> or this server hands out a template SDP for everything.")
        if sdp_b.strip() == sdp_r.strip():
            print("   >>> (bogus and known SDPs are byte-identical)")
    else:
        print("\n   >>> Server rejects bogus paths, so /live/ch00_0 is a real path.")


def dump_sdp():
    print("\n" + "=" * 60)
    print("[4] Full DESCRIBE response for /live/ch00_0")
    print("=" * 60)
    st, hd, sdp = rtsp_describe("/live/ch00_0")
    print("   status:", st)
    print("   --- headers ---")
    for line in hd.splitlines():
        print("   " + line)
    print("   --- SDP ---")
    for line in sdp.splitlines():
        print("   " + line)
    ntracks = sdp.count("m=")
    print("   --- media tracks advertised: %d ---" % ntracks)
    if ntracks > 1:
        print("   NOTE: more than one track. Some servers refuse to stream")
        print("   until EVERY advertised track has been SETUP.")


def try_paths():
    print("\n" + "=" * 60)
    print("[5] Alternate stream paths")
    print("=" * 60)
    paths = [
        "/", "/live", "/live/", "/live/ch0", "/live/ch00", "/live/ch00_0",
        "/live/ch01_0", "/live/av0", "/live/main", "/live/sub",
        "/11", "/12", "/0", "/1", "/ch0", "/ch0_0", "/ch1",
        "/video", "/video0", "/video1", "/stream", "/stream0", "/stream1",
        "/h264", "/h264/ch1/main/av_stream", "/media/video1", "/mainstream",
        "/onvif1", "/profile1", "/cam/realmonitor?channel=1&subtype=0",
    ]
    for p in paths:
        st, hd, sdp = rtsp_describe(p)
        code = st.split()[1] if len(st.split()) > 1 else "?"
        base = ""
        m = re.search(r"Content-Base:\s*(.+)", hd, re.I)
        if m:
            base = "  Content-Base: " + m.group(1).strip()
        marker = " <<<" if ("200" in st and "m=video" in sdp) else ""
        print("   %-38s %s%s%s" % (p, code, base, marker))
        time.sleep(0.35)


# ---------------------------------------------------------------- HTTP

def http_get(url, timeout=4):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read(3000)
    except Exception as e:
        return None, "", str(e).encode()


def http_endpoints(ports):
    print("\n" + "=" * 60)
    print("[6] HTTP snapshot / MJPEG / CGI discovery")
    print("=" * 60)
    paths = [
        "/custom/getSnapShot.cgi", "/custom/snapshot.cgi", "/custom/getImage.cgi",
        "/custom/getVideoStream.cgi", "/custom/startStream.cgi",
        "/custom/setStreamCtrl.cgi", "/custom/getStreamCtrl.cgi",
        "/isp/getSnapShot.cgi", "/isp/snapshot.cgi",
        "/snapshot.cgi", "/snapshot.jpg", "/snap.jpg", "/jpg/image.jpg",
        "/image.jpg", "/cgi-bin/snapshot.cgi", "/cgi-bin/hi3510/snap.cgi",
        "/videostream.cgi", "/mjpegstream.cgi", "/video.mjpg", "/mjpg/video.mjpg",
        "/live.jpg", "/tmpfs/snap.jpg", "/tmpfs/auto.jpg",
        "/custom/getDeviceInformation.cgi",   # known-good control
    ]
    web_ports = [p for p in (80, 8080, 8000, 8081, 8090) if p in ports] or [80]
    for wp in web_ports:
        for path in paths:
            url = "http://%s%s" % (CAR, path) if wp == 80 else \
                  "http://%s:%d%s" % (CAR, wp, path)
            st, ctype, body = http_get(url)
            if st == 200:
                kind = ctype or "?"
                if body[:2] == b"\xff\xd8":
                    kind = "JPEG IMAGE  <<< this is a live frame"
                print("   200  %-42s %s (%d bytes)" % (path, kind, len(body)))
            time.sleep(0.05)


def onvif(ports):
    print("\n" + "=" * 60)
    print("[7] ONVIF probe (asks the device for its own stream URI)")
    print("=" * 60)
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
        '<s:Body><GetProfiles xmlns="http://www.onvif.org/ver10/media/wsdl"/>'
        '</s:Body></s:Envelope>'
    ).encode()
    cands = [(p, "/onvif/device_service") for p in
             (80, 8000, 8080, 8899, 2020, 5000, 8090) if p in ports]
    cands += [(80, "/onvif/media_service"), (8899, "/onvif/device_service")]
    seen = set()
    for port, path in cands:
        key = (port, path)
        if key in seen:
            continue
        seen.add(key)
        url = "http://%s:%d%s" % (CAR, port, path)
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/soap+xml; charset=utf-8"})
        try:
            with urllib.request.urlopen(req, timeout=4) as r:
                text = r.read(2000).decode("latin-1", "replace")
            print("   %s -> %d" % (url, r.status))
            print("   " + text[:600].replace("\n", "\n   "))
            print("   >>> ONVIF is alive. It can tell us the real stream URI.")
        except Exception as e:
            print("   %s -> %s" % (url, str(e)[:60]))


def main():
    print("Batmobile camera probe 2 — target", CAR)
    print("Make sure you're joined to E6F4-BATMOBILE and the car is powered on.\n")
    ports = scan_ports()
    rtsp_options()
    dump_sdp()
    path_validation_test()
    try_paths()
    http_endpoints(ports)
    onvif(ports)
    print("\nDone. Paste the whole output back to Claude.")


if __name__ == "__main__":
    main()

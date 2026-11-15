#!/usr/bin/env python3
"""
batmobile_rtsp_probe.py — find out WHY the camera negotiates RTSP but sends
no video. Pure standard library; no ffmpeg needed.

It performs the RTSP handshake by hand (OPTIONS / DESCRIBE / SETUP / PLAY),
prints exactly what the camera agrees to, then listens for real RTP media.
It tests UDP first, tears down, then tests TCP-interleaved.

    Power-cycle the car, join E6F4-BATMOBILE, then:
        python3 batmobile_rtsp_probe.py

What we learn:
  * Does the camera send ANY RTP packets after PLAY?  (UDP)
  * If UDP: from which server port, and does it match what it promised?
  * Does the camera support RTP/AVP/TCP interleaving at all?  (TCP)
This decides whether the fix is a client-port/transport workaround or whether
we need to capture the original app.
"""

import re
import socket
import sys
import time

CAR = "192.168.201.1"
PORT = 554
URL = "rtsp://%s/live/ch00_0" % CAR


def recv_response(sock):
    sock.settimeout(6)
    data = b""
    try:
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
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
            chunk = sock.recv(4096)
        except socket.timeout:
            break
        if not chunk:
            break
        body += chunk
    return head, body.decode("latin-1", "replace")


def request(sock, method, url, cseq, extra=None):
    lines = ["%s %s RTSP/1.0" % (method, url), "CSeq: %d" % cseq,
             "User-Agent: batprobe/1.0"]
    for k, v in (extra or {}).items():
        lines.append("%s: %s" % (k, v))
    sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
    return recv_response(sock)


def status(head):
    return head.splitlines()[0] if head else "(no response)"


def get(head, field):
    m = re.search(r"^%s:\s*(.+)$" % re.escape(field), head, re.I | re.M)
    return m.group(1).strip() if m else None


def bind_rtp_pair():
    """Get an even RTP port with the RTCP port right after it."""
    for _ in range(20):
        rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rtp.bind(("", 0))
        p = rtp.getsockname()[1]
        if p % 2:  # want even RTP port
            rtp.close()
            continue
        rtcp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            rtcp.bind(("", p + 1))
            return rtp, rtcp, p
        except OSError:
            rtp.close()
            rtcp.close()
    # fallback: any port
    rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rtp.bind(("", 0))
    return rtp, None, rtp.getsockname()[1]


def control_url(sdp):
    """Find the media-level control attribute for the video track."""
    ctrl = None
    in_video = False
    for line in sdp.splitlines():
        if line.startswith("m="):
            in_video = line.startswith("m=video")
        if in_video and line.startswith("a=control:"):
            ctrl = line.split(":", 1)[1].strip()
    if not ctrl or ctrl == "*":
        return URL
    if ctrl.startswith("rtsp://"):
        return ctrl
    return URL + "/" + ctrl


def test_udp():
    print("\n=== UDP test ===")
    s = socket.create_connection((CAR, PORT), timeout=6)
    cseq = 1
    h, _ = request(s, "OPTIONS", URL, cseq); print("OPTIONS :", status(h))
    cseq += 1
    h, sdp = request(s, "DESCRIBE", URL, cseq, {"Accept": "application/sdp"})
    print("DESCRIBE:", status(h))
    if "m=video" not in sdp:
        print("  no SDP video track returned; raw head:\n ", status(h))
    setup_url = control_url(sdp)
    print("  control URL:", setup_url)

    rtp, rtcp, cport = bind_rtp_pair()
    rtp.settimeout(1.0)
    cseq += 1
    h, _ = request(s, "SETUP", setup_url, cseq,
                   {"Transport": "RTP/AVP;unicast;client_port=%d-%d" % (cport, cport + 1)})
    print("SETUP   :", status(h))
    tp = get(h, "Transport")
    sess = get(h, "Session")
    print("  our client_port :", "%d-%d" % (cport, cport + 1))
    print("  server Transport:", tp)
    print("  Session         :", sess)
    if sess:
        sess = sess.split(";")[0].strip()
    cseq += 1
    h, _ = request(s, "PLAY", URL, cseq,
                   {"Session": sess or "", "Range": "npt=0.000-"})
    print("PLAY    :", status(h))

    print("  listening 6s for RTP media...")
    pkts, byts, ports = 0, 0, set()
    t_end = time.time() + 6
    while time.time() < t_end:
        try:
            d, addr = rtp.recvfrom(2048)
            pkts += 1
            byts += len(d)
            ports.add(addr[1])
        except socket.timeout:
            pass
    try:
        request(s, "TEARDOWN", URL, cseq + 1, {"Session": sess or ""})
    except Exception:
        pass
    s.close(); rtp.close()
    if rtcp:
        rtcp.close()
    if pkts:
        print("  >>> RECEIVED %d RTP packets, %d bytes, from server port(s) %s"
              % (pkts, byts, sorted(ports)))
        print("  >>> The camera DOES stream. This is a player/depacketizer issue.")
    else:
        print("  >>> ZERO RTP packets. The camera accepted PLAY but sent no media.")
    return pkts > 0


def test_tcp():
    print("\n=== TCP-interleaved test ===")
    s = socket.create_connection((CAR, PORT), timeout=6)
    cseq = 1
    request(s, "OPTIONS", URL, cseq)
    cseq += 1
    h, sdp = request(s, "DESCRIBE", URL, cseq, {"Accept": "application/sdp"})
    setup_url = control_url(sdp)
    cseq += 1
    h, _ = request(s, "SETUP", setup_url, cseq,
                   {"Transport": "RTP/AVP/TCP;unicast;interleaved=0-1"})
    print("SETUP   :", status(h))
    tp = get(h, "Transport")
    sess = get(h, "Session")
    print("  server Transport:", tp)
    accepted = tp and ("TCP" in tp or "interleaved" in tp.lower())
    print("  interleaving accepted:", "YES" if accepted else "NO (camera ignored TCP request)")
    if sess:
        sess = sess.split(";")[0].strip()
    cseq += 1
    h, _ = request(s, "PLAY", URL, cseq, {"Session": sess or ""})
    print("PLAY    :", status(h))

    print("  listening 6s for interleaved media ($ frames)...")
    s.settimeout(1.0)
    byts, frames = 0, 0
    t_end = time.time() + 6
    while time.time() < t_end:
        try:
            chunk = s.recv(4096)
            if not chunk:
                break
            byts += len(chunk)
            frames += chunk.count(b"$")
        except socket.timeout:
            pass
    try:
        request(s, "TEARDOWN", URL, cseq + 1, {"Session": sess or ""})
    except Exception:
        pass
    s.close()
    if byts:
        print("  >>> RECEIVED %d bytes of interleaved data. Camera streams over TCP." % byts)
    else:
        print("  >>> ZERO interleaved bytes.")
    return byts > 0


def main():
    print("=" * 58)
    print("Batmobile RTSP probe —", URL)
    print("=" * 58)
    try:
        udp_ok = test_udp()
        if not udp_ok:
            tcp_ok = test_tcp()
    except ConnectionRefusedError:
        print("Port 554 refused — is the car on and are you joined to its WiFi?")
        sys.exit(1)
    except OSError as e:
        print("Network error:", e)
        sys.exit(1)
    print("\nPaste this whole output back to Claude.")


if __name__ == "__main__":
    main()

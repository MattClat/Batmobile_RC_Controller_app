#!/usr/bin/env python3
"""
batmobile_camera_probe4.py — is the camera sending RTP somewhere else?

Everything client-side is now ruled out: transport, path, firewall,
control-channel, competing viewers. And the app sends no start-encoder
command over HTTP, so it starts video with plain RTSP - the same thing we
do. That leaves one big untested possibility:

    the server echoes our requested transport but actually sends RTP to a
    hardcoded destination (a fixed port, or a fixed client IP like .2).

So this script:
  1. reports the laptop's IP on the car's network
  2. opens a wide net of UDP listeners on ports these modules commonly
     hardcode, PLUS the port the server negotiates
  3. sends PLAY and reports which port (if any) receives anything
  4. repeats with an explicit  destination=<our ip>  in the Transport
     header, which some servers honour

Run it, then read the verdict at the bottom.

    POWER-CYCLE THE CAR, join E6F4-BATMOBILE, then:
        python3 batmobile_camera_probe4.py

Stdlib only.
"""

import re
import socket
import time

CAR = "192.168.201.1"
URL = "rtsp://%s/live/ch00_0" % CAR
TRACK = URL + "/trackID=0"

# Ports these cheap encoders are known to hardcode for RTP.
FIXED_PORTS = [5004, 5006, 6970, 6971, 6972, 6974, 8000, 8002, 9000,
               1234, 5000, 5002, 10000, 10002, 50000, 51000]


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((CAR, 9))
        return s.getsockname()[0]
    finally:
        s.close()


class Rtsp:
    def __init__(self):
        self.s = socket.create_connection((CAR, 554), timeout=6)
        self.cseq = 0
        self.session = ""

    def req(self, method, target, extra=None):
        self.cseq += 1
        lines = ["%s %s RTSP/1.0" % (method, target), "CSeq: %d" % self.cseq,
                 "User-Agent: batprobe"]
        for k, v in (extra or {}).items():
            lines.append("%s: %s" % (k, v))
        self.s.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        self.s.settimeout(6)
        data = b""
        try:
            while b"\r\n\r\n" not in data:
                c = self.s.recv(4096)
                if not c:
                    break
                data += c
        except socket.timeout:
            pass
        head = data.split(b"\r\n\r\n")[0].decode("latin-1")
        return head

    def close(self):
        try:
            if self.session:
                self.req("TEARDOWN", URL, {"Session": self.session})
        except Exception:
            pass
        try:
            self.s.close()
        except Exception:
            pass


def open_listeners(extra_ports):
    """Bind every candidate UDP port we can."""
    socks = []
    for p in sorted(set(FIXED_PORTS + list(extra_ports))):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", p))
            s.setblocking(False)
            socks.append((p, s))
        except OSError:
            pass
    return socks


def listen(socks, seconds, label):
    print("   listening %ds on %d ports (%s)..." % (seconds, len(socks), label))
    got = {}
    end = time.time() + seconds
    while time.time() < end:
        for p, s in socks:
            try:
                d, addr = s.recvfrom(4096)
                if d:
                    key = (p, addr[0])
                    got[key] = got.get(key, 0) + len(d)
            except BlockingIOError:
                pass
            except OSError:
                pass
        time.sleep(0.01)
    return got


def report(got):
    if not got:
        print("   >>> nothing arrived on ANY port.")
        return False
    for (p, src), n in sorted(got.items(), key=lambda kv: -kv[1]):
        print("   >>> RECEIVED %d bytes on local port %d from %s" % (n, p, src))
    return True


def attempt(label, transport_extra, use_destination=False, ip=None):
    print("\n" + "=" * 60)
    print(label)
    print("=" * 60)
    r = Rtsp()
    try:
        h = r.req("DESCRIBE", URL, {"Accept": "application/sdp"})
        print("   DESCRIBE:", h.splitlines()[0])

        # pick a client port pair, then listen on it AND the fixed candidates
        base = 41000
        transport = "RTP/AVP;unicast;client_port=%d-%d" % (base, base + 1)
        if use_destination and ip:
            transport += ";destination=%s" % ip
        transport += transport_extra

        socks = open_listeners([base, base + 1])
        h = r.req("SETUP", TRACK, {"Transport": transport})
        print("   SETUP   :", h.splitlines()[0])
        tp = re.search(r"Transport:\s*(.+)", h, re.I)
        print("   server transport:", tp.group(1).strip() if tp else "(none)")
        m = re.search(r"Session:\s*([^;\r\n]+)", h, re.I)
        r.session = m.group(1).strip() if m else ""

        # if the server named its own server_port, also listen on those
        sp = re.search(r"server_port=(\d+)-(\d+)", h)
        if sp:
            extra = open_listeners([int(sp.group(1)), int(sp.group(2))])
            socks += extra

        h = r.req("PLAY", URL, {"Session": r.session, "Range": "npt=0.000-"})
        print("   PLAY    :", h.splitlines()[0])

        got = listen(socks, 12, label)
        found = report(got)
        for _, s in socks:
            try:
                s.close()
            except Exception:
                pass
        return found
    finally:
        r.close()


def main():
    ip = local_ip()
    print("=" * 60)
    print("Batmobile camera probe 4")
    print("=" * 60)
    print("   car        :", CAR)
    print("   this laptop:", ip)
    last = ip.rsplit(".", 1)[-1]
    if last != "2":
        print("   NOTE: you are .%s, not .2 . If the camera hardcodes its RTP" % last)
        print("   destination to 192.168.201.2 (the address a phone would")
        print("   typically get first), the video is being sent into the void.")
        print("   See the verdict at the end for how to test that.")

    a = attempt("[A] standard UDP SETUP, listening on many ports", "")
    time.sleep(3)
    b = attempt("[B] UDP SETUP with explicit destination=%s" % ip,
                "", use_destination=True, ip=ip)

    print("\n" + "=" * 60)
    print("VERDICT")
    print("=" * 60)
    if a or b:
        print("   Media DID arrive. Note the port above - the server is")
        print("   ignoring the negotiated port and using a fixed one. We can")
        print("   build a receiver around that.")
    else:
        print("   Nothing on any port, with or without an explicit destination.")
        print("   Two things left worth doing:")
        print()
        print("   1. If your address above is not 192.168.201.2, give this")
        print("      laptop a STATIC ip of 192.168.201.2 on the Batmobile")
        print("      network (mask 255.255.255.0, gateway 192.168.201.1) and")
        print("      run this again. If the camera hardcodes .2, that fixes it")
        print("      outright.")
        print()
        print("   2. Run Wireshark on the wifi adapter with filter")
        print("        ip.addr == 192.168.201.1 || arp")
        print("      then start ffplay. If you see the camera ARPing for an")
        print("      address that isn't yours, that is the whole answer.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
batmobile_camera_probe5.py — last cheap RTSP tricks before packet capture.

Ruled out so far: transport, path, firewall, control channel, competing
viewers, stale sessions, fixed RTP ports, hardcoded destination IP, and any
HTTP start command (the app has none).

Three mechanisms left that are cheap to test:

  A. PUNCH PACKETS. Some embedded servers ignore the client_port header and
     learn where to send RTP from the first packet the client sends TO them.
     ffmpeg does this only for NAT traversal, so a normal client never
     triggers it.

  B. RTCP RECEIVER REPORT. A few servers wait for proof of a live receiver
     before opening the tap.

  C. MULTICAST. If the server only ever streams multicast, unicast SETUP
     would succeed and deliver nothing - exactly our symptom.

    POWER-CYCLE THE CAR, join E6F4-BATMOBILE, then:
        python3 batmobile_camera_probe5.py

Stdlib only.
"""

import re
import socket
import struct
import time

CAR = "192.168.201.1"
URL = "rtsp://%s/live/ch00_0" % CAR
TRACK = URL + "/trackID=0"


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
        return data.split(b"\r\n\r\n")[0].decode("latin-1")

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


def rtcp_rr(ssrc=0x13579BDF):
    """Minimal RTCP Receiver Report with no report blocks."""
    return struct.pack("!BBHI", 0x80, 201, 1, ssrc)


def rtp_dummy(ssrc=0x13579BDF):
    """Empty RTP packet, payload type 96, used purely as a punch."""
    return struct.pack("!BBHII", 0x80, 96, 0, 0, ssrc)


def drain(socks, seconds, note=""):
    print("   listening %ds%s..." % (seconds, note))
    got = {}
    end = time.time() + seconds
    while time.time() < end:
        for name, s in socks:
            try:
                d, addr = s.recvfrom(4096)
                if d:
                    got[(name, addr[0], addr[1])] = \
                        got.get((name, addr[0], addr[1]), 0) + len(d)
            except BlockingIOError:
                pass
            except OSError:
                pass
        time.sleep(0.01)
    if got:
        for (name, ip, port), n in sorted(got.items(), key=lambda kv: -kv[1]):
            print("   >>> %d bytes on %s from %s:%d" % (n, name, ip, port))
        return True
    print("   >>> nothing.")
    return False


def unicast_with_punch(use_punch=True, use_rr=True):
    label = "punch + RTCP RR" if (use_punch and use_rr) else "plain"
    print("\n" + "=" * 60)
    print("[A/B] Unicast SETUP, then %s" % label)
    print("=" * 60)
    rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rtcp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rtp.bind(("", 41100))
    rtcp.bind(("", 41101))
    rtp.setblocking(False)
    rtcp.setblocking(False)

    r = Rtsp()
    try:
        r.req("DESCRIBE", URL, {"Accept": "application/sdp"})
        h = r.req("SETUP", TRACK,
                  {"Transport": "RTP/AVP;unicast;client_port=41100-41101"})
        print("   SETUP:", h.splitlines()[0])
        tp = re.search(r"Transport:\s*(.+)", h, re.I)
        print("   transport:", tp.group(1).strip() if tp else "?")
        m = re.search(r"Session:\s*([^;\r\n]+)", h, re.I)
        r.session = m.group(1).strip() if m else ""
        sp = re.search(r"server_port=(\d+)-(\d+)", h)
        if not sp:
            print("   no server_port; cannot punch.")
            return False
        srtp, srtcp = int(sp.group(1)), int(sp.group(2))
        print("   server rtp/rtcp ports: %d / %d" % (srtp, srtcp))

        if use_punch:
            for _ in range(4):
                try:
                    rtp.sendto(rtp_dummy(), (CAR, srtp))
                    rtcp.sendto(rtcp_rr(), (CAR, srtcp))
                except OSError:
                    pass
                time.sleep(0.05)
            print("   sent punch packets to both server ports")

        h = r.req("PLAY", URL, {"Session": r.session, "Range": "npt=0.000-"})
        print("   PLAY :", h.splitlines()[0])

        # keep punching / reporting while we wait
        socks = [("rtp:41100", rtp), ("rtcp:41101", rtcp)]
        got = {}
        end = time.time() + 15
        nextka = time.time() + 2
        print("   listening 15s, re-punching every 2s...")
        while time.time() < end:
            if time.time() > nextka:
                if use_punch:
                    try:
                        rtp.sendto(rtp_dummy(), (CAR, srtp))
                    except OSError:
                        pass
                if use_rr:
                    try:
                        rtcp.sendto(rtcp_rr(), (CAR, srtcp))
                    except OSError:
                        pass
                nextka = time.time() + 2
            for name, s in socks:
                try:
                    d, addr = s.recvfrom(4096)
                    if d:
                        got[name] = got.get(name, 0) + len(d)
                except BlockingIOError:
                    pass
                except OSError:
                    pass
            time.sleep(0.01)
        if got:
            for k, v in got.items():
                print("   >>> RECEIVED %d bytes on %s" % (v, k))
            return True
        print("   >>> nothing.")
        return False
    finally:
        r.close()
        rtp.close()
        rtcp.close()


def multicast_test():
    print("\n" + "=" * 60)
    print("[C] Multicast SETUP")
    print("=" * 60)
    r = Rtsp()
    try:
        r.req("DESCRIBE", URL, {"Accept": "application/sdp"})
        h = r.req("SETUP", TRACK, {"Transport": "RTP/AVP;multicast"})
        print("   SETUP:", h.splitlines()[0])
        tp = re.search(r"Transport:\s*(.+)", h, re.I)
        line = tp.group(1).strip() if tp else ""
        print("   transport:", line or "(none)")
        if "multicast" not in line.lower():
            print("   >>> server refused multicast; this path is closed.")
            return False
        dest = re.search(r"destination=([\d.]+)", line)
        port = re.search(r"port=(\d+)", line)
        if not (dest and port):
            print("   >>> accepted but gave no group/port.")
            return False
        grp, p = dest.group(1), int(port.group(1))
        print("   group %s:%d - joining" % (grp, p))
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", p))
        mreq = struct.pack("4sl", socket.inet_aton(grp), socket.INADDR_ANY)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        s.setblocking(False)
        m = re.search(r"Session:\s*([^;\r\n]+)", h, re.I)
        r.session = m.group(1).strip() if m else ""
        h = r.req("PLAY", URL, {"Session": r.session})
        print("   PLAY :", h.splitlines()[0])
        ok = drain([("multicast", s)], 12)
        s.close()
        return ok
    except Exception as e:
        print("   error:", e)
        return False
    finally:
        r.close()


def main():
    print("=" * 60)
    print("Batmobile camera probe 5")
    print("=" * 60)
    results = []
    results.append(("punch + RTCP", unicast_with_punch(True, True)))
    time.sleep(3)
    results.append(("multicast", multicast_test()))

    print("\n" + "=" * 60)
    print("VERDICT")
    print("=" * 60)
    for name, ok in results:
        print("   %-16s %s" % (name, "MEDIA RECEIVED" if ok else "nothing"))
    if not any(ok for _, ok in results):
        print()
        print("   Every RTSP mechanism is exhausted. Next is Wireshark, which")
        print("   answers the only remaining question: does the camera put ANY")
        print("   packet on the wire after PLAY?")
        print()
        print("     filter:  ip.addr == 192.168.201.1 || arp")
        print("     then run:  ffplay -rtsp_transport udp rtsp://192.168.201.1/live/ch00_0")
        print()
        print("   If the capture shows only RTSP and no RTP at all, the encoder")
        print("   never starts and no client-side fix exists.")


if __name__ == "__main__":
    main()

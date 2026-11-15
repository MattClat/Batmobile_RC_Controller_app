#!/usr/bin/env python3
"""
batmobile_recon.py — map the network surface of the Mattel Ultimate
Justice League Batmobile (FKM40) so we can rebuild a controller for it.

Run this from a laptop that is JOINED TO THE CAR'S OWN WI-FI NETWORK.
Do a factory reset on the car first (paperclip in the hole in the battery
bay, hold 10s while powered on) so it comes up with its default AP.

    python3 batmobile_recon.py

Stdlib only. No install needed. Python 3.8+.
"""

import socket
import struct
import subprocess
import sys
import threading
import time
from queue import Queue

TCP_PORTS = list(range(1, 1025)) + [
    1080, 2000, 2001, 2222, 3333, 4000, 4444, 5000, 5001, 5555, 6000, 6666,
    7000, 7060, 7070, 8000, 8080, 8081, 8088, 8888, 8899, 9000, 9060, 9999,
    10000, 10001, 11111, 12345, 20000, 50000,
]

UDP_PORTS = [
    53, 67, 68, 123, 1900, 2000, 2001, 5000, 5353, 6000, 7060, 8000, 8080,
    8888, 8899, 9000, 9060, 9999, 10000, 20000, 50000,
]

open_tcp = []
open_udp = []
lock = threading.Lock()


def find_gateway():
    """The car is almost certainly the DHCP gateway."""
    try:
        if sys.platform == "darwin":
            out = subprocess.check_output(["route", "-n", "get", "default"], text=True)
            for line in out.splitlines():
                if "gateway:" in line:
                    return line.split(":")[1].strip()
        elif sys.platform.startswith("linux"):
            with open("/proc/net/route") as f:
                for line in f.readlines()[1:]:
                    fields = line.split()
                    if fields[1] == "00000000":
                        return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
        elif sys.platform.startswith("win"):
            out = subprocess.check_output("ipconfig", text=True, errors="ignore")
            for line in out.splitlines():
                if "Default Gateway" in line and line.split(":")[-1].strip():
                    return line.split(":")[-1].strip()
    except Exception:
        pass
    return None


def my_ip(target):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((target, 9))
        return s.getsockname()[0]
    finally:
        s.close()


def tcp_worker(host, q):
    while True:
        port = q.get()
        if port is None:
            return
        s = socket.socket()
        s.settimeout(0.6)
        try:
            if s.connect_ex((host, port)) == 0:
                banner = b""
                try:
                    s.settimeout(1.2)
                    banner = s.recv(256)
                except Exception:
                    pass
                with lock:
                    open_tcp.append((port, banner))
                    tag = f"  banner: {banner[:80]!r}" if banner else ""
                    print(f"  [TCP OPEN] {port}{tag}")
        except Exception:
            pass
        finally:
            s.close()
            q.task_done()


def scan_tcp(host, threads=200):
    print(f"\n[1] TCP scan of {host} ({len(TCP_PORTS)} ports)...")
    q = Queue()
    workers = [threading.Thread(target=tcp_worker, args=(host, q), daemon=True)
               for _ in range(threads)]
    for w in workers:
        w.start()
    for p in TCP_PORTS:
        q.put(p)
    q.join()
    for _ in workers:
        q.put(None)
    if not open_tcp:
        print("  (nothing open — control is probably UDP-only)")


def scan_udp(host):
    """UDP is unreliable to scan, but toys often answer a poke."""
    print(f"\n[2] UDP probe of {host}...")
    probes = [b"\x00", b"\xff", b"\x66\x66", b"hello\r\n", bytes(range(8))]
    for port in UDP_PORTS:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.4)
        try:
            for probe in probes:
                s.sendto(probe, (host, port))
                try:
                    data, addr = s.recvfrom(2048)
                    with lock:
                        open_udp.append((port, probe, data))
                    print(f"  [UDP REPLY] {port} <- {data[:64]!r} (probe {probe!r})")
                    break
                except socket.timeout:
                    continue
        except Exception:
            pass
        finally:
            s.close()
    if not open_udp:
        print("  (no replies — normal; the car may only listen, never answer)")


def listen_broadcast(seconds=25):
    """Many of these toys shout a discovery/heartbeat packet on their own."""
    print(f"\n[3] Listening {seconds}s for broadcast/beacon traffic...")
    print("    >>> Power-cycle the Batmobile NOW so we catch its boot chatter. <<<")
    socks = []
    for port in (5000, 6000, 7060, 8000, 8888, 9000, 9060, 10000, 1900, 5353, 50000):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind(("", port))
            s.setblocking(False)
            socks.append((port, s))
        except Exception:
            pass
    heard = False
    end = time.time() + seconds
    while time.time() < end:
        for port, s in socks:
            try:
                data, addr = s.recvfrom(4096)
                heard = True
                print(f"  [HEARD] port {port} from {addr[0]}:{addr[1]} -> {data[:96]!r}")
            except BlockingIOError:
                pass
            except Exception:
                pass
        time.sleep(0.02)
    for _, s in socks:
        s.close()
    if not heard:
        print("  (silence)")


def probe_http(host):
    print(f"\n[4] Poking HTTP endpoints...")
    paths = ["/", "/index.html", "/status", "/info", "/cgi-bin/", "/api",
             "/videostream.cgi", "/snapshot.cgi", "/config"]
    for port in [80, 8080, 8000, 8081, 8888]:
        for path in paths:
            try:
                s = socket.socket()
                s.settimeout(1.0)
                if s.connect_ex((host, port)) != 0:
                    s.close()
                    break
                req = f"GET {path} HTTP/1.0\r\nHost: {host}\r\n\r\n".encode()
                s.sendall(req)
                data = s.recv(512)
                s.close()
                if data and b"404" not in data.split(b"\r\n")[0]:
                    print(f"  [HTTP] :{port}{path} -> {data.split(chr(13).encode())[0][:80]!r}")
            except Exception:
                pass


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else find_gateway()
    if not host:
        print("Could not auto-detect the car's IP. Pass it manually:")
        print("  python3 batmobile_recon.py 192.168.1.1")
        sys.exit(1)

    print("=" * 62)
    print(f"Batmobile recon — target {host}, this machine {my_ip(host)}")
    print("=" * 62)
    print("Make sure you are connected to the CAR'S Wi-Fi, not your house's.")

    scan_tcp(host)
    scan_udp(host)
    probe_http(host)
    listen_broadcast()

    print("\n" + "=" * 62)
    print("SUMMARY")
    print("=" * 62)
    print(f"Target IP     : {host}")
    print(f"Open TCP      : {[p for p, _ in open_tcp] or 'none'}")
    print(f"UDP responders: {[p for p, _, _ in open_udp] or 'none'}")
    print("\nPaste this whole output back into the chat.")


if __name__ == "__main__":
    main()

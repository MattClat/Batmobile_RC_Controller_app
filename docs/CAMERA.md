# The camera — unsolved

The Batmobile has an onboard camera. It works in the original iOS app. It has never worked in any other client, despite an extensive investigation.

This document records everything tested so the next person doesn't repeat it.

**Status: open.** Contributions welcome.

---

## The hardware

A separate module from the car's control MCU, sharing the same WiFi AP.

```
GET /custom/getDeviceInformation.cgi

{"result":"OK","device_name":"MY WIFI CAR DVR","serial_number":"0123456789",
 "software_version":"v1.02.52","hardware_version":"v1.01",
 "kernel_version":"v1.00.05","record_len":180,"auto_reboot":0,
 "Focus_enable":0,"Focus_min":0,"auto_del_oldfiles":0}
```

- RTSP on port **554** — `Server: Streaming Server v0.1`, SDP banner `ICL Streaming Media`
- HTTP CGI on port **80**, under `/custom/` and `/isp/`
- **Only those two ports are open.** No ONVIF, no proprietary video port

> ⚠️ A port scan may also report 25/110/119/143/465/563/587/993/995 open. Those are every mail and news port in the book — it's a local antivirus mail-shield intercepting them, not the camera. Ignore them.

Two encoder profiles are configured and both report `video_enable: 1`:

```
GET /custom/getVideoProfiles.cgi

MAIN  25 fps, 2048 kbps, audio_enable 0
SUB   30 fps, 8192 kbps, audio_enable 1
```

---

## The symptom

RTSP negotiates **flawlessly**, then delivers zero bytes of media. Forever. On every transport.

```
OPTIONS  200 OK   Public: DESCRIBE, SETUP, TEARDOWN, PLAY, PAUSE,
                          SET_PARAMETER, GET_PARAMETER
DESCRIBE 200 OK   Content-Base: rtsp://192.168.201.1/live/ch00_0/
SETUP    200 OK   RTP/AVP;unicast;mode=play;client_port=X;server_port=Y
PLAY     200 OK
                  ...nothing. ever.
```

The server allocates a *different* `server_port` per session, so it is genuinely doing per-connection work rather than parroting headers back.

### The SDP is a static template

```
v=0
o=- 1 1 IN IP4 127.0.0.1
s=RTSP Server Live
i=ICL Streaming Media
c=IN IP4 0.0.0.0
t=0 0
m=video 0 RTP/AVP 96
b=AS:5000
a=rtpmap:96 H264/90000
a=fmtp:96 profile-level-id=42A01E;packetization-mode=1;sprop-parameter-sets=Z2QAKKzoBQBbkA==,aO48MA==
a=control:trackID=0
```

Note the internal contradictions:

- `b=AS:5000` claims 5000 kbps, but the encoder reports MAIN at **2048** kbps
- `profile-level-id=42A01E` claims Baseline 3.0, but the actual SPS bytes (`Z2QAKKzoBQBbkA==` → `67 64 00 28 ...`) decode to **profile_idc 100 (High), level 4.0**

This SDP does not reflect live encoder state. The RTSP server is a thin shim bolted in front of the real video pipeline — which fits the symptom exactly: the shim completes the handshake because handshaking is all it does.

---

## The decisive constraint

The original app's **complete HTTP surface** is six endpoints:

```
/custom/getDeviceInformation.cgi
/custom/getVideoProfiles.cgi
/custom/setVideoProfiles.cgi?stream0Bitrate={0}
/custom/setImageSetting.cgi
/isp/awb_ctl.cgi?ENABLE=1
/custom/getWifiConfig.cgi
```

**The app sends no start-encoder command over HTTP.** And its video path (`RtspClient.cpp`, YETi CGI) is built on **stock ffmpeg** — the same demuxer `ffplay` and VLC use.

So the app does the same thing we do, with the same library, and gets frames. The difference is some runtime detail invisible in the binaries.

---

## Ruled out

Every one of these was tested against the car and came back negative.

| Hypothesis | Result |
|---|---|
| Wrong transport | UDP **and** TCP-interleaved both accepted, both silent |
| Windows Firewall | TCP interleaving reuses the outbound socket — cannot be blocked |
| Wrong URL path | 404 for bogus paths, 200 for any `/live/<anything>`. `/live/ch00_0` is correct |
| Competing viewer / stale session | Clean after power-cycle with the phone off the network entirely |
| Encoder gated on active control session | Tested with the controller running and the car **actively driving**. Still nothing |
| Camera asleep | `awb_ctl.cgi?ENABLE=1` returns OK; full app CGI warm-up sequence replayed |
| Fixed RTP port | Listened on 36 candidate ports simultaneously |
| Hardcoded destination IP | DHCP hands out `.100`, which the phone gets too. Explicit `destination=` also tried |
| NAT punch packets | Sent to both server ports before and during PLAY, re-punched every 2 s |
| RTCP receiver reports | Sent alongside the punches |
| Multicast | `461 Unsupported Transport` |
| SET_PARAMETER / GET_PARAMETER keepalives | No effect |
| ONVIF | Not present on any open port |
| The `?cmd=NNN&param=X&value=Y` API | The string `cmd=301&param=network_ap` exists in the app, but the device forcibly closes the connection on every form of it. Dead code or a different hardware revision |
| String extraction | Exhausted — IL2CPP metadata and all 16 native `.so` files contain no stream URL and no vendor start command |

---

## The one hard error

```
GET /custom/startRecord.cgi

{"result": "Fail"}
```

The endpoint **exists** and **fails**. It's the only concrete error found anywhere on the device.

On a DVR, a failing record command usually means no storage. **Whether the car has an SD card slot has never been checked.** If it does and it's empty, insert a microSD, power-cycle, and retry — some of these modules won't start their H.264 encoder without somewhere to write.

This is the cheapest untried thing by a wide margin.

---

## What to try next

### 1. The SD card

See above. Five minutes, possibly the whole answer.

### 2. Wireshark — the decisive measurement

Never run, and it settles the question completely.

```
filter:  ip.addr == 192.168.201.1 || arp
then:    ffplay -rtsp_transport udp rtsp://192.168.201.1/live/ch00_0
```

Two possible outcomes, pointing opposite directions:

- **RTP packets on the wire but not reaching the player** → a local problem, and fixable
- **No RTP at all after PLAY** → the encoder never starts; no client-side fix exists

### 3. Emulator packet capture — the guaranteed answer

Install the Android app in LDPlayer or BlueStacks **on a laptop** that is joined to `E6F4-BATMOBILE`. The emulator routes its traffic through the host, so Wireshark on the host captures the entire working RTSP exchange in clear text (above the WiFi encryption layer — nothing needs cracking).

Diff that session against ours. Whatever the app does differently will be right there, byte for byte.

### 4. If the stream is ever recovered

It is **unknown** whether the camera serves more than one client at a time — untested, don't assume either way. If it turns out to be single-client, a relay (ffmpeg or [MediaMTX](https://github.com/bluenviron/mediamtx) on a laptop or Pi holding the one session and republishing it) is how you'd let several people watch at once.

---

## Diagnostic tools

The probes used in this investigation are in [`tools/camera/`](../tools/camera/), roughly in the order they were written. See that directory's README for what each one does.

> ⚠️ **Do not run an aggressive threaded port scan against this camera.** A 150-thread scan wedged its HTTP server, and every subsequent probe returned false negatives until a power-cycle. Probe one connection at a time with pauses between.

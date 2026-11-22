# Batmobile RC Controller

Replacement controller apps for the **Mattel Ultimate Justice League Batmobile (FKM40)**, a WiFi-controlled RC car whose official app was pulled from the App Store and Google Play, leaving the toy unusable.

This repo documents the complete reverse-engineered control protocol and provides three working controllers: desktop (Python), iPad/iPhone (Swift), and Pythonista (Python on iOS).

![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux%20%7C%20iOS-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-brightgreen)
![Swift](https://img.shields.io/badge/swift-SwiftUI-orange)
[![License](https://shields.io)](./LICENSE)


---

## The problem

Mattel discontinued the **Batmobile™ R/C Controller** app (`com.mattel.batmobilerc`) sometime after 2018. The car has no physical remote — it creates its own WiFi access point and is driven entirely from a phone. With the app gone from both stores, every one of these cars became a paperweight.

The FCC-filed user manual even reserved the right to terminate the service after 09/01/2018, so this was planned obsolescence rather than an oversight.

## The solution

The control protocol was recovered by decompiling an archived copy of the Android app. It turns out to be simple: an ASCII string of hex opcode pairs sent over UDP ten times a second. The full specification is in **[docs/PROTOCOL.md](docs/PROTOCOL.md)**.

The WiFi password — never printed on the car or its packaging, only ever displayed by the app — was extracted from the Unity IL2CPP metadata blob. See **[docs/REVERSE_ENGINEERING.md](docs/REVERSE_ENGINEERING.md)** for the full method.

---

## Quick start

### 1. Connect to the car

| | |
|---|---|
| **SSID** | `E6F4-BATMOBILE` *(prefix varies per car)* |
| **Password** | `BATMOBILE1` |

If the password doesn't work, the car was paired previously and generated a random one. **Factory reset it:** paperclip into the small hole in the battery bay, hold 10 seconds while powered on. That restores the default.

### 2. Pick a controller

#### Desktop — Windows, macOS, Linux

```bash
cd controllers/desktop
pip install -r requirements.txt
python batmobile_control.py
```

Keyboard and gamepad support, steering trim, engine-sound workaround, and a live packet readout. See **[controllers/desktop](controllers/desktop/)**.

#### iPad / iPhone — real native app, no Mac required

Built entirely on the device in **Swift Playgrounds** (free). Two thumbsticks, action buttons, and a diagnostics panel.

See **[controllers/ios](controllers/ios/)** for the full build walkthrough.

#### iPad / iPhone — Pythonista

If you already own [Pythonista 3](https://apps.apple.com/app/pythonista-3/id1085978097), `controllers/pythonista/batmobile_ipad.py` runs as-is with a touch UI. See **[controllers/pythonista](controllers/pythonista/)**.

---

## What works

| Feature | Status |
|---|---|
| Throttle (forward / reverse, 100 steps) | ✅ |
| Steering (100 steps each way) | ✅ |
| Steering trim | ✅ |
| Headlights | ✅ |
| Smoke generator | ✅ |
| Gun elevation / rotation | ✅ |
| Body / armor mode | ✅ |
| Engine sound selection | ✅ |
| Engine **mute** | ⚠️ Partial — no protocol support, see below |
| Telemetry from car | ⚠️ Received but undecoded |
| Onboard camera | ❌ Unsolved — see [docs/CAMERA.md](docs/CAMERA.md) |

### About the sound

**There is no mute command in the protocol.** This was verified both statically (the only audio-related method in the app's Java bridge is `SetVoice`; every `Mute`/`SetVolume` symbol in the binary belongs to Unity or FMOD and controls the *phone's* speaker) and empirically (all 256 values of the sound opcode were swept).

Three sound indices — `0x09`, `0x0E`, `0x10` — silence the engine, but only for ~3 seconds before the firmware reverts to the idle loop, and each one replays a ~1 second intro clip when triggered. The desktop controller works around this by re-firing the index every 2 seconds. The iOS app deliberately **omits** this: each resend consumes the packet's single spare channel slot, which makes button presses feel laggy.

For true silence, open the shell and unplug the speaker, or put a 100–470 Ω resistor inline to attenuate it.

---

## Repository layout

```
├── docs/
│   ├── PROTOCOL.md              Complete wire protocol specification
│   ├── REVERSE_ENGINEERING.md   How the protocol and password were recovered
│   ├── CAMERA.md                The unsolved video stream investigation
│   └── TROUBLESHOOTING.md       Common failures and fixes
├── controllers/
│   ├── desktop/                 Python + pygame, keyboard and gamepad
│   ├── ios/                     SwiftUI app for Swift Playgrounds
│   └── pythonista/              Python with touch UI for Pythonista 3
└── tools/
    ├── camera/                  Diagnostic probes from the RTSP investigation
    └── apk/                     APK string-extraction utilities
```

---

## Hardware

- **Product:** Mattel Ultimate Justice League Batmobile
- **Model:** FKM40
- **FCC ID:** PIYFKM40-17A5W
- **Original app:** `com.mattel.batmobilerc` (Unity / IL2CPP, v1.3.1, developed by YETi CGI)
- **Car endpoint:** UDP `192.168.201.1:1051`
- **Camera module:** separate "MY WIFI CAR DVR" unit, RTSP on port 554, HTTP CGI on port 80

---

## Contributing

Two open threads if you want to pick something up:

1. **Decode the telemetry.** The car replies to every command with 14 bytes, which `AndroidMain.showData()` unpacks into seven 10-bit values. The controllers receive these but nobody has worked out what they mean. Battery voltage and sensor readings are the obvious guesses.
2. **Crack the camera.** The video stream works in the original app and in no other client. Fourteen hypotheses have been tested and eliminated — all documented in [docs/CAMERA.md](docs/CAMERA.md), along with the three approaches that remain untried.

Issues and pull requests welcome.

## Legal

This is an independent interoperability project. It is not affiliated with, endorsed by, or supported by Mattel, Warner Bros., DC Comics, or YETi CGI. "Batmobile", "Justice League", and related marks belong to their respective owners.

Reverse engineering was performed on a lawfully purchased device for the sole purpose of restoring interoperability after the manufacturer discontinued support. No app code, assets, or binaries are redistributed here — only the protocol documentation and independently written implementations.

## License

This project is licensed under the **PolyForm Noncommercial License 1.0.0**. 

* **Allowed:** You are free to download, use, and modify this app for **personal, educational, or non-commercial purposes**.
* **Not Allowed:** You may **not** sell this app, offer it as a paid service, or use it for any commercial or for-profit purpose.

See the [LICENSE](./LICENSE) file for the full legal terms.


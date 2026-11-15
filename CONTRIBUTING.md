# Contributing

This started as a weekend project to un-brick a toy. Contributions welcome, especially on the two open threads below.

## Open problems

### 1. Decode the telemetry

The car replies to every command with a **14-byte datagram**. The original app's `AndroidMain.showData()` unpacks it into seven 10-bit values (`Result1`–`Result7`) and hands them to Unity — but the app never displayed them anywhere, so there's no reference behaviour to compare against.

The controllers here receive these packets. The iOS app displays the raw bytes in its diagnostics panel. Nobody has worked out what the seven values mean; battery voltage and sensor readings are the obvious guesses.

If you have a car, logging these while varying one thing at a time (battery level, throttle, orientation) would probably crack it quickly.

### 2. The camera

Works in the original app, in nothing else. Read [docs/CAMERA.md](docs/CAMERA.md) before starting — fourteen hypotheses are already eliminated and documented. The three untried approaches, cheapest first:

1. Check whether the car has an SD card slot (`startRecord.cgi` returns `Fail`, which on a DVR usually means no storage)
2. A Wireshark capture during a PLAY attempt — settles whether the camera transmits at all
3. An emulator packet capture of the original app — guaranteed to show what it does differently

## Verifying protocol changes

Any change to packet construction must still produce these exact outputs:

```
idle              41_80_31_80_50_F0_00_00_00
full forward      41_e4
full reverse      41_64
half forward      41_b2
steer right       31_e4
steer left        31_64
sound index 9     01_9          ← lowercase, no leading zero
heartbeat tail    00 ×9, then 01 on the 10th packet
```

The no-leading-zero quirk is the one most likely to be broken by a reimplementation. The firmware parser is not fixed-width — `01_09` does not work.

Test against `controllers/desktop/batmobile_control.py`, which is the known-good reference.

## Hardware testing

If you're changing anything that moves the car, **put it on a stand with the wheels off the ground** for the first run. The fail-safe only triggers when the packet stream stops entirely; a bug that pins the throttle will happily keep sending.

## Scope

Happy to take: bug fixes, additional platforms, UI improvements, telemetry decoding, camera progress, documentation corrections.

Please don't submit: the original app's code, assets, or binaries. This repo documents a protocol and provides independent implementations. Keep it that way.

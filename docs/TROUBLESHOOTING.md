# Troubleshooting

---

## The car doesn't move

Work through these in order.

### 1. Is the WiFi password being rejected?

Default is `BATMOBILE1` on SSID `E6F4-BATMOBILE`.

If it's refused, the car was paired with the original app at some point and generated a random password. **Factory reset:** paperclip into the small hole in the battery bay, hold **10 seconds** while the car is powered on. That restores the default SSID and password.

### 2. Did your device leave the car's network?

**This is the single most common failure**, and it resolves itself in a way that makes it look like a software bug.

The Batmobile's access point has no internet. iOS and Windows both quietly jump back to a network that does — especially after an app restart or when the screen wakes.

- **iOS:** Settings → WiFi, confirm `E6F4-BATMOBILE`. If it keeps wandering, turn off Auto-Join on your home network while playing.
- **Windows:** check the network tray. Same fix — uncheck "Connect automatically" on your home network temporarily.

The iOS app's diagnostics panel catches this instantly: the `my ip` row flags **WRONG NETWORK** in red if you aren't on `192.168.201.x`.

### 3. Battery

These cars get flaky *before* they die outright — intermittent response, weak steering, dropped connections. If behaviour is erratic rather than absent, charge it.

### 4. Power-cycle the car

Clears any stuck state. Off, ten seconds, on.

### 5. Isolate the problem

Run the desktop controller from a laptop on the car's WiFi:

```bash
python controllers/desktop/batmobile_control.py
```

- **Laptop drives it** → the car is fine; the problem is your other client
- **Laptop can't either** → it's the car or the network, not the app

The desktop controller is the known-good reference implementation. Use it as the control in any experiment.

---

## iOS: app runs but the car ignores it

### Local Network permission

iOS **silently** blocks local network traffic without this permission — no error, no prompt the second time, nothing in the logs. Packets just vanish.

- **Swift Playgrounds:** sidebar → App Settings → Capabilities → **+** → Local Network. The capability must be declared *before* you run.
- **Both:** Settings → *(app name)* → Local Network must be ON.

### Read the diagnostics panel

The SwiftUI app shows seven rows at the bottom:

| Row | Healthy | If not |
|---|---|---|
| `my ip` | `192.168.201.x` | Wrong network — see above |
| `state` | `ready` | Stuck on `preparing`/`waiting` = Local Network permission denied |
| `sent` | climbing ~10/sec | Frozen = the send timer died; relaunch |
| `packet` | changing as you move sticks | Frozen = UI isn't reaching the link object |
| `replies` | climbing | Zero is survivable — the car may just not be answering |
| `error` | `none` | **Whatever is here is the real problem** |

Press **SELF TEST** with the wheels off the ground. It fires eight full-throttle packets directly, bypassing the thumbsticks. Wheels spin → the pipe works and the problem is in the gesture handling. Nothing, but `sent` climbing and `error` none → packets are leaving the device and dying before the car.

### The app must stay in the foreground

iOS suspends background apps, the packet stream stops, and the car fail-safes. This is expected behaviour, not a bug.

---

## Desktop: `pip install pygame` fails

Typical on recent Python versions:

```
ModuleNotFoundError: No module named 'setuptools._distutils.msvccompiler'
ERROR: Failed to build 'pygame' when getting requirements to build wheel
```

pip can't find a prebuilt wheel for your Python version, so it tries to compile from source, which needs a Visual Studio C++ toolchain you probably don't have.

**Fix — use the community fork:**

```bash
pip uninstall pygame -y
pip install pygame-ce
```

`pygame-ce` ships prebuilt wheels for current Python versions and is a drop-in replacement — it still imports as `pygame`, so no code changes.

Alternatives if that fails:

```bash
python -m pip install --upgrade pip setuptools wheel   # then retry pygame
```

or create the venv with Python 3.12, which has wheels for mainline pygame.

---

## Pythonista: import errors

**Make sure you're running the right file.** `controllers/pythonista/batmobile_ipad.py` imports only `socket`, `threading`, `time`, `ui`, and `console` — all built in.

If you see a pygame error, you're running `controllers/desktop/batmobile_control.py` by mistake. That one is desktop-only and will never work in Pythonista.

Quick way to tell them apart: the desktop version prints keyboard instructions (W/S/A/D); the Pythonista version draws two circular thumbsticks with a button row.

---

## Buttons feel laggy

A packet carries at most **three active channels**. Throttle and steering always occupy two, leaving exactly one slot for a button action.

If something queues into that slot on every tick — as the engine-mute workaround does — button presses wait their turn and feel delayed.

This is why the iOS app omits the mute feature entirely. On the desktop controller, press `M` to turn mute off if the lag bothers you.

---

## The engine noise

There's no mute command in the protocol — see [the README](../README.md#about-the-sound) for the full explanation.

The partial workaround on desktop (`M` to toggle, `-`/`=` to tune the resend interval) re-triggers a near-silent sound clip every ~2 seconds. You'll hear a brief intro each time it fires.

For real silence: open the shell (same access as the battery bay) and unplug the small speaker, or put a 100–470 Ω resistor inline to attenuate rather than kill it.

---

## The camera

Doesn't work in anything but the original app. This is a known, extensively investigated, unsolved problem — see [CAMERA.md](CAMERA.md). Don't spend time on it before reading what's already been eliminated.

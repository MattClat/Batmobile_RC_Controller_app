# Batmobile FKM40 — Control Protocol

Complete wire specification for the Mattel Ultimate Justice League Batmobile (FKM40), recovered by decompiling `com.mattel.batmobilerc` v1.3.1.

---

## Transport

| | |
|---|---|
| **Host** | `192.168.201.1` |
| **Port** | `1051` |
| **Protocol** | UDP |
| **Rate** | one packet every 100 ms (10 Hz) |
| **Encoding** | ASCII |

The car **fail-safes if the stream stops.** A controller must keep sending at 10 Hz for the whole session, including while idle — that's what the neutral keepalive is for.

The car is reached by joining its own access point:

| | |
|---|---|
| **SSID** | `E6F4-BATMOBILE` — the `E6F4` prefix is derived from the device MAC and varies per car |
| **Password** | `BATMOBILE1` |

On first pairing the original app generated a random password and pushed it to the car, so a used car may not accept the default. A factory reset (paperclip in the battery-bay hole, 10 seconds while powered on) restores it.

---

## Packet format

A packet is a sequence of `OPCODE_VALUE` pairs joined by underscores, followed by a heartbeat byte.

```
41_80_31_80_50_F0_00_00_00
└─┬─┘ └─┬─┘ └─┬─┘ └─┬─┘ └┬┘
  │     │     │     │    └── heartbeat
  │     │     │     └─────── padding (unused slot)
  │     │     └───────────── fixed marker, always 50_F0
  │     └─────────────────── steering, centered
  └───────────────────────── throttle, stopped
```

Construction rules, reproducing `getSendCmd()` from the app:

1. Start with throttle and steering — these are **always** present.
2. If any one-shot command is queued (a button press), append it. **Maximum three active channels**, so at most one button action rides along per packet.
3. Append the fixed marker `50_F0`.
4. Pad with `00_00` until there are four pairs total.
5. Append the heartbeat byte: `00`, except every 10th packet where it is `01`.

### Heartbeat

A counter cycling 1–10. The tail byte is `00` for packets 1 through 9 and `01` on packet 10, then it repeats.

```
packet  1: 41_80_31_80_50_F0_00_00_00
packet  9: 41_80_31_80_50_F0_00_00_00
packet 10: 41_80_31_80_50_F0_00_00_01
```

### ⚠️ Hex formatting — the critical detail

Values are formatted with Java's `Integer.toHexString()`: **lowercase, no leading zero.**

```
sound index 9  →  01_9     ✅
sound index 9  →  01_09    ❌  will not work
```

The marker `50_F0` is the single exception — it's a hardcoded uppercase literal in the app.

Equivalents by language:

| Language | Call |
|---|---|
| Java | `Integer.toHexString(v)` |
| Python | `format(v & 0xFF, 'x')` |
| Swift | `String(v & 0xFF, radix: 16)` |

Zero-padded hex was tested against the car and rejected — the firmware parser is not fixed-width.

---

## Opcode reference

| Opcode | Channel | Values |
|---|---|---|
| `41` | Throttle | `80` stop · `81`–`e4` forward 1–100 · `01`–`64` reverse 1–100 |
| `31` | Steering | `80` center · `81`–`e4` one way · `01`–`64` the other |
| `B1` | Steering trim | `00` center · `81` one way · `01` the other |
| `A1` | Headlights | `10` on · `01` off |
| `91` | Smoke generator | `10` on · `01` off |
| `21` | Body / armor `64` · gun up-down `e4` | |
| `11` | Gun rotate | `e4` |
| `01` | Sound clip | `01_<hex(i-1)>` — note the 1-based → 0-based shift, so `SetVoice(1)` sends `01_0` |
| `50` | Fixed marker | always `F0` |

### Magnitude encoding

Analog channels (throttle, steering) use a split range:

```
reverse / left        neutral       forward / right
0x01 ──────── 0x64      0x80      0x81 ──────── 0xE4
  1            100                  1            100
```

Forward/right values are `magnitude + 128`. So 50% forward throttle is `50 + 128 = 178 = 0xb2`, sent as `41_b2`.

### Completeness

**This is the entire opcode set.** The Java bridge `android.unity.AndroidMain` exposes exactly nine control methods and there is nothing else. Opcodes `0x00`–`0xFF` were swept against the car; nothing outside this table produces a response.

---

## Worked examples

```
# idle keepalive
41_80_31_80_50_F0_00_00_00

# full throttle forward, straight
41_e4_31_80_50_F0_00_00_00

# half reverse, full right
41_32_31_e4_50_F0_00_00_00

# forward with headlights on (button rides in the spare slot)
41_b2_31_80_A1_10_50_F0_00

# tenth packet in the cycle — note the trailing 01
41_80_31_80_50_F0_00_00_01
```

Reference implementation (Python):

```python
def hx(v):
    """Java Integer.toHexString: lowercase, no leading zero."""
    return format(int(v) & 0xFF, "x")

def throttle_token(axis):          # axis in [-1.0, 1.0], + is forward
    if abs(axis) < 0.1:
        return "41_80"
    mag = max(1, min(100, round(abs(axis) * 100)))
    return "41_" + hx(mag + 128 if axis > 0 else mag)

def build(throttle, steer, oneshots, heartbeat):
    pairs = [throttle, steer]
    if oneshots and len(pairs) < 3:
        pairs.append(oneshots.pop(0))
    pairs.append("50_F0")
    while len(pairs) < 4:
        pairs.append("00_00")
    heartbeat = (heartbeat + 1) % 10
    return "_".join(pairs) + "_" + ("01" if heartbeat == 0 else "00"), heartbeat
```

---

## Telemetry (undecoded)

The car replies to commands with a **14-byte datagram**. In the original app, `AndroidMain.showData()` unpacks it into **seven 10-bit values** and forwards them to Unity as `Result1` through `Result7`.

The controllers in this repo receive these packets and use their arrival as a "link established" indicator, and the iOS app displays the raw bytes. **Nobody has decoded what the seven values mean.** Battery voltage and sensor readings are the obvious candidates. This is an open invitation.

Note that the original app never wired this up to any visible UI either, so there's no reference behaviour to compare against.

---

## Dead ends

Documented so nobody repeats them:

| Thing | Result |
|---|---|
| `strADJ` channel field in the Java | Dead code — no public method ever sets it, no known opcode behind it |
| Zero-padded hex (`01_09`) | Rejected by the firmware parser |
| Sweeping opcode `50` (the marker) through all 256 values | No effect |
| Scanning all opcodes `0x00`–`0xFF` | Nothing beyond the documented table |
| Any mute / volume command | Does not exist — see [the sound section in the README](../README.md#about-the-sound) |

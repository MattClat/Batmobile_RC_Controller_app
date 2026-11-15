# How the protocol was recovered

A walkthrough of the method, written so it can be reapplied to a similar abandoned Unity-based device.

---

## The starting position

Nothing was publicly documented. No existing teardown, no protocol notes, no GitHub project. The car had:

- No physical remote — the phone app was the only control surface
- An app that no longer existed on either store
- An undocumented WiFi password that was never printed on the car or box

Two problems, in order: get onto the network, then work out what to say.

---

## Step 1 — get the right APK

The app is `com.mattel.batmobilerc`. Mirrors still carry archived copies; APKCombo had it.

**Two traps:**

- **Don't decompile the store installer.** Aptoide's download button hands you *their* client app, not the one you asked for. If the root package in your decompiler is `cm.aptoide`, you have the wrong file. You want `com.mattel.batmobilerc`.
- **Take the plain APK, not the XAPK.** The listing offered a 210 MB XAPK and a 72 MB APK of the same version. The extra 140 MB is bundled video assets, nothing useful. The plain APK opens directly in jadx.

Search mirrors by **package name**, not by title — title search goes fuzzy and tends to surface the iOS listing instead.

---

## Step 2 — the Java layer (jadx)

On Windows, grab the `jadx-gui-x.x.x-with-jre-win.zip` bundle — it ships its own Java runtime, so there's no separate JDK install to fight with.

Open the APK and search. The Java in a Unity app is only a thin bridge to the native engine, but **that bridge is where the networking lives**, which is exactly what we needed.

Searching for `socket` landed on `android.unity.AndroidMain`:

```java
DatagramSocket socket = null;
AndroidMain.this.socket = new DatagramSocket();
AndroidMain.this.socket.setSoTimeout(100);
AndroidMain.this.conHandler.postDelayed(AndroidMain.this.socketRun, 100L);
AndroidMain.this.socket.send(new DatagramPacket(AndroidMain.this.buf, ...));
```

UDP, posted on a 100 ms loop. That's the 10 Hz command stream.

The same class contained `getSendCmd()` (the packet builder), every control setter, and the destination address and port. **The entire control protocol was in this one class** — see [PROTOCOL.md](PROTOCOL.md) for the result.

### Why the Java was enough

In a Unity IL2CPP build, the C# game logic is compiled to native machine code and is painful to read. But Unity can't open a socket by itself on Android — it calls into a small Java shim. That shim is ordinary, readable, fully-decompilable Java. **For any Unity app that talks to hardware, check the Java bridge first.**

---

## Step 3 — the WiFi password (IL2CPP metadata)

The password wasn't in the Java. Searching the decompiled source for `password` returned nothing but OkHttp and Google SDK noise.

It wasn't in a .NET assembly either — there was no `Assembly-CSharp.dll`. The presence of `assets/bin/Data/Managed/Metadata/` instead is the signature of an **IL2CPP** build: the C# was compiled to native code, and the DLLs are gone.

**But the string literals survive.** IL2CPP dumps every C# string constant into:

```
assets/bin/Data/Managed/Metadata/global-metadata.dat
```

A blind `strings` on that file gives thousands of fragments. Parsing it properly is much better — the format is documented and simple:

```python
import struct

data = open('global-metadata.dat', 'rb').read()

# header: uint32 sanity (0xFAB11BAF), int32 version
sanity, version = struct.unpack_from('<Ii', data, 0)
assert sanity == 0xFAB11BAF

stringLiteralOffset     = struct.unpack_from('<i', data, 8)[0]
stringLiteralCount      = struct.unpack_from('<i', data, 12)[0]   # byte size
stringLiteralDataOffset = struct.unpack_from('<i', data, 16)[0]

# each Il2CppStringLiteral is { uint32 length; int32 dataIndex } = 8 bytes
literals = []
for k in range(stringLiteralCount // 8):
    base = stringLiteralOffset + k * 8
    length    = struct.unpack_from('<I', data, base)[0]
    dataIndex = struct.unpack_from('<i', data, base + 4)[0]
    s = data[stringLiteralDataOffset + dataIndex:
             stringLiteralDataOffset + dataIndex + length]
    literals.append(s.decode('utf-8', 'replace'))
```

This version-24 metadata yielded **7,690 clean string literals**.

### Finding the password among them

Filtering for `password`, `wifi`, `ssid` keywords surfaced a `BatcarWifi` class and `com.yeticgi.batmobile.WifiSettings`, but no obvious credential.

The win came from **positional context**. IL2CPP keeps literals from the same class adjacent in the table, so dumping the neighbours of each candidate reveals which UI screen a string belongs to:

```
2868  'wifi-step-one'
2869  'Default'
2870  'BATMOBILE1'      ← 10 characters, valid WPA2 length
2871  'wifi-novice-desc1'
2872  'wifi-main-settings'
```

Sitting directly after `Default`, surrounded on both sides by WiFi-setup UI strings. That's the default passphrase, and it worked first try.

**Takeaway:** when string extraction gives you a flat list, don't just grep it — dump the *neighbourhood* around each candidate. Adjacency carries meaning.

---

## Step 4 — verification

The protocol was confirmed by building a controller and driving the car. Each subsequent port (Pythonista, SwiftUI) was validated by transcribing its packet-building functions and diffing the output against the known-good packets:

```
idle            41_80_31_80_50_F0_00_00_00
full forward    41_e4
full reverse    41_64
half forward    41_b2
steer right     31_e4
sound index 9   01_9        ← the no-leading-zero quirk
heartbeat       00 ×9 then 01
```

Any reimplementation should pass these before it touches real hardware.

---

## Tooling

| Tool | Used for | Note |
|---|---|---|
| [jadx](https://github.com/skylot/jadx) | APK → readable Java | Get the `with-jre` bundle on Windows |
| Python + `struct` | IL2CPP metadata parsing | stdlib only, no dependencies |
| [ILSpy](https://github.com/icsharpcode/ILSpy) | .NET assemblies | **Not needed here** — would apply to a Mono build with `Assembly-CSharp.dll` |
| [Il2CppDumper](https://github.com/Perfare/Il2CppDumper) | Full IL2CPP reconstruction | Not needed — metadata strings were sufficient |
| `tools/apk/` in this repo | Native `.so` string extraction | Written during the camera hunt |

---

## What this method could not reach

String extraction has a hard ceiling: **it only finds constants, not runtime behaviour.**

The camera stream URL is assembled at runtime and never appears as a literal anywhere — not in the IL2CPP metadata, not in any of the 16 native `.so` files. The video path turned out to be YETi CGI's own `RtspClient.cpp` built on stock ffmpeg, so every RTSP string in the binary is generic ffmpeg machinery with no device-specific values.

That's why the camera remains unsolved, and why the remaining approaches in [CAMERA.md](CAMERA.md) all involve observing a *live working session* rather than reading files.

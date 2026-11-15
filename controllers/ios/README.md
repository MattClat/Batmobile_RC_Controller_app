# iPad / iPhone app

A real native SwiftUI app, built **entirely on the device** in Swift Playgrounds. No Mac, no Xcode, no Apple Developer account, no cost.

SwiftUI is universal, so the same project runs on iPhone — though the layout is sized for iPad and will be cramped on a phone.

## Build

1. Install **Swift Playgrounds** (free, App Store). Version 4 or later.

2. Tap **+** → **App**.

   > Not "Playground" — that's a read-only tutorial scratchpad with no app settings and nothing editable.

   An App project opens with a sidebar listing `MyApp.swift` and `ContentView.swift`.

3. Open `ContentView.swift`, select all, and replace it with [`ContentView.swift`](ContentView.swift) from this directory. Leave `MyApp.swift` alone — it already presents `ContentView()`.

4. **Sidebar → App Settings → Capabilities → + → Local Network.**

   > ⚠️ **Everything depends on this step.** Without the Local Network capability, iOS silently discards every packet — no error, no prompt, no log entry. App Settings is at the bottom of the file sidebar.

5. Join the car's WiFi: `E6F4-BATMOBILE` / `BATMOBILE1`.

6. Run, and approve the Local Network prompt.

A permanent home-screen icon requires an Apple Developer account ($99/yr) to build to device or submit. Without one it still runs full-screen from inside Playgrounds.

## Controls

- **Left thumbstick** — steering
- **Right thumbstick** — throttle (up forward, down reverse)
- Both spring back to neutral on release
- **Buttons:** lights, smoke, gun, rotate, armor, self test

## Diagnostics panel

Seven rows at the bottom of the screen:

| Row | Meaning |
|---|---|
| `my ip` | This device's address, read via `getifaddrs`. Must be `192.168.201.x` — flags red otherwise |
| `target` | Where packets are going |
| `state` | `NWConnection` state. Must reach `ready` |
| `sent` | Packet counter. Should climb ~10/sec |
| `packet` | The literal bytes being transmitted |
| `replies` | Telemetry from the car, as hex |
| `error` | Send/receive errors, verbatim |

**SELF TEST** fires eight full-throttle packets directly, bypassing the thumbsticks. Put the car on a stand first.

## Implementation notes

**No mute feature.** The workaround requires queueing a sound command every ~2 seconds, which occupies the packet's single spare channel slot and makes button presses feel laggy. Not worth it. See the [protocol docs](../../docs/PROTOCOL.md#packet-format).

**Never swallow send errors.** An early version used `.contentProcessed { _ in }`, discarding every error silently. When the app mysteriously stopped working there was no way to diagnose it. The current code surfaces every error to the panel.

**The app must stay in the foreground.** iOS suspends background apps; the stream stops and the car fail-safes.

# Pythonista controller

Touch controller for iPad and iPhone running in [Pythonista 3](https://apps.apple.com/app/pythonista-3/id1085978097) (paid app, ~$10).

If you don't already own Pythonista, the [SwiftUI app](../ios/) is free and gives you a real native app. This version exists because it's a near-direct port of the desktop controller, which makes it easy to modify if you prefer Python.

## Install

Standard library plus Pythonista's own `ui` and `console` modules — **no dependencies to install**.

1. Get `batmobile_ipad.py` onto the device: AirDrop or email it, then Share → Copy to Pythonista. Or drop it in `iCloud Drive/Pythonista 3/`. Or just paste the contents into a new script.
2. Join `E6F4-BATMOBILE` / `BATMOBILE1`.
3. Run it, and approve the Local Network prompt.

> If you see a `pygame` import error, you're running the **desktop** controller by mistake. This file imports only `socket`, `threading`, `time`, `ui`, and `console`.

## Launch it like an app

Shortcuts → new shortcut → "Run Pythonista Script" → pick this one → Share → **Add to Home Screen**. It gets its own icon.

## Controls

- **Left thumb** — steering
- **Right thumb** — throttle (up forward, down reverse)
- **Buttons** — lights, smoke, gun, rotate, armor, mute
- Both sticks spring back to neutral on release

The readout at the bottom shows the live packet, and reads `linked` rather than `sending` once the car starts replying with telemetry.

## Notes

**Mute auto-fires at launch** so the sound clip's intro plays before you drive. Press the MUTE button to toggle.

**Settings → Pythonista 3 → Local Network** must be ON or nothing reaches the car.

On exit the script sends neutral packets so the car doesn't drive away.

# Desktop controller

Python controller for Windows, macOS, and Linux. Keyboard and gamepad input, plus the engine-sound workaround and steering trim.

This is the **reference implementation** — if another client misbehaves, run this to confirm the car itself is fine.

## Install

```bash
pip install -r requirements.txt
python batmobile_control.py
```

If pygame fails to build, see [TROUBLESHOOTING.md](../../docs/TROUBLESHOOTING.md#desktop-pip-install-pygame-fails). Short version: use `pygame-ce`, which is what `requirements.txt` specifies.

## Controls

| Key | Action |
|---|---|
| `W` / `S` | Throttle forward / reverse |
| `A` / `D` | Steer left / right |
| `Shift` | Full boost (hold with throttle) |
| `L` | Toggle headlights |
| `K` | Toggle smoke generator |
| `Space` | Gun up/down |
| `R` | Gun rotate |
| `B` | Body / armor toggle |
| `[` / `]` | Steering trim left / right |
| `,` / `.` | Sweep engine sound index |
| `V` | Re-send current sound index |
| `M` | Toggle auto-mute |
| `-` / `=` | Adjust mute resend interval |
| `Esc` | Quit |

Plug in a gamepad and the left stick drives (X = steer, Y = throttle); face buttons map to lights, smoke, and guns.

## Notes

**Mute is on by default** and fires at launch, so the sound clip's ~1 second intro plays while you're getting set up rather than mid-drive. Press `M` to disable it.

If buttons feel delayed, that's the mute resend occupying the packet's one spare channel slot. Turn mute off.

**On exit** the controller sends several neutral packets so the car doesn't drive away if it was moving.

The HUD shows the exact packet being transmitted — useful for confirming the protocol is behaving.

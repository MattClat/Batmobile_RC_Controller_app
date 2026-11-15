#!/usr/bin/env python3
"""
batmobile_control.py — controller for the Mattel Ultimate Justice League
Batmobile (FKM40), rebuilt from the decompiled app's protocol.

The car listens on UDP 192.168.201.1:1051 and expects an ASCII command
string ~10x/second, e.g.  "41_80_31_80_50_F0_00_00_00"  (idle).
Each token pair is OPCODE_VALUE in hex:

    41 = throttle   80 stop | 81..E4 forward(1..100) | 01..64 reverse(1..100)
    31 = steering   80 center| 81..E4 one way         | 01..64 other way
    A1 = headlights 10 on / 01 off
    91 = smoke      10 on / 01 off
    21 = body/armor 64  |  gun up-down 21_E4
    11 = gun rotate E4
    01 = engine voice  01_<index>
    B1 = steering trim 00 / 81 / 01
    50_F0 = fixed marker, always appended
Trailing single byte is a heartbeat: 00, flipping to 01 every 10th packet.

You must be JOINED TO THE CAR'S WIFI (E6F4-BATMOBILE) for this to work.

    pip install pygame
    python3 batmobile_control.py

Controls (keyboard):
    W / S ............ throttle forward / reverse   (hold Shift = full boost)
    A / D ............ steer left / right
    L ................ toggle headlights
    K ................ toggle smoke
    Space ............ gun up/down (fire pose)
    R ................ gun rotation
    B ................ body / armor mode toggle
    [ / ] ............ steering trim left / right
    Esc .............. quit

Plug in a gamepad and the left stick drives it (X=steer, Y=throttle);
face buttons map to lights / smoke / guns.
"""

import socket
import sys
import time

try:
    import pygame
except ImportError:
    sys.exit("Need pygame:  pip install pygame")

CAR_IP = "192.168.201.1"
CAR_PORT = 1051
TICK_HZ = 10                      # app sends every 100 ms
DEADZONE = 0.12
CRUISE = 0.7                      # keyboard throttle without boost
TRIM_MARKER = "50_F0"
MUTE_SECONDS = 2.0               # default: re-send the silent index this often
MUTE_MIN, MUTE_MAX = 0.5, 2.9    # revert kicks in ~3s, so stay under that
AUTO_MUTE_ON_START = True        # fire the silent index at launch, before you drive
MUTE_START_VAL = 0x10            # index that silences the engine (0x0E/0x09/0x10 all work)


def hx(v):
    """Match Java Integer.toHexString: lowercase, no leading zero."""
    return format(int(v) & 0xFF, "x")


def throttle_token(axis):
    """axis in [-1,1]; +forward. Returns '41_xx' or None if neutral."""
    if abs(axis) < DEADZONE:
        return "41_80"
    mag = max(1, min(100, round(abs(axis) * 100)))
    val = mag + 128 if axis > 0 else mag      # fwd: 0x81..0xE4  rev: 0x01..0x64
    return "41_" + hx(val)


def steer_token(axis):
    """axis in [-1,1]; +right. Returns '31_xx'."""
    if abs(axis) < DEADZONE:
        return "31_80"
    mag = max(1, min(100, round(abs(axis) * 100)))
    val = mag + 128 if axis > 0 else mag
    return "31_" + hx(val)


class Batmobile:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.heartbeat = 0
        self.oneshots = []          # queued single-fire commands (A1_10, etc.)
        self.headlights = False
        self.smoke = False
        self.armor = False
        self.voice_val = 0          # opcode 01 sound index; sweep to hunt for silence
        self.mute = False           # when on, re-send the silent index on a timer
        self.mute_val = 0x10        # index found to silence the engine
        self.mute_secs = MUTE_SECONDS

    def queue(self, token):
        self.oneshots.append(token)

    def build(self, throttle, steer):
        """Replicates getSendCmd(): up to 3 channels + 50_F0 + pad + heartbeat."""
        pairs = [throttle, steer]
        if self.oneshots and len(pairs) < 3:
            pairs.append(self.oneshots.pop(0))
        pairs.append(TRIM_MARKER)
        while len(pairs) < 4:
            pairs.append("00_00")
        self.heartbeat = (self.heartbeat + 1) % 10
        tail = "01" if self.heartbeat == 0 else "00"
        return "_".join(pairs) + "_" + tail

    def send(self, cmd):
        try:
            self.sock.sendto(cmd.encode("ascii"), (CAR_IP, CAR_PORT))
        except OSError as e:
            print("send error:", e)


def main():
    pygame.init()
    screen = pygame.display.set_mode((560, 320))
    pygame.display.set_caption("Batmobile Control")
    font = pygame.font.SysFont("consolas", 18)
    big = pygame.font.SysFont("consolas", 22, bold=True)
    clock = pygame.time.Clock()

    pad = None
    if pygame.joystick.get_count():
        pad = pygame.joystick.Joystick(0)
        pad.init()
        print("Gamepad:", pad.get_name())

    car = Batmobile()
    last_cmd = ""
    mute_ticks = 0
    if AUTO_MUTE_ON_START:
        car.mute = True
        car.mute_val = MUTE_START_VAL
        car.voice_val = MUTE_START_VAL
        car.queue("01_" + hx(MUTE_START_VAL))
    running = True

    while running:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key == pygame.K_l:
                    car.headlights = not car.headlights
                    car.queue("A1_10" if car.headlights else "A1_01")
                elif e.key == pygame.K_k:
                    car.smoke = not car.smoke
                    car.queue("91_10" if car.smoke else "91_01")
                elif e.key == pygame.K_SPACE:
                    car.queue("21_E4")               # gun up/down
                elif e.key == pygame.K_r:
                    car.queue("11_E4")               # gun rotate
                elif e.key == pygame.K_b:
                    car.armor = not car.armor
                    car.queue("21_64")               # body/armor
                elif e.key == pygame.K_LEFTBRACKET:
                    car.queue("B1_01")               # trim left
                elif e.key == pygame.K_RIGHTBRACKET:
                    car.queue("B1_81")               # trim right
                elif e.key == pygame.K_COMMA:        # engine-sound sweep down
                    car.voice_val = (car.voice_val - 1) & 0xFF
                    car.queue("01_" + hx(car.voice_val))
                elif e.key == pygame.K_PERIOD:       # engine-sound sweep up
                    car.voice_val = (car.voice_val + 1) & 0xFF
                    car.queue("01_" + hx(car.voice_val))
                elif e.key == pygame.K_v:            # re-send current sound index
                    car.queue("01_" + hx(car.voice_val))
                elif e.key == pygame.K_m:            # toggle auto-mute
                    car.mute = not car.mute
                    if car.mute:
                        car.mute_val = car.voice_val  # lock in whatever's silent now
                        car.queue("01_" + hx(car.mute_val))
                        mute_ticks = 0
                elif e.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    car.mute_secs = max(MUTE_MIN, round(car.mute_secs - 0.25, 2))
                elif e.key in (pygame.K_EQUALS, pygame.K_KP_PLUS):
                    car.mute_secs = min(MUTE_MAX, round(car.mute_secs + 0.25, 2))
            elif e.type == pygame.JOYBUTTONDOWN and pad:
                b = e.button
                if b == 0:                            # A
                    car.queue("21_E4")
                elif b == 1:                          # B
                    car.headlights = not car.headlights
                    car.queue("A1_10" if car.headlights else "A1_01")
                elif b == 2:                          # X
                    car.smoke = not car.smoke
                    car.queue("91_10" if car.smoke else "91_01")
                elif b == 3:                          # Y
                    car.queue("11_E4")

        keys = pygame.key.get_pressed()
        boost = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        level = 1.0 if boost else CRUISE

        thr_axis = 0.0
        str_axis = 0.0
        if pad:
            str_axis = pad.get_axis(0)                # left stick X
            thr_axis = -pad.get_axis(1)              # left stick Y (up = fwd)
        # keyboard overrides / adds
        if keys[pygame.K_w]:
            thr_axis = level
        elif keys[pygame.K_s]:
            thr_axis = -level
        if keys[pygame.K_a]:
            str_axis = -level
        elif keys[pygame.K_d]:
            str_axis = level

        # keep the engine quiet: re-send the silent index before it wears off
        if car.mute:
            mute_ticks += 1
            if mute_ticks >= max(1, int(car.mute_secs * TICK_HZ)):
                car.queue("01_" + hx(car.mute_val))
                mute_ticks = 0

        cmd = car.build(throttle_token(thr_axis), steer_token(str_axis))
        car.send(cmd)
        last_cmd = cmd

        # --- HUD ---
        screen.fill((12, 12, 16))
        screen.blit(big.render("BATMOBILE", True, (200, 60, 60)), (16, 12))
        lines = [
            f"target   {CAR_IP}:{CAR_PORT}",
            f"packet   {last_cmd}",
            f"throttle {thr_axis:+.2f}   steer {str_axis:+.2f}",
            f"lights {'ON ' if car.headlights else 'off'}   "
            f"smoke {'ON ' if car.smoke else 'off'}   "
            f"gamepad {'yes' if pad else 'no'}",
            f"sound index (01) = 0x{car.voice_val:02X}   "
            f"[ , . sweep,  V resend — listen for a silent one ]",
            f"MUTE {('ON  0x%02X  every %.2fs' % (car.mute_val, car.mute_secs)) if car.mute else 'off'}"
            "   [ M toggle,  -/= interval ]",
            "",
            "W/S throttle  A/D steer  Shift boost",
            "L lights  K smoke  Space gun  R rotate  B armor",
            ", . sound sweep   M mute   -/= mute rate   [ ] trim   Esc quit",
        ]
        y = 60
        for ln in lines:
            screen.blit(font.render(ln, True, (180, 200, 180)), (16, y))
            y += 26
        pygame.display.flip()
        clock.tick(TICK_HZ)

    # send neutral a few times on exit so it doesn't run away
    for _ in range(5):
        car.send("41_80_31_80_50_F0_00_00_00")
        time.sleep(0.05)
    pygame.quit()


if __name__ == "__main__":
    main()

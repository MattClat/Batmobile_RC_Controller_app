# batmobile_ipad.py — Batmobile controller for Pythonista 3 on iPad
#
# Talks to the car over UDP 192.168.201.1:1051 using the protocol we
# reverse-engineered. Two thumbsticks, a button row, live packet readout.
#
# SETUP
#   1. Install Pythonista 3 from the App Store.
#   2. Put this file in Pythonista (see the notes at the bottom).
#   3. Join wifi  E6F4-BATMOBILE  password  BATMOBILE1
#   4. Run it. iOS will ask for Local Network permission -- say yes, or
#      nothing will work. (Settings > Pythonista 3 > Local Network if you
#      miss the prompt.)
#
# CONTROLS
#   left thumb  : steering    (drag left/right)
#   right thumb : throttle    (drag up = forward, down = reverse)
#   buttons     : lights, smoke, gun, rotate, armor, mute
#   both sticks spring back to neutral when you lift off.

import socket
import threading
import time

import ui

try:
    import console
except ImportError:
    console = None

CAR_IP = "192.168.201.1"
CAR_PORT = 1051
TICK_HZ = 10                 # the car expects a packet every 100 ms
DEADZONE = 0.10
TRIM_MARKER = "50_F0"

MUTE_VALUE = 0x10            # sound index that silences the engine
MUTE_INTERVAL = 2.0          # resend before the ~3 s revert
AUTO_MUTE = True             # fire it at launch so the intro plays early

BG = (0.06, 0.06, 0.08)
FG = (0.72, 0.80, 0.72)
ACCENT = (0.78, 0.16, 0.16)
DIM = (0.20, 0.20, 0.24)


def hx(v):
    """Match Java Integer.toHexString: lowercase, no leading zero."""
    return format(int(v) & 0xFF, "x")


def throttle_token(axis):
    if abs(axis) < DEADZONE:
        return "41_80"
    mag = max(1, min(100, int(round(abs(axis) * 100))))
    return "41_" + hx(mag + 128 if axis > 0 else mag)


def steer_token(axis):
    if abs(axis) < DEADZONE:
        return "31_80"
    mag = max(1, min(100, int(round(abs(axis) * 100))))
    return "31_" + hx(mag + 128 if axis > 0 else mag)


class Stick(object):
    """A thumbstick that springs back to centre when released."""

    def __init__(self, name, horizontal):
        self.name = name
        self.horizontal = horizontal
        self.cx = self.cy = 0.0
        self.radius = 110.0
        self.touch_id = None
        self.dx = 0.0
        self.dy = 0.0

    def contains(self, x, y):
        # generous grab area so you don't have to look at the screen
        return ((x - self.cx) ** 2 + (y - self.cy) ** 2) ** 0.5 < self.radius * 1.9

    def move_to(self, x, y):
        dx = x - self.cx
        dy = y - self.cy
        d = (dx * dx + dy * dy) ** 0.5
        if d > self.radius:
            dx *= self.radius / d
            dy *= self.radius / d
        self.dx, self.dy = dx, dy

    def release(self):
        self.touch_id = None
        self.dx = self.dy = 0.0

    @property
    def value(self):
        if self.horizontal:
            return self.dx / self.radius
        return -self.dy / self.radius          # screen y grows downward


class Batmobile(object):
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.settimeout(0.0)
        self.heartbeat = 0
        self.oneshots = []
        self.lights = False
        self.smoke = False
        self.armor = False
        self.mute = AUTO_MUTE
        self.mute_val = MUTE_VALUE
        self.last_cmd = ""
        self.replies = 0

    def queue(self, token):
        self.oneshots.append(token)

    def build(self, thr, steer):
        """Replicates getSendCmd(): channels + 50_F0 + padding + heartbeat."""
        pairs = [thr, steer]
        if self.oneshots and len(pairs) < 3:
            pairs.append(self.oneshots.pop(0))
        pairs.append(TRIM_MARKER)
        while len(pairs) < 4:
            pairs.append("00_00")
        self.heartbeat = (self.heartbeat + 1) % 10
        return "_".join(pairs) + "_" + ("01" if self.heartbeat == 0 else "00")

    def send(self, cmd):
        try:
            self.sock.sendto(cmd.encode("ascii"), (CAR_IP, CAR_PORT))
            self.last_cmd = cmd
        except OSError:
            pass
        # the car answers with 14-byte telemetry; use it as a link indicator
        try:
            while True:
                data, _ = self.sock.recvfrom(64)
                if not data:
                    break
                self.replies += 1
        except OSError:
            pass

    def neutral(self):
        for _ in range(5):
            self.send("41_80_31_80_50_F0_00_00_00")
            time.sleep(0.05)


class ControllerView(ui.View):
    def __init__(self, *args, **kwargs):
        ui.View.__init__(self, *args, **kwargs)
        self.background_color = BG
        self.multitouch_enabled = True

        self.car = Batmobile()
        self.steer = Stick("steer", horizontal=True)
        self.throttle = Stick("throttle", horizontal=False)

        self.make_buttons()

        self.running = True
        self.mute_ticks = 0
        if AUTO_MUTE:
            self.car.queue("01_" + hx(MUTE_VALUE))
        self.thread = threading.Thread(target=self.loop)
        self.thread.daemon = True
        self.thread.start()

    # ---------------------------------------------------------- buttons

    def make_buttons(self):
        specs = [
            ("LIGHTS", self.tap_lights),
            ("SMOKE", self.tap_smoke),
            ("GUN", self.tap_gun),
            ("ROTATE", self.tap_rotate),
            ("ARMOR", self.tap_armor),
            ("MUTE", self.tap_mute),
        ]
        self.buttons = {}
        for title, action in specs:
            b = ui.Button(title=title)
            b.background_color = DIM
            b.tint_color = FG
            b.corner_radius = 8
            b.font = ("Menlo", 15)
            b.action = action
            self.add_subview(b)
            self.buttons[title] = b

    def layout(self):
        w, h = self.width, self.height
        n = len(self.buttons)
        pad, top, bh = 10, 14, 44
        bw = (w - pad * (n + 1)) / float(n)
        for i, title in enumerate(["LIGHTS", "SMOKE", "GUN",
                                   "ROTATE", "ARMOR", "MUTE"]):
            self.buttons[title].frame = (pad + i * (bw + pad), top, bw, bh)

        r = min(140, max(80, h * 0.20))
        self.steer.radius = r
        self.throttle.radius = r
        cy = h * 0.63
        self.steer.cx, self.steer.cy = w * 0.22, cy
        self.throttle.cx, self.throttle.cy = w * 0.78, cy

    # ---------------------------------------------------------- actions

    def tap_lights(self, sender):
        self.car.lights = not self.car.lights
        self.car.queue("A1_10" if self.car.lights else "A1_01")
        sender.background_color = ACCENT if self.car.lights else DIM

    def tap_smoke(self, sender):
        self.car.smoke = not self.car.smoke
        self.car.queue("91_10" if self.car.smoke else "91_01")
        sender.background_color = ACCENT if self.car.smoke else DIM

    def tap_gun(self, sender):
        self.car.queue("21_E4")

    def tap_rotate(self, sender):
        self.car.queue("11_E4")

    def tap_armor(self, sender):
        self.car.armor = not self.car.armor
        self.car.queue("21_64")
        sender.background_color = ACCENT if self.car.armor else DIM

    def tap_mute(self, sender):
        self.car.mute = not self.car.mute
        if self.car.mute:
            self.car.queue("01_" + hx(self.car.mute_val))
            self.mute_ticks = 0
        sender.background_color = ACCENT if self.car.mute else DIM

    # ---------------------------------------------------------- touches

    def _claim(self, touch):
        x, y = touch.location
        for stick in (self.steer, self.throttle):
            if stick.touch_id is None and stick.contains(x, y):
                stick.touch_id = touch.touch_id
                stick.move_to(x, y)
                return

    def touch_began(self, touch):
        self._claim(touch)
        self.set_needs_display()

    def touch_moved(self, touch):
        x, y = touch.location
        for stick in (self.steer, self.throttle):
            if stick.touch_id == touch.touch_id:
                stick.move_to(x, y)
        self.set_needs_display()

    def touch_ended(self, touch):
        for stick in (self.steer, self.throttle):
            if stick.touch_id == touch.touch_id:
                stick.release()
        self.set_needs_display()

    # ---------------------------------------------------------- drawing

    def draw(self):
        w, h = self.width, self.height

        ui.set_color(ACCENT)
        ui.draw_string("BATMOBILE", rect=(0, 66, w, 30),
                       font=("Menlo-Bold", 22), alignment=ui.ALIGN_CENTER)

        link = "linked" if self.car.replies else "sending"
        info = "%s:%d   %s   %s" % (CAR_IP, CAR_PORT, link, self.car.last_cmd)
        ui.set_color(FG)
        ui.draw_string(info, rect=(0, h - 34, w, 24),
                       font=("Menlo", 13), alignment=ui.ALIGN_CENTER)

        self.draw_stick(self.steer, "STEER", horizontal=True)
        self.draw_stick(self.throttle, "THROTTLE", horizontal=False)

    def draw_stick(self, stick, label, horizontal):
        cx, cy, r = stick.cx, stick.cy, stick.radius

        ui.set_color(DIM)
        base = ui.Path.oval(cx - r, cy - r, r * 2, r * 2)
        base.line_width = 3
        base.stroke()

        # axis hint through the middle
        ui.set_color((0.16, 0.16, 0.20))
        guide = ui.Path()
        if horizontal:
            guide.move_to(cx - r, cy)
            guide.line_to(cx + r, cy)
        else:
            guide.move_to(cx, cy - r)
            guide.line_to(cx, cy + r)
        guide.line_width = 2
        guide.stroke()

        # the thumb knob
        kx, ky = cx + stick.dx, cy + stick.dy
        kr = r * 0.38
        active = stick.touch_id is not None
        ui.set_color(ACCENT if active else (0.30, 0.30, 0.34))
        ui.Path.oval(kx - kr, ky - kr, kr * 2, kr * 2).fill()

        ui.set_color(FG)
        ui.draw_string(label, rect=(cx - r, cy + r + 10, r * 2, 22),
                       font=("Menlo", 14), alignment=ui.ALIGN_CENTER)

        val = stick.value
        ui.draw_string("%+.2f" % (0.0 if abs(val) < DEADZONE else val),
                       rect=(cx - r, cy + r + 32, r * 2, 22),
                       font=("Menlo", 13), alignment=ui.ALIGN_CENTER)

    # ---------------------------------------------------------- send loop

    def loop(self):
        period = 1.0 / TICK_HZ
        mute_every = max(1, int(MUTE_INTERVAL * TICK_HZ))
        while self.running:
            start = time.time()

            if self.car.mute:
                self.mute_ticks += 1
                if self.mute_ticks >= mute_every:
                    self.car.queue("01_" + hx(self.car.mute_val))
                    self.mute_ticks = 0

            cmd = self.car.build(throttle_token(self.throttle.value),
                                 steer_token(self.steer.value))
            self.car.send(cmd)

            slept = time.time() - start
            if slept < period:
                time.sleep(period - slept)

    def will_close(self):
        self.running = False
        time.sleep(0.2)
        self.car.neutral()          # don't let it drive away
        if console:
            console.set_idle_timer_disabled(False)


def main():
    if console:
        console.set_idle_timer_disabled(True)   # keep the screen awake
    v = ControllerView()
    v.name = "Batmobile"
    v.present("fullscreen", hide_title_bar=False)


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------
# GETTING THIS FILE ONTO THE IPAD
#
# Easiest: email or AirDrop it to yourself, then Share > Copy to Pythonista.
# Or: Pythonista can open files from iCloud Drive -- drop it in
#     iCloud Drive/Pythonista 3/ and it appears in the script library.
# Or: just retype/paste it. Make a new script in Pythonista, paste, save.
#
# LAUNCH IT LIKE AN APP
#   Shortcuts app > new shortcut > "Run Pythonista Script" > pick this one
#   > share sheet > Add to Home Screen. Now it has its own icon.
#
# IF IT DOESN'T MOVE
#   * Confirm you're on E6F4-BATMOBILE, not your house wifi.
#   * Settings > Pythonista 3 > Local Network must be ON.
#   * The readout at the bottom shows the exact packet being sent; it should
#     be changing as you move the sticks. If it says "sending" forever and
#     the car ignores you, the packets are going out but not arriving --
#     check the wifi. "linked" means the car is answering back.
# ---------------------------------------------------------------------

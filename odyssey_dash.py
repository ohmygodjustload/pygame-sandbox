"""
2006 Honda Odyssey digital instrument cluster (pygame)

Composites the pre-rendered assets in ``assets/odyssey/`` over a live vehicle
simulation. The visual language is a 1985 Nissan 300ZX digital cluster; the
data model is an Odyssey EX-L: J35A7 3.5 V6, 5-speed automatic, 21.0 gal tank,
6300 rpm redline, Variable Cylinder Management.

Generate the assets first:

    python tools/gen_odyssey_assets.py

Then run:

    python odyssey_dash.py            # native 1280x520
    python odyssey_dash.py --scale 0.8

Press F1 in the window for the control list.
"""

from __future__ import annotations

import argparse
import os
import sys

import pygame

import odyssey_layout as L
from odyssey_layout import (
    BAR_FRAME_COUNT,
    C,
    CANVAS_H,
    CANVAS_W,
    FONT_DSEG7,
    FPS,
    GEARS,
    LABEL_FONT_NAME,
    LAMPS,
    TACH_FRAME_COUNT,
    TACH_RPM_STEP,
    gear_rect,
    lamp_rect,
)


# ---------------------------------------------------------------------------
# Drivetrain constants (2006 Odyssey EX-L, 235/65R16)
# ---------------------------------------------------------------------------

GEAR_RATIOS = (2.652, 1.517, 1.037, 0.738, 0.566)
FINAL_DRIVE = 4.312
REVS_PER_MILE = 720
IDLE_RPM = 700
REDLINE_RPM = L.TACH_REDLINE_RPM
FUEL_CAPACITY = L.FUEL_CAPACITY_GAL
LOW_FUEL_GAL = 2.4

COOLANT_AMBIENT_F = 74.0
COOLANT_THERMOSTAT_F = 195.0


def rpm_for(speed_mph: float, gear: int) -> float:
    ratio = GEAR_RATIOS[gear - 1]
    return speed_mph * REVS_PER_MILE * ratio * FINAL_DRIVE / 60.0


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def ease(current: float, target: float, rate: float) -> float:
    return current + (target - current) * clamp(rate, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------


class Assets:
    def __init__(self) -> None:
        root = L.ASSET_ROOT
        if not os.path.isdir(root):
            raise SystemExit(
                f"Assets missing at {root}\nRun:  python tools/gen_odyssey_assets.py"
            )

        self.background = self._img(os.path.join(root, "background.png"))
        self.tach = [
            self._img(os.path.join(root, "tach", f"tach_{i:02d}.png"))
            for i in range(TACH_FRAME_COUNT)
        ]
        self.bars = {
            key: [
                self._img(os.path.join(root, "bars", f"{key}_{i:02d}.png"))
                for i in range(BAR_FRAME_COUNT)
            ]
            for key in ("fuel", "temp", "oil", "volt")
        }
        self.lamps = {
            key: self._img(os.path.join(root, "lamps", f"{key}.png"))
            for key, _glyph, _col in LAMPS
        }
        for extra in ("turn_left", "turn_right", "cruise", "eco", "pip"):
            self.lamps[extra] = self._img(os.path.join(root, "lamps", f"{extra}.png"))
        self.gear = [
            self._img(os.path.join(root, "gear", f"gear_{i}.png")) for i in range(len(GEARS))
        ]

        self.seg_speed = pygame.font.Font(FONT_DSEG7, 48)
        self.seg_med = pygame.font.Font(FONT_DSEG7, 30)
        self.seg_fuel = pygame.font.Font(FONT_DSEG7, 26)
        self.seg_odo = pygame.font.Font(FONT_DSEG7, 32)
        self.seg_trip = pygame.font.Font(FONT_DSEG7, 24)
        self.seg_temp = pygame.font.Font(FONT_DSEG7, 26)
        self.help_font = pygame.font.SysFont(LABEL_FONT_NAME, 13)
        self.help_title = pygame.font.SysFont(LABEL_FONT_NAME, 15, bold=True)

    @staticmethod
    def _img(path: str) -> pygame.Surface:
        if not os.path.isfile(path):
            raise SystemExit(
                f"Missing asset: {path}\nRun:  python tools/gen_odyssey_assets.py"
            )
        return pygame.image.load(path).convert_alpha()


# ---------------------------------------------------------------------------
# Vehicle model
# ---------------------------------------------------------------------------

# Manually toggled warning lamps -> key binding.
MANUAL_LAMP_KEYS = {
    pygame.K_m: "mil",
    pygame.K_a: "abs",
    pygame.K_v: "vsa_off",
    pygame.K_s: "srs",
    pygame.K_z: "seatbelt",
    pygame.K_o: "door",
    pygame.K_k: "slide_door",
    pygame.K_g: "tailgate",
    pygame.K_w: "washer",
    pygame.K_j: "maint",
    pygame.K_e: "brake",
    pygame.K_y: "security",
    pygame.K_b: "highbeam",
}

LEVER_KEYS = {
    pygame.K_p: 0,
    pygame.K_r: 1,
    pygame.K_n: 2,
    pygame.K_d: 3,
    pygame.K_3: 4,
    pygame.K_2: 5,
    pygame.K_1: 6,
}

# Lever position -> highest selectable gear.
LEVER_GEAR_CAP = {0: 1, 1: 1, 2: 1, 3: 5, 4: 3, 5: 2, 6: 1}


class Vehicle:
    def __init__(self) -> None:
        self.engine_on = True
        self.throttle = 0.0
        self.brake = 0.0
        self.speed = 0.0
        self.rpm = float(IDLE_RPM)
        self.gear = 1
        self.shift_cooldown = 0.0
        self.lever = 3                      # D

        self.coolant_f = COOLANT_AMBIENT_F
        self.oil_psi = 0.0
        self.volts = 12.4
        self.outside_f = 74.0

        self.fuel = 17.5
        self.odo = 118_412.0
        self.trip_a = 213.6
        self.trip_b = 41.2
        self.gal_since_a = 8.6
        self.instant_gph = 0.0

        self.cruise_on = False
        self.cruise_set = 0.0
        self.vcm_active = False
        self.wheelspin = 0.0
        self.turn_left = False
        self.turn_right = False

        self.manual_lamps = {key: False for key, _g, _c in LAMPS}
        self.lamp_test = False

    # -- input ---------------------------------------------------------------

    def apply_held_keys(self, keys, dt: float) -> None:
        want_throttle = 1.0 if keys[pygame.K_UP] else 0.0
        want_brake = 1.0 if (keys[pygame.K_DOWN] or keys[pygame.K_SPACE]) else 0.0

        if self.cruise_on and want_throttle == 0.0 and want_brake == 0.0:
            error = self.cruise_set - self.speed
            want_throttle = clamp(error * 0.12, 0.0, 0.55)

        self.throttle = ease(self.throttle, want_throttle, min(1.0, dt * 7.0))
        self.brake = ease(self.brake, want_brake, min(1.0, dt * 12.0))
        self.lamp_test = bool(keys[pygame.K_l])

        if want_brake > 0.0:
            self.cruise_on = False

    def handle_keydown(self, event: pygame.event.Event) -> bool:
        if event.key == pygame.K_ESCAPE:
            return False
        if event.key in LEVER_KEYS:
            self.lever = LEVER_KEYS[event.key]
            if self.lever != 3:
                self.cruise_on = False
        elif event.key in MANUAL_LAMP_KEYS:
            name = MANUAL_LAMP_KEYS[event.key]
            self.manual_lamps[name] = not self.manual_lamps[name]
        elif event.key == pygame.K_c:
            if self.cruise_on:
                self.cruise_on = False
            elif self.speed >= 25 and self.lever == 3:
                self.cruise_on = True
                self.cruise_set = self.speed
        elif event.key == pygame.K_x:
            self.engine_on = not self.engine_on
            if not self.engine_on:
                self.cruise_on = False
        elif event.key == pygame.K_q:
            mods = pygame.key.get_mods()
            self.fuel = 2.0 if (mods & pygame.KMOD_SHIFT) else FUEL_CAPACITY
        elif event.key == pygame.K_t:
            if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                self.trip_b = 0.0
            else:
                self.trip_a = 0.0
                self.gal_since_a = 0.0
        return True

    # -- simulation ----------------------------------------------------------

    def update(self, dt: float) -> None:
        self._update_motion(dt)
        self._update_driveline(dt)
        self._update_fluids(dt)
        self._update_consumption(dt)

    def _update_motion(self, dt: float) -> None:
        drives = self.engine_on and self.lever in (3, 4, 5, 6)
        drive_accel = 0.0
        if drives:
            # Falls off as speed rises; roughly 0-60 in 9 s at full throttle.
            drive_accel = self.throttle * 7.2 * (1.0 - self.speed / 132.0)
        road_drag = 0.25 + 0.00035 * self.speed**2
        decel = self.brake * 15.0 + road_drag
        self.speed = clamp(self.speed + (drive_accel - decel) * dt, 0.0, 130.0)

        # Traction loss when stomping it from low speed.
        spin = 1.0 if (drives and self.throttle > 0.82 and self.speed < 22) else 0.0
        self.wheelspin = ease(self.wheelspin, spin, min(1.0, dt * 6.0))

    def _update_driveline(self, dt: float) -> None:
        if not self.engine_on:
            self.rpm = ease(self.rpm, 0.0, min(1.0, dt * 4.0))
            self.gear = 1
            return

        if self.lever in (0, 2):            # Park / Neutral - free rev
            target = IDLE_RPM + self.throttle * (REDLINE_RPM - IDLE_RPM) * 0.92
            self.rpm = ease(self.rpm, target, min(1.0, dt * 5.5))
            self.gear = 1
            return

        cap = LEVER_GEAR_CAP[self.lever]
        self.shift_cooldown = max(0.0, self.shift_cooldown - dt)
        want = self._select_gear(cap)
        if want != self.gear and self.shift_cooldown == 0.0:
            self.gear = want
            self.shift_cooldown = 0.45

        target = max(float(IDLE_RPM), rpm_for(self.speed, self.gear))
        if self.lever == 1:                 # Reverse holds the converter loaded
            target = max(target, IDLE_RPM + self.throttle * 2200)
        self.rpm = clamp(ease(self.rpm, target, min(1.0, dt * 6.0)), 0.0, L.TACH_MAX_RPM)

    def _select_gear(self, cap: int) -> int:
        # Hold a higher rpm the harder the throttle is pressed.
        min_rpm = 1150 + self.throttle * 1750
        best = 1
        for g in range(1, cap + 1):
            if rpm_for(self.speed, g) >= min_rpm:
                best = g
        return best

    def _update_fluids(self, dt: float) -> None:
        if self.engine_on:
            load = 0.35 + self.throttle * 0.9
            target = COOLANT_THERMOSTAT_F + self.throttle * 22.0
            rate = 0.016 * load if self.coolant_f < COOLANT_THERMOSTAT_F else 0.006
            self.coolant_f = ease(self.coolant_f, target, min(1.0, dt * rate * 6.0))
            self.oil_psi = ease(self.oil_psi, clamp(12 + self.rpm * 0.011, 0, 90), min(1.0, dt * 5))
            self.volts = ease(self.volts, 14.2 - self.throttle * 0.25, min(1.0, dt * 2.0))
        else:
            self.coolant_f = ease(self.coolant_f, COOLANT_AMBIENT_F, min(1.0, dt * 0.01))
            self.oil_psi = ease(self.oil_psi, 0.0, min(1.0, dt * 4.0))
            self.volts = ease(self.volts, 12.4, min(1.0, dt * 1.5))

        self.vcm_active = (
            self.engine_on
            and self.lever == 3
            and self.gear >= 4
            and self.speed > 25
            and self.throttle < 0.22
            and self.coolant_f > 170
            and self.fuel > 0.2
        )

    def _update_consumption(self, dt: float) -> None:
        if not self.engine_on or self.fuel <= 0.0:
            self.instant_gph = 0.0
            if self.fuel <= 0.0:
                self.engine_on = False
            return

        # Road-load horsepower, then a BSFC-style fuel rate.
        road_hp = 0.011 * self.speed + 0.00013 * self.speed**3
        accel_hp = self.throttle * 62.0
        gph = 0.30 + (road_hp + accel_hp) * 0.0725
        if self.vcm_active:
            gph *= 0.78
        self.instant_gph = gph

        used = gph * dt / 3600.0
        self.fuel = max(0.0, self.fuel - used)
        self.gal_since_a += used

        miles = self.speed * dt / 3600.0
        self.odo = min(999_999.0, self.odo + miles)
        self.trip_a = min(999.9, self.trip_a + miles)
        self.trip_b = min(999.9, self.trip_b + miles)

    # -- derived readouts ----------------------------------------------------

    @property
    def avg_mpg(self) -> float:
        if self.gal_since_a < 0.05:
            return 0.0
        return clamp(self.trip_a / self.gal_since_a, 0.0, 99.9)

    @property
    def dte(self) -> float:
        mpg = self.avg_mpg or 24.0
        return clamp(self.fuel * mpg, 0.0, 999.0)

    @property
    def instant_mpg(self) -> float:
        if self.instant_gph < 0.01 or self.speed < 1.0:
            return 0.0
        return clamp(self.speed / self.instant_gph, 0.0, 99.9)

    def lamp_state(self, key: str, blink: bool) -> bool:
        if self.lamp_test:
            return True
        if key == "low_fuel":
            return self.fuel <= LOW_FUEL_GAL
        if key == "oil_press":
            return (not self.engine_on) or self.oil_psi < 10
        if key == "battery":
            return self.volts < 13.0
        if key == "vcm":
            return self.vcm_active
        if key == "vsa":
            return self.wheelspin > 0.35 and blink
        if key == "security":
            return (not self.engine_on) and blink
        return self.manual_lamps.get(key, False)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def seg_text(
    surface: pygame.Surface,
    font: pygame.font.Font,
    value: str,
    midright: tuple[int, int],
    color=C.CYAN,
) -> None:
    rendered = font.render(value, True, color)
    surface.blit(rendered, rendered.get_rect(midright=midright))


def draw_cluster(
    canvas: pygame.Surface, a: Assets, v: Vehicle, blink: bool, show_help: bool
) -> None:
    canvas.blit(a.background, (0, 0))

    # Tachometer bar-graph
    frame = int(clamp(round(v.rpm / TACH_RPM_STEP), 0, TACH_FRAME_COUNT - 1))
    canvas.blit(a.tach[frame], (L.TACH_BAR_RECT[0], L.TACH_BAR_RECT[1]))

    # Vertical bar gauges
    _blit_bar(canvas, a, "fuel", v.fuel / FUEL_CAPACITY, L.FUEL_BAR_RECT)
    _blit_bar(
        canvas,
        a,
        "temp",
        (v.coolant_f - L.COOLANT_MIN_F) / (L.COOLANT_MAX_F - L.COOLANT_MIN_F),
        (L.TRIPLE_BAR_X[0], L.TRIPLE_BAR_Y, L.TRIPLE_BAR_W, L.TRIPLE_BAR_H),
    )
    _blit_bar(
        canvas,
        a,
        "oil",
        (v.oil_psi - L.OIL_MIN_PSI) / (L.OIL_MAX_PSI - L.OIL_MIN_PSI),
        (L.TRIPLE_BAR_X[1], L.TRIPLE_BAR_Y, L.TRIPLE_BAR_W, L.TRIPLE_BAR_H),
    )
    _blit_bar(
        canvas,
        a,
        "volt",
        (v.volts - L.VOLT_MIN_V) / (L.VOLT_MAX_V - L.VOLT_MIN_V),
        (L.TRIPLE_BAR_X[2], L.TRIPLE_BAR_Y, L.TRIPLE_BAR_W, L.TRIPLE_BAR_H),
    )

    # Indicator strip
    for i, (key, _glyph, _col) in enumerate(LAMPS):
        if v.lamp_state(key, blink):
            canvas.blit(a.lamps[key], lamp_rect(i)[:2])

    # Turn signals, cruise, ECO / VCM badge
    if (v.turn_left and blink) or v.lamp_test:
        canvas.blit(a.lamps["turn_left"], L.TURN_L_RECT[:2])
    if (v.turn_right and blink) or v.lamp_test:
        canvas.blit(a.lamps["turn_right"], L.TURN_R_RECT[:2])
    if v.cruise_on or v.lamp_test:
        canvas.blit(a.lamps["cruise"], L.CRUISE_LAMP_RECT[:2])
    if v.vcm_active or v.lamp_test:
        canvas.blit(a.lamps["eco"], L.VCM_BADGE_RECT[:2])

    # Selector lever position
    canvas.blit(a.gear[v.lever], gear_rect(v.lever)[:2])

    # Digital readouts
    seg_text(canvas, a.seg_speed, f"{int(round(v.speed))}", L.SPEED_DIGITS_MIDRIGHT)
    seg_text(canvas, a.seg_med, f"{int(round(v.rpm / 100))}", L.TACH_DIGITS_MIDRIGHT)
    seg_text(canvas, a.seg_fuel, f"{int(round(v.fuel))}", L.FUEL_DIGITS_MIDRIGHT)
    seg_text(canvas, a.seg_odo, f"{int(v.odo):06d}", L.ODO_DIGITS_MIDRIGHT)
    seg_text(canvas, a.seg_temp, f"{int(round(v.outside_f))}", L.OUTSIDE_TEMP_MIDRIGHT)

    values = {
        "trip_a": f"{v.trip_a:.1f}",
        "trip_b": f"{v.trip_b:.1f}",
        "avg_mpg": f"{v.avg_mpg:.1f}",
        "dte": f"{int(round(v.dte))}",
    }
    for key, _label, _box, digits_mr, _unit, _unit_tl, _ghost in L.TRIP_FIELDS:
        seg_text(canvas, a.seg_trip, values[key], digits_mr)

    # Speed reference pips
    pip = a.lamps["pip"]
    for mph in L.SPEED_SCALE_TICKS:
        if v.speed + 0.5 >= mph:
            t = mph / max(L.SPEED_SCALE_TICKS)
            px = L.SPEED_SCALE_X0 + (L.SPEED_SCALE_X1 - L.SPEED_SCALE_X0) * t
            canvas.blit(pip, pip.get_rect(center=(int(px), L.SPEED_SCALE_Y + L.SPEED_PIP_DY)))

    if show_help:
        draw_help(canvas, a)


def _blit_bar(canvas: pygame.Surface, a: Assets, key: str, frac: float, rect) -> None:
    frame = int(clamp(round(clamp(frac, 0.0, 1.0) * (BAR_FRAME_COUNT - 1)), 0, BAR_FRAME_COUNT - 1))
    canvas.blit(a.bars[key][frame], rect[:2])


HELP_LINES = (
    ("Drive", "UP throttle   DOWN / SPACE brake   C cruise   X engine on/off"),
    ("Lever", "P  R  N  D  3  2  1"),
    ("Signals", "LEFT / RIGHT turn signals   B high beam   L lamp test (hold)"),
    ("Warnings", "M check engine   A ABS   V VSA OFF   S SRS   Z seatbelt"),
    ("", "O door   K sliding door   G tailgate   W washer   J maint   E park brake   Y security"),
    ("Fuel/Trip", "Q refuel   SHIFT+Q drain   T reset trip A   SHIFT+T reset trip B"),
    ("Window", "F1 toggle this help   ESC quit"),
)


def draw_help(canvas: pygame.Surface, a: Assets) -> None:
    pad = 16
    w, h = 760, 30 + len(HELP_LINES) * 20 + pad
    panel = pygame.Surface((w, h), pygame.SRCALPHA)
    panel.fill((4, 12, 14, 236))
    pygame.draw.rect(panel, C.CYAN_MID, panel.get_rect(), 1, border_radius=4)
    title = a.help_title.render("CONTROLS", True, C.CYAN)
    panel.blit(title, (pad, 10))
    y = 34
    for label, text in HELP_LINES:
        if label:
            panel.blit(a.help_font.render(label, True, C.LABEL), (pad, y))
        panel.blit(a.help_font.render(text, True, C.LABEL_DIM), (pad + 78, y))
        y += 20
    canvas.blit(panel, ((CANVAS_W - w) // 2, (CANVAS_H - h) // 2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="2006 Honda Odyssey digital cluster")
    parser.add_argument("--scale", type=float, default=1.0, help="window scale (default 1.0)")
    args = parser.parse_args(argv)

    pygame.init()
    pygame.display.set_caption("2006 Honda Odyssey - Digital Cluster")

    scale = clamp(args.scale, 0.3, 2.0)
    win_w, win_h = int(CANVAS_W * scale), int(CANVAS_H * scale)
    window = pygame.display.set_mode((win_w, win_h))

    assets = Assets()
    canvas = pygame.Surface((CANVAS_W, CANVAS_H)).convert()
    vehicle = Vehicle()
    clock = pygame.time.Clock()

    show_help = False
    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        now_ms = pygame.time.get_ticks()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F1:
                    show_help = not show_help
                elif event.key == pygame.K_LEFT:
                    vehicle.turn_left = not vehicle.turn_left
                    vehicle.turn_right = False
                elif event.key == pygame.K_RIGHT:
                    vehicle.turn_right = not vehicle.turn_right
                    vehicle.turn_left = False
                else:
                    running = vehicle.handle_keydown(event) and running

        vehicle.apply_held_keys(pygame.key.get_pressed(), dt)
        vehicle.update(dt)

        blink = (now_ms // 380) % 2 == 0
        draw_cluster(canvas, assets, vehicle, blink, show_help)

        if scale == 1.0:
            window.blit(canvas, (0, 0))
        else:
            pygame.transform.smoothscale(canvas, (win_w, win_h), window)
        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()

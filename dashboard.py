"""
VW Digifiz dashboard (pygame)

Asset-driven recreation of the 80s VW Digifiz cluster, layered on top of the
1920x720 background image from the Digifiz-Dash project (gfunkbus76 on
GitHub) and the DSEG-7 7-segment font. The cluster is rendered onto an
internal 1920x720 surface and then blit-scaled down to a friendlier window
size.

Controls
--------
UP / DOWN ........ speed (and rpm-derived) +/- 1
LEFT / RIGHT ..... rpm  +/- 100 r/min (manual override)
F / V ............ fuel +/- 1 L (FUEL R indicator triggers below 7 L)
T / G ............ MFA temperature display +/- 1
B / N ............ boost level frame +/- 1
C ................ coolant frame +/- 1
O ................ oil-pressure frame +/- 1
E ................ EGT frame +/- 1
1 ................ toggle illumination indicator
2 ................ toggle foglight indicator
3 ................ toggle defog indicator
4 ................ toggle highbeam indicator
[ / ] ............ toggle left / right turn signal
5 ................ toggle brake-warn indicator
6 ................ toggle oil-light indicator
7 ................ toggle alternator indicator
8 ................ toggle glow-plug indicator
ESC / X / window-close ... quit
"""

from __future__ import annotations

import math
import os
import sys
from datetime import datetime

import pygame


# ---------------------------------------------------------------------------
# Paths & display setup
# ---------------------------------------------------------------------------

ASSET_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "digifiz")

NATIVE_W, NATIVE_H = 1920, 720
DEFAULT_SCALE = 0.66            # window = 1267x475 by default
FPS = 60


# ---------------------------------------------------------------------------
# Colours (used only for text rendered from DSEG fonts)
# ---------------------------------------------------------------------------

NEON_YELLOW = (236, 253, 147)   # speedometer
NEON_GREEN = (145, 213, 89)     # clock, MFA, fuel, odo
DARK_GREY = (9, 52, 50)         # ghost segments


# ---------------------------------------------------------------------------
# Layout constants - lifted from temp/Digifiz-Dash/constants.py so the
# overlay positions line up with the painted background image.
# ---------------------------------------------------------------------------

RPM_XY = (135, 5)
COOLANT_XY = (1481, 105)
EGT_XY = (1599, 105)
OILPRESSURE_XY = (1711, 105)
BOOST_XY = (1822, 105)

CLOCK_XY = (555, 620)
FUEL_XY = (1717, 667)           # midright anchor for fuel digits
ODO_L_XY = (395, 678)           # midright anchor for odometer

MFABG_XY = (1021, 563)          # MFA background overlay top-left
MFA_XY = (1435, 668)            # midright anchor for MFA temp digits
SPEEDO_XY = (1247, 305)         # midright anchor for speed digits

FUELRES_XY = (1795, 616)

FONT_LARGE = 174                # speedometer
FONT_MEDIUM = 94                # clock / MFA / fuel
FONT_SMALL = 67                 # odometer

TACH_MAX_RPM = 5000             # gauge frames are 0..5000 in 100-r/min steps


# ---------------------------------------------------------------------------
# Indicator metadata
# ---------------------------------------------------------------------------
#
# Each indicator has a position (top-left) and the file-name stem used by the
# repo (`<stem>On.png` and `<stem>Off.png`). Positions come from
# `temp/Digifiz-Dash/main.py::draw_indicators`.

INDICATORS: dict[str, tuple[str, tuple[int, int]]] = {
    "illumination": ("illumination", (45, 460)),
    "foglight":     ("foglight",     (185, 460)),
    "defog":        ("defog",        (325, 460)),
    "highbeam":     ("highbeam",     (465, 460)),
    "leftturn":     ("leftturn",     (605, 460)),
    "rightturn":    ("rightturn",    (1220, 460)),
    "brakewarn":    ("brakewarn",    (1360, 460)),
    "oillight":     ("oillight",     (1500, 460)),
    "alt":          ("alt",          (1640, 460)),
    "glow":         ("glow",         (1780, 460)),
}


# ---------------------------------------------------------------------------
# Asset loader
# ---------------------------------------------------------------------------


class Assets:
    """Container that loads every Digifiz-Dash image + font once at startup."""

    def __init__(self) -> None:
        self.background = self._load("background.png")
        self.mfa = self._load(os.path.join("indicators", "MFA_temp.png"))
        self.fuelres_on = self._load(os.path.join("indicators", "fuelResOn.png"))
        self.fuelres_off = self._load(os.path.join("indicators", "fuelResOff.png"))

        self.rpm_frames: list[pygame.Surface] = []
        for hundreds in range(0, TACH_MAX_RPM // 100 + 1):
            name = f"RPM {hundreds}00.png"
            self.rpm_frames.append(self._load(os.path.join("rpm", name)))

        self.aux_frames: list[pygame.Surface] = []
        for i in range(20):
            self.aux_frames.append(self._load(os.path.join("gauges", f"aux{i}.png")))

        self.indicator_on: dict[str, pygame.Surface] = {}
        self.indicator_off: dict[str, pygame.Surface] = {}
        for key, (stem, _pos) in INDICATORS.items():
            self.indicator_on[key] = self._load(os.path.join("indicators", f"{stem}On.png"))
            try:
                self.indicator_off[key] = self._load(os.path.join("indicators", f"{stem}Off.png"))
            except (pygame.error, FileNotFoundError):
                self.indicator_off[key] = None  # type: ignore[assignment]

        font_path = os.path.join(ASSET_ROOT, "fonts", "DSEG7Classic-Bold.ttf")
        self.font_speed = pygame.font.Font(font_path, FONT_LARGE)
        self.font_medium = pygame.font.Font(font_path, FONT_MEDIUM)
        self.font_small = pygame.font.Font(font_path, FONT_SMALL)

    @staticmethod
    def _load(rel_path: str) -> pygame.Surface:
        path = os.path.join(ASSET_ROOT, rel_path)
        return pygame.image.load(path).convert_alpha()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def ease_toward(current: float, target: float, rate: float) -> float:
    return current + (target - current) * clamp(rate, 0.0, 1.0)


def rpm_to_frame_index(rpm: float) -> int:
    """Snap rpm to nearest available frame (0..50)."""
    idx = int(round(rpm / 100.0))
    return clamp(idx, 0, TACH_MAX_RPM // 100)


def render_anchored_text(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    midright: tuple[int, int],
    color: tuple[int, int, int],
    ghost_text: str | None = None,
) -> None:
    """Render `text` so its midright sits at `midright`. Optionally draw a
    dim ghost (e.g. '888' under '049') first to mimic LCD off-segments."""
    if ghost_text is not None:
        ghost = font.render(ghost_text, True, DARK_GREY)
        rect = ghost.get_rect(midright=midright)
        surface.blit(ghost, rect)
    rendered = font.render(text, True, color)
    rect = rendered.get_rect(midright=midright)
    surface.blit(rendered, rect)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def make_state() -> dict:
    return {
        "speed_target": 55.0,
        "speed": 55.0,
        "rpm_target": 2200.0,
        "rpm": 2200.0,
        "rpm_manual": False,
        "fuel": 31.0,            # litres (matches the photo's "31")
        "outside_temp": 18.0,    # MFA reading, deg C
        "odo": 10000,
        "boost_frame": 8,
        "coolant_frame": 12,
        "oilpressure_frame": 14,
        "egt_frame": 9,
        "indicators": {key: 0 for key in INDICATORS},
        "fuelres_blink_phase": 0.0,
    }


# ---------------------------------------------------------------------------
# Draw routines
# ---------------------------------------------------------------------------


def draw_rpm(target: pygame.Surface, assets: Assets, rpm: float) -> None:
    idx = rpm_to_frame_index(rpm)
    target.blit(assets.rpm_frames[idx], RPM_XY)


def draw_aux_gauges(target: pygame.Surface, assets: Assets, state: dict) -> None:
    for frame_key, pos in (
        ("coolant_frame", COOLANT_XY),
        ("egt_frame", EGT_XY),
        ("oilpressure_frame", OILPRESSURE_XY),
        ("boost_frame", BOOST_XY),
    ):
        idx = clamp(int(state[frame_key]), 0, len(assets.aux_frames) - 1)
        target.blit(assets.aux_frames[idx], pos)


def draw_speed(target: pygame.Surface, assets: Assets, speed: float) -> None:
    digits = max(0, int(round(speed)))
    text = str(digits)
    render_anchored_text(
        target,
        assets.font_speed,
        text,
        SPEEDO_XY,
        NEON_YELLOW,
        ghost_text="888",
    )


def draw_clock(target: pygame.Surface, assets: Assets) -> None:
    now = datetime.now().strftime("%H:%M")
    bg_rect = assets.font_medium.render("88:88", True, DARK_GREY)
    target.blit(bg_rect, CLOCK_XY)
    fg = assets.font_medium.render(now, True, NEON_GREEN)
    target.blit(fg, CLOCK_XY)


def draw_fuel(target: pygame.Surface, assets: Assets, fuel: float) -> None:
    text = f"{int(round(fuel)):2d}"
    render_anchored_text(
        target, assets.font_medium, text, FUEL_XY, NEON_GREEN, ghost_text="88"
    )


def draw_odo(target: pygame.Surface, assets: Assets, odo: int) -> None:
    text = f"{int(odo):05d}"
    render_anchored_text(
        target, assets.font_small, text, ODO_L_XY, NEON_GREEN, ghost_text="88888"
    )


def draw_mfa(target: pygame.Surface, assets: Assets, outside_temp: float) -> None:
    target.blit(assets.mfa, MFABG_XY)
    text = f"{int(round(outside_temp)):2d}"
    render_anchored_text(
        target, assets.font_medium, text, MFA_XY, NEON_GREEN, ghost_text="88"
    )


def draw_indicators(target: pygame.Surface, assets: Assets, state: dict, blink_on: bool) -> None:
    for key, (stem, pos) in INDICATORS.items():
        active = bool(state["indicators"][key])
        # Turn signals blink when active.
        if key in ("leftturn", "rightturn") and active:
            active = blink_on
        if active:
            target.blit(assets.indicator_on[key], pos)
        else:
            off = assets.indicator_off.get(key)
            if off is not None:
                target.blit(off, pos)

    fuel_low = state["fuel"] <= 7
    if fuel_low and (blink_on or state["fuel"] <= 3):
        target.blit(assets.fuelres_on, FUELRES_XY)
    else:
        target.blit(assets.fuelres_off, FUELRES_XY)


def draw_digifiz(target: pygame.Surface, assets: Assets, state: dict, blink_on: bool) -> None:
    target.blit(assets.background, (0, 0))
    draw_rpm(target, assets, state["rpm"])
    draw_aux_gauges(target, assets, state)
    draw_indicators(target, assets, state, blink_on)
    draw_clock(target, assets)
    draw_mfa(target, assets, state["outside_temp"])
    draw_fuel(target, assets, state["fuel"])
    draw_odo(target, assets, state["odo"])
    draw_speed(target, assets, state["speed"])


# ---------------------------------------------------------------------------
# Input handling + per-frame update
# ---------------------------------------------------------------------------

INDICATOR_KEYS = {
    pygame.K_1: "illumination",
    pygame.K_2: "foglight",
    pygame.K_3: "defog",
    pygame.K_4: "highbeam",
    pygame.K_5: "brakewarn",
    pygame.K_6: "oillight",
    pygame.K_7: "alt",
    pygame.K_8: "glow",
}


def handle_keydown(event: pygame.event.Event, state: dict) -> bool:
    """Return False to quit."""
    if event.key in (pygame.K_ESCAPE, pygame.K_x):
        return False
    if event.key == pygame.K_UP:
        state["speed_target"] = clamp(state["speed_target"] + 1, 0, 220)
    elif event.key == pygame.K_DOWN:
        state["speed_target"] = clamp(state["speed_target"] - 1, 0, 220)
    elif event.key == pygame.K_LEFT:
        state["rpm_target"] = clamp(state["rpm_target"] - 100, 0, TACH_MAX_RPM)
        state["rpm_manual"] = True
    elif event.key == pygame.K_RIGHT:
        state["rpm_target"] = clamp(state["rpm_target"] + 100, 0, TACH_MAX_RPM)
        state["rpm_manual"] = True
    elif event.key == pygame.K_f:
        state["fuel"] = clamp(state["fuel"] + 1, 0, 60)
    elif event.key == pygame.K_v:
        state["fuel"] = clamp(state["fuel"] - 1, 0, 60)
    elif event.key == pygame.K_t:
        state["outside_temp"] = clamp(state["outside_temp"] + 1, -40, 99)
    elif event.key == pygame.K_g:
        state["outside_temp"] = clamp(state["outside_temp"] - 1, -40, 99)
    elif event.key == pygame.K_b:
        state["boost_frame"] = clamp(state["boost_frame"] + 1, 0, 19)
    elif event.key == pygame.K_n:
        state["boost_frame"] = clamp(state["boost_frame"] - 1, 0, 19)
    elif event.key == pygame.K_c:
        state["coolant_frame"] = clamp(state["coolant_frame"] + 1, 0, 19)
    elif event.key == pygame.K_o:
        state["oilpressure_frame"] = clamp(state["oilpressure_frame"] + 1, 0, 19)
    elif event.key == pygame.K_e:
        state["egt_frame"] = clamp(state["egt_frame"] + 1, 0, 19)
    elif event.key == pygame.K_LEFTBRACKET:
        ind = state["indicators"]
        ind["leftturn"] = 0 if ind["leftturn"] else 1
    elif event.key == pygame.K_RIGHTBRACKET:
        ind = state["indicators"]
        ind["rightturn"] = 0 if ind["rightturn"] else 1
    elif event.key in INDICATOR_KEYS:
        key = INDICATOR_KEYS[event.key]
        ind = state["indicators"]
        ind[key] = 0 if ind[key] else 1
    return True


def update(state: dict, now_ms: int, dt_ms: int) -> None:
    state["speed"] = ease_toward(state["speed"], state["speed_target"], 0.12)

    # RPM tracks speed loosely with idle floor unless the user has just
    # manually nudged it.
    derived = 800 + state["speed"] * 45
    if state["rpm_manual"]:
        if abs(state["rpm"] - state["rpm_target"]) < 75:
            state["rpm_manual"] = False
    else:
        state["rpm_target"] = derived

    jitter = math.sin(now_ms / 220.0) * 25 + math.sin(now_ms / 73.0) * 8
    state["rpm"] = ease_toward(state["rpm"], state["rpm_target"] + jitter, 0.18)
    state["rpm"] = clamp(state["rpm"], 0, TACH_MAX_RPM)

    # Slow odometer accumulation based on speed.
    state["odo"] = clamp(state["odo"] + state["speed"] * dt_ms / 3600000.0, 0, 999999)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def main() -> None:
    pygame.init()
    pygame.display.set_caption("Digifiz Dashboard")

    win_w = int(NATIVE_W * DEFAULT_SCALE)
    win_h = int(NATIVE_H * DEFAULT_SCALE)
    window = pygame.display.set_mode((win_w, win_h))

    assets = Assets()
    canvas = pygame.Surface((NATIVE_W, NATIVE_H)).convert()

    state = make_state()
    clock = pygame.time.Clock()

    running = True
    while running:
        dt_ms = clock.tick(FPS)
        now_ms = pygame.time.get_ticks()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                running = handle_keydown(event, state) and running

        update(state, now_ms, dt_ms)

        blink_on = (now_ms // 450) % 2 == 0
        draw_digifiz(canvas, assets, state, blink_on)
        pygame.transform.smoothscale(canvas, (win_w, win_h), window)

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()

"""
Retro 80s Digital Dashboard (pygame)

A faithful homage to early-80s digital instrument clusters: curved cyan
speedometer on the left, stacked diagnostic / trip panels in the center,
mirrored tachometer with pink redline on the right. Idles with subtle
sinusoidal drift on every gauge so it feels alive without input.

Run:  python dashboard.py
Quit: ESC or window close.
"""

from __future__ import annotations

import math
import random
import sys

import pygame


# ---------------------------------------------------------------------------
# Window / timing
# ---------------------------------------------------------------------------

WIDTH, HEIGHT = 1024, 768
FPS = 60


# ---------------------------------------------------------------------------
# Palette - tuned against the reference image
# ---------------------------------------------------------------------------


class Colors:
    BG = (0, 0, 0)
    CYAN = (0, 220, 220)
    CYAN_DIM = (0, 50, 60)
    CYAN_DEEP = (0, 110, 130)
    PINK = (255, 30, 170)
    PINK_DIM = (80, 10, 55)
    GREEN_LED = (140, 255, 140)
    GREEN_DIM = (5, 22, 5)
    YELLOW_LED = (255, 220, 60)
    YELLOW_DIM = (28, 22, 3)
    MAGENTA = (255, 50, 170)
    MAGENTA_DIM = (70, 12, 45)
    WHITE = (235, 235, 235)
    LABEL = (210, 220, 230)
    LABEL_DIM = (110, 145, 155)
    PANEL_OUTLINE = (0, 200, 220)
    PANEL_OUTLINE_GLOW = (0, 90, 120)


# ---------------------------------------------------------------------------
# Tiny helpers
# ---------------------------------------------------------------------------


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def angle_to_xy(cx: float, cy: float, r: float, deg: float) -> tuple[float, float]:
    """Standard math angle (0 = +x, 90 = -y because pygame y-down)."""
    rad = math.radians(deg)
    return cx + math.cos(rad) * r, cy - math.sin(rad) * r


# ---------------------------------------------------------------------------
# Seven-segment renderer
# ---------------------------------------------------------------------------

# Segments labelled like a standard 7-seg:
#     aaaa
#    f    b
#    f    b
#     gggg
#    e    c
#    e    c
#     dddd
SEG_TABLE: dict[str, tuple[int, int, int, int, int, int, int]] = {
    "0": (1, 1, 1, 1, 1, 1, 0),
    "1": (0, 1, 1, 0, 0, 0, 0),
    "2": (1, 1, 0, 1, 1, 0, 1),
    "3": (1, 1, 1, 1, 0, 0, 1),
    "4": (0, 1, 1, 0, 0, 1, 1),
    "5": (1, 0, 1, 1, 0, 1, 1),
    "6": (1, 0, 1, 1, 1, 1, 1),
    "7": (1, 1, 1, 0, 0, 0, 0),
    "8": (1, 1, 1, 1, 1, 1, 1),
    "9": (1, 1, 1, 1, 0, 1, 1),
    " ": (0, 0, 0, 0, 0, 0, 0),
    "-": (0, 0, 0, 0, 0, 0, 1),
    "L": (0, 0, 0, 1, 1, 1, 0),
    "E": (1, 0, 0, 1, 1, 1, 1),
    "F": (1, 0, 0, 0, 1, 1, 1),
}


def draw_seg_digit(
    surface: pygame.Surface,
    char: str,
    x: int,
    y: int,
    w: int,
    h: int,
    on_color: tuple[int, int, int],
    off_color: tuple[int, int, int] | None = None,
    show_ghost: bool = True,
) -> None:
    """Draw a single 7-segment digit using slim filled polygons."""
    segs = SEG_TABLE.get(char, SEG_TABLE[" "])
    t = max(2, w // 7)  # segment thickness
    g = max(1, t // 4)  # gap between adjacent segments
    hw = h // 2
    if off_color is None:
        off_color = tuple(c // 8 for c in on_color)

    # horizontal segments: a (top), g (mid), d (bottom)
    def hseg(yc: int) -> list[tuple[int, int]]:
        return [
            (x + t + g, yc - t // 2),
            (x + t + g + (w - 2 * (t + g)), yc - t // 2),
            (x + w - t - g, yc),
            (x + t + g + (w - 2 * (t + g)), yc + t // 2),
            (x + t + g, yc + t // 2),
            (x + g, yc),
        ]

    # vertical segments: b/c (right), f/e (left)
    def vseg(xc: int, y0: int, y1: int) -> list[tuple[int, int]]:
        return [
            (xc, y0 + t + g),
            (xc + t // 2, y0 + g),
            (xc + t, y0 + t + g),
            (xc + t, y1 - t - g),
            (xc + t // 2, y1 - g),
            (xc, y1 - t - g),
        ]

    polys = [
        ("a", hseg(y + t // 2)),
        ("g", hseg(y + hw)),
        ("d", hseg(y + h - t // 2)),
        ("b", vseg(x + w - t, y, y + hw)),
        ("c", vseg(x + w - t, y + hw, y + h)),
        ("f", vseg(x, y, y + hw)),
        ("e", vseg(x, y + hw, y + h)),
    ]

    seg_index = {"a": 0, "b": 1, "c": 2, "d": 3, "e": 4, "f": 5, "g": 6}
    if show_ghost:
        for name, poly in polys:
            pygame.draw.polygon(surface, off_color, poly)
    for name, poly in polys:
        if segs[seg_index[name]]:
            pygame.draw.polygon(surface, on_color, poly)


def draw_seg_string(
    surface: pygame.Surface,
    text: str,
    x: int,
    y: int,
    w: int,
    h: int,
    on_color: tuple[int, int, int],
    off_color: tuple[int, int, int] | None = None,
    spacing: int | None = None,
    show_ghost: bool = True,
) -> int:
    """Draw a string of digits/letters. Returns total pixel width drawn."""
    if spacing is None:
        spacing = max(4, w // 4)
    cx = x
    for ch in text:
        if ch == ".":
            r = max(2, w // 8)
            pygame.draw.rect(surface, on_color, (cx, y + h - r, r, r))
            cx += r + spacing // 2
            continue
        draw_seg_digit(surface, ch, cx, y, w, h, on_color, off_color, show_ghost)
        cx += w + spacing
    return cx - x


# ---------------------------------------------------------------------------
# Arc gauge (used for speedometer + tachometer)
# ---------------------------------------------------------------------------


class ArcGauge:
    """A thick curved gauge.

    Drawn as a stack of small filled annular trapezoids stepping along the arc.
    A "lit" portion is rendered brighter up to the current value. An optional
    redline range (start_pct, end_pct in 0..1) overdraws those steps in pink.
    """

    def __init__(
        self,
        cx: int,
        cy: int,
        inner_r: int,
        outer_r: int,
        start_deg: float,
        end_deg: float,
        steps: int = 90,
        ticks_major: int = 9,
        ticks_minor_per_major: int = 4,
        redline_pct: float | None = None,
        font_major: pygame.font.Font | None = None,
        font_minor: pygame.font.Font | None = None,
        major_label_min: float = 5.0,
        major_label_max: float = 85.0,
        major_label_step: float = 10.0,
        minor_label_min: float = 20.0,
        minor_label_max: float = 120.0,
        minor_label_step: float = 20.0,
        major_label_radius_offset: int = 26,
        minor_label_radius_offset: int = 6,
        unit_major: str = "MPH",
        unit_minor: str = "KM/H",
    ) -> None:
        self.cx, self.cy = cx, cy
        self.inner_r, self.outer_r = inner_r, outer_r
        self.start_deg, self.end_deg = start_deg, end_deg
        self.steps = steps
        self.ticks_major = ticks_major
        self.ticks_minor_per_major = ticks_minor_per_major
        self.redline_pct = redline_pct
        self.font_major = font_major
        self.font_minor = font_minor
        self.major_label_min = major_label_min
        self.major_label_max = major_label_max
        self.major_label_step = major_label_step
        self.minor_label_min = minor_label_min
        self.minor_label_max = minor_label_max
        self.minor_label_step = minor_label_step
        self.major_label_radius_offset = major_label_radius_offset
        self.minor_label_radius_offset = minor_label_radius_offset
        self.unit_major = unit_major
        self.unit_minor = unit_minor

    def _trap(self, a0: float, a1: float, ir: float, or_: float) -> list[tuple[float, float]]:
        return [
            angle_to_xy(self.cx, self.cy, ir, a0),
            angle_to_xy(self.cx, self.cy, or_, a0),
            angle_to_xy(self.cx, self.cy, or_, a1),
            angle_to_xy(self.cx, self.cy, ir, a1),
        ]

    def draw(self, surface: pygame.Surface, value_pct: float) -> None:
        value_pct = clamp(value_pct, 0.0, 1.0)

        # 1) The arc body is a single uniform cyan band (matches the
        #    reference, where the curve itself is decorative).
        for i in range(self.steps):
            t0 = i / self.steps
            t1 = (i + 1) / self.steps
            a0 = lerp(self.start_deg, self.end_deg, t0)
            a1 = lerp(self.start_deg, self.end_deg, t1)
            poly = self._trap(a0, a1, self.inner_r, self.outer_r)
            pygame.draw.polygon(surface, Colors.CYAN, poly)

        # 2) Redline overlay (always in bright pink, no dim variant): the
        #    upper section of the arc.
        if self.redline_pct is not None:
            for i in range(self.steps):
                t0 = i / self.steps
                t1 = (i + 1) / self.steps
                if t1 < self.redline_pct:
                    continue
                a0 = lerp(self.start_deg, self.end_deg, max(t0, self.redline_pct))
                a1 = lerp(self.start_deg, self.end_deg, t1)
                poly = self._trap(a0, a1, self.inner_r, self.outer_r)
                pygame.draw.polygon(surface, Colors.PINK, poly)

        # 3) "Position highlight" - a small triangular marker pointing inward
        #    from just outside the arc at the current value. The marker is
        #    the only animated visual cue carried by the arc itself.
        a_val = lerp(self.start_deg, self.end_deg, value_pct)
        tip_r = self.outer_r + 2
        base_r = self.outer_r + 14
        tip = angle_to_xy(self.cx, self.cy, tip_r, a_val)
        b1 = angle_to_xy(self.cx, self.cy, base_r, a_val - 1.6)
        b2 = angle_to_xy(self.cx, self.cy, base_r, a_val + 1.6)
        pygame.draw.polygon(surface, Colors.WHITE, [tip, b1, b2])

        # 4) Crisp inner / outer arc edges.
        self._stroke_arc(surface, self.inner_r, Colors.CYAN_DEEP, 1)
        self._stroke_arc(surface, self.outer_r, Colors.CYAN_DEEP, 1)

        # 5) Tick marks: major + minor along the inner edge.
        total_majors = self.ticks_major
        total_ticks = (total_majors - 1) * (self.ticks_minor_per_major + 1) + 1
        for i in range(total_ticks):
            t = i / (total_ticks - 1)
            a = lerp(self.start_deg, self.end_deg, t)
            is_major = (i % (self.ticks_minor_per_major + 1)) == 0
            tick_len = 10 if is_major else 4
            color = Colors.WHITE if is_major else Colors.CYAN
            x0, y0 = angle_to_xy(self.cx, self.cy, self.inner_r - 1, a)
            x1, y1 = angle_to_xy(self.cx, self.cy, self.inner_r - 1 - tick_len, a)
            pygame.draw.line(surface, color, (x0, y0), (x1, y1), 2 if is_major else 1)

        # 6) Major numeric labels (MPH style) and minor (KM/H style).
        self._draw_labels(
            surface,
            self.font_major,
            self.major_label_min,
            self.major_label_max,
            self.major_label_step,
            self.inner_r - self.major_label_radius_offset,
            Colors.WHITE,
        )
        self._draw_labels(
            surface,
            self.font_minor,
            self.minor_label_min,
            self.minor_label_max,
            self.minor_label_step,
            self.inner_r - self.major_label_radius_offset - self.minor_label_radius_offset - 14,
            Colors.LABEL_DIM,
        )

    def _stroke_arc(self, surface: pygame.Surface, r: int, color, width: int) -> None:
        steps = self.steps
        prev = angle_to_xy(self.cx, self.cy, r, self.start_deg)
        for i in range(1, steps + 1):
            a = lerp(self.start_deg, self.end_deg, i / steps)
            curr = angle_to_xy(self.cx, self.cy, r, a)
            pygame.draw.line(surface, color, prev, curr, width)
            prev = curr

    def _draw_labels(
        self,
        surface: pygame.Surface,
        font: pygame.font.Font | None,
        v_min: float,
        v_max: float,
        v_step: float,
        radius: float,
        color,
    ) -> None:
        if font is None or radius <= 0:
            return
        v = v_min
        while v <= v_max + 0.01:
            t = (v - v_min) / (v_max - v_min)
            a = lerp(self.start_deg, self.end_deg, t)
            label = font.render(f"{int(v)}", True, color)
            x, y = angle_to_xy(self.cx, self.cy, radius, a)
            rect = label.get_rect(center=(int(x), int(y)))
            surface.blit(label, rect)
            v += v_step


# ---------------------------------------------------------------------------
# Vertical bar gauge (used for fuel)
# ---------------------------------------------------------------------------


class BarGauge:
    def __init__(
        self,
        rect: pygame.Rect,
        segments: int = 10,
        on_color: tuple[int, int, int] = Colors.CYAN,
        off_color: tuple[int, int, int] = Colors.CYAN_DIM,
        gap: int = 2,
    ) -> None:
        self.rect = rect
        self.segments = segments
        self.on_color = on_color
        self.off_color = off_color
        self.gap = gap

    def draw(self, surface: pygame.Surface, value: float) -> None:
        value = clamp(value, 0.0, 1.0)
        seg_h = (self.rect.height - self.gap * (self.segments - 1)) / self.segments
        lit_count = round(value * self.segments)
        for i in range(self.segments):
            y = self.rect.y + (self.segments - 1 - i) * (seg_h + self.gap)
            r = pygame.Rect(self.rect.x, int(y), self.rect.width, int(seg_h))
            color = self.on_color if i < lit_count else self.off_color
            pygame.draw.rect(surface, color, r)


# ---------------------------------------------------------------------------
# Panel (rounded outline with glow + child cells)
# ---------------------------------------------------------------------------


def draw_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    radius: int = 10,
    outline_color=Colors.PANEL_OUTLINE,
    glow_color=Colors.PANEL_OUTLINE_GLOW,
) -> None:
    pygame.draw.rect(surface, glow_color, rect.inflate(4, 4), width=1, border_radius=radius + 2)
    pygame.draw.rect(surface, glow_color, rect.inflate(2, 2), width=1, border_radius=radius + 1)
    pygame.draw.rect(surface, outline_color, rect, width=2, border_radius=radius)


def draw_cell_divider_v(surface: pygame.Surface, x: int, y0: int, y1: int) -> None:
    pygame.draw.line(surface, Colors.PANEL_OUTLINE, (x, y0 + 4), (x, y1 - 4), 1)


def draw_cell_divider_h(surface: pygame.Surface, x0: int, x1: int, y: int) -> None:
    pygame.draw.line(surface, Colors.PANEL_OUTLINE, (x0 + 4, y), (x1 - 4, y), 1)


# ---------------------------------------------------------------------------
# Tiny iconography (drawn procedurally so we have no asset deps)
# ---------------------------------------------------------------------------


def draw_oilcan_icon(surface: pygame.Surface, x: int, y: int, color=Colors.CYAN) -> None:
    # Body: rounded rectangle
    pygame.draw.rect(surface, color, (x, y + 6, 18, 10), border_radius=2)
    # Spout
    pygame.draw.line(surface, color, (x + 18, y + 6), (x + 28, y), 2)
    pygame.draw.line(surface, color, (x + 28, y), (x + 28, y + 4), 2)
    # Drop
    pygame.draw.polygon(surface, color, [(x + 28, y + 5), (x + 25, y + 10), (x + 31, y + 10)])


def draw_thermo_icon(surface: pygame.Surface, x: int, y: int, color=Colors.CYAN) -> None:
    pygame.draw.rect(surface, color, (x + 5, y, 4, 14), border_radius=2)
    pygame.draw.circle(surface, color, (x + 7, y + 16), 5)
    # Fluid line
    pygame.draw.line(surface, Colors.PINK, (x + 7, y + 4), (x + 7, y + 14), 2)


def draw_pump_icon(surface: pygame.Surface, x: int, y: int, color=Colors.CYAN) -> None:
    # Pump body
    pygame.draw.rect(surface, color, (x, y + 4, 14, 22), 2)
    # Base
    pygame.draw.rect(surface, color, (x - 2, y + 26, 18, 3))
    # Hose to top
    pygame.draw.line(surface, color, (x + 14, y + 8), (x + 20, y + 8), 2)
    pygame.draw.line(surface, color, (x + 20, y + 8), (x + 20, y + 2), 2)
    # Window
    pygame.draw.rect(surface, color, (x + 2, y + 6, 10, 6), 1)


def draw_indicator_bar(
    surface: pygame.Surface,
    x: int,
    y: int,
    w: int,
    h: int,
    value: float,
    color=Colors.MAGENTA,
    bg=Colors.MAGENTA_DIM,
    segments: int = 6,
) -> None:
    """Tiny segmented horizontal indicator (oil press / coolant temp)."""
    value = clamp(value, 0.0, 1.0)
    seg_w = (w - (segments - 1) * 2) / segments
    lit = round(value * segments)
    for i in range(segments):
        rx = int(x + i * (seg_w + 2))
        c = color if i < lit else bg
        pygame.draw.rect(surface, c, (rx, y, int(seg_w), h))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


class Dashboard:
    def __init__(self, size: tuple[int, int]) -> None:
        self.w, self.h = size

        # Fonts (small UI labels). pygame falls back gracefully if a face
        # name is missing.
        self.font_label = pygame.font.SysFont("arial", 13, bold=True)
        self.font_label_sm = pygame.font.SysFont("arial", 11, bold=True)
        self.font_label_xs = pygame.font.SysFont("arial", 10, bold=True)
        self.font_arc_major = pygame.font.SysFont("arial", 18, bold=True)
        self.font_arc_minor = pygame.font.SysFont("arial", 12, bold=True)
        self.font_unit_big = pygame.font.SysFont("arial", 18, bold=True)

        # Animated state
        self.t = 0.0
        self.speed_mph = 32.0
        self.rpm_x100 = 18.0
        self.fuel_pct = 0.92
        self.volts = 13.8
        self.oil_psi = 42.0
        self.oil_temp = 0.55
        self.coolant = 0.0  # warms over time
        self.instant_mpg = 12.8
        self.average_mpg = 14.2
        self.trip_miles = 16.2
        self.range_miles = 312
        self.rev_pulse_t = 0.0
        self.blink = True
        self._blink_accum = 0.0

        # ------------------------------------------------------------------
        # Geometry
        # ------------------------------------------------------------------
        # Each gauge is a tall C-shape arc bulging OUT toward the screen edge
        # with its numeric labels on the inside (toward the center stack).
        # The speedometer's circle is centered on the RIGHT side of the
        # speedo panel area, with the arc occupying the LEFT half of the
        # circle; the tachometer mirrors this on the right side of the screen.
        speed_cx, speed_cy = 320, 360
        speed_inner, speed_outer = 285, 320
        # Angle range: 245 (down-and-left => 5 MPH at bottom) sweeping CCW
        # through 180 (left = ~45 MPH at the leftmost extent of the arc) up to
        # 115 (up-and-left => 85 MPH at the top).
        self.speedo = ArcGauge(
            cx=speed_cx,
            cy=speed_cy,
            inner_r=speed_inner,
            outer_r=speed_outer,
            start_deg=245,
            end_deg=115,
            steps=120,
            ticks_major=9,
            ticks_minor_per_major=4,
            font_major=self.font_arc_major,
            font_minor=self.font_arc_minor,
            major_label_min=5,
            major_label_max=85,
            major_label_step=10,
            minor_label_min=20,
            minor_label_max=120,
            minor_label_step=20,
            major_label_radius_offset=22,
            minor_label_radius_offset=4,
            unit_major="MPH",
            unit_minor="KM/H",
        )

        # Tachometer: mirror to the right.
        tach_cx, tach_cy = self.w - speed_cx, speed_cy
        self.tacho = ArcGauge(
            cx=tach_cx,
            cy=tach_cy,
            inner_r=speed_inner,
            outer_r=speed_outer,
            # Mirrored arc on the RIGHT half of the right circle.
            # 295 (down-and-right => 10 RPM at bottom) sweeping CW through 0
            # (right = midpoint) up to 65 (up-and-right => 60 RPM at top).
            start_deg=-65,
            end_deg=65,
            steps=120,
            ticks_major=6,
            ticks_minor_per_major=4,
            redline_pct=0.83,
            font_major=self.font_arc_major,
            font_minor=None,
            major_label_min=10,
            major_label_max=60,
            major_label_step=10,
            minor_label_min=0,
            minor_label_max=0,
            minor_label_step=1,
            major_label_radius_offset=22,
            minor_label_radius_offset=4,
            unit_major="RPM/100",
            unit_minor="",
        )

        # Center stack rectangles
        center_w, center_h_top, center_h_bot = 440, 130, 100
        center_gap = 16
        cx = self.w // 2 - center_w // 2
        top_y = 90
        self.center_top_rect = pygame.Rect(cx, top_y, center_w, center_h_top)
        self.center_bot_rect = pygame.Rect(
            cx, top_y + center_h_top + center_gap, center_w, center_h_bot
        )

        # Fuel bar inside top center panel
        cell_w = center_w // 3
        fuel_cell_x = cx + cell_w
        self.fuel_bar = BarGauge(
            rect=pygame.Rect(fuel_cell_x + cell_w // 2 - 12, top_y + 18, 24, 100),
            segments=14,
            on_color=Colors.CYAN,
            off_color=Colors.CYAN_DIM,
            gap=2,
        )

        # LCD readouts.
        # Speedometer 3-digit MPH: bottom of speedo panel, sitting just
        # inside the arc's lower terminus (near "5 MPH").
        self.speedo_digit_origin = (140, self.h - 180)
        self.speedo_digit_size = (44, 66)
        # Tachometer 2-digit RPM: bottom of tach panel, mirror.
        self.tacho_digit_origin = (self.w - 230, self.h - 180)
        self.tacho_digit_size = (40, 60)

    # ---------------------------------------------------------------- update
    def update(self, dt: float) -> None:
        self.t += dt
        t = self.t

        # speed: 32 +/- a few mph, plus low-amp noise
        self.speed_mph = clamp(
            32 + 4 * math.sin(t * 0.4) + random.uniform(-0.3, 0.3), 0, 85
        )

        # rpm: drifts around 18 with periodic "rev pulses" toward 45
        self.rev_pulse_t -= dt
        if self.rev_pulse_t < -10:  # wait period after pulse
            self.rev_pulse_t = 1.0
        rev_amount = 0.0
        if self.rev_pulse_t > 0:
            # Smooth bell over the pulse window (1s)
            rev_amount = 27 * math.sin(math.pi * (1 - self.rev_pulse_t))
        self.rpm_x100 = clamp(
            18 + 2 * math.sin(t * 0.7) + rev_amount + random.uniform(-0.3, 0.3), 0, 60
        )

        # fuel slowly drains
        self.fuel_pct = clamp(self.fuel_pct - 0.0008 * dt, 0.0, 1.0)

        # voltage flicker
        self.volts = 13.8 + 0.12 * math.sin(t * 2.1) + random.uniform(-0.02, 0.02)

        # oil press wobble
        self.oil_psi = 42 + 1.5 * math.sin(t * 0.3)

        # coolant: cold for 20s then ramps to ~0.45
        if t < 20:
            self.coolant = 0.0
        else:
            self.coolant = clamp((t - 20) / 60, 0.0, 0.55)

        # mpg
        self.instant_mpg = clamp(12.8 + 4 * math.sin(t * 1.3), 0, 99)
        self.average_mpg += (self.instant_mpg - self.average_mpg) * 0.02 * dt

        # trip / range
        self.trip_miles += (self.speed_mph / 3600.0) * dt
        # rough range estimate: gallons left * mpg, assume 18gal tank
        gallons = 18.0 * self.fuel_pct
        self.range_miles = max(0, gallons * self.average_mpg)

        # blink at 1Hz
        self._blink_accum += dt
        if self._blink_accum >= 0.5:
            self.blink = not self.blink
            self._blink_accum = 0.0

    # ------------------------------------------------------------------ draw
    def draw(self, surface: pygame.Surface) -> None:
        self._draw_speedo(surface)
        self._draw_tacho(surface)
        self._draw_center_top(surface)
        self._draw_center_bot(surface)
        self._draw_vignette(surface)

    # ---- speedometer ---------------------------------------------------
    def _draw_speedo(self, surface: pygame.Surface) -> None:
        value = self.speed_mph / 85.0
        self.speedo.draw(surface, value)

        # 3-digit LCD readout
        ox, oy = self.speedo_digit_origin
        dw, dh = self.speedo_digit_size
        s = f"{int(self.speed_mph):3d}"
        spacing = 8
        # Box around digits
        box = pygame.Rect(
            ox - 6, oy - 6, (dw + spacing) * 3 - spacing + 12, dh + 12
        )
        pygame.draw.rect(surface, Colors.GREEN_DIM, box, border_radius=4)
        pygame.draw.rect(surface, Colors.GREEN_LED, box, width=1, border_radius=4)
        for i, ch in enumerate(s):
            draw_seg_digit(
                surface,
                ch if ch != " " else " ",
                ox + i * (dw + spacing),
                oy,
                dw,
                dh,
                Colors.GREEN_LED,
                Colors.GREEN_DIM,
                show_ghost=True,
            )

        # Unit labels
        kmh = self.font_unit_big.render("KM/H", True, Colors.GREEN_LED)
        mph = self.font_unit_big.render("MPH", True, Colors.GREEN_LED)
        surface.blit(kmh, (ox + 30, oy - 30))
        surface.blit(mph, (ox + (dw + spacing) * 3 - 50, oy + dh + 8))

    # ---- tachometer ----------------------------------------------------
    def _draw_tacho(self, surface: pygame.Surface) -> None:
        value = self.rpm_x100 / 60.0
        self.tacho.draw(surface, value)

        # 2-digit LCD (yellow)
        ox, oy = self.tacho_digit_origin
        dw, dh = self.tacho_digit_size
        s = f"{int(self.rpm_x100):2d}"
        spacing = 8
        box = pygame.Rect(
            ox - 6, oy - 6, (dw + spacing) * 2 - spacing + 12, dh + 12
        )
        pygame.draw.rect(surface, Colors.YELLOW_DIM, box, border_radius=4)
        pygame.draw.rect(surface, Colors.YELLOW_LED, box, width=1, border_radius=4)
        for i, ch in enumerate(s):
            draw_seg_digit(
                surface,
                ch if ch != " " else " ",
                ox + i * (dw + spacing),
                oy,
                dw,
                dh,
                Colors.YELLOW_LED,
                Colors.YELLOW_DIM,
                show_ghost=True,
            )

        rpm = self.font_unit_big.render("RPM/100", True, Colors.YELLOW_LED)
        surface.blit(rpm, (ox, oy + dh + 8))

    # ---- center top panel: oil / fuel / coolant / volts ---------------
    def _draw_center_top(self, surface: pygame.Surface) -> None:
        r = self.center_top_rect
        draw_panel(surface, r)

        cell_w = r.width // 3
        x_left = r.x
        x_mid = r.x + cell_w
        x_right = r.x + cell_w * 2
        draw_cell_divider_v(surface, x_mid, r.y, r.bottom)
        draw_cell_divider_v(surface, x_right, r.y, r.bottom)

        # ---- Left cell: oil press / oil temp -------------------------
        # Top row labels
        psi = self.font_label_xs.render("PSI", True, Colors.CYAN)
        kpa = self.font_label_xs.render("KPa", True, Colors.LABEL_DIM)
        surface.blit(psi, (x_left + 8, r.y + 6))
        surface.blit(kpa, (x_left + 8, r.y + 18))

        # Indicator bar (magenta) showing oil pressure normalized
        draw_indicator_bar(
            surface,
            x_left + 38,
            r.y + 10,
            64,
            10,
            self.oil_psi / 80.0,
            color=Colors.MAGENTA,
            bg=Colors.MAGENTA_DIM,
            segments=8,
        )

        # Right side of top row: a small "0" digit (oil temp display)
        draw_seg_digit(
            surface,
            "0",
            x_left + cell_w - 18,
            r.y + 8,
            11,
            16,
            Colors.YELLOW_LED,
            Colors.YELLOW_DIM,
            show_ghost=True,
        )

        # Bottom row labels + oil can icon
        draw_oilcan_icon(surface, x_left + 6, r.y + r.height // 2 + 8, Colors.CYAN)
        oilp = self.font_label_sm.render("OIL PRESS", True, Colors.LABEL)
        oilt = self.font_label_sm.render("OIL TEMP", True, Colors.LABEL_DIM)
        surface.blit(oilp, (x_left + 40, r.y + r.height // 2 + 8))
        surface.blit(oilt, (x_left + 40, r.y + r.height // 2 + 22))

        # ---- Middle cell: fuel bar ----------------------------------
        bar_x = self.fuel_bar.rect.x
        bar_top = self.fuel_bar.rect.y
        bar_bot = self.fuel_bar.rect.bottom
        # F / E labels alongside the bar (right side)
        f = self.font_label_sm.render("F", True, Colors.LABEL)
        e = self.font_label_sm.render("E", True, Colors.LABEL)
        surface.blit(f, (bar_x + self.fuel_bar.rect.width + 6, bar_top - 2))
        surface.blit(e, (bar_x + self.fuel_bar.rect.width + 6, bar_bot - 12))
        # Tick marks on the LEFT side of the bar
        for i in range(5):
            ty = bar_top + i * (self.fuel_bar.rect.height) / 4
            pygame.draw.line(
                surface,
                Colors.LABEL_DIM,
                (bar_x - 8, ty),
                (bar_x - 2, ty),
                1,
            )
        self.fuel_bar.draw(surface, self.fuel_pct)

        # ---- Right cell: coolant temp / volts -----------------------
        # Top row: coolant indicator + volts numeric on the right
        draw_indicator_bar(
            surface,
            x_right + 8,
            r.y + 10,
            70,
            10,
            self.coolant,
            color=Colors.MAGENTA,
            bg=Colors.MAGENTA_DIM,
            segments=8,
        )
        # Volts numeric (top-right corner) + F.E.V hint label.
        volts_text = f"{self.volts:.1f}"
        vw, vh = 11, 16
        right_edge = x_right + cell_w - 8
        # Compute total width
        total_w = sum((5 if c == "." else (vw + 2)) for c in volts_text) - 2
        cx2 = right_edge - total_w
        for ch in volts_text:
            if ch == ".":
                pygame.draw.rect(
                    surface, Colors.YELLOW_LED, (cx2, r.y + 10 + vh - 3, 3, 3)
                )
                cx2 += 5
            else:
                draw_seg_digit(
                    surface, ch, cx2, r.y + 10, vw, vh,
                    Colors.YELLOW_LED, Colors.YELLOW_DIM, show_ghost=True,
                )
                cx2 += vw + 2
        fev = self.font_label_xs.render("F.E.V", True, Colors.LABEL_DIM)
        surface.blit(fev, (right_edge - fev.get_width(), r.y + 28))

        # When cold, show "L L" indicator below the bar (matches reference)
        if self.coolant < 0.05:
            ll_color = Colors.YELLOW_LED if self.blink else Colors.YELLOW_DIM
            ll_w, ll_h = 9, 14
            ll_y = r.y + 32
            for i, ch in enumerate("L  L"):
                if ch == " ":
                    continue
                draw_seg_digit(
                    surface, ch, x_right + 8 + i * (ll_w + 4), ll_y,
                    ll_w, ll_h, ll_color, Colors.YELLOW_DIM, show_ghost=True,
                )

        # Bottom row: thermometer icon + COOLANT TEMP / VOLTS labels
        draw_thermo_icon(surface, x_right + 6, r.y + r.height // 2 + 8, Colors.CYAN)
        ct = self.font_label_sm.render("COOLANT TEMP", True, Colors.LABEL)
        vt = self.font_label_sm.render("VOLTS", True, Colors.LABEL_DIM)
        surface.blit(ct, (x_right + 26, r.y + r.height // 2 + 8))
        surface.blit(vt, (x_right + 26, r.y + r.height // 2 + 22))

    # ---- center bottom panel: trip / fuel-only / mpg -----------------
    def _draw_center_bot(self, surface: pygame.Surface) -> None:
        r = self.center_bot_rect
        draw_panel(surface, r)

        cell_w = r.width // 3
        x_left = r.x
        x_mid = r.x + cell_w
        x_right = r.x + cell_w * 2
        draw_cell_divider_v(surface, x_mid, r.y, r.bottom)
        draw_cell_divider_v(surface, x_right, r.y, r.bottom)

        # ---- Left: MILES KM ON RESERVE TRIP / 16.2 ------------------
        miles_lbl = self.font_label_xs.render("MILES", True, Colors.LABEL)
        km_lbl = self.font_label_xs.render("KM", True, Colors.LABEL_DIM)
        on_lbl = self.font_label_xs.render("ON", True, Colors.LABEL_DIM)
        rng_lbl = self.font_label_xs.render("RANGE", True, Colors.LABEL)
        res_lbl = self.font_label_xs.render("RESERVE", True, Colors.LABEL_DIM)
        trip_lbl = self.font_label_xs.render("TRIP", True, Colors.LABEL)

        surface.blit(miles_lbl, (x_left + 6, r.y + 4))
        surface.blit(km_lbl, (x_left + 6, r.y + 16))
        surface.blit(on_lbl, (x_left + 44, r.y + 4))
        surface.blit(rng_lbl, (x_left + 44, r.y + 16))
        surface.blit(res_lbl, (x_left + 80, r.y + 4))
        surface.blit(trip_lbl, (x_left + 80, r.y + 16))

        # 16.2 readout (green LCD)
        text = f"{self.trip_miles:.1f}"
        dw, dh = 22, 32
        cx = x_left + 6
        cy = r.y + 36
        for ch in text:
            if ch == ".":
                pygame.draw.rect(
                    surface, Colors.GREEN_LED, (cx, cy + dh - 5, 5, 5)
                )
                cx += 8
            else:
                draw_seg_digit(
                    surface, ch, cx, cy, dw, dh,
                    Colors.GREEN_LED, Colors.GREEN_DIM, show_ghost=True,
                )
                cx += dw + 4

        # ---- Middle: UNLEADED FUEL ONLY ----------------------------
        u_lbl = self.font_label_sm.render("UNLEADED", True, Colors.LABEL)
        f_lbl = self.font_label_sm.render("FUEL", True, Colors.LABEL)
        o_lbl = self.font_label_sm.render("ONLY", True, Colors.LABEL)
        surface.blit(u_lbl, (x_mid + 8, r.y + 6))
        surface.blit(f_lbl, (x_mid + 8, r.y + 22))
        surface.blit(o_lbl, (x_mid + 8, r.y + 38))
        draw_pump_icon(surface, x_mid + cell_w - 36, r.y + r.height // 2 - 14, Colors.CYAN)

        # ---- Right: INSTANT AVERAGE MPG / 12.8 ---------------------
        i_lbl = self.font_label_xs.render("INSTANT", True, Colors.LABEL)
        a_lbl = self.font_label_xs.render("AVERAGE", True, Colors.LABEL_DIM)
        mpg_lbl = self.font_label_xs.render("MPG", True, Colors.LABEL)
        l_per_lbl = self.font_label_xs.render("L/100 KM", True, Colors.LABEL_DIM)
        surface.blit(i_lbl, (x_right + 6, r.y + 4))
        surface.blit(a_lbl, (x_right + 6, r.y + 16))
        surface.blit(mpg_lbl, (x_right + cell_w - 38, r.y + 4))
        surface.blit(l_per_lbl, (x_right + cell_w - 50, r.y + 16))

        text = f"{self.instant_mpg:.1f}"
        dw, dh = 22, 32
        cx = x_right + 6
        cy = r.y + 36
        for ch in text:
            if ch == ".":
                pygame.draw.rect(
                    surface, Colors.GREEN_LED, (cx, cy + dh - 5, 5, 5)
                )
                cx += 8
            else:
                draw_seg_digit(
                    surface, ch, cx, cy, dw, dh,
                    Colors.GREEN_LED, Colors.GREEN_DIM, show_ghost=True,
                )
                cx += dw + 4

    # ---- vignette ------------------------------------------------------
    def _draw_vignette(self, surface: pygame.Surface) -> None:
        """Soft edge darkening + faint horizontal scanlines for CRT vibe."""
        vignette = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        # Edge darkening: nested rectangle outlines fading inward.
        for i in range(8):
            alpha = max(0, 70 - i * 9)
            pygame.draw.rect(
                vignette,
                (0, 0, 0, alpha),
                pygame.Rect(i, i, self.w - 2 * i, self.h - 2 * i),
                width=1,
            )
        # Subtle scanlines.
        for y in range(0, self.h, 3):
            pygame.draw.line(vignette, (0, 0, 0, 22), (0, y), (self.w, y))
        surface.blit(vignette, (0, 0))


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def main() -> None:
    pygame.init()
    pygame.display.set_caption("Retro Digital Dashboard")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()

    dash = Dashboard(screen.get_size())

    while True:
        dt = clock.tick(FPS) / 1000.0
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                pygame.quit()
                sys.exit(0)

        dash.update(dt)
        screen.fill(Colors.BG)
        dash.draw(screen)
        pygame.display.flip()


if __name__ == "__main__":
    main()

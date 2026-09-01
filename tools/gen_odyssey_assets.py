"""
Asset generator for the 2006 Honda Odyssey digital cluster.

Draws every asset procedurally at SUPERSAMPLE resolution and downsamples for
antialiasing, then writes them into ``assets/odyssey/``:

    background.png              static "stencil" - bezels, silkscreen labels,
                                scales, ghost segments, unlit lamp glyphs
    tach/tach_NN.png            71 bar-graph frames (0..7000 rpm, 100 rpm step)
    bars/<name>_NN.png          21 frames each for fuel / temp / oil / volt
    lamps/<key>.png             lit indicator glyphs
    gear/gear_<n>.png           lit P-R-N-D-3-2-1 cells

Run:  python tools/gen_odyssey_assets.py
"""

from __future__ import annotations

import math
import os
import sys

import pygame

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from odyssey_layout import (  # noqa: E402
    ASSET_ROOT,
    BAR_FRAME_COUNT,
    BAR_SEGMENTS,
    C,
    CANVAS_H,
    CANVAS_W,
    FONT_DSEG7,
    FONT_DSEG14,
    GEARS,
    LABEL_FONT_NAME,
    LAMPS,
    SUPERSAMPLE as SS,
    TACH_FRAME_COUNT,
    TACH_REDLINE_RPM,
    TACH_RPM_STEP,
    gear_rect,
    lamp_rect,
)
import odyssey_layout as L  # noqa: E402


# ---------------------------------------------------------------------------
# Painter - a supersampled surface addressed in design-space coordinates
# ---------------------------------------------------------------------------


class Painter:
    """Wraps a surface drawn at SS scale but addressed in 1x design units."""

    _font_cache: dict[tuple[str, int, bool], pygame.font.Font] = {}

    def __init__(self, w: int, h: int, origin: tuple[int, int] = (0, 0)) -> None:
        self.w, self.h = w, h
        self.ox, self.oy = origin
        self.surf = pygame.Surface((w * SS, h * SS), pygame.SRCALPHA)

    # -- coordinate mapping -------------------------------------------------

    def _p(self, pt) -> tuple[int, int]:
        return (int(round((pt[0] - self.ox) * SS)), int(round((pt[1] - self.oy) * SS)))

    def _r(self, rect) -> pygame.Rect:
        x, y, w, h = rect
        return pygame.Rect(
            int(round((x - self.ox) * SS)),
            int(round((y - self.oy) * SS)),
            int(round(w * SS)),
            int(round(h * SS)),
        )

    # -- primitives ---------------------------------------------------------

    def rect(self, rect, color, width: float = 0, radius: float = 0) -> None:
        pygame.draw.rect(
            self.surf,
            color,
            self._r(rect),
            int(round(width * SS)) if width else 0,
            border_radius=int(round(radius * SS)),
        )

    def line(self, p1, p2, color, width: float = 1) -> None:
        pygame.draw.line(self.surf, color, self._p(p1), self._p(p2), max(1, int(round(width * SS))))

    def lines(self, points, color, width: float = 1, closed: bool = False) -> None:
        pygame.draw.lines(
            self.surf, color, closed, [self._p(p) for p in points], max(1, int(round(width * SS)))
        )

    def polygon(self, points, color, width: float = 0) -> None:
        pygame.draw.polygon(
            self.surf, color, [self._p(p) for p in points], int(round(width * SS)) if width else 0
        )

    def circle(self, center, r: float, color, width: float = 0) -> None:
        pygame.draw.circle(
            self.surf,
            color,
            self._p(center),
            int(round(r * SS)),
            int(round(width * SS)) if width else 0,
        )

    def arc(self, rect, start_deg: float, end_deg: float, color, width: float = 1) -> None:
        pygame.draw.arc(
            self.surf,
            color,
            self._r(rect),
            math.radians(start_deg),
            math.radians(end_deg),
            max(1, int(round(width * SS))),
        )

    # -- text ---------------------------------------------------------------

    @classmethod
    def _font(cls, kind: str, size: int, bold: bool) -> pygame.font.Font:
        key = (kind, size, bold)
        if key not in cls._font_cache:
            px = max(1, int(round(size * SS)))
            if kind == "seg7":
                cls._font_cache[key] = pygame.font.Font(FONT_DSEG7, px)
            elif kind == "seg14":
                cls._font_cache[key] = pygame.font.Font(FONT_DSEG14, px)
            else:
                cls._font_cache[key] = pygame.font.SysFont(LABEL_FONT_NAME, px, bold=bold)
        return cls._font_cache[key]

    def text(
        self,
        value: str,
        pos,
        size: int,
        color,
        anchor: str = "topleft",
        kind: str = "label",
        bold: bool = False,
        spacing: float = 0.0,
    ) -> pygame.Rect:
        font = self._font(kind, size, bold)
        if spacing:
            rendered = self._render_tracked(font, value, color, spacing)
        else:
            rendered = font.render(value, True, color)
        rect = rendered.get_rect()
        setattr(rect, anchor, self._p(pos))
        self.surf.blit(rendered, rect)
        return rect

    def _render_tracked(
        self, font: pygame.font.Font, value: str, color, spacing: float
    ) -> pygame.Surface:
        """Render with extra letter spacing (used for wide silkscreen labels)."""
        gap = int(round(spacing * SS))
        glyphs = [font.render(ch, True, color) for ch in value]
        total = sum(g.get_width() for g in glyphs) + gap * max(0, len(glyphs) - 1)
        height = max((g.get_height() for g in glyphs), default=1)
        out = pygame.Surface((max(1, total), height), pygame.SRCALPHA)
        x = 0
        for g in glyphs:
            out.blit(g, (x, 0))
            x += g.get_width() + gap
        return out

    # -- output -------------------------------------------------------------

    def result(self) -> pygame.Surface:
        return pygame.transform.smoothscale(self.surf, (self.w, self.h))

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        pygame.image.save(self.result(), path)


# ---------------------------------------------------------------------------
# Tach bar-graph geometry
# ---------------------------------------------------------------------------

TACH_BARS = TACH_FRAME_COUNT - 1          # 70 bars, one per 100 rpm


def tach_envelope(t: float) -> float:
    """Normalised bar height at position t (0..1) across the tach.

    An S-curve that rises steeply through the mid range then droops slightly
    at the top, reproducing the printed power-curve envelope on the 300ZX.
    """
    s = 0.09 + 0.91 / (1.0 + math.exp(-9.2 * (t - 0.46)))
    droop = 1.0 - 0.13 * max(0.0, (t - 0.74) / 0.26)
    return s * droop


def tach_bar_geom(i: int) -> tuple[float, float, float, float]:
    x0, y0, w, h = L.TACH_BAR_RECT
    pitch = w / TACH_BARS
    bw = pitch * 0.66
    bx = x0 + i * pitch + (pitch - bw) / 2.0
    bh = h * tach_envelope((i + 0.5) / TACH_BARS)
    return bx, y0 + h - bh, bw, bh


def tach_bar_is_redline(i: int) -> bool:
    return (i + 1) * TACH_RPM_STEP > TACH_REDLINE_RPM


def tach_x_for_rpm(rpm: float) -> float:
    x0, _y0, w, _h = L.TACH_BAR_RECT
    return x0 + w * (rpm / L.TACH_MAX_RPM)


# ---------------------------------------------------------------------------
# Vertical bar gauge geometry
# ---------------------------------------------------------------------------


def bar_segment_rects(rect) -> list[tuple[float, float, float, float]]:
    """Bottom-up list of segment rects for a vertical bar gauge."""
    x, y, w, h = rect
    gap = 2.0
    seg_h = (h - gap * (BAR_SEGMENTS - 1)) / BAR_SEGMENTS
    out = []
    for i in range(BAR_SEGMENTS):
        sy = y + h - (i + 1) * seg_h - i * gap
        out.append((x, sy, w, seg_h))
    return out


# Dim red zone markers printed on the background (bottom-up segment index).
# These show the driver where the danger ends of each scale are.
BAR_WARN_ZONES: dict[str, set[int]] = {
    "fuel": {0, 1, 2},
    "temp": {16, 17, 18, 19},
    "oil": {0, 1, 2},
    "volt": {0, 1, 2, 17, 18, 19},
}

# How many segments count as "in the low danger zone" for bottom-referenced
# gauges (fuel, oil, low voltage).
LOW_ZONE_LIMIT = 3


def lit_segment_color(key: str, i: int, lit_count: int):
    """Colour of lit segment `i` when `lit_count` segments are illuminated.

    Bottom-referenced gauges (fuel, oil, undervoltage) are only alarming when
    the *level* is low, so their whole column turns red rather than lighting
    the bottom zone red on every frame. Top-referenced zones (overheat,
    overcharge) go red per-segment as the level reaches them.
    """
    if key in ("fuel", "oil"):
        return C.RED if lit_count <= LOW_ZONE_LIMIT else C.CYAN
    if key == "temp":
        return C.RED if i >= 16 else C.CYAN
    if key == "volt":
        if lit_count <= LOW_ZONE_LIMIT:
            return C.RED
        return C.RED if i >= 17 else C.CYAN
    return C.CYAN

BAR_RECTS: dict[str, tuple[int, int, int, int]] = {
    "fuel": L.FUEL_BAR_RECT,
    "temp": (L.TRIPLE_BAR_X[0], L.TRIPLE_BAR_Y, L.TRIPLE_BAR_W, L.TRIPLE_BAR_H),
    "oil": (L.TRIPLE_BAR_X[1], L.TRIPLE_BAR_Y, L.TRIPLE_BAR_W, L.TRIPLE_BAR_H),
    "volt": (L.TRIPLE_BAR_X[2], L.TRIPLE_BAR_Y, L.TRIPLE_BAR_W, L.TRIPLE_BAR_H),
}


# ---------------------------------------------------------------------------
# Indicator glyphs
# ---------------------------------------------------------------------------


def _van_body(p: Painter, x, y, w, h, col, width=1.6):
    """Minivan silhouette outline used by the door / tailgate lamps."""
    pts = [
        (x, y + h * 0.78),
        (x, y + h * 0.42),
        (x + w * 0.24, y + h * 0.10),
        (x + w * 0.72, y + h * 0.10),
        (x + w, y + h * 0.44),
        (x + w, y + h * 0.78),
    ]
    p.lines(pts, col, width)
    p.line((x, y + h * 0.78), (x + w, y + h * 0.78), col, width)


def draw_glyph(p: Painter, kind: str, rect, col) -> None:
    """Draw indicator glyph `kind` inside `rect` in colour `col`."""
    rx, ry, rw, rh = rect
    m = 4.0
    x, y = rx + m, ry + m
    w, h = rw - 2 * m, rh - 2 * m
    cx, cy = x + w / 2.0, y + h / 2.0
    lw = 1.7

    if kind == "thermo":
        stem_w = max(3.0, w * 0.14)
        p.rect((cx - stem_w / 2, y + h * 0.04, stem_w, h * 0.52), col, lw, radius=stem_w / 2)
        p.circle((cx, y + h * 0.70), h * 0.16, col, lw)
        for i in range(3):
            ly = y + h * (0.16 + i * 0.14)
            p.line((cx + stem_w * 0.9, ly), (cx + stem_w * 2.0, ly), col, lw)
        wave = [
            (cx - w * 0.38 + i * w * 0.13, y + h * 0.94 + (h * 0.05 if i % 2 else -h * 0.05))
            for i in range(7)
        ]
        p.lines(wave, col, lw)

    elif kind == "highbeam":
        p.arc((x + w * 0.10, y, w * 0.62, h), -90, 90, col, 2.0)
        p.line((x + w * 0.10, y + 1), (x + w * 0.10, y + h - 1), col, 2.0)
        for i in range(4):
            ly = y + h * (0.16 + i * 0.22)
            p.line((x + w * 0.66, ly), (x + w, ly), col, lw)

    elif kind == "engine":
        p.rect((x + w * 0.20, y + h * 0.30, w * 0.52, h * 0.44), col, lw, radius=2)
        p.rect((x + w * 0.30, y + h * 0.16, w * 0.16, h * 0.16), col, lw)
        p.line((x + w * 0.72, y + h * 0.42), (x + w * 0.88, y + h * 0.42), col, lw)
        p.line((x + w * 0.88, y + h * 0.42), (x + w * 0.88, y + h * 0.62), col, lw)
        p.line((x + w * 0.10, y + h * 0.44), (x + w * 0.20, y + h * 0.44), col, lw)
        p.line((x + w * 0.10, y + h * 0.60), (x + w * 0.20, y + h * 0.60), col, lw)
        p.text("!", (cx - w * 0.02, cy + h * 0.02), int(rh * 0.34), col, "center", bold=True)

    elif kind == "oilcan":
        p.polygon(
            [
                (x + w * 0.16, y + h * 0.72),
                (x + w * 0.16, y + h * 0.44),
                (x + w * 0.34, y + h * 0.34),
                (x + w * 0.64, y + h * 0.34),
                (x + w * 0.64, y + h * 0.72),
            ],
            col,
            lw,
        )
        p.line((x + w * 0.64, y + h * 0.44), (x + w * 0.94, y + h * 0.24), col, lw)
        p.line((x + w * 0.16, y + h * 0.72), (x + w * 0.64, y + h * 0.72), col, lw)
        p.circle((x + w * 0.40, y + h * 0.88), h * 0.07, col)

    elif kind == "battery":
        p.rect((x + w * 0.14, y + h * 0.32, w * 0.72, h * 0.44), col, lw, radius=1.5)
        p.rect((x + w * 0.26, y + h * 0.22, w * 0.12, h * 0.10), col)
        p.rect((x + w * 0.62, y + h * 0.22, w * 0.12, h * 0.10), col)
        p.line((x + w * 0.24, y + h * 0.52), (x + w * 0.40, y + h * 0.52), col, lw)
        p.line((x + w * 0.32, y + h * 0.44), (x + w * 0.32, y + h * 0.60), col, lw)
        p.line((x + w * 0.60, y + h * 0.52), (x + w * 0.76, y + h * 0.52), col, lw)

    elif kind == "brake":
        r = min(w, h) * 0.30
        p.circle((cx, cy), r, col, lw)
        p.line((cx, cy - r * 0.52), (cx, cy + r * 0.16), col, lw)
        p.circle((cx, cy + r * 0.46), lw * 0.8, col)
        p.arc((cx - r * 1.9, cy - r * 1.25, r * 1.0, r * 2.5), 55, 305, col, lw)
        p.arc((cx + r * 0.9, cy - r * 1.25, r * 1.0, r * 2.5), -125, 125, col, lw)

    elif kind == "abs":
        r = min(w, h) * 0.44
        p.circle((cx, cy), r, col, lw)
        p.text("ABS", (cx, cy), int(rh * 0.30), col, "center", bold=True)
        for sx in (-1, 1):
            p.line((cx + sx * r * 1.05, cy - r * 0.5), (cx + sx * r * 1.45, cy - r * 0.5), col, lw)
            p.line((cx + sx * r * 1.05, cy + r * 0.5), (cx + sx * r * 1.45, cy + r * 0.5), col, lw)

    elif kind in ("vsa", "vsa_off"):
        p.polygon(
            [
                (x + w * 0.16, y + h * 0.50),
                (x + w * 0.30, y + h * 0.30),
                (x + w * 0.56, y + h * 0.30),
                (x + w * 0.68, y + h * 0.50),
            ],
            col,
            lw,
        )
        p.line((x + w * 0.16, y + h * 0.50), (x + w * 0.68, y + h * 0.50), col, lw)
        p.circle((x + w * 0.28, y + h * 0.56), h * 0.07, col, lw)
        p.circle((x + w * 0.56, y + h * 0.56), h * 0.07, col, lw)
        wave = [
            (x + w * 0.14 + i * w * 0.09, y + h * 0.80 + (h * 0.07 if i % 2 else -h * 0.07))
            for i in range(7)
        ]
        p.lines(wave, col, lw)
        if kind == "vsa_off":
            p.text("OFF", (x + w * 0.98, y + h * 0.24), int(rh * 0.26), col, "topright", bold=True)

    elif kind == "airbag":
        p.circle((x + w * 0.30, y + h * 0.26), h * 0.11, col, lw)
        p.lines(
            [
                (x + w * 0.14, y + h * 0.80),
                (x + w * 0.20, y + h * 0.46),
                (x + w * 0.40, y + h * 0.44),
                (x + w * 0.44, y + h * 0.60),
            ],
            col,
            lw,
        )
        p.line((x + w * 0.14, y + h * 0.80), (x + w * 0.48, y + h * 0.80), col, lw)
        p.circle((x + w * 0.72, y + h * 0.52), h * 0.20, col, lw)
        p.line((x + w * 0.72, y + h * 0.74), (x + w * 0.72, y + h * 0.84), col, lw)

    elif kind == "seatbelt":
        p.circle((x + w * 0.34, y + h * 0.24), h * 0.11, col, lw)
        p.lines(
            [
                (x + w * 0.18, y + h * 0.82),
                (x + w * 0.24, y + h * 0.46),
                (x + w * 0.46, y + h * 0.44),
                (x + w * 0.52, y + h * 0.62),
            ],
            col,
            lw,
        )
        p.line((x + w * 0.18, y + h * 0.82), (x + w * 0.56, y + h * 0.82), col, lw)
        p.line((x + w * 0.62, y + h * 0.20), (x + w * 0.34, y + h * 0.84), col, 2.2)

    elif kind == "door":
        _van_body(p, x + w * 0.08, y, w * 0.84, h, col, lw)
        p.line((x + w * 0.36, y + h * 0.24), (x + w * 0.36, y + h * 0.78), col, lw)
        p.polygon(
            [
                (x + w * 0.36, y + h * 0.34),
                (x + w * 0.06, y + h * 0.44),
                (x + w * 0.06, y + h * 0.66),
                (x + w * 0.36, y + h * 0.70),
            ],
            col,
            lw,
        )

    elif kind == "slide_door":
        _van_body(p, x + w * 0.06, y, w * 0.72, h, col, lw)
        p.polygon(
            [
                (x + w * 0.52, y + h * 0.32),
                (x + w * 0.96, y + h * 0.38),
                (x + w * 0.96, y + h * 0.74),
                (x + w * 0.52, y + h * 0.74),
            ],
            col,
            lw,
        )
        p.line((x + w * 0.52, y + h * 0.22), (x + w * 0.96, y + h * 0.22), col, lw)

    elif kind == "tailgate":
        _van_body(p, x + w * 0.08, y + h * 0.14, w * 0.80, h * 0.86, col, lw)
        p.lines(
            [
                (x + w * 0.88, y + h * 0.52),
                (x + w * 0.86, y + h * 0.16),
                (x + w * 0.40, y + h * 0.06),
            ],
            col,
            lw,
        )

    elif kind == "pump":
        p.rect((x + w * 0.22, y + h * 0.24, w * 0.34, h * 0.60), col, lw, radius=1.5)
        p.rect((x + w * 0.28, y + h * 0.32, w * 0.22, h * 0.16), col)
        p.line((x + w * 0.56, y + h * 0.40), (x + w * 0.76, y + h * 0.40), col, lw)
        p.line((x + w * 0.76, y + h * 0.40), (x + w * 0.76, y + h * 0.84), col, lw)
        p.line((x + w * 0.18, y + h * 0.84), (x + w * 0.60, y + h * 0.84), col, lw)

    elif kind == "wrench":
        p.circle((x + w * 0.28, y + h * 0.32), h * 0.15, col, lw)
        p.line((x + w * 0.38, y + h * 0.44), (x + w * 0.76, y + h * 0.80), col, 2.4)
        p.line((x + w * 0.20, y + h * 0.22), (x + w * 0.34, y + h * 0.22), col, lw)

    elif kind == "key":
        p.circle((x + w * 0.30, y + h * 0.36), h * 0.16, col, lw)
        p.line((x + w * 0.42, y + h * 0.48), (x + w * 0.80, y + h * 0.82), col, 2.2)
        p.line((x + w * 0.62, y + h * 0.78), (x + w * 0.72, y + h * 0.66), col, lw)

    elif kind == "washer":
        p.arc((x + w * 0.10, y + h * 0.44, w * 0.60, h * 0.66), 180, 360, col, lw)
        p.line((x + w * 0.10, y + h * 0.78), (x + w * 0.70, y + h * 0.78), col, lw)
        for i, ang in enumerate((-38, -14, 10)):
            r0, r1 = h * 0.20, h * 0.42
            a = math.radians(ang)
            p.line(
                (x + w * 0.72 + math.cos(a) * r0, y + h * 0.40 + math.sin(a) * r0),
                (x + w * 0.72 + math.cos(a) * r1, y + h * 0.40 + math.sin(a) * r1),
                col,
                lw,
            )

    elif kind == "vcm":
        p.rect((x, y + h * 0.18, w, h * 0.64), col, lw, radius=2)
        p.text("VCM", (cx, cy), int(rh * 0.36), col, "center", bold=True)

    else:  # pragma: no cover - guard for typos in the layout table
        p.rect((x, y, w, h), col, lw)


def draw_turn_arrow(p: Painter, rect, col, facing: str) -> None:
    """Hollow chevron turn-signal arrow, matching the 300ZX outline style."""
    x, y, w, h = rect
    if facing == "left":
        pts = [
            (x, y + h * 0.5),
            (x + w * 0.42, y),
            (x + w * 0.42, y + h * 0.28),
            (x + w, y + h * 0.28),
            (x + w, y + h * 0.72),
            (x + w * 0.42, y + h * 0.72),
            (x + w * 0.42, y + h),
        ]
    else:
        pts = [
            (x + w, y + h * 0.5),
            (x + w * 0.58, y),
            (x + w * 0.58, y + h * 0.28),
            (x, y + h * 0.28),
            (x, y + h * 0.72),
            (x + w * 0.58, y + h * 0.72),
            (x + w * 0.58, y + h),
        ]
    p.polygon(pts, col, 2.0)


# ---------------------------------------------------------------------------
# Background
# ---------------------------------------------------------------------------


def build_background() -> Painter:
    p = Painter(CANVAS_W, CANVAS_H)
    p.rect((0, 0, CANVAS_W, CANVAS_H), C.BG)

    _bg_top_strip(p)
    _bg_fuel(p)
    _bg_tach(p)
    _bg_triple_bars(p)
    _bg_lamp_row(p)
    _bg_bottom(p)

    # Horizontal dividers that frame the lamp strip, as on the 300ZX panel.
    for yy in (L.LAMP_ROW_Y - 6, L.LAMP_ROW_Y + L.LAMP_ROW_H + 6):
        p.line((16, yy), (CANVAS_W - 16, yy), C.SCALE_LINE, 1.4)

    return p


def _bg_top_strip(p: Painter) -> None:
    p.text("SPEED", L.SPEED_LABEL_MIDRIGHT, 19, C.LABEL, "midright", bold=True, spacing=1.2)

    draw_turn_arrow(p, L.TURN_L_RECT, C.GREEN_GHOST, "left")
    draw_turn_arrow(p, L.TURN_R_RECT, C.GREEN_GHOST, "right")

    p.rect(L.SPEED_BOX, C.PANEL, radius=4)
    p.rect(L.SPEED_BOX, C.PANEL_EDGE, 1, radius=4)
    p.text("888", L.SPEED_DIGITS_MIDRIGHT, 48, C.CYAN_GHOST, "midright", kind="seg7")
    p.text("MPH", L.SPEED_UNIT_TOPLEFT, 15, C.LABEL, bold=True)

    p.text("CRUISE CONT.", L.CRUISE_LABEL_TOPLEFT, 12, C.LABEL_DIM, bold=True, spacing=0.6)
    p.rect(L.CRUISE_LAMP_RECT, C.GREEN_GHOST, 1.4, radius=3)
    cl = L.CRUISE_LAMP_RECT
    p.text("CRUISE", (cl[0] + cl[2] / 2, cl[1] + cl[3] / 2), 13, C.GREEN_GHOST, "center", bold=True)

    p.text("888", L.OUTSIDE_TEMP_MIDRIGHT, 26, C.CYAN_GHOST, "midright", kind="seg7")
    p.text("\u00b0F", L.OUTSIDE_TEMP_LABEL_TOPLEFT, 13, C.LABEL, bold=True)
    p.text(
        "OUTSIDE TEMP",
        L.OUTSIDE_TEMP_CAPTION_MIDRIGHT,
        9,
        C.LABEL_DIM,
        "midright",
        bold=True,
        spacing=0.6,
    )

    # Dotted speed reference scale
    x0, x1, yy = L.SPEED_SCALE_X0, L.SPEED_SCALE_X1, L.SPEED_SCALE_Y
    for mph in L.SPEED_SCALE_TICKS:
        t = mph / max(L.SPEED_SCALE_TICKS)
        tx = x0 + (x1 - x0) * t
        p.circle((tx, yy - 8), 1.6, C.CYAN_MID)
        p.text(str(mph), (tx, yy + 2), 11, C.LABEL_DIM, "midtop", bold=True)
    p.text("MPH", L.SPEED_SCALE_LABEL_TOPLEFT, 10, C.LABEL_DIM, bold=True)


def _bg_fuel(p: Painter) -> None:
    p.text("FUEL", L.FUEL_LABEL_MIDRIGHT, 15, C.LABEL, "midright", bold=True, spacing=0.8)
    draw_glyph(p, "pump", L.FUEL_ICON_RECT, C.LABEL)

    rect = L.FUEL_BAR_RECT
    p.rect(L.FUEL_FRAME_RECT, C.PANEL, radius=3)
    p.rect(L.FUEL_FRAME_RECT, C.PANEL_EDGE, 1, radius=3)

    for i, seg in enumerate(bar_segment_rects(rect)):
        col = C.RED_GHOST if i in BAR_WARN_ZONES["fuel"] else C.CYAN_GHOST
        p.rect(seg, col, radius=1)

    sx = L.FUEL_SCALE_X
    for label, frac in (("F", 0.0), ("", 0.5), ("E", 1.0)):
        ly = rect[1] + rect[3] * frac
        p.line((sx + 2, ly), (sx + 9, ly), C.SCALE_LINE, 1.2)
        if label:
            p.text(label, (sx + 12, ly), 12, C.LABEL, "midleft", bold=True)

    p.text("88", L.FUEL_DIGITS_MIDRIGHT, 26, C.CYAN_GHOST, "midright", kind="seg7")
    p.text("GAL", L.FUEL_UNIT_TOPLEFT, 11, C.LABEL, bold=True)
    p.text("REGULAR UNLEADED ONLY", L.FUEL_NOTE_TOPLEFT, 8, C.LABEL_DIM, bold=True)


def _bg_tach(p: Painter) -> None:
    p.text("TACH", L.TACH_LABEL_MIDRIGHT, 18, C.LABEL, "midright", bold=True, spacing=1.2)

    # Ghost bars - the lit frames overlay these exactly.
    for i in range(TACH_BARS):
        bx, by, bw, bh = tach_bar_geom(i)
        col = C.RED_GHOST if tach_bar_is_redline(i) else C.CYAN_GHOST
        p.rect((bx, by, bw, bh), col)

    # Printed envelope curve over the top of the bars.
    pts_white, pts_red = [], []
    for i in range(TACH_BARS):
        bx, by, bw, _bh = tach_bar_geom(i)
        pt = (bx + bw / 2.0, by - 4)
        (pts_red if tach_bar_is_redline(i) else pts_white).append(pt)
    if pts_white:
        p.lines(pts_white, C.SCALE_LINE, 1.8)
    if pts_red:
        p.lines([pts_white[-1]] + pts_red, C.RED, 2.2)

    # Digital x100 r/min readout
    p.text("88", L.TACH_DIGITS_MIDRIGHT, 30, C.CYAN_GHOST, "midright", kind="seg7")
    p.text("x100r/min", L.TACH_DIGITS_UNIT_TOPLEFT, 11, C.LABEL, bold=True)

    # Scale along the bottom
    yy = L.TACH_SCALE_Y
    for tick in L.TACH_SCALE_TICKS:
        tx = tach_x_for_rpm(tick * 1000)
        red = tick * 1000 >= TACH_REDLINE_RPM
        col = C.RED if red else C.LABEL
        p.line((tx, yy - 8), (tx, yy - 2), C.SCALE_LINE, 1.2)
        text = f"{tick:g}"
        p.text(text, (tx, yy), 13, col, "midtop", bold=True)
    p.text("x1000r/min", L.TACH_SCALE_UNIT_TOPLEFT, 11, C.LABEL, bold=True)


def _bg_triple_bars(p: Painter) -> None:
    for idx, (key, icon, top_lbl, bot_lbl, unit) in enumerate(L.TRIPLE_SPECS):
        bx = L.TRIPLE_BAR_X[idx]
        rect = (bx, L.TRIPLE_BAR_Y, L.TRIPLE_BAR_W, L.TRIPLE_BAR_H)
        frame = (bx - 5, L.TRIPLE_FRAME_Y, L.TRIPLE_BAR_W + 10, L.TRIPLE_FRAME_H)
        p.rect(frame, C.PANEL, radius=3)
        p.rect(frame, C.PANEL_EDGE, 1, radius=3)

        for i, seg in enumerate(bar_segment_rects(rect)):
            col = C.RED_GHOST if i in BAR_WARN_ZONES[key] else C.CYAN_GHOST
            p.rect(seg, col, radius=1)

        draw_glyph(p, icon, (bx - 3, L.TRIPLE_ICON_Y, L.TRIPLE_BAR_W + 6, 24), C.LABEL)

        cx = bx + L.TRIPLE_BAR_W / 2.0
        p.text(top_lbl, (cx, L.TRIPLE_TOP_LABEL_Y), 11, C.LABEL, "center", bold=True)
        p.text(bot_lbl, (cx, L.TRIPLE_BOT_LABEL_Y), 11, C.LABEL, "center", bold=True)
        p.text(unit, (cx, L.TRIPLE_UNIT_Y), 11, C.LABEL, "midtop", bold=True)


def _bg_lamp_row(p: Painter) -> None:
    for i, (_key, glyph, col) in enumerate(LAMPS):
        rect = lamp_rect(i)
        ghost = {
            C.RED: C.RED_GHOST,
            C.AMBER: C.AMBER_GHOST,
            C.GREEN: C.GREEN_GHOST,
            C.BLUE: C.BLUE_GHOST,
        }[col]
        draw_glyph(p, glyph, rect, ghost)


def _bg_bottom(p: Painter) -> None:
    # Odometer
    p.rect(L.ODO_BOX, C.PANEL, radius=3)
    p.rect(L.ODO_BOX, C.PANEL_EDGE, 1, radius=3)
    p.text("888888", L.ODO_DIGITS_MIDRIGHT, 32, C.CYAN_GHOST, "midright", kind="seg7")
    p.text("MILE", L.ODO_UNIT_TOPLEFT, 11, C.LABEL, bold=True)
    p.text("ODOMETER", L.ODO_CAPTION_TOPLEFT, 9, C.LABEL_DIM, bold=True, spacing=0.8)

    # Gear selector cells
    for i, g in enumerate(GEARS):
        rect = gear_rect(i)
        p.rect(rect, C.PANEL, radius=3)
        p.rect(rect, C.PANEL_EDGE, 1, radius=3)
        p.text(
            g,
            (rect[0] + rect[2] / 2, rect[1] + rect[3] / 2),
            24,
            C.CYAN_GHOST,
            "center",
            bold=True,
        )
    p.text("SELECT LEVER POSITION", L.GEAR_CAPTION_TOPLEFT, 9, C.LABEL_DIM, bold=True, spacing=0.8)

    # Trip computer fields
    for _key, label, box, digits_mr, unit, unit_tl, ghost in L.TRIP_FIELDS:
        p.rect(box, C.PANEL, radius=3)
        p.rect(box, C.PANEL_EDGE, 1, radius=3)
        p.text(
            label,
            (box[0] + L.TRIP_LABEL_DX, box[1] + box[3] / 2),
            14,
            C.LABEL,
            "midright",
            bold=True,
        )
        p.text(ghost, digits_mr, 24, C.CYAN_GHOST, "midright", kind="seg7")
        p.text(unit, unit_tl, 10, C.LABEL, bold=True)

    p.text("TRIP", L.TRIP_CAPTION_TOPRIGHT, 9, C.LABEL_DIM, "topright", bold=True, spacing=0.8)

    # VCM badge (Variable Cylinder Management - 2006 EX-L / Touring)
    vb = L.VCM_BADGE_RECT
    p.rect(vb, C.PANEL, radius=3)
    p.rect(vb, C.PANEL_EDGE, 1, radius=3)
    p.text("ECO", (vb[0] + vb[2] / 2, vb[1] + vb[3] / 2), 22, C.GREEN_GHOST, "center", bold=True)
    p.text("VCM 3-CYL MODE", L.VCM_CAPTION_TOPLEFT, 9, C.LABEL_DIM, bold=True, spacing=0.5)


# ---------------------------------------------------------------------------
# Frame generators
# ---------------------------------------------------------------------------


def gen_tach_frames(out_dir: str) -> int:
    x0, y0, w, h = L.TACH_BAR_RECT
    for frame in range(TACH_FRAME_COUNT):
        p = Painter(w, h, origin=(x0, y0))
        for i in range(frame):
            bx, by, bw, bh = tach_bar_geom(i)
            col = C.RED if tach_bar_is_redline(i) else C.CYAN
            p.rect((bx, by, bw, bh), col)
        p.save(os.path.join(out_dir, f"tach_{frame:02d}.png"))
    return TACH_FRAME_COUNT


def gen_bar_frames(out_dir: str) -> int:
    count = 0
    for key, rect in BAR_RECTS.items():
        segs = bar_segment_rects(rect)
        for frame in range(BAR_FRAME_COUNT):
            p = Painter(rect[2], rect[3], origin=(rect[0], rect[1]))
            for i in range(frame):
                p.rect(segs[i], lit_segment_color(key, i, frame), radius=1)
            p.save(os.path.join(out_dir, f"{key}_{frame:02d}.png"))
            count += 1
    return count


def gen_lamp_sprites(out_dir: str) -> int:
    for i, (key, glyph, col) in enumerate(LAMPS):
        rect = lamp_rect(i)
        p = Painter(rect[2], rect[3], origin=(rect[0], rect[1]))
        draw_glyph(p, glyph, rect, col)
        p.save(os.path.join(out_dir, f"{key}.png"))

    # Turn arrows and the cruise / VCM badges are lamps too, just placed
    # outside the strip.
    for key, rect, facing in (
        ("turn_left", L.TURN_L_RECT, "left"),
        ("turn_right", L.TURN_R_RECT, "right"),
    ):
        p = Painter(rect[2], rect[3], origin=(rect[0], rect[1]))
        draw_turn_arrow(p, rect, C.GREEN, facing)
        p.save(os.path.join(out_dir, f"{key}.png"))

    cl = L.CRUISE_LAMP_RECT
    p = Painter(cl[2], cl[3], origin=(cl[0], cl[1]))
    p.rect(cl, C.GREEN, 1.4, radius=3)
    p.text("CRUISE", (cl[0] + cl[2] / 2, cl[1] + cl[3] / 2), 13, C.GREEN, "center", bold=True)
    p.save(os.path.join(out_dir, "cruise.png"))

    vb = L.VCM_BADGE_RECT
    p = Painter(vb[2], vb[3], origin=(vb[0], vb[1]))
    p.text("ECO", (vb[0] + vb[2] / 2, vb[1] + vb[3] / 2), 22, C.GREEN, "center", bold=True)
    p.save(os.path.join(out_dir, "eco.png"))

    # Small pip that lights up along the speed reference scale.
    p = Painter(8, 8)
    p.circle((4, 4), 2.4, C.CYAN)
    p.save(os.path.join(out_dir, "pip.png"))

    return len(LAMPS) + 5


def gen_gear_sprites(out_dir: str) -> int:
    for i, g in enumerate(GEARS):
        rect = gear_rect(i)
        p = Painter(rect[2], rect[3], origin=(rect[0], rect[1]))
        p.rect(rect, (18, 40, 42), radius=3)
        p.rect(rect, C.CYAN_MID, 1.2, radius=3)
        p.text(g, (rect[0] + rect[2] / 2, rect[1] + rect[3] / 2), 24, C.CYAN, "center", bold=True)
        p.save(os.path.join(out_dir, f"gear_{i}.png"))
    return len(GEARS)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    pygame.init()
    pygame.display.set_mode((1, 1))

    os.makedirs(ASSET_ROOT, exist_ok=True)

    bg = build_background()
    bg.save(os.path.join(ASSET_ROOT, "background.png"))
    print(f"background.png          {CANVAS_W}x{CANVAS_H}")

    n = gen_tach_frames(os.path.join(ASSET_ROOT, "tach"))
    print(f"tach/                   {n} frames")

    n = gen_bar_frames(os.path.join(ASSET_ROOT, "bars"))
    print(f"bars/                   {n} frames")

    n = gen_lamp_sprites(os.path.join(ASSET_ROOT, "lamps"))
    print(f"lamps/                  {n} sprites")

    n = gen_gear_sprites(os.path.join(ASSET_ROOT, "gear"))
    print(f"gear/                   {n} sprites")

    pygame.quit()


if __name__ == "__main__":
    main()

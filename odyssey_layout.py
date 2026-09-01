"""
Shared layout / palette map for the 2006 Honda Odyssey digital cluster.

This module is the single source of truth for the design. Both the asset
generator (``tools/gen_odyssey_assets.py``) and the runtime
(``odyssey_dash.py``) import from here, so a coordinate only ever exists in
one place.

Visual language is borrowed from the 1985 Nissan 300ZX digital cluster:
cyan vacuum-fluorescent segments on near-black, silkscreened white labels,
a horizontal tach bar-graph under a printed power-curve envelope, and
vertical segmented bars for the secondary gauges.

Vehicle data is specific to a 2006 Honda Odyssey (J35A7 3.5 V6, 5-speed
automatic, 21.0 US gal tank, ~6300 rpm redline, VCM on EX-L/Touring).
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ASSET_ROOT = os.path.join(PROJECT_ROOT, "assets", "odyssey")
FONT_ROOT = os.path.join(PROJECT_ROOT, "assets", "digifiz", "fonts")

FONT_DSEG7 = os.path.join(FONT_ROOT, "DSEG7Classic-Bold.ttf")
FONT_DSEG14 = os.path.join(FONT_ROOT, "DSEG14Classic-Regular.ttf")
LABEL_FONT_NAME = "dejavusans"

# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------

# 2.46:1 - matches the aspect of the 300ZX panel in the reference photo and
# maps cleanly onto stretched aftermarket cluster LCDs.
CANVAS_W, CANVAS_H = 1280, 520

# Supersample factor used by the generator for antialiasing.
SUPERSAMPLE = 3

FPS = 60

# ---------------------------------------------------------------------------
# Palette - sampled from the reference photo
# ---------------------------------------------------------------------------


class C:
    BG = (5, 9, 11)
    PANEL = (9, 15, 17)
    PANEL_EDGE = (26, 44, 47)

    CYAN = (78, 245, 238)
    CYAN_MID = (30, 132, 130)
    CYAN_GHOST = (12, 44, 46)

    RED = (255, 62, 48)
    RED_GHOST = (52, 12, 10)
    AMBER = (255, 168, 32)
    AMBER_GHOST = (52, 34, 6)
    GREEN = (86, 240, 120)
    GREEN_GHOST = (12, 48, 22)
    BLUE = (90, 170, 255)
    BLUE_GHOST = (14, 30, 52)
    WHITE = (226, 238, 240)

    LABEL = (196, 214, 218)
    LABEL_DIM = (104, 126, 130)
    SCALE_LINE = (150, 172, 176)


# ---------------------------------------------------------------------------
# Vehicle constants (2006 Odyssey)
# ---------------------------------------------------------------------------

TACH_MAX_RPM = 7000
TACH_RPM_STEP = 100                     # one generated frame per step
TACH_FRAME_COUNT = TACH_MAX_RPM // TACH_RPM_STEP + 1
TACH_REDLINE_RPM = 6300

SPEED_MAX_MPH = 120
FUEL_CAPACITY_GAL = 21.0
BAR_SEGMENTS = 20                       # segments in each vertical bar gauge
BAR_FRAME_COUNT = BAR_SEGMENTS + 1

COOLANT_MIN_F, COOLANT_MAX_F = 120, 270
OIL_MIN_PSI, OIL_MAX_PSI = 0, 90
VOLT_MIN_V, VOLT_MAX_V = 10.0, 16.0

GEARS = ("P", "R", "N", "D", "3", "2", "1")

# ---------------------------------------------------------------------------
# Top strip
# ---------------------------------------------------------------------------

SPEED_LABEL_MIDRIGHT = (392, 34)
TURN_L_RECT = (404, 14, 46, 34)          # x, y, w, h
SPEED_BOX = (470, 6, 262, 60)
SPEED_DIGITS_MIDRIGHT = (700, 36)        # midright anchor inside SPEED_BOX
SPEED_UNIT_TOPLEFT = (740, 24)
TURN_R_RECT = (800, 14, 46, 34)

CRUISE_LABEL_TOPLEFT = (900, 14)
CRUISE_LAMP_RECT = (900, 30, 84, 22)

OUTSIDE_TEMP_MIDRIGHT = (1224, 34)
OUTSIDE_TEMP_LABEL_TOPLEFT = (1230, 22)
OUTSIDE_TEMP_CAPTION_MIDRIGHT = (1224, 56)

# Speed reference scale (the dotted 35/45/55/... strip on the 300ZX)
SPEED_SCALE_Y = 78
SPEED_SCALE_X0, SPEED_SCALE_X1 = 476, 726
SPEED_SCALE_TICKS = (20, 40, 60, 80, 100)
SPEED_SCALE_LABEL_TOPLEFT = (734, 70)
SPEED_PIP_DY = -8                        # pip sits this far above SPEED_SCALE_Y

# ---------------------------------------------------------------------------
# Main gauge row
# ---------------------------------------------------------------------------

# Fuel gauge (left column)
FUEL_LABEL_MIDRIGHT = (72, 106)
FUEL_ICON_RECT = (78, 96, 22, 22)
FUEL_BAR_RECT = (40, 130, 44, 128)       # the segmented column itself
FUEL_FRAME_RECT = (35, 125, 54, 138)
FUEL_SCALE_X = 88                        # F / mid / E tick labels
FUEL_DIGITS_MIDRIGHT = (84, 284)
FUEL_UNIT_TOPLEFT = (90, 276)
FUEL_NOTE_TOPLEFT = (16, 300)

# Tachometer (centre)
TACH_BAR_RECT = (196, 128, 700, 150)     # bar-graph plot area
TACH_LABEL_MIDRIGHT = (188, 234)
TACH_DIGITS_MIDRIGHT = (300, 150)        # the "14" x100 r/min readout
TACH_DIGITS_UNIT_TOPLEFT = (306, 140)
TACH_SCALE_Y = 290
TACH_SCALE_TICKS = (0.5, 1, 2, 3, 4, 5, 6, 7)
TACH_SCALE_UNIT_TOPLEFT = (902, 284)

# Right-hand triple bars
TRIPLE_BAR_Y = 130
TRIPLE_BAR_H = 128
TRIPLE_BAR_W = 34
TRIPLE_BAR_X = (966, 1058, 1150)         # temp, oil, volt
TRIPLE_FRAME_Y = 112
TRIPLE_FRAME_H = 164
TRIPLE_TOP_LABEL_Y = 121
TRIPLE_BOT_LABEL_Y = 268
TRIPLE_ICON_Y = 86
TRIPLE_UNIT_Y = 280
TRIPLE_SPECS = (
    # key, icon, top scale label, bottom scale label, unit caption
    ("temp", "thermo", "270", "120", "\u00b0F"),
    ("oil", "oilcan", "90", "45", "lb/in\u00b2"),
    ("volt", "battery", "16", "10", "V"),
)

# ---------------------------------------------------------------------------
# Indicator lamp row
# ---------------------------------------------------------------------------

LAMP_ROW_Y = 324
LAMP_ROW_H = 46
LAMP_W, LAMP_H = 58, 34
LAMP_GAP = 8
LAMP_ROW_X0 = 30

# (key, glyph, colour) - order is left to right across the strip.
LAMPS: tuple[tuple[str, str, tuple[int, int, int]], ...] = (
    ("highbeam", "highbeam", C.BLUE),
    ("mil", "engine", C.AMBER),
    ("oil_press", "oilcan", C.RED),
    ("battery", "battery", C.RED),
    ("brake", "brake", C.RED),
    ("abs", "abs", C.AMBER),
    ("vsa", "vsa", C.AMBER),
    ("vsa_off", "vsa_off", C.AMBER),
    ("srs", "airbag", C.RED),
    ("seatbelt", "seatbelt", C.RED),
    ("door", "door", C.RED),
    ("slide_door", "slide_door", C.RED),
    ("tailgate", "tailgate", C.RED),
    ("low_fuel", "pump", C.AMBER),
    ("maint", "wrench", C.AMBER),
    ("vcm", "vcm", C.GREEN),
    ("security", "key", C.GREEN),
    ("washer", "washer", C.AMBER),
)


def lamp_rect(index: int) -> tuple[int, int, int, int]:
    x = LAMP_ROW_X0 + index * (LAMP_W + LAMP_GAP)
    return (x, LAMP_ROW_Y + (LAMP_ROW_H - LAMP_H) // 2, LAMP_W, LAMP_H)


# ---------------------------------------------------------------------------
# Bottom data row
# ---------------------------------------------------------------------------

ODO_BOX = (30, 392, 268, 52)
ODO_DIGITS_MIDRIGHT = (252, 418)
ODO_UNIT_TOPLEFT = (258, 410)
ODO_CAPTION_TOPLEFT = (30, 450)

GEAR_STRIP_Y = 396
GEAR_CELL_W, GEAR_CELL_H = 40, 44
GEAR_STRIP_X0 = 336
GEAR_CAPTION_TOPLEFT = (336, 450)


def gear_rect(index: int) -> tuple[int, int, int, int]:
    return (GEAR_STRIP_X0 + index * (GEAR_CELL_W + 4), GEAR_STRIP_Y, GEAR_CELL_W, GEAR_CELL_H)


# Trip computer (right side): two rows of two fields.
TRIP_FIELDS = (
    # key, label, box rect, digit midright, unit, unit topleft, ghost
    ("trip_a", "A", (676, 388, 200, 44), (826, 410), "MILE", (832, 402), "888.8"),
    ("trip_b", "B", (930, 388, 200, 44), (1080, 410), "MILE", (1086, 402), "888.8"),
    ("avg_mpg", "AVG", (676, 442, 200, 44), (826, 464), "MPG", (832, 456), "88.8"),
    ("dte", "DTE", (930, 442, 200, 44), (1080, 464), "MILE", (1086, 456), "888"),
)
TRIP_LABEL_DX = -10          # label sits this far left of each box
TRIP_CAPTION_TOPRIGHT = (668, 374)

VCM_BADGE_RECT = (1150, 388, 106, 44)
VCM_CAPTION_TOPLEFT = (1150, 438)

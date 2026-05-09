"""
Toyota Cressida TRONIX DISPLAY Dashboard (~1982)
Recreates the iconic digital instrument cluster and dashboard interior.
Controls: UP/DOWN arrows = speed/rpm, F/E = fuel level
"""

import pygame
import math
import sys
import random

pygame.init()

WIDTH, HEIGHT = 1280, 720
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Toyota TRONIX DISPLAY — 1982 Cressida")
clock = pygame.time.Clock()

# ── Color Palette ──────────────────────────────────────────────────────────────
BG           = (6, 4, 2)
BROWN_DARK   = (52, 30, 10)
BROWN_MID    = (95, 58, 24)
BROWN_LIGHT  = (138, 90, 44)
BROWN_PALE   = (175, 128, 72)
TAN          = (200, 158, 98)
BEZEL_DARK   = (18, 11, 4)
BEZEL_RIM    = (55, 38, 16)
PANEL_BG     = (10, 6, 2)

DIGI_GREEN   = (0, 230, 180)
DIGI_DIM     = (0, 30, 22)
DIGI_RED     = (230, 45, 25)
DIGI_RED_DIM = (40, 8, 5)
DIGI_AMBER   = (220, 160, 0)
DIGI_CYAN    = (0, 200, 230)

WARN_GREEN   = (30, 210, 60)
WARN_RED     = (230, 40, 20)
WARN_YELLOW  = (220, 200, 10)
WARN_CYAN    = (0, 195, 225)
WARN_ORANGE  = (230, 120, 0)

TICK_DIM     = (65, 55, 42)
TICK_LIGHT   = (170, 158, 135)
NEEDLE_COL   = (220, 55, 30)


# ── Seven-Segment Display ──────────────────────────────────────────────────────
SEG_MAP = {
    '0': (1,1,1,1,1,1,0), '1': (0,1,1,0,0,0,0),
    '2': (1,1,0,1,1,0,1), '3': (1,1,1,1,0,0,1),
    '4': (0,1,1,0,0,1,1), '5': (1,0,1,1,0,1,1),
    '6': (1,0,1,1,1,1,1), '7': (1,1,1,0,0,0,0),
    '8': (1,1,1,1,1,1,1), '9': (1,1,1,1,0,1,1),
    ' ': (0,0,0,0,0,0,0), '-': (0,0,0,0,0,0,1),
}

def draw_seg(surf, ch, x, y, w, h, col, dim):
    """Draw one 7-segment character with ghost segments."""
    segs = SEG_MAP.get(str(ch), SEG_MAP[' '])
    t = max(2, w // 10)
    gap = 1
    hw = h // 2

    def bar(active, rect):
        pygame.draw.rect(surf, col if active else dim, rect)

    # a top
    bar(segs[0], (x+t+gap, y,         w-2*t-2*gap, t))
    # b top-right
    bar(segs[1], (x+w-t,   y+t+gap,   t, hw-t-2*gap))
    # c bot-right
    bar(segs[2], (x+w-t,   y+hw+gap,  t, hw-t-gap))
    # d bottom
    bar(segs[3], (x+t+gap, y+h-t,     w-2*t-2*gap, t))
    # e bot-left
    bar(segs[4], (x,       y+hw+gap,  t, hw-t-gap))
    # f top-left
    bar(segs[5], (x,       y+t+gap,   t, hw-t-2*gap))
    # g middle
    bar(segs[6], (x+t+gap, y+hw-t//2, w-2*t-2*gap, t))


def draw_number(surf, val, x, y, dw, dh, col, dim, digits=3, show_leading=False):
    s = str(abs(int(val))).rjust(digits)
    for i, ch in enumerate(s):
        ch_draw = ' ' if (not show_leading and ch == ' ') else ch
        draw_seg(surf, ch_draw, x + i*(dw+4), y, dw, dh, col, dim)


# ── Tachometer ─────────────────────────────────────────────────────────────────
def draw_tacho(surf, rpm, cx, cy, r):
    # Glow backing
    glow = pygame.Surface((r*2+20, r*2+20), pygame.SRCALPHA)
    pygame.draw.circle(glow, (30, 20, 10, 120), (r+10, r+10), r+8)
    surf.blit(glow, (cx-r-10, cy-r-10))

    # Face
    pygame.draw.circle(surf, (12, 7, 3), (cx, cy), r)
    pygame.draw.circle(surf, BEZEL_RIM, (cx, cy), r, 3)
    pygame.draw.circle(surf, (35, 22, 8), (cx, cy), r, 1)

    font_num  = pygame.font.SysFont('monospace', 12, bold=True)
    font_unit = pygame.font.SysFont('monospace', 9)

    # Redline arc (6-8)
    for deg in range(0, 49):  # covers 6k-8k
        a = math.radians(220 - (6/8)*240 - deg * (240/8/6))
        px = int(cx + (r-6) * math.cos(a))
        py = int(cy - (r-6) * math.sin(a))
        pygame.draw.circle(surf, (180, 20, 10), (px, py), 2)

    # Tick marks
    for i in range(49):  # minor
        a = math.radians(220 - i*(240/48))
        is_major = (i % 6 == 0)
        r_out = r - 8
        r_in  = r - (20 if is_major else 14)
        x1 = int(cx + r_out * math.cos(a)); y1 = int(cy - r_out * math.sin(a))
        x2 = int(cx + r_in  * math.cos(a)); y2 = int(cy - r_in  * math.sin(a))
        col = DIGI_RED if i >= 36 else (TICK_LIGHT if is_major else TICK_DIM)
        pygame.draw.line(surf, col, (x1,y1), (x2,y2), 2 if is_major else 1)

    # RPM number labels (0-8)
    for i in range(9):
        a = math.radians(220 - i*(240/8))
        tx = int(cx + (r-34) * math.cos(a))
        ty = int(cy - (r-34) * math.sin(a))
        col = DIGI_RED if i >= 6 else TICK_LIGHT
        lbl = font_num.render(str(i), True, col)
        surf.blit(lbl, (tx - lbl.get_width()//2, ty - lbl.get_height()//2))

    # Unit label
    ul = font_unit.render("×1000 r/min", True, (100, 90, 75))
    surf.blit(ul, (cx - ul.get_width()//2, cy + r//2 + 4))

    # Needle
    clamped = max(0, min(rpm, 8000))
    na = math.radians(220 - (clamped/8000)*240)
    nx = int(cx + (r-22) * math.cos(na))
    ny = int(cy - (r-22) * math.sin(na))
    # Shadow
    pygame.draw.line(surf, (20,10,5), (cx+2, cy+2), (nx+2, ny+2), 2)
    pygame.draw.line(surf, NEEDLE_COL, (cx, cy), (nx, ny), 2)
    pygame.draw.circle(surf, (190, 40, 20), (cx, cy), 6)
    pygame.draw.circle(surf, NEEDLE_COL,   (cx, cy), 4)


# ── Bar Graph ──────────────────────────────────────────────────────────────────
def draw_bar(surf, val, max_v, x, y, w, h, n=10):
    """Vertical segmented bar graph."""
    seg_h = (h - n) // n
    filled = int((val / max_v) * n)
    pygame.draw.rect(surf, (8,5,2), (x, y, w, h))
    for i in range(n):
        sy = y + h - (i+1)*(seg_h+1)
        if i < filled:
            if i >= n-2:  c = DIGI_RED
            elif i >= n-4: c = DIGI_AMBER
            else:          c = DIGI_GREEN
        else:
            if i >= n-2:  c = DIGI_RED_DIM
            else:          c = DIGI_DIM
        pygame.draw.rect(surf, c, (x+2, sy, w-4, seg_h))


# ── Steering Wheel ─────────────────────────────────────────────────────────────
def draw_wheel(surf, cx, cy, r_out, r_hub_x, r_hub_y):
    # Drop shadow
    sh = pygame.Surface((r_out*2+20, r_out*2+20), pygame.SRCALPHA)
    pygame.draw.circle(sh, (0,0,0,100), (r_out+10+6, r_out+10+8), r_out)
    surf.blit(sh, (cx-r_out-10, cy-r_out-10))

    # Rim base
    pygame.draw.circle(surf, BROWN_DARK, (cx, cy), r_out)

    # Rim shading rings
    rim_w = 22
    for i in range(rim_w, 0, -1):
        t = i / rim_w
        c = (
            int(BROWN_DARK[0] + (BROWN_LIGHT[0]-BROWN_DARK[0]) * (1-t)**0.6),
            int(BROWN_DARK[1] + (BROWN_LIGHT[1]-BROWN_DARK[1]) * (1-t)**0.6),
            int(BROWN_DARK[2] + (BROWN_LIGHT[2]-BROWN_DARK[2]) * (1-t)**0.6),
        )
        pygame.draw.circle(surf, c, (cx, cy), r_out - (rim_w - i), 1)

    # Grip texture lines
    for deg in range(0, 360, 8):
        a = math.radians(deg)
        x1 = int(cx + (r_out-rim_w+2) * math.cos(a))
        y1 = int(cy - (r_out-rim_w+2) * math.sin(a))
        x2 = int(cx + (r_out-4) * math.cos(a))
        y2 = int(cy - (r_out-4) * math.sin(a))
        pygame.draw.line(surf, (45, 25, 8), (x1,y1), (x2,y2), 1)

    # Rim highlight edge
    pygame.draw.circle(surf, (160, 115, 60), (cx, cy), r_out, 1)
    pygame.draw.circle(surf, BROWN_DARK, (cx, cy), r_out - rim_w)

    # Spokes — 3 at 90°, 205°, 335°
    spoke_angles = [90, 205, 335]
    inner_r = 52
    for ang in spoke_angles:
        a = math.radians(ang)
        sx1 = cx + int(inner_r * math.cos(a))
        sy1 = cy - int(inner_r * math.sin(a))
        sx2 = cx + int((r_out - rim_w) * math.cos(a))
        sy2 = cy - int((r_out - rim_w) * math.sin(a))
        # Spoke body
        pygame.draw.line(surf, BROWN_DARK, (sx1,sy1), (sx2,sy2), 26)
        pygame.draw.line(surf, BROWN_MID,  (sx1,sy1), (sx2,sy2), 18)
        pygame.draw.line(surf, BROWN_LIGHT,(sx1,sy1), (sx2,sy2), 8)
        # Center seam line
        pygame.draw.line(surf, BROWN_DARK, (sx1,sy1), (sx2,sy2), 1)

    # Center hub — rounded rectangle
    hw, hh = 100, 60
    hub_rect = pygame.Rect(cx-hw//2, cy-hh//2, hw, hh)
    for i in range(5):
        r = 10 - i
        c_val = 52 + i*12
        pygame.draw.rect(surf, (c_val, int(c_val*0.58), int(c_val*0.22)), hub_rect.inflate(i*-3, i*-3), border_radius=r)

    pygame.draw.rect(surf, BEZEL_RIM, hub_rect, 2, border_radius=10)

    # Horizontal seam line on hub
    pygame.draw.line(surf, BROWN_DARK,
                     (cx - hw//2 + 8, cy - 6),
                     (cx + hw//2 - 8, cy - 6), 1)

    # TOYOTA badge
    font_badge = pygame.font.SysFont('arial', 13, bold=True)
    badge = font_badge.render("TOYOTA", True, (215, 185, 135))
    surf.blit(badge, (cx - badge.get_width()//2, cy - badge.get_height()//2 + 4))


# ── AC Vent ────────────────────────────────────────────────────────────────────
def draw_vent(surf, x, y, w, h, slats=7):
    pygame.draw.rect(surf, (8,5,2), (x, y, w, h), border_radius=3)
    pygame.draw.rect(surf, BEZEL_RIM, (x, y, w, h), 2, border_radius=3)

    # Divider in middle
    mid = x + w//2
    pygame.draw.rect(surf, BEZEL_RIM, (mid-3, y+4, 6, h-8))

    # Slats
    slat_h = 5
    gap = (h - slats*slat_h) // (slats+1)
    for i in range(slats):
        sy = y + gap + i*(slat_h+gap)
        # Left half
        pygame.draw.rect(surf, BROWN_MID, (x+6, sy, mid-x-12, slat_h), border_radius=2)
        pygame.draw.line(surf, BROWN_LIGHT, (x+6, sy), (mid-7, sy), 1)
        # Right half
        pygame.draw.rect(surf, BROWN_MID, (mid+6, sy, w-(mid-x)-12, slat_h), border_radius=2)
        pygame.draw.line(surf, BROWN_LIGHT, (mid+6, sy), (x+w-7, sy), 1)


# ── Small Rounded Button ────────────────────────────────────────────────────────
def draw_button(surf, x, y, w, h, label, lit=False, font=None):
    col = BROWN_MID if not lit else (80, 130, 80)
    pygame.draw.rect(surf, col, (x, y, w, h), border_radius=3)
    pygame.draw.rect(surf, BEZEL_RIM, (x, y, w, h), 1, border_radius=3)
    if font and label:
        l = font.render(label, True, (180,160,120) if not lit else (120,230,120))
        surf.blit(l, (x + w//2 - l.get_width()//2, y + h//2 - l.get_height()//2))


# ── Main Draw ──────────────────────────────────────────────────────────────────
def draw_dashboard(surf, speed, rpm, fuel, anim_tick):
    surf.fill(BG)

    # ── Dashboard body ─────────────────────────────────────────────────────────
    # Upper dark pad
    pygame.draw.rect(surf, (22, 13, 5), (0, 0, WIDTH, 230))
    pygame.draw.rect(surf, (16, 10, 3), (0, 0, WIDTH, 195))

    # Main lower dash surface
    pygame.draw.rect(surf, BROWN_MID, (0, 520, WIDTH, HEIGHT-520))
    # Top trim strip
    for i in range(6):
        c_val = 80 + i*8
        pygame.draw.rect(surf, (c_val, int(c_val*0.6), int(c_val*0.25)),
                         (0, 510+i*2, WIDTH, 3))

    # ── Instrument cluster frame ───────────────────────────────────────────────
    CX, CY = 215, 68   # cluster top-left
    CW, CH = 620, 330

    # Outer shadow
    pygame.draw.rect(surf, (4,2,0), (CX-14, CY-14, CW+28, CH+28), border_radius=10)
    # Bezel frame
    for i in range(6):
        c = 15 + i*5
        pygame.draw.rect(surf, (c, int(c*0.62), int(c*0.22)),
                         (CX-8+i, CY-8+i, CW+16-i*2, CH+16-i*2), border_radius=8)
    # Inner panel
    pygame.draw.rect(surf, PANEL_BG, (CX, CY, CW, CH), border_radius=5)

    # Subtle scan-line texture
    for row in range(0, CH, 3):
        pygame.draw.line(surf, (14,9,3), (CX, CY+row), (CX+CW, CY+row))

    # Header strip
    pygame.draw.rect(surf, (20, 13, 5), (CX, CY, CW, 22))

    font_hdr  = pygame.font.SysFont('monospace', 11, bold=True)
    font_sm   = pygame.font.SysFont('monospace', 10, bold=True)
    font_xs   = pygame.font.SysFont('monospace', 9)
    font_unit = pygame.font.SysFont('monospace', 13, bold=True)

    hdr = font_hdr.render("TRONIX  DISPLAY", True, (115, 100, 80))
    surf.blit(hdr, (CX+12, CY+6))

    # Model/computer label right side of header
    comp = font_xs.render("COMPUTER", True, (70, 60, 45))
    surf.blit(comp, (CX+CW-80, CY+7))

    # ── Tachometer ────────────────────────────────────────────────────────────
    tacho_cx = CX + 118
    tacho_cy = CY + 175
    tacho_r  = 108
    draw_tacho(surf, rpm, tacho_cx, tacho_cy, tacho_r)

    # ── Digital Speed Panel ────────────────────────────────────────────────────
    SPX, SPY = CX+262, CY+58
    SPW, SPH = 175, 110

    # Panel surround
    pygame.draw.rect(surf, (6,4,1), (SPX-4, SPY-4, SPW+8, SPH+8), border_radius=4)
    pygame.draw.rect(surf, (32,22,8), (SPX-4, SPY-4, SPW+8, SPH+8), 2, border_radius=4)
    pygame.draw.rect(surf, (5,8,6), (SPX, SPY, SPW, SPH), border_radius=3)

    # Speed digits — 3 digits, large
    dw, dh = 40, 68
    sx0 = SPX + 10
    draw_number(surf, int(speed), sx0, SPY+18, dw, dh, DIGI_GREEN, DIGI_DIM, digits=3)

    # MPH label
    mph_l = font_unit.render("MPH", True, DIGI_GREEN)
    surf.blit(mph_l, (SPX+SPW-45, SPY+SPH-22))

    # SPEED label above panel
    spd_lbl = font_sm.render("SPEED", True, (75, 65, 50))
    surf.blit(spd_lbl, (SPX+4, SPY-16))

    # ── Odometer strip ────────────────────────────────────────────────────────
    ODX, ODY = CX+262, CY+185
    pygame.draw.rect(surf, (5,7,5), (ODX, ODY, 175, 28), border_radius=2)
    pygame.draw.rect(surf, (28,20,8), (ODX, ODY, 175, 28), 1, border_radius=2)

    font_odo = pygame.font.SysFont('monospace', 14, bold=True)
    odo = font_odo.render("0 0 3 4 7 . 2  km", True, (160,148,110))
    surf.blit(odo, (ODX+8, ODY+7))

    # ── Bar graphs: FUEL and TEMP ──────────────────────────────────────────────
    BGX = CX+468
    BGY = CY+38
    BARW, BARH = 28, 130

    # FUEL
    fuel_lbl = font_sm.render("FUEL", True, (75, 65, 50))
    surf.blit(fuel_lbl, (BGX-2, BGY-16))
    draw_bar(surf, fuel, 1.0, BGX, BGY, BARW, BARH, n=12)

    f_l = font_xs.render("F", True, (120,110,90))
    e_l = font_xs.render("E", True, (120,110,90))
    surf.blit(f_l, (BGX+BARW+4, BGY))
    surf.blit(e_l, (BGX+BARW+4, BGY+BARH-12))

    # TEMP
    temp_val = 0.55
    tmp_lbl = font_sm.render("TEMP", True, (75, 65, 50))
    surf.blit(tmp_lbl, (BGX+50-4, BGY-16))
    draw_bar(surf, temp_val, 1.0, BGX+50, BGY, BARW, BARH, n=12)

    h_l = font_xs.render("H", True, (120,110,90))
    c_l = font_xs.render("C", True, (120,110,90))
    surf.blit(h_l, (BGX+50+BARW+4, BGY))
    surf.blit(c_l, (BGX+50+BARW+4, BGY+BARH-12))

    # ── Warning lights row ─────────────────────────────────────────────────────
    WY  = CY + 248
    WX0 = CX + 265
    WGAP = 28

    lights = [
        (WARN_RED,    "●", True),
        (WARN_GREEN,  "●", True),
        (WARN_YELLOW, "●", False),
        (WARN_CYAN,   "●", True),
        (WARN_RED,    "●", False),
        (WARN_ORANGE, "●", True),
        (WARN_GREEN,  "●", False),
        (WARN_RED,    "●", False),
    ]
    font_warn = pygame.font.SysFont('monospace', 14)
    font_icon = pygame.font.SysFont('monospace', 8)

    WARN_LABELS = ["OIL","CHG","TEMP","DOOR","BELT","BRAKE","FUEL","ENG"]
    for i, (col, sym, lit) in enumerate(lights):
        wx = WX0 + i*WGAP
        # Indicator LED
        base_col = col if lit else tuple(max(0,c//6) for c in col)
        # Blink effect for certain ones
        if i in (0, 5) and lit and (anim_tick // 30) % 2 == 0:
            base_col = tuple(max(0,c//4) for c in col)
        pygame.draw.circle(surf, base_col, (wx+6, WY+6), 5)
        if lit:
            glow_s = pygame.Surface((20,20), pygame.SRCALPHA)
            pygame.draw.circle(glow_s, (*col, 60), (10,10), 8)
            surf.blit(glow_s, (wx-4, WY-4))
        # Tiny label
        lbl = font_icon.render(WARN_LABELS[i], True, (70,60,45))
        surf.blit(lbl, (wx-4, WY+14))

    # ── Divider lines inside cluster ───────────────────────────────────────────
    pygame.draw.line(surf, BEZEL_RIM, (CX+248, CY+30), (CX+248, CY+CH-10), 1)
    pygame.draw.line(surf, BEZEL_RIM, (CX+455, CY+30), (CX+455, CY+CH-10), 1)
    pygame.draw.line(surf, BEZEL_RIM, (CX+10,  CY+CH-70),(CX+CW-10,CY+CH-70), 1)

    # ── Right side panel ───────────────────────────────────────────────────────
    RPX = CX + CW + 30
    RPY = 60
    RPW = WIDTH - RPX - 18
    RPH = 370

    # Panel backing
    pygame.draw.rect(surf, BROWN_DARK, (RPX-6, RPY-6, RPW+12, RPH+12), border_radius=6)
    pygame.draw.rect(surf, (28,17,6), (RPX, RPY, RPW, RPH), border_radius=5)

    # ── AC Vents ──────────────────────────────────────────────────────────────
    draw_vent(surf, RPX+10, RPY+15, RPW-20, 78, slats=6)

    # Vent direction thumb
    pygame.draw.rect(surf, BROWN_MID, (RPX+RPW//2-18, RPY+15+78//2-8, 36, 16), border_radius=3)

    # ── Climate control label strip ────────────────────────────────────────────
    STRIP_Y = RPY + 105
    pygame.draw.rect(surf, (18,11,4), (RPX+10, STRIP_Y, RPW-20, 24))
    pygame.draw.rect(surf, BEZEL_RIM, (RPX+10, STRIP_Y, RPW-20, 24), 1)

    clim_labels = [("A/C", False), ("REC", False), ("VENT", True), ("HEAT", False), ("DEF", False)]
    cw_each = (RPW-20) // len(clim_labels)
    font_clim = pygame.font.SysFont('monospace', 9, bold=True)
    for i, (lbl, active) in enumerate(clim_labels):
        lx = RPX + 10 + i*cw_each
        col = (0,180,120) if active else (55,45,32)
        pygame.draw.circle(surf, col, (lx + cw_each//2, STRIP_Y+8), 4)
        l = font_clim.render(lbl, True, (130,110,80) if active else (70,58,42))
        surf.blit(l, (lx + cw_each//2 - l.get_width()//2, STRIP_Y+13))

    # ── Radio / Cassette unit ──────────────────────────────────────────────────
    RDX, RDY = RPX+10, STRIP_Y+35
    RDW, RDH = RPW-20, 52
    pygame.draw.rect(surf, (8,5,2), (RDX, RDY, RDW, RDH), border_radius=3)
    pygame.draw.rect(surf, BEZEL_RIM, (RDX, RDY, RDW, RDH), 2, border_radius=3)

    # Cassette slot
    pygame.draw.rect(surf, (3,2,0), (RDX+10, RDY+16, RDW-80, 18), border_radius=1)
    pygame.draw.rect(surf, (30,20,8), (RDX+10, RDY+16, RDW-80, 18), 1, border_radius=1)

    # Radio display
    pygame.draw.rect(surf, (3,12,4), (RDX+14, RDY+5, 65, 10))
    font_radio = pygame.font.SysFont('monospace', 8)
    freq = font_radio.render("FM 98.7", True, DIGI_GREEN)
    surf.blit(freq, (RDX+16, RDY+5))

    # Preset buttons
    for i in range(4):
        bx = RDX + RDW - 72 + i*17
        draw_button(surf, bx, RDY+8, 14, 12, str(i+1), False, font_xs)

    # Eject / vol knob
    pygame.draw.circle(surf, BROWN_MID, (RDX+RDW-10, RDY+RDH//2), 14)
    pygame.draw.circle(surf, BEZEL_RIM, (RDX+RDW-10, RDY+RDH//2), 14, 1)
    pygame.draw.circle(surf, BROWN_LIGHT,(RDX+RDW-10, RDY+RDH//2), 6)

    # ── Climate slider panel ───────────────────────────────────────────────────
    SLP_Y = RDY + RDH + 16
    SLP_H = 90
    pygame.draw.rect(surf, (14,9,4), (RPX+10, SLP_Y, RPW-20, SLP_H), border_radius=3)
    pygame.draw.rect(surf, BEZEL_RIM, (RPX+10, SLP_Y, RPW-20, SLP_H), 1, border_radius=3)

    slider_defs = [
        ("TEMP", 0.62),
        ("FAN",  0.45),
        ("MODE", 0.30),
        ("REC",  0.80),
        ("A/C",  0.55),
    ]
    n_sliders = len(slider_defs)
    sw_each = (RPW-40) // n_sliders
    font_sl = pygame.font.SysFont('monospace', 8)

    for i, (label, pos) in enumerate(slider_defs):
        sx = RPX + 20 + i*sw_each + sw_each//2 - 5
        # Track
        pygame.draw.rect(surf, (6,4,1), (sx, SLP_Y+8, 10, SLP_H-22))
        pygame.draw.rect(surf, (40,28,10), (sx, SLP_Y+8, 10, SLP_H-22), 1)
        # Knob
        ky = SLP_Y + 8 + int((1-pos)*(SLP_H-38))
        pygame.draw.rect(surf, TAN, (sx-6, ky, 22, 12), border_radius=2)
        pygame.draw.rect(surf, BROWN_PALE, (sx-6, ky, 22, 4), border_radius=2)
        pygame.draw.rect(surf, BEZEL_RIM, (sx-6, ky, 22, 12), 1, border_radius=2)
        # Label
        sl = font_sl.render(label, True, (90,78,58))
        surf.blit(sl, (sx-6+11 - sl.get_width()//2, SLP_Y+SLP_H-15))

    # ── Left side controls panel ───────────────────────────────────────────────
    LPX, LPY = 18, 68
    LPW, LPH = 180, 330
    pygame.draw.rect(surf, BROWN_DARK, (LPX-4, LPY-4, LPW+8, LPH+8), border_radius=6)
    pygame.draw.rect(surf, (22,14,5), (LPX, LPY, LPW, LPH), border_radius=5)

    # Switch buttons
    sw_info = [
        ("DEFROST",  False),
        ("HAZARD",   False),
        ("REAR DEF", False),
        ("WIPERS",   False),
    ]
    for i, (label, lit) in enumerate(sw_info):
        draw_button(surf, LPX+15, LPY+20+i*52, LPW-30, 34, label, lit, font_sm)

    # Dimmer knob
    pygame.draw.circle(surf, BROWN_MID, (LPX+LPW//2, LPY+260), 24)
    pygame.draw.circle(surf, BEZEL_RIM, (LPX+LPW//2, LPY+260), 24, 2)
    pygame.draw.circle(surf, BROWN_LIGHT,(LPX+LPW//2, LPY+260), 10)
    dim_l = font_xs.render("DIM", True, (100,88,65))
    surf.blit(dim_l, (LPX+LPW//2-10, LPY+292))

    # ── Ignition cylinder ─────────────────────────────────────────────────────
    IGX, IGY = CX+CW//2+80, CY+CH+8
    pygame.draw.circle(surf, BROWN_DARK, (IGX, IGY), 22)
    pygame.draw.circle(surf, BEZEL_RIM, (IGX, IGY), 22, 2)
    pygame.draw.circle(surf, (14,9,3), (IGX, IGY), 14)
    # Key slot
    pygame.draw.rect(surf, (8,5,2), (IGX-2, IGY-12, 4, 10))
    pygame.draw.circle(surf, (8,5,2), (IGX, IGY-3), 5)
    # Labels
    for ang, label in [(-45,"ACC"),(0,"ON"),(45,"ST")]:
        a = math.radians(ang+90)
        lx = IGX + int(28*math.cos(a)) - 8
        ly = IGY - int(28*math.sin(a)) - 4
        il = font_xs.render(label, True, (85,72,52))
        surf.blit(il, (lx, ly))

    # ── Steering column ───────────────────────────────────────────────────────
    # Column tube
    pygame.draw.rect(surf, BROWN_DARK, (265, 435, 22, 180), border_radius=5)
    pygame.draw.rect(surf, BROWN_MID, (267, 435, 14, 180), border_radius=4)

    # Left turn stalk
    pygame.draw.rect(surf, BROWN_MID, (108, 462, 158, 18), border_radius=9)
    pygame.draw.rect(surf, BROWN_LIGHT,(112, 464, 140, 8), border_radius=4)
    pygame.draw.circle(surf, BROWN_PALE, (108, 471), 12)

    # Right turn stalk
    pygame.draw.rect(surf, BROWN_MID, (290, 462, 150, 18), border_radius=9)
    pygame.draw.rect(surf, BROWN_LIGHT,(294, 464, 130, 8), border_radius=4)
    pygame.draw.circle(surf, BROWN_PALE, (438, 471), 11)

    # ── Steering wheel ────────────────────────────────────────────────────────
    SW_CX, SW_CY = 276, 510
    draw_wheel(surf, SW_CX, SW_CY, 158, 100, 60)

    # ── Lower dash & trim ──────────────────────────────────────────────────────
    # Glove box panel
    pygame.draw.rect(surf, BROWN_MID, (RPX-6, 540, RPW+12, 155), border_radius=5)
    pygame.draw.rect(surf, BROWN_LIGHT,(RPX-6, 538, RPW+12, 8), border_radius=2)
    pygame.draw.line(surf, BROWN_DARK, (RPX-6, 540+75), (RPX-6+RPW+12, 540+75), 2)

    # Glove box handle
    pygame.draw.rect(surf, BROWN_DARK, (RPX+RPW//2-25, 576, 50, 10), border_radius=5)
    pygame.draw.rect(surf, TAN, (RPX+RPW//2-22, 578, 44, 6), border_radius=3)

    # Center console area
    CCX, CCY = 450, 548
    pygame.draw.rect(surf, BROWN_DARK, (CCX, CCY, 280, 172), border_radius=5)
    pygame.draw.rect(surf, (28,17,6), (CCX+4, CCY+4, 272, 164), border_radius=4)

    # Ashtray / coin tray
    pygame.draw.rect(surf, (12,8,3), (CCX+20, CCY+15, 100, 38), border_radius=3)
    pygame.draw.rect(surf, BEZEL_RIM, (CCX+20, CCY+15, 100, 38), 1, border_radius=3)

    # Small switches row
    for i in range(5):
        draw_button(surf, CCX+20+i*48, CCY+68, 40, 22, "", False, None)
        pygame.draw.circle(surf, (40,28,10) if i!=2 else (0,100,70),
                           (CCX+40+i*48, CCY+79), 5)

    # ── HUD-style speed ghost (subtle) ─────────────────────────────────────────
    font_ghost = pygame.font.SysFont('monospace', 9)
    if speed > 0:
        spd_ghost = font_ghost.render(f"{int(speed)} km/h", True, (40,60,40))
        surf.blit(spd_ghost, (10, HEIGHT-18))

    # ── Reflection sheen on upper dash ─────────────────────────────────────────
    sheen = pygame.Surface((WIDTH, 40), pygame.SRCALPHA)
    for i in range(40):
        alpha = int(15 * (1 - i/40))
        pygame.draw.line(sheen, (200,160,100,alpha), (0,i), (WIDTH,i))
    surf.blit(sheen, (0, 190))

    # ── Bottom wood-grain trim strip ───────────────────────────────────────────
    for i in range(12):
        t = i/12
        c = (
            int(80 + t*60),
            int(48 + t*36),
            int(16 + t*12),
        )
        pygame.draw.rect(surf, c, (0, 505+i*2, WIDTH, 3))


# ── Main loop ──────────────────────────────────────────────────────────────────
def main():
    speed = 0.0
    rpm   = 800.0
    fuel  = 0.74
    tick  = 0

    font_help = pygame.font.SysFont('monospace', 11)

    while True:
        dt = clock.tick(60) / 1000.0
        tick += 1

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit(); sys.exit()

        keys = pygame.key.get_pressed()
        if keys[pygame.K_UP]:
            speed = min(speed + 60*dt, 200)
            rpm   = 800 + (speed/200)*7200
        elif keys[pygame.K_DOWN]:
            speed = max(speed - 80*dt, 0)
            rpm   = 800 + (speed/200)*7200
        else:
            # Idle: small rpm oscillation
            rpm = 850 + 40*math.sin(tick*0.04)
            speed = max(speed - 15*dt, 0)
            if speed > 0:
                rpm = 800 + (speed/200)*7200

        if keys[pygame.K_f]:
            fuel = min(fuel + 0.3*dt, 1.0)
        if keys[pygame.K_e]:
            fuel = max(fuel - 0.3*dt, 0.0)

        draw_dashboard(screen, speed, rpm, fuel, tick)

        # Help overlay
        helps = ["↑↓ Accelerate/Brake", "F/E Fuel ±", "ESC Quit"]
        for i, h in enumerate(helps):
            lbl = font_help.render(h, True, (60, 50, 35))
            screen.blit(lbl, (WIDTH-200, HEIGHT-55+i*15))

        pygame.display.flip()


if __name__ == "__main__":
    main()

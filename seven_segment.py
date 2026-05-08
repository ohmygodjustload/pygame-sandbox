import pygame
import sys
import time

AMBER = (255, 176, 0)
DIM = (60, 30, 0)
BLACK = (0, 0, 0)

SEGMENTS = {
    "0": "abdcef", "1": "bc", "2": "abged", "3": "abgcd",
    "4": "fgbc", "5": "afgcd", "6": "afgcde", "7": "abc",
    "8": "abcdefg", "9": "abcdfg",
}

def draw_digit(surface, x, y, w, h, char, thick=8):
    cx, cy = x + w // 2, y + h // 2
    on = set(SEGMENTS.get(char, ""))
    coords = {
        "a": (x, y, w, thick),
        "b": (x + w - thick, y, thick, h // 2),
        "c": (x + w - thick, cy, thick, h // 2),
        "d": (x, y + h - thick, w, thick),
        "e": (x, cy, thick, h // 2),
        "f": (x, y, thick, h // 2),
        "g": (x, cy - thick // 2, w, thick),
    }
    for seg, rect in coords.items():
        color = AMBER if seg in on else DIM
        pygame.draw.rect(surface, color, rect)

pygame.init()
screen = pygame.display.set_mode((800, 300))
pygame.display.set_caption("retro digits")
clock = pygame.time.Clock()
start = time.time()

while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT or (
            event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
        ):
            pygame.quit()
            sys.exit()
    screen.fill(BLACK)
    n = int((time.time() - start) * 60) % 10000
    s = f"{n:04d}"
    for i, ch in enumerate(s):
        draw_digit(screen, 60 + i * 180, 50, 140, 200, ch)
    pygame.display.flip()
    clock.tick(60)
    # TODO - create digital dash design based on 1984 Toyota Cressida

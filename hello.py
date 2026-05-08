import pygame
import sys

pygame.init()
screen = pygame.display.set_mode((640, 360))
pygame.display.set_caption("pygame sandbox - hello")
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 64)
text = font.render("Hello, world!", True, (255, 176, 0))
text_rect = text.get_rect(center=screen.get_rect().center)

while True:
    for event in pygame.event.get():
        if event.type == pygame.QUIT or (
            event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
        ):
            pygame.quit()
            sys.exit()
    screen.fill((0, 0, 0))
    screen.blit(text, text_rect)
    pygame.display.flip()
    clock.tick(60)

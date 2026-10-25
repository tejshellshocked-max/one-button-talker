"""
Gaze grid test using the EyeGestures library (Python 3.13).

1) CALIBRATION (~30 s): a red dot appears. Look at it; when you've looked at it
   long enough it jumps somewhere else. Keep following it.
2) TEST: a 3x3 grid appears. The tile you look at lights up; a blue dot shows
   where it thinks you're looking.
Keys:  ESC = quit,  C = calibrate again,  4 = switch to a 4x7 (keyboard-size) grid
Keep your head still, about an arm's length from the screen.

Eye tracking: EyeGestures (open source, GPL-3.0) https://github.com/NativeSensors/EyeGestures
"""
import time
import mp_solutions_shim  # noqa: F401  (must come before eyeGestures)
import cv2
import pygame
from eyeGestures import EyeGestures_v3

CALIBRATION_SECONDS = 30

pygame.init()
screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
W, H = screen.get_size()
font = pygame.font.SysFont(None, 48)
clock = pygame.time.Clock()

tracker = EyeGestures_v3()
camera = cv2.VideoCapture(0)
rows, cols = 3, 3
calib_until = time.time() + CALIBRATION_SECONDS

running = True
while running:
    for e in pygame.event.get():
        if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
            running = False
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_c:
            calib_until = time.time() + CALIBRATION_SECONDS
        elif e.type == pygame.KEYDOWN and e.key == pygame.K_4:
            rows, cols = (4, 7) if (rows, cols) == (3, 3) else (3, 3)

    ok, frame = camera.read()
    if not ok:
        continue
    calibrating = time.time() < calib_until
    try:
        event, cevent = tracker.step(frame, calibrating, W, H, context="grid")
    except Exception:
        event = cevent = None

    screen.fill((20, 20, 30))
    if event is None:
        msg = font.render("Looking for your face...", True, (200, 200, 200))
        screen.blit(msg, msg.get_rect(center=(W // 2, H // 2)))
    elif calibrating:
        cx, cy = int(cevent.point[0]), int(cevent.point[1])
        pygame.draw.circle(screen, (230, 60, 60), (cx, cy), 28)
        left = int(calib_until - time.time())
        msg = font.render(f"Look at the red dot ({left}s)", True, (200, 200, 200))
        screen.blit(msg, (40, 40))
    else:
        x, y = float(event.point[0]), float(event.point[1])
        col = min(cols - 1, max(0, int(x / W * cols)))
        row = min(rows - 1, max(0, int(y / H * rows)))
        for r in range(rows):
            for c in range(cols):
                rect = pygame.Rect(c * W // cols + 6, r * H // rows + 6, W // cols - 12, H // rows - 12)
                color = (255, 205, 60) if (r, c) == (row, col) else (60, 60, 75)
                pygame.draw.rect(screen, color, rect, border_radius=16)
                label = font.render(str(r * cols + c + 1), True, (20, 20, 30))
                screen.blit(label, label.get_rect(center=rect.center))
        pygame.draw.circle(screen, (60, 200, 255), (int(x), int(y)), 12)
        hint = font.render("ESC quit   C recalibrate   4 switch grid", True, (150, 150, 160))
        screen.blit(hint, (40, H - 60))
    pygame.display.flip()
    clock.tick(30)

pygame.quit()

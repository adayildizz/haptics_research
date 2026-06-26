"""
Demo entry point.

Usage:
    python demo/main.py --heart
    python demo/main.py --train
    python demo/main.py --texture
    python demo/main.py --bar
    python demo/main.py --pie
    python demo/main.py --image path/to/img.png
"""

import pygame
import os
import sys
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import *
from core.haptics import HapticController

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description="Haptic Demo")
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("--heart",   action="store_true")
group.add_argument("--train",   action="store_true")
group.add_argument("--texture", action="store_true")
group.add_argument("--bar",     action="store_true")
group.add_argument("--pie",     action="store_true")
group.add_argument("--image",   metavar="PATH", help="Image file path")

args = parser.parse_args()

# ---------------------------------------------------------------------------
# Hardware + display init
# ---------------------------------------------------------------------------

os.environ['SDL_VIDEO_WINDOW_POS'] = f"{X_COORDINATE},{Y_COORDINATE}"
pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.NOFRAME)
pygame.display.set_caption("Haptic Demo")
haptics = HapticController()
clock   = pygame.time.Clock()

# ---------------------------------------------------------------------------
# Mode selection
# ---------------------------------------------------------------------------

from demo.heart_mode   import HeartMode
from demo.train_mode   import TrainMode
from demo.texture_mode import TextureMode
from demo.pie_mode     import PieMode
from demo.bar_mode     import BarMode
from demo.image_mode   import ImageMode

if args.heart:
    start = "heart"
elif args.train:
    start = "train"
elif args.texture:
    start = "texture"
elif args.bar:
    start = "bar"
elif args.pie:
    start = "pie"
else:
    start = "image"

DEMO_MODES = {
    "heart"  : HeartMode(),
    "train"  : TrainMode(),
    "texture": TextureMode(),
    "pie"    : PieMode(),
    "bar"    : BarMode(),
    "image"  : ImageMode(image_path=args.image),
}

mode_keys  = list(DEMO_MODES.keys())
mode_index = mode_keys.index(start)
current_mode = DEMO_MODES[start]

print(f"System Initialized. MAX VOLTAGE: {MAX_VOLTAGE}V  |  Demo: {start.upper()}")

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

running = True
while running:
    current_time = pygame.time.get_ticks()
    finger_pos   = None

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            elif event.key == pygame.K_RETURN:
                mode_index   = (mode_index + 1) % len(mode_keys)
                current_mode = DEMO_MODES[mode_keys[mode_index]]
                print(f"Demo: {mode_keys[mode_index].upper()}")

        if hasattr(current_mode, 'handle_event'):
            current_mode.handle_event(event)

    mouse_x, mouse_y = pygame.mouse.get_pos()
    if pygame.mouse.get_pressed()[0]:
        raw_x = mouse_x / WIDTH
        raw_y = mouse_y / HEIGHT
        if INVERT_X:
            raw_x = 1.0 - raw_x
        if INVERT_Y:
            raw_y = 1.0 - raw_y
        finger_pos = (int(raw_x * WIDTH), int(raw_y * HEIGHT))

    wave, freq, volt = current_mode.update(finger_pos, current_time)
    haptics.update_signal(wave, freq, volt)

    current_mode.draw(screen, finger_pos)
    pygame.display.flip()
    clock.tick(60)

haptics.close()
pygame.quit()
sys.exit()

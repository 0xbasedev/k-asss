"""Load SubSpace BM2 sprite sheets and extract individual frames."""

import struct
from PIL import Image
import numpy as np
from pathlib import Path


SPRITE_DIR = Path(__file__).parent / "assets" / "sprites"

SHIP_NAMES = ["Warbird", "Javelin", "Spider", "Leviathan",
              "Terrier", "Weasel", "Lancaster", "Shark"]
SHIP_SIZE = 36
SHIP_ROTATIONS = 40
SHIPS_PER_ROW = 10

FREQ_COLORS = [
    (0xB0, 0xB0, 0x15),  # freq 0 - yellow
    (0x30, 0x90, 0xD0),  # freq 1 - blue
    (0x20, 0xC0, 0x20),  # freq 2 - green
    (0xD0, 0x40, 0x40),  # freq 3 - red
    (0xC0, 0x60, 0xE0),  # freq 4 - purple
    (0xE0, 0x90, 0x20),  # freq 5 - orange
    (0x20, 0xD0, 0xD0),  # freq 6 - cyan
    (0xD0, 0x70, 0xA0),  # freq 7 - pink
]


def _load_bm2(filename):
    path = SPRITE_DIR / filename
    img = Image.open(str(path))
    return img


def _make_rgba(img):
    if img.mode == "P":
        rgba = img.convert("RGBA")
        pixels = np.array(rgba)
        indexed = np.array(img)
        pixels[indexed == 0] = [0, 0, 0, 0]
        return Image.fromarray(pixels)
    return img.convert("RGBA")


class ShipSprites:
    def __init__(self, filename="ships.bm2"):
        self._sheet = _load_bm2(filename)
        self._cache = {}

    def get_frame(self, ship_type, rotation):
        key = (ship_type, rotation)
        if key in self._cache:
            return self._cache[key]

        rotation = rotation % SHIP_ROTATIONS
        row_in_ship = rotation // SHIPS_PER_ROW
        col = rotation % SHIPS_PER_ROW
        row = ship_type * 4 + row_in_ship

        x = col * SHIP_SIZE
        y = row * SHIP_SIZE
        frame = self._sheet.crop((x, y, x + SHIP_SIZE, y + SHIP_SIZE))
        frame = _make_rgba(frame)
        self._cache[key] = frame
        return frame

    def get_frame_colored(self, ship_type, rotation, freq):
        base = self.get_frame(ship_type, rotation)
        if freq < 0 or freq >= len(FREQ_COLORS):
            return base

        arr = np.array(base).copy()
        mask = arr[:, :, 3] > 0
        if not mask.any():
            return base

        r, g, b = FREQ_COLORS[freq % len(FREQ_COLORS)]
        visible = arr[mask]
        gray = visible[:, :3].mean(axis=1, keepdims=True) / 255.0
        visible[:, 0] = np.clip(visible[:, 0] * 0.4 + r * gray[:, 0] * 0.6, 0, 255)
        visible[:, 1] = np.clip(visible[:, 1] * 0.4 + g * gray[:, 0] * 0.6, 0, 255)
        visible[:, 2] = np.clip(visible[:, 2] * 0.4 + b * gray[:, 0] * 0.6, 0, 255)
        arr[mask] = visible
        return Image.fromarray(arr)


class AnimatedSprite:
    def __init__(self, filename, frame_w, frame_h):
        sheet = _load_bm2(filename)
        self._frames = []
        cols = sheet.size[0] // frame_w
        rows = sheet.size[1] // frame_h
        for row in range(rows):
            for col in range(cols):
                x = col * frame_w
                y = row * frame_h
                frame = sheet.crop((x, y, x + frame_w, y + frame_h))
                frame = _make_rgba(frame)
                self._frames.append(frame)
        self.frame_count = len(self._frames)
        self.frame_w = frame_w
        self.frame_h = frame_h

    def get_frame(self, index):
        return self._frames[index % self.frame_count]


class SpriteManager:
    def __init__(self, sprite_dir=None):
        if sprite_dir:
            global SPRITE_DIR
            SPRITE_DIR = Path(sprite_dir)

        self.ships = ShipSprites()
        self.explode_small = AnimatedSprite("explode0.bm2", 16, 16)
        self.explode_medium = AnimatedSprite("explode1.bm2", 32, 32)
        self.explode_large = AnimatedSprite("explode2.bm2", 80, 80)
        self.bullets = AnimatedSprite("bullets.bm2", 5, 5)
        self.bombs = AnimatedSprite("bombs.bm2", 16, 16)
        self.exhaust = AnimatedSprite("exhaust.bm2", 16, 16)
        self.warp = AnimatedSprite("warp.bm2", 48, 48)
        self.flag = AnimatedSprite("flag.bm2", 16, 16)
        self.shield = AnimatedSprite("shield.bm2", 16, 16)
        self.repel = AnimatedSprite("repel.bm2", 48, 48)

    def get_ship(self, ship_type, rotation, freq=-1):
        if freq >= 0 and freq < len(FREQ_COLORS):
            return self.ships.get_frame_colored(ship_type, rotation, freq)
        return self.ships.get_frame(ship_type, rotation)

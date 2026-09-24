"""Load and render SubSpace LVL maps."""

import struct
from PIL import Image
import numpy as np
from pathlib import Path


MAP_SIZE_TILES = 1024
TILE_SIZE = 16
MAP_SIZE_PIXELS = MAP_SIZE_TILES * TILE_SIZE  # 16384


class MapRenderer:
    def __init__(self, lvl_path, tileset_path=None):
        self.tiles = {}
        self.tileset = None
        self.tileset_rgba = None
        self._tile_cache = {}
        self._load_lvl(lvl_path)
        if self.tileset is None and tileset_path:
            self.tileset = Image.open(str(tileset_path))
            self.tileset_rgba = self._make_tileset_rgba()
        elif self.tileset is None:
            default = Path(__file__).parent / "assets" / "sprites" / "tiles.bm2"
            if default.exists():
                self.tileset = Image.open(str(default))
                self.tileset_rgba = self._make_tileset_rgba()

    def _load_lvl(self, path):
        with open(path, "rb") as f:
            data = f.read()

        # Check for BMP header
        if len(data) < 2 or data[0:2] != b"BM":
            self._load_plain_lvl(data)
            return

        bf_size = struct.unpack_from("<I", data, 2)[0]
        bf_res1 = struct.unpack_from("<H", data, 6)[0]
        bf_offbits = struct.unpack_from("<I", data, 10)[0]

        # Load tileset BMP
        tileset_end = bf_size
        if bf_res1 != 0:
            # Extended format - metadata between BMP and tile data
            tileset_end = bf_res1

        from io import BytesIO
        self.tileset = Image.open(BytesIO(data[:tileset_end]))
        self.tileset_rgba = self._make_tileset_rgba()

        # Skip metadata if present, read tile data after BMP
        if bf_res1 != 0:
            tile_start = bf_res1
            meta_magic = struct.unpack_from("<I", data, tile_start)[0]
            if meta_magic == 0x6C766C65:
                meta_total = struct.unpack_from("<I", data, tile_start + 4)[0]
                tile_start = bf_res1 + meta_total
                # Align to 4 bytes
                tile_start = (tile_start + 3) & ~3
        else:
            tile_start = bf_size

        self._parse_tiles(data[tile_start:])

    def _load_plain_lvl(self, data):
        self._parse_tiles(data)

    def _parse_tiles(self, data):
        pos = 0
        while pos + 4 <= len(data):
            b1, b2, b3, tile_type = struct.unpack_from("<BBBB", data, pos)
            x = b1 | ((b2 & 0x0F) << 8)
            y = (b2 >> 4) | (b3 << 4)
            if tile_type > 0 and x < MAP_SIZE_TILES and y < MAP_SIZE_TILES:
                self.tiles[(x, y)] = tile_type
            pos += 4

    def _make_tileset_rgba(self):
        if self.tileset is None:
            return None
        rgba = self.tileset.convert("RGBA")
        if self.tileset.mode == "P":
            arr = np.array(rgba)
            indexed = np.array(self.tileset)
            arr[indexed == 0] = [0, 0, 0, 255]
            return Image.fromarray(arr)
        return rgba

    def get_tile_image(self, tile_type):
        if tile_type in self._tile_cache:
            return self._tile_cache[tile_type]

        if self.tileset_rgba is None or tile_type < 1 or tile_type > 190:
            img = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 255))
            self._tile_cache[tile_type] = img
            return img

        # Tileset is 19 columns x 10 rows of 16x16 tiles
        idx = tile_type - 1
        col = idx % 19
        row = idx // 19
        x = col * TILE_SIZE
        y = row * TILE_SIZE

        if x + TILE_SIZE > self.tileset_rgba.size[0] or y + TILE_SIZE > self.tileset_rgba.size[1]:
            img = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (0, 0, 0, 255))
        else:
            img = self.tileset_rgba.crop((x, y, x + TILE_SIZE, y + TILE_SIZE))

        self._tile_cache[tile_type] = img
        return img

    def render_viewport(self, cx, cy, vw, vh, scale=1.0):
        """Render the map viewport centered at (cx, cy) in pixel coordinates.

        Returns an RGBA image of size (vw, vh).
        """
        out = Image.new("RGBA", (vw, vh), (0, 0, 0, 255))

        half_w = vw / (2 * scale)
        half_h = vh / (2 * scale)
        left = cx - half_w
        top = cy - half_h

        tile_x_start = max(0, int(left) // TILE_SIZE)
        tile_y_start = max(0, int(top) // TILE_SIZE)
        tile_x_end = min(MAP_SIZE_TILES, int(left + vw / scale) // TILE_SIZE + 2)
        tile_y_end = min(MAP_SIZE_TILES, int(top + vh / scale) // TILE_SIZE + 2)

        for ty in range(tile_y_start, tile_y_end):
            for tx in range(tile_x_start, tile_x_end):
                tile_type = self.tiles.get((tx, ty))
                if tile_type is None:
                    continue

                tile_img = self.get_tile_image(tile_type)

                px = int((tx * TILE_SIZE - left) * scale)
                py = int((ty * TILE_SIZE - top) * scale)

                if scale != 1.0:
                    s = max(1, int(TILE_SIZE * scale))
                    tile_img = tile_img.resize((s, s), Image.NEAREST)

                if -TILE_SIZE * scale < px < vw and -TILE_SIZE * scale < py < vh:
                    out.paste(tile_img, (px, py), tile_img)

        return out

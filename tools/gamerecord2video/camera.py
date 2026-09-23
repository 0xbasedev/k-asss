"""Smooth camera system that tracks player clusters."""

import math


class Camera:
    def __init__(self, view_w=1920, view_h=1080, zoom=2.0):
        self.view_w = view_w
        self.view_h = view_h
        self.zoom = zoom
        self.x = 8192.0
        self.y = 8192.0
        self.target_x = 8192.0
        self.target_y = 8192.0
        self.smoothing = 0.03

    def set_target(self, x, y):
        self.target_x = max(0, min(16383, x))
        self.target_y = max(0, min(16383, y))

    def update(self):
        self.x += (self.target_x - self.x) * self.smoothing
        self.y += (self.target_y - self.y) * self.smoothing

    def snap_to(self, x, y):
        self.x = x
        self.y = y
        self.target_x = x
        self.target_y = y

    def world_to_screen(self, wx, wy):
        sx = (wx - self.x) * self.zoom + self.view_w / 2
        sy = (wy - self.y) * self.zoom + self.view_h / 2
        return int(sx), int(sy)

    def screen_to_world(self, sx, sy):
        wx = (sx - self.view_w / 2) / self.zoom + self.x
        wy = (sy - self.view_h / 2) / self.zoom + self.y
        return wx, wy

    def is_visible(self, wx, wy, margin=50):
        sx, sy = self.world_to_screen(wx, wy)
        return (-margin < sx < self.view_w + margin and
                -margin < sy < self.view_h + margin)

    @property
    def world_viewport(self):
        left = self.x - self.view_w / (2 * self.zoom)
        top = self.y - self.view_h / (2 * self.zoom)
        right = self.x + self.view_w / (2 * self.zoom)
        bottom = self.y + self.view_h / (2 * self.zoom)
        return left, top, right, bottom

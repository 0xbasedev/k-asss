"""Frame renderer — composites map, ships, effects, and HUD."""

import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

from sprites import SpriteManager, SHIP_SIZE, FREQ_COLORS
from simulation import GameSimulation, SHIP_SPEC, Explosion, WeaponShot
from camera import Camera
from gameparser import W_BULLET, W_BOUNCEBULLET, W_BOMB, W_PROXBOMB, W_REPEL, W_BURST, W_THOR, MSG_ARENA


WEAPON_COLORS = {
    W_BULLET: (255, 255, 100),
    W_BOUNCEBULLET: (100, 255, 100),
    W_BOMB: (255, 80, 80),
    W_PROXBOMB: (255, 120, 40),
    W_REPEL: (180, 180, 255),
    W_BURST: (255, 255, 255),
    W_THOR: (255, 60, 200),
}


def _try_load_font(size):
    for name in ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


class FrameRenderer:
    def __init__(self, sim, map_renderer, sprites, camera, width=1920, height=1080):
        self.sim = sim
        self.map_renderer = map_renderer
        self.sprites = sprites
        self.camera = camera
        self.width = width
        self.height = height
        self.font_name = _try_load_font(11)
        self.font_kill = _try_load_font(14)
        self.font_chat = _try_load_font(13)
        self.font_hud = _try_load_font(16)
        self.font_title = _try_load_font(20)

    def render_frame(self, tick):
        frame = self._render_map()
        draw = ImageDraw.Draw(frame)
        self._render_weapons(frame, draw, tick)
        self._render_explosions(frame, tick)
        self._render_ships(frame, draw, tick)
        self._render_kill_feed(frame, draw, tick)
        self._render_chat(frame, draw, tick)
        self._render_hud(frame, draw, tick)
        return frame

    def _render_map(self):
        cx, cy = self.camera.x, self.camera.y
        return self.map_renderer.render_viewport(
            cx, cy, self.width, self.height, scale=self.camera.zoom
        )

    def _render_ships(self, frame, draw, tick):
        active = self.sim.get_active_players()
        for pid, player in active.items():
            pos = self.sim.get_interpolated_pos(pid, tick)
            if not pos:
                continue
            wx, wy, rotation = pos
            if not self.camera.is_visible(wx, wy, margin=100):
                continue

            sx, sy = self.camera.world_to_screen(wx, wy)

            rotation = rotation % 40
            ship_img = self.sprites.get_ship(player.ship, rotation, player.freq)

            scaled_size = int(SHIP_SIZE * self.camera.zoom)
            if scaled_size < 4:
                continue
            ship_img = ship_img.resize((scaled_size, scaled_size), Image.NEAREST)

            paste_x = sx - scaled_size // 2
            paste_y = sy - scaled_size // 2

            if (paste_x + scaled_size > 0 and paste_x < self.width and
                    paste_y + scaled_size > 0 and paste_y < self.height):
                frame.paste(ship_img, (paste_x, paste_y), ship_img)

            # Player name
            name_x = sx
            name_y = sy - scaled_size // 2 - 14
            freq = player.freq
            if freq < len(FREQ_COLORS):
                color = FREQ_COLORS[freq]
            else:
                color = (200, 200, 200)

            text = player.name
            if player.bounty > 0:
                text += f" ({player.bounty})"
            bbox = self.font_name.getbbox(text)
            tw = bbox[2] - bbox[0]
            draw.text((name_x - tw // 2, name_y), text, fill=color, font=self.font_name)

    def _render_weapons(self, frame, draw, tick):
        shots = self.sim.get_active_shots(tick)
        for shot in shots:
            dt = (tick - shot.tick) / 100.0
            angle = 0
            speed = math.sqrt(shot.xspeed ** 2 + shot.yspeed ** 2)
            if speed < 10:
                continue

            # Projectile position
            wx = shot.x + shot.xspeed * dt * 10
            wy = shot.y + shot.yspeed * dt * 10

            if not self.camera.is_visible(wx, wy, margin=20):
                continue
            sx, sy = self.camera.world_to_screen(wx, wy)

            color = WEAPON_COLORS.get(shot.weapon_type, (255, 255, 100))

            if shot.weapon_type in (W_BOMB, W_PROXBOMB, W_THOR):
                r = int(4 * self.camera.zoom)
                draw.ellipse([sx - r, sy - r, sx + r, sy + r], fill=color)
            elif shot.weapon_type == W_REPEL:
                progress = min(1.0, dt * 3)
                r = int(progress * 60 * self.camera.zoom)
                alpha = int(255 * (1 - progress))
                draw.ellipse([sx - r, sy - r, sx + r, sy + r],
                             outline=(*color, alpha), width=2)
            else:
                r = max(1, int(2 * self.camera.zoom))
                draw.ellipse([sx - r, sy - r, sx + r, sy + r], fill=color)

    def _render_explosions(self, frame, tick):
        explosions = self.sim.get_active_explosions(tick)
        for exp in explosions:
            if not self.camera.is_visible(exp.x, exp.y, margin=100):
                continue
            sx, sy = self.camera.world_to_screen(exp.x, exp.y)

            progress = (tick - exp.tick) / exp.duration_ticks
            if progress < 0 or progress >= 1:
                continue

            if exp.size == "large":
                sprite_set = self.sprites.explode_large
            elif exp.size == "medium":
                sprite_set = self.sprites.explode_medium
            else:
                sprite_set = self.sprites.explode_small

            frame_idx = int(progress * sprite_set.frame_count)
            exp_img = sprite_set.get_frame(frame_idx)

            scale = self.camera.zoom
            if exp.size == "large":
                scale *= 2.0
            elif exp.size == "medium":
                scale *= 1.5

            sw = int(exp_img.size[0] * scale)
            sh = int(exp_img.size[1] * scale)
            if sw < 2 or sh < 2:
                continue

            exp_img = exp_img.resize((sw, sh), Image.NEAREST)
            px = sx - sw // 2
            py = sy - sh // 2

            if px + sw > 0 and px < self.width and py + sh > 0 and py < self.height:
                frame.paste(exp_img, (px, py), exp_img)

    def _render_kill_feed(self, frame, draw, tick):
        kills = self.sim.get_recent_kills(tick, window=500)
        kills = kills[-8:]  # show max 8

        x = self.width - 10
        y = 60

        for kill in reversed(kills):
            age = tick - kill.tick
            alpha = max(0, min(255, 255 - int(age * 255 / 500)))

            killer_freq = -1
            killed_freq = -1
            kp = self.sim.players.get(kill.killer_pid)
            dp = self.sim.players.get(kill.killed_pid)
            if kp:
                killer_freq = kp.freq
            if dp:
                killed_freq = dp.freq

            killer_color = FREQ_COLORS[killer_freq % len(FREQ_COLORS)] if 0 <= killer_freq < len(FREQ_COLORS) else (200, 200, 200)
            killed_color = FREQ_COLORS[killed_freq % len(FREQ_COLORS)] if 0 <= killed_freq < len(FREQ_COLORS) else (200, 200, 200)

            text = f"{kill.killer_name} killed {kill.killed_name}"
            if kill.pts:
                text += f" (+{kill.pts})"

            bbox = self.font_kill.getbbox(text)
            tw = bbox[2] - bbox[0]

            # Background
            draw.rectangle([x - tw - 10, y - 2, x + 2, y + 18], fill=(0, 0, 0, 128))
            draw.text((x - tw - 5, y), text, fill=(220, 220, 220), font=self.font_kill)
            y += 22

    def _render_chat(self, frame, draw, tick):
        chats = self.sim.get_recent_chats(tick, window=400)
        chats = chats[-6:]

        x = 10
        y = self.height - 30

        for chat in reversed(chats):
            age = tick - chat.tick
            alpha = max(100, 255 - int(age * 200 / 400))

            if chat.msg_type == MSG_ARENA:
                color = (0, 200, 0)
                text = chat.msg
            else:
                color = (230, 230, 230)
                text = f"{chat.name}: {chat.msg}" if chat.name else chat.msg

            text = text[:100]

            draw.rectangle([x - 2, y - 2, x + 800, y + 16], fill=(0, 0, 0, 100))
            draw.text((x, y), text, fill=color, font=self.font_chat)
            y -= 20

    def _render_hud(self, frame, draw, tick):
        active = self.sim.get_active_players()
        player_count = len(active)
        elapsed = tick / 100.0
        total = self.sim.recording.duration_seconds

        minutes = int(elapsed) // 60
        seconds = int(elapsed) % 60
        total_min = int(total) // 60
        total_sec = int(total) % 60

        time_text = f"{minutes:02d}:{seconds:02d} / {total_min:02d}:{total_sec:02d}"
        draw.rectangle([5, 5, 220, 30], fill=(0, 0, 0, 160))
        draw.text((10, 8), time_text, fill=(255, 255, 255), font=self.font_hud)

        info_text = f"Players: {player_count}"
        draw.rectangle([5, 33, 160, 55], fill=(0, 0, 0, 160))
        draw.text((10, 35), info_text, fill=(200, 200, 200), font=self.font_name)

        # Arena name
        arena = self.sim.recording.header.arenaname
        if arena:
            bbox = self.font_hud.getbbox(arena)
            tw = bbox[2] - bbox[0]
            ax = self.width // 2 - tw // 2
            draw.rectangle([ax - 5, 5, ax + tw + 5, 30], fill=(0, 0, 0, 160))
            draw.text((ax, 8), arena, fill=(200, 200, 200), font=self.font_hud)

        # Progress bar
        bar_y = self.height - 6
        bar_w = self.width - 20
        progress = min(1.0, elapsed / max(1, total))
        draw.rectangle([10, bar_y, 10 + bar_w, bar_y + 4], fill=(40, 40, 40))
        draw.rectangle([10, bar_y, 10 + int(bar_w * progress), bar_y + 4], fill=(100, 180, 255))

        # Freq scoreboard
        freq_kills = {}
        for kill in self.sim.kills:
            if kill.tick <= tick:
                kp = self.sim.players.get(kill.killer_pid)
                if kp:
                    freq_kills[kp.freq] = freq_kills.get(kp.freq, 0) + 1

        if freq_kills:
            sorted_freqs = sorted(freq_kills.items(), key=lambda x: -x[1])[:4]
            sb_x = 10
            sb_y = 60
            draw.rectangle([sb_x - 2, sb_y - 2, sb_x + 120, sb_y + len(sorted_freqs) * 18 + 2],
                           fill=(0, 0, 0, 140))
            for freq, kills in sorted_freqs:
                color = FREQ_COLORS[freq % len(FREQ_COLORS)] if freq < len(FREQ_COLORS) else (200, 200, 200)
                draw.text((sb_x + 2, sb_y), f"Freq {freq}: {kills} kills",
                          fill=color, font=self.font_name)
                sb_y += 18

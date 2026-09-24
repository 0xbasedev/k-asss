"""Game state simulation from recorded events with position interpolation."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math

from gameparser import (
    EventEnter, EventLeave, EventShipChange, EventFreqChange,
    EventKill, EventChat, EventPosition, SHIP_SPEC
)


@dataclass
class PlayerState:
    pid: int
    name: str
    squad: str
    ship: int
    freq: int
    x: float = 8192.0
    y: float = 8192.0
    xspeed: float = 0.0
    yspeed: float = 0.0
    rotation: int = 0
    bounty: int = 0
    energy: int = 1000
    status: int = 0
    alive: bool = True
    last_update_tick: int = 0
    prev_x: float = 8192.0
    prev_y: float = 8192.0
    prev_rotation: int = 0
    prev_tick: int = 0
    weapon_type: int = 0
    weapon_level: int = 0
    firing_tick: int = -1000


@dataclass
class KillEvent:
    tick: int
    killer_name: str
    killed_name: str
    killer_pid: int
    killed_pid: int
    pts: int
    flags: int


@dataclass
class ChatMessage:
    tick: int
    name: str
    msg: str
    msg_type: int


@dataclass
class Explosion:
    tick: int
    x: float
    y: float
    size: str  # "small", "medium", "large"
    duration_ticks: int = 60


@dataclass
class WeaponShot:
    tick: int
    pid: int
    x: float
    y: float
    xspeed: float
    yspeed: float
    weapon_type: int
    weapon_level: int
    duration_ticks: int = 100


class GameSimulation:
    def __init__(self, recording):
        self.recording = recording
        self.players: Dict[int, PlayerState] = {}
        self.kills: List[KillEvent] = []
        self.chats: List[ChatMessage] = []
        self.explosions: List[Explosion] = []
        self.weapon_shots: List[WeaponShot] = []
        self._event_idx = 0
        self._current_tick = 0

    def advance_to(self, target_tick):
        while self._event_idx < len(self.recording.events):
            ev = self.recording.events[self._event_idx]
            if ev.time > target_tick:
                break
            self._process_event(ev)
            self._event_idx += 1
        self._current_tick = target_tick

    def _process_event(self, ev):
        if isinstance(ev, EventEnter):
            self.players[ev.pid] = PlayerState(
                pid=ev.pid, name=ev.name, squad=ev.squad,
                ship=ev.ship, freq=ev.freq,
                last_update_tick=ev.time, prev_tick=ev.time,
            )

        elif isinstance(ev, EventLeave):
            self.players.pop(ev.pid, None)

        elif isinstance(ev, EventShipChange):
            p = self.players.get(ev.pid)
            if p:
                p.ship = ev.newship
                p.freq = ev.newfreq

        elif isinstance(ev, EventFreqChange):
            p = self.players.get(ev.pid)
            if p:
                p.freq = ev.newfreq

        elif isinstance(ev, EventPosition):
            p = self.players.get(ev.pid)
            if p:
                if not p.alive:
                    p.alive = True
                p.prev_x = p.x
                p.prev_y = p.y
                p.prev_rotation = p.rotation
                p.prev_tick = p.last_update_tick
                p.x = float(ev.x)
                p.y = float(ev.y)
                p.xspeed = float(ev.xspeed)
                p.yspeed = float(ev.yspeed)
                p.rotation = ev.rotation
                p.bounty = ev.bounty
                p.energy = ev.energy
                p.status = ev.status
                p.last_update_tick = ev.time

                if ev.weapon.type != 0:
                    p.weapon_type = ev.weapon.type
                    p.weapon_level = ev.weapon.level
                    p.firing_tick = ev.time
                    self.weapon_shots.append(WeaponShot(
                        tick=ev.time, pid=ev.pid,
                        x=p.x, y=p.y,
                        xspeed=p.xspeed, yspeed=p.yspeed,
                        weapon_type=ev.weapon.type,
                        weapon_level=ev.weapon.level,
                    ))

        elif isinstance(ev, EventKill):
            killer = self.players.get(ev.killer)
            killed = self.players.get(ev.killed)
            killer_name = killer.name if killer else f"pid:{ev.killer}"
            killed_name = killed.name if killed else f"pid:{ev.killed}"

            self.kills.append(KillEvent(
                tick=ev.time,
                killer_name=killer_name, killed_name=killed_name,
                killer_pid=ev.killer, killed_pid=ev.killed,
                pts=ev.pts, flags=ev.flags,
            ))

            if killed:
                self.explosions.append(Explosion(
                    tick=ev.time, x=killed.x, y=killed.y,
                    size="large", duration_ticks=80,
                ))
                killed.alive = False

        elif isinstance(ev, EventChat):
            p = self.players.get(ev.pid)
            name = p.name if p else ""
            self.chats.append(ChatMessage(
                tick=ev.time, name=name,
                msg=ev.msg, msg_type=ev.msg_type,
            ))

    def get_interpolated_pos(self, pid, tick) -> Optional[Tuple[float, float, int]]:
        p = self.players.get(pid)
        if not p:
            return None

        dt = tick - p.last_update_tick
        if dt <= 0:
            return p.x, p.y, p.rotation

        # Extrapolate from last known position using velocity
        # Speed is in pixels per 10ms (SubSpace units)
        x = p.x + p.xspeed * dt / 1000.0
        y = p.y + p.yspeed * dt / 1000.0
        return x, y, p.rotation

    def get_active_players(self):
        return {pid: p for pid, p in self.players.items()
                if p.ship != SHIP_SPEC and p.alive}

    def get_active_explosions(self, tick):
        return [e for e in self.explosions
                if e.tick <= tick < e.tick + e.duration_ticks]

    def get_active_shots(self, tick):
        return [s for s in self.weapon_shots
                if s.tick <= tick < s.tick + s.duration_ticks]

    def get_recent_kills(self, tick, window=500):
        return [k for k in self.kills if tick - window <= k.tick <= tick]

    def get_recent_chats(self, tick, window=500):
        return [c for c in self.chats if tick - window <= c.tick <= tick]

    def get_player_cluster_center(self, tick) -> Tuple[float, float]:
        active = self.get_active_players()
        if not active:
            return 8192.0, 8192.0

        positions = []
        for pid, p in active.items():
            pos = self.get_interpolated_pos(pid, tick)
            if pos:
                positions.append((pos[0], pos[1]))

        if not positions:
            return 8192.0, 8192.0

        if len(positions) == 1:
            return positions[0]

        # Find the densest cluster using a simple approach:
        # score each player by how many others are nearby
        best_score = -1
        best_center = positions[0]
        radius = 2000  # pixel radius to consider "nearby"

        for i, (px, py) in enumerate(positions):
            score = 0
            for j, (qx, qy) in enumerate(positions):
                if i != j:
                    dist = math.sqrt((px - qx) ** 2 + (py - qy) ** 2)
                    if dist < radius:
                        score += 1
                    elif dist < radius * 2:
                        score += 0.5
            if score > best_score:
                best_score = score
                best_center = (px, py)

        # Average positions of players near the best center
        nearby = [(x, y) for x, y in positions
                  if math.sqrt((x - best_center[0]) ** 2 + (y - best_center[1]) ** 2) < radius]

        if nearby:
            cx = sum(x for x, y in nearby) / len(nearby)
            cy = sum(y for x, y in nearby) / len(nearby)
            return cx, cy

        return best_center

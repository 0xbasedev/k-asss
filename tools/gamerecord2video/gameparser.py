"""Parse SubSpace game recording files (.game format)."""

import struct
import zlib
import io
from dataclasses import dataclass, field
from typing import List, Optional


EV_NULL = 0
EV_ENTER = 1
EV_LEAVE = 2
EV_SHIPCHANGE = 3
EV_FREQCHANGE = 4
EV_KILL = 5
EV_CHAT = 6
EV_POS = 7
EV_PACKET = 8

SHIP_SPEC = 8

MSG_ARENA = 0
MSG_PUB = 2
MSG_FREQ = 4

W_NULL = 0
W_BULLET = 1
W_BOUNCEBULLET = 2
W_BOMB = 3
W_PROXBOMB = 4
W_REPEL = 5
W_DECOY = 6
W_BURST = 7
W_THOR = 8


@dataclass
class FileHeader:
    magic: str
    version: int
    offset: int
    events: int
    endtime: int
    maxpid: int
    specfreq: int
    recorded: int
    mapchecksum: int
    recorder: str
    arenaname: str


@dataclass
class EventEnter:
    time: int
    pid: int
    name: str
    squad: str
    ship: int
    freq: int


@dataclass
class EventLeave:
    time: int
    pid: int


@dataclass
class EventShipChange:
    time: int
    pid: int
    newship: int
    newfreq: int


@dataclass
class EventFreqChange:
    time: int
    pid: int
    newfreq: int


@dataclass
class Weapons:
    type: int = 0
    level: int = 0
    shrapbouncing: int = 0
    shraplevel: int = 0
    shrap: int = 0
    alternate: int = 0


@dataclass
class EventPosition:
    time: int
    pid: int
    rotation: int
    x: int
    y: int
    xspeed: int
    yspeed: int
    bounty: int
    energy: int
    status: int
    weapon: Weapons = field(default_factory=Weapons)


@dataclass
class EventKill:
    time: int
    killer: int
    killed: int
    pts: int
    flags: int


@dataclass
class EventChat:
    time: int
    pid: int
    msg_type: int
    sound: int
    msg: str


def parse_weapons(data):
    if len(data) < 2:
        return Weapons()
    val = struct.unpack_from("<H", data, 0)[0]
    return Weapons(
        type=val & 0x1F,
        level=(val >> 5) & 0x03,
        shrapbouncing=(val >> 7) & 0x01,
        shraplevel=(val >> 8) & 0x03,
        shrap=(val >> 10) & 0x1F,
        alternate=(val >> 15) & 0x01,
    )


def _is_valid_name(data):
    try:
        s = data.split(b"\x00")[0].decode("ascii")
        return all(32 <= ord(c) < 127 for c in s) if s else True
    except (UnicodeDecodeError, ValueError):
        return False


def parse_header(f) -> FileHeader:
    raw = f.read(128)
    if len(raw) < 88:
        raise ValueError(f"File too short for header: {len(raw)} bytes")

    magic = raw[:8].rstrip(b"\x00").decode("ascii", errors="replace")
    if magic != "asssgame":
        raise ValueError(f"Bad magic: {magic!r}")

    version, offset, events, endtime, maxpid, specfreq = struct.unpack_from("<6I", raw, 8)

    if version != 2:
        raise ValueError(f"Unsupported version: {version}")

    # Detect 32-bit vs 64-bit time_t layout.
    # With #pragma pack(1): 32-bit time_t gives sizeof(header)=88,
    # 64-bit gives sizeof(header)=92. The offset field equals
    # sizeof(header) + optional comments length.
    # Try 32-bit first, validate by checking if recorder/arenaname are ASCII.
    if _is_valid_name(raw[40:64]) and _is_valid_name(raw[64:88]):
        recorded = struct.unpack_from("<I", raw, 32)[0]
        mapchecksum = struct.unpack_from("<I", raw, 36)[0]
        recorder = raw[40:64].split(b"\x00")[0].decode("ascii", errors="replace")
        arenaname = raw[64:88].split(b"\x00")[0].decode("ascii", errors="replace")
    elif _is_valid_name(raw[44:68]) and _is_valid_name(raw[68:92]):
        recorded = struct.unpack_from("<Q", raw, 32)[0]
        mapchecksum = struct.unpack_from("<I", raw, 40)[0]
        recorder = raw[44:68].split(b"\x00")[0].decode("ascii", errors="replace")
        arenaname = raw[68:92].split(b"\x00")[0].decode("ascii", errors="replace")
    else:
        recorded = struct.unpack_from("<I", raw, 32)[0]
        mapchecksum = struct.unpack_from("<I", raw, 36)[0]
        recorder = raw[40:64].split(b"\x00")[0].decode("ascii", errors="replace")
        arenaname = raw[64:88].split(b"\x00")[0].decode("ascii", errors="replace")

    return FileHeader(
        magic=magic, version=version, offset=offset,
        events=events, endtime=endtime, maxpid=maxpid,
        specfreq=specfreq, recorded=recorded, mapchecksum=mapchecksum,
        recorder=recorder, arenaname=arenaname,
    )


def _read_event(gz_data, pos):
    if pos + 6 > len(gz_data):
        return None, pos

    tm, ev_type = struct.unpack_from("<Ih", gz_data, pos)
    pos += 6

    if ev_type == EV_ENTER:
        if pos + 54 > len(gz_data):
            return None, pos
        pid = struct.unpack_from("<h", gz_data, pos)[0]
        name = gz_data[pos + 2:pos + 26].split(b"\x00")[0].decode("ascii", errors="replace")
        squad = gz_data[pos + 26:pos + 50].split(b"\x00")[0].decode("ascii", errors="replace")
        ship, freq = struct.unpack_from("<HH", gz_data, pos + 50)
        pos += 54
        return EventEnter(time=tm, pid=pid, name=name, squad=squad, ship=ship, freq=freq), pos

    elif ev_type == EV_LEAVE:
        if pos + 2 > len(gz_data):
            return None, pos
        pid = struct.unpack_from("<h", gz_data, pos)[0]
        pos += 2
        return EventLeave(time=tm, pid=pid), pos

    elif ev_type == EV_SHIPCHANGE:
        if pos + 6 > len(gz_data):
            return None, pos
        pid, newship, newfreq = struct.unpack_from("<hhh", gz_data, pos)
        pos += 6
        return EventShipChange(time=tm, pid=pid, newship=newship, newfreq=newfreq), pos

    elif ev_type == EV_FREQCHANGE:
        if pos + 4 > len(gz_data):
            return None, pos
        pid, newfreq = struct.unpack_from("<hh", gz_data, pos)
        pos += 4
        return EventFreqChange(time=tm, pid=pid, newfreq=newfreq), pos

    elif ev_type == EV_KILL:
        if pos + 8 > len(gz_data):
            return None, pos
        killer, killed, pts, flags = struct.unpack_from("<hhhh", gz_data, pos)
        pos += 8
        return EventKill(time=tm, killer=killer, killed=killed, pts=pts, flags=flags), pos

    elif ev_type == EV_CHAT:
        if pos + 6 > len(gz_data):
            return None, pos
        pid = struct.unpack_from("<h", gz_data, pos)[0]
        msg_type = gz_data[pos + 2]
        sound = gz_data[pos + 3]
        msg_len = struct.unpack_from("<H", gz_data, pos + 4)[0]
        pos += 6
        if msg_len < 1 or msg_len > 512 or pos + msg_len > len(gz_data):
            return None, pos
        msg = gz_data[pos:pos + msg_len].split(b"\x00")[0].decode("ascii", errors="replace")
        pos += msg_len
        return EventChat(time=tm, pid=pid, msg_type=msg_type, sound=sound, msg=msg), pos

    elif ev_type == EV_POS:
        # Special: header.type (ev_type) is EV_POS
        # The first byte of the pos data is the total length of the pos struct
        # header.tm holds the pid repurposed into the pos.time field
        # Actually, looking at the C code more carefully:
        #   ev->pos.type = len;  (the packet length stored in pos.type)
        #   ev->pos.time = p->pid;  (pid stored in pos.time)
        # The data written is: event_header(6) + C2SPosition(variable)
        # On read: first read 1 byte to get pos.type (=length), then read length-1 more bytes
        if pos + 1 > len(gz_data):
            return None, pos
        pkt_len = gz_data[pos]
        if pkt_len not in (22, 24, 32):
            return None, pos + pkt_len
        if pos + pkt_len > len(gz_data):
            return None, pos
        # C2SPosition layout (packed):
        # type(u8) rotation(i8) time(u32) xspeed(i16) y(i16) checksum(u8) status(u8) x(i16) yspeed(i16) bounty(u16) energy(i16) weapon(2) extra(10)
        # But type=pkt_len, time=pid
        pos_data = gz_data[pos:pos + pkt_len]
        pos += pkt_len

        ptype = pos_data[0]  # actually pkt_len
        rotation = struct.unpack_from("<b", pos_data, 1)[0]
        pid = struct.unpack_from("<I", pos_data, 2)[0]  # time field holds pid
        xspeed = struct.unpack_from("<h", pos_data, 6)[0]
        y = struct.unpack_from("<h", pos_data, 8)[0]
        checksum = pos_data[10]
        status = pos_data[11]
        x = struct.unpack_from("<h", pos_data, 12)[0]
        yspeed = struct.unpack_from("<h", pos_data, 14)[0]
        bounty = struct.unpack_from("<H", pos_data, 16)[0]
        energy = struct.unpack_from("<h", pos_data, 18)[0]

        weapon = Weapons()
        if pkt_len >= 22:
            weapon = parse_weapons(pos_data[20:22])

        return EventPosition(
            time=tm, pid=pid, rotation=rotation,
            x=x, y=y, xspeed=xspeed, yspeed=yspeed,
            bounty=bounty, energy=energy, status=status,
            weapon=weapon,
        ), pos

    elif ev_type == EV_PACKET:
        if pos + 2 > len(gz_data):
            return None, pos
        pkt_len = struct.unpack_from("<h", gz_data, pos)[0]
        pos += 2
        actual_len = abs(pkt_len)
        if actual_len < 1 or actual_len > 4000 or pos + actual_len > len(gz_data):
            return None, pos
        pos += actual_len
        return None, pos  # skip generic packets for video rendering

    else:
        return None, pos


class GameRecording:
    def __init__(self, filepath):
        self.filepath = filepath
        self.header = None
        self.events = []
        self._parse()

    def _parse(self):
        with open(self.filepath, "rb") as f:
            self.header = parse_header(f)
            f.seek(self.header.offset)
            compressed = f.read()

        decompressor = zlib.decompressobj(wbits=15 + 32)
        try:
            decompressed = decompressor.decompress(compressed)
        except zlib.error:
            decompressor = zlib.decompressobj(wbits=-15)
            decompressed = decompressor.decompress(compressed)

        pos = 0
        while pos < len(decompressed):
            event, pos = _read_event(decompressed, pos)
            if event is not None:
                self.events.append(event)
            elif pos >= len(decompressed):
                break

    @property
    def duration_ticks(self):
        return self.header.endtime

    @property
    def duration_seconds(self):
        return self.header.endtime / 100.0

    def events_in_range(self, start_tick, end_tick):
        return [e for e in self.events if start_tick <= e.time < end_tick]

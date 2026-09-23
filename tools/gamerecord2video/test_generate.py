#!/usr/bin/env python3
"""Generate a synthetic game recording for testing the converter."""

import struct
import zlib
import math
import os


def write_event(buf, tm, ev_type, payload):
    buf += struct.pack("<Ih", tm, ev_type)
    buf += payload
    return buf


def make_enter(pid, name, squad, ship, freq):
    return struct.pack("<h", pid) + \
           name.encode("ascii").ljust(24, b"\x00") + \
           squad.encode("ascii").ljust(24, b"\x00") + \
           struct.pack("<HH", ship, freq)


def make_leave(pid):
    return struct.pack("<h", pid)


def make_kill(killer, killed, pts, flags):
    return struct.pack("<hhhh", killer, killed, pts, flags)


def make_pos(pid, rotation, x, y, xspeed, yspeed, bounty, energy, weapon_type=0, weapon_level=0):
    # C2SPosition: type(u8) rotation(i8) time(u32) xspeed(i16) y(i16)
    #              checksum(u8) status(u8) x(i16) yspeed(i16) bounty(u16) energy(i16) weapon(u16)
    pkt_len = 22
    weapon_bits = (weapon_type & 0x1F) | ((weapon_level & 0x03) << 5)
    pos_data = struct.pack("<bBI", pkt_len, rotation % 256, pid)
    pos_data += struct.pack("<hh", xspeed, y)
    pos_data += struct.pack("<BB", 0, 0)  # checksum, status
    pos_data += struct.pack("<hh", x, yspeed)
    pos_data += struct.pack("<Hh", bounty, energy)
    pos_data += struct.pack("<H", weapon_bits)
    return pos_data


def make_chat(pid, msg_type, sound, msg):
    msg_bytes = msg.encode("ascii") + b"\x00"
    return struct.pack("<hBBH", pid, msg_type, sound, len(msg_bytes)) + msg_bytes


def generate_test_recording(output_path):
    events = bytearray()
    duration = 3000  # 30 seconds at 100 ticks/sec

    # Enter 6 players on 2 teams
    names = ["TestPilot1", "StarFox", "NoobSlayer", "DarkWing", "BlueHawk", "RedBaron"]
    ships = [0, 1, 2, 3, 0, 1]  # WB, JV, SP, LV, WB, JV
    freqs = [0, 0, 0, 1, 1, 1]

    for i, (name, ship, freq) in enumerate(zip(names, ships, freqs)):
        events = write_event(events, 0, 1, make_enter(i, name, "", ship, freq))

    # Chat
    events = write_event(events, 50, 6, make_chat(-1, 0, 0, "Game starting!"))

    # Scripted kills and chats at specific ticks
    scripted = {
        1000: [("kill", 0, 4, 15, 0)],
        1500: [("chat", 0, 2, 0, "Got em!")],
        2000: [("kill", 3, 1, 20, 1)],
        2500: [("kill", 5, 2, 10, 0)],
    }

    # Position updates - make players fly around in interesting patterns
    for tick in range(0, duration, 10):
        # Insert scripted events at correct timestamps
        for st in sorted(scripted.keys()):
            if tick <= st < tick + 10:
                for ev in scripted[st]:
                    if ev[0] == "kill":
                        events = write_event(events, st, 5, make_kill(ev[1], ev[2], ev[3], ev[4]))
                    elif ev[0] == "chat":
                        events = write_event(events, st, 6, make_chat(ev[1], ev[2], ev[3], ev[4]))

        for pid in range(6):
            t = tick / 100.0
            if pid < 3:
                cx, cy = 8100, 8100
                angle = t * 0.5 + pid * 2.094
                radius = 200 + pid * 50
            else:
                cx, cy = 8300, 8200
                angle = -t * 0.4 + (pid - 3) * 2.094
                radius = 180 + (pid - 3) * 60

            x = int(cx + math.cos(angle) * radius)
            y = int(cy + math.sin(angle) * radius)
            rotation = int((-angle * 40 / (2 * math.pi)) + 10) % 40
            xspeed = int(-math.sin(angle) * 300)
            yspeed = int(math.cos(angle) * 300)

            weapon = 0
            wlevel = 0
            if tick % 200 == 0 and pid in (0, 3):
                weapon = 1  # bullet
                wlevel = 1

            events = write_event(events, tick, 7,
                                 make_pos(pid, rotation, x, y, xspeed, yspeed, pid * 5, 900, weapon, wlevel))

    # Compress events
    compressed = zlib.compress(bytes(events), 9)

    # Build file header
    header_size = 120  # sizeof(file_header) with padding
    header = b"asssgame"
    header += struct.pack("<I", 2)  # version
    header += struct.pack("<I", header_size)  # offset to events
    header += struct.pack("<I", 0)  # events count (approximate)
    header += struct.pack("<I", duration)  # endtime
    header += struct.pack("<I", 5)  # maxpid
    header += struct.pack("<I", 8025)  # specfreq
    header += struct.pack("<I", 0)  # recorded timestamp
    header += struct.pack("<I", 0)  # mapchecksum
    header += b"TestRecorder\x00".ljust(24, b"\x00")  # recorder
    header += b"TestArena\x00".ljust(24, b"\x00")  # arenaname

    # Pad to header_size
    header = header.ljust(header_size, b"\x00")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(header)
        f.write(compressed)

    print(f"Generated test recording: {output_path}")
    print(f"  Duration: {duration / 100:.1f}s")
    print(f"  Header: {len(header)} bytes")
    print(f"  Events compressed: {len(compressed)} bytes")


if __name__ == "__main__":
    generate_test_recording("/home/user/k-asss/tools/gamerecord2video/test.game")

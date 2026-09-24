#!/usr/bin/env python3
"""Convert SubSpace game recordings (.game) to MP4 video.

Usage:
    python convert.py recording.game -m map.lvl -o output.mp4
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

from gameparser import GameRecording
from maprender import MapRenderer
from sprites import SpriteManager
from simulation import GameSimulation
from camera import Camera
from renderer import FrameRenderer


def create_ffmpeg_pipe(output_path, width, height, fps):
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{width}x{height}",
        "-pix_fmt", "rgb24",
        "-r", str(fps),
        "-i", "-",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]
    return subprocess.Popen(
        cmd, stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def main():
    parser = argparse.ArgumentParser(description="Convert SubSpace game recordings to MP4 video")
    parser.add_argument("recording", help="Path to .game recording file")
    parser.add_argument("-m", "--map", required=True, help="Path to .lvl map file")
    parser.add_argument("-o", "--output", default="output.mp4", help="Output MP4 path")
    parser.add_argument("-W", "--width", type=int, default=1920, help="Video width")
    parser.add_argument("-H", "--height", type=int, default=1080, help="Video height")
    parser.add_argument("--fps", type=int, default=30, help="Frames per second")
    parser.add_argument("--zoom", type=float, default=2.0, help="Camera zoom level")
    parser.add_argument("--start", type=float, default=0, help="Start time in seconds")
    parser.add_argument("--end", type=float, default=0, help="End time in seconds (0 = full)")
    parser.add_argument("--sprites", help="Path to sprites directory")
    parser.add_argument("--camera-smoothing", type=float, default=0.03, help="Camera smoothing (0-1)")
    args = parser.parse_args()

    print(f"Loading recording: {args.recording}")
    recording = GameRecording(args.recording)
    print(f"  Arena: {recording.header.arenaname}")
    print(f"  Recorded by: {recording.header.recorder}")
    print(f"  Duration: {recording.duration_seconds:.1f}s")
    print(f"  Events: {len(recording.events)}")

    print(f"Loading map: {args.map}")
    map_renderer = MapRenderer(args.map)
    print(f"  Tiles loaded: {len(map_renderer.tiles)}")

    print("Loading sprites...")
    sprites = SpriteManager(args.sprites) if args.sprites else SpriteManager()

    sim = GameSimulation(recording)
    camera = Camera(args.width, args.height, args.zoom)
    camera.smoothing = args.camera_smoothing

    renderer = FrameRenderer(sim, map_renderer, sprites, camera, args.width, args.height)

    start_tick = int(args.start * 100)
    end_tick = int(args.end * 100) if args.end > 0 else recording.duration_ticks
    ticks_per_frame = 100.0 / args.fps
    total_frames = int((end_tick - start_tick) / ticks_per_frame)

    print(f"\nRendering {total_frames} frames at {args.fps}fps ({args.width}x{args.height})")
    print(f"  Zoom: {args.zoom}x, Camera smoothing: {args.camera_smoothing}")
    print(f"  Output: {args.output}")

    # Pre-simulate to start tick
    if start_tick > 0:
        print(f"  Fast-forwarding to {args.start:.1f}s...")
        sim.advance_to(start_tick)
        cluster = sim.get_player_cluster_center(start_tick)
        camera.snap_to(*cluster)

    ffmpeg = create_ffmpeg_pipe(args.output, args.width, args.height, args.fps)

    t0 = time.time()
    last_report = t0

    try:
        for frame_num in range(total_frames):
            tick = start_tick + int(frame_num * ticks_per_frame)

            sim.advance_to(tick)

            cluster = sim.get_player_cluster_center(tick)
            camera.set_target(*cluster)
            camera.update()

            frame = renderer.render_frame(tick)
            rgb = frame.convert("RGB")
            ffmpeg.stdin.write(rgb.tobytes())

            now = time.time()
            if now - last_report >= 2.0:
                elapsed = now - t0
                fps_actual = (frame_num + 1) / elapsed if elapsed > 0 else 0
                pct = (frame_num + 1) / total_frames * 100
                eta = (total_frames - frame_num - 1) / fps_actual if fps_actual > 0 else 0
                print(f"  [{pct:5.1f}%] Frame {frame_num + 1}/{total_frames} "
                      f"({fps_actual:.1f} fps, ETA {eta:.0f}s)")
                last_report = now

    except KeyboardInterrupt:
        print("\nInterrupted!")
    finally:
        try:
            ffmpeg.stdin.close()
        except (BrokenPipeError, OSError, ValueError):
            pass
        ffmpeg.wait()

    elapsed = time.time() - t0
    print(f"\nDone! Rendered {total_frames} frames in {elapsed:.1f}s "
          f"({total_frames / elapsed:.1f} fps)")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()

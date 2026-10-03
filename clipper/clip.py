#!/usr/bin/env python3
"""Cut a long video into short clips (YouTube Shorts) using ffmpeg.

Two modes:
  auto    split the whole video into equal clips of --length seconds
  manual  cut the clips listed in a timestamps file

Examples:
  python3 clipper/clip.py auto  video.mp4 --length 58
  python3 clipper/clip.py manual video.mp4 --timestamps clips.txt
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

SHORTS_W, SHORTS_H = 1080, 1920
MAX_SHORT_SECONDS = 180


def require_ffmpeg():
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            sys.exit(f"Error: '{tool}' was not found. Install ffmpeg first.")


def video_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def parse_time(text):
    """Accept '75', '75.5', '1:15' or '0:01:15'."""
    parts = text.strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError(f"bad time: {text!r}")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


def slugify(text):
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip()
    return re.sub(r"[\s-]+", "_", text)[:60]


def read_timestamps(path):
    """Each line: START END [title]. Blank lines and '#' comments are ignored."""
    clips = []
    for n, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split(maxsplit=2)
        if len(fields) < 2:
            sys.exit(f"{path}:{n}: expected 'START END [title]'")
        start, end = parse_time(fields[0]), parse_time(fields[1])
        if end <= start:
            sys.exit(f"{path}:{n}: END must be after START")
        title = fields[2] if len(fields) > 2 else ""
        clips.append((start, end, title))
    return clips


def auto_clips(duration, length, min_length):
    clips = []
    start = 0.0
    while start < duration:
        end = min(start + length, duration)
        if end - start >= min_length:
            clips.append((start, end, ""))
        start = end
    return clips


def video_filter(fmt):
    if fmt == "crop":
        # Fill the 9:16 frame by cropping the sides.
        return (f"scale={SHORTS_W}:{SHORTS_H}:force_original_aspect_ratio=increase,"
                f"crop={SHORTS_W}:{SHORTS_H},setsar=1")
    if fmt == "blur":
        # Keep the whole picture, fill the empty space with a blurred copy.
        return (f"split[bg][fg];"
                f"[bg]scale={SHORTS_W}:{SHORTS_H}:force_original_aspect_ratio=increase,"
                f"crop={SHORTS_W}:{SHORTS_H},boxblur=20:2[bg];"
                f"[fg]scale={SHORTS_W}:{SHORTS_H}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
    return None  # "original": keep the source frame


def cut(src, dst, start, end, fmt):
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-ss", f"{start:.3f}", "-i", str(src), "-t", f"{end - start:.3f}"]
    vf = video_filter(fmt)
    if vf:
        cmd += ["-filter_complex", vf]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(dst)]
    subprocess.run(cmd, check=True)


def fmt_time(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def main():
    p = argparse.ArgumentParser(description="Cut long videos into Shorts.")
    sub = p.add_subparsers(dest="mode", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("video", type=Path, help="source video file")
    common.add_argument("-o", "--out", type=Path, default=Path("clips"),
                        help="output folder (default: clips/)")
    common.add_argument("--format", choices=["blur", "crop", "original"], default="blur",
                        help="blur: 9:16 with blurred background (default), "
                             "crop: 9:16 cropped, original: keep source frame")

    a = sub.add_parser("auto", parents=[common], help="split into equal clips")
    a.add_argument("--length", type=float, default=58,
                   help="clip length in seconds (default: 58)")
    a.add_argument("--min-length", type=float, default=15,
                   help="drop a final leftover shorter than this (default: 15)")

    m = sub.add_parser("manual", parents=[common], help="cut clips from a timestamps file")
    m.add_argument("--timestamps", type=Path, required=True,
                   help="text file with lines: START END [title]")

    args = p.parse_args()
    require_ffmpeg()

    if not args.video.is_file():
        sys.exit(f"Error: video not found: {args.video}")
    duration = video_duration(args.video)

    if args.mode == "auto":
        if args.length <= 0:
            sys.exit("Error: --length must be positive")
        clips = auto_clips(duration, args.length, args.min_length)
    else:
        clips = read_timestamps(args.timestamps)
        for start, end, _ in clips:
            if start >= duration:
                sys.exit(f"Error: clip starts at {fmt_time(start)}, "
                         f"but the video is only {fmt_time(duration)} long")

    if not clips:
        sys.exit("No clips to cut.")

    args.out.mkdir(parents=True, exist_ok=True)
    stem = slugify(args.video.stem) or "clip"
    for i, (start, end, title) in enumerate(clips, 1):
        end = min(end, duration)
        name = f"{stem}_{i:02d}" + (f"_{slugify(title)}" if title else "") + ".mp4"
        dst = args.out / name
        note = ""
        if args.format != "original" and end - start > MAX_SHORT_SECONDS:
            note = f"  (warning: longer than {MAX_SHORT_SECONDS}s, too long for a Short)"
        print(f"[{i}/{len(clips)}] {fmt_time(start)}-{fmt_time(end)} -> {dst}{note}")
        cut(args.video, dst, start, end, args.format)

    print(f"Done: {len(clips)} clip(s) in {args.out}/")


if __name__ == "__main__":
    main()

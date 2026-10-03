#!/usr/bin/env python3
"""Cut a long video into short clips (YouTube Shorts, TikTok, Reels) using ffmpeg.

Modes:
  auto        split the whole video into equal clips of --length seconds
  manual      cut the clips listed in a timestamps file
  transcript  write what is said, with times, to pick the best moments from

The video can be a local file or a link (YouTube, Twitch, Kick, ...).

Examples:
  python3 clipper/clip.py auto  video.mp4 --length 58
  python3 clipper/clip.py transcript "https://youtu.be/..."
  python3 clipper/clip.py manual "https://youtu.be/..." --timestamps clips.txt --captions
"""

import argparse
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from captions import Transcriber, write_ass

SHORTS_W, SHORTS_H = 1080, 1920
MAX_SHORT_SECONDS = 180
DOWNLOADS = Path("downloads")


def require_ffmpeg():
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            sys.exit(f"Error: '{tool}' was not found. Install ffmpeg first.")


def probe(path, *args):
    return subprocess.run(
        ["ffprobe", "-v", "error", *args, "-of", "default=noprint_wrappers=1:nokey=1",
         str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.split()


def video_duration(path):
    return float(probe(path, "-show_entries", "format=duration")[0])


def has_audio(path):
    return bool(probe(path, "-select_streams", "a", "-show_entries", "stream=index"))


def is_url(text):
    return re.match(r"https?://", text) is not None


def download(url):
    try:
        import yt_dlp
    except ImportError:
        sys.exit("Error: downloading from a link needs yt-dlp: pip install yt-dlp")
    DOWNLOADS.mkdir(exist_ok=True)
    opts = {
        "outtmpl": str(DOWNLOADS / "%(title).80s [%(id)s].%(ext)s"),
        "format": "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    return Path(info["requested_downloads"][0]["filepath"])


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


def frame_size(fmt, src):
    if fmt == "original":
        w, h = probe(src, "-select_streams", "v:0", "-show_entries", "stream=width,height")
        return int(w), int(h)
    return SHORTS_W, SHORTS_H


def cut(src, dst, start, end, fmt, transcriber=None):
    vf = video_filter(fmt)
    with tempfile.TemporaryDirectory() as tmp:
        if transcriber:
            words = transcriber.words(src, start, end)
            write_ass(Path(tmp) / "captions.ass", words, end - start, *frame_size(fmt, src))
            # ffmpeg runs inside tmp, so the subtitle path needs no escaping.
            vf = f"{vf},ass=captions.ass" if vf else "ass=captions.ass"
        cmd = ["ffmpeg", "-y", "-loglevel", "error",
               "-ss", f"{start:.3f}", "-i", str(src.resolve()), "-t", f"{end - start:.3f}"]
        if vf:
            cmd += ["-filter_complex", vf]
        cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
                str(dst.resolve())]
        subprocess.run(cmd, check=True, cwd=tmp)


def fmt_time(seconds):
    """Format as M:SS or H:MM:SS, which read_timestamps also accepts."""
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def write_transcript(transcriber, video, path):
    """One line per sentence, 'START END text': the same format as a timestamps file."""
    with open(path, "w", encoding="utf-8") as f:
        for seg in transcriber.segments(video):
            line = f"{fmt_time(seg.start)} {fmt_time(math.ceil(seg.end))}  {seg.text.strip()}"
            print(line)
            f.write(line + "\n")


def main():
    p = argparse.ArgumentParser(description="Cut long videos into Shorts.")
    sub = p.add_subparsers(dest="mode", required=True)

    source = argparse.ArgumentParser(add_help=False)
    source.add_argument("video", help="source video file or link")
    source.add_argument("--lang", help="spoken language, e.g. en, fr or ar (default: detect)")
    source.add_argument("--whisper-model", default="small",
                        help="tiny, base, small (default), medium or large-v3: "
                             "bigger is more accurate but slower")

    common = argparse.ArgumentParser(add_help=False, parents=[source])
    common.add_argument("-o", "--out", type=Path, default=Path("clips"),
                        help="output folder (default: clips/)")
    common.add_argument("--format", choices=["blur", "crop", "original"], default="blur",
                        help="blur: 9:16 with blurred background (default), "
                             "crop: 9:16 cropped, original: keep source frame")
    common.add_argument("--captions", action="store_true",
                        help="burn in word-by-word captions (needs faster-whisper)")

    a = sub.add_parser("auto", parents=[common], help="split into equal clips")
    a.add_argument("--length", type=float, default=58,
                   help="clip length in seconds (default: 58)")
    a.add_argument("--min-length", type=float, default=15,
                   help="drop a final leftover shorter than this (default: 15)")

    m = sub.add_parser("manual", parents=[common], help="cut clips from a timestamps file")
    m.add_argument("--timestamps", type=Path, required=True,
                   help="text file with lines: START END [title]")

    t = sub.add_parser("transcript", parents=[source],
                       help="write what is said, with times, to help pick the best moments")
    t.add_argument("-o", "--out", type=Path, default=Path("transcripts"),
                   help="output folder (default: transcripts/)")

    args = p.parse_args()
    require_ffmpeg()

    video = download(args.video) if is_url(args.video) else Path(args.video)
    if not video.is_file():
        sys.exit(f"Error: video not found: {video}")
    duration = video_duration(video)

    if args.mode == "transcript":
        if not has_audio(video):
            sys.exit("Error: the video has no audio, so there is nothing to transcribe.")
        args.out.mkdir(parents=True, exist_ok=True)
        path = args.out / f"{slugify(video.stem) or 'transcript'}.txt"
        write_transcript(Transcriber(args.whisper_model, args.lang), video, path)
        print(f"Done: transcript saved to {path}")
        return

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

    transcriber = None
    if args.captions:
        if not has_audio(video):
            sys.exit("Error: the video has no audio, so there is nothing to caption.")
        transcriber = Transcriber(args.whisper_model, args.lang)

    args.out.mkdir(parents=True, exist_ok=True)
    stem = slugify(video.stem) or "clip"
    for i, (start, end, title) in enumerate(clips, 1):
        end = min(end, duration)
        name = f"{stem}_{i:02d}" + (f"_{slugify(title)}" if title else "") + ".mp4"
        dst = args.out / name
        note = ""
        if args.format != "original" and end - start > MAX_SHORT_SECONDS:
            note = f"  (warning: longer than {MAX_SHORT_SECONDS}s, too long for a Short)"
        print(f"[{i}/{len(clips)}] {fmt_time(start)}-{fmt_time(end)} -> {dst}{note}")
        cut(video, dst, start, end, args.format, transcriber)

    print(f"Done: {len(clips)} clip(s) in {args.out}/")


if __name__ == "__main__":
    main()

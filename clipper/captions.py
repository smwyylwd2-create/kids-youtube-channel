"""Word-by-word captions (clipping style), transcribed with Whisper and
written as an ASS subtitle file that ffmpeg burns into the clip."""

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

WORDS_PER_LINE = 3
MAX_GAP = 0.6        # a pause longer than this (seconds) starts a new line
HOLD = 0.25          # keep a line on screen a little after its last word
HIGHLIGHT = "&H00FFFF&"  # colour of the word being spoken (ASS is BGR: yellow)
FONT = "Arial"


@dataclass
class Word:
    start: float
    end: float
    text: str


class Transcriber:
    def __init__(self, model_size="small", language=None):
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            sys.exit("Error: captions need faster-whisper: pip install faster-whisper")
        print(f"Loading Whisper model '{model_size}' (downloaded once on first use)...")
        self.model = WhisperModel(model_size, device="auto", compute_type="int8")
        self.language = language

    def words(self, src, start, end):
        """Transcribe src between start and end; times are relative to start."""
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "audio.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-i", str(src),
                 "-t", f"{end - start:.3f}", "-vn", "-ac", "1", "-ar", "16000", str(wav)],
                check=True,
            )
            segments, _ = self.model.transcribe(
                str(wav), language=self.language, word_timestamps=True, vad_filter=True)
            return [Word(w.start, w.end, w.word.strip())
                    for seg in segments for w in seg.words]

    def segments(self, src):
        """Transcribe a whole file, yielding sentences as they are recognised."""
        segments, _ = self.model.transcribe(str(src), language=self.language,
                                            vad_filter=True)
        return segments


def clean(text):
    # Drop characters that would be read as ASS override tags.
    text = text.replace("\\", "").replace("{", "").replace("}", "")
    return text.strip(" .,;:").upper()


def group(words):
    """Split words into short caption lines."""
    lines, line = [], []
    for w in words:
        if line and (len(line) >= WORDS_PER_LINE
                     or w.start - line[-1].end > MAX_GAP
                     or line[-1].text[-1:] in ".?!,"):
            lines.append(line)
            line = []
        line.append(w)
    if line:
        lines.append(line)
    return lines


def ass_time(seconds):
    cs = max(0, round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def events(words, duration):
    """One event per spoken word: the whole line, with that word highlighted."""
    lines = group([w for w in words if clean(w.text)])
    out = []
    for n, line in enumerate(lines):
        next_start = lines[n + 1][0].start if n + 1 < len(lines) else duration
        line_end = min(line[-1].end + HOLD, next_start, duration)
        for i, word in enumerate(line):
            end = line[i + 1].start if i + 1 < len(line) else line_end
            if end <= word.start:
                continue
            text = " ".join(
                f"{{\\c{HIGHLIGHT}}}{clean(w.text)}{{\\r}}" if w is word else clean(w.text)
                for w in line)
            out.append(f"Dialogue: 0,{ass_time(word.start)},{ass_time(end)},"
                       f"Caption,,0,0,0,,{text}")
    return out


def write_ass(path, words, duration, width, height):
    size = round(min(width, height) * 0.075)
    outline = max(2, size // 12)
    margin_lr = round(width * 0.06)
    margin_v = round(height * 0.25)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{FONT},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{outline},2,2,{margin_lr},{margin_lr},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    Path(path).write_text(header + "\n".join(events(words, duration)) + "\n",
                          encoding="utf-8")

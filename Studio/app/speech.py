"""Speech to text for the 🎙 buttons (local faster-whisper, no Claude usage) + turning spoken times into m:ss.

normalize_times("cut from one minute to one thirty") -> "cut from 1:00 to 1:30"
normalize_times("remove 2.20 to 2.45")               -> "remove 2:20 to 2:45"
"""
import os
import re
import subprocess
import sys
import tempfile
import threading

import numpy as np

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_MODEL = {"m": None}
_LOCK = threading.Lock()

ONES = {"zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}
NUMW = r"(?:(?:twenty|thirty|forty|fifty)(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?|zero|oh|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen)"


def _wnum(w):
    w = w.lower().replace("-", " ").split()
    if len(w) == 2:
        return TENS[w[0]] + ONES[w[1]]
    return TENS.get(w[0], ONES.get(w[0], 0))


def normalize_times(text):
    t = " " + text + " "
    # number words -> digits ("one minute thirty" -> "1 minute 30")
    t = re.sub(r"\b" + NUMW + r"\b", lambda m: str(_wnum(m.group(0))), t, flags=re.I)
    # "1 minute 30 seconds", "1 minute and 30", "1 min 30"
    # durations stay durations: "for 6 seconds" -> "6s" (B-roll length)
    t = re.sub(r"\bfor\s+(\d{1,3})\s*(?:seconds?|secs?)\b", r"\1s", t, flags=re.I)
    t = re.sub(r"\b(\d{1,2})\s*(?:minutes?|mins?)\s*(?:and\s*)?(\d{1,2})(?!\s*(?:minutes?|mins?|:))(?:\s*(?:seconds?|secs?))?\b", lambda m: f"{int(m.group(1))}:{int(m.group(2)):02d}", t, flags=re.I)
    # "1 minute" alone -> 1:00
    t = re.sub(r"\b(\d{1,2})\s*(?:minutes?|mins?)\b", lambda m: f"{int(m.group(1))}:00", t, flags=re.I)
    # "45 seconds" alone -> 0:45
    t = re.sub(r"\b(\d{1,2})\s*(?:seconds?|secs?)\b", lambda m: f"0:{int(m.group(1)):02d}", t, flags=re.I)
    # "1.30" / "1 30" right after a time word or another time ("to 1 30") -> 1:30
    t = re.sub(r"\b(\d{1,2})\.(\d{2})\b(?!\s*%)", r"\1:\2", t)
    t = re.sub(r"\b(at|to|from|until|till|and|cut|protect|-)\s(\d{1,2})\s(\d{2})\b", r"\1 \2:\3", t, flags=re.I)
    t = re.sub(r"^\s*(\d{1,2})\s(\d{2})\b", r"\1:\2", t)
    # "from 1:00 to 1:30" / "between 1:00 and 1:30" -> "1:00-1:30" so the note is a range
    t = re.sub(r"(?:from\s+|between\s+)?(\d{1,2}:\d{2}(?:\.\d+)?)\s*(?:to|until|till|and|through|-|–)\s*(\d{1,2}:\d{2}(?:\.\d+)?)", r"\1-\2", t, flags=re.I)
    return re.sub(r"\s+", " ", t).strip()


def _model():
    with _LOCK:
        if _MODEL["m"] is None:
            from faster_whisper import WhisperModel
            _MODEL["m"] = WhisperModel("small.en", device="cpu", compute_type="int8", cpu_threads=8)
        return _MODEL["m"]


def transcribe_bytes(data, note_mode=False):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as f:
        f.write(data)
        path = f.name
    try:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True,
                             creationflags=CREATE_NO_WINDOW).stdout
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    if len(a) < 8000:
        return ""
    # times hint only: a "B-roll at 3:20" example in the prompt can be echoed back as if he said it (jordan 3 2026-10-23)
    prompt = "Cut 1:22-1:30. Protect 2:03 to 2:10." if note_mode else None
    segs, _ = _model().transcribe(a, beam_size=1, vad_filter=False, condition_on_previous_text=False, initial_prompt=prompt)   # greedy: ~1 s for a short note
    echo = {"cut 1:22-1:30.", "protect 2:03 to 2:10.", "b-roll at 3:20 for 6 seconds."}
    text = " ".join(s.text.strip() for s in segs if s.text.strip().lower() not in echo).strip()
    return normalize_times(text) if note_mode else text


def warm():
    threading.Thread(target=_model, daemon=True).start()

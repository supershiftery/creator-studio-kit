"""Word timestamps of a finished render (so Shorts moments are measured on the exact file they are cut from).
python transcribe_render.py <render.mp4> <out words.json>   (skips when out is newer than the render)"""
import json
import os
import subprocess
import sys

import numpy as np

src, out = sys.argv[1], sys.argv[2]
if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(src):
    print("transcript of this render is current")
    sys.exit(0)
from faster_whisper import WhisperModel  # noqa: E402

raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
print(f"transcribing the render ({len(a) / 16000 / 60:.1f} min)", flush=True)
m = WhisperModel("small.en", device="cpu", compute_type="int8", cpu_threads=12)
segs, _ = m.transcribe(a, word_timestamps=True, condition_on_previous_text=False, vad_filter=True)
words = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)} for s in segs for w in (s.words or [])]
json.dump(words, open(out, "w", encoding="utf-8"))
print(f"{len(words)} words")

"""Scan music for vocals / producer tags (the no-vocal rule).  python vocal_scan.py <results.json> file [file ...]
medium.en, no VAD, highpass 200 Hz. > 20 confident words = vocal track (reject); producer tags like "beatstars" count too.
Results are merged into results.json: {path: {"words", "hits", "verdict", "when"}}."""
import json
import os
import subprocess
import sys
import time

import numpy as np

out_path = sys.argv[1]
files = sys.argv[2:]
try:
    results = json.load(open(out_path, encoding="utf-8"))
except Exception:
    results = {}
from faster_whisper import WhisperModel  # noqa: E402

m = WhisperModel("medium.en", device="cpu", compute_type="int8", cpu_threads=12)
TAGS = ("beatstars", "prod", "beat by", "type beat", "free beat", "subscribe", "instagram", "youtube")
for f in files:
    if not os.path.exists(f):
        continue
    print(f"scanning {os.path.basename(f)}", flush=True)
    cmd = ["ffmpeg", "-v", "error", "-t", "150", "-i", f, "-af", "highpass=f=200", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"]
    a = np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, dtype=np.float32)
    segs, _ = m.transcribe(a, vad_filter=False, condition_on_previous_text=False, no_speech_threshold=0.9, log_prob_threshold=-2.0)
    hits = []
    for s in segs:
        if s.avg_logprob > -1.0 and s.no_speech_prob < 0.7 and len(s.text.split()) >= 2:
            hits.append([round(s.start, 1), round(s.end, 1), s.text.strip()[:80]])
    words = sum(len(h[2].split()) for h in hits)
    tag = any(t in h[2].lower() for h in hits for t in TAGS)
    verdict = "vocal" if words > 20 else ("tag" if tag else "clean")
    results[f] = {"words": words, "hits": hits[:6], "verdict": verdict, "when": time.strftime("%Y-%m-%d")}
    print(f"  {words} words -> {verdict}", flush=True)
    for h in hits[:3]:
        print("   ", h, flush=True)
    json.dump(results, open(out_path, "w", encoding="utf-8"), indent=0)
print("done")

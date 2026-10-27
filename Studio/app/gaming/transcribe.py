"""Step 2: word-level transcript of the mic (faster-whisper small.en, on the RTX 4070 when CUDA loads, else CPU int8).
python transcribe.py <project>"""
import json
import sys
import wave

import numpy as np

from glib import Project, say

P = Project(sys.argv[1])
sys.path.insert(0, r"{{KIT}}/tools")
from whisper_gpu import load  # noqa: E402

w = wave.open(str(P.wf("mic16k.wav")))
x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
vocab = P.settings.get("vocabulary") or []
prompt = "Um, so, uh, " + ", ".join(["Minecraft Bedrock", "realm code", "honorable mention", "server IP", "add-on"] + list(vocab)) + "."
m, where = load("small.en", cpu_threads=12)
say(f"transcribing {len(x) / 16000 / 60:.1f} min (small.en, {where})")
segs, _ = m.transcribe(x, word_timestamps=True, condition_on_previous_text=False, vad_filter=False, initial_prompt=prompt)
words = []
last = 0
for s in segs:
    for wd in (s.words or []):
        words.append({"w": wd.word.strip(), "s": round(wd.start, 3), "e": round(wd.end, 3), "p": round(wd.probability, 2)})
    if s.end - last > 120:
        say(f"  {s.end / 60:5.1f} min  {s.text.strip()[:80]}")
        last = s.end
P.write("words.json", words)
say(f"WORDS {len(words)}")

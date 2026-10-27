"""Where a finished intro's voice-over ends, so the main video can start right after it (reselling spreadsheet 2026-10-23,
user: "removing the 1 second was a good call across all of our videos ... no spacing in between the intro for the
voiceover and the other intro"). Pre-made intros (gaming HyperFrames renders) have the VO mixed with music, so the last
word is found with Whisper word times, not silence. Cached next to the intro as <stem>.vo-end.json (keyed by size+mtime).
    python intro_end.py <intro.mp4>        -> prints the last word's end in seconds
    from intro_end import vo_end; vo_end(path) -> float | None"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def vo_end(path, size="medium.en"):   # small.en lost "shocking." under the music (realms-intro-v7 ends 25.46, not 25.04)
    st = os.stat(path)
    key = f"{st.st_size}:{int(st.st_mtime)}"
    cache = os.path.splitext(path)[0] + ".vo-end.json"
    try:
        c = json.load(open(cache))
        if c.get("key") == key:
            return c.get("end")
    except (OSError, ValueError):
        pass
    import numpy as np
    # raw float samples, not a file: this PC's PyAV rejects faster_whisper's decode_audio (metadata_errors)
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    from whisper_gpu import load
    model, _ = load(size)
    segs, _ = model.transcribe(np.frombuffer(pcm, np.float32), word_timestamps=True, vad_filter=False, language="en")
    words = [w for s in segs for w in (s.words or []) if w.word.strip() and (w.probability or 0) > 0.3]
    end = round(words[-1].end, 2) if words else None
    try:
        json.dump({"key": key, "end": end, "last": words[-1].word.strip() if words else ""}, open(cache, "w"))
    except OSError:
        pass
    return end


if __name__ == "__main__":
    print(vo_end(sys.argv[1]))

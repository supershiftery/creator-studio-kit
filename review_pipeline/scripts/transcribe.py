"""Step 1: word-level transcript of the camera audio, cached to work/transcript.json."""
import json, subprocess, sys
from pathlib import Path

def transcribe(project: Path, cfg: dict) -> list:
    out = project / "work" / "transcript.json"
    if out.exists():
        return json.loads(out.read_text(encoding="utf-8"))
    from faster_whisper import WhisperModel
    import numpy as np
    pcm = subprocess.run(["ffmpeg", "-v", "error", "-i", str(project / "raw" / "camera.mp4"),
                          "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], check=True, capture_output=True).stdout
    wav = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
    w = cfg["whisper"]
    try:
        model = WhisperModel(w["model"], device="cuda", compute_type="float16")
        segs, _ = model.transcribe(wav, language=w["language"], word_timestamps=True, vad_filter=False)
        segs = list(segs)
    except Exception:
        model = WhisperModel(w["model"], device="cpu", compute_type="int8")
        segs, _ = model.transcribe(wav, language=w["language"], word_timestamps=True, vad_filter=False)
        segs = list(segs)
    words = [{"w": x.word.strip(), "s": round(x.start, 3), "e": round(x.end, 3)} for s in segs for x in (s.words or [])]
    out.write_text(json.dumps(words, indent=0), encoding="utf-8")
    return words

if __name__ == "__main__":
    here = Path(__file__).parent
    cfg = json.loads((here / "config.json").read_text())
    print(len(transcribe(Path(sys.argv[1]), cfg)), "words")

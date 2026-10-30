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
    # through whisper_gpu (2026-10-29, speed): a bare device="cuda" load had no cuBLAS on PATH, failed at the first encode
    # and fell back to the CPU, and that failed CUDA try left every later GPU Whisper in the build (word guards, joins)
    # hanging 90 s before its own CPU fallback. Every laptop build since 10-25 lost minutes to it (Mon Clear: 4.5 min
    # transcript + 5 min guards). whisper_gpu registers the DLLs, proves the GPU and falls back to the CPU itself.
    sys.path.insert(0, str(Path(cfg.get("tools", r"{{KIT}}/tools"))))
    try:
        import whisper_gpu
        model, _dev = whisper_gpu.load(w["model"])
    except ImportError:
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

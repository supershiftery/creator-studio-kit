"""One place that loads faster-whisper: on the RTX 4070 when CUDA works, else on the CPU like before.
GPU = the pip packages nvidia-cublas-cu12 + nvidia-cudnn-cu12 (installed 2026-10-22, user: "faster builds"). On Windows their
DLL folders are not on PATH, so they are registered here before ctranslate2 loads. A tiny test decode proves the GPU path
really works (a missing DLL only fails at the first encode), otherwise it falls back silently.
    from whisper_gpu import load
    model, where = load("small.en")      # where = "cuda float16" | "cpu int8"
Env WHISPER_DEVICE=cpu forces the CPU."""
import importlib.util
import os
import sys

_DONE = False


def _dll_dirs():
    global _DONE
    if _DONE or sys.platform != "win32":
        return
    _DONE = True
    for mod in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_nvrtc", "nvidia.cuda_runtime"):
        try:
            spec = importlib.util.find_spec(mod)
        except (ImportError, ValueError):
            spec = None
        for base in (spec.submodule_search_locations if spec else []) or []:
            b = os.path.join(base, "bin")
            if os.path.isdir(b):
                os.add_dll_directory(b)
                os.environ["PATH"] = b + os.pathsep + os.environ.get("PATH", "")


class _Watched:
    """A GPU model whose transcribe() cannot hang the build (2026-10-24: four review builds sat 25 min at 0 CPU inside a
    CUDA transcribe until Studio's stall kill retried them; with two render slots the GPU is shared more). The segments
    are read in a worker thread; past the time limit the call is redone on a CPU model, which this process keeps using.
    Returns (list_of_segments, info) like faster-whisper (a list instead of the lazy generator)."""
    def __init__(self, gpu, size, cpu_threads):
        self.gpu, self.size, self.cpu_threads, self.cpu = gpu, size, cpu_threads, None

    def __getattr__(self, name):
        return getattr(self.cpu or self.gpu, name)

    def _cpu(self):
        if self.cpu is None:
            from faster_whisper import WhisperModel
            self.cpu = WhisperModel(self.size, device="cpu", compute_type="int8", cpu_threads=self.cpu_threads)
        return self.cpu

    def transcribe(self, audio, *a, **kw):
        if self.cpu is not None:
            segs, info = self.cpu.transcribe(audio, *a, **kw)
            return list(segs), info
        import threading
        # a quarter of the audio length, at least 90 s (the GPU runs ~20-50x realtime); a file path counts as 40 min
        secs = len(audio) / 16000 if hasattr(audio, "__len__") and not isinstance(audio, str) else 2400
        limit = float(os.environ.get("WHISPER_GPU_TIMEOUT", 0)) or max(90.0, 0.25 * secs)
        box = {}

        def work():
            try:
                segs, info = self.gpu.transcribe(audio, *a, **kw)
                box["r"] = (list(segs), info)
            except Exception as e:  # noqa
                box["e"] = e
        t = threading.Thread(target=work, daemon=True)
        t.start()
        t.join(limit)
        if "r" in box:
            return box["r"]
        why = f"failed ({type(box['e']).__name__})" if "e" in box else f"no answer after {limit:.0f} s (GPU hang)"
        print(f"whisper: GPU transcribe {why}; redoing it on the CPU", flush=True)
        segs, info = self._cpu().transcribe(audio, *a, **kw)
        return list(segs), info


def load(size="small.en", cpu_threads=12):
    from faster_whisper import WhisperModel
    if os.environ.get("WHISPER_DEVICE", "").lower() != "cpu":
        _dll_dirs()
        try:
            import numpy as np
            m = WhisperModel(size, device="cuda", compute_type="float16")
            w = _Watched(m, size, cpu_threads)
            w.transcribe(np.zeros(16000, np.float32), vad_filter=False)   # proves cuBLAS/cuDNN really load
            if w.cpu is not None:
                return w.cpu, "cpu int8"
            return w, "cuda float16"
        except Exception as e:  # noqa: no GPU libs / no CUDA: the CPU path is the old, known-good one
            print(f"whisper: GPU unavailable ({type(e).__name__}: {str(e)[:120]}), using the CPU", flush=True)
    return WhisperModel(size, device="cpu", compute_type="int8", cpu_threads=cpu_threads), "cpu int8"

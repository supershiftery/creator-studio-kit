"""A quiet sound on every B-roll pop of his own footage (watch spreadsheet 2026-10-24: "having a sound effect when the clips
pop up, that might actually help it move along faster ... design that soundscape, but we don't want to use the same sound
all the time"). Sparse + quiet (playbook): short swishes / a shutter / a soft click, every one levelled to the same peak,
never the same sound twice in a row (a list of 4 names = 4 different sounds). No risers, 808s, cartoon whistles or zaps."""
import subprocess
from pathlib import Path

POOL = [  # (file, seconds to keep, lead: s before the pop the sound starts, so its peak lands ON the cut)
    (r"{{MUSIC_ROOT}}\Sound Effects\Swoosh Pack\Fast Swish.wav", 0.57, 0.10),
    (r"{{KIT}}/tools\intro_library\kit\sfx\whoosh-short.mp3", 0.57, 0.10),
    (r"{{KIT}}/tools\intro_library\kit\sfx\shutter.mp3", 0.6, 0.02),
    (r"{{MUSIC_ROOT}}\Sound Effects\Swoosh Pack\Standard Swoosh.wav", 0.8, 0.15),
    (r"{{KIT}}/tools\intro_library\kit\sfx\click.mp3", 0.36, 0.0),
    (r"{{MUSIC_ROOT}}\Sound Effects\Swoosh Pack\Breath Whoosh.mp3", 1.0, 0.20),
]
_PEAK = {}


def _peak(f):
    if f not in _PEAK:
        r = subprocess.run(["ffmpeg", "-v", "info", "-i", f, "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
        m = [l for l in r.stderr.splitlines() if "max_volume" in l]
        _PEAK[f] = float(m[0].split(":")[1].split()[0]) if m else 0.0
    return _PEAK[f]


def plan(placed, peak_db=-21.0):
    """[{file, at, keep, gain_db}] for every placed clip of his own footage (named_broll), in time order."""
    pool = [p for p in POOL if Path(p[0]).exists()]
    out, last = [], None
    for k, c in enumerate(sorted([c for c in placed if c.get("named")], key=lambda c: c["out_start"])):
        # rotate; skip the one just used (and the one before, when the pool allows)
        opts = [p for p in pool if p[0] != last] or pool
        f, keep, lead = opts[k % len(opts)]
        last = f
        out.append({"file": f, "at": round(max(0.0, c["out_start"] - lead), 3), "keep": keep,
                    "gain_db": round(peak_db - _peak(f), 2)})
    return out


def filters(sfx, first_input):
    """Audio filter lines -> (lines, labels) for the final amix."""
    lines, labels = [], []
    for k, s in enumerate(sfx):
        lines.append(f"[{first_input + k}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{s['keep']},"
                     f"afade=t=out:st={max(0.0, s['keep'] - 0.12):.3f}:d=0.12,volume={s['gain_db']}dB,"
                     f"adelay={int(s['at'] * 1000)}:all=1[pop{k}]")
        labels.append(f"[pop{k}]")
    return lines, labels

"""Full-screen clips for the Top 5 Realms "trailer" intro (v2), cut from the raw recording's game half at 1080p60.
Crops keep every realm code / Discord code sidebar OUT of frame (no codes in intros).
The m0-m5 montage clips are copied from realms-intro-kv (same crops)."""
import subprocess, os
from concurrent.futures import ThreadPoolExecutor

RAW = r"{{RECORDINGS}}/2026-10-20 20-06-56.mp4"
GP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "gameplay")

FULL = (0, 0, 1920, 1080)
DF = (300, 120, 1200, 675)      # Dragonforge: realm code sidebar from x 1540
TC = (420, 60, 1100, 619)       # ThunderCloud: chat left, Discord code sidebar right
LU = (60, 140, 1400, 788)       # Lunar Box: Discord sidebar from x 1480
VC = (0, 120, 1400, 788)        # Village City: realm codes sidebar from x 1600

# name, raw time, duration, crop (x, y, w, h) in game-half pixels
CLIPS = [
    ("c01-anarchy", 2082.0, 2.0, FULL),        # Minecraft realms
    ("c02-rennmon-street", 3596.5, 2.0, FULL),  # still going?
    ("c03-people", 2614.0, 2.2, FULL),          # apparently people are hosting (other players on a realm)
    ("c04-crate", 3216.0, 1.8, LU),             # secret game modes
    ("c05-skygen", 995.5, 1.4, TC),             # Sky Gen
    ("c06-kitpvp", 1226.5, 1.8, (420, 400, 1100, 619)),            # Kit PvP
    ("c07-prisons", 3243.0, 1.0, LU),           # prisons
    ("c08-limited", 2567.0, 2.2, FULL),         # on these limited servers
    ("c09-players", 1146.0, 2.2, FULL),         # only up to ten players (Players in TC (10))
    ("c10-trials", 2674.0, 2.6, FULL),          # really curious, what's going on
    ("c11-dragonforge", 773.8, 1.3, DF),        # Minecraft
    ("c12-lunar-portal", 3302.0, 1.3, LU),      # Bedrock Edition
    ("c13-village", 2833.5, 1.2, VC),           # realms
    ("c14-starter", 3604.5, 1.6, FULL),         # in today's video (the drop)
    ("c15-charmander", 3650.5, 2.2, FULL),      # investigating just that
    ("c16-galaxy", 3341.0, 2.3, LU),            # watch to the very end
    ("c17-garden", 3695.0, 1.6, FULL),          # Top 5 Realms
]

def clip(job):
    name, t, d, (x, y, w, h) = job
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", RAW, "-t", str(d), "-an",
                    "-vf", f"crop={w}:{h}:{1920 + x}:{y},scale=1920:1080:flags=lanczos,fps=60,format=yuv420p",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-movflags", "+faststart",
                    os.path.join(GP, name + ".mp4")], check=True)
    return name

if __name__ == "__main__":
    os.makedirs(GP, exist_ok=True)
    with ThreadPoolExecutor(3) as ex:
        for n in ex.map(clip, CLIPS): print("clip", n)

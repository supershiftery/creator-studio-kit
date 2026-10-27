"""Cut the KV intro's realm clips + collage stills from the Top 5 Realms raw recording (game half).
Crops keep every realm code / Discord code sidebar OUT of frame (no codes in intros)."""
import subprocess, os
from concurrent.futures import ThreadPoolExecutor

RAW = r"{{RECORDINGS}}/2026-10-20 20-06-56.mp4"
HERE = os.path.dirname(os.path.abspath(__file__))
GP = os.path.join(HERE, "assets", "gameplay")
ST = os.path.join(HERE, "assets", "stills")

FULL = (0, 0, 1920, 1080)
DF = (300, 120, 1200, 675)      # Dragonforge: realm code sidebar from x 1540
TC = (420, 60, 1100, 619)       # ThunderCloud: chat left, Discord code sidebar right
LU = (60, 140, 1400, 788)       # Lunar Box: Discord sidebar from x 1500

# name, raw time, duration, crop (x, y, w, h) in game-half pixels, output size
CLIPS = [
    ("keyart-anarchy", 2082.0, 4.0, FULL, (1280, 720)),
    ("card-skygen", 995.5, 4.5, (520, 0, 900, 1062), (600, 708)),
    ("card-kitpvp", 1226.0, 4.5, (520, 0, 900, 1062), (600, 708)),
    ("card-prisons", 3243.0, 4.5, (420, 0, 900, 1062), (600, 708)),
    ("players-tc", 1146.0, 3.0, (1230, 200, 640, 860), (640, 860)),
    ("bg-limited", 2581.0, 3.0, FULL, (1280, 720)),
    ("bg-invest", 3650.5, 3.0, FULL, (1280, 720)),
    ("m0-rennmon", 3606.6, 1.2, FULL, (1920, 1080)),
    ("m1-lunar", 3322.0, 1.2, LU, (1920, 1080)),
    ("m2-thunder", 1159.0, 1.2, TC, (1920, 1080)),
    ("m3-spectrixious", 2641.0, 1.2, FULL, (1920, 1080)),
    ("m4-anarchy", 2133.5, 1.2, FULL, (1920, 1080)),
    ("m5-dragonforge", 695.0, 1.4, DF, (1920, 1080)),
]
STILLS = [
    ("s-dragonforge", 695.5, DF), ("s-thunder", 1159.4, TC), ("s-anarchy", 2133.7, FULL),
    ("s-spectrixious", 2641.4, FULL), ("s-lunar", 3322.0, LU), ("s-rennmon", 3607.5, FULL),
]

def crop(c):
    x, y, w, h = c
    return f"crop={w}:{h}:{1920 + x}:{y}"

def clip(job):
    name, t, d, c, (ow, oh) = job
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", RAW, "-t", str(d), "-an",
                    "-vf", f"{crop(c)},scale={ow}:{oh}:flags=lanczos,fps=60,format=yuv420p",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-movflags", "+faststart",
                    os.path.join(GP, name + ".mp4")], check=True)
    return name

def still(job):
    name, t, c = job
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", RAW, "-frames:v", "1",
                    "-vf", f"{crop(c)},scale=1120:630:flags=lanczos", "-q:v", "2",
                    os.path.join(ST, name + ".jpg")], check=True)
    return name

if __name__ == "__main__":
    os.makedirs(GP, exist_ok=True); os.makedirs(ST, exist_ok=True)
    with ThreadPoolExecutor(3) as ex:
        for n in ex.map(clip, CLIPS): print("clip", n)
        for n in ex.map(still, STILLS): print("still", n)

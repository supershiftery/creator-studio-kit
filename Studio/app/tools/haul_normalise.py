"""Haul recordings -> one clean source (user 2026-10-23: "these may be 4K or 1080p, some clips 30 fps and others 60").

    python haul_normalise.py <project>

A haul is one long phone recording (iPhone .MOV / .mp4), often split into several clips. Phone clips arrive as HEVC 10-bit
HDR (HLG + Dolby Vision on the iPhone 17 Pro Max), variable frame rate, at 4K or 1080p, some 30 fps and some 60. Every
clip is probed and brought to ONE format before anything else touches it:
- picture: SDR BT.709 (HDR tone-mapped with libplacebo on the GPU, zscale+hable on the CPU as the fallback; libplacebo looked
  natural, hable dull, 30kg haul test), 1920x1080 (1080x1920 for a vertical Short; a clip of the other shape sits on a blurred fill of itself), one CONSTANT frame
  rate, always 60 (4K and 30 fps clips included), H.264 High yuv420p (never HEVC);
- sound: the first stereo AAC track (iPhones add an "apac" spatial track; Spatial Audio / wide clips are folded to mono
  + EQ-matched to the plain clips, 2026-10-23), 48 kHz stereo AAC, padded / trimmed to the
  picture so the two always end together; ALWAYS 1920x1080 at 60 fps CFR, 4K scaled down (user 2026-10-23);
- checks: STREAM durations, never the format duration (VFR phone and OBS files lie there). A source clip whose picture and
  sound differ by more than 0.5 s is refused; every normalised clip must come out with picture = sound (+-1 frame), else
  the build stops.
Clips are cached per source (size + mtime + settings) in raw/clips/norm/, then joined by stream copy into raw/source.mp4.
Writes raw/clips/norm/clips.json: [{src, start, dur, fps_in, w_in, h_in, hdr}] (start = where the clip begins in source.mp4).
"""
import json
import re
import os
import subprocess
import sys
from pathlib import Path

proj = Path(sys.argv[1])
doc = json.loads((proj / "studio.json").read_text(encoding="utf-8-sig"))
S = doc.get("settings") or {}
clips = [c for c in (doc.get("slots") or {}).get("clips") or [] if c]
if not clips:
    sys.exit("no haul clips in this project (slots.clips is empty)")
norm_dir = proj / "raw" / "clips" / "norm"
norm_dir.mkdir(parents=True, exist_ok=True)
out = proj / "raw" / "source.mp4"
# canvas: 1920x1080 for a haul; 1080x1920 for a vertical Short (Studio type "short", user 2026-10-23: "keep it 1080x1920")
VERTICAL = doc.get("type") == "short"
W, H = (1080, 1920) if VERTICAL else (1920, 1080)
CQ = str(S.get("normalise_cq") or 19)


def probe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(p)], capture_output=True, text=True)
    return json.loads(r.stdout or "{}")


def rate(s):
    a, _, b = (s or "0/1").partition("/")
    try:
        return float(a) / float(b or 1)
    except ZeroDivisionError:
        return 0.0


def stream_durs(d):
    """first video + first audio STREAM duration (the format duration is not trusted on VFR phone / OBS files)"""
    v = next((s for s in d.get("streams", []) if s["codec_type"] == "video"), None)
    a = next((s for s in d.get("streams", []) if s["codec_type"] == "audio"), None)
    f = lambda s: float(s["duration"]) if s and s.get("duration") not in (None, "N/A") else None   # noqa: E731
    return f(v), f(a)


info = []
for c in clips:
    d = probe(c)
    v = next((s for s in d.get("streams", []) if s["codec_type"] == "video"), None)
    auds = [s for s in d.get("streams", []) if s["codec_type"] == "audio"]
    if not v or not auds:
        sys.exit(f"{Path(c).name}: no picture or no sound")
    # the voice track: first AAC (or any decodable codec) track; iPhone "apple_apac" spatial audio is skipped
    ai = next((k for k, s in enumerate(auds) if s.get("codec_name") not in ("apple_apac", None, "unknown")), 0)
    vd, ad = stream_durs({"streams": [v, auds[ai]]})
    if vd is None or ad is None:
        sys.exit(f"{Path(c).name}: stream durations missing, can't check picture vs sound")
    if abs(vd - ad) > 0.5:
        sys.exit(f"REFUSED {Path(c).name}: picture {vd:.2f} s vs sound {ad:.2f} s differ by {abs(vd - ad):.2f} s (broken recording)")
    rot = 0
    for sd in v.get("side_data_list") or []:
        if "rotation" in sd:
            rot = int(sd["rotation"])
    w, h = v["width"], v["height"]
    if abs(rot) in (90, 270):
        w, h = h, w
    hdr = v.get("color_transfer") in ("arib-std-b67", "smpte2084") or "bt2020" in (v.get("color_primaries") or "")
    # VFR phone files: r_frame_rate is the nominal rate (60000/1001, 30/1), avg_frame_rate drifts below it
    fps = rate(v.get("r_frame_rate")) or rate(v.get("avg_frame_rate")) or 30.0
    made = ((d.get("format") or {}).get("tags") or {}).get("creation_time") or ""
    num = re.findall(r"(\d{3,})", Path(c).stem)
    info.append({"made": made, "num": int(num[-1]) if num else 0, "src": c, "dur": vd, "adur": ad, "fps_in": round(fps, 3), "w_in": w, "h_in": h, "hdr": hdr, "codec": v.get("codec_name"),
                 "audio_index": ai, "pix_fmt": v.get("pix_fmt"), "spatial": any(s.get("codec_name") == "apple_apac" for s in auds)})
    print(f"{Path(c).name}: {v.get('codec_name')} {w}x{h} {fps:.2f} fps (avg {rate(v.get('avg_frame_rate')):.2f}, "
          f"{'VFR' if abs(rate(v.get('avg_frame_rate')) - fps) > 0.5 else 'CFR'}), {'HDR' if hdr else 'SDR'}, "
          f"picture {vd:.2f} s / sound {ad:.2f} s", flush=True)

# recording order (user 2026-10-23: "they're recorded in order ... the default iPhone name"): the camera's creation time,
# then the IMG_#### number (iPhone numbers count up). settings.haul_keep_order = true keeps the order they were added in.
if not S.get("haul_keep_order"):
    info.sort(key=lambda i: (i["made"] or "9999", i["num"], Path(i["src"]).name))
print("order: " + " -> ".join(f"{Path(i['src']).name} ({i['made'][11:19] or '?'})" for i in info), flush=True)

# one frame rate for the whole video: ALWAYS 1080p60 (user 2026-10-23: "even if these videos are recorded in 4K, they need
# to be downscaled to 1080p (60fps)"); 30 fps clips get each frame twice, 4K is scaled down. settings.haul_fps overrides.
by = {}
for i in info:
    k = 60 if i["fps_in"] > 45 else 30 if i["fps_in"] > 26 else 24
    by[k] = by.get(k, 0) + i["dur"]
FPS = int(S.get("haul_fps") or 60)
mixed = len(by) > 1
print(f"target: {W}x{H} {FPS} fps CFR, SDR BT.709, H.264 High yuv420p + AAC 48 kHz" + (f" (mixed input rates {sorted(by)})" if mixed else ""), flush=True)

# voice match (30kg haul 2026-10-23, clip 1 "sounds like it's going around me"): an iPhone clip filmed with Spatial Audio
# on (it carries an apple_apac track) has a WIDE stereo AAC render (L/R correlation 0.43, side only 6 dB under mid) and a
# brighter voice (+5 dB at 2.5-6 kHz, -2 dB under 250 Hz), while the normal clips are dual-mono (L = R). Wide clips are
# folded to mono and EQ'd towards the plain clips' voice bands (+-6 dB), so every clip sounds like one mic.
BANDS = [("lowpass=f=250", "bass=f=200:t=q:w=0.7:g={g}"),
         ("highpass=f=2500,lowpass=f=6000", "equalizer=f=3900:t=o:w=1.3:g={g}"),
         ("highpass=f=6000", "treble=f=7000:t=q:w=0.7:g={g}")]
MID = "highpass=f=250,lowpass=f=2500"


def rms(src, idx, t0, af):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{t0:.1f}", "-t", "60", "-i", src, "-map", f"0:a:{idx}",
                        "-af", af + ",astats=measure_overall=RMS_level:measure_perchannel=none", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace")
    m = re.findall(r"RMS level dB: (-?[\d.]+|-inf)", r.stderr)
    return float(m[-1]) if m and m[-1] != "-inf" else -120.0


def lufs(i, af):
    t0 = max(0.0, min(60.0, i["dur"] / 2 - 30))
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-ss", f"{t0:.1f}", "-t", "60", "-i", i["src"], "-map", f"0:a:{i['audio_index']}",
                        "-af", af + (",aformat=channel_layouts=stereo" if "pan=mono" in af else "") + ",ebur128", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace")
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1]) if m else -23.0


def voice_profile(i):
    t0 = max(0.0, min(60.0, i["dur"] / 2 - 30))
    src, idx = i["src"], i["audio_index"]
    mid = rms(src, idx, t0, "pan=mono|c0=0.5*c0+0.5*c1")
    side = rms(src, idx, t0, "pan=mono|c0=0.5*c0-0.5*c1")
    m = rms(src, idx, t0, f"pan=mono|c0=0.5*c0+0.5*c1,{MID}")
    return {"width_db": round(side - mid, 1), "bands": [round(rms(src, idx, t0, f"pan=mono|c0=0.5*c0+0.5*c1,{b}") - m, 1) for b, _ in BANDS]}


if not S.get("haul_keep_stereo"):
    for i in info:
        i["voice"] = voice_profile(i)
    wide = lambda i: i["spatial"] or i["voice"]["width_db"] > -15   # noqa: E731
    refs = [i for i in info if not wide(i)]
    for i in info:
        if not wide(i):
            continue
        fx = ["pan=mono|c0=0.5*c0+0.5*c1"]
        if refs:   # duration-weighted voice bands of the plain clips
            tot = sum(r["dur"] for r in refs)
            for k, (_, eq) in enumerate(BANDS):
                g = sum(r["voice"]["bands"][k] * r["dur"] for r in refs) / tot - i["voice"]["bands"][k]
                g = max(-6.0, min(6.0, g))
                if abs(g) >= 1.0:
                    fx.append(eq.format(g=f"{g:.1f}"))
            # the fold drops the side energy (30kg clip 1: -4.5 LU), and the render has no per-clip leveller: match loudness
            ref = sum(lufs(r, "anull") * r["dur"] for r in refs) / tot
            g = max(-10.0, min(10.0, ref - lufs(i, ",".join(fx))))
            if abs(g) >= 0.5:
                fx.append(f"volume={g:.1f}dB")
        i["afix"] = ",".join(fx)
        print(f"{Path(i['src']).name}: {'Spatial Audio, ' if i['spatial'] else ''}stereo width {i['voice']['width_db']} dB "
              f"-> mono + match EQ ({i['afix']})", flush=True)

placebo_ok = None


def needs_fill(i):
    """the clip's shape differs from the canvas (upright clip in a haul, sideways clip in a Short)"""
    return abs(i["w_in"] / i["h_in"] - W / H) > 0.02


def vf_for(i, placebo):
    fill = needs_fill(i)
    # fit inside the canvas: the limiting side is the canvas size, the other side follows (-2 = keep the aspect, even)
    fw, fh = (W, H) if not fill else ((W, -2) if i["w_in"] / i["h_in"] > W / H else (-2, H))
    if placebo:
        tm = (f"libplacebo=w={fw}:h={fh}:fps={FPS}:colorspace=bt709:color_primaries=bt709:color_trc=bt709:"
              f"range=tv:format=yuv420p:tonemapping=bt.2390")
        base = tm
    else:
        tm = ("zscale=t=linear:npl=203,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,"
              if i["hdr"] else "")
        base = f"{tm}scale={fw}:{fh}:flags=lanczos,fps={FPS},format=yuv420p"
    if fill:   # the clip centred on a blurred, zoomed copy of itself
        return (f"{base},split[a][b];[b]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:2[bg];"
                f"[bg][a]overlay=(W-w)/2:(H-h)/2,format=yuv420p")
    return base


def encode(i, dst):
    global placebo_ok
    tries = [True, False] if placebo_ok is not False else [False]
    for pl in tries:
        cmd = ["ffmpeg", "-v", "error", "-stats", "-y"] + (["-init_hw_device", "vulkan"] if pl else []) + [
            "-i", i["src"], "-map", "0:v:0", "-map", f"0:a:{i['audio_index']}",
            "-filter_complex" if needs_fill(i) else "-vf", vf_for(i, pl),
            # sound: resampled with drift correction, padded and cut to the picture's length so both end together
            "-af", (i["afix"] + "," if i.get("afix") else "") + f"aresample=48000:async=1,apad,atrim=0:{i['dur']:.3f}", "-ac", "2",
            "-c:v", "h264_nvenc", "-profile:v", "high", "-pix_fmt", "yuv420p", "-preset", "p5", "-rc", "vbr", "-cq", CQ, "-b:v", "0",
            "-g", str(FPS * 2), "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{i['dur']:.3f}", "-movflags", "+faststart", str(dst)]
        if needs_fill(i):   # filter_complex needs explicit labels
            k = cmd.index("-filter_complex")
            cmd[k + 1] = "[0:v]" + cmd[k + 1] + "[v]"
            cmd[cmd.index("0:v:0")] = "[v]"
        r = subprocess.run(cmd)
        if r.returncode == 0:
            if pl:
                placebo_ok = True
            return "libplacebo (GPU)" if pl else ("zscale + hable" if i["hdr"] else "scale")
        if pl:
            print("libplacebo failed, falling back to zscale on the CPU", flush=True)
            placebo_ok = False
    sys.exit(f"could not normalise {Path(i['src']).name}")


start = 0.0
listing = []
for n, i in enumerate(info):
    st = os.stat(i["src"])
    key = f"{st.st_size}-{int(st.st_mtime)}-{FPS}-{W}x{H}-cq{CQ}-v2" + (f"-a:{i['afix']}" if i.get("afix") else "")
    dst = norm_dir / f"{n + 1:02d} {Path(i['src']).stem}.mp4"
    meta = dst.with_suffix(".json")
    if dst.exists() and meta.exists() and json.loads(meta.read_text()).get("key") == key:
        how = "cached"
    else:
        how = encode(i, dst)
        meta.write_text(json.dumps({"key": key}))
    vd, ad = stream_durs(probe(dst))
    if vd is None or ad is None or abs(vd - ad) > 1.5 / FPS + 0.025:
        dst.unlink(missing_ok=True)
        sys.exit(f"REFUSED {dst.name}: normalised picture {vd} s vs sound {ad} s don't match")
    print(f"clip {n + 1}: {Path(i['src']).name} -> {dst.name} ({how}), picture {vd:.3f} s / sound {ad:.3f} s", flush=True)
    listing.append({**i, "norm": str(dst), "start": round(start, 3), "dur": round(vd, 3)})
    start += vd

# join by stream copy (every piece now has the same codec, size, rate and audio layout)
lst = norm_dir / "concat.txt"
lst.write_text("".join(f"file '{Path(x['norm']).as_posix()}'\n" for x in listing), encoding="utf-8")
sig = json.dumps([(x["norm"], os.path.getmtime(x["norm"])) for x in listing])
sigf = norm_dir / "source.sig"
if not (out.exists() and sigf.exists() and sigf.read_text() == sig):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", "-movflags", "+faststart",
                    str(out)], check=True)
    sigf.write_text(sig)
vd, ad = stream_durs(probe(out))
if vd is None or ad is None or abs(vd - ad) > 0.1:
    sys.exit(f"REFUSED source.mp4: picture {vd} s vs sound {ad} s")
(norm_dir / "clips.json").write_text(json.dumps({"fps": FPS, "w": W, "h": H, "clips": listing}, indent=1), encoding="utf-8")
print(f"source.mp4: {len(listing)} clips, {vd / 60:.1f} min, picture {vd:.2f} s / sound {ad:.2f} s, {FPS} fps", flush=True)

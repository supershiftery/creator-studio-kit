"""QC check for a rendered edit, run BEFORE showing the user any cut.

Idea from Duncan Rogoff "I Finally Solved AI Video Editing" (youtube VVWiJm0sA7Y, job 5):
checking 1 frame per second misses what a viewer sees right away, so look at 10 frames per second
and check for specific mistakes. His six, plus the user's own rules:

  1. repeat   - an animation / shot that plays twice
  2. flash    - a shot or graphic on screen for a split second (A-B-A flash frames, shots < 0.3 s)
  3. brief    - something pops up in part of the frame and is gone in under 1 s (text too fast to read)
  4. cover    - a sudden change inside the face cam box that isn't a cut (graphic covering the face) [--protect]
  5. words    - a word or phrase said twice in a row (Whisper word timestamps)
  6. sync     - lips vs voice: `sync` sub-command measures camera-audio vs mic offset across the recording
  + format (H.264 High yuv420p + AAC, see render-h264-only), black frames, frozen frames, dead air,
    loudness / true peak, and contact sheets at 10 fps for every flag so Claude LOOKS at each one.

Usage:
  python check_video.py check <video.mp4> [--protect x,y,w,h] [--sheets flags|all|none] [--no-words] [--raw]
        --no-words for voiceover-only pieces (intros, MP3 VOs): they have no retakes, the user said 2026-10-20
        --raw for a cut-only draft of a raw recording: skips repeat/brief (phone scrolls trip them)
        --protect is the face cam box as fractions of the frame, e.g. 0.70,0.55,0.28,0.42
        output: <video>_check/report.md, report.json, sheets/*.jpg
  python check_video.py sync <camera.mp4> <mic.wav>   # offset every 60 s; drift = lips drifting
"""
import json
import os
import re
import subprocess
import sys

import cv2
import numpy as np

FPS = 10
W, H = 192, 108


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def ts(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


def probe(path):
    out = json.loads(run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path]).stdout)
    issues, info = [], {"duration": float(out["format"]["duration"])}
    v = next((s for s in out["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in out["streams"] if s["codec_type"] == "audio"), None)
    if v:
        num, den = v["r_frame_rate"].split("/")
        info["fps"] = float(num) / float(den)
        info["video"] = f'{v["codec_name"]} {v.get("profile", "")} {v.get("pix_fmt", "")} {v["width"]}x{v["height"]} {v.get("r_frame_rate")}'
        if v["codec_name"] != "h264" or v.get("pix_fmt") != "yuv420p" or v.get("profile") != "High":
            issues.append(f'video is {info["video"]}, deliver H.264 High yuv420p')
        if (v["width"], v["height"]) not in [(1920, 1080), (3840, 2160)]:
            issues.append(f'size {v["width"]}x{v["height"]} is not 1920x1080 (half-size draft?)')
    if not a:
        issues.append("no audio stream")
    else:
        info["audio"] = f'{a["codec_name"]} {a.get("sample_rate")} Hz {a.get("channels")} ch'
        if a["codec_name"] != "aac":
            issues.append(f'audio is {a["codec_name"]}, deliver AAC')
    if v and a and v.get("duration") and a.get("duration"):
        # picture and sound must be the same length: a broken timebase stretched the picture of Uber codes october
        # to 25:42 over 9:01 of sound (a frozen draft that passed QC with only 4 'frozen' flags, 2026-10-25)
        vd, ad = float(v["duration"]), float(a["duration"])
        if abs(vd - ad) > 1.0:
            issues.append(f'video stream {vd:.1f} s but audio {ad:.1f} s: timestamps broken (frozen picture)')
    return info, issues


def _hwdec():
    """["-hwaccel", "cuda"] only with CHECK_HWDEC=1: measured 2026-10-24 on a 4 min 1080p final it was SLOWER (22 s vs 16 s
    CPU) while another render used the GPU, so the CPU decode stays the default"""
    if os.environ.get("CHECK_HWDEC") != "1":
        return []
    try:
        ok = "cuda" in subprocess.run(["ffmpeg", "-hide_banner", "-hwaccels"], capture_output=True, text=True).stdout
    except Exception:
        ok = False
    return ["-hwaccel", "cuda"] if ok else []


HWDEC = _hwdec()


def frames(path, native_fps):
    """Stream every frame: flash frames are checked at full rate (a 2-frame flash falls between 10 fps
    samples), everything else on a 10 fps copy."""
    # HWDEC: GPU decode, opt-in (see _hwdec)
    p = subprocess.Popen(["ffmpeg", "-v", "error", *HWDEC, "-i", path, "-vf", f"scale={W}:{H},format=gray",
                          "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    step, kept, buf, flashes, i = native_fps / FPS, [], [], [], 0
    while True:
        raw = p.stdout.read(W * H)
        if len(raw) < W * H:
            break
        fr = np.frombuffer(raw, np.uint8).astype(np.float32)
        if i >= len(kept) * step:
            kept.append(fr.reshape(H, W))
        buf = (buf + [fr])[-5:]
        # A-B-A: frames 1..k differ a lot from frame 0, and the frame after them matches frame 0 again
        for k in (1, 2, 3):
            if len(buf) >= k + 2:
                a, mid, b = buf[-k - 2], buf[-k - 1:-1], buf[-1]
                if np.mean(np.abs(a - b)) < 6 and all(np.mean(np.abs(m - a)) > 25 for m in mid):
                    t = (i - k) / native_fps
                    if not flashes or t - flashes[-1]["t"] > 0.5:
                        flashes.append({"type": "flash", "t": t, "end": t + k / native_fps,
                                        "note": f"flash frame: {k} frame(s) of something else, then back"})
        i += 1
    p.wait()
    return np.stack(kept), flashes


def diff(a, b):
    return float(np.mean(np.abs(a - b)))


def visual_checks(f, protect):
    n = len(f)
    d = np.array([0.0] + [diff(f[i], f[i - 1]) for i in range(1, n)])
    cut_th = max(18.0, np.percentile(d, 99) * 0.6)
    cuts = [i for i in range(1, n) if d[i] > cut_th]

    # 2. flash (A-B-A is checked at full frame rate in frames()); here: a still shot < 0.3 s between two HARD cuts.
    # Whip pans / blurred scrolls are runs of high-diff frames, so they are grouped as one transition.
    flags = []
    hard = [c for c in cuts if (c - 1 not in cuts) and (c + 1 not in cuts)]
    for a, b in zip(hard, hard[1:]):
        if b - a <= 3 and np.max(d[a + 1:b], initial=0) < 6 and not any(fl["t"] == a / FPS for fl in flags):
            flags.append({"type": "flash", "t": a / FPS, "end": b / FPS,
                          "note": f"shot only {(b - a) / FPS:.1f} s long between two hard cuts"})

    # 3. brief: a grid cell changes and reverts within 0.2-1.0 s while the rest of the frame stays put
    gy, gx = 4, 4
    ch, cw = H // gy, W // gx
    cutset = set(cuts)
    for y in range(gy):
        for x in range(gx):
            c = f[:, y * ch:(y + 1) * ch, x * cw:(x + 1) * cw]
            cd = np.array([0.0] + [diff(c[i], c[i - 1]) for i in range(1, n)])
            jumps = [i for i in range(1, n) if cd[i] > 25 and i not in cutset]
            for i in jumps:
                for k in range(i + 2, min(n, i + 11)):
                    # the popped thing must HOLD still (text/graphic); moving effects like speed lines don't count
                    held = max(diff(c[m], c[m - 1]) for m in range(i + 1, k)) < 6
                    if held and diff(c[k], c[i - 1]) < 8 and diff(c[i + 1], c[i - 1]) > 20:
                        flags.append({"type": "brief", "t": i / FPS, "end": k / FPS,
                                      "note": f"something in cell row {y + 1} col {x + 1} shows for only {(k - i) / FPS:.1f} s"})
                        break

    # 1. repeat: a moving 1 s+ stretch that matches an earlier stretch within 15 s
    small = np.stack([cv2.resize(fr, (32, 18), interpolation=cv2.INTER_AREA) for fr in f]) if n else f
    i = 0
    while i < n - 10:
        motion = d[i:i + 10].mean()
        if motion < 3:
            i += 1
            continue
        best = None
        for j in range(max(0, i - 150), i - 15):
            if np.mean(np.abs(small[i] - small[j])) < 4:
                run_len = 0
                while i + run_len < n and np.mean(np.abs(small[i + run_len] - small[j + run_len])) < 5:
                    run_len += 1
                if run_len >= 10 and (best is None or run_len > best[1]):
                    best = (j, run_len)
        if best:
            j, r = best
            flags.append({"type": "repeat", "t": i / FPS, "end": (i + r) / FPS,
                          "note": f"{r / FPS:.1f} s here repeats {ts(j / FPS)} (animation/shot plays twice?)"})
            i += r
        else:
            i += 1

    # 4. cover: sudden change inside the face cam box that is not a full cut
    if protect:
        px, py, pw, ph = protect
        x0, y0, x1, y1 = int(px * W), int(py * H), int((px + pw) * W), int((py + ph) * H)
        r = f[:, y0:y1, x0:x1]
        last = -99
        for i in range(1, n):
            if i not in cutset and diff(r[i], r[i - 1]) > 22 and i - last > 10:
                flags.append({"type": "cover", "t": i / FPS, "end": i / FPS + 0.5,
                              "note": "sudden change inside the face cam box (graphic covering the face?)"})
                last = i
    return flags, len(cuts)


def ffmpeg_detects(path):
    flags = []
    # the two ffmpeg passes run side by side (2026-10-24 speed pass; same output, each pass decodes on its own)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(2) as ex:
        f1 = ex.submit(run, ["ffmpeg", "-v", "info", "-i", path, "-vf", "blackdetect=d=0.15:pix_th=0.06,freezedetect=n=0.002:d=2.5",
                             "-af", "silencedetect=n=-45dB:d=1.5", "-f", "null", "-"])
        f2 = ex.submit(run, ["ffmpeg", "-v", "info", "-i", path, "-af", "loudnorm=print_format=json", "-f", "null", "-"])
        err, loud = f1.result().stderr, f2.result().stderr
    for m in re.finditer(r"black_start:([\d.]+) black_end:([\d.]+)", err):
        flags.append({"type": "black", "t": float(m[1]), "end": float(m[2]), "note": "black frames (intended dip?)"})
    for s, e in re.findall(r"freeze_start: ([\d.]+).*?freeze_end: ([\d.]+)", err, re.S):
        flags.append({"type": "frozen", "t": float(s), "end": float(e), "note": f"picture frozen {float(e) - float(s):.1f} s (title hold or stuck render?)"})
    for s, e in re.findall(r"silence_start: ([\d.]+).*?silence_end: ([\d.]+)", err, re.S):
        flags.append({"type": "dead-air", "t": float(s), "end": float(e), "note": f"near-silence {float(e) - float(s):.1f} s"})
    j = json.loads(loud[loud.rfind("{"):loud.rfind("}") + 1])
    return flags, {"lufs": float(j["input_i"]), "true_peak": float(j["input_tp"])}


def word_checks(path):
    from faster_whisper import WhisperModel
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                         capture_output=True).stdout
    audio = np.frombuffer(raw, np.int16).astype(np.float32) / 32768  # array input: PyAV decode is broken here
    model = WhisperModel("small.en", device="cpu", compute_type="int8")
    # Whisper silently drops repeated words; a disfluent prompt + no carry-over keeps it verbatim
    segs, _ = model.transcribe(audio, word_timestamps=True, vad_filter=True, condition_on_previous_text=False,
                               initial_prompt="Um, so, so I I was, uh, the the thing is, like, like this.")
    words = [{"w": re.sub(r"[^a-z0-9']", "", w.word.lower()), "t": w.start, "e": w.end} for s in segs for w in s.words]
    words = [w for w in words if w["w"]]
    flags = []
    for n_gram in (3, 2, 1):
        for i in range(len(words) - 2 * n_gram + 1):
            a = [w["w"] for w in words[i:i + n_gram]]
            b = [w["w"] for w in words[i + n_gram:i + 2 * n_gram]]
            if a == b and words[i + n_gram]["t"] - words[i]["t"] < 4 and not any(f["t"] == words[i]["t"] for f in flags):
                flags.append({"type": "words", "t": words[i]["t"], "end": words[i + 2 * n_gram - 1]["t"] + 0.4,
                              "note": f'said twice: "{" ".join(a)} {" ".join(b)}"'})
    # Whisper often swallows a doubled word and stretches its neighbour instead
    for k, w in enumerate(words):
        if not re.search(r"\d", w["w"]) and w["e"] - w["t"] > max(1.2, 0.3 + 0.09 * len(w["w"])) and (k + 1 == len(words) or words[k + 1]["t"] - w["e"] < 0.15):
            flags.append({"type": "words", "t": w["t"], "end": w["e"],
                          "note": f'"{w["w"]}" lasts {w["e"] - w["t"]:.1f} s: listen for a hidden repeat or stretched word'})
    flags += echo_checks(audio)
    return flags, " ".join(w["w"] for w in words)


def echo_checks(audio, sr=16000):
    """Audio that is nearly identical to what was heard 0.3-3 s earlier = the same words twice (a retake left in
    or a doubled clip). Works on the full mix because the voice sits ~17 LU over the music."""
    hop, win = 160, 512
    nfr = (len(audio) - win) // hop
    if nfr < 100:
        return []
    idx = np.arange(win)[None, :] + hop * np.arange(nfr)[:, None]
    spec = np.abs(np.fft.rfft(audio[idx] * np.hanning(win), axis=1))
    freqs = np.fft.rfftfreq(win, 1 / sr)
    edges = np.geomspace(300, 4000, 33)
    bands = np.stack([spec[:, (freqs >= lo) & (freqs < hi)].mean(1) for lo, hi in zip(edges, edges[1:])], 1)
    energy = 20 * np.log10(bands.mean(1) + 1e-9)
    X = np.log(bands + 1e-6)
    X -= X.mean(0)
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
    speech = energy > np.percentile(energy, 60)
    flags, ker = [], np.ones(40) / 40
    for lag in range(30, 300):
        sim = np.convolve(np.sum(X[lag:] * X[:-lag], 1) * speech[lag:], ker, "same")
        for t in np.where(sim > 0.9)[0]:
            ts_ = (t + lag) * hop / sr
            if not any(abs(f["t"] - ts_) < 1.5 for f in flags):
                flags.append({"type": "words", "t": ts_ - 0.2, "end": ts_ + 0.2,
                              "note": f"audio repeats what was heard {lag / 100:.1f} s earlier (same words twice?)"})
    return flags


def sheet(path, t0, out, label, cols=6, rows=5):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0, t0):.2f}", "-i", path, "-t", f"{cols * rows / FPS:.2f}",
                          "-vf", f"fps={FPS},scale=320:180", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                         capture_output=True).stdout
    imgs = np.frombuffer(raw, np.uint8).reshape(-1, 180, 320, 3)
    if not len(imgs):
        return
    grid = np.zeros((rows * 180 + 30, cols * 320, 3), np.uint8)
    cv2.putText(grid, label[:110], (6, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 220, 255), 1, cv2.LINE_AA)
    for k, im in enumerate(imgs[:cols * rows]):
        y, x = 30 + (k // cols) * 180, (k % cols) * 320
        grid[y:y + 180, x:x + 320] = im
        cv2.putText(grid, ts(max(0, t0) + k / FPS), (x + 4, y + 172), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.imwrite(out, grid, [cv2.IMWRITE_JPEG_QUALITY, 80])


def check(path, protect=None, sheets="flags", words=True, raw=False):
    out_dir = os.path.splitext(path)[0] + "_check"
    os.makedirs(os.path.join(out_dir, "sheets"), exist_ok=True)
    info, format_issues = probe(path)
    print("probe:", info)
    # the ffmpeg detect passes run while this process scans the frames (2026-10-24 speed pass: three full decodes were
    # back to back; the results are the same)
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(1)
    det = pool.submit(ffmpeg_detects, path)
    f, flashes = frames(path, info["fps"])
    flags, n_cuts = visual_checks(f, protect)
    if raw:  # raw side-by-side recording: phone scrolls / loading screens trip repeat+brief; check those on the final layout
        flags = [x for x in flags if x["type"] not in ("repeat", "brief")]
    flags += flashes
    more, loud = det.result()
    pool.shutdown()
    flags += more
    transcript = ""
    if words:
        wf, transcript = word_checks(path)
        flags += wf
    flags.sort(key=lambda x: x["t"])
    if loud["true_peak"] > -1.0:
        format_issues.append(f'true peak {loud["true_peak"]} dBTP, keep it under -1')
    # BROKEN = the render itself is wrong; the step exits 3 so the build fails and no AI QC can call it "fine"
    # (Uber codes october draft 1, 2026-10-25: 8:40 of picture over 25 min of sound, 4 frozen flags, AI said fine)
    broken = [x for x in format_issues if "timestamps broken" in x]
    broken += [f"picture frozen {x['end'] - x['t']:.0f} s at {ts(x['t'])} (stuck or stretched render)"
               for x in flags if x["type"] == "frozen" and x["end"] - x["t"] >= 30]

    if sheets == "all":
        t = 0.0
        while t < info["duration"]:
            sheet(path, t, os.path.join(out_dir, "sheets", f"all_{int(t * 10):05d}.jpg"), f"{ts(t)} - {ts(t + 3)}")
            t += 3.0
    elif sheets == "flags":
        for k, fl in enumerate(flags):
            if fl["type"] in ("dead-air", "words"):
                continue
            fl["sheet"] = f"sheets/flag_{k:03d}_{fl['type']}.jpg"
            sheet(path, fl["t"] - 1.0, os.path.join(out_dir, fl["sheet"]), f'{fl["type"]} @ {ts(fl["t"])}: {fl["note"]}')

    report = {"video": path, "info": info, "loudness": loud, "cuts": n_cuts,
              "cuts_per_min": round(n_cuts / max(info["duration"], 1) * 60, 1),
              "format_issues": format_issues, "broken": broken, "flags": flags, "transcript": transcript}
    json.dump(report, open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8"), indent=1)
    lines = [f"# QC: {os.path.basename(path)}", "",
             f"- {info.get('video')} / {info.get('audio')} / {info['duration']:.1f} s",
             f"- loudness {loud['lufs']} LUFS, true peak {loud['true_peak']} dBTP, {n_cuts} cuts ({report['cuts_per_min']}/min)", ""]
    lines += [f"- ❌ BROKEN: {x}" for x in broken]
    lines += [f"- FORMAT: {x}" for x in format_issues]
    lines += ["", "| time | check | note | sheet |", "|---|---|---|---|"]
    lines += [f"| {ts(x['t'])} | {x['type']} | {x['note']} | {x.get('sheet', '')} |" for x in flags]
    open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    counts = {}
    for x in flags:
        counts[x["type"]] = counts.get(x["type"], 0) + 1
    print(f"{len(flags)} flags {counts}; format issues: {format_issues or 'none'}")
    print("report:", os.path.join(out_dir, "report.md"))
    for x in broken:
        print(f"!! BROKEN RENDER: {x}")
    return broken


def sync(cam, mic):
    """Cross-correlate the camera's scratch audio with the mic in 20 s windows every 60 s."""
    from scipy.signal import correlate

    def load(p):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                             capture_output=True).stdout
        x = np.abs(np.frombuffer(raw, np.int16).astype(np.float32))
        return np.convolve(x, np.ones(40) / 40, "same")[::8]  # 1 kHz envelope, 1 ms steps

    a, b = load(cam), load(mic)
    rate, win, maxlag = 1000, 20000, 1000
    rows = []
    for start in range(maxlag, min(len(a), len(b)) - win - maxlag, 60000):
        x = a[start:start + win] - a[start:start + win].mean()
        y = b[start - maxlag:start + win + maxlag] - b[start - maxlag:start + win + maxlag].mean()
        c = correlate(y, x, "valid")
        lag = int(np.argmax(c)) - maxlag
        rows.append((start / rate, lag))
        print(f"{ts(start / rate)}  mic is {lag:+d} ms vs camera  (picture {'behind' if lag < 0 else 'ahead of'} sound)")
    if rows:
        lags = [r[1] for r in rows]
        print(f"median {int(np.median(lags)):+d} ms, drift {max(lags) - min(lags)} ms across the recording "
              f"({'fixed offset: shift once' if max(lags) - min(lags) <= 20 else 'DRIFTING: re-sync per section'})")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] not in ("check", "sync"):
        print(__doc__)
        sys.exit(1)
    if args[0] == "sync":
        sync(args[1], args[2])
    else:
        prot = None
        if "--protect" in args:
            prot = [float(v) for v in args[args.index("--protect") + 1].split(",")]
        mode = args[args.index("--sheets") + 1] if "--sheets" in args else "flags"
        if check(args[1], prot, mode, "--no-words" not in args, "--raw" in args):
            sys.exit(3)

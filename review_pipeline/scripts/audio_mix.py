"""Two-mic switching. When raw/camera.mp4 has a second audio track (the DJI clip-on),
swap to it wherever the main mic (track 1, Focusrite) drops super low — e.g. the try-on
section where he walks away. Hard cuts, no crossfade (it's a new section).

Runs before everything else: raw/camera.mp4 is replaced by the mixed version, the
original is kept as raw/camera_original.mp4. Cached: if the original backup exists,
the mix is already done. Settings: "audio_mix" in config.json.
"""
import json, math, re, shutil, subprocess, sys, time
from pathlib import Path


def _move(src, dst, tries=6):
    """shutil.move with retries — Windows/GoogleDriveFS can hold a brief lock on the file."""
    for i in range(tries):
        try:
            shutil.move(str(src), str(dst))
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))

import numpy as np

HERE = Path(__file__).resolve().parent

DEFAULTS = {
    "enabled": True,
    "window_seconds": 0.5,       # loudness measured per window
    "drop_below_db": 14,         # this far under the median window = "super low"
    "floor_db": -48,             # never switch above this absolute level
    "min_seconds": 1.5,          # low must last at least this long before switching
    "merge_gap_seconds": 2.0,    # DJI runs closer than this merge into one
    "pad_seconds": 0.4,          # start the DJI run slightly before the drop
    "hide_facecam": True,        # hide the face circle during away-from-mic segments
    "hide_merge_gap_seconds": 8.0,
    "hide_min_seconds": 3.0,
    "boost_when_no_second_track": True,  # Gling exports keep one track: lift the quiet parts instead
    "boost_cap_db": 12,
}


def _cfg(cfg):
    ac = dict(DEFAULTS)
    ac.update((cfg or {}).get("audio_mix", {}))
    return ac


def audio_stream_count(path: Path) -> int:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a",
                        "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return len([l for l in r.stdout.strip().splitlines() if l.strip()])


def swap_track_count(path: Path, work: Path, checks: list = None) -> int:
    """audio_stream_count, but a DJI track that never carries sound (receiver off / unplugged) doesn't count: swapping to
    it replaced the voice with digital silence (dhgate asics 2026-10-22: track 1 flat at -91 dB, 2.6 min of the review
    muted, "let's dive right into it" cut off). Such a recording takes the boost path like a one-track file."""
    n = audio_stream_count(path)
    if n < 2:
        return n
    work.mkdir(exist_ok=True)
    db, _ = _windows_db(path, 1, work)
    if len(db) and float(np.percentile(db, 99)) < -80:
        if checks is not None:
            # not a mistake (user 2026-10-25): a silent DJI track just means he didn't use that mic this time
            checks.append("FYI: no DJI mic on this recording (second track silent), so the main mic was used throughout "
                          "and its quiet parts were boosted.")
        return 1
    return n


def _window_db(pcm: np.ndarray, sr: int, win: float) -> np.ndarray:
    n = int(sr * win)
    if n == 0 or len(pcm) < n:
        return np.array([])
    pcm = pcm[: len(pcm) // n * n]
    rms = np.sqrt((pcm.reshape(-1, n) ** 2).mean(axis=1))
    return 20 * np.log10(np.maximum(rms, 1e-8))


def find_dji_ranges(cam: Path, work: Path, ac, track: int = 0) -> list:
    """Source-time ranges where the main mic (given track) is super low -> use the DJI."""
    work.mkdir(exist_ok=True)
    wav = work / "mic_main_16k.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(cam), "-map", f"0:a:{track}",
                    "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
                   check=True, capture_output=True)
    import wave
    with wave.open(str(wav)) as w:
        sr, raw = w.getframerate(), w.readframes(w.getnframes())
    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    wav.unlink(missing_ok=True)
    win = ac["window_seconds"]
    db = _window_db(pcm, sr, win)
    if len(db) == 0:
        return []
    floor = max(ac["floor_db"], float(np.median(db)) - ac["drop_below_db"])
    low = db < floor
    min_w = max(1, round(ac["min_seconds"] / win))
    gap_w = round(ac["merge_gap_seconds"] / win)
    # find low runs of at least min_w windows
    ranges, i = [], 0
    while i < len(low):
        if not low[i]:
            i += 1
            continue
        j = i
        while j < len(low) and low[j]:
            j += 1
        if j - i >= min_w:
            ranges.append([i, j])  # window indices
        i = j
    # merge runs separated by a short gap
    merged = []
    for r in ranges:
        if merged and r[0] - merged[-1][1] <= gap_w:
            merged[-1][1] = r[1]
        else:
            merged.append(list(r))
    dur = len(pcm) / sr
    pad = ac["pad_seconds"]
    # the pad only reaches back into quiet: a swap that opens 0.4 s early inside the last word put "luck" on the other
    # mic ("out of | luck" sounded distorted, dhgate rick owens 2026-10-22, 5:26)
    speech = floor + ac.get("pad_speech_db", 6.0)
    return [(max(0.0, a * win - (pad if a == 0 or db[a - 1] < speech else 0.0)), min(dur, b * win)) for a, b in merged]


def find_gap_ranges(cam: Path, work: Path, ac, main_track: int = 0, dji_track: int = 1) -> list:
    """Second away test for two-mic files: where the DJI sits far louder than the condenser compared with
    their usual desk relation, he is away from the desk even if the condenser still catches him. The
    median-based floor in find_dji_ranges bottoms out on long recordings that are mostly quiet (amiri jeans
    2026-10-22, 2:45-3:12: floor -48 dB, the condenser caught the star-jeans try-on at -42 dB = 15 dB under
    desk speech while the DJI was 24 dB louder -> "it's using the wrong mic")."""
    c, win = _windows_db(cam, main_track, work)
    d, _ = _windows_db(cam, dji_track, work)
    n = min(len(c), len(d))
    if n < 10:
        return []
    c, d = c[:n], d[:n]
    k = max(1, round(ac.get("gap_window_seconds", 3.0) / win))
    pad = np.pad(np.arange(n), (k // 2, k - 1 - k // 2), mode="edge")
    idx = np.lib.stride_tricks.sliding_window_view(pad, k)
    cr, dr = np.percentile(c[idx], 85, axis=1), np.percentile(d[idx], 85, axis=1)
    diff = dr - cr
    desk = c >= np.percentile(c, 70)                    # condenser picking up speech = at the desk
    desk_gap = float(np.median((d - c)[desk]))
    # ...and the condenser itself well under desk speech: holding a product up at the desk drops it only ~5 dB
    desk_speech = float(np.median(cr[desk]))
    away = ((diff > desk_gap + ac.get("gap_margin_db", 8.0)) & (dr >= np.percentile(d, 85) - 10)
            & (cr < desk_speech - ac.get("gap_condenser_drop_db", 10.0)))
    runs, i = [], 0
    min_w, gap_w = round(ac.get("gap_min_seconds", 3.0) / win), round(ac.get("gap_merge_seconds", 8.0) / win)
    while i < n:
        if not away[i]:
            i += 1
            continue
        j = i
        while j < n and away[j]:
            j += 1
        if j - i >= min_w:
            if runs and i - runs[-1][1] <= gap_w:
                runs[-1][1] = j
            else:
                runs.append([i, j])
        i = j
    return [(a * win, b * win) for a, b in runs]


def union_ranges(*lists) -> list:
    out = []
    for a, b in sorted(r for l in lists for r in l):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _track_lufs(cam: Path, track: int) -> float:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(cam), "-map", f"0:a:{track}",
                        "-af", "ebur128", "-vn", "-f", "null", "-"], capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    return float(m[-1]) if m else -23.0


def _windows_db(cam: Path, track: int, work: Path, win: float = 0.5):
    """Per-window RMS dB of one audio track (16 kHz mono decode, cached nowhere)."""
    import wave
    tmp = work / f"_gm_{track}.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(cam), "-map", f"0:a:{track}",
                    "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(tmp)], check=True, capture_output=True)
    with wave.open(str(tmp)) as w:
        sr, raw = w.getframerate(), w.readframes(w.getnframes())
    tmp.unlink(missing_ok=True)
    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    n = int(sr * win)
    pcm = pcm[: len(pcm) // n * n]
    return 20 * np.log10(np.maximum(np.sqrt((pcm.reshape(-1, n) ** 2).mean(axis=1)), 1e-8)), win


def mix(cam: Path, dji_ranges: list, duration: float, out: Path, ac=None, work=None,
        main_track: int = 0, dji_track: int = 1):
    """Hard-cut between the main track and the DJI track over the given ranges; video copied.
    Done as a volume envelope (no re-segmentation — segment concat drifts on AAC frame edges).
    DJI gain match: speech-percentile level of the DJI inside the swap ranges vs the main
    mic outside them (integrated LUFS is wrong — room tone dominates the DJI track)."""
    gain_db = 0.0
    if (ac or {}).get("dji_gain_match", True) and dji_ranges and work is not None:
        main_db, win = _windows_db(cam, main_track, work)
        dji_db, _ = _windows_db(cam, dji_track, work)
        in_r = np.zeros(len(main_db), bool)
        for a, b in dji_ranges:
            in_r[int(a / win): int(b / win) + 1] = True
        p = (ac or {}).get("dji_gain_percentile", 85)  # speech-level match, not median —
        main_ref = float(np.percentile(main_db[~in_r], p)) if (~in_r).any() else float(np.percentile(main_db, p))
        dji_ref = float(np.percentile(dji_db[in_r], p)) if in_r.any() else float(np.percentile(dji_db, p))
        gain_db = main_ref - dji_ref
        cap = abs((ac or {}).get("dji_gain_cap_db", 15))
        gain_db = max(-cap, min(cap, gain_db))
    e = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in dji_ranges)
    graph = (f"[0:a:{main_track}]aformat=sample_rates=48000:channel_layouts=stereo,volume=eval=frame:volume='1-({e})'[m];"
             f"[0:a:{dji_track}]aformat=sample_rates=48000:channel_layouts=stereo,volume={gain_db:.1f}dB,"
             f"volume=eval=frame:volume='{e}'[d];"
             f"[m][d]amix=inputs=2:normalize=0[a]")
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(cam), "-filter_complex", graph,
           "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


def boost_low(cam: Path, ranges: list, duration: float, out: Path, ac):
    """No DJI track (e.g. Gling stripped it): lift the low (away-from-mic) segments toward the
    median instead, with short fades on the segment edges so the gain steps don't click."""
    wav = None
    # per-segment boost: median of all windows minus segment's own level, capped
    tmp = out.parent / "_boost_probe.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(cam), "-map", "0:a:0",
                    "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(tmp)], check=True, capture_output=True)
    import wave
    with wave.open(str(tmp)) as w:
        sr, raw = w.getframerate(), w.readframes(w.getnframes())
    tmp.unlink(missing_ok=True)
    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    # gain = desk SPEECH level minus the range's speech level (P85 of 0.5 s windows, like the DJI gain
    # match). Averages that include silence made a short pause-range read low and boosted the normal-level
    # word inside it (dhgate asics 2026-10-22: "dive right into it" came out ~5 dB hot at 1:06).
    win, pct = 0.5, ac.get("dji_gain_percentile", 85)
    db = _window_db(pcm, sr, win)
    inside = np.zeros(len(db), bool)
    for a, b in ranges:
        inside[int(a / win): int(b / win) + 1] = True
    desk = float(np.percentile(db[~inside], pct)) if (~inside).any() else float(np.percentile(db, pct))
    # per-range gain as a linear-amplitude envelope (no re-segmentation — concat drifts on AAC frames)
    terms = []
    for a, b in ranges:
        if b - a < ac.get("boost_min_seconds", 8.0):
            continue    # short dips are pauses at a cut, not him walking away from the mic
        seg = db[int(a / win): int(b / win) + 1]
        lvl = float(np.percentile(seg, pct)) if len(seg) else desk
        # ...and never lift any word in the range above desk speech (+1 dB): a range that holds a desk-level
        # word next to a pause is a pause, not him walking away
        top = float(seg.max()) if len(seg) else desk
        gain_db = min(ac["boost_cap_db"], max(0.0, desk - lvl), max(0.0, desk + 1.0 - top))
        if gain_db < ac.get("boost_min_db", 2.0):
            continue
        terms.append(f"({10 ** (gain_db / 20):.4f}-1)*between(t,{a:.3f},{b:.3f})")
    e = "1" + ("+" + "+".join(terms) if terms else "")
    graph = f"[0:a:0]aformat=sample_rates=48000:channel_layouts=stereo,volume=eval=frame:volume='{e}'[a]"
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(cam), "-filter_complex", graph,
           "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


def hide_ranges(ranges: list, ac) -> list:
    """Away segments merged for face-cam hiding: close gaps (he steps back to the mic mid-try-on)
    and drop tiny blips so the circle doesn't flicker."""
    gap, min_len = ac["hide_merge_gap_seconds"], ac["hide_min_seconds"]
    merged = []
    for a, b in ranges:
        if merged and a - merged[-1][1] <= gap:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [[round(a, 2), round(b, 2)] for a, b in merged if b - a >= min_len]


def _clip_to_kept(ranges: list, kept, min_seconds: float = 1.0):
    """Drop swap/boost moments that fall outside the kept footage (else a 0.3 s DJI blip
    lands right before a cut). Fragments shorter than min_seconds go too."""
    out = []
    for a, b in ranges:
        for ka, kb in kept:
            lo, hi = max(a, ka), min(b, kb)
            if hi - lo >= min_seconds:
                out.append((lo, hi))
    return out


def ensure_mixed(project: Path, cfg: dict, checks: list, source: Path = None, kept=None):
    """Two-mic handling, before transcription/edit: swap to the DJI track when present, else
    boost the low (away-from-mic) segments. Always records away ranges for face-cam hiding.

    source=... (XML edit-list mode): mix FROM that original file INTO raw/camera.mp4 —
    the original is never modified or moved. kept=... clips ranges to the kept footage."""
    raw = project / "raw"
    cam, orig, mixed = raw / "camera.mp4", raw / "camera_original.mp4", raw / "camera_mixed.mp4"
    ac = _cfg(cfg)
    if not ac["enabled"]:
        return
    if source is not None:
        if cam.exists():  # already built from the original
            return
        _ensure_from_source(project, source, cfg, checks, kept=kept)
        return
    work = project / "work"
    if orig.exists() and cam.exists():
        # a swap mix cached BEFORE the dead-DJI guard existed: rebuild it from the original (dhgate yeezy slides
        # 2026-10-23: track 2 was -180 dB all 11 min, every quiet dip swapped to it and muted the word at the edge —
        # "dive right into [it]", "unbox [it]", "how to buy" all cut off at the cut)
        prev = json.loads((work / "audio_mix.json").read_text(encoding="utf-8")) if (work / "audio_mix.json").exists() else {}
        if prev.get("mode") == "swap" and swap_track_count(orig, work) < 2:
            cam.unlink()
            _move(orig, cam)
            for f in ("audio_mix.json", "levels.json", "mic16k.wav"):
                (work / f).unlink(missing_ok=True)
            checks.append("The cached mic mix had swapped to a DJI track that is silent the whole recording; "
                          "it was rebuilt from raw/camera_original.mp4 (boost instead of swap).")
    if orig.exists() or not cam.exists():
        return
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(cam)], capture_output=True, text=True)
    duration = float(r.stdout.strip())
    ranges = find_dji_ranges(cam, work, ac)
    n_tracks = swap_track_count(cam, work, checks)
    if n_tracks >= 2 and ac.get("gap_away", True):
        ranges = union_ranges(ranges, find_gap_ranges(cam, work, ac))
    if not ranges:
        if n_tracks >= 2:
            checks.append("camera.mp4 has a second audio track (DJI) but the main mic never dropped low enough to use it.")
        (work / "audio_mix.json").write_text(json.dumps({"mode": "none", "ranges": [], "hide_ranges": []}, indent=2), encoding="utf-8")
        shutil.copy2(cam, orig)  # mark as processed so we don't re-scan every run
        return
    info = {"mode": "swap" if n_tracks >= 2 else "boost",
            "ranges": [[round(a, 2), round(b, 2)] for a, b in ranges],
            "hide_ranges": hide_ranges(ranges, ac),
            "seconds": round(sum(b - a for a, b in ranges), 1)}
    if n_tracks >= 2:
        mix(cam, ranges, duration, mixed, ac=ac, work=work)
    elif ac["boost_when_no_second_track"]:
        boost_low(cam, ranges, duration, mixed, ac)
    else:
        (work / "audio_mix.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
        return
    _move(cam, orig)
    _move(mixed, cam)
    (work / "audio_mix.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    if info["mode"] == "swap":
        checks.append(f"DJI mic used for {info['seconds'] / 60:.1f} min across {len(ranges)} switch(es) "
                      f"(main mic super low — try-on section). Original audio kept in raw/camera_original.mp4.")
    else:
        checks.append(f"No DJI track in this file (Gling export keeps one track), so the away-from-mic parts "
                      f"({info['seconds'] / 60:.1f} min) were boosted instead of swapped. "
                      f"Face cam is hidden while he's away. Original kept in raw/camera_original.mp4.")


def ensure_source(project: Path, source: Path):
    """XML mode, phase 1: put the original at raw/camera.mp4 so transcription/analysis can
    run BEFORE the mic mix is decided. COPY, never hardlink — a later move/write onto a
    hardlink would write through to the original and destroy it."""
    cam = project / "raw" / "camera.mp4"
    if cam.exists():
        return
    shutil.copy2(source, cam)


def compute_block(away_ranges, kept, screen_starts, ac):
    """The try-on block: from the first real away-from-mic segment (>=8 s) to the moment the
    screen recording appears. Edges snap to Gling cuts (wide window — audio detection lags
    the visual step-away by several seconds). Returns (start, end) or None."""
    merged = hide_ranges(away_ranges, ac)  # 8 s-gap merge first, else try-on fragments
    big = [r for r in merged if r[1] - r[0] >= ac.get("hide_block_min_seconds", 8.0)]
    if not big:
        return None
    import xml_cuts
    start = xml_cuts.snap(big[0][0], kept, max_dist=ac.get("block_snap_seconds", 10.0))
    end = next((x for x in screen_starts if x > big[0][0]), None)
    if end is None:
        end = big[-1][1]
    end = xml_cuts.snap(end, kept, max_dist=ac.get("block_snap_seconds", 10.0))
    return (min(start, end), max(start, end))


def identify_tracks(source: Path, work: Path, kept, ac):
    """Which audio track is the condenser (desk) and which is the DJI (clip-on)?
    Condenser = loudest during the desk window (first kept clip). DJI = loudest during the
    try-on window (where the condenser is quiet). Never trust track ORDER."""
    n = audio_stream_count(source)
    if n < 2:
        return 0, None, 0.5
    dbs, win = [], 0.5
    for t in range(n):
        d, win = _windows_db(source, t, work)
        dbs.append(d)
    ka, kb = kept[0]
    desk = slice(int(ka / win), int(min(ka + 20, kb) / win))
    desk_lv = [np.percentile(d[desk], ac.get("dji_gain_percentile", 85)) if desk.stop > desk.start else -99
               for d in dbs]
    condenser = int(np.argmax(desk_lv))
    # try-on window = where the condenser is >drop_below_db under its own desk level
    thresh = desk_lv[condenser] - ac["drop_below_db"]
    away_idx = np.where(dbs[condenser] < thresh)[0]
    dji, dji_lv = None, -99
    if len(away_idx):
        s = slice(int(away_idx[0]), int(away_idx[-1]) + 1)
        # a track that never carries sound (receiver off, empty OBS track) is never the DJI
        cand = [(t, float(np.percentile(dbs[t][s], 60))) for t in range(n)
                if t != condenser and len(dbs[t]) and float(np.percentile(dbs[t], 99)) >= -80]
        if cand:
            dji, dji_lv = max(cand, key=lambda x: x[1])
    return condenser, dji, win


def apply_block_mix(project: Path, cfg: dict, checks: list, source: Path, kept, screen_runs):
    """XML mode, phase 2 (after analysis): one mic per section, fully automatic —
    identifies the mics by measurement, DJI for the whole try-on block, condenser elsewhere.
    Block: first real away segment (snapped to cuts) -> the cut where the computer segment
    starts (the kept clip containing the first screen run), NOT the screen frame itself."""
    raw, work = project / "raw", project / "work"
    cam, mixed = raw / "camera.mp4", raw / "camera_mixed.mp4"
    ac = _cfg(cfg)
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(source)], capture_output=True, text=True)
    duration = float(r.stdout.strip())
    condenser, dji, win = identify_tracks(source, work, kept, ac)
    away = _clip_to_kept(find_dji_ranges(source, work, ac, track=condenser), kept)
    block = compute_block(away, kept, [x[0] for x in screen_runs], ac) if ac.get("swap_block", True) else None
    if block:
        # end at the CUT where the computer segment starts: the kept clip that contains
        # the first real screen run — not the screen frame itself (he's already talking
        # at the desk in that clip's opening)
        for rs, re_ in screen_runs:
            if rs > block[0]:
                containing = next((ka for ka, kb in kept if ka <= rs < kb), None)
                block = (block[0], containing if containing is not None else block[1])
                break
        ranges = _clip_to_kept([block], kept, min_seconds=1.0)
        hide = [list(block)]
    else:
        ranges, hide = away, hide_ranges(away, ac)
    info = {"mode": "swap" if dji is not None and ranges else ("boost" if ranges else "none"),
            "ranges": [[round(a, 2), round(b, 2)] for a, b in ranges],
            "hide_ranges": hide,
            "seconds": round(sum(b - a for a, b in ranges), 1),
            "tracks": {"condenser": condenser, "dji": dji}}
    if dji is not None and ranges:
        mix(source, ranges, duration, mixed, ac=ac, work=work, main_track=condenser, dji_track=dji)
        checks.append(f"DJI mic (track {dji + 1}) for the whole try-on block ({info['seconds'] / 60:.1f} min, "
                      f"{len(ranges)} kept clip(s)), gain-matched to the condenser (track {condenser + 1}).")
    elif ranges and ac["boost_when_no_second_track"]:
        boost_low(source, ranges, duration, mixed, ac)
        info["mode"] = "boost"
        checks.append(f"Only one usable audio track, so the away-from-mic block "
                      f"({info['seconds'] / 60:.1f} min) was boosted. Face cam is hidden while he's away.")
    else:
        (work / "audio_mix.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
        return
    cam.unlink(missing_ok=True)  # CRITICAL: unlink first — a move onto a
                                 # hardlink path writes THROUGH it and destroys the original
    _move(mixed, cam)
    (work / "audio_mix.json").write_text(json.dumps(info, indent=2), encoding="utf-8")


def _ensure_from_source(project: Path, source: Path, cfg: dict, checks: list, kept=None):
    """XML mode: build raw/camera.mp4 from the untouched original (all audio tracks present)."""
    raw, work = project / "raw", project / "work"
    cam, mixed = raw / "camera.mp4", raw / "camera_mixed.mp4"
    ac = _cfg(cfg)
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(source)], capture_output=True, text=True)
    duration = float(r.stdout.strip())
    ranges = find_dji_ranges(source, work, ac)
    if kept:
        ranges = _clip_to_kept(ranges, kept)
    hide = hide_ranges(ranges, ac)
    if ac.get("swap_block", True):
        # one mic for the whole try-on block: from the first real away segment to the last —
        # no jumping back and forth between Focusrite and DJI mid-try-on
        big = [r for r in hide if r[1] - r[0] >= ac.get("hide_block_min_seconds", 8.0)]
        if big:
            block = (big[0][0], big[-1][1])
            ranges = _clip_to_kept([block], kept, min_seconds=1.0) if kept else [block]
    n_tracks = swap_track_count(source, work, checks)
    info = {"mode": "swap" if n_tracks >= 2 and ranges else ("boost" if ranges else "none"),
            "ranges": [[round(a, 2), round(b, 2)] for a, b in ranges],
            "hide_ranges": hide,
            "seconds": round(sum(b - a for a, b in ranges), 1)}
    if n_tracks >= 2 and ranges:
        mix(source, ranges, duration, mixed, ac=ac, work=work)
        _move(mixed, cam)
        checks.append(f"DJI mic used for {info['seconds'] / 60:.1f} min across {len(ranges)} switch(es) "
                      f"(main mic super low — try-on section). Original untouched at {source.name}.")
    elif ranges and ac["boost_when_no_second_track"]:
        boost_low(source, ranges, duration, mixed, ac)
        _move(mixed, cam)
        info["mode"] = "boost"
        checks.append(f"Only one audio track in the original, so the away-from-mic parts "
                      f"({info['seconds'] / 60:.1f} min) were boosted. Face cam is hidden while he's away.")
    else:
        try:
            cam.hardlink_to(source)     # same drive: zero-copy reference to the original
        except OSError:
            shutil.copy2(source, cam)
    (work / "audio_mix.json").write_text(json.dumps(info, indent=2), encoding="utf-8")


def restore_original(project: Path):
    """--fresh: put the untouched file back so the mix can be rebuilt (XML mode: just drop the built copy)."""
    raw = project / "raw"
    orig, cam = raw / "camera_original.mp4", raw / "camera.mp4"
    if orig.exists():
        _move(orig, cam)
    elif list(raw.glob("*.xml")) or list(raw.glob("*.fcpxml")):
        cam.unlink(missing_ok=True)
    (project / "work" / "audio_mix.json").unlink(missing_ok=True)


if __name__ == "__main__":
    p = Path(sys.argv[1]).resolve()
    cfg = json.loads((HERE / "config.json").read_text())
    checks = []
    ensure_mixed(p, cfg, checks)
    print(checks[0] if checks else "no second audio track, nothing to mix")

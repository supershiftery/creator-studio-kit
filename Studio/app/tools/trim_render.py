"""Trim-only render (New Project "Trim only", any video type): the recording exactly as filmed, with only the cutter's kept
pieces, no layout / intro / graphics / music.   python trim_render.py <project>
Reads <project>/Edit/studio (prep.py, cuts.py). One select/aselect pass on the kept ranges, so picture and sound drop the
same frames and cannot drift (same method as _tools/render_draft.py). Voice = the mic track; a second non-silent track
(game / desktop audio) is mixed under it at settings.game_volume (0.3). settings.trim_speed (1.0 default; 1.1, 1.25,
1.5...) speeds the whole result up, pitch kept (atempo).
Output: <project>/<title> - TRIMMED.mp4 (H.264 High yuv420p + AAC, the house delivery format)."""
import json
import re
import subprocess
import sys
from pathlib import Path

proj = Path(sys.argv[1])
doc = json.loads((proj / "studio.json").read_text(encoding="utf-8-sig"))
S = doc.get("settings", {})
work = proj / "Edit" / "studio"
si = json.loads((work / "source.json").read_text(encoding="utf-8"))
keep = json.loads((work / "cuts" / "cuts.json").read_text(encoding="utf-8"))["keep"]
src = doc["source"]
speed = max(0.5, min(2.0, float(S.get("trim_speed") or 1.0)))
title = re.sub(r'[<>:"/\\|?*]', "", doc.get("title") or proj.name).strip()
screen = bool(S.get("screen"))   # screen recording (no cam): full screen + music bed + fades + loudness (MacBook one-off recipe)
out = proj / (f"{title} - EDIT.mp4" if screen else f"{title} - TRIMMED.mp4")
fps = min(60.0, float(si.get("fps") or 30))
# the recording's picture and sound must be the same length (Chime 2026-10-23: a re-encoded source had 2027 s of picture
# under 2232 s of sound, and the draft froze after 7:37 with the voice still running)
_lens = {}
for _ln in subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "csv=p=0", src],
                          capture_output=True, text=True).stdout.split():
    _k, _, _d = _ln.partition(",")
    if _d and _d != "N/A" and _k not in _lens:
        _lens[_k] = float(_d)
if "video" in _lens and "audio" in _lens and abs(_lens["video"] - _lens["audio"]) > 1.0:
    sys.exit(f"the recording's picture ({_lens['video']:.1f} s) and sound ({_lens['audio']:.1f} s) differ: {src} is broken, "
             f"re-make it before building")
if screen and S.get("midstart") is not False and (work / "mic16k.wav").exists():
    # no piece opens mid-sentence (Chime 2026-10-23: "...can literally replace", "...have their own spreadsheet editor",
    # "...have to have not ever opened" all opened one word late): the review pipeline's midstart_guard (lv trainer) re-hears
    # the seam with medium.en and puts the sentence start back; retakes stay cut. Cached in Edit/studio/midstart.json.
    sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "product-review-edit" / "scripts"))
    try:
        import edit_review as ER
        notes_ = []
        # the user's cut notes are deliberate: a start right after one is not "mid-sentence" (Chime 2026-10-23: the guard
        # put back the false start "If it sounds good," that the cut note removed)
        deliberate = [(n["raw0"], n["raw1"]) for n in doc.get("notes", []) if n.get("kind") == "cut" and "raw0" in n and not n.get("off")]
        keep = [[round(s * fps) / fps, e] for s, e in ER.midstart_guard([tuple(x) for x in keep], work / "mic16k.wav", notes_,
                                                                          work / "midstart.json", deliberate=deliberate)]
        for n_ in notes_:
            print("midstart:", n_, flush=True)
    except Exception as ex:  # noqa: the guard never stops a build
        print(f"midstart guard skipped ({type(ex).__name__}: {str(ex)[:120]})", flush=True)
def sel(ranges):
    """select/aselect expression for the kept ranges. Times are frame-snapped; 4-dp rounding (181/60 -> 3.0167) used to
    drop each piece's first frame, so compare 0.5 ms early. Built as a balanced (a+b) tree: ffmpeg's expression parser
    fails ("Cannot allocate memory") on a flat chain of > ~100 terms (Chime tight pauses, 144 pieces, 2026-10-23)."""
    t = [f"between(t,{s - 0.0005:.4f},{e - 0.0005:.4f})" for s, e in ranges]
    while len(t) > 1:
        t = [f"({t[i]}+{t[i + 1]})" if i + 1 < len(t) else t[i] for i in range(0, len(t), 2)]
    return t[0] if t else "0"


expr = sel(keep)


def scene_cuts(t0, dur):
    """hard cuts in the source picture inside [t0, t0 + dur] (ffmpeg scene score)"""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-ss", f"{max(0, t0):.3f}", "-t", f"{dur:.3f}", "-i", src, "-an", "-vf",
                        "select='gt(scene,0.25)',showinfo", "-f", "null", "-"], capture_output=True, text=True, errors="replace")
    return [max(0, t0) + float(x) for x in re.findall(r"pts_time:([0-9.]+)", r.stderr)]


vkeep = [list(r) for r in keep]
if screen:
    # a trailer / video playing on screen can hard-cut just before or after a join, leaving a 0.2 s shot (checker "flash",
    # MacBook one-off 2026-10-22). Fix the PICTURE only: end on the source's own cut and run the next piece that much earlier
    # (or start the piece after the cut). Screen recordings have no lips, so the voice stays exactly where it is.
    for k in range(len(vkeep) - 1):
        s, e = vkeep[k]
        cut = [c for c in scene_cuts(e - 0.36, 0.36) if s + 0.5 < c < e - 0.02]
        if cut:
            d = round((e - cut[-1]) * fps) / fps
            vkeep[k][1] -= d; vkeep[k + 1][0] -= d   # the next piece's picture starts d earlier, same end: no frames lost
            continue
        s2, e2 = vkeep[k + 1]
        cut = [c for c in scene_cuts(s2, 0.36) if s2 + 0.02 < c < e2 - 0.5]
        if cut:
            d = round((cut[0] - s2) * fps) / fps
            # ranges must never overlap, or select would drop frames and the picture would run short of the sound
            if k + 2 >= len(vkeep) or vkeep[k + 2][0] - vkeep[k + 1][1] > d + 0.02:
                vkeep[k + 1][0] += d; vkeep[k + 1][1] += d
    moved = sum(1 for a_, b_ in zip(vkeep, keep) if abs(a_[0] - b_[0]) > 1e-6)
    if moved:
        print(f"picture nudged at {moved} joins (on-screen video cut right at the join)", flush=True)
vexpr = sel(vkeep)
v = f"[0:v]select='{vexpr}',setpts=N/FRAME_RATE/TB" + (f",setpts=PTS/{speed}" if speed != 1 else "") + f",fps={fps:g},format=yuv420p[v]"
mic, game = si.get("mic_track", 0), si.get("game_track")
a = f"[0:a:{mic}]aselect='{expr}',asetpts=N/SR/TB[m]"
if game is not None and game != mic:
    a += (f";[0:a:{game}]aselect='{expr}',asetpts=N/SR/TB,volume={float(S.get('game_volume', 0.3))}[g];"
          f"[m][g]amix=inputs=2:normalize=0:duration=first[mx]")
    last = "mx"
else:
    last = "m"
kept = sum(e - s for s, e in keep)
out_len = kept / speed


def edit_time(t):
    """raw recording time -> time in this edit (kept ranges, then the speed-up)"""
    acc = 0.0
    for s, e in keep:
        if t < s:
            return acc / speed
        if t <= e:
            return (acc + t - s) / speed
        acc += e - s
    return acc / speed


if screen and S.get("zooms") and (work / "words.json").exists():
    # zoom in on what he talks about (tools/screen_zooms.py, user 2026-10-23 Chime): Claude picks the lines, his cursor
    # sets the spot. Never while a privacy blur is up (its boxes sit in unzoomed coordinates).
    import screen_zooms as SZ
    pj_ = work / "pii.json"
    avoid = []
    if pj_.exists() and S.get("privacy") is not False:
        for h in json.loads(pj_.read_text(encoding="utf-8")).get("hits") or []:
            if any(s - 1.0 <= h["t"] <= e + 1.0 for s, e in keep):
                avoid.append((edit_time(h["t"]) - 1.0, edit_time(h["t"]) + 1.5))
    for ov in S.get("overlays") or []:   # a designed overlay (the intro) owns its stretch: no zoom under it
        if Path(ov.get("file", "")).exists():
            d_ = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", ov["file"]],
                                      capture_output=True, text=True).stdout or 0)
            a_ = float(ov["edit"]) if "edit" in ov else edit_time(float(ov.get("raw", 0)))
            avoid.append((a_ - 1.0, a_ + d_ + 1.0))
    words_ = json.loads((work / "words.json").read_text(encoding="utf-8"))
    words_ = words_["words"] if isinstance(words_, dict) else words_
    zooms = SZ.plan(words_, keep, speed, out_len, str(work), src, avoid)
    zp = SZ.filter_expr(zooms, fps)
    if zp:
        v = v.replace(f",fps={fps:g},format=yuv420p[v]", f",{zp},format=yuv420p[v]")
        print(f"zooms: {len(zooms)} punch-ins on the cursor ({SZ.ZOOM}x)", flush=True)


# motion graphics (settings.graphics, tools/motion_graphics.py): full-frame inserts laid over the picture, voice keeps running
gfx_in, n_in = [], 1
gj = work / "graphics" / "graphics.json"
if screen and (S.get("graphics") or {}).get("on") and gj.exists():
    for it in json.loads(gj.read_text(encoding="utf-8")).get("items", []):
        if not Path(it["file"]).exists():
            continue
        at, d = edit_time(it["raw"]), float(it["dur"])
        v = v.replace("[v]", f"[b{n_in}]")
        v += (f";[{n_in}:v]format=yuva420p,fade=t=in:st=0:d=0.35:alpha=1,fade=t=out:st={d - 0.35:.3f}:d=0.35:alpha=1,"
              f"setpts=PTS+{at:.3f}/TB[g{n_in}];[b{n_in}][g{n_in}]overlay=eof_action=pass:format=auto,format=yuv420p[v]")
        gfx_in += ["-i", it["file"]]
        print(f"motion graphic: {it['type']} at {at:.1f}s ({d:.1f}s)", flush=True)
        n_in += 1
# designed overlays (settings.overlays: [{"file": <transparent .mov/.webm>, "edit": s | "raw": s}], user 2026-10-23, the
# Chime hook's HyperFrames intro): laid over the picture with their alpha, voice and music keep running underneath
for ov in S.get("overlays") or []:
    if not Path(ov.get("file", "")).exists():
        print(f"overlay missing, skipped: {ov.get('file')}", flush=True)
        continue
    at = float(ov["edit"]) if "edit" in ov else edit_time(float(ov.get("raw", 0)))
    v = v.replace("[v]", f"[o{n_in}]")
    v += f";[{n_in}:v]setpts=PTS+{at:.3f}/TB[ov{n_in}];[o{n_in}][ov{n_in}]overlay=eof_action=pass:format=auto,format=yuv420p[v]"
    gfx_in += ["-i", ov["file"]]
    print(f"overlay: {Path(ov['file']).name} at {at:.1f}s", flush=True)
    n_in += 1

music = []
if screen:
    # picture fades out at the end; voice + a lo-fi bed ~23 dB under it (gain 0.07, approved on the MacBook video),
    # looped, fading out over the last 3 s; the mix is levelled to -14 LUFS / -1.5 dBTP (house delivery)
    v = v.replace("format=yuv420p[v]", f"fade=t=out:st={max(0.0, out_len - 1.2):.3f}:d=1.2,format=yuv420p[v]")
    a += f";[{last}]" + (f"atempo={speed}," if speed != 1 else "") + "aresample=48000[vo]"
    bed = S.get("screen_music") or r"{{MUSIC_ROOT}}\Type Beats\Lo-Fi\Free LoFi Type Beat - Interstellar Dreams.mp3"
    beats = []
    # no style set = "chill" from the whole music library (music_lib via screen_music, 2026-10-24) instead of the one looped
    # Interstellar Dreams bed every screen edit got; settings.screen_music (one chosen track) still loops as before
    mstyle = S.get("music_style") or ("chill" if not S.get("screen_music") else None)
    if S.get("music") is not False and mstyle in ("beats", "chill") and not S.get("screen_music") and (work / "words.json").exists():
        # phone-style music (user 2026-10-23, friend's Chime video: tools/screen_music.py): a new beat per section, never
        # looped, switching on a pause with a 1.5 s crossfade, 15 LU under the voice like the phone videos
        import screen_music as SM
        words = json.loads((work / "words.json").read_text(encoding="utf-8"))
        words = words["words"] if isinstance(words, dict) else words
        joins, acc = [], 0.0
        for f in (S.get("joined_from") or [])[:-1]:   # the seams between joined recordings are section changes too
            acc += float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f],
                                        capture_output=True, text=True).stdout or 0)
            joins.append(edit_time(acc))
        pid = str(doc.get("id") or "0")
        beats = SM.plan(words, keep, speed, out_len, str(work), joins, seed=sum(map(ord, pid)), style=mstyle)
        (work / "music_plan.json").write_text(json.dumps(beats, indent=1), encoding="utf-8")
    if beats:
        expr_v = f"aselect='{expr}',asetpts=N/SR/TB" + (f",atempo={speed}" if speed != 1 else "")
        err = subprocess.run(["ffmpeg", "-v", "info", "-i", src, "-map", f"0:a:{mic}", "-af", expr_v + ",ebur128", "-f", "null", "-"],
                             capture_output=True, text=True, errors="replace").stderr
        m = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
        voice_l = float(m[-1]) if m else -18.0
        XF = 1.5
        mixes = ["[vo]"]
        for k, b in enumerate(beats):
            s0 = max(0.0, b["s"] - (XF / 2 if k else 0))
            e0 = min(out_len, b["e"] + (XF / 2 if k < len(beats) - 1 else 0))
            d = e0 - s0
            gain = voice_l - SM.POOLS[mstyle][1] - SM.lufs(b["track"], 0, min(d, 90))
            music += ["-i", b["track"]]
            fin = f"afade=t=in:st=0:d={XF}," if k else ""
            fout = f"afade=t=out:st={d - XF:.3f}:d={XF}" if k < len(beats) - 1 else f"afade=t=out:st={max(0.0, d - 3):.3f}:d=3"
            a += (f";[{n_in}:a]atrim=0:{d:.3f},asetpts=N/SR/TB,aresample=48000,volume={gain:.2f}dB,{fin}{fout},"
                  f"adelay={int(s0 * 1000)}:all=1[mu{k}]")
            mixes.append(f"[mu{k}]")
            n_in += 1
        a += f";{''.join(mixes)}amix=inputs={len(mixes)}:duration=first:normalize=0[vm]"
        last = "vm"
        print(f"music: {len(beats)} beats, voice {voice_l:.1f} LUFS, bed {SM.POOLS[mstyle][1]:.0f} LU under it ({mstyle})", flush=True)
    elif S.get("music") is not False and Path(bed).exists():
        music = ["-stream_loop", "-1", "-i", bed]
        a += (f";[{n_in}:a]atrim=0:{out_len:.3f},asetpts=N/SR/TB,afade=t=out:st={max(0.0, out_len - 3):.3f}:d=3,volume=0.07,aresample=48000[mu];"
              "[vo][mu]amix=inputs=2:duration=first:normalize=0[vm]")
        last = "vm"
    else:
        last = "vo"
    a += f";[{last}]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]"
else:
    a += f";[{last}]" + (f"atempo={speed}," if speed != 1 else "") + "aresample=48000[a]"


sys.path.insert(0, str(Path(__file__).parent))
import captions as CAPS   # noqa: E402  the caption presets (Studio Captions setting, 2026-10-23)

cap_style = CAPS.style_for(S)   # settings.captions = true (-> bold) or {"on", "style"}; None = off
if cap_style:
    # captions throughout (user 2026-10-23, Chime: "this video needs captions throughout the whole thing"): the transcript's
    # kept words, mapped onto the edit, in short bottom-centre chunks (<= 5 words / 2.2 s, a new chunk after a sentence end
    # or a 0.5 s pause), shown from the first word to the next chunk (held at most 0.4 s after the last word). Burned in
    # with libass (Edit/studio/captions.ass, also usable as a YouTube upload).
    # Words: medium.en over the EDITED audio (the raw small.en transcript heard "a $300" for "a free hundred dollars" in
    # the Chime hook), cached per cut list in captions_words.json; the raw transcript is the fallback.
    import hashlib
    import wave
    import numpy as np
    sig = hashlib.md5(json.dumps([keep, speed]).encode()).hexdigest()
    cw = work / "captions_words.json"
    cached = json.loads(cw.read_text(encoding="utf-8")) if cw.exists() else {}
    raw_words = []
    if cached.get("sig") == sig:
        raw_words = cached["words"]
    elif (work / "mic16k.wav").exists():
        try:
            sys.path.insert(0, r"{{KIT}}/tools")
            from whisper_gpu import load as _wload
            with wave.open(str(work / "mic16k.wav")) as wf:
                sr_ = wf.getframerate()
                pcm = np.frombuffer(wf.readframes(wf.getnframes()), np.int16)
            xa = np.concatenate([pcm[int(s * sr_):int(e * sr_)] for s, e in keep]).astype(np.float32) / 32768
            wm, where = _wload("medium.en", cpu_threads=12)
            print(f"captions: transcribing the edit ({len(xa) / sr_ / 60:.1f} min, medium.en, {where})", flush=True)
            # settings.vocabulary spells the brands ("Chime has a SpotMe", not "time has a spot me"; "designer.com")
            vocab = S.get("vocabulary") or []
            segs, _ = wm.transcribe(xa, language="en", word_timestamps=True, condition_on_previous_text=False,
                                    initial_prompt=("So, um, " + ", ".join(vocab) + ".") if vocab else None)
            raw_words = [{"w": x.word, "s": x.start / speed, "e": x.end / speed} for sg in segs for x in (sg.words or [])]
            cw.write_text(json.dumps({"sig": sig, "words": raw_words}), encoding="utf-8")
        except Exception as ex:  # noqa: fall back to the raw transcript
            print(f"captions: medium.en pass skipped ({type(ex).__name__}: {str(ex)[:120]})", flush=True)
    if raw_words:
        wl = [(w["w"].strip(), w["s"], w["e"]) for w in raw_words]
    else:
        words = json.loads((work / "words.json").read_text(encoding="utf-8"))
        words = words["words"] if isinstance(words, dict) else words
        wl = [(w["w"].strip(), edit_time(w["s"]), edit_time(w["e"])) for w in words
              if any(s <= (w["s"] + w["e"]) / 2 < e for s, e in keep)]
    toks = []
    for t, ws_, we_ in wl:
        if not t:
            continue
        if toks and (t[0] in ".%-'" or t.startswith(("’", ","))) and ws_ - toks[-1][2] < 0.3:
            toks[-1][0] += t   # Whisper splits "designer .com", "100 %", "-for -sale"
            toks[-1][2] = we_
            continue
        if not toks or toks[-1][0][-1:] in ".?!":
            t = t[:1].upper() + t[1:]   # a sentence start (also the first word after a cut into a sentence)
        toks.append([t, ws_, we_])
    # said-twice check (Chime 2026-10-23): small.en hides doubles ("unemployed, unemployed", "for a free one, for a free
    # $1,000") that the medium.en pass on the edit hears; the friend's editor cut every one. Listed for the review.
    nt = [re.sub(r"[^a-z0-9$]", "", t[0].lower()) for t in toks]
    OKD = {"very", "really", "that", "had", "is", "to", "no", "so", "bye", "ha"}
    for i in range(len(nt)):
        for n_ in (4, 3, 2, 1):
            a_, b_ = nt[i:i + n_], nt[i + n_:i + 2 * n_]
            # across a sentence end it is speech, not a double ("...by designer.com. Designer.com is a one platform")
            if len(b_) == n_ and a_ == b_ and all(a_) and toks[i + 2 * n_ - 1][2] - toks[i][1] < 4.0 \
                    and toks[i + n_ - 1][0][-1:] not in ".?!" \
                    and not (n_ == 1 and (a_[0] in OKD or len(a_[0]) < 3)):
                at = toks[i][1]
                print(f"caption check: said twice at {int(at // 60)}:{at % 60:04.1f}: "
                      f"'{' '.join(t[0] for t in toks[max(0, i - 3):i + 2 * n_ + 2])}'", flush=True)
                break
    # style, chunking, size and highlight = the project's caption preset (tools/captions.py; the first Arial 64 was "very
    # small"); the words stay this file's own (medium.en on the edit, vocabulary, merged tokens, said-twice check)
    ass = CAPS.build_ass([{"w": t, "s": ws_, "e": we_} for t, ws_, we_ in toks], 1920, 1080, cap_style)
    (work / "captions.ass").write_text(ass, encoding="utf-8")
    v = v[:-len("[v]")] + "," + CAPS._filt(work / "captions.ass") + "[v]"   # last on [v]: above the zooms, graphics and overlays
    ev = [ln for ln in ass.splitlines() if ln.startswith("Dialogue:")]
    print(f"captions: {CAPS.PRESETS[cap_style]['label']} (font {CAPS.font_for(cap_style)[0]})", flush=True)
    print(f"captions: {len(ev)} lines from {len(toks)} words", flush=True)
graph = work / "trim-graph.txt"
graph.write_text(v + ";" + a, encoding="utf-8")
kept = sum(e - s for s, e in keep)
print(f"trim only: {len(keep)} pieces, {kept / 60:.1f} of {si['duration'] / 60:.1f} min kept" + (f", {speed}x speed" if speed != 1 else ""), flush=True)
subprocess.run(["ffmpeg", "-v", "error", "-stats", "-y", "-i", src, *gfx_in, *music, "-/filter_complex", str(graph), "-map", "[v]", "-map", "[a]",
                "-c:v", "h264_nvenc", "-profile:v", "high", "-pix_fmt", "yuv420p", "-preset", "p5", "-rc", "vbr", "-b:v", "0", "-cq", "19",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out)], check=True, cwd=str(work))
(work / "timeline-trim.json").write_text(json.dumps({"keep": keep, "intro": 0.0, "speed": speed, "out": str(out)}), encoding="utf-8")
print(f"wrote {out} ({kept / speed / 60:.1f} min)")

# privacy (user 2026-10-23, cut first then privacy): the "privacy" step scanned only the kept parts of the recording
# (tools/pii_scan.py --ranges -> Edit/studio/pii.json, recording time); what lands in this edit is blurred now, in one pass
# over the edit only. The "privacy_check" step then scans the finished edit as the safety net.
pj = work / "pii.json"
if screen and S.get("privacy") is not False and pj.exists():
    hits = json.loads(pj.read_text(encoding="utf-8")).get("hits") or []
    inside = [h for h in hits if any(s - 1.0 <= h["t"] <= e + 1.0 for s, e in keep)]   # keep = after the midstart guard
    if inside:
        tmp = out.with_name(out.stem + ".blurring.mp4")
        subprocess.run([sys.executable, "-X", "utf8", str(Path(__file__).with_name("pii_blur.py")), str(out), str(pj), str(tmp),
                        "--fps", "2", "--map", str(work / "timeline-trim.json")], check=True)
        tmp.replace(out)
        print(f"privacy: blurred {len(inside)} sightings of personal info in the edit", flush=True)
    else:
        print("privacy: nothing private found in the kept parts", flush=True)

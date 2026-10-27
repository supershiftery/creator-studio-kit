"""Step 6: intro + body, a wipe over every section cut, cards at section starts, sectioned soft game-OST bed,
whooshes, limiter -> <project>/Edit/<title> <mode>.mp4 + timeline-<mode>.json.   python assemble.py <project> draft|final

Sound rules (user, 2026-10-20): soft game OSTs (never Minecraft's own soundtrack, never type beats in gaming videos),
voice about -17 LUFS, bed about -36 LUFS, tracks loop so the bed never goes silent, Pokémon music only on Pokémon
sections, one whoosh per wipe, nothing else.
"""
import json
import os
import re
import sys
from pathlib import Path

from glib import HERE, NVENC, Project, SFX_DIR, duration, fmt, lufs, run, say, wipe_for

P = Project(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "draft")
W, H, FPS = P.W, P.H, P.FPS
S = P.settings
# test builds (user 2026-10-24 KV body test): STUDIO_SETTINGS_OVERLAY = a JSON file whose "cards" are merged and whose
# "graphics" are appended for THIS build only (studio.json untouched); STUDIO_OUT_TAG = suffix for the output video and
# its timeline, so a test never overwrites the delivered "<title> final.mp4"
_ov = os.environ.get("STUDIO_SETTINGS_OVERLAY")
if _ov and os.path.exists(_ov):
    _o = json.loads(Path(_ov).read_text(encoding="utf-8"))
    S = dict(S)
    S["cards"] = dict(S.get("cards") or {}, **(_o.get("cards") or {}))
    S["graphics"] = list(S.get("graphics") or []) + list(_o.get("graphics") or [])
    say(f"settings overlay {Path(_ov).name}: {len(_o.get('cards') or {})} cards, {len(_o.get('graphics') or [])} graphics")
OUT_TAG = os.environ.get("STUDIO_OUT_TAG", "").strip()
body = P.read(f"body-{P.mode}.json")
if not body:
    sys.exit("build the body first")
BODY = P.wf(f"body-{P.mode}.mp4")
INTRO = P.doc.get("slots", {}).get("intro") or ""
INTRO = INTRO if INTRO and os.path.exists(INTRO) else ""
INTRO_D = duration(INTRO) if INTRO else 0.0
# settings.intro_out: end the pre-made intro early (its end card held ~3 s after "Let's go" before "Hello YouTube",
# Top 10 Servers round 2: "too much spacing in between the intro and the other intro")
if INTRO and S.get("intro_out"):
    INTRO_D = min(INTRO_D, float(S["intro_out"]))
elif INTRO and S.get("intro_tight", True):
    # no intro_out = end it 0.3 s after its last spoken word, automatically (reselling spreadsheet 2026-10-23: "removing
    # the 1 second was a good call across all of our videos ... no spacing in between the intro for the voiceover and the
    # other intro"); settings.intro_tight=false keeps the whole render
    try:
        sys.path.insert(0, r"{{KIT}}/tools")
        from intro_end import vo_end
        _e = vo_end(INTRO)
        if _e and _e + 0.3 < INTRO_D:
            say(f"intro ends 0.3 s after its last word: {INTRO_D:.2f} -> {_e + 0.3:.2f} s")
            INTRO_D = round(_e + 0.3, 3)
    except Exception as ex:   # never fail a build over this; the full intro plays
        say(f"intro end not measured ({ex}); full intro kept")
WIPE = wipe_for(P.doc, P.path)   # a project's own *transition*.mov in Graphics first, else Realms wipe on Realms videos, server transition elsewhere
BED, VOICE = float(S.get("music_bed_lufs", -36.0)), float(S.get("voice_lufs", -17.0))
NO_MUSIC = os.environ.get("STUDIO_NO_MUSIC") == "1"   # New Project "Music" unticked: the bed is silent, wipe SFX stay
pool = json.loads((HERE / "music_pool.json").read_text(encoding="utf-8"))
# the WHOLE {{MUSIC_ROOT}} library on top of the vetted pool (user 2026-10-24: "we've been using the same tracks over and over
# again"): music_lib adds every vocal-scanned clean game OST / game beat / anime / cinematic track (never Minecraft's, never
# type beats; Pokémon tracks only in the pokemon pool) and moves tracks the channel's last 15 videos used to the back, so
# take() (least used in THIS video first, then pool order) reaches fresh tracks first.
try:
    sys.path.insert(0, r"{{KIT}}/tools")
    import music_lib
    _pd = str(getattr(P, "path", None) or sys.argv[1])
    _used, _ = music_lib.recent_tracks(P.doc.get("channel") or "{{GAMING_CHANNEL}}", _pd)
    for _key, _kind, _title in (("general", "gaming", ""), ("pokemon", "gaming", "pokemon")):
        _have = {music_lib._norm(t["track"]) for t in pool.get(_key, [])}
        _lib = music_lib.pick(_kind, 40, title=_title, project=_pd, min_len=45, log=False, keep=False)
        _add = [{"track": t, "offset": min(8.0, float(music_lib.info(t).get("lead_in") or 0)), "mood": "library",
                 "dur": music_lib.info(t).get("usable")} for t in _lib if music_lib._norm(t) not in _have]
        _all = [t for t in pool.get(_key, []) if t.get("mood") not in ("intro", "outro")] + _add
        _keep = [t for t in pool.get(_key, []) if t.get("mood") in ("intro", "outro")]
        pool[_key] = _keep + [t for t in _all if music_lib._norm(t["track"]) not in _used] + \
            [t for t in _all if music_lib._norm(t["track"]) in _used]
        # copyright-claimed tracks are retired for good (Studio Uploads copyright check, 2026-10-26)
        pool[_key] = [t for t in pool[_key] if not music_lib.retired(t["track"])]
except Exception as _e:
    music_lib = None
    say(f"music_lib skipped: {type(_e).__name__}: {str(_e)[:160]}")
words = P.words
secs = body["sections"]
keep = body["keep"]
POKE = re.compile(r"pok[eé]|cobblemon|pixelmon|pokerein|rennmon|pokefind", re.I)


def section_words(name):
    rng = next(((s, e) for n, s, e in P.sections if n == name), None)
    if not rng:
        return ""
    return " ".join(w["w"] for w in words if rng[0] <= w["s"] <= rng[1])


def theme_of(name):
    """music theme of a section: 'pokemon' when the section is a Pokémon server/realm/add-on (its name, or the word
    said 3+ times in it), else None. Themes get their own pool and never leak into neighbouring sections."""
    return "pokemon" if POKE.search(name) or len(POKE.findall(section_words(name))) >= 3 else None


def tdur(t):
    return float(t.get("dur") or duration(t["track"]) or 120.0)


# 1. music: every section its OWN track (user 2026-10-22: "every single section should have different music"), no
# track twice in a video while the pool lasts. A section longer than its track continues into the next track of the
# same kind (Pokémon -> another Pokémon track) with a crossfade instead of looping. Chains: {section: [(track, off, len)]}
spans = []
for i, s in enumerate(secs):
    end = secs[i + 1]["t"] if i + 1 < len(secs) else body["duration"]
    if s["section"].startswith("HM") and spans and spans[-1][0].startswith("HM"):
        spans[-1][2] = end
        continue
    spans.append([s["section"], s["t"], end])
USED = {}


def take(cands, need):
    """tracks from cands (least used first, pool order) until `need` seconds are covered"""
    chain, got = [], 0.0
    cands = [t for t in cands if os.path.exists(t["track"])]
    while got < need and cands:
        cands.sort(key=lambda t: USED.get(t["track"], 0))
        t = next((c for c in cands if c["track"] not in [x[0] for x in chain]), None)
        if t is None:
            break
        ln = max(tdur(t) - float(t.get("offset", 0)) - 1.0, 20.0)
        chain.append((t["track"], float(t.get("offset", 0)), ln))
        USED[t["track"]] = USED.get(t["track"], 0) + 1
        got += ln - 2.0
    return chain


def pick_music():
    user = S.get("music", {}) or {}
    out = {}
    gen = [t for t in pool["general"] if t.get("mood") not in ("intro", "outro")]
    for name, a, b in spans:
        need = b - a + 1.0
        if name in user and user[name].get("track") and os.path.exists(user[name]["track"]):
            t = {"track": user[name]["track"], "offset": float(user[name].get("offset", 0))}
            ln = max(tdur(t) - t["offset"] - 1.0, 1.0)
            out[name] = [(t["track"], t["offset"], ln)]
            USED[t["track"]] = USED.get(t["track"], 0) + 1
            if ln < need:   # a picked track shorter than its section crossfades into the next one instead of looping
                # through its silent tail + fade-in (Top 10 Servers #3: 1.5 s hole where the 83 s track restarted)
                pool_ = (pool.get(theme_of(name)) or gen) if theme_of(name) else gen
                out[name] += take([c for c in pool_ if c["track"] != t["track"]], need - ln + 2.0)
        elif name in ("intro", "outro"):
            out[name] = take([pool[name]], 0.1) or take(gen, need)
        elif theme_of(name):
            out[name] = take(pool.get(theme_of(name)) or gen, need)
        else:
            out[name] = take(gen, need)
    return out


MUSIC = pick_music()
for n, ch in MUSIC.items():
    if not ch:
        sys.exit(f"no music track for {n}")
if music_lib and not NO_MUSIC:
    try:
        music_lib.log_use(_pd, "gaming", list(dict.fromkeys(c[0] for ch in MUSIC.values() for c in ch)),
                          P.doc.get("channel") or "{{GAMING_CHANNEL}}", P.doc.get("title", ""))
    except Exception:
        pass


def raw_to_body(raw):
    t = 0.0
    for a_, b_ in keep:
        if raw < a_:
            return t
        if raw <= b_:
            return t + raw - a_
        t += b_ - a_
    return t


def piece_end(raw):
    """body time where the kept piece holding raw ends"""
    t = 0.0
    for a_, b_ in keep:
        if a_ <= raw <= b_:
            return t + b_ - a_
        t += b_ - a_
    return t


# music moments (user 2026-10-22: "if I'm in a PvP fight we might have suspenseful music ... fade out the other track,
# then once the fight is done go back into the track that was playing like nothing happened"): the section bed ducks
# (-17 dB, 0.6 s ramps) under a suspense track and comes back where it would have been. From settings.music_moments
# [{"raw0", "raw1", "mood"}] and, unless music_moments_auto is false, fight talk in the recording: a cluster of 3+
# cues ("combo", "pvp", "fight", "kill", "hold on", ...) within 6 s. One per section, 5-30 s, only with a pool for it.
FIGHT = re.compile(r"^(pvp|combo|comboing|fight|fighting|attack|attacking|kill|killed|killing|chasing|1v1)$")
moments = []
for m in S.get("music_moments", []) or []:
    moments.append((float(m["raw0"]), float(m["raw1"]), m.get("mood", "suspense"), "note"))
if S.get("music_moments_auto", True) and pool.get("suspense"):
    tok = [re.sub(r"[^a-z0-9]", "", w["w"].lower()) for w in words]
    cues = [words[i] for i in range(len(words) - 1) if FIGHT.match(tok[i]) or (tok[i] == "hold" and tok[i + 1] == "on")]
    cues = [c for c in cues if any(a_ <= c["s"] <= b_ for a_, b_ in keep) and P.section_of(c["s"]) not in ("intro", "outro", "?")]
    k_ = 0
    while k_ < len(cues):
        j_ = k_
        while j_ + 1 < len(cues) and cues[j_ + 1]["s"] - cues[j_]["s"] <= 6.0:
            j_ += 1
        grp = cues[k_:j_ + 1]
        sec = P.section_of(grp[0]["s"])
        if len(grp) >= 3 and not any(P.section_of(m[0]) == sec for m in moments):
            moments.append((grp[0]["s"] - 2.0, grp[-1]["e"] + 1.0, "suspense", f"{len(grp)} fight cues"))
        k_ = j_ + 1
MOMENTS = []   # (body t0, body t1, track dict)
for i_, (r0, r1, mood, why) in enumerate(sorted(moments)):
    lst = [t for t in pool.get(mood, []) if os.path.exists(t["track"])]
    if not lst:
        continue
    t0 = raw_to_body(max(r0, next((a_ for a_, b_ in keep if a_ <= r0 <= b_), r0)))
    t1 = min(raw_to_body(r1), piece_end(r1 - 1.0) + 0.2)   # never past the piece of the last cue (an insert may follow)
    if t1 - t0 < 5.0:
        t1 = t0 + 5.0
    t1 = min(t1, t0 + 30.0)
    MOMENTS.append((t0, t1, lst[i_ % len(lst)]))
    say(f"  music moment {fmt(t0)}-{fmt(t1)} ({mood}, {why})")
parts = []
for name, a, b in spans:
    chain = MUSIC[name]
    d = b - a + 1.0
    st = max(a - 0.5, 0)
    out = P.wf(f"music-{len(parts):02d}.wav")
    raw = P.wf("music-tmp.wav")
    if len(chain) == 1:   # one track: loop it if the section is longer
        track, off, _ = chain[0]
        run(["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-ss", str(off), "-i", track, "-t", f"{d:.3f}", "-ac", "2", "-ar", "48000", str(raw)])
    else:                 # several tracks: each from its offset, 2 s crossfades between them
        cmd = ["ffmpeg", "-v", "error", "-y"]
        for track, off, ln in chain:
            cmd += ["-ss", str(off), "-t", f"{ln:.3f}", "-i", track]
        fl, last = [], "[0:a]"
        for q in range(1, len(chain)):
            fl.append(f"{last}[{q}:a]acrossfade=d=2:c1=tri:c2=tri[x{q}]")
            last = f"[x{q}]"
        cmd += ["-filter_complex", ";".join(fl), "-map", last, "-t", f"{d:.3f}", "-ac", "2", "-ar", "48000", str(raw)]
        run(cmd)
    # settings.music[section].gain: dB on top of the normal bed level (round 2: "a little bit too loud ... keep the track,
    # just lower the volume")
    g = -91.0 if NO_MUSIC else BED - lufs(raw) + float(((S.get("music") or {}).get(name) or {}).get("gain", 0))
    duck = "".join(f"-0.86*min(max((t-{m0 - st:.2f})/0.6,0),1)*min(max(({m1 - st:.2f}-t)/0.6,0),1)" for m0, m1, _ in MOMENTS if m0 < b and m1 > a)
    vol = f"volume={g:.2f}dB" + (f",volume='max(1{duck},0.05)':eval=frame" if duck else "")
    run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af",
         f"{vol},afade=t=in:d=0.8,afade=t=out:st={d - 1.0:.3f}:d=1.0,adelay={int(st * 1000)}:all=1", str(out)])
    parts.append(out)
    say(f"  music {name}: " + ("off (no music)" if NO_MUSIC else " + ".join(Path(c[0]).stem[:40] for c in chain) + f" ({g:+.1f} dB)"))
for m0, m1, t in MOMENTS:   # the suspense track itself, a touch above the bed
    out = P.wf(f"music-{len(parts):02d}.wav")
    raw = P.wf("music-tmp.wav")
    d = m1 - m0 + 0.6
    run(["ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-ss", str(t.get("offset", 0)), "-i", t["track"], "-t", f"{d:.3f}", "-ac", "2", "-ar", "48000", str(raw)])
    g = -91.0 if NO_MUSIC else BED + 1.5 - lufs(raw)
    run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af",
         f"volume={g:.2f}dB,afade=t=in:d=0.5,afade=t=out:st={d - 0.7:.3f}:d=0.7,adelay={int(max(m0 - 0.1, 0) * 1000)}:all=1", str(out)])
    parts.append(out)
wipes = [s["t"] for s in secs if s["section"] not in ("intro", "outro")]
# one light swish per wipe, peaking on the wipe's middle (the transition MOV's own audio is not mixed). Was
# whoosh-short.mp3 at 0.2: a low "whomp" (-7 dB full band, -37 dB above 3 kHz) that the voice + game audio masked in
# the Top 10 Servers final, so the user heard no transition sound (2026-10-24: "we need transition sounds for the
# transitions we already have"). swish-fast.wav = "Fast Swish" from {{MUSIC_ROOT}}\Sound Effects\Swoosh Pack: same 0.57 s,
# airy (no bass, no riser), sits above the voice's highs but ~3-6 dB under its level.
# settings.wipe_sfx = file in SFX_DIR or a full path ("off" = none); settings.wipe_sfx_vol = linear volume.
WIPE_SFX = str(S.get("wipe_sfx") or "swish-fast.wav")
WIPE_SFX_VOL = float(S.get("wipe_sfx_vol", 0.9))
cues = [] if WIPE_SFX.lower() in ("off", "none", "0") else [(t - 0.28, WIPE_SFX, WIPE_SFX_VOL) for t in wipes]
if cues:
    say(f"  wipe sfx: {Path(WIPE_SFX).name} x{len(cues)} at volume {WIPE_SFX_VOL}")
cues += [tuple(c) for c in body.get("sfx", [])]
# a graphic may carry its own sound (KV keyword box: one soft pitchless swoosh, approved intro sound)
cues += [(raw_to_body(float(g["raw"])), g["sfx"], float(g.get("sfx_vol", 0.1))) for g in S.get("graphics", []) or []
         if g.get("sfx") and os.path.exists(str(g["sfx"]))]
mix = P.wf("music-bed.wav")
cmd = ["ffmpeg", "-v", "error", "-y"]
for p in parts:
    cmd += ["-i", str(p)]
for t, f, v in cues:
    cmd += ["-i", str(f if os.path.isabs(f) else SFX_DIR / f)]
fl = [f"[{len(parts) + n}]volume={v},adelay={int(max(t, 0) * 1000)}:all=1[s{n}]" for n, (t, f, v) in enumerate(cues)]
cmd += ["-filter_complex", ";".join(fl + ["".join(f"[{i}]" for i in range(len(parts))) + "".join(f"[s{n}]" for n in range(len(cues)))
        + f"amix=inputs={len(parts) + len(cues)}:normalize=0:duration=longest,atrim=0:{body['duration']:.3f}[m]"]), "-map", "[m]", str(mix)]
run(cmd)
holes = re.findall(r"silence_start: ([\d.]+)", run(["ffmpeg", "-nostats", "-i", str(mix), "-af", "silencedetect=n=-60dB:d=1.5", "-f", "null", "-"], check=False).stderr)
if holes and not NO_MUSIC:
    say("WARNING music gaps at", holes)
# 2. voice level
vg = VOICE - lufs(BODY)
say(f"voice gain {vg:+.1f} dB")


# 3. picture: intro + body, wipes, cards, CTA graphics
def auto_cards():
    """section -> transparent MOV from <project>/Graphics (code cards, IP cards) matched by rank number or name."""
    found = {}
    movs = [p for p in Path(P.path, "Graphics").rglob("*.mov")] if (P.path / "Graphics").is_dir() else []
    movs = [m for m in movs if "_replaced" not in m.parts and "transition" not in m.stem.lower() and "cta" not in m.stem.lower()]
    for s in secs:
        name = s["section"]
        m = re.match(r"#(\d+)\s*(.*)", name)
        toks = [t for t in re.sub(r"[^a-z0-9 ]", " ", name.lower()).split() if len(t) > 3]
        best = None
        for mv in movs:
            st = mv.stem.lower()
            score = 0
            if m and re.search(rf"(^|\D)0?{int(m.group(1))}(\D|$)", st):
                score += 2
            score += sum(1 for t in toks if t in st)
            if name.startswith("HM") and "hm" in st:
                score += 1
            if score >= 2 and (best is None or score > best[0] or (score == best[0] and "transparent" in str(mv).lower())):
                best = (score, mv)
        if best:
            found[name] = str(best[1])
    return found


cards = dict(auto_cards())
cards.update({k: v for k, v in (S.get("cards") or {}).items() if v and os.path.exists(v)})
inputs = (["-t", f"{INTRO_D:.3f}", "-i", INTRO] if INTRO else []) + ["-i", str(BODY), "-i", str(mix)]
over = []


_checked = set()


def add_overlay(path, t, d):
    """A graphic below the video's frame rate shows every frame twice over 60 fps gameplay: the wipes and IP cards were
    30 fps HyperFrames renders and the user saw transitions "at some weird frame rate" (2026-10-24). HyperFrames graphics
    now carry data-fps="60"; re-render an older one with `npx hyperframes render --fps 60 --format mov`."""
    if path not in _checked:
        _checked.add(path)
        import subprocess
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
                            "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
        num, _, den = r.partition("/")
        try:
            if float(num) / float(den or 1) < FPS - 0.5:
                say(f"  WARNING overlay {Path(path).name} is {r} fps (video {FPS}): choppy, re-render it at {FPS} fps")
        except ValueError:
            pass
    inputs.extend(["-i", path])
    over.append((inputs.count("-i") - 1, t, d))   # count inputs, not args: the intro has an extra "-t" pair


if os.path.exists(WIPE):
    for t in wipes:
        add_overlay(WIPE, INTRO_D + t - 0.4, 0.8)
for s in secs:
    if s["section"] in cards:
        add_overlay(cards[s["section"]], INTRO_D + s["t"] + 0.45, min(duration(cards[s["section"]]) or 11, 14))
        say(f"  card {s['section']}: {Path(cards[s['section']]).name}")


for g in S.get("graphics", []) or []:   # [{"raw": t, "file": mov, "dur": s}] graphics tied to a spoken line
    if g.get("file") and os.path.exists(g["file"]):
        add_overlay(g["file"], INTRO_D + raw_to_body(float(g["raw"])), float(g.get("dur") or duration(g["file"]) or 5))
bi = 1 if INTRO else 0
# the body's audio holds ~1 AAC frame of encoder priming per piece (48 pieces = 991.6 s of samples in a 990.1 s body);
# amix reads samples, not timestamps, so the music bed + wipe swishes slid up to 1.4 s EARLY by the end (Top 10 Servers,
# 2026-10-24: swish 1.4 s before the #1 wipe, #1's music early too). aresample to the timestamps (hard-drop every
# overlap > 10 ms) puts voice, picture and bed on one clock again.
fc = [f"[{bi}:v]fps={FPS},setsar=1[bv]", f"[{bi}:a]aresample=async=1:min_hard_comp=0.01:first_pts=0,volume={vg:.2f}dB[vo]",
      f"[vo][{bi + 1}:a]amix=inputs=2:normalize=0,alimiter=limit=0.8:attack=3:release=60:level=disabled[ba]"]
if INTRO:
    fc += [f"[0:v]scale={W}:{H},fps={FPS},setsar=1[iv]", f"[0:a]aresample=48000,aformat=channel_layouts=stereo,afade=t=out:st={max(INTRO_D - 0.25, 0):.3f}:d=0.25[ia]",
           "[ba]aformat=channel_layouts=stereo[ba2]", "[iv][ia][bv][ba2]concat=n=2:v=1:a=1[v0][aout0]"]
else:
    fc += ["[bv]null[v0]", "[ba]anull[aout0]"]
fc.append("[aout0]alimiter=limit=0.75:attack=3:release=60:level=disabled[aout]")
last = "v0"
for n, (idx, t, d) in enumerate(over):
    fc.append(f"[{idx}:v]scale={W}:{H},format=yuva420p,setpts=PTS-STARTPTS+{t:.3f}/TB[c{n}]")
    fc.append(f"[{last}][c{n}]overlay=eof_action=pass:enable='between(t,{t:.3f},{t + d:.3f})'[v{n + 1}]")
    last = f"v{n + 1}"
out = P.out_video()
if OUT_TAG:
    out = out.with_name(f"{out.stem} {OUT_TAG}{out.suffix}")
graph = P.wf(f"assemble-graph{'-' + OUT_TAG.replace(' ', '-') if OUT_TAG else ''}.txt")
graph.write_text(";".join(fc), encoding="utf-8")
r = run(["ffmpeg", "-v", "error", "-y"] + inputs + ["-/filter_complex", str(graph), "-map", f"[{last}]", "-map", "[aout]"] + NVENC + [
    "-preset", "p6", "-rc", "vbr", "-b:v", "0", "-cq", "23" if P.mode == "draft" else "17",
    "-maxrate", "16M" if P.mode == "draft" else "60M", "-bufsize", "32M" if P.mode == "draft" else "120M",
    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)], check=False)
if r.returncode:
    sys.exit(r.stderr[-1500:])
P.write(f"timeline-{P.mode}{'-' + OUT_TAG.replace(' ', '-') if OUT_TAG else ''}.json", {"intro": round(INTRO_D, 3), "video": str(out), "keep": keep,
                                     "sections": [dict(s, t_final=round(INTRO_D + s["t"], 2)) for s in secs],
                                     "music": {k: {"track": v[0][0], "offset": v[0][1], "chain": [{"track": c[0], "offset": c[1]} for c in v]} for k, v in MUSIC.items()},
                                     "music_moments": [{"t": round(INTRO_D + m0, 2), "t1": round(INTRO_D + m1, 2), "track": t["track"]} for m0, m1, t in MOMENTS], "cards": cards})
say("wrote", out)
for s in secs:
    say(f"  {fmt(INTRO_D + s['t'])}  {s['section']}")

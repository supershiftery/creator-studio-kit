"""Haul render (Studio type "haul", user 2026-10-23): one long phone recording showing a bunch of products, no separate
intro VO, no OBS side-by-side.   python haul_render.py <project> [--draft]

Reads <project>/Edit/studio (prep.py, transcribe.py, cuts.py on raw/source.mp4 = haul_normalise.py's 1080p60 SDR join).
1. The cutter's kept pieces, with the review pipeline's midstart_guard (no piece opens mid-sentence).
2. Structure (cached in Edit/studio/haul_structure.json): the spoken intro ("hey guys ..."), the products in order, and the
   outro ("anyways guys that's pretty much it" through the sign-off). Regex first for the greeting and the outro, Claude
   (tools claude_brain) for where the intro ends and where each product starts. Everything kept before the greeting or
   after the sign-off is dropped.
3. Music like the product reviews: type beats. The intro has its own beat, the body plays beats through (the next one starts
   when one runs out, never looped, switching on a pause), the outro has its own beat (user 2026-10-23). Whisper-checked for vocals / producer tags ({{MUSIC_ROOT}}\\_vocal_scan.json), rotated against the
   review pipeline's music history so recent videos' beats aren't reused. The bed sits 15 LU under the voice OF ITS SECTION
   (volume follows the voice), 1.5 s crossfades on a pause.
4. Captions over the intro AND the outro, Gling "Doug" style (tools/captions.py preset "doug"); none in the body.
5. -16 LUFS / -1.5 dBTP (the approved review finals: -16.0..-16.1), H.264 High yuv420p + AAC 48 kHz. Draft = 960x540 30 fps cq 23, final = 1920x1080 60 fps cq 17.
Output: <project>/<title> - DRAFT.mp4 | - FINAL.mp4; Edit/studio/timeline-haul.json (keep, intro, outro, sections, music).

SHORT mode (Studio type "short", user 2026-10-23: "a Studio type for raw vertical Short recordings: keep it 1080x1920, trim,
music, captions"): same trim / midstart guard / Spatial-Audio-matched source, but no greeting / outro / product structure
(no Claude call), beats played through from 0:00 (no intro / outro beat), Doug captions over the WHOLE Short in the
vertical preset "doug_v", 1080x1920 60 fps (draft 540x960 30 fps). Writes Edit/studio/timeline-short.json.
"""
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, r"{{KIT}}/tools")
import captions as CAPS   # noqa: E402

proj = Path(sys.argv[1])
DRAFT = "--draft" in sys.argv
doc = json.loads((proj / "studio.json").read_text(encoding="utf-8-sig"))
S = doc.get("settings") or {}
SHORT = doc.get("type") == "short"
work = proj / "Edit" / "studio"
si = json.loads((work / "source.json").read_text(encoding="utf-8"))
keep = [list(x) for x in json.loads((work / "cuts" / "cuts.json").read_text(encoding="utf-8"))["keep"]]
words = json.loads((work / "words.json").read_text(encoding="utf-8"))
words = words["words"] if isinstance(words, dict) else words
src = doc["source"]
title = re.sub(r'[<>:"/\\|?*]', "", doc.get("title") or proj.name).strip()
out = proj / f"{title} - {'DRAFT' if DRAFT else 'FINAL'}.mp4"
FPS_SRC = float(si.get("fps") or 60)
W, H, FPS = ((540, 960, 30) if DRAFT else (1080, 1920, 60)) if SHORT else ((960, 540, 30) if DRAFT else (1920, 1080, 60))


def say(*a):
    print(*a, flush=True)


def stream_durs(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "json", str(p)],
                       capture_output=True, text=True).stdout
    d = {}
    for s in json.loads(r or "{}").get("streams", []):   # STREAM durations (csv output had trailing side-data commas)
        if s.get("duration") not in (None, "N/A") and s["codec_type"] not in d:
            d[s["codec_type"]] = float(s["duration"])
    return d.get("video"), d.get("audio")


vd, ad = stream_durs(src)
if vd is None or ad is None or abs(vd - ad) > 0.5:
    sys.exit(f"REFUSED: the source's picture ({vd} s) and sound ({ad} s) differ; re-run the normalise step")

# ---- 1. midstart guard (same as the screen edits / reviews)
deliberate = [(n["raw0"], n["raw1"]) for n in doc.get("notes", []) if n.get("kind") == "cut" and "raw0" in n and not n.get("off")]
if S.get("midstart") is not False and (work / "mic16k.wav").exists():
    sys.path.insert(0, str(Path.home() / ".claude" / "skills" / "product-review-edit" / "scripts"))
    try:
        import edit_review as ER
        notes_ = []
        keep = [[round(s * FPS_SRC) / FPS_SRC, e] for s, e in ER.midstart_guard([tuple(x) for x in keep], work / "mic16k.wav", notes_,
                                                                                work / "midstart.json", deliberate=deliberate)]
        for n_ in notes_:
            say("midstart:", n_)
    except Exception as ex:  # noqa: the guard never stops a build
        say(f"midstart guard skipped ({type(ex).__name__}: {str(ex)[:120]})")

# ---- 2. structure: greeting, intro end, products, outro, sign-off (raw recording times)
kw = [w for w in words if any(s <= (w["s"] + w["e"]) / 2 < e for s, e in keep)]


def lines_of(ws):
    out_, cur = [], []
    for i, w in enumerate(ws):
        cur.append(w)
        gap = ws[i + 1]["s"] - w["e"] if i + 1 < len(ws) else 9
        if re.search(r"[.?!]$", w["w"].strip()) or gap > 0.8 or len(cur) > 35:
            out_.append({"s": cur[0]["s"], "e": cur[-1]["e"], "text": " ".join(x["w"].strip() for x in cur)})
            cur = []
    return out_


L = lines_of(kw)
if not L:
    sys.exit("nothing kept to render")
total_kept = sum(e - s for s, e in keep)
GREET = r"\b(?:hey|hi|hello|yo|what'?s (?:up|good)|welcome back)\b[^.?!]{0,40}\b(?:guys|everybody|everyone|youtube|y'all)\b|\bwelcome back\b"
OUTRO = (r"\bany ?ways?,? (?:guys|y'all)\b|\bthat'?s (?:pretty much |basically )?(?:it|all)\b(?: for (?:this|today))?|\bthat wraps\b|"
         r"\bthat'?ll be it\b|\bthat'?s gonna be it\b|\bhope you (?:guys )?enjoyed\b")
SIGNOFF = r"\b(?:peace|bye|see (?:y'?all|you(?: guys)?)|catch you|later|next (?:one|video)|take care|deuces)\b"
greet = None if SHORT else next((x for x in L[:max(3, len(L) // 4)] if re.search(GREET, x["text"], re.I)), None)
outro_l = None
for x in ([] if SHORT else L):
    if x["s"] > L[0]["s"] + 0.7 * (L[-1]["e"] - L[0]["s"]) and re.search(OUTRO, x["text"], re.I):
        outro_l = x
        break
sign_end = None
if outro_l:
    after = [x for x in L if x["s"] >= outro_l["s"]]
    hits = [x for x in after if re.search(SIGNOFF, x["text"], re.I)]
    if hits:   # the end of the last line holding the sign-off word ("... peace", "see you guys in the next one")
        sign_end = hits[-1]["e"]

cache = work / "haul_structure.json"
key = hashlib.md5(json.dumps([(round(x["s"], 1), x["text"]) for x in L]).encode()).hexdigest()
st = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() and not SHORT else {}
if st.get("key") != key and not SHORT:   # a Short has no intro / products / outro to find
    import claude_brain as B
    text = "\n".join(f"L{i} [{x['s'] // 60:.0f}:{x['s'] % 60:04.1f}] {x['text']}" for i, x in enumerate(L))
    prompt = f"""This is the transcript of a YouTube HAUL video: one creator films, on his phone, a pile of products he bought
(clothes, shoes, accessories ...) and shows them one after another. It was recorded in one take; this is what is KEPT.

Find:
1. intro_end: the LAST line of his spoken intro (greeting, what the haul is, how much it weighs/cost, "let's get into it"),
   i.e. the line right before he starts on the first product. The intro is usually 10-60 seconds.
2. products: every product in the order he shows them; for each, the line where he STARTS talking about it, and a short
   name (2-5 words, e.g. "Black Chrome Hearts hoodie"). Several of the same item count as one product.
3. outro_start: the line where he starts wrapping up ("anyways guys that's pretty much it ..."), or null.

TRANSCRIPT (line number, time, words)
{text}

Reply with ONLY JSON: {{"intro_end": <line>, "outro_start": <line or null>, "products": [{{"line": <line>, "name": "..."}}, ...]}}"""
    ans = B.ask("haul_structure", prompt, model="sonnet", say=say) or {}

    def li(v):
        try:
            i = int(str(v).lstrip("L"))
            return i if 0 <= i < len(L) else None
        except (TypeError, ValueError):
            return None
    prods = []
    for p in ans.get("products") or []:
        i = li(p.get("line"))
        if i is not None:
            prods.append({"raw": round(L[i]["s"], 3), "name": str(p.get("name") or "")[:50]})
    prods = sorted({p["raw"]: p for p in prods}.values(), key=lambda p: p["raw"])
    ie = li(ans.get("intro_end"))
    oi = li(ans.get("outro_start"))
    st = {"key": key, "intro_end": round(L[ie]["e"], 3) if ie is not None else None,
          "outro_ai": round(L[oi]["s"], 3) if oi is not None else None, "products": prods, "ai": bool(ans)}
    cache.write_text(json.dumps(st, indent=1), encoding="utf-8")

# greeting -> start, sign-off -> end; protects win (a user protect before the greeting keeps it)
prot = [(n["raw0"], n["raw1"]) for n in doc.get("notes", []) if n.get("kind") == "protect" and "raw0" in n and not n.get("off")]
t0 = greet["s"] - 0.15 if greet else keep[0][0]
if prot:
    t0 = min([t0] + [a for a, b in prot])
outro_s = outro_l["s"] if outro_l else st.get("outro_ai")
t1 = (sign_end + 0.6) if sign_end else keep[-1][1]
if prot:
    t1 = max([t1] + [b for a, b in prot])
before = sum(e - s for s, e in keep)
keep = [[max(s, t0), min(e, t1)] for s, e in keep if e > t0 and s < t1]
keep = [[round(s * FPS_SRC) / FPS_SRC, round(e * FPS_SRC) / FPS_SRC] for s, e in keep if e - s > 0.1]
dropped = before - sum(e - s for s, e in keep)
say(f"greeting: {greet['text'][:70] if greet else '(not found: starts at the first kept word)'}")
say(f"outro: {('%d:%04.1f ' % divmod(outro_s, 60)) if outro_s else ''}{(outro_l or {}).get('text', '(not found)')[:70]}"
    + (f"; sign-off ends {sign_end // 60:.0f}:{sign_end % 60:04.1f}" if sign_end else ""))
if dropped > 0.05:
    say(f"dropped {dropped:.1f} s kept before the greeting / after the sign-off")


def edit_time(t):
    acc = 0.0
    for s, e in keep:
        if t < s:
            return acc
        if t <= e:
            return acc + t - s
        acc += e - s
    return acc


out_len = sum(e - s for s, e in keep)
intro_end_raw = st.get("intro_end")
prods = [p for p in st.get("products") or [] if keep[0][0] - 1 < p["raw"] < keep[-1][1]]
if not intro_end_raw and prods:
    intro_end_raw = prods[0]["raw"]
intro_e = edit_time(intro_end_raw) if intro_end_raw else min(30.0, out_len)
if SHORT:
    intro_e = 0.0
elif intro_e < 4 or intro_e > 120:   # nonsense from the planner: the intro is 10-60 s in every haul so far
    say(f"intro end {intro_e:.1f} s looks wrong, using the first product / 30 s")
    intro_e = edit_time(prods[0]["raw"]) if prods and 4 < edit_time(prods[0]["raw"]) < 120 else min(30.0, out_len)
outro_e = edit_time(outro_s) if outro_s and (not intro_end_raw or outro_s > intro_end_raw) else None
say(f"intro: 0:00-{intro_e // 60:.0f}:{intro_e % 60:04.1f}; {len(prods)} products; edit {out_len / 60:.1f} min")
for p in prods:
    t = edit_time(p["raw"])
    say(f"  {t // 60:.0f}:{t % 60:04.1f}  {p['name']}")


def sel(ranges):
    t = [f"between(t,{s - 0.0005:.4f},{e - 0.0005:.4f})" for s, e in ranges]
    while len(t) > 1:
        t = [f"({t[i]}+{t[i + 1]})" if i + 1 < len(t) else t[i] for i in range(0, len(t), 2)]
    return t[0] if t else "0"


expr = sel(keep)
v = (f"[0:v]select='{expr}',setpts=N/FRAME_RATE/TB,fps={FPS},scale={W}:{H}:flags=lanczos,"
     f"fade=t=out:st={max(0.0, out_len - 1.0):.3f}:d=1.0,format=yuv420p[v]")
ZOOMS = []   # SHORT punch-ins, filled in once the edited words are known (section 3)
a = "[0:a:0]aselect='" + expr + "',asetpts=N/SR/TB,aresample=48000,afade=t=in:st=0:d=0.04[vo]"
n_in = 1
inputs = []

# ---- 3. music
EW = []
acc = 0.0
for s, e in keep:
    for w in words:
        if s <= w["s"] < e:
            EW.append({"w": w["w"], "s": acc + w["s"] - s, "e": acc + min(w["e"], e) - s})
    acc += e - s


# SHORT punch-ins on 3-4 KEY WORDS only (Grow with Alex, "Learn 90% of Claude Video Editing", 2026-10-23: "one steady framing
# per layout, punch-ins only on a few key words"; the first build alternated at every sentence). The words come from the
# card planner (tools/short_cards.py, cards.json "punch": raw time of the word -> end of its line, held 1.2-2.5 s); a 1.15x
# push-in on the upper third (the face). settings.short_zoom = false turns it off, a number sets the push-in.
if SHORT and S.get("short_zoom") is not False and EW:
    zf = float(S.get("short_zoom") or 1.15)
    cj_ = work / "cards" / "cards.json"
    for p in (json.loads(cj_.read_text(encoding="utf-8")).get("punch") or []) if cj_.exists() else []:
        za = edit_time(p["raw_s"])   # (not a / b: "a" is the audio graph)
        zb = min(out_len, max(za + 1.2, min(za + 2.5, edit_time(p["raw_e"]) + 0.15)))
        if zb - za > 0.6 and not any(x < zb and za < y for x, y in ZOOMS):
            ZOOMS.append((za, zb))
    if ZOOMS:
        en = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in ZOOMS)
        v = v.replace(f"scale={W}:{H}:flags=lanczos,", f"scale={W}:{H}:flags=lanczos,split[zf][zz];[zz]crop=iw/{zf}:ih/{zf}:(iw-ow)/2:(ih-oh)*0.35,"
                      f"scale={W}:{H}:flags=lanczos[zi];[zf][zi]overlay=0:0:enable='{en}',", 1)
        say(f"punch-ins: {len(ZOOMS)} x {zf}x on key words ({', '.join(f'{a // 60:.0f}:{a % 60:04.1f}' for a, b in ZOOMS)})")


def pause_near(t, win=4.0):
    best = None
    for x, y in zip(EW, EW[1:]):
        g0, g1 = x["e"], y["s"]
        if g1 - g0 >= 0.25 and abs((g0 + g1) / 2 - t) <= win:
            sc = (g1 - g0) - 0.15 * abs((g0 + g1) / 2 - t)
            if best is None or sc > best[0]:
                best = (sc, (g0 + g1) / 2)
    return best[1] if best else t


def usable(track):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", track, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    db = 20 * np.log10(np.sqrt((x[:len(x) // 4000 * 4000].reshape(-1, 4000) ** 2).mean(1)) + 1e-9)
    on = np.where(db > np.median(db) - 14)[0]
    return (on[-1] + 1) * 0.5 if len(on) else len(x) / 8000


def lufs(path, ss=0.0, t=None):
    cmd = ["ffmpeg", "-v", "info", "-ss", f"{ss:.3f}"] + (["-t", f"{t:.3f}"] if t else []) + ["-i", str(path), "-af", "ebur128", "-f", "null", "-"]
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", subprocess.run(cmd, capture_output=True, text=True, errors="replace").stderr)
    return float(m[-1]) if m else -20.0


VSCAN = Path(r"{{MUSIC_ROOT}}\_vocal_scan.json")
TAGS = ("beatstars", "prod", "beat by", "type beat", "free beat", "subscribe", "instagram", "youtube", "tagged")


def clean(track, model_box):
    """the no-vocal rule: medium.en, no VAD, highpass 200 Hz over the first 150 s; > 20 confident words = vocal, any producer tag = out"""
    db = json.loads(VSCAN.read_text(encoding="utf-8")) if VSCAN.exists() else {}
    k = f"{track}|{os.path.getsize(track)}"
    if k not in db:
        if not model_box:
            from whisper_gpu import load
            model_box.append(load("medium.en")[0])
        raw = subprocess.run(["ffmpeg", "-v", "error", "-t", "150", "-i", track, "-af", "highpass=f=200", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                             capture_output=True).stdout
        x = np.frombuffer(raw, dtype=np.float32)
        segs, _ = model_box[0].transcribe(x, vad_filter=False, condition_on_previous_text=False, no_speech_threshold=0.9, log_prob_threshold=-2.0)
        hits = [s.text.strip()[:80] for s in segs if s.avg_logprob > -1.0 and s.no_speech_prob < 0.7 and len(s.text.split()) >= 2]
        nw = sum(len(h.split()) for h in hits)
        tag = any(t_ in h.lower() for h in hits for t_ in TAGS)
        db[k] = {"verdict": "vocal" if nw > 20 else ("tag" if tag else "clean"), "words": nw, "hits": hits[:4]}
        VSCAN.write_text(json.dumps(db, indent=0), encoding="utf-8")
        say(f"vocal scan: {Path(track).name}: {db[k]['verdict']} ({nw} words)")
    # a pure beat gives 0-5 junk words; 19 (Drake "Feds Emotional Piano", 30kg haul) is too close to the 20-word vocal line
    return db[k]["verdict"] == "clean" and db[k]["words"] <= 8


beats = []
if S.get("music") is not False and os.environ.get("STUDIO_NO_MUSIC") != "1":
    hist_p = Path.home() / ".claude" / "skills" / "product-review-edit" / "work" / "music_history.json"
    hist = json.loads(hist_p.read_text(encoding="utf-8")) if hist_p.exists() else []
    mine = next((h["beats"] for h in reversed(hist) if h.get("project") == str(proj)), [])
    recent = {b for h in [h for h in hist if h.get("project") != str(proj)][-5:] for b in h["beats"]}
    root = Path(S.get("music_root") or r"{{MUSIC_ROOT}}\Type Beats")
    pool = sorted(p for p in root.rglob("*") if p.suffix.lower() in (".mp3", ".wav", ".m4a") and "lo-fi" not in str(p).lower())
    rng = random.Random(sum(map(ord, str(doc.get("id") or title))))
    rng.shuffle(pool)
    # a re-render keeps its beats; otherwise beats not used in the last 5 videos first (user: stop reusing the same tracks)
    order = [p for n in mine for p in pool if p.name == n] + [p for p in pool if p.name not in recent and p.name not in mine] + \
            [p for p in pool if p.name in recent and p.name not in mine]
    # the WHOLE {{MUSIC_ROOT}} library first (user 2026-10-24: "we've been using the same tracks over and over again"):
    # music_lib orders beats by fit to this video's title + transcript, skips the channel's last 15 videos and spreads
    # artists; a re-render still keeps its own beats (mine) first. The folder shuffle above stays the fallback tail.
    try:
        sys.path.insert(0, r"{{KIT}}/tools")
        import music_lib
        lib = [Path(t) for t in music_lib.pick("short" if SHORT else "haul", 14, title=title, channel=doc.get("channel") or None,
                                                 project=str(proj), min_len=20, log=False, keep=False)]
        head = [p for n in mine for p in order if p.name == n]
        order = head + [p for p in lib if p.name not in mine] + [p for p in order if p not in head and p not in lib]
        order = [p for p in order if not music_lib.retired(p)]   # copyright-claimed = retired (Uploads, 2026-10-26)
    except Exception as e:
        music_lib = None
        say(f"music_lib skipped: {type(e).__name__}: {str(e)[:160]}")
    # user 2026-10-23 (30kg haul): "the intro gets its own music. Throughout the whole video you're going to change the
    # track: once one ends, the next one's going to go, and then the outro is going to get its own music."
    # -> intro = its own beat (switches on the pause at the intro end); body = beats played through, the next one starting
    # when one runs out (never looped, switch on a pause near its end); outro = another beat of its own.
    model_box, chosen = [], []
    k = 0

    def next_track(min_len=40):
        global k
        while k < len(order):
            tr = str(order[k])
            k += 1
            if clean(tr, model_box):
                room = usable(tr) - 2.0
                if room >= min_len:
                    return tr, room
        return None, 0

    has_outro = bool(outro_e and intro_e < outro_e < out_len - 3)
    body_end = outro_e if has_outro else out_len
    if SHORT:   # a Short: beats from 0:00, no intro beat
        tr, i_end = True, 0.0
    else:
        i_end = round(pause_near(intro_e, 1.5), 3)
        tr, room = next_track(20)
        if tr:
            beats.append({"s": 0.0, "e": i_end, "track": tr, "part": "intro"})
            chosen.append(Path(tr).name)
    t = i_end
    while tr and t < body_end - 0.5:
        tr, room = next_track(min(40.0, max(10.0, out_len - t)))
        if not tr:
            break
        end_max = t + room
        e = body_end if end_max >= body_end - 8 else min(end_max, pause_near(end_max - 3.0, 3.0))
        if end_max >= body_end - 8 and end_max < body_end:   # a beat that would stop just short: let the next one carry the tail
            e = min(end_max, pause_near(end_max - 3.0, 3.0))
        beats.append({"s": round(t, 3), "e": round(e, 3), "track": tr, "part": "body"})
        chosen.append(Path(tr).name)
        t = e
    if beats and has_outro:
        tr, room = next_track(15)
        if tr:
            beats[-1]["e"] = round(pause_near(outro_e, 2.0), 3)
            beats = [b for b in beats if b["e"] - b["s"] > 1.0]
            beats.append({"s": beats[-1]["e"], "e": round(out_len, 3), "track": tr, "part": "outro"})
            chosen.append(Path(tr).name)
    if beats:
        hist = [h for h in hist if h.get("project") != str(proj)] + [{"project": str(proj), "date": __import__("time").strftime("%Y-%m-%d"),
                                                                    "beats": list(dict.fromkeys(chosen)), "type": "short" if SHORT else "haul"}]
        hist_p.write_text(json.dumps(hist, indent=2), encoding="utf-8")
        try:
            music_lib.log_use(str(proj), "short" if SHORT else "haul", list(dict.fromkeys(b["track"] for b in beats)),
                              doc.get("channel") or None, title)
        except Exception:
            pass

if beats:
    # volume follows the voice: each beat sits 15 LU under the voice of ITS stretch (edited mic, measured per beat)
    tmpv = work / "haul_voice.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-map", "0:a:0", "-af", f"aselect='{expr}',asetpts=N/SR/TB", "-ac", "1", "-ar", "48000",
                    str(tmpv)], check=True)
    XF = 1.5
    mixes = ["[vo]"]
    for k, b in enumerate(beats):
        s0 = max(0.0, b["s"] - (XF / 2 if k else 0))
        e0 = min(out_len, b["e"] + (XF / 2 if k < len(beats) - 1 else 0))
        d = e0 - s0
        vl = lufs(tmpv, b["s"], max(3.0, b["e"] - b["s"]))
        vl = max(-30.0, min(-12.0, vl))
        ss = 0.0
        gain = vl - 15.0 - lufs(b["track"], ss, min(d, 90))
        b["gain_db"], b["voice_lufs"] = round(gain, 2), round(vl, 1)
        inputs += ["-ss", f"{ss:.2f}", "-i", b["track"]]
        fin = f"afade=t=in:st=0:d={XF}," if k else "afade=t=in:st=0:d=0.5,"
        fout = f"afade=t=out:st={d - XF:.3f}:d={XF}" if k < len(beats) - 1 else f"afade=t=out:st={max(0.0, d - 3):.3f}:d=3"
        a += (f";[{n_in}:a]atrim=0:{d:.3f},asetpts=N/SR/TB,aresample=48000,aformat=channel_layouts=stereo,volume={gain:.2f}dB,{fin}{fout},"
              f"adelay={int(s0 * 1000)}:all=1[mu{k}]")
        mixes.append(f"[mu{k}]")
        n_in += 1
    a += f";{''.join(mixes)}amix=inputs={len(mixes)}:duration=first:normalize=0[vm]"
    last = "vm"
    for b in beats:
        say(f"music {b['s'] // 60:.0f}:{b['s'] % 60:04.1f}-{b['e'] // 60:.0f}:{b['e'] % 60:04.1f} {Path(b['track']).name[:48]} "
            f"({b['gain_db']:+.1f} dB, voice {b['voice_lufs']} LUFS)[{b.get('part', '')}]")
else:
    last = "vo"
    say("music: none")
# true-peak limiter after loudnorm: the AAC encode overshot to -0.8 dBTP on the first draft (target <= -1)
a += f";[{last}]loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000,alimiter=limit=0.75:level=false:attack=2:release=50[a]"

# ---- 4. Doug captions over the intro AND the outro (user 2026-10-23, 30kg haul: "it didn't even go to the outro captions"),
# none in the body. medium.en on the edited audio of each stretch. The outro stretch starts at the detected outro, or at
# settings.haul_outro_captions_from (a RAW recording time, e.g. the wrap-up sentence before "anyways guys").
cap_style = (S.get("haul_captions") or "doug") if S.get("haul_captions") is not False else None
if SHORT and cap_style == "doug":
    cap_style = "doug_v"   # the 1080p sizes are fractions of the height: 293 px letters on a 1920-tall Short


def stretch_words(a0, a1, name):
    """Whisper words (edit times) for the edited stretch a0-a1, cached on keep + range"""
    sig = hashlib.md5(json.dumps([keep, round(a0, 3), round(a1, 3)]).encode()).hexdigest()
    cw = work / f"haul_{name}_words.json"
    cached = json.loads(cw.read_text(encoding="utf-8")) if cw.exists() else {}
    if cached.get("sig") == sig:
        return cached["words"]
    with wave.open(str(work / "mic16k.wav")) as wf:
        sr_ = wf.getframerate()
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), np.int16)
    xa, acc = [], 0.0
    for s, e in keep:   # the edited audio from a0 to a1 (+1 s so the last word is whole)
        lo, hi = max(s, s + a0 - acc), min(e, s + a1 + 1 - acc)
        if hi > lo:
            xa.append(pcm[int(lo * sr_):int(hi * sr_)])
        acc += e - s
        if acc >= a1 + 1:
            break
    xa = np.concatenate(xa).astype(np.float32) / 32768
    from whisper_gpu import load
    wm, where = load("medium.en")
    vocab = S.get("vocabulary") or ["DHgate"]
    segs, _ = wm.transcribe(xa, language="en", word_timestamps=True, condition_on_previous_text=False,
                            initial_prompt="So, um, " + ", ".join(vocab) + ".")
    ws = [{"w": x.word.strip(), "s": round(a0 + x.start, 3), "e": round(a0 + x.end, 3)} for sg in segs for x in (sg.words or [])]
    cw.write_text(json.dumps({"sig": sig, "words": ws}), encoding="utf-8")
    return ws


W_CAP, H_CAP = (1080, 1920) if SHORT else (1920, 1080)   # captions are laid out on the FINAL canvas (the draft scales them)
if cap_style:
    spans = [("short", 0.0, out_len)] if SHORT else [("intro", 0.0, intro_e)] if intro_e > 1 else []
    oc_raw = S.get("haul_outro_captions_from")
    oc = edit_time(float(oc_raw)) if oc_raw else outro_e
    if not SHORT and oc and oc > intro_e + 1 and out_len - oc > 1:
        spans.append(("outro", oc, out_len))
    head, dlg, said = None, [], []
    cap_all, cap_shown, cap_changes = [], [], []   # for <project>/captions.json (the editor draws + fixes captions from it)
    for name, a0, a1 in spans:
        ws = [x for x in stretch_words(a0, a1, name) if a0 - 0.05 <= x["s"] < a1 - 0.05]
        ws, ch = CAPS.CF.apply(ws, doc, say=say)   # AI typo pass + the editor's manual fixes (tools/caption_fixes.py)
        cap_all += ws
        cap_changes += ch
        ass = CAPS.build_ass(ws, W_CAP, H_CAP, cap_style, shown=cap_shown)
        lines = ass.splitlines()
        k = next(i for i, ln in enumerate(lines) if ln.startswith("Dialogue:")) if any(ln.startswith("Dialogue:") for ln in lines) else len(lines)
        head = head or lines[:k]
        for ln in lines[k:]:
            if ln.startswith("Dialogue:"):   # nothing may hang past its stretch
                parts = ln.split(",", 9)
                hh, mm, ss_ = parts[2].split(":")
                if int(hh) * 3600 + int(mm) * 60 + float(ss_) > a1:
                    parts[2] = CAPS._t(a1)
                ln = ",".join(parts)
                dlg.append(ln)
        said.append(f"{name} {a0 // 60:.0f}:{a0 % 60:04.1f}-{a1 // 60:.0f}:{a1 % 60:04.1f} ({len(ws)} words)")
    CAPS.CF.record(proj, out.name, cap_all, cap_shown, cap_changes, cap_style)
    if SHORT and S.get("short_hook") is not False and EW and head:
        # hook headline: 3-6 words naming what the Short is about, top of the frame for the first ~3 s, one keyword yellow.
        # settings.short_hook = "text" overrides it ("*word*" marks the keyword), false turns it off.
        hk = work / "short_hook.json"
        said_txt = " ".join(x["w"] for x in EW)[:1500]
        hook = S.get("short_hook") if isinstance(S.get("short_hook"), str) else None
        if not hook:
            cached = json.loads(hk.read_text(encoding="utf-8")) if hk.exists() else {}
            if cached.get("said") == said_txt:
                hook = cached.get("hook")
            else:
                try:
                    import claude_brain as B
                    ans = B.ask("short_hook", "This is everything said in a vertical YouTube Short (talking head):\n" + said_txt +
                                "\n\nWrite the on-screen HOOK HEADLINE shown over the first 3 seconds: 3-6 words, the claim or question that makes "
                                "someone stop scrolling, in the creator's own terms, no emoji, no hashtags, sentence case. Mark the ONE most "
                                "important word with *stars*. Reply ONLY JSON {\"hook\": \"...\"}", say=say) or {}
                    hook = str(ans.get("hook") or "").strip()[:60] or None
                except Exception as ex:  # noqa: a headline never stops a build
                    say(f"hook headline skipped ({type(ex).__name__}: {str(ex)[:100]})")
                hk.write_text(json.dumps({"said": said_txt, "hook": hook}), encoding="utf-8")
        if hook:
            hend = min(3.2, out_len)
            fam = CAPS.font_for(cap_style)[0]
            # measure, don't guess (Grow with Alex: "find the highest point of my head before framing anything over it"):
            # the face detector on 3 frames of the hook; the head top = face top - 35 % of the face height. The headline
            # goes in the space above the head (smaller to fit); with too little room it sits on the chest above the captions.
            hook_size, hook_align, hook_mv = round(H_CAP * 0.07), 8, round(H_CAP * 0.06)
            try:
                import mediapipe as mp
                from mediapipe.tasks.python import vision, BaseOptions
                FM = r"{{KIT}}/review_pipeline/models/face_landmarker.task"   # as gaming/glib.py
                lm = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=FM), num_faces=1))
                tops = []
                for tt in (0.4, 1.4, 2.6):
                    traw = keep[0][0] + tt   # close enough: the hook is the first kept piece or two
                    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{traw:.2f}", "-i", src, "-frames:v", "1", "-vf", "scale=540:960",
                                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
                    if len(raw) == 540 * 960 * 3:
                        r_ = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.frombuffer(raw, np.uint8).reshape(960, 540, 3).copy()))
                        if r_.face_landmarks:
                            ys = [q.y for q in r_.face_landmarks[0]]
                            # the mesh stops at the forehead: the skull top is ~30 % of the mesh height above it
                            tops.append((min(ys) - 0.3 * (max(ys) - min(ys))) * 1920)
                if tops:
                    room = min(tops) - 50   # px above the highest head top, on the 1920-tall canvas
                    lines = 2 if len(hook.split()) > 3 else 1
                    fit = room / (lines * 1.18) - 10
                    if fit >= H_CAP * 0.04:
                        hook_size = round(min(H_CAP * 0.07, fit))
                        hook_mv = max(30, round((room - lines * 1.18 * hook_size) / 2) + 20)
                        where = "above the head"
                    else:
                        hook_align, hook_mv = 2, round(H_CAP * 0.42)
                        where = "on the chest (no room above the head)"
                    say(f"hook: head top {min(tops):.0f} px -> {where}, {hook_size} px")
            except Exception as ex:  # noqa: placement never stops a build
                say(f"hook placement default ({type(ex).__name__}: {str(ex)[:80]})")
            hw = hook.replace("{", "(").replace("}", ")").split()
            if len(hw) > 3:   # two lines, the shorter one first (these subtitles never auto-wrap)
                k = len(hw) // 2
                hw = [" ".join(hw[:k]) + r"\N" + hw[k]] + hw[k + 1:] if k < len(hw) else hw
            txt = re.sub(r"\*([^*]+)\*", r"{\\c&H00FFFF&}\1{\\c&HFFFFFF&}", " ".join(hw))
            head = head + [] if any(ln.startswith("Style: Hook") for ln in head) else \
                [ln for ln in head if not ln.startswith("[Events]") and not ln.startswith("Format: Layer")] + \
                [f"Style: Hook,{fam},{hook_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,"
                 f"{max(4, round(hook_size * 0.1))},{round(H_CAP * 0.002)},{hook_align},{round(W_CAP * 0.08)},{round(W_CAP * 0.08)},{hook_mv},1"] + \
                [ln for ln in head if ln.startswith("[Events]") or ln.startswith("Format: Layer")]
            dlg.insert(0, f"Dialogue: 1,{CAPS._t(0.0)},{CAPS._t(hend)},Hook,,0,0,0,,{{\\fad(120,200)}}{txt}")
            said.append(f"hook '{hook}' 0-{hend:.1f} s")
    if dlg:
        (work / "haul_captions.ass").write_text("\n".join(head + dlg) + "\n", encoding="utf-8")
        v = v[:-len("format=yuv420p[v]")] + CAPS._filt(work / "haul_captions.ass") + ",format=yuv420p[v]"
        say(f"captions: {CAPS.PRESETS[cap_style]['label']} over " + ", ".join(said) + f", font {CAPS.font_for(cap_style)[0]}")

# ---- 5. SHORT explainer cards (tools/short_cards.py, user 2026-10-23: "Joseph-style white explainer cards + keyword visuals"):
# full-screen white cards cut in over the talking head (and over its captions: a card has its own headline), raw -> edit time
cards_p = work / "cards" / "cards.json"
if SHORT and S.get("short_cards") is not False and cards_p.exists():
    placed = []
    for it in json.loads(cards_p.read_text(encoding="utf-8")).get("items") or []:
        s0 = edit_time(it["raw_s"])
        d = min(float(it["dur"]), out_len - s0 - 0.05)
        if d >= 0.8 and Path(it.get("file") or "").exists() and not any(a < s0 + d and s0 < b for a, b in placed):
            placed.append((s0, s0 + d))
            inputs += ["-i", it["file"]]
            k = len(placed) - 1
            v = v[:-len("[v]")] + f"[vc{k}];[{n_in}:v]scale={W}:{H}:flags=lanczos,fps={FPS},setpts=PTS-STARTPTS+{s0:.3f}/TB[ci{k}];" \
                f"[vc{k}][ci{k}]overlay=0:0:eof_action=pass:enable='between(t,{s0:.3f},{s0 + d:.3f})'[v]"
            n_in += 1
    if placed:
        say(f"cards: {len(placed)} over {sum(b - a for a, b in placed):.1f} s of {out_len:.1f} s ("
            + ", ".join(f"{a // 60:.0f}:{a % 60:04.1f}" for a, b in placed) + ")")

graph = work / "haul-graph.txt"
graph.write_text(v + ";" + a, encoding="utf-8")
if os.environ.get("HAUL_DRY") == "1":   # plan only (structure, music, captions), no render
    sys.exit(0)
say(f"{'short' if SHORT else 'haul'} render: {len(keep)} pieces, {out_len / 60:.2f} of {si['duration'] / 60:.1f} min kept -> {W}x{H} {FPS} fps")
cmd = ["ffmpeg", "-v", "error", "-stats", "-y", "-i", src, *inputs, "-/filter_complex", str(graph), "-map", "[v]", "-map", "[a]",
       "-c:v", "h264_nvenc", "-profile:v", "high", "-pix_fmt", "yuv420p", "-preset", "p5", "-rc", "vbr", "-b:v", "0", "-cq", "23" if DRAFT else "17",
       "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out)]
subprocess.run(cmd, check=True, cwd=str(work))
vd, ad = stream_durs(out)
if vd is None or ad is None or abs(vd - ad) > 0.15 or abs(vd - out_len) > 0.5:
    sys.exit(f"render check FAILED: picture {vd} s, sound {ad} s, expected {out_len:.2f} s")
c = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,profile,pix_fmt",
                               "-of", "json", str(out)], capture_output=True, text=True).stdout)["streams"][0]
if c["codec_name"] != "h264" or c["pix_fmt"] != "yuv420p":
    sys.exit(f"render is {c}, not H.264 yuv420p")
(work / ("timeline-short.json" if SHORT else "timeline-haul.json")).write_text(json.dumps({
    "keep": keep, "intro": 0.0, "speed": 1.0, "out": str(out), "intro_end": round(intro_e, 3), "outro_start": round(outro_e, 3) if outro_e else None,
    "sections": [["Short", 0.0, round(out_len, 3)]] if SHORT else [["Intro", 0.0, round(intro_e, 3)]] + [[p["name"], round(edit_time(p["raw"]), 3), None] for p in prods]
    + ([["Outro", round(outro_e, 3), round(out_len, 3)]] if outro_e else []),
    "products": prods, "music": beats}, indent=1), encoding="utf-8")
say(f"wrote {out} ({out_len / 60:.2f} min, picture {vd:.2f} s / sound {ad:.2f} s, h264 {c['profile']})")

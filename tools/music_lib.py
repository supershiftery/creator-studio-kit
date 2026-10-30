"""The whole {{MUSIC_ROOT}} library as one picker (user 2026-10-24: "we've been using the same tracks over and over again, like
probably the same 10, we probably should incorporate our whole library of like type beats and like music that fits the
category well"; 2026-10-23 Chime: "analyze our music and themes and moods and tailor it toward the video").

Index ({{MUSIC_ROOT}}\\_index.json, one-time + incremental, keyed by path, redone when size/mtime change):
  category / sub (from the folder), duration, usable seconds (minus the fade-out tail), BPM, energy 0-1, brightness,
  steadiness, beat switch, mood scores, and the no-vocal-music verdict: medium.en Whisper, vad off, 200 Hz highpass,
  first 150 s + a late window; > 8 confident words or any producer tag (BeatStars, prod by...) = rejected.
Picker: pick(kind, ...) gives each video a mood from its type, title and transcript (product review = type beats that
  fit the brand's vibe, phone/app = clean steady beats, gaming = other games' OSTs never Minecraft's, chill screen
  recordings = calm but not all lo-fi), draws from the whole library and logs every use (_state/music_log.json) so no
  track repeats across the last 15 videos of that channel (or the last 5 of any channel).
CLI:
  python music_lib.py index [--no-scan]        build / update the index (the Whisper scan waits while Studio renders)
  python music_lib.py show [kind]              tracks the picker may use, by mood
  python music_lib.py dry <project> [kind]     what a project would get (no log write)
Overrides: {{MUSIC_ROOT}}\\_music_overrides.json {"block": [name substrings], "allow": [name substrings]}."""
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import time

import numpy as np

ROOT = r"{{MUSIC_ROOT}}"
import music_kit as _kit  # noqa: E402  kit: library + extra roots from Studio -> Settings, genre from the audio
ROOT, EXTRA_ROOTS = _kit.roots(ROOT)
INDEX = os.path.join(ROOT, "_index.json")
OVERRIDES = os.path.join(ROOT, "_music_overrides.json")
VSCAN = os.path.join(ROOT, "_vocal_scan.json")     # the haul/short renderer's scan cache (same key format, kept in sync)
HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "_state", "music_log.json")
EXT = (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus")
SKIP_DIRS = ("sound effects", "personal archive")   # SFX + his diss tracks / channel clips are never a bed
TAGS = ("beatstars", "prod by", "prod. by", "produced by", "beat by", "type beat", "free beat", "subscribe", "instagram",
        "youtube", "tagged", "soundcloud", "download", "made this", "on the beat", "on the track", "in the booth")
# Whisper's stock hallucinations on quiet tails, not words in the track
HALLU = re.compile(r"^\W*(thanks?( you)? (so much )?for watching( guys)?|thank you|you|bye|\.+)\W*$", re.I)
RECENT_CHANNEL, RECENT_GLOBAL = 15, 5

MOODS = ("chill", "smooth", "dark", "hype", "upbeat", "emotional", "oldschool", "epic", "playful", "calm")
# words in the file name / folder -> mood
KW = {
    "chill": r"lo-?fi|lo fi|chill|relax|jazz|study|sleep|cozy|mellow|interstellar|autumn",
    "smooth": r"\br ?n ?b\b|r&b|smooth|soul|love|melodic|vibe|wave|close to me|luxury|silk|velvet|kendall|sade",
    "dark": r"dark|evil|menac|sinister|horror|night|drill|phonk|demon|grim|trouble|thug|shadow|haunt|creep",
    "hype": r"hard|aggressive|fire|rage|hype|banger|energy|enrgy|drill|strikes|\brun\b|war\b|punch|crazy|turn up|bounce",
    "upbeat": r"happy|summer|fun\b|party|upbeat|sunny|good vibes|\bwin\b|celebrat|bright|groove|dance|ncs|funk",
    "emotional": r"emotional|sad|pain|cry|heart|tears|reflect|thought|memor|lonely|feels|piano",
    "oldschool": r"boom ?bap|old ?school|90s|jazzy|sample|golden|classic|east coast|new york",
    "epic": r"epic|cinematic|orchestr|battle|boss|trailer|legend|final|champion|victory|hero|inferno|armada",
    "playful": r"theme|town|route|mario|kirby|sonic|pokemon|pok.mon|smash|zelda|jingle|cypher|shop|cafe|bebop",
    "calm": r"ambient|calm|peace|village|field|rain|lullab|piano cover|forest|ocean|morning",
}
# folder priors (category / sub) -> mood weights
FOLDER = {
    "type beats/lo-fi": {"chill": 2, "calm": 1}, "type beats/old school boom bap": {"oldschool": 2, "chill": 0.5},
    "type beats/hard trap": {"hype": 2, "dark": 0.5}, "type beats/detroit": {"hype": 1.5, "dark": 1},
    "type beats/flint (enrgy)": {"hype": 2}, "type beats/philly (kur-style)": {"hype": 1, "dark": 1}, "type beats/kur": {"hype": 1, "dark": 1},
    "type beats/underground (suicideboys-bones)": {"dark": 2}, "type beats/drake": {"smooth": 1.5, "emotional": 0.5},
    "type beats/j cole": {"oldschool": 1, "emotional": 1, "smooth": 0.5}, "type beats/logic": {"oldschool": 1, "upbeat": 0.5, "emotional": 0.5},
    "type beats/big sean": {"smooth": 1, "hype": 0.5}, "type beats/jack harlow": {"upbeat": 1, "smooth": 1},
    "type beats/gunna": {"smooth": 1, "dark": 0.5}, "type beats/meek mill": {"hype": 1, "emotional": 0.5},
    "type beats/dave east": {"oldschool": 1, "dark": 0.5}, "type beats/wondagurl": {"dark": 1, "smooth": 0.5},
    "type beats/moneybagg yo": {"hype": 1, "dark": 0.5}, "type beats/ytb fatt": {"hype": 1, "dark": 0.5},
    "type beats/tre capital": {"hype": 1}, "type beats/vonoff1700": {"hype": 1, "dark": 0.5},
    "type beats/other artists": {}, "electronic & ncs": {"upbeat": 1.5, "hype": 0.5},
    "cinematic & background": {"epic": 1, "calm": 1}, "anime/piano covers": {"calm": 1.5, "emotional": 1.5},
    "anime/soundtracks": {"epic": 1.5, "emotional": 0.5}, "game & anime beats": {"hype": 1, "playful": 1},
    "game music": {"playful": 1.5, "epic": 0.5}, "pokemon": {"playful": 2}, "instrumentals (real songs)": {"smooth": 0.5, "upbeat": 0.5},
    **_kit.MOOD_FOLDERS,   # kit: the mood library setup makes
}


def _cat(rel):
    parts = rel.replace("\\", "/").split("/")
    cat = parts[0]
    sub = parts[1] if len(parts) > 2 else ""
    genre = {"Type Beats": "lofi" if sub == "Lo-Fi" else "type beat", "Game Music": "game ost", "Pokemon": "pokemon",
             "Game & Anime Beats": "game beat", "Anime": "anime", "Electronic & NCS": "electronic",
             "Cinematic & Background": "cinematic", "Instrumentals (Real Songs)": "instrumental"}.get(cat, "other")
    return cat, sub, genre


def _pcm(path, sr=11025, ss=None, t=None, af=None):
    cmd = ["ffmpeg", "-v", "error"] + (["-ss", f"{ss:.2f}"] if ss else []) + (["-t", f"{t:.2f}"] if t else []) + ["-i", path]
    cmd += (["-af", af] if af else []) + ["-ac", "1", "-ar", str(sr), "-f", "f32le", "-"]
    return np.frombuffer(subprocess.run(cmd, capture_output=True).stdout, np.float32)


def features(path):
    """duration, usable seconds, bpm, energy, brightness, steadiness, beat switch: numpy only (no librosa here)"""
    sr = 11025
    a = _pcm(path, sr)
    dur = len(a) / sr
    if dur < 5:
        return {"dur": round(dur, 1), "bad": "too short / undecodable"}
    w = sr // 2
    n = len(a) // w
    db = 20 * np.log10(np.sqrt((a[:n * w].reshape(n, w) ** 2).mean(1)) + 1e-9)   # 0.5 s windows
    on = np.where(db > np.median(db) - 14)[0]
    usable = (on[-1] + 1) * 0.5 if len(on) else dur
    first = on[0] * 0.5 if len(on) else 0.0
    b0 = int(min(first + 8, dur / 3) * 2)   # past the lead-in (a quiet intro is not "unsteady")
    body = db[b0: max(int(usable * 2) - 4, b0 + 4)]
    # steadiness: spread of 3 s loudness over the body (low = a steady bed, what phone videos want; no drop tricks)
    k = 6
    blk = np.array([body[i:i + k].mean() for i in range(0, max(1, len(body) - k), k)]) if len(body) > k else body
    spread = float(np.std(blk)) if len(blk) > 1 else 0.0
    # spectral: a 60 s window from the body
    s0 = int(min(max(first + 5, dur * 0.25), max(0, dur - 60)) * sr)
    x = a[s0:s0 + 60 * sr]
    hop, nf = 256, 1024
    frames = np.lib.stride_tricks.sliding_window_view(x, nf)[::hop] * np.hanning(nf) if len(x) > nf * 4 else None
    bpm = bright = low = flux_r = 0.0
    if frames is not None:
        S = np.abs(np.fft.rfft(frames, axis=1))
        fr = np.fft.rfftfreq(nf, 1 / sr)
        tot = S.sum(1) + 1e-9
        bright = float(np.median((S * fr).sum(1) / tot))
        low = float((S[:, fr < 150].sum(1) / tot).mean())
        L = np.log1p(S * 10)
        flux = np.maximum(0, np.diff(L, axis=0)).sum(1)
        flux = flux - np.convolve(flux, np.ones(16) / 16, "same")
        flux = np.maximum(flux, 0)
        flux_r = float(flux.mean() / (L.mean() * L.shape[1] + 1e-9))
        # tempo: autocorrelation of the onset envelope, 70-180 BPM, the strongest peak with a light 100-140 prior
        fps = sr / hop
        f = flux - flux.mean()
        ac = np.correlate(f, f, "full")[len(f) - 1:]
        lags = np.arange(len(ac))
        ok = (lags >= fps * 60 / 180) & (lags <= fps * 60 / 70)
        if ok.any() and ac[0] > 0:
            bpms = 60 * fps / np.maximum(lags, 1)
            score = ac / ac[0] * np.exp(-0.5 * ((np.log2(bpms / 120)) / 0.9) ** 2)
            score[~ok] = -1
            i = int(np.argmax(score))
            if 1 <= i < len(ac) - 1:   # parabolic interpolation for a finer tempo
                y0, y1, y2 = ac[i - 1], ac[i], ac[i + 1]
                d = 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2 + 1e-9)
                bpm = float(60 * fps / (i + d))
    # beat switch: a long stretch whose brightness / low end jumps compared to the first half
    switch = False
    if dur > 90:
        h = _pcm(path, 4000, ss=max(0, usable * 0.6), t=30)
        g = _pcm(path, 4000, ss=max(0, first + 8), t=30)
        if len(h) > 4000 and len(g) > 4000:
            def cen(z):
                F = np.abs(np.fft.rfft(z[:len(z) // 1024 * 1024].reshape(-1, 1024), axis=1))
                fq = np.fft.rfftfreq(1024, 1 / 4000)
                return float(np.median((F * fq).sum(1) / (F.sum(1) + 1e-9)))
            c1, c2 = cen(g), cen(h)
            switch = abs(c1 - c2) / max(c1, c2, 1) > 0.35
    return {"dur": round(dur, 1), "usable": round(float(usable), 1), "lead_in": round(float(first), 1), "bpm": round(bpm, 1),
            "loud_db": round(float(np.median(body)) if len(body) else -40.0, 1), "spread": round(spread, 2),
            "bright": round(bright), "low": round(low, 3), "flux": round(flux_r, 4), "switch": bool(switch)}


_MODEL = []


def _studio_busy():
    """a Studio job is rendering (one GPU build at a time): the Whisper scan waits"""
    try:
        import urllib.request
        j = json.load(urllib.request.urlopen(f"http://localhost:{_kit.port()}/api/jobs", timeout=3))
        return any(x.get("status") == "running" for x in j.get("jobs", []))
    except Exception:
        return False


def vocal_scan(path, dur, wait=True, say=print):
    """the no-vocal-music rule: medium.en, vad off, highpass 200 Hz over the first 150 s plus a 90 s late window (a voice
    outro at 584 s got through a first-150-s scan: Undella Town). > 8 confident words = vocal, any tag = out."""
    while wait and _studio_busy() and os.environ.get("MUSIC_SCAN_NOWAIT") != "1":
        say("  (Studio is rendering: the vocal scan waits 60 s)")
        time.sleep(60)
    if not _MODEL:
        sys.path.insert(0, HERE)
        from whisper_gpu import load
        _MODEL.append(load("medium.en")[0])
    hits = []
    wins = [(0, 150)] + ([(max(150, dur * 0.7 - 45), 90)] if dur > 200 else [])
    for ss, t in wins:
        x = _pcm(path, 16000, ss=ss, t=t, af="highpass=f=200")
        if len(x) < 16000:
            continue
        segs, _ = _MODEL[0].transcribe(x, vad_filter=False, condition_on_previous_text=False, no_speech_threshold=0.9,
                                       log_prob_threshold=-2.0, language="en", beam_size=1, best_of=1, temperature=0.0)   # greedy, no fallback retries: words-or-not
        hits += [f"{ss + s.start:.0f}s {s.text.strip()[:80]}" for s in segs
                 if s.avg_logprob > -1.0 and s.no_speech_prob < 0.7 and len(s.text.split()) >= 2 and not HALLU.match(s.text.strip())]
    nw = sum(len(h.split()) - 1 for h in hits)
    tag = any(t_ in h.lower() for h in hits for t_ in TAGS)
    # a spoken line of 4+ words is a voice (producer tag "This was PRPLPRNCH, and I'm out!", a sample shout), not junk;
    # pure beats give 0-4 scattered junk words
    line = any(len(h.split()) - 1 >= 4 for h in hits)
    verdict = "vocal" if nw > 20 else ("tag" if tag or line else ("words" if nw > 4 else "clean"))
    return {"verdict": verdict, "words": nw, "hits": hits[:5], "scanned": "medium.en novad hp200 v3"}


def mood_scores(rel, f):
    name = os.path.splitext(os.path.basename(rel))[0].lower()
    folder = os.path.dirname(rel).replace("\\", "/").lower()
    sc = {m: 0.0 for m in MOODS}
    for m, rx in KW.items():
        if re.search(rx, name):
            sc[m] += 1.5
        if re.search(rx, folder):
            sc[m] += 0.5
    pri = FOLDER.get(folder) or FOLDER.get(folder.split("/")[0]) or {}
    for m, v in pri.items():
        sc[m] += v
    e = f.get("energy", 0.5)
    sc["hype"] += 1.5 * max(0, e - 0.55) * 2
    sc["upbeat"] += 1.0 * max(0, e - 0.5) * 2 * (1 if f.get("bright", 0) > 1300 else 0.4)
    sc["chill"] += 1.5 * max(0, 0.45 - e) * 2
    sc["calm"] += 1.5 * max(0, 0.35 - e) * 2
    if f.get("bpm", 0) and f["bpm"] < 85:
        sc["chill"] += 0.3
        sc["emotional"] += 0.2
    if f.get("bright", 2000) < 600:
        sc["dark"] += 0.3
    return {m: round(v, 2) for m, v in sc.items()}


def _energy(recs):
    """energy 0-1 = percentile of (onset strength + loudness + low end) across the library, so mastering doesn't decide it"""
    keys = [k for k, r in recs.items() if "flux" in r]
    if not keys:
        return
    def pct(v):
        order = np.argsort(np.argsort(v))
        return order / max(1, len(v) - 1)
    fl = pct(np.array([recs[k]["flux"] for k in keys]))
    ld = pct(np.array([recs[k]["loud_db"] for k in keys]))
    lo = pct(np.array([recs[k]["low"] for k in keys]))
    for i, k in enumerate(keys):
        recs[k]["energy"] = round(float(0.5 * fl[i] + 0.3 * ld[i] + 0.2 * lo[i]), 3)


def load_index():
    try:
        return json.load(open(INDEX, encoding="utf-8"))
    except (OSError, ValueError):
        return {"tracks": {}}


def save_index(idx):
    tmp = INDEX + ".tmp"
    json.dump(idx, open(tmp, "w", encoding="utf-8"), indent=0, ensure_ascii=False)
    os.replace(tmp, INDEX)


def _files():
    yield from _kit.files(ROOT, EXTRA_ROOTS, SKIP_DIRS, EXT)   # kit: the library + extra roots



def build_index(scan=True, say=print):
    idx = load_index()
    T = idx.setdefault("tracks", {})
    seen = set()
    vs = {}
    try:
        vs = json.load(open(VSCAN, encoding="utf-8"))
    except (OSError, ValueError):
        pass
    files = list(_files())
    say(f"{len(files)} music files under {ROOT}")
    for i, p in enumerate(files):
        rel = _kit.rel(p, ROOT)
        seen.add(rel)
        st = os.stat(p)
        sig = f"{st.st_size}:{int(st.st_mtime)}"
        r = T.get(rel)
        if not r or r.get("sig") != sig:
            cat, sub, genre = _cat(rel)
            try:
                f = features(p)
            except Exception as e:
                f = {"bad": f"{type(e).__name__}: {e}"[:120]}
            r = {"sig": sig, "cat": cat, "sub": sub, "genre": genre, **f}
            r["genre"] = _kit.genre(rel, r, ROOT)   # kit: folders that mean nothing -> what setup decided / the audio
            T[rel] = r
            say(f"[{i + 1}/{len(files)}] features {rel[:90]}  bpm {r.get('bpm')}  {r.get('dur')} s")
            if i % 20 == 0:
                save_index(idx)
    for gone in [k for k in T if k not in seen]:
        del T[gone]
    _energy(T)
    for rel, r in T.items():
        if "bad" not in r:
            r["moods"] = _kit.pin(rel, mood_scores(rel, r))   # kit: a mood picked by hand stays
    save_index(idx)
    if scan:
        todo = [rel for rel, r in T.items() if "bad" not in r and (r.get("vocal") or {}).get("scanned") != "medium.en novad hp200 v3"]
        # cheapest-to-use first: the beds the pickers want most (type beats, then the rest)
        todo.sort(key=lambda k: (T[k]["genre"] not in ("type beat", "lofi"), T[k]["genre"] == "other", k))
        say(f"vocal scan: {len(todo)} tracks to scan")
        for j, rel in enumerate(todo):
            p = os.path.join(ROOT, rel)
            try:
                v = vocal_scan(p, T[rel]["dur"], say=say)
            except Exception as e:
                say(f"  scan failed {rel}: {type(e).__name__}: {e}")
                continue
            T[rel]["vocal"] = v
            vs[f"{p}|{os.path.getsize(p)}"] = {"verdict": "clean" if v["verdict"] == "clean" else ("tag" if v["verdict"] == "tag" else "vocal"),
                                              "words": v["words"], "hits": v["hits"][:4]}
            say(f"[{j + 1}/{len(todo)}] {v['verdict']:6s} {v['words']:3d} w  {rel[:90]}")
            if j % 5 == 4 or j == len(todo) - 1:
                save_index(idx)
                json.dump(vs, open(VSCAN, "w", encoding="utf-8"), indent=0)
    idx["updated"] = time.strftime("%Y-%m-%d %H:%M")
    save_index(idx)
    return idx


# ------------------------------------------------------------------------------------------------- picking
# profile per video kind: allowed genres, mood weights, energy window, and rules
PROFILES = {
    "review": {"genres": {"type beat": 1.0, "instrumental": 0.5, "electronic": 0.3}, "moods": {"hype": 1, "smooth": 1, "oldschool": 0.6, "dark": 0.4},
               "energy": (0.35, 0.95)},
    "haul": {"genres": {"type beat": 1.0, "instrumental": 0.5, "electronic": 0.4}, "moods": {"hype": 1, "upbeat": 1, "smooth": 0.7},
             "energy": (0.4, 1.0)},
    "short": {"genres": {"type beat": 1.0, "electronic": 0.6, "game beat": 0.3}, "moods": {"hype": 1.2, "upbeat": 1}, "energy": (0.5, 1.0)},
    # phone/app: clean steady beats, no drop trick / beat switch, nothing dark or aggressive under a code walkthrough.
    # TYPE BEATS ONLY (Uber codes october 2026-10-25: an NCS track "sounds cheap, 2016 ... the type beats were working
    # pretty nicely for these Uber videos")
    "phone": {"genres": {"type beat": 1.0}, "moods": {"smooth": 1.2, "upbeat": 1, "oldschool": 0.5, "chill": 0.3},
              "energy": (0.3, 0.9), "steady": True, "avoid": {"dark": 1.5, "hype": 1.0}},
    "screen": {"genres": {"type beat": 1.0, "instrumental": 0.6, "electronic": 0.5}, "moods": {"smooth": 1.2, "upbeat": 1, "oldschool": 0.5},
               "energy": (0.3, 0.9), "steady": True, "avoid": {"dark": 1.5, "hype": 1.0}},
    # chill = calm but NOT all lo-fi (Chime 2026-10-23 "too much lo-fi"): lo-fi is one genre among several
    "screen_chill": {"genres": {"lofi": 0.6, "type beat": 0.8, "anime": 0.7, "cinematic": 0.7, "instrumental": 0.6},
                     "moods": {"chill": 1, "calm": 1, "smooth": 0.8, "oldschool": 0.5}, "energy": (0.0, 0.55), "steady": True,
                     "avoid": {"dark": 1.0, "hype": 1.0}, "max_per_genre": 1},
    # gaming: other games' OSTs, never Minecraft's own soundtrack, never type beats (gaming/assemble.py rules)
    "gaming": {"genres": {"game ost": 1.0, "game beat": 0.6, "anime": 0.5, "cinematic": 0.4}, "moods": {"playful": 1, "epic": 0.8, "calm": 0.6},
               "energy": (0.0, 0.8), "no_minecraft": True},
    "gaming_pokemon": {"genres": {"pokemon": 1.0}, "moods": {"playful": 1}, "energy": (0.0, 1.0)},
}
CHANNEL_OF = {"gaming": "{{GAMING_CHANNEL}}", "phone": "{{PHONE_CHANNEL}}", "screen": "{{PHONE_CHANNEL}}", "review": "{{REVIEW_CHANNEL}}",
              "haul": "{{REVIEW_CHANNEL}}", "short": "Shorts"}
# channels that never get NCS / NoCopyrightSounds releases (user 2026-10-25, Uber codes october: "let's never use NCS
# music ... I don't wanna ever use it for this channel ... it's not gonna be good for a brand")
NO_NCS = {"{{PHONE_CHANNEL}}"}
NCS_RX = re.compile(r"\bNCS\b|no ?copyright ?sounds?|Electronic & NCS", re.I)


def banned(track, channel):
    """a track this channel never uses (also stops a re-render from keeping one it picked before the rule)"""
    # {{REVIEW_CHANNEL}} channels too: type beats only (EDIT_RULES F1; remote test prada 2 2026-10-26 got "Electro-Light - Symbolism
    # [NCS Release]" as its showcase beat)
    return (channel in NO_NCS or "{{REVIEW_CHANNEL}}" in str(channel).lower()) and bool(NCS_RX.search(str(track)))

# topic words in the title / transcript -> mood nudges (product review = the brand's vibe)
TOPIC = [
    (r"cartier|rolex|louis vuitton|\blv\b|prada|gucci|chanel|dior|moncler|canada goose|herm[eè]s|ysl|saint laurent|balenciaga|"
     r"versace|burberry|fendi|bottega|loewe|luxury|designer|expensive|omega|patek|audemars", {"smooth": 1.2, "oldschool": 0.6, "emotional": 0.3, "hype": -0.3}),
    (r"jordan|yeezy|nike|sp5der|spider|amiri|rick owens|supreme|off-?white|bape|essentials|trapstar|corteiz|asics|dunk|"
     r"travis|hoodie|sneaker|streetwear|drip|hype", {"hype": 1.0, "dark": 0.5}),
    (r"\bs2\d|iphone|samsung|galaxy|airpods|ps5|xbox|nintendo switch|laptop|macbook|\btech\b|gadget",
     {"upbeat": 1.0, "smooth": 0.6, "dark": -0.5}),
    (r"alo\b|lululemon|gym|yoga|athleisure|sunglasses|cups|stanley", {"upbeat": 1.0, "chill": 0.4}),
    (r"resell|reselling|profit|spreadsheet|flip|money|business|side hustle|bulk|supplier|wholesale", {"oldschool": 0.8, "hype": 0.6}),
    (r"uber ?eats|doordash|grubhub|food|restaurant|delivery", {"upbeat": 1.0, "smooth": 0.5}),
    (r"chime|cash ?app|bank|credit|bonus|sign ?up|finance|paypal", {"smooth": 1.0, "chill": 0.5, "hype": -0.5}),
    (r"shein|temu|coupon|promo|discount|code|haul|dhgate|mulebuy", {"upbeat": 0.8}),
    (r"story time|scam|caught|police|\btsa\b|customs|seized", {"dark": 0.6, "epic": 0.4}),
]
POKE = re.compile(r"pok[eé]mon|pixelmon|cobblemon|cobbledrock|pocketmobs|rennmon|pokerein", re.I)


def video_mood(kind, title="", text="", style=None):
    """the mood a video gets: its type's profile, nudged by topic words in the title (x3) and the transcript"""
    key = "screen_chill" if kind == "screen" and style == "chill" else kind
    if kind == "gaming" and POKE.search(title or ""):
        key = "gaming_pokemon"
    prof = PROFILES.get(key) or PROFILES["review"]
    want = dict(prof["moods"])
    hay_t, hay_x = (title or "").lower(), (text or "").lower()[:20000]
    why = []
    if not key.startswith("gaming"):
        for rx, nudge in TOPIC:
            nx = len(re.findall(rx, hay_x))   # the transcript counts only when the topic keeps coming up (3+ times)
            n = 3 * len(re.findall(rx, hay_t)) + (min(3, nx - 2) if nx >= 3 else 0)
            if n:
                why.append(re.search(rx, hay_t + " " + hay_x).group(0))
                for m, v in nudge.items():
                    want[m] = want.get(m, 0) + v * min(1.5, n / 3)
    for m, v in (prof.get("avoid") or {}).items():
        want[m] = want.get(m, 0) - v
    return key, prof, {m: round(v, 2) for m, v in want.items()}, why


def _overrides():
    try:
        o = json.load(open(OVERRIDES, encoding="utf-8"))
    except (OSError, ValueError):
        o = {}
    # retired = got a YouTube copyright claim (Studio Uploads, 2026-10-26): never picked again, like block
    block = [b.lower() for b in o.get("block", [])] + [os.path.basename(r.get("track", "")).lower() for r in o.get("retired", [])]
    # removed = he right-clicked it out of the Studio music picker (2026-10-29): never picked again, file stays on disk
    block += [os.path.basename(r.get("track", "")).lower() for r in o.get("removed", [])]
    return [b for b in block if b], [a.lower() for a in o.get("allow", [])]


def retired(track):
    """a track retired after a copyright claim (matched by file name, so copies in work/music count too)"""
    n = os.path.basename(str(track)).lower()
    try:
        o = json.load(open(OVERRIDES, encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return any(os.path.basename(r.get("track", "")).lower() == n for r in o.get("retired", []))


def retire(track, claim="", video="", project=""):
    """take a track out of the library for good (user 2026-10-26: a copyright claim "will basically mark that music as
    like retired from the library and will never use it again"). The file stays on disk; the picker skips it and a
    re-render drops it from the video that had it."""
    try:
        o = json.load(open(OVERRIDES, encoding="utf-8"))
    except (OSError, ValueError):
        o = {}
    lst = o.setdefault("retired", [])
    if not any(os.path.basename(r.get("track", "")).lower() == os.path.basename(str(track)).lower() for r in lst):
        lst.append({"track": str(track), "claim": claim, "video": video, "project": str(project), "date": time.strftime("%Y-%m-%d %H:%M")})
        json.dump(o, open(OVERRIDES, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return lst


def removed():
    """file names he took out of the library from Studio (lower case)"""
    try:
        o = json.load(open(OVERRIDES, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [os.path.basename(r.get("track", "")).lower() for r in o.get("removed", [])]


def remove(track, undo=False):
    """take a song out of the library (user 2026-10-29: "remove a song from the library simply by right-clicking on it").
    Like retire() without the copyright claim: the picker and the Studio list skip it, the file stays on disk, undo = put back."""
    try:
        o = json.load(open(OVERRIDES, encoding="utf-8"))
    except (OSError, ValueError):
        o = {}
    n = os.path.basename(str(track)).lower()
    lst = [r for r in o.get("removed", []) if os.path.basename(r.get("track", "")).lower() != n]
    if not undo:
        lst.append({"track": str(track), "date": time.strftime("%Y-%m-%d %H:%M")})
    o["removed"] = lst
    json.dump(o, open(OVERRIDES, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return removed()


def is_clean(r, rel=""):
    block, allow = _overrides()
    n = rel.lower()
    if any(b in n for b in block):
        return False
    if any(a in n for a in allow):
        return True
    v = r.get("vocal") or {}
    return v.get("verdict") == "clean" and v.get("words", 99) <= 4 and not any(len(h.split()) - 1 >= 4 for h in v.get("hits", []))


def load_log():
    try:
        return json.load(open(LOG, encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _norm(p):
    return os.path.normcase(os.path.normpath(str(p)))


def recent_tracks(channel, project=None, n_channel=RECENT_CHANNEL, n_global=RECENT_GLOBAL):
    """tracks used by the last 15 videos of this channel + the last 5 videos of any channel (this project excluded),
    plus the older pickers' histories (product-review music_history.json, build_intro music.json) so the switch-over
    doesn't replay what just went out"""
    log = [h for h in load_log() if _norm(h.get("project", "")) != _norm(project or "")]
    mine = [h for h in log if h.get("channel") == channel][-n_channel:]
    used = {_norm(t) for h in mine + log[-n_global:] for t in h.get("tracks", [])}
    names = set()
    try:
        old = json.load(open(os.path.expanduser(r"~/.claude/skills/product-review-edit/work/music_history.json"), encoding="utf-8"))
        names |= {b.lower() for h in old[-8:] if _norm(h.get("project", "")) != _norm(project or "") for b in h.get("beats", [])}
    except (OSError, ValueError):
        pass
    return used, names


def project_tracks(project):
    """what this project already got (a re-render keeps its music)"""
    for h in reversed(load_log()):
        if _norm(h.get("project", "")) == _norm(project or ""):
            return h
    return None


def _candidates(kind, title="", text="", style=None, min_len=40, avoid=(), channel=None, project=None, idx=None, relax=False):
    idx = idx or load_index()
    key, prof, want, why = video_mood(kind, title, text, style)
    channel = channel or CHANNEL_OF.get(kind, kind)
    used, used_names = recent_tracks(channel, project)
    bad = {_norm(a) for a in avoid or ()}
    lo, hi = prof["energy"]
    out = []
    for rel, r in idx.get("tracks", {}).items():
        if "bad" in r or (r["genre"] not in prof["genres"] and not relax) or not is_clean(r, rel) or banned(rel, channel):
            continue
        p = os.path.join(ROOT, rel)
        if _norm(p) in bad or not os.path.exists(p):
            continue
        if prof.get("no_minecraft") and "minecraft" in rel.lower():
            continue
        if r.get("usable", 0) - r.get("lead_in", 0) < min_len:
            continue
        if prof.get("steady") and (r.get("switch") or re.search(r"switch", rel, re.I) or r.get("spread", 0) > 6.0):
            continue
        m = r.get("moods", {})
        fit = sum(want.get(k, 0) * min(m.get(k, 0), 3) for k in want) / 3
        e = r.get("energy", 0.5)
        fit -= 2.0 * max(0, lo - e, e - hi)
        fit += prof["genres"].get(r["genre"], -0.5)
        recent = _norm(p) in used or os.path.basename(p).lower() in used_names
        out.append({"track": p, "rel": rel, "fit": round(fit, 3), "recent": recent, "genre": r["genre"], "sub": r.get("sub") or r["cat"],
                    "energy": e, "bpm": r.get("bpm"), "usable": r.get("usable"),
                    "top": sorted(((v, k) for k, v in m.items() if v > 0.6), reverse=True)[:3]})
    return key, want, why, out


def candidates(kind, title="", text="", style=None, min_len=40, avoid=(), channel=None, project=None, idx=None):
    """kit: a small or unsorted library still gets music: under 3 fitting tracks, the other genres join (ranked lower)"""
    res = _candidates(kind, title, text, style, min_len, avoid, channel, project, idx)
    if len(res[3]) < 3:
        res = _candidates(kind, title, text, style, min_len, avoid, channel, project, idx, relax=True)
    return res


def pick(kind, n=1, title="", text="", style=None, min_len=40, avoid=(), channel=None, project=None, seed=None, keep=True,
         log=True, exclude=(), role="main"):
    """n different tracks for one video, best fit first, never one from the channel's last 15 videos while fitting
    tracks remain, different artist folders / genres within the video, a re-render keeps its tracks"""
    channel = channel or CHANNEL_OF.get(kind, kind)
    bad = {_norm(a) for a in avoid or ()} | {_norm(e) for e in exclude or ()}
    have = []
    if keep and project:   # a re-render keeps this role's tracks (intro beat / section beats) unless one was turned down
        h = project_tracks(project)
        roles = (h or {}).get("roles") or {}
        have = [t for t in roles.get(role, []) if os.path.exists(t) and _norm(t) not in bad and not banned(t, channel)
                and not retired(t)]
        # the video's other parts keep their own tracks (the intro beat is not a section beat too)
        bad |= {_norm(t) for r, ts in roles.items() if r != role for t in ts}
        if len(have) >= n:
            return have[:n]
        if have and n > len(have):
            exclude = list(exclude or ()) + have
            bad |= {_norm(t) for t in have}
    key, want, why, c = candidates(kind, title, text, style, min_len, avoid, channel, project)
    c = [x for x in c if _norm(x["track"]) not in bad]
    if not c:
        return []
    rng = random.Random(seed if seed is not None else int(hashlib.md5(f"{project}|{title}".encode()).hexdigest()[:8], 16))
    for x in c:   # a little jitter so equally fitting tracks rotate instead of always the same top few
        x["score"] = x["fit"] + rng.uniform(0, 0.6) - (3.0 if x["recent"] else 0)
    c.sort(key=lambda x: -x["score"])
    prof = PROFILES.get(key, {})
    chosen, subs, genres, tops = [], {}, {}, {}
    cap = max(1, -(-n // 2))   # no single mood takes more than half a video's tracks (variety between sections)
    thr = c[0]["score"] - 1.5   # ...but variety never reaches for a track that doesn't fit (those only fill a small pool)
    for x in c:
        if len(chosen) >= n or x["score"] < thr:
            break
        if subs.get(x["sub"], 0) >= (1 if x["sub"] != "Other Artists" else 2) and len(c) > n * 3:
            continue
        tm = x["top"][0][1] if x["top"] else ""
        if n > 1 and tm and tops.get(tm, 0) >= cap and len(c) > n * 3:
            continue
        tops[tm] = tops.get(tm, 0) + 1
        if prof.get("max_per_genre") and genres.get(x["genre"], 0) >= prof["max_per_genre"] and len(chosen) < n - 1:
            continue
        chosen.append(x)
        subs[x["sub"]] = subs.get(x["sub"], 0) + 1
        genres[x["genre"]] = genres.get(x["genre"], 0) + 1
    for x in c:   # small pools: fill without the variety limits
        if len(chosen) >= n:
            break
        if x not in chosen:
            chosen.append(x)
    tracks = [x["track"] for x in chosen]
    if keep and project and have:
        tracks = (have + tracks)[:n]
    if log and project:
        log_use(project, kind, tracks, channel, title, role=role)
    return tracks


def log_use(project, kind, tracks, channel=None, title="", role="main"):
    """record what a video used, per role (intro / main / outro...): one entry per project, newest last"""
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    log = load_log()
    prev = next((h for h in log if _norm(h.get("project", "")) == _norm(project)), None) or {}
    log = [h for h in log if _norm(h.get("project", "")) != _norm(project)]
    roles = dict(prev.get("roles") or {})
    roles[role] = list(tracks)
    allt = []
    for r in roles.values():
        allt += [t for t in r if _norm(t) not in {_norm(x) for x in allt}]
    log.append({"project": str(project), "kind": kind, "channel": channel or prev.get("channel") or CHANNEL_OF.get(kind, kind),
                "title": title or prev.get("title", ""), "date": time.strftime("%Y-%m-%d %H:%M"), "roles": roles, "tracks": allt})
    json.dump(log[-400:], open(LOG, "w", encoding="utf-8"), indent=1, ensure_ascii=False)


def info(path, idx=None):
    """the index record of a track (dur, usable, lead_in, bpm, energy, moods, vocal) or {}"""
    idx = idx or load_index()
    try:
        return idx.get("tracks", {}).get(_kit.rel(path, ROOT), {})
    except ValueError:
        return {}


def project_context(path):
    """(project dir, kind, channel, title, transcript text) from any folder inside a project (studio.json + a words file)"""
    d = os.path.abspath(path)
    proj = None
    for _ in range(5):
        if os.path.exists(os.path.join(d, "studio.json")):
            proj = d
            break
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    proj = proj or os.path.abspath(path)
    doc = {}
    try:
        doc = json.load(open(os.path.join(proj, "studio.json"), encoding="utf-8-sig"))
    except (OSError, ValueError):
        pass
    text = ""
    for rel in ("edit/out_words.json", "work/words.json", "edit/words.json", "Edit/studio/words.json", "work/transcript.json",
                "edit/work/words.json"):
        p = os.path.join(proj, rel)
        if os.path.exists(p):
            try:
                w = json.load(open(p, encoding="utf-8"))
                w = w.get("words", w) if isinstance(w, dict) else w
                text = " ".join(str(x.get("w") or x.get("word") or x.get("text") or "") for x in w if isinstance(x, dict))
                if text.strip():
                    break
            except (OSError, ValueError, AttributeError):
                pass
    return proj, doc.get("type"), doc.get("channel") or None, doc.get("title") or os.path.basename(proj), text


def pick_for(path, kind=None, n=1, **kw):
    """pick() with the project's own title / transcript / channel filled in"""
    proj, k, ch, title, text = project_context(path)
    kind = kind or k or "review"
    return pick(kind, n, title=kw.pop("title", None) or title, text=kw.pop("text", None) or text, channel=kw.pop("channel", None) or ch,
                project=proj, **kw)


def _cli():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    a = sys.argv[1:]
    if not a or a[0] == "index":
        build_index(scan="--no-scan" not in a)
    elif a[0] == "show":
        kind = a[1] if len(a) > 1 else "review"
        key, want, why, c = candidates(kind, style="chill" if "chill" in a else None, project="-")
        print(key, want)
        for x in sorted(c, key=lambda x: -x["fit"]):
            print(f"{x['fit']:5.2f} e{x['energy']:.2f} {x['bpm'] or 0:5.0f}bpm {'R ' if x['recent'] else '  '}{x['rel'][:95]}")
        print(len(c), "usable tracks")
    elif a[0] == "dry":
        proj, k, ch, title, text = project_context(a[1])
        kind = a[2] if len(a) > 2 else (k or "review")
        n = int(a[3]) if len(a) > 3 else 4
        key, want, why, _ = candidates(kind, title, text, project=proj)
        tr = pick(kind, n, title=title, text=text, channel=ch, project=proj, log=False, keep=False)
        print(json.dumps({"project": proj, "kind": kind, "channel": ch or CHANNEL_OF.get(kind), "mood": key, "want": want, "topic": why,
                          "tracks": tr}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    _cli()

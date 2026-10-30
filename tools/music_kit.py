"""Music setup for a new kit user: find the music already on this PC, sort it into a mood library, and tell music_lib where
the library lives (most YouTubers' music is loose files in Downloads / Desktop / OneDrive, in folders that mean nothing).

    python music_kit.py find [--place DIR ...] [--json]     look in the usual places (Music, Downloads, Desktop, Videos, OneDrive,
                                                            other drives' top-level music folders) -> <library>/_setup/found.json
    python music_kit.py organise (--all | --sel FILE) [--skip FOLDER ...] [--copy]
                                                            analyse + vocal-scan, then link/copy the clean tracks into
                                                            <library>/<mood>/ and write <library>/_setup/report.md (+ .json)
    python music_kit.py status                              library, tracks per mood, whether setup is still needed

Your own files are never moved, renamed or deleted: the library gets a hard link (same drive, no extra space) or a copy.
Instrumentals only: every track gets music_lib's vocal / producer-tag scan (medium.en Whisper, waits while the Studio renders);
anything with vocals, lyrics, a producer tag or a spoken line is left out and listed in the report with the words it heard.

Settings (Studio -> Settings -> Music, or Studio/data/settings.json):
  music_root         the mood library (music_lib indexes and picks from it)
  music_extra_roots  more folders music_lib indexes as they are (nothing copied); the genre then comes from the audio
This file only uses the standard library at import time: music_lib imports it for the settings.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
SETTINGS = KIT / "Studio" / "data" / "settings.json"
STUDIO_SCAN = KIT / "Studio" / "data" / "music-scan.json"   # the Studio music picker's ★ marks
EXT = (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus")    # what music_lib indexes
MIN_SECONDS = 60
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
# the library's mood folders, and the mood priors music_lib gives a track for sitting in one
MOODS = ("chill", "upbeat", "hype", "dark", "cinematic", "lo-fi")
# The folder IS the track's mood (user 2026-10-29: "the category of music changes, it's not correct"): music_lib's energy is
# a percentile across the whole library, so adding music used to shift every track's mood scores (energy adds up to ~1.4,
# a name keyword 1.5). A folder prior of 4 always wins, so a track only changes mood when it's moved (right-click -> Mood).
MOOD_FOLDERS = {"chill": {"chill": 4, "smooth": 1, "calm": 0.8}, "lo-fi": {"chill": 4, "calm": 1.5},
                "upbeat": {"upbeat": 4, "playful": 0.8}, "hype": {"hype": 4}, "dark": {"dark": 4},
                "cinematic": {"epic": 4, "calm": 1, "emotional": 1}}
# the editor's mood chips for each library mood (a pinned track outside the mood folders gets this one on top)
CHIP = {"chill": "chill", "lo-fi": "chill", "upbeat": "upbeat", "hype": "hype", "dark": "dark", "cinematic": "epic"}
# genre from the file / folder name when it says something (checked in this order)
NAME_GENRE = [
    ("lofi", r"lo[- ]?fi|chillhop|study beats?"),
    ("game ost", r"\bost\b|soundtrack|pok[eé]mon|zelda|mario|nintendo|game music|\bvgm\b|undertale|kirby|sonic|final fantasy"),
    ("anime", r"anime|piano cover|ghibli"),
    ("electronic", r"\bncs\b|\bedm\b|house|techno|electro|dubstep|synthwave|future bass|trance"),
    ("cinematic", r"cinematic|orchestra|epic music|ambient|film score|trailer"),
    ("instrumental", r"\binstrumental\b|\binst\b|karaoke"),
    ("type beat", r"type beat|\bbeats?\b|\btrap\b|\bdrill\b|boom ?bap|hip ?hop|\bprod\b"),
]


# ------------------------------------------------------------------------------------------------ settings
def settings():
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(patch):
    s = settings()
    s.update(patch)
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding="utf-8")
    return s


def _n(p):
    return os.path.normcase(os.path.normpath(str(p)))


def roots(default):
    """(library, [extra roots]) for music_lib: Settings win over the folder setup filled in"""
    s = settings()
    lib = s.get("music_root") or default
    extra = [p for p in s.get("music_extra_roots") or [] if p and os.path.isdir(p) and _n(p) != _n(lib)]
    return os.path.normpath(lib), extra


def library():
    return Path(roots(str(KIT / "Music"))[0])


def port():
    try:
        return int(settings().get("port") or 8765)
    except (TypeError, ValueError):
        return 8765


def setup_dir():
    d = library() / "_setup"
    d.mkdir(parents=True, exist_ok=True)
    return d


def rel(p, root):
    """music_lib's index key: relative inside the library, the full path for a track in an extra root"""
    try:
        r = os.path.relpath(os.path.abspath(p), root)
    except ValueError:   # another drive
        return os.path.abspath(p)
    return os.path.abspath(p) if r.startswith("..") else r


def files(root, extra, skip_dirs, ext):
    """every track music_lib indexes: the library (its own rules) plus the extra roots"""
    for top in [root] + list(extra):
        for dp, dn, fn in os.walk(top):
            parts = os.path.relpath(dp, top).lower().split(os.sep)
            if any(p in skip_dirs for p in parts) or os.path.basename(dp).startswith("_"):
                dn[:] = []
                continue
            for f in fn:
                if f.lower().endswith(ext) and not f.startswith("_"):
                    yield os.path.join(dp, f)


# ------------------------------------------------------------------------------------------------ genre from the audio
_REF = []


def audio_genre(f):
    """type beat / lofi / electronic / cinematic from the analysis alone: 7 nearest neighbours among an already-sorted
    instrumental library's features (music_genre_ref.json; votes weighted 1/sqrt(class size) so the small electronic class
    isn't drowned out: 81% right in a leave-one-out test), lo-fi = a muffled, quiet, steady, slow beat"""
    if "flux" not in f:
        return "other"
    import numpy as np
    if not _REF:
        ref = json.loads((HERE / "music_genre_ref.json").read_text(encoding="utf-8"))["points"]
        X = np.array([_vec(dict(low=r[0], flux=r[1], loud_db=r[2], bright=r[3], spread=r[4])) for r in ref])
        mu, sd = X.mean(0), X.std(0) + 1e-9
        size = {}
        for r in ref:
            size[r[5]] = size.get(r[5], 0) + 1
        _REF.extend([(X - mu) / sd, [r[5] for r in ref], mu, sd, size])
    Z, Y, mu, sd, size = _REF
    z = (np.array(_vec(f)) - mu) / sd
    near = np.argsort(((Z - z) ** 2).sum(1))[:7]
    votes = {}
    for i in near:
        votes[Y[i]] = votes.get(Y[i], 0) + size[Y[i]] ** -0.5
    g = max(votes, key=votes.get)
    if g == "type beat" and f.get("bright", 9999) < 650 and f.get("loud_db", 0) < -11 and f.get("spread", 9) < 4 \
            and 0 < f.get("bpm", 0) < 100:
        g = "lofi"
    return g


def _vec(f):
    import math
    return [f.get("low", 0), math.log(f.get("flux", 0) + 1e-3), f.get("loud_db", -20), math.log(f.get("bright", 1000) + 1),
            f.get("spread", 3)]


def name_genre(text):
    t = text.lower()
    for g, rx in NAME_GENRE:
        if re.search(rx, t):
            return g
    return None


def _meta():
    try:
        return json.loads((library() / "_setup" / "library.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def genre(rel_key, r, root):
    """music_lib's genre for a track whose folder means nothing: what setup decided, else the name, else the audio"""
    if r.get("genre") not in (None, "other"):
        return r["genre"]
    m = _meta().get(rel_key.replace("\\", "/"))
    if m and m.get("genre"):
        return m["genre"]
    src = (m or {}).get("source") or rel_key
    return name_genre(os.path.splitext("/".join(Path(src).parts[-3:]))[0]) or audio_genre(r)


# ------------------------------------------------------------------------------------------------ find
SKIP_PARTS = {"windows", "program files", "program files (x86)", "programdata", "appdata", "$recycle.bin", "recycler",
              "system volume information", "recovery", "perflogs", "msocache", "$windows.~bt", "$windows.~ws", "windowsapps",
              "node_modules", ".git", "site-packages", "__pycache__", "steamapps", "steam", "steamlibrary", "epic games",
              "riot games", "xboxgames", "origin games", "battle.net", "ea games", "gog galaxy", "ubisoft", "rockstar games",
              "sound effects", "sfx", "ringtones", "notifications", "alarms", "cache", "temp", "tmp", "_rejected",
              # meeting / voice recordings and editors' own stock libraries: not your music
              "zoom", "microsoft teams", "audacity", "reaper media", "sound recordings", "voice recorder", "voice memos",
              "recordings", "media content", "capcut", "wondershare filmora", "movavi video editor"}
NAME_SKIP = re.compile(r"notification|ringtone|alarm|\bsfx\b|sound ?effects?|whoosh|swoosh|\bding\b", re.I)
MUSICY = re.compile(r"music|beats?\b|audio|songs?|tracks|instrumentals?|lo-?fi|\bncs\b|\bbgm\b|soundtracks?|\bost\b|playlists?|"
                    r"\bmp3s?\b", re.I)
CLOUD_ONLY = 0x00400000 | 0x00040000 | 0x00001000   # OneDrive / Drive "online-only": reading it would download it


def places():
    """(folder, why) for the usual places music piles up"""
    if os.environ.get("MUSIC_KIT_PLACES"):   # tests: look only here
        return [(Path(x), "test") for x in os.environ["MUSIC_KIT_PLACES"].split(os.pathsep) if Path(x).is_dir()]
    home = Path.home()
    out = [(home / n, n) for n in ("Music", "Downloads", "Desktop", "Videos")]
    out += [(p, "OneDrive") for p in sorted(home.glob("OneDrive*")) if p.is_dir()]
    if sys.platform == "win32":
        import ctypes
        import string
        for d in string.ascii_uppercase[2:]:
            r = f"{d}:\\"
            if ctypes.windll.kernel32.GetDriveTypeW(r) not in (2, 3):   # removable / fixed only: no network or DVD drives
                continue
            try:
                for e in os.scandir(r):
                    if e.is_dir() and MUSICY.search(e.name) and e.name.lower() not in SKIP_PARTS:
                        out.append((Path(e.path), f"{d}: drive"))
            except OSError:
                pass
    seen, keep = set(), []
    for p, why in out:   # an inside folder of one already listed goes once
        if p.is_dir() and _n(p) not in seen and not any(_n(p).startswith(s + os.sep) for s in seen):
            keep = [(q, w) for q, w in keep if not _n(q).startswith(_n(p) + os.sep)]
            keep.append((p, why))
            seen.add(_n(p))
    return keep


def _never_scan():
    """the kit, the library itself, project folders and the voiceover folder: not 'your music'"""
    s = settings()
    out = {_n(KIT), _n(library())}
    for v in list((s.get("roots") or {}).values()) + [s.get("vo_folder")]:
        if v:
            out.add(_n(v))
    return out


def duration(p):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                           capture_output=True, text=True, timeout=30, creationflags=NO_WINDOW)
        return float(r.stdout.strip() or 0)
    except (ValueError, subprocess.SubprocessError, OSError):
        return 0.0


def find(extra_places=(), say=print, progress=None):
    never = _never_scan()
    todo = [(Path(p), "added") for p in extra_places] + places()
    cand, skipped = [], {"short": 0, "system_or_sfx": 0, "online_only": 0, "duplicate": 0, "in_library": 0}
    have = {(os.path.basename(m.get("source", "")).lower(), m.get("size")) for m in _meta().values()}
    for top, why in todo:
        say(f"looking in {top} ({why})")
        if progress:
            progress({"state": "finding", "msg": f"Looking in {top}", "found": len(cand)})
        for dp, dn, fn in os.walk(top):
            below = Path(dp).parts[len(top.parts):]   # only folders under the place count (the place itself may sit anywhere)
            if _n(dp) in never or any(x.lower() in SKIP_PARTS for x in below) or len(below) > 8:
                dn[:] = []
                continue
            for f in fn:
                if not f.lower().endswith(EXT):
                    continue
                p = os.path.join(dp, f)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if getattr(st, "st_file_attributes", 0) & CLOUD_ONLY:
                    skipped["online_only"] += 1
                    continue
                if NAME_SKIP.search(f):
                    skipped["system_or_sfx"] += 1
                    continue
                if st.st_size < 200_000:   # under ~60 s at any normal bitrate
                    skipped["short"] += 1
                    continue
                cand.append({"path": p, "size": st.st_size, "folder": dp, "place": why})
    say(f"{len(cand)} audio files, checking their length")
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(8) as ex:
        durs = list(ex.map(lambda c: duration(c["path"]), cand))
    found, dup = [], set()
    for c, d in zip(cand, durs):
        if d < MIN_SECONDS:
            skipped["short"] += 1
            continue
        key = (os.path.basename(c["path"]).lower(), c["size"])
        if key in have:
            skipped["in_library"] += 1
            continue
        if key in dup:
            skipped["duplicate"] += 1
            continue
        dup.add(key)
        found.append({**c, "dur": round(d, 1)})
    res = {"when": time.strftime("%Y-%m-%d %H:%M"), "library": str(library()), "places": [str(p) for p, _ in todo],
           "files": found, "skipped": skipped, "minutes": round(sum(f["dur"] for f in found) / 60)}
    _wj(setup_dir() / "found.json", res)
    return res


def by_folder(found):
    g = {}
    for f in found.get("files", []):
        x = g.setdefault(f["folder"], {"folder": f["folder"], "place": f["place"], "count": 0, "minutes": 0, "files": []})
        x["count"] += 1
        x["minutes"] += f["dur"] / 60
        x["files"].append({"path": f["path"], "name": os.path.basename(f["path"]), "dur": f["dur"]})
    out = sorted(g.values(), key=lambda x: -x["count"])
    for x in out:
        x["minutes"] = round(x["minutes"], 1)
    return out


# ------------------------------------------------------------------------------------------------ organise
def _wj(p, obj):
    tmp = str(p) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)
    os.replace(tmp, p)


def _rj(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def progress(**kw):
    p = setup_dir() / "progress.json"
    cur = _rj(p, {})
    cur.update(kw, beat=time.time(), pid=os.getpid())
    _wj(p, cur)


def mood_of(scores, genre_, energy=0.5):
    """the library folder for a track, from music_lib's mood scores"""
    if genre_ == "lofi":
        return "lo-fi"
    s = scores
    b = {"chill": s.get("chill", 0) + s.get("smooth", 0) + 0.7 * s.get("calm", 0) + 0.5 * s.get("oldschool", 0),
         "upbeat": s.get("upbeat", 0) + s.get("playful", 0) + (0.8 if genre_ == "electronic" else 0),
         "hype": s.get("hype", 0) * 1.1,
         "dark": s.get("dark", 0) * 1.2,
         "cinematic": s.get("epic", 0) + s.get("emotional", 0) + 0.4 * s.get("calm", 0)
                      + (1.5 * (1 - energy) if genre_ in ("cinematic", "game ost", "anime") else 0)}
    return max(b, key=b.get)


def reason(v):
    hits = "; ".join(v.get("hits", [])[:2])
    if v.get("verdict") == "vocal":
        return f"vocals / lyrics ({v.get('words')} words heard)"
    if v.get("verdict") == "tag":
        return f"producer tag or spoken line: {hits}" if hits else "producer tag"
    return f"spoken words ({v.get('words')}): {hits}"


def _unique(dst):
    if not dst.exists():
        return dst
    for i in range(2, 999):
        d = dst.with_name(f"{dst.stem} ({i}){dst.suffix}")
        if not d.exists():
            return d
    return dst


def organise(paths, mode="link", say=print):
    sys.path.insert(0, str(HERE))
    import music_lib as ml
    lib = library()
    for m in MOODS:
        (lib / m).mkdir(parents=True, exist_ok=True)
    cache_p = setup_dir() / "cache.json"
    cache = _rj(cache_p, {})
    added, rejected, already, failed = [], [], [], []
    clean = []
    t0 = time.time()
    for i, p in enumerate(paths):
        name = os.path.basename(p)
        progress(state="organising", done=i, total=len(paths), current=name, msg=f"Analysing {name}")
        try:
            st = os.stat(p)
        except OSError:
            failed.append({"name": name, "source": p, "reason": "file not found any more"})
            continue
        key = f"{_n(p)}|{st.st_size}|{int(st.st_mtime)}"
        c = cache.get(key) or {}
        if "f" not in c:
            try:
                c["f"] = ml.features(p)
            except Exception as e:
                c["f"] = {"bad": f"{type(e).__name__}: {e}"[:120]}
        f = c["f"]
        if "bad" in f or f.get("dur", 0) < MIN_SECONDS:
            rejected.append({"name": name, "source": p, "reason": "couldn't read it" if "bad" in f else "shorter than 60 s"})
            cache[key] = c
            continue
        if (c.get("vocal") or {}).get("scanned") != "medium.en novad hp200 v3":
            say(f"[{i + 1}/{len(paths)}] vocal check {name}")
            progress(msg=f"Checking {name} for vocals / producer tags")
            try:
                c["vocal"] = ml.vocal_scan(p, f["dur"], say=lambda m: (say(m), progress(msg=m.strip())))
            except Exception as e:
                failed.append({"name": name, "source": p, "reason": f"vocal check failed: {type(e).__name__}: {e}"[:160]})
                continue
        cache[key] = c
        if i % 5 == 4:
            _wj(cache_p, cache)
        v = c["vocal"]
        if not ml.is_clean({"vocal": v}, name):
            rejected.append({"name": name, "source": p, "reason": reason(v), "words": v.get("words"), "hits": v.get("hits", [])[:4]})
            continue
        clean.append((p, st, f, v))
    _wj(cache_p, cache)

    # energy is a percentile across the whole library, so the existing tracks take part
    idx = ml.load_index()
    T = idx.setdefault("tracks", {})
    recs = {k: dict(r) for k, r in T.items() if "flux" in r}
    for p, st, f, v in clean:
        recs["new|" + p] = dict(f)
    ml._energy(recs)
    meta_p = setup_dir() / "library.json"
    meta = _rj(meta_p, {})
    have = {(os.path.basename(m.get("source", "")).lower(), m.get("size")): k for k, m in meta.items()}
    scans = _rj(STUDIO_SCAN, {})
    for p, st, f, v in clean:
        name = os.path.basename(p)
        if (name.lower(), st.st_size) in have:
            already.append({"name": name, "source": p, "dest": str(lib / have[(name.lower(), st.st_size)])})
            continue
        f = {**f, "energy": recs["new|" + p].get("energy", 0.5)}
        near = "/".join(Path(p).parts[-3:])   # its folder names say something sometimes ("lofi beats/...")
        g = name_genre(os.path.splitext(near)[0]) or audio_genre(f)
        scores = ml.mood_scores(near, f)
        mood = mood_of(scores, g, f["energy"])
        dst = _unique(lib / mood / name)
        how = "copy"
        if mode == "link":
            try:
                os.link(p, dst)
                how = "hard link"
            except OSError:
                shutil.copy2(p, dst)
        else:
            shutil.copy2(p, dst)
        k = os.path.relpath(dst, lib)
        meta[k.replace("\\", "/")] = {"source": p, "size": st.st_size, "genre": g, "mood": mood, "method": how,
                                      "added": time.strftime("%Y-%m-%d %H:%M"), "words": v.get("words")}
        ds = os.stat(dst)
        T[k] = {"sig": f"{ds.st_size}:{int(ds.st_mtime)}", "cat": mood, "sub": "", "genre": g,
                **{x: y for x, y in f.items() if x != "energy"}, "vocal": v}
        scans[str(dst)] = {"verdict": "clean", "words": v.get("words"), "hits": v.get("hits", [])[:4]}
        added.append({"name": name, "source": p, "dest": str(dst), "mood": mood, "genre": g, "bpm": f.get("bpm"),
                      "energy": f.get("energy"), "method": how, "minutes": round(f["dur"] / 60, 1)})
        say(f"  {mood:9s} {g:11s} {how:9s} {name}")
    _wj(meta_p, meta)
    ml.save_index(idx)
    STUDIO_SCAN.parent.mkdir(parents=True, exist_ok=True)
    _wj(STUDIO_SCAN, scans)
    progress(msg="Updating the music index")
    ml.build_index(scan=True, say=lambda m: (say(m), progress(msg=m.strip())))   # moods + energy for the whole library
    rep = report(added, rejected, already, failed, mode, round((time.time() - t0) / 60, 1))
    progress(state="done", done=len(paths), total=len(paths), current="", msg="Done", report=rep["counts"])
    return rep


def report(added, rejected, already, failed, mode, minutes):
    lib = library()
    counts = {m: sum(1 for f in (lib / m).glob("*") if f.suffix.lower() in EXT) for m in MOODS}
    rep = {"when": time.strftime("%Y-%m-%d %H:%M"), "library": str(lib), "mode": mode, "took_min": minutes, "counts": counts,
           "added": added, "rejected": rejected, "already": already, "failed": failed}
    d = setup_dir()
    _wj(d / "report.json", rep)
    L = [f"# Music setup report ({rep['when']})", "",
         f"Library: `{lib}`. Your original files were not moved or changed: the library holds "
         f"{'hard links (no extra space) or copies' if mode == 'link' else 'copies'}.", "",
         f"**{len(added)} added**, {len(rejected)} left out (vocals / tags), {len(already)} already in the library, "
         f"{len(failed)} failed. Took {minutes} min.", "", "| Mood | Tracks in the library |", "|---|---|"]
    L += [f"| {m} | {n} |" for m, n in counts.items()]
    if added:
        L += ["", "## Added", "", "| Track | Mood | Genre | BPM | Energy | From |", "|---|---|---|---|---|---|"]
        L += [f"| {a['name']} | {a['mood']} | {a['genre']} | {a['bpm'] or 0:.0f} | {a['energy']:.2f} | {a['source']} |" for a in added]
    if rejected:
        L += ["", "## Left out (instrumentals only)", "",
              "A track with vocals, lyrics, a producer tag (\"BeatStars\", \"prod by\") or a spoken line distracts viewers, so the "
              "picker never uses it. If one is wrong (a clean beat), add part of its name to `allow` in "
              f"`{lib / '_music_overrides.json'}` and run setup again.", "", "| Track | Why | From |", "|---|---|---|"]
        L += [f"| {r['name']} | {r['reason']} | {r['source']} |" for r in rejected]
    if failed:
        L += ["", "## Failed", ""] + [f"- {r['name']}: {r['reason']}" for r in failed]
    L += ["", "Move a track to another mood folder by hand any time; `python tools/music_lib.py index` picks it up."]
    (d / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    hist = d / "reports"
    hist.mkdir(exist_ok=True)
    shutil.copy2(d / "report.md", hist / f"report {time.strftime('%Y-%m-%d %H%M')}.md")
    return rep


# ------------------------------------------------------------------------------------------------ remove / change mood
# Right-click a track in any song picker (Studio: music_setup.js): "Remove from library" = never picked again (its name goes
# in _music_overrides.json "block", which music_lib and organise both honour), and the setup's own link / copy is deleted.
# Your original file is never touched. "Mood" = moved to that mood folder (or pinned, for a track outside the library).
def overrides_path():
    return library() / "_music_overrides.json"


def overrides():
    return _rj(overrides_path(), {})


def _save_overrides(o):
    _wj(overrides_path(), o)


def pin(rel_key, moods):
    """music_lib calls this on every track's mood scores: a mood you picked by hand comes out on top"""
    m = (overrides().get("moods") or {}).get(os.path.basename(str(rel_key)).lower())
    if m in CHIP and moods is not None:
        moods = dict(moods)
        moods[CHIP[m]] = round(max(moods.values() or [0]) + 2, 2)
    return moods


def _index_key(path):
    lib = library()
    return rel(path, str(lib))


def remove(path):
    lib = library()
    name = os.path.basename(path)
    o = overrides()
    if name.lower() not in [b.lower() for b in o.get("block", [])]:
        o.setdefault("block", []).append(name)
    meta = _rj(setup_dir() / "library.json", {})
    k = _index_key(path).replace("\\", "/")
    m = meta.pop(k, None)
    deleted = False
    if m and _n(path).startswith(_n(lib) + os.sep) and os.path.exists(path):   # the setup's own link / copy: safe to delete
        try:
            os.remove(path)
            deleted = True
        except OSError:
            pass
    o.setdefault("removed", [])
    o["removed"] = [r for r in o["removed"] if r.get("name", "").lower() != name.lower()] + [
        {"name": name, "path": str(path), "source": (m or {}).get("source", "" if deleted else str(path)),
         "mood": (m or {}).get("mood") or Path(path).parent.name, "deleted": deleted, "date": time.strftime("%Y-%m-%d %H:%M")}]
    _save_overrides(o)
    _wj(setup_dir() / "library.json", meta)
    idx = _rj(lib / "_index.json", {"tracks": {}})
    idx.get("tracks", {}).pop(_index_key(path), None)
    _wj(lib / "_index.json", idx)
    return {"ok": True, "name": name, "deleted": deleted}


def restore(name):
    """put a removed track back (Settings -> Music -> Removed tracks)"""
    o = overrides()
    rec = next((r for r in o.get("removed", []) if r.get("name", "").lower() == name.lower()), None)
    o["block"] = [b for b in o.get("block", []) if b.lower() != name.lower()]
    o["removed"] = [r for r in o.get("removed", []) if r.get("name", "").lower() != name.lower()]
    _save_overrides(o)
    if rec and rec.get("deleted") and rec.get("source") and os.path.exists(rec["source"]):
        mood = rec.get("mood") if rec.get("mood") in MOODS else "chill"
        dst = _unique(library() / mood / name)
        try:
            os.link(rec["source"], dst)
            how = "hard link"
        except OSError:
            shutil.copy2(rec["source"], dst)
            how = "copy"
        meta = _rj(setup_dir() / "library.json", {})
        meta[os.path.relpath(dst, library()).replace("\\", "/")] = {"source": rec["source"], "size": os.path.getsize(dst), "mood": mood,
                                                                   "method": how, "added": time.strftime("%Y-%m-%d %H:%M")}
        _wj(setup_dir() / "library.json", meta)
    return {"ok": True, "reindex": True}


def set_mood(path, mood):
    if mood not in MOODS:
        raise ValueError("unknown mood " + str(mood))
    lib = library()
    name = os.path.basename(path)
    o = overrides()
    o.setdefault("moods", {})[name.lower()] = mood
    _save_overrides(o)
    idx = _rj(lib / "_index.json", {"tracks": {}})
    T = idx.setdefault("tracks", {})
    old = _index_key(path)
    new_path = Path(path)
    in_mood_folder = _n(Path(path).parent.parent) == _n(lib) and Path(path).parent.name in MOODS
    if in_mood_folder and Path(path).parent.name != mood and os.path.exists(path):   # library tracks: the folder is the mood
        new_path = _unique(lib / mood / name)
        os.replace(path, new_path)
        meta = _rj(setup_dir() / "library.json", {})
        m = meta.pop(old.replace("\\", "/"), None)
        if m:
            meta[os.path.relpath(new_path, lib).replace("\\", "/")] = {**m, "mood": mood}
            _wj(setup_dir() / "library.json", meta)
        scans = _rj(STUDIO_SCAN, {})
        if str(path) in scans:
            scans[str(new_path)] = scans.pop(str(path))
            _wj(STUDIO_SCAN, scans)
    r = T.pop(old, None)
    new_key = _index_key(new_path)
    if r is not None:
        sys.path.insert(0, str(HERE))
        import music_lib as ml
        st = os.stat(new_path)
        r.update(cat=mood if in_mood_folder else r.get("cat", ""), sig=f"{st.st_size}:{int(st.st_mtime)}")
        r["moods"] = pin(new_key, ml.mood_scores(new_key, r))
        T[new_key] = r
        _wj(lib / "_index.json", idx)
    return {"ok": True, "path": str(new_path), "mood": mood, "moods": (r or {}).get("moods", {})}


# ------------------------------------------------------------------------------------------------ status
def status():
    lib = library()
    counts = {m: sum(1 for f in (lib / m).glob("*") if f.suffix.lower() in EXT) if (lib / m).is_dir() else 0 for m in MOODS}
    idx = _rj(lib / "_index.json", {"tracks": {}})
    T = idx.get("tracks", {})
    clean = sum(1 for r in T.values() if (r.get("vocal") or {}).get("verdict") == "clean")
    other = sum(1 for f in lib.rglob("*") if f.suffix.lower() in EXT and "_setup" not in f.parts) if lib.is_dir() else 0
    s = settings()
    prog = _rj(lib / "_setup" / "progress.json", {})
    if prog.get("state") in ("finding", "organising") and time.time() - prog.get("beat", 0) > 600:
        prog["state"] = "stopped"   # nothing reported for 10 min: the run was closed
    return {"library": str(lib), "extra_roots": s.get("music_extra_roots") or [], "counts": counts, "files": other,
            "indexed": len(T), "clean": clean, "needed": clean == 0 and not s.get("music_setup_dismissed"),
            "dismissed": bool(s.get("music_setup_dismissed")), "progress": prog,
            "removed": overrides().get("removed", []) if lib.is_dir() else [],
            "has_found": (lib / "_setup" / "found.json").exists(), "has_report": (lib / "_setup" / "report.json").exists(),
            "report_md": str(lib / "_setup" / "report.md")}


def _cli():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    a = sys.argv[1:]
    cmd = a[0] if a else "status"

    def opt(flag):
        return [a[i + 1] for i, x in enumerate(a) if x == flag and i + 1 < len(a)]
    if cmd == "find":
        try:
            r = find(opt("--place"), progress=lambda d: progress(**d))
        except Exception as e:
            progress(state="error", msg=f"{type(e).__name__}: {e}")
            raise
        progress(state="found", msg=f"Found {len(r['files'])} tracks", found=len(r["files"]))
        if "--json" in a:
            print(json.dumps(r, indent=1, ensure_ascii=False))
        else:
            for g in by_folder(r):
                print(f"{g['count']:4d} tracks {g['minutes']:6.1f} min  {g['folder']}")
            print(f"\n{len(r['files'])} tracks, {r['minutes']} min. Skipped: {r['skipped']}")
    elif cmd == "organise":
        if opt("--sel"):
            sel = _rj(opt("--sel")[0], [])
            paths = sel.get("paths", []) if isinstance(sel, dict) else sel
        elif "--all" in a:
            paths = [f["path"] for f in _rj(setup_dir() / "found.json", {}).get("files", [])]
        else:
            sys.exit("organise needs --all (everything find listed) or --sel FILE (a JSON list of paths)")
        skip = [_n(s) for s in opt("--skip")]
        paths = [p for p in paths if not any(_n(p).startswith(s + os.sep) or _n(os.path.dirname(p)) == s for s in skip)]
        try:
            r = organise(paths, mode="copy" if "--copy" in a else "link")
        except Exception as e:
            progress(state="error", msg=f"{type(e).__name__}: {e}")
            raise
        print(f"\nadded {len(r['added'])}, left out {len(r['rejected'])}, already there {len(r['already'])}, failed {len(r['failed'])}")
        print("per mood:", r["counts"])
        print("report:", setup_dir() / "report.md")
    else:
        print(json.dumps(status(), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    _cli()

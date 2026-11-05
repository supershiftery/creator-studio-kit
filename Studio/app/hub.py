"""The hub: everything the other tools know, read-only, in one place.
Competitor outliers (tracker.py), the Minecraft library (mc.py), live realms (Realm Checker), the two watchers,
Drive finished videos, recordings not yet in a project, VO takes, intro templates, music library."""
import json
import os
import re
import threading
import time
from pathlib import Path

import media
import store

ADDONS = Path(r"{{KIT}}/tools/minecraft")
REALMS_DB = ADDONS / "Tools" / "Realm Checker" / "realms-db.json"
HF = Path(r"{{KIT}}/assets\Graphics\HyperFrames")
_cache = {"t": 0, "data": None}


def tail(path, n=6):
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        return [l for l in lines if l.strip()][-n:]
    except OSError:
        return []


def pid_alive(pid_file):
    try:
        pid = int(Path(pid_file).read_text().strip())
    except Exception:
        return None
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        return False
    except Exception:
        return None


def competitors():
    bot = Path(store.settings()["competitor_tracker"])
    d = store.read_json(bot / "tracker_data.json", {}) or {}
    vids, out = d.get("videos", {}), []
    for vid, o in (d.get("outliers") or {}).items():
        if o.get("status") == "dismissed":
            continue
        v = vids.get(vid, {})
        out.append({"id": vid, "title": v.get("title", vid), "views": v.get("views", 0), "niche": v.get("niche", ""), "score": o.get("score") or 0,
                    "status": o.get("status", ""), "board": o.get("board", ""), "subs_x": v.get("subs_x"), "url": f"https://www.youtube.com/watch?v={vid}",
                    "published": v.get("published")})
    out.sort(key=lambda r: -(r["score"] or 0))
    ls = d.get("last_scan")
    return {"outliers": out[:15], "total": len(out), "last_scan": time.strftime("%Y-%m-%d %H:%M", time.localtime(ls)) if ls else "",
            "report": str(bot / "tracker_report.html") if (bot / "tracker_report.html").exists() else ""}


def library():
    L = store.read_json(ADDONS / "library.json", {}) or {}
    cfg = store.read_json(ADDONS / "config.json", {}) or {}
    vids = []
    for slug, v in (L.get("videos") or {}).items():
        n = len(v.get("mods", []) or []) + len(v.get("servers", []) or []) + len(v.get("clients", []) or [])
        folder = Path(r"{{GAMING_ROOT}}") / store.safe_name(v.get("title", slug))
        posts = 0
        for coll in ("mods", "servers", "clients"):
            for key in v.get(coll, []) or []:
                e = (L.get(coll) or {}).get(key) or {}
                if e.get("website"):
                    posts += 1
        vids.append({"slug": slug, "title": v.get("title", slug), "entries": n, "created": v.get("created", ""), "url": v.get("video_url", ""),
                     "folder": str(folder) if folder.is_dir() else "", "website_posts": posts, "screenshots": len(v.get("screenshots", []) or [])})
    vids.sort(key=lambda r: r["created"], reverse=True)
    return {"mods": len(L.get("mods", {})), "servers": len(L.get("servers", {})), "clients": len(L.get("clients", {})), "videos": vids,
            "current": cfg.get("current_video", ""), "library": str(ADDONS / "library.json")}


def realms():
    d = store.read_json(REALMS_DB, {}) or {}
    counts = {}
    live = []
    for code, v in d.items():
        st = v.get("status", "?")
        counts[st] = counts.get(st, 0) + 1
        if st in ("PLAYABLE", "OPT_IN"):
            live.append({"code": code, "name": v.get("realm_name") or v.get("name") or "", "status": st, "category": v.get("category", ""),
                         "checked": (v.get("last_checked") or "")[:10], "players": v.get("max_players"), "discord": v.get("discord", "")})
    live.sort(key=lambda r: (r["checked"], r["name"]), reverse=True)
    return {"counts": counts, "live": live[:40], "live_total": len(live), "db": str(REALMS_DB) if REALMS_DB.exists() else ""}


def watchers():
    w = Path(r"{{KIT}}/watcher")
    return [
        {"name": "AI Editing watcher", "what": "Gling XML / phone drops in {{PROJECTS_ROOT}} → product review + phone edits, Drive upload",
         "alive": pid_alive(w / "watcher.pid"), "log": tail(w / "watcher.log", 5), "log_path": str(w / "watcher.log")},
        {"name": "Minecraft B-roll watcher", "what": "OBS recordings with Director pink flashes → B-roll clips + stills + .broll.json sidecar",
         "alive": None, "log": tail(ADDONS / "broll-watch.log", 5), "log_path": str(ADDONS / "broll-watch.log")},
    ]


def drive_recent(n=12):
    root = Path(store.settings()["drive_root"])
    out = []
    if not root.is_dir():
        return {"ok": False, "root": str(root), "files": []}
    for ch in root.iterdir():
        if not ch.is_dir():
            continue
        for f in ch.rglob("*"):
            if f.is_file() and f.suffix.lower() in media.VIDEO_EXT:
                st = f.stat()
                out.append({"channel": ch.name, "name": f.name, "path": str(f), "size": st.st_size, "mtime": st.st_mtime,
                            "when": time.strftime("%Y-%m-%d", time.localtime(st.st_mtime))})
    out.sort(key=lambda r: -r["mtime"])
    return {"ok": True, "root": str(root), "files": out[:n], "total": len(out)}


_REC = {"t": 0, "key": None, "out": None}


def unassigned_recordings(docs, n=12):
    used = {(d.get("source") or "").lower() for d in docs}
    # the folder walk is ~0.2 s (stat per file): reuse it for 20 s unless a project took a recording (speed pass 2026-10-29)
    key = (frozenset(used), n)
    if _REC["key"] == key and time.time() - _REC["t"] < 20:
        return _REC["out"]
    _REC.update(t=time.time(), key=key, out=_unassigned(used, n))
    return _REC["out"]


def _unassigned(used, n):
    s = store.settings()
    out = []
    for r in s["recordings"]:
        if not os.path.isdir(r):
            continue
        for f in Path(r).iterdir():
            if f.is_file() and f.suffix.lower() in media.VIDEO_EXT and str(f).lower() not in used:
                mkv_twin = f.with_suffix(".mkv")
                if f.suffix.lower() == ".mkv" and f.with_suffix(".mp4").exists():
                    continue   # OBS remux twin
                st = f.stat()
                out.append({"name": f.name, "path": str(f), "size": st.st_size, "mtime": st.st_mtime, "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                            "broll": (Path(str(f) + ".broll.json")).exists()})
    out.sort(key=lambda r: -r["mtime"])
    return out[:n]


def vo_recent(n=8):
    s = store.settings()
    p = Path(s["vo_folder"])
    out = []
    if p.is_dir():
        for f in p.iterdir():
            if f.is_file() and f.suffix.lower() in media.AUDIO_EXT:
                st = f.stat()
                out.append({"name": f.name, "path": str(f), "when": time.strftime("%Y-%m-%d", time.localtime(st.st_mtime)), "mtime": st.st_mtime})
    out.sort(key=lambda r: -r["mtime"])
    return out[:n]


def intros():
    out = []
    if HF.is_dir():
        for d in HF.iterdir():
            if not d.is_dir() or not (d / "index.html").exists():
                continue
            renders = sorted((d / "renders").glob("*.mp4"), key=lambda f: f.stat().st_mtime) if (d / "renders").is_dir() else []
            kind = "intro" if "intro" in d.name else ("card" if "card" in d.name else ("transition" if "transition" in d.name else "graphic"))
            out.append({"name": d.name, "path": str(d), "kind": kind, "render": str(renders[-1]) if renders else "",
                        "when": time.strftime("%Y-%m-%d", time.localtime((renders[-1] if renders else d / "index.html").stat().st_mtime))})
    out.sort(key=lambda r: r["when"], reverse=True)
    return out


def music():
    root = Path(store.settings()["music_root"])
    out = []
    if root.is_dir():
        for d in sorted(root.iterdir()):
            if d.is_dir() and not d.name.startswith("_"):
                n = sum(1 for f in d.rglob("*") if f.suffix.lower() in media.AUDIO_EXT)
                out.append({"name": d.name, "count": n, "path": str(d)})
    return out


def _gather():
    data = {}
    for k, fn in (("competitors", competitors), ("library", library), ("realms", realms), ("watchers", watchers), ("drive", drive_recent),
                  ("vo", vo_recent), ("intros", intros), ("music", music)):
        try:
            data[k] = fn()
        except Exception as e:  # noqa
            data[k] = {"error": str(e)}
    _cache.update(t=time.time(), data=data)
    return data


def snapshot(docs, max_age=60):
    if _cache["data"] and time.time() - _cache["t"] < max_age:
        data = dict(_cache["data"])
    elif _cache["data"] and max_age > 0:   # stale: last numbers now, new ones in the background (speed pass 2026-10-29)
        if not _cache.get("bg"):
            _cache["bg"] = True

            def bg():
                try:
                    _gather()
                finally:
                    _cache["bg"] = False
            threading.Thread(target=bg, name="hub-refresh", daemon=True).start()
        data = dict(_cache["data"])
    else:
        data = dict(_gather())
    data["recordings"] = unassigned_recordings(docs)
    return data

"""Tracker: dashboard numbers, stages, Google Drive hand-off, article discovery, to-do."""
import os
import re
import shutil
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import store

STAGES = ["idea", "filming", "editing", "review", "final", "shipped", "published"]
STAGE_LABEL = {"idea": "Idea", "filming": "Filming", "editing": "Editing", "review": "Review draft", "final": "Final ready", "shipped": "On Drive (done)", "published": "Published"}
_drive_checked = {}


def auto_drive(doc):
    """A final that landed in the Drive folder = your part is done: tick 'drive' and stamp shipped_on (checked once a minute)."""
    if doc["checklist"].get("drive"):
        return
    now = time.time()
    if now - _drive_checked.get(doc["id"], 0) < 60:
        return
    _drive_checked[doc["id"]] = now
    try:
        folder = drive_folder(doc)
        if folder.is_dir():
            vids = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in (".mp4", ".mov", ".mkv") and f.stat().st_size > 20_000_000]
            if vids:
                doc["checklist"]["drive"] = True
                doc["checklist"]["final"] = True
                doc["shipped_on"] = time.strftime("%Y-%m-%d", time.localtime(max(f.stat().st_mtime for f in vids)))
                store.save(doc)
    except Exception:
        pass


def derived_stage(doc):
    c = doc.get("checklist", {})
    if c.get("published") or doc.get("links", {}).get("youtube"):
        return "published"
    if c.get("drive"):
        return "shipped"
    if c.get("final"):
        return "final"
    if c.get("draft"):
        return "review"
    if c.get("footage") or doc.get("source"):
        return "editing"
    return doc.get("stage") if doc.get("stage") in ("idea", "filming") else "idea"


def stage(doc):
    manual = doc.get("stage_manual")
    return manual if manual in STAGES else derived_stage(doc)


def parse_date(s):
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def week_bounds(d=None):
    d = d or date.today()
    start = d - timedelta(days=d.weekday())
    return start, start + timedelta(days=6)


def channel_cfg(name):
    for c in store.settings()["channels"]:
        if c["name"].lower() == (name or "").lower():
            return c
    return None


def summary(docs):
    today = date.today()
    ws, we = week_bounds(today)
    out = {"today": str(today), "week": [str(ws), str(we)], "channels": [], "overdue": [], "due_soon": [], "needs_thumbnail": [],
           "needs_description": [], "in_review": [], "ready_to_ship": [], "counts": {s: 0 for s in STAGES}}
    for d in docs:
        st = stage(d)
        out["counts"][st] += 1
        due = parse_date(d.get("due") or "")
        row = {"id": d["id"], "title": d["title"], "type": d["type"], "channel": d.get("channel", ""), "due": d.get("due", ""), "stage": st}
        if due and st not in ("shipped", "published"):
            if due < today:
                out["overdue"].append(dict(row, days=(today - due).days))
            elif (due - today).days <= 14:
                out["due_soon"].append(dict(row, days=(due - today).days))
        if st in ("review", "final", "editing") and not d["checklist"].get("thumbnail"):
            out["needs_thumbnail"].append(row)
        if st in ("review", "final") and not d["checklist"].get("description"):
            out["needs_description"].append(row)
        if st == "review":
            out["in_review"].append(row)
        if st == "final":
            out["ready_to_ship"].append(row)
    out["overdue"].sort(key=lambda r: -r["days"])
    out["due_soon"].sort(key=lambda r: r["days"])
    for ch in store.settings()["channels"]:
        mine = [d for d in docs if (d.get("channel") or "").lower() == ch["name"].lower()]
        done_week = [d for d in mine if stage(d) in ("shipped", "published") and (parse_date(d.get("shipped_on") or d.get("published_on") or d.get("updated", "")) or today) >= ws]
        published_week = done_week
        planned_week = [d for d in mine if stage(d) not in ("shipped", "published") and parse_date(d.get("due") or "") and ws <= parse_date(d["due"]) <= we]
        out["channels"].append({"name": ch["name"], "per_week": ch.get("per_week", 0), "published": len(published_week),
                                "planned": len(planned_week), "in_progress": len([d for d in mine if stage(d) in ("editing", "review", "final")]),
                                "types": ch.get("types", [])})
    return out


# ------------------------------------------------------------------ Drive
def _norm_name(x):
    """'alo clothing v2 FINAL' == 'alo clothing v2' == 'Alo Clothing V2 (2026)'"""
    x = re.sub(r"\(\d{4}\)", "", x.lower())
    x = re.sub(r"\b(final|draft)\b$", "", x.strip())
    return re.sub(r"[^a-z0-9]", "", re.sub(r"\bfinal\b", "", x))


_DRIVE_INDEX = {"at": 0, "root": None, "chans": {}}   # one listing of the Drive channel folders, shared by every project


def _drive_index(root, max_age=90):
    """{channel folder: [its sub-folders]}. Google Drive (G:) answers each stat slowly: every project used to walk the whole
    tree twice per refresh (113 walks, 15 s on the first Projects load, 2026-10-29). Now one walk, reused for 90 s."""
    now = time.time()
    if _DRIVE_INDEX["root"] == root and now - _DRIVE_INDEX["at"] < max_age:
        return _DRIVE_INDEX["chans"]
    chans = {}
    try:
        if root.is_dir():
            for c in root.iterdir():
                try:
                    if c.is_dir():
                        chans[c] = [d for d in c.iterdir() if d.is_dir()]
                except OSError:
                    pass
    except OSError:
        pass
    _DRIVE_INDEX.update(at=now, root=root, chans=chans)
    return chans


def drive_folder(doc):
    """The project's Drive hand-off folder: an existing folder with the same name in ANY channel folder wins (the
    bot and the watcher sometimes file a video under a different channel, or as '<name> FINAL'); else <channel>/<title>."""
    s = store.settings()
    ch = channel_cfg(doc.get("channel"))
    sub = (ch or {}).get("drive") or doc.get("channel") or "_Unknown Channel"
    root = Path(s["drive_root"])
    base = root / sub
    wants = {_norm_name(store.safe_name(doc["title"])), _norm_name(Path(doc["path"]).name)}
    idx = _drive_index(root)
    for c in [base] + [c for c in idx if c != base]:
        for d in idx.get(c, []):
            if _norm_name(d.name) in wants:
                return d
    return base / store.safe_name(doc["title"])


IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
_thumb_checked = {}


def auto_thumb(doc, force=False):
    """A thumbnail image in the project's Drive folder (the designer's) becomes the
    project's thumbnail: copied into <project>\\Thumbnail, shown on the card, and 'Thumbnail' ticked. A newer image on
    Drive replaces an older one. Checked at most once a minute per project."""
    now = time.time()
    if not force and now - _thumb_checked.get(doc["id"], 0) < 60:
        return False
    _thumb_checked[doc["id"]] = now
    try:
        folder = drive_folder(doc)
        if not folder.is_dir():
            return False
        imgs = [f for f in folder.rglob("*") if f.is_file() and f.suffix.lower() in IMG_EXT]
        if not imgs:
            return False
        best = max(imgs, key=lambda f: f.stat().st_mtime)
        # the video was filed under a different channel on Drive: that is where it really went, follow it
        drive_ch = folder.parent.name
        if channel_cfg(drive_ch) and (doc.get("channel") or "").lower() != drive_ch.lower():
            doc["channel"] = channel_cfg(drive_ch)["name"]
        cur = doc["slots"].get("thumbnail") or ""
        if cur and os.path.exists(cur):
            if os.path.getmtime(cur) >= best.stat().st_mtime - 1 and os.path.getsize(cur) == best.stat().st_size:
                return False   # already have this one (or a newer one made in the app)
            if os.path.getmtime(cur) > best.stat().st_mtime + 1 and "frame" not in Path(cur).name.lower():
                return False   # a thumbnail added in the app after the Drive one: keep it
        dest_dir = Path(doc["path"]) / "Thumbnail"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / ("thumbnail (from Drive)" + best.suffix.lower())
        shutil.copy2(best, dest)
        doc["slots"]["thumbnail"] = str(dest)
        doc["checklist"]["thumbnail"] = True
        doc["thumb_source"] = str(best)
        store.save(doc)
        return True
    except Exception:
        return False


def drive_status(doc):
    root = Path(store.settings()["drive_root"])
    folder = drive_folder(doc)
    files = []
    if folder.is_dir():
        for f in sorted(folder.iterdir()):
            if f.is_file():
                files.append({"name": f.name, "size": f.stat().st_size, "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime))})
    return {"root_ok": root.is_dir(), "folder": str(folder), "exists": folder.is_dir(), "files": files}


def send_to_drive(doc, final_path, extra=()):
    """Copy the FINAL (never a draft: drafts never go to Drive) + description + thumbnail."""
    root = Path(store.settings()["drive_root"])
    if not root.is_dir():
        raise FileNotFoundError(f"Drive folder not mounted: {root}")
    folder = drive_folder(doc)
    folder.mkdir(parents=True, exist_ok=True)
    copied = []
    dest = folder / f"{store.safe_name(doc['title'])}.mp4"
    if dest.exists() and dest.stat().st_size == os.path.getsize(final_path):
        copied.append(("video (already there)", str(dest)))
    else:
        if dest.exists():   # Drive serves stale copies of a replaced same-name file: deliver under a fresh name
            dest = folder / f"{store.safe_name(doc['title'])} FINAL {time.strftime('%H%M')}.mp4"
        shutil.copy2(final_path, dest)
        copied.append(("video", str(dest)))
    desc = doc["slots"].get("description")
    if desc and os.path.exists(desc):
        shutil.copy2(desc, folder / "YouTube description.txt")
        copied.append(("description", str(folder / "YouTube description.txt")))
    th = doc["slots"].get("thumbnail")
    if th and os.path.exists(th):
        shutil.copy2(th, folder / ("thumbnail" + Path(th).suffix.lower()))
        copied.append(("thumbnail", str(folder / ("thumbnail" + Path(th).suffix.lower()))))
    for e in extra:
        if e and os.path.exists(e):
            shutil.copy2(e, folder / Path(e).name)
            copied.append((Path(e).name, str(folder / Path(e).name)))
    return {"folder": str(folder), "copied": copied}


# ------------------------------------------------------------------ articles / listings (gaming)
def find_articles(doc):
    p = Path(doc["path"])
    out = []
    seen = set()

    def add(f, kind):
        if str(f) in seen or not f.is_file():
            return
        seen.add(str(f))
        out.append({"file": str(f), "name": (f.parent.name + " / " + f.name) if kind == "entry article" else f.name, "kind": kind, "size": f.stat().st_size,
                    "when": time.strftime("%Y-%m-%d", time.localtime(f.stat().st_mtime))})
    for f in sorted(p.glob("*.html")) + sorted(p.glob("*.md")) + sorted(p.glob("*.txt")):
        if f.name.lower().startswith(("roundup", "article", "youtube", "00 start", "showcase")):
            add(f, "roundup" if "roundup" in f.name.lower() else ("description" if "description" in f.name.lower() else "guide"))
    for d in sorted(p.glob("#*")) + sorted(p.glob("Extra - *")):
        if d.is_dir():
            for f in sorted(d.glob("article.*")) + sorted(d.glob("*.html")):
                add(f, "entry article")
    for d in ("listings listings", "Listings", "Articles"):
        if (p / d).is_dir():
            for f in sorted((p / d).iterdir()):
                add(f, "listing")
    for f in doc["slots"].get("articles", []):
        if os.path.exists(f):
            add(Path(f), "article")
    return out


def website_posts(doc):
    """post ids stored in the Minecraft library for this video's entries (mc.py website uploads)."""
    lib = store.read_json(r"{{KIT}}/tools/minecraft\library.json", {}) or {}
    slug = doc.get("settings", {}).get("library_slug") or ""
    vids = lib.get("videos", {})
    if not slug:
        want = store.slug(doc["title"])
        slug = next((k for k, v in vids.items() if store.slug(v.get("title", "")) == want or k == want), "")
    if not slug or slug not in vids:
        return {"slug": "", "posts": []}
    v = vids[slug]
    posts = []
    for coll in ("mods", "servers", "clients"):
        for key in v.get(coll, []) or []:
            e = (lib.get(coll) or {}).get(key) or {}
            mp = e.get("website")
            if mp:
                pid = mp.get("post_id") if isinstance(mp, dict) else mp
                posts.append({"entry": e.get("name", key), "post_id": pid, "status": (mp.get("status") if isinstance(mp, dict) else "draft"),
                              "url": f"https://{{WEBSITE}}/admin/edit-post/{pid}"})
    rp = v.get("website")
    if rp:
        pid = rp.get("post_id") if isinstance(rp, dict) else rp
        posts.append({"entry": "Roundup", "post_id": pid, "status": "draft", "url": f"https://{{WEBSITE}}/admin/edit-post/{pid}"})
    return {"slug": slug, "posts": posts, "screenshots": v.get("screenshots", [])}

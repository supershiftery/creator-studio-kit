"""Projects, settings and the index. Everything is plain JSON on disk so the user (and Claude) can read it.

- data/settings.json      app settings (roots, channels, drive folder, targets)
- data/projects.json      index: [{"id", "path"}] - the truth about a project is its own studio.json
- <project>/studio.json   the project: type, title, slots, settings, notes, tracker checklist, renders
"""
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path

APP = Path(__file__).resolve().parent
HOME = APP.parent
DATA = HOME / "data"
DATA.mkdir(exist_ok=True)

DEFAULT_SETTINGS = {
    "roots": {
        "gaming": r"{{GAMING_ROOT}}",
        "phone": r"{{PROJECTS_ROOT}}",
        "review": r"{{PROJECTS_ROOT}}",
        "haul": r"{{PROJECTS_ROOT}}",
        "short": r"{{PROJECTS_ROOT}}",
    },
    "drive_root": r"{{DRIVE_FINISHED}}",
    "default_machine": "Desktop",   # kit: one PC builds and schedules everything
    "recordings": [r"{{RECORDINGS}}"],
    "vo_folder": r"{{VO_FOLDER}}",
    "music_root": r"{{MUSIC_ROOT}}",
    "channels": [
        {"name": "{{GAMING_CHANNEL}}", "types": ["gaming"], "per_week": 3, "drive": "{{GAMING_CHANNEL}}"},
        {"name": "{{PHONE_CHANNEL}}", "types": ["phone"], "per_week": 3, "drive": "{{PHONE_CHANNEL}}"},
        {"name": "{{REVIEW_CHANNEL}}", "types": ["review", "haul"], "per_week": 2, "drive": "{{REVIEW_CHANNEL}}"},
    ],
    "python": None,  # None = this interpreter
    "notify_toast": True,
    "port": 8765,
}

TYPES = {
    "gaming": {"label": "Gaming / Minecraft", "icon": "⛏", "accent": "#5bd97a",
               "blurb": "Top 5 / Top 10 realms, servers, add-ons. Corner cam, B-roll reel, wipes, cards, soft game OST bed."},
    "phone": {"label": "Phone / app tutorial", "icon": "📱", "accent": "#3ec6ff",
              "blurb": "Promo-code and app walkthroughs (Uber Eats style). Full webcam, phone PiP left, brand wipes, type beats."},
    "review": {"label": "Product review", "icon": "📦", "accent": "#ffb13d",
               "blurb": "Dual-camera DHgate reviews. Two-mic swap, circular face cam, zooms, price callout, type beats."},
    "haul": {"label": "Haul", "icon": "🛍", "accent": "#ff6fb1",
             "blurb": "One long phone recording, products back to back. 1080p60 normalise, trim, type beat per section, Doug captions on the intro + outro."},
    "short": {"label": "Short (vertical)", "icon": "📲", "accent": "#b98cff",
              "blurb": "A raw vertical recording edited as its own Short / TikTok. 1080x1920 60 fps, tight trim, type beat, Doug captions throughout."},
}

CHECKLIST = [
    ("footage", "Footage in"),
    ("intro", "Intro"),
    ("draft", "Draft built"),
    ("approved", "Draft approved"),
    ("final", "Final rendered"),
]   # editor-only kit: just the editing steps (no thumbnails, descriptions, uploads or to-do)
CHECK_IDS = [c for c, _ in CHECKLIST]


def now():
    return time.strftime("%Y-%m-%d %H:%M")


def read_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def write_json(path, data):
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def settings():
    s = read_json(DATA / "settings.json", {}) or {}
    out = json.loads(json.dumps(DEFAULT_SETTINGS))
    for k, v in s.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def save_settings(patch):
    s = read_json(DATA / "settings.json", {}) or {}
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(s.get(k), dict):
            s[k].update(v)
        else:
            s[k] = v
    write_json(DATA / "settings.json", s)
    return settings()


def safe_name(title):
    n = re.sub(r'[<>:"/\\|?*]', "", title).strip().rstrip(".")
    return re.sub(r"\s+", " ", n) or "video"


def slug(title):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", title.lower())).strip("-") or "video"


def _f_alias():
    """where F: really lives when it is a subst (the laptop: F: = C:\\Hub, 2026-10-25), else None"""
    try:
        r = str(Path("F:\\").resolve()).rstrip("\\")
    except OSError:
        return None
    return r if r.upper() != "F:" else None


def make_id(path):
    # resolve() turns the laptop's F:\... into C:\Hub\...; map it back so a project has the SAME id on both machines
    # (the desktop asks the laptop to build project <id>)
    p = str(Path(path).resolve())
    alias = _f_alias()
    if alias and p.lower().startswith(alias.lower() + "\\"):
        p = "F:" + p[len(alias):]
    return hashlib.sha1(p.lower().encode()).hexdigest()[:10]


# ------------------------------------------------------------------ index
def index():
    return read_json(DATA / "projects.json", []) or []


def save_index(items):
    write_json(DATA / "projects.json", items)


def register(path):
    items = index()
    pid = make_id(path)
    if not any(i["id"] == pid for i in items):
        items.append({"id": pid, "path": str(path)})
        save_index(items)
    return pid


def unregister(pid):
    save_index([i for i in index() if i["id"] != pid])


def project_path(pid):
    for i in index():
        if i["id"] == pid:
            pth = Path(i["path"])
            if (pth / "studio.json").exists():
                return pth
            moved = find_moved(pid)   # renamed in Explorer / by another Claude session: follow it by the id in studio.json
            if moved:
                set_path(pid, moved)
                return moved
            return pth
    return None


def set_path(pid, new_path):
    items = index()
    for i in items:
        if i["id"] == pid:
            i["path"] = str(new_path)
    save_index(items)


def find_moved(pid):
    s = settings()
    for root in {s["roots"]["gaming"], s["roots"]["phone"], s["roots"]["review"]}:
        r = Path(root)
        if not r.is_dir():
            continue
        for d in r.iterdir():
            f = d / "studio.json"
            if d.is_dir() and f.exists():
                try:
                    if (read_json(f) or {}).get("id") == pid:
                        return d
                except Exception:
                    pass
    return None


def _swap_prefix(obj, old, new):
    """every string in obj that starts with the old folder now starts with the new one"""
    if isinstance(obj, str):
        return new + obj[len(old):] if obj.lower().startswith(old.lower()) else obj
    if isinstance(obj, list):
        return [_swap_prefix(x, old, new) for x in obj]
    if isinstance(obj, dict):
        return {k: _swap_prefix(v, old, new) for k, v in obj.items()}
    return obj


def rename_project(pid, title, rename_folder=True):
    """New title; optionally the folder (and the files named after it) too, so the name is the same everywhere."""
    doc = load(pid)
    if not doc:
        raise FileNotFoundError(pid)
    old_title, old_path = doc["title"], Path(doc["path"])
    title = title.strip()
    if not title:
        raise ValueError("empty name")
    renamed = []
    if rename_folder:
        new_path = old_path.parent / safe_name(title)
        if new_path.exists() and new_path.resolve() != old_path.resolve():
            raise ValueError(f"a folder called {new_path.name} already exists")
        if new_path.name != old_path.name:
            if new_path == old_path:   # only the capitals changed: Windows paths compare equal, so step through a temp name
                tmp = old_path.with_name(old_path.name + ".renaming")
                os.rename(old_path, tmp)
                old_path_tmp = tmp
            else:
                old_path_tmp = old_path
            os.rename(old_path_tmp, new_path)
            renamed.append((str(old_path), str(new_path)))
            set_path(pid, new_path)
            doc = _swap_prefix(doc, str(old_path), str(new_path))
            doc["path"] = str(new_path)
            # files named after the folder / title: phone "<name> - DRAFT*.mp4", gaming "Edit\<title> draft|final.mp4"
            oldn, newn = old_path.name, new_path.name
            for d in (new_path / "output", new_path / "Edit"):
                if d.is_dir():
                    for f in list(d.iterdir()):
                        for o, nn in ((oldn, newn), (safe_name(old_title), safe_name(title))):
                            if f.name.startswith(o + " ") or f.name.startswith(o + "_"):
                                dest = f.with_name(nn + f.name[len(o):])
                                if not dest.exists():
                                    os.rename(f, dest)
                                    renamed.append((str(f), str(dest)))
                                    doc = _swap_prefix(doc, str(f), str(dest))
                                break
    doc["title"] = title
    save(doc)
    return {"title": title, "path": str(load(pid)["path"]), "renamed": renamed}


# ------------------------------------------------------------------ projects
def new_project_doc(title, vtype, channel="", due="", source=""):
    return {
        "id": "",
        "title": title,
        "type": vtype,
        "channel": channel,
        "due": due,
        "stage": "editing",          # idea | filming | editing | review | final | published
        "created": now(),
        "updated": now(),
        "source": source,            # main footage: path (gaming references the recording in place)
        "slots": {"intro": "", "intro_vo": "", "broll": [], "thumbnail": "", "description": "", "articles": [], "music": {}},
        "settings": {},
        "notes": [],
        "checklist": {c: False for c in CHECK_IDS},
        "renders": [],
        "links": {"youtube": "", "ticktick": "", "website": [], "listings": []},
    }


def load(pid):
    p = project_path(pid)
    if not p:
        return None
    doc = read_json(p / "studio.json")
    if not doc:
        return None
    doc["id"] = pid
    doc["path"] = str(p)
    return doc


def save(doc):
    p = Path(doc["path"])
    out = {k: v for k, v in doc.items() if k not in ("path",)}
    out["updated"] = now()
    write_json(p / "studio.json", out)
    return load(doc["id"])


def all_projects():
    out = []
    for i in index():
        d = load(i["id"])
        if d:
            out.append(d)
    out.sort(key=lambda d: d.get("updated", ""), reverse=True)
    return out


def create(title, vtype, channel="", due="", source="", root=None):
    s = settings()
    root = Path(root or s["roots"][vtype])
    root.mkdir(parents=True, exist_ok=True)
    folder = root / safe_name(title)
    n = 2
    while folder.exists() and (folder / "studio.json").exists():
        folder = root / f"{safe_name(title)} ({n})"
        n += 1
    folder.mkdir(parents=True, exist_ok=True)
    doc = new_project_doc(title, vtype, channel, due, source)
    pid = register(folder)
    doc["id"] = pid
    doc["path"] = str(folder)
    return save(doc)


def adopt(folder, vtype=None, title=None):
    """Turn an existing folder (a past edit) into a project without moving anything."""
    folder = Path(folder)
    if not folder.is_dir():
        raise FileNotFoundError(folder)
    existing = read_json(folder / "studio.json")
    pid = register(folder)
    if existing:
        return load(pid)
    vtype = vtype or guess_type(folder)
    doc = new_project_doc(title or folder.name, vtype)
    doc["id"], doc["path"] = pid, str(folder)
    # pick up what is already there
    raw = folder / "raw"
    if (raw / "source.mp4").exists():
        doc["source"] = str(raw / "source.mp4")
    elif (raw / "camera.mp4").exists():
        doc["source"] = str(raw / "camera.mp4")
    for cand in ("youtube-description.txt", "description.txt"):
        if (folder / cand).exists():
            doc["slots"]["description"] = str(folder / cand)
    for f in sorted(folder.glob("*.html")):
        doc["slots"]["articles"].append(str(f))
    intros = sorted((folder / "Intro").glob("*.mp4")) if (folder / "Intro").is_dir() else []
    if intros:
        doc["slots"]["intro"] = str(intros[-1])
    for ri in list(raw.glob("intro.*")) if raw.is_dir() else []:
        doc["slots"]["intro_vo"] = str(ri)
    if not doc["source"]:   # the recording may still sit in the OBS folder under the project's name
        s = settings()
        for r in s["recordings"]:
            for ext in (".mp4", ".mkv", ".mov"):
                cand = Path(r) / (folder.name + ext)
                if cand.exists():
                    doc["source"] = str(cand)
                    break
            if doc["source"]:
                break
    doc["checklist"]["footage"] = bool(doc["source"])
    doc["checklist"]["description"] = bool(doc["slots"]["description"])
    doc["checklist"]["intro"] = bool(doc["slots"]["intro"] or doc["slots"]["intro_vo"])
    # renders already made by hand (Edit\*draft*.mp4, output\* - FINAL*.mp4 ...)
    found = []
    for d in (folder / "Edit", folder / "output", folder):
        if d.is_dir():
            for f in d.glob("*.mp4"):
                low = f.name.lower()
                if low.startswith("draft-cut") or "_check" in low:
                    continue   # cut-only review copies
                if "draft" in low:
                    found.append((f.stat().st_mtime, f, "draft"))
                elif "final" in low:
                    found.append((f.stat().st_mtime, f, "final"))
    found.sort()
    keep = [x for x in found if x[2] == "draft"][-3:] + [x for x in found if x[2] == "final"][-2:]
    for _, f, kind in sorted(keep):
        add_render(doc, f, kind)
    return save(doc)


def guess_type(folder):
    s = settings()
    f = str(folder).lower()
    if f.startswith(s["roots"]["gaming"].lower()):
        return "gaming"
    if (folder / "raw" / "camera.mp4").exists() or (folder / "raw" / "edit.xml").exists():
        return "review"
    return "phone"


def add_render(doc, path, kind):
    doc["renders"] = [r for r in doc.get("renders", []) if r["file"] != str(path)]
    doc["renders"].append({"file": str(path), "kind": kind, "when": now(),
                           "size": os.path.getsize(path) if os.path.exists(path) else 0})
    doc["checklist"]["draft" if kind == "draft" else "final"] = True
    if kind == "final":
        doc["checklist"]["draft"] = True
    return doc


def copy_into(src, dest_dir, name=None):
    """Copy a dropped file into the project (never hardlink: a hardlink once destroyed an original)."""
    src = Path(src)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (name or src.name)
    if dest.resolve() == src.resolve():
        return dest
    if dest.exists():
        dest.unlink()
    size = src.stat().st_size
    if size < 300e6:
        shutil.copy2(src, dest)
        return dest
    # big files are copied in chunks so the app can show how far it is (sp5der hoodie 2026-10-23: a 17 GB recording picked from
    # the Google Drive G: drive streamed down for minutes with the New Project window looking frozen)
    key = str(dest)
    COPYING[key] = {"src": str(src), "done": 0, "total": size, "started": time.time()}
    try:
        with open(src, "rb") as fi, open(dest, "wb") as fo:
            while True:
                b = fi.read(16 << 20)
                if not b:
                    break
                fo.write(b)
                COPYING[key]["done"] += len(b)
        shutil.copystat(src, dest)
    except BaseException:
        try:
            dest.unlink()
        except OSError:
            pass
        raise
    finally:
        COPYING.pop(key, None)
    return dest


COPYING = {}   # dest path -> {"src", "done", "total", "started"} while a big file is being copied in


def copying_into(folder):
    """the big copy running into this project folder, as {"src", "done", "total", "started"} (or None)"""
    f = str(folder).rstrip("\\/").lower() + os.sep
    return next((dict(c, dest=k) for k, c in list(COPYING.items()) if k.lower().startswith(f)), None)

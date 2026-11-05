"""Local HTTP API + static UI + range-capable media serving. Stdlib only.
python server.py [port]   (main.py normally starts this in a thread and opens the window)"""
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import shutil
import time
import traceback
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobs  # noqa: E402
import media  # noqa: E402
import store  # noqa: E402
import tracker  # noqa: E402
import hub  # noqa: E402
import todo  # noqa: E402
import chat  # noqa: E402
import notify  # noqa: E402
import extras  # noqa: E402
import extras2  # noqa: E402
import external  # noqa: E402
import speech  # noqa: E402
import detect  # noqa: E402
import kit_update  # noqa: E402
import music_setup  # noqa: E402
import edit_stats  # noqa: E402
import setup_wizard  # noqa: E402
import mystyle  # noqa: E402
import remote  # noqa: E402
import schedule  # noqa: E402
from recipes import RECIPES, common, one_take  # noqa: E402
from recipes import get as recipe  # noqa: E402

UI = store.HOME / "ui"
mimetypes.add_type("application/javascript", ".js")


class ApiError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


# ------------------------------------------------------------------ project views
ACTIVE_ORDER = {"importing": 0, "rendering": 0, "waiting": 1, "revising": 2}


def activity(doc, v):
    """What is happening to this video right now (user 2026-10-23: 'show it's working on a revision', active ones on top):
    rendering (pct, eta) | waiting (place in the render queue) | revising (the AI is reading the notes / fixing) |
    importing (its files are still being copied in, e.g. from Google Drive) | None."""
    c = store.copying_into(doc["path"])
    if c or doc["id"] in IMPORTING:
        c = c or {}
        pct = 100 * c["done"] / c["total"] if c.get("total") else 0
        rate = c.get("done", 0) / max(1e-3, time.time() - c["started"]) if c else 0
        where = "Google Drive" if c.get("src", "").upper().startswith("G:") else "your files"
        return {"state": "importing", "label": f"Copying from {where} {round(pct)}%" if c else "Copying files in",
                "pct": pct, "eta_s": (c["total"] - c["done"]) / rate if rate > 1e6 else 0,
                "detail": f"{Path(c['src']).name}: {c['done'] / 1e9:.1f} of {c['total'] / 1e9:.1f} GB" if c else "", "job": None}
    j = v["jobs"][0] if v["jobs"] else None
    if j and j.get("current") == "remote" and j.get("status") == "running":
        # sent to the laptop and still in ITS line: "waiting #N on Laptop", not a render with a creeping % (user 2026-10-26)
        where, rj = remote.job_for(doc["id"])
        if rj and (rj.get("queue") or {}).get("state") == "waiting":
            return job_activity(rj, where)
    if j:
        return job_activity(j)
    where, rj = remote.job_for(doc["id"])   # built on another machine (remote.py: the laptop's Studio)
    if rj:
        return job_activity(rj, where)
    if v.get("external"):
        x = v["external"]
        return {"state": "rendering", "label": f"Rendering {round(x.get('pct') or 0)}%", "pct": x.get("pct") or 0, "eta_s": x.get("eta_s") or 0, "detail": x.get("step", "")}
    claude = v.get("claude") or {}
    if claude.get("busy") or chat.run_active(doc) or any(n.get("status") == "claude" for n in doc.get("notes", [])):
        steps = claude.get("steps") or []
        return {"state": "revising", "label": "Revision in progress", "detail": ((steps[-1] or {}).get("text", "") if steps else "")[:120],
                "elapsed": claude.get("elapsed", 0)}
    return None


def job_activity(j, where=None):
    """A job view -> card activity. where = the other machine's name for a remote job: the label says so and there is no
    job id (the move / cancel buttons would act on THIS machine's queue)."""
    q = j.get("queue") or {}
    pr = j.get("progress") or {}
    on = f" on {where}" if where else ""
    jid = None if where else j["id"]
    if q.get("state") == "waiting":
        return {"state": "waiting", "label": f"Waiting to render{on} · #{q['pos']} in line", "pos": q["pos"], "wait_s": q.get("wait_s", 0),
                "job": jid, "where": where}
    if q.get("state") == "ai" and j.get("current") == "remote" and j.get("status") == "running":
        # our "Building on <machine>" proxy: it IS a render (there), with its own upload / build / bring-back %
        # the step's own label ("Building on Laptop"; the step list shows its stages, so read it from the queue / progress)
        lab = q.get("step") or pr.get("step") or ""
        there = (lab.rsplit(" ", 1)[-1] if lab.startswith(("Building on ", "Uploading to ", "Bringing back from ")) else "") or where or "the other PC"
        return {"state": "rendering", "label": f"Rendering on {there} {round(pr.get('pct') or 0)}%", "pct": pr.get("pct") or 0,
                "eta_s": pr.get("eta_s") or 0, "detail": pr.get("step", ""), "job": jid, "where": there, "via": True}
    if q.get("state") == "ai":
        return {"state": "revising", "label": f"Revision in progress{on}", "detail": q.get("step", ""), "job": jid, "where": where}
    return {"state": "rendering", "label": f"Rendering{on} {round(pr.get('pct') or 0)}%", "pct": pr.get("pct") or 0, "eta_s": pr.get("eta_s") or 0,
            "detail": pr.get("step", ""), "job": jid, "stuck_s": pr.get("stuck_s") or 0, "where": where}


def project_view(doc, full=False):
    r = recipe(doc["type"])
    info = media.probe(doc["source"]) if doc.get("source") else None
    layout = media.layout_of(info)
    thumb_crop = None
    if layout == "side-by-side":
        thumb_crop = "right" if doc["type"] == "gaming" else "left"
    v = {k: doc[k] for k in ("id", "title", "type", "channel", "due", "created", "updated", "source", "slots", "settings", "notes", "checklist", "renders", "links", "path")}
    v["thumb_brief"] = doc.get("thumb_brief", "")
    v["auto_send"] = bool(doc.get("auto_send"))   # phone notes waiting for the current build/revision run to finish
    v["builds"] = doc.get("builds", [])
    v["yt_title"] = doc.get("yt_title", "")
    v["title_ideas"] = doc.get("title_ideas", [])
    v["shipped_on"] = doc.get("shipped_on", "")
    if full:   # the list (Projects / Dashboard) gets these from the background sweep: Drive is slow (user 2026-10-29)
        tracker.auto_drive(doc)
        if tracker.auto_thumb(doc):
            doc = store.load(doc["id"])
    v["stage"] = tracker.stage(doc)
    v["stage_manual"] = doc.get("stage_manual", "")
    v["published_on"] = doc.get("published_on", "")
    v["type_label"] = store.TYPES[doc["type"]]["label"]
    v["accent"] = store.TYPES[doc["type"]]["accent"]
    v["source_info"] = info
    v["layout"] = layout
    v["thumb"] = doc["slots"].get("thumbnail") or doc.get("source") or ""
    v["thumb_crop"] = None if doc["slots"].get("thumbnail") else thumb_crop
    outs = r.outputs(doc)
    have = {o["file"].lower() for o in outs}
    home = os.path.normcase(os.path.abspath(doc["path"])) + os.sep
    for rr in doc.get("renders", []):   # hand-made renders registered on adopt; never another project's file
        if rr["file"].lower() not in have and os.path.exists(rr["file"]) and os.path.normcase(os.path.abspath(rr["file"])).startswith(home):
            outs.append({"kind": rr["kind"], "file": rr["file"]})
    outs.sort(key=lambda o: os.path.getmtime(o["file"]) if os.path.exists(o["file"]) else 0)
    v["outputs"] = outs
    v["jobs"] = [j.view(frm=max(0, len(j.log) - 1)) for j in jobs.running_for(doc["id"])]
    v["external"] = None if v["jobs"] else external.describe(doc)
    v["claude"] = chat.activity(doc)
    v["activity"] = activity(doc, v)
    try:
        v["batches"] = revision_batches(doc)
    except Exception:   # never let the grouping break the project page
        v["batches"] = []
    mine = sorted([j for j in jobs.JOBS.values() if j.project_id == doc["id"]], key=lambda j: j.started or 0)
    v["last_job"] = mine[-1].view(frm=len(mine[-1].log)) if mine else None
    if full:
        v["steps"] = r.steps(doc)
        v["timeline"] = r.timeline_info(doc)
        v["drive"] = tracker.drive_status(doc)
        v["articles"] = tracker.find_articles(doc) if doc["type"] == "gaming" else []
        v["website"] = {"posts": []} if doc["type"] == "gaming" else {"posts": []}
        v["checklist_labels"] = store.CHECKLIST
        v["description_text"] = ""
        d = doc["slots"].get("description")
        if d and os.path.exists(d):
            try:
                v["description_text"] = Path(d).read_text(encoding="utf-8", errors="replace")[:20000]
            except OSError:
                pass
        v["log_tail"] = common.read_report(r.paths(doc).get("log", ""), 60)[-60:] if r.paths(doc).get("log") and os.path.exists(r.paths(doc)["log"]) else []
        if doc["type"] == "gaming":
            v["transcript_lines"] = transcript_lines(r.paths(doc)["words"])
    return v


def transcript_lines(words_path, max_lines=1500):
    words = store.read_json(words_path, [])
    if not words:
        return []
    lines, cur, start = [], [], None
    for w in words:
        if start is None:
            start = w["s"]
        cur.append(w["w"])
        gap_next = False
        if w["w"][-1:] in ".!?" and len(cur) >= 3:
            gap_next = True
        if gap_next or len(cur) >= 24:
            lines.append({"t": round(start, 2), "e": round(w["e"], 2), "text": " ".join(cur)})
            cur, start = [], None
    if cur:
        lines.append({"t": round(start, 2), "e": round(words[-1]["e"], 2), "text": " ".join(cur)})
    return lines[:max_lines]


def all_views():
    return [project_view(d) for d in store.all_projects()]


# ------------------------------------------------------------------ API
_SWEEP = {"on": False}


def _drive_sweep():
    """Drive hand-off + Drive thumbnails for every project, once a minute in the background, so the Projects page never waits
    on Google Drive (was 6-22 s per load). A change shows on the next refresh."""
    while True:
        try:
            for d in store.all_projects():
                tracker.auto_drive(d)
                tracker.auto_thumb(d)
        except Exception:  # noqa: a Drive hiccup never stops the sweep
            traceback.print_exc()
        time.sleep(60)


def api_state(q, body):
    if not _SWEEP["on"] and not os.environ.get("STUDIO_TEST"):   # a test copy on a spare port never writes project docs
        _SWEEP["on"] = True
        threading.Thread(target=_drive_sweep, name="drive-sweep", daemon=True).start()
    docs = store.all_projects()
    views = [project_view(d) for d in docs]
    # videos being worked on first (rendering, then the render line in order, then revisions), the rest by last update
    act = lambda p: p.get("activity") or {}
    views.sort(key=lambda p: (ACTIVE_ORDER.get(act(p).get("state"), 9), act(p).get("pos", 0)))
    role = q.get("_role", "owner")
    if role != "owner":   # his overnight / test experiments are not hers to review (2026-10-27)
        hide = {d["id"] for d in docs if notify.owner_only(d["id"])}
        views = [v for v in views if v.get("id") not in hide]
    s = store.settings()
    # an assistant sees the projects, not the owner's settings (keys, chats, logins)
    shown = s if role == "owner" else {k: s.get(k) for k in ("channels", "phone_url", "machine_name", "port") if k in s}
    return {"settings": shown, "role": role, "by": q.get("_by") if role != "owner" else None,
            "types": store.TYPES, "projects": views, "queue": jobs.gpu_view(),
            "tracker": tracker.summary(docs), "jobs": jobs.all_views(), "checklist": store.CHECKLIST,
            "remote": remote.snapshot(), "machine": store.settings().get("machine_name", "Desktop"),
            "schedule": [e for e in schedule.load() if e.get("state") in ("pending", "started") or e.get("at", "") >= time.strftime("%Y-%m-%d")][-40:],
            "default_machine": store.settings().get("default_machine") or ("Laptop" if remote.workers() or store.settings().get("peers") else store.settings().get("machine_name", "Desktop")),
            "mode": os.environ.get("STUDIO_MODE", "browser"), "stages": tracker.STAGES, "stage_labels": tracker.STAGE_LABEL}


def api_hub(q, body):
    return hub.snapshot(store.all_projects(), max_age=0 if q.get("fresh") else 60)


def api_todo(q, body):
    return todo.snapshot(max_age=0 if q.get("fresh") else 45)


def api_todo_lists(q, body):
    return {"lists": todo.lists()}


def api_todo_add(q, body):
    return todo.add(body.get("title"), body.get("list"), body.get("due"), body.get("notes"))


def api_todo_complete(q, body):
    return todo.complete(body["pid"], body["tid"])


def api_todo_push(q, body):
    return todo.push(body["pid"], body["tid"], body.get("days", 1))



def api_projects_create(q, body):
    title = (body.get("title") or "").strip()
    vtype = body.get("type")
    if (body.get("settings") or {}).get("my_type") or str(vtype or "").startswith("my:"):   # a custom video type (my_style)
        slug = (body.get("settings") or {}).get("my_type") or vtype[3:]
        vtype, mine = mystyle.create_settings(slug)
        body["settings"] = {**(body.get("settings") or {}), **mine}   # the type's style wins over New Project's default options
    if not title or vtype not in RECIPES:
        raise ApiError("title and a valid type are required")
    doc = store.create(title, vtype, body.get("channel", ""), body.get("due", ""))
    doc["settings"] = body.get("settings") or {}
    sync_requests(doc)
    if body.get("stage"):
        doc["stage_manual"] = body["stage"]
    store.save(doc)
    files = dict(body.get("files") or {})
    for slot, src in files.items():
        for p in ([src] if isinstance(src, str) else src or []):
            if p and not os.path.exists(p):
                raise ApiError(f"file not found: {p}")

    def bring_in(doc):
        mains = files.pop("main", None)
        if mains:
            mains = [mains] if isinstance(mains, str) else [m for m in mains if m]
            if len(mains) > 1 and vtype not in ("haul", "short"):   # several recordings in the chosen order -> one joined file (stream copy, no re-encode)
                out = Path(doc["path"]) / ("raw" if vtype != "gaming" else "Edit") / ("source.mp4" if vtype != "gaming" else "joined-recording.mp4")
                out.parent.mkdir(parents=True, exist_ok=True)
                joined = media.concat(mains, out)
                doc["settings"]["joined_from"] = mains
                mains = [joined]
            for mp in (mains if vtype in ("haul", "short") else mains[:1]):   # haul: every phone clip in order; normalise joins them (mixed fps/HDR)
                _ingest(doc, "main", mp)
            if vtype in ("haul", "short") and len(mains) > 1:
                doc["settings"]["joined_from"] = mains
        for slot, src in files.items():
            for p in ([src] if isinstance(src, str) else src):
                if p:
                    _ingest(doc, slot, p)
        doc = store.save(doc)
        auto_build(doc)
        return doc

    # big files (a recording picked from Google Drive's G: drive streams down at ~40 MB/s: 17 GB = 7+ min) are copied in the
    # background: the window closes at once, the card shows "Copying from Google Drive 40%", the build starts when it lands
    allp = [p for v in files.values() for p in ([v] if isinstance(v, str) else v or []) if p]
    if sum(os.path.getsize(p) for p in allp) > 1e9 or any(Path(p).drive.upper() == "G:" for p in allp):
        def worker(d0=doc):
            IMPORTING[d0["id"]] = time.time()
            try:
                bring_in(d0)
            except Exception as e:  # noqa
                traceback.print_exc()
                notify.notify("Could not bring the files in", f"{d0['title']}: {e}", tg=True)
            finally:
                IMPORTING.pop(d0["id"], None)
        IMPORTING[doc["id"]] = time.time()
        threading.Thread(target=worker, daemon=True, name=f"import-{doc['id']}").start()
        return project_view(store.load(doc["id"]), full=True)
    bring_in(doc)
    return project_view(store.load(doc["id"]), full=True)


IMPORTING = {}   # project id -> started, while its files are copied in the background


def api_projects_adopt(q, body):
    doc = store.adopt(body["path"], body.get("type"), body.get("title"))
    if body.get("channel"):
        doc["channel"] = body["channel"]
    if body.get("source"):
        doc["source"] = body["source"]
        doc["checklist"]["footage"] = True
    return project_view(store.save(doc), full=True)


def _doc(q):
    doc = store.load(q["id"])
    if not doc:
        raise ApiError("no such project", 404)
    return doc


def api_project_get(q, body):
    return project_view(_doc(q), full=True)


def api_project_update(q, body):
    doc = _doc(q)
    for k in ("title", "channel", "due", "stage_manual", "published_on", "thumb_brief", "shipped_on", "yt_title"):
        if k in body:
            doc[k] = body[k]
    if body.get("type") and body["type"] != doc["type"]:   # Project details → Change video type (the next build starts over)
        if body["type"] not in store.TYPES:
            raise ApiError("unknown video type")
        doc.setdefault("settings", {})["type_was"] = doc["type"]
        doc["type"] = body["type"]
    if "links" in body:
        doc["links"].update(body["links"])
    if "settings" in body:
        doc["settings"].update(body["settings"])
        for k in [k for k, v in body["settings"].items() if v is None]:
            doc["settings"].pop(k, None)
        if "requests" in body["settings"]:
            sync_requests(doc)
    if "checklist" in body:
        doc["checklist"].update(body["checklist"])
    if "slots" in body:
        doc["slots"].update(body["slots"])
    saved = store.save(doc)
    if (body.get("checklist") or {}).get("approved"):
        save_answer_key(doc)
    return project_view(saved, full=True)


APPROVED_CUTS = r"{{KIT}}/tools\approved_cuts.py"
MUSIC_LOG = r"{{KIT}}/tools\_state\music_log.json"


def music_used(doc):
    """the tracks music_lib picked for this project's last build, by role ({"intro": [...], "main": [...]}): review / phone
    builds don't put them in timeline_info, so the editor's Music panel reads the picker's own log"""
    try:
        home = os.path.normcase(os.path.abspath(doc.get("path") or ""))
        for e in reversed(store.read_json(MUSIC_LOG, []) or []):
            if os.path.normcase(os.path.abspath(e.get("project") or "")) == home:
                return {k: [t for t in (v if isinstance(v, list) else [v]) if t] for k, v in (e.get("roles") or {}).items()}
    except Exception:  # noqa: the panel just says the next build picks
        pass
    return {}


def review_music(doc, offset):
    """a review build's songs in DRAFT time, from its own report ("- Beats:" lines + "Segment transitions ... intro -> review at
    0:27.5 ...", main-edit times) and the intro's intro_music.json: [{"part", "track", "s", "e"}] for the editor's Music row"""
    try:
        home = Path(doc.get("path") or "")
        rep = home / "output" / "report.md"
        if not rep.exists():
            return []
        text = rep.read_text(encoding="utf-8", errors="replace")
        beats = re.findall(r"^\s*-\s*(Intro|Product review|Review|Showcase|Outro|Body|Main)\s*:\s*(.+?\.(?:mp3|wav|m4a|flac))\s*$", text, re.M | re.I)
        if not beats:
            return []
        at = [media.parse_t(m) for m in re.findall(r"->\s*\w+\s+at\s+(\d+:\d+(?:\.\d+)?)", text)]
        main_len = sum(abs(b - a) for a, b in (recipe(doc["type"]).timeline_info(doc).get("keep") or []))
        bounds = [0.0] + at + [main_len]
        out = []
        im = store.read_json(home / "intro" / "build" / "intro_music.json", None)
        if offset and isinstance(im, dict) and im.get("track"):
            out.append({"part": "opening", "track": im["track"], "s": 0.0, "e": round(offset, 2)})
        for i, (part, name) in enumerate(beats):
            f = home / "work" / "music" / name.strip()
            s, e = bounds[min(i, len(bounds) - 1)], bounds[min(i + 1, len(bounds) - 1)]
            out.append({"part": part.lower(), "track": str(f) if f.exists() else name.strip(), "s": round(offset + s, 2), "e": round(offset + e, 2)})
        return out
    except Exception:  # noqa: the row just says the next draft picks
        return []


def save_answer_key(doc):
    """approved = this edit's cut list becomes the answer key for its footage (approved_cuts.py, user 2026-10-26: two
    laptop rebuilds of the approved prada glasses brought back five takes it had cut). Any later build of the same
    recording, under any name, starts from it and stops before rendering if it drifts."""
    def run():
        try:
            subprocess.run([sys.executable, "-X", "utf8", APPROVED_CUTS, "approve", str(store.project_path(doc["id"])), "--force"],
                           capture_output=True, timeout=300, creationflags=0x08000000 if os.name == "nt" else 0)
        except Exception:  # noqa: never blocks an approval
            traceback.print_exc()
    threading.Thread(target=run, daemon=True).start()


def api_project_rename(q, body):
    doc = _doc(q)
    if jobs.running_for(doc["id"]) or external.describe(doc):
        raise ApiError("a build is running on this project; rename it when the build is done")
    try:
        return store.rename_project(doc["id"], body.get("title", ""), rename_folder=body.get("folder", True))
    except (ValueError, OSError) as e:
        raise ApiError(f"could not rename: {e}")


def api_project_delete(q, body):
    doc = _doc(q)
    store.unregister(doc["id"])   # only forgets the project; files stay where they are
    return {"ok": True}


def _ingest(doc, slot, src):
    src = str(src)
    if not os.path.exists(src):
        raise ApiError(f"file not found: {src}")
    r = recipe(doc["type"])
    if slot == "thumbnail":
        dest = store.copy_into(src, r.paths(doc).get("thumb_dir") or Path(doc["path"]) / "Thumbnail")
        doc["slots"]["thumbnail"] = str(dest)
        doc["checklist"]["thumbnail"] = True
        return str(dest)
    if slot == "thumb_ref":
        dest = store.copy_into(src, Path(r.paths(doc).get("thumb_dir") or Path(doc["path"]) / "Thumbnail") / "refs")
        doc["slots"]["thumb_refs"] = sorted(set(doc["slots"].get("thumb_refs", []) + [str(dest)]))
        return str(dest)
    if slot == "description":
        if Path(src).suffix.lower() == ".txt":
            doc["slots"]["description"] = src if Path(src).parent == Path(doc["path"]) else str(store.copy_into(src, Path(doc["path"]), "youtube-description.txt"))
            doc["checklist"]["description"] = True
            return doc["slots"]["description"]
        raise ApiError("the description must be a .txt file")
    if slot == "article":
        doc["slots"]["articles"] = sorted(set(doc["slots"].get("articles", []) + [src]))
        return src
    if slot == "music":
        return src
    dest = r.ingest(doc, slot, src)
    if dest is None:
        raise ApiError(f"slot {slot!r} is not used by {doc['type']} projects")
    return dest


def api_project_slot(q, body):
    doc = _doc(q)
    files = body.get("files") or ([body["path"]] if body.get("path") else [])
    done = [_ingest(doc, body["slot"], f) for f in files]
    doc = store.save(doc)
    if body["slot"] == "main":
        auto_build(doc)
    return {"files": done, "project": project_view(store.load(doc["id"]), full=True)}


def api_project_slot_remove(q, body):
    doc = _doc(q)
    slot, path = body["slot"], body.get("path", "")
    if slot in ("broll", "articles", "thumb_refs"):
        doc["slots"][slot] = [p for p in doc["slots"].get(slot, []) if p != path]
    elif slot == "main":
        doc["source"] = ""
    else:
        doc["slots"][slot] = ""
    return project_view(store.save(doc), full=True)


def next_overnight():
    """when tonight's batch starts (settings.overnight_at, default 01:00): later today, or now when the night has begun"""
    from datetime import datetime, timedelta
    hh, mm = (str(store.settings().get("overnight_at") or "01:00") + ":00").split(":")[:2]
    now = datetime.now()
    t = now.replace(hour=int(hh) % 24, minute=int(mm) % 60, second=0, microsecond=0)
    if t <= now:
        t = now if now.hour < 7 or now - t < timedelta(hours=6) else t + timedelta(days=1)   # already night: start now
    return t.strftime("%Y-%m-%d %H:%M")


def defer_build(doc, action, body):
    """Queue page "When should videos be made?" (2026-10-29): the UI sends when = "now" | "tonight" | "YYYY-MM-DD HH:MM".
    Anything but now goes on the schedule (schedule.py starts it; renders still go one at a time). No `when` = build now, so
    the revision AI's own rebuilds and older buttons are never pushed to tonight."""
    when = (body or {}).get("when")
    if not when or when == "now":
        return None
    at = next_overnight() if when == "tonight" else str(when).replace("T", " ")[:16]
    try:
        time.strptime(at, "%Y-%m-%d %H:%M")
    except ValueError:
        raise ApiError("pick a date and time")
    e = schedule.add(doc, at, schedule.me(), action)
    return {"scheduled": e, "at": at, "mode": "scheduled"}


def api_schedule_when(q, body):
    """Queue page per-item When: {"id": schedule entry | "job": waiting job id, "when": "now" | "tonight" | "YYYY-MM-DD HH:MM"}"""
    when = body.get("when") or "now"
    if body.get("job"):
        j = jobs.JOBS.get(body["job"])
        if not j or j.status not in ("queued", "running"):
            raise ApiError("that build is not waiting any more")
        if when == "now":
            jobs.move(j.id, "top")
            return {"ok": True}
        doc = store.load(j.project_id)
        action = (j.title or "").split(": ")[-1] or "draft"
        j.cancel()
        return defer_build(doc, action if action in ("draft", "final", "intro", "revise") else "draft", {"when": when})
    e = schedule.get(body.get("id"))
    if not e or e.get("state") != "pending":
        raise ApiError("that item is not waiting any more")
    if when == "now":
        e["at"] = time.strftime("%Y-%m-%d %H:%M")
    else:
        e["at"] = next_overnight() if when == "tonight" else str(when).replace("T", " ")[:16]
    return {"item": schedule.upsert(e)}


def api_project_run(q, body):
    doc = _doc(q)
    d = defer_build(doc, body.get("action", "draft"), body) if body.get("action", "draft") in ("draft", "final", "intro") else None
    if d:
        return d
    if body.get("intro") == "rebuild":   # intro lock (2026-10-24): this build may re-make the intro
        doc["intro_rebuild"] = True
    # ...also when the revision run behind this build has an open note about the intro: a Claude Code chat calls this API
    # itself and never passes through api_rebuild_notes (watchb 2026-10-24: 5 intro notes, only a style change unlocked it)
    run = chat.load(doc).get("run") or {}
    if run.get("state") == "running" and not doc.get("intro_rebuild"):
        idur = intro_len(doc)
        if idur and any(note_in_intro(n, idur) for n in doc.get("notes", [])
                        if n.get("nid") in run.get("nids", []) and n.get("status") not in ("applied", "failed")):
            doc["intro_rebuild"] = True
    job = start_build(doc, body.get("action", "draft"), force=bool(body.get("force")), machine=body.get("machine"))
    out = {"job": job.view()}
    # one build per revision batch (2026-10-24): the revision AI reads this reply, so it is told when it keeps rebuilding
    run = chat.load(doc).get("run") or {}
    if run.get("state") == "running":
        n = sum(1 for b in doc.get("builds", []) if b.get("when", "") >= run.get("started", "~")) + 1
        if n >= 2:
            out["warning"] = (f"This is build {n} of this revision batch. One build per batch: check the draft with frames "
                              "at each note's time instead of rebuilding; rebuild only for a note it shows still wrong.")
    return out


def auto_build(doc):
    """A project with footage and no draft yet builds itself (the whole point of dropping files in)."""
    if not doc.get("source") or jobs.running_for(doc["id"]):
        return None
    if any(o["kind"] in ("draft", "final", "trimmed") for o in recipe(doc["type"]).outputs(doc)):
        return None
    # New Project "First build" (2026-10-25): "hold" = not yet; a time = put it on the schedule (on settings.machine);
    # nothing = build now (on settings.machine, laptop first)
    at = (doc.get("settings") or {}).get("build_at")
    if at == "hold":
        return None
    if not at and store.settings().get("build_mode") == "overnight":   # Queue page: "Overnight" = new videos wait for tonight
        if not any(e.get("project_id") == doc["id"] and e.get("state") == "pending" for e in schedule.load()):
            schedule.add(doc, next_overnight(), schedule.me(), "draft")
        return None
    if at:
        try:
            if time.strptime(at, "%Y-%m-%d %H:%M") > time.localtime():
                if not any(e.get("project_id") == doc["id"] and e.get("state") == "pending" for e in schedule.load()):
                    schedule.add(doc, at, (doc.get("settings") or {}).get("machine") or store.settings().get("default_machine") or "Laptop")
                    if remote.workers() and doc["type"] != "gaming":
                        threading.Thread(target=ship_to_workers, args=(doc,), daemon=True).start()
                return None
        except ValueError:
            pass
    try:
        return start_build(doc, "draft")
    except Exception:
        return None


def find_intro(doc):
    """The intro made for THIS video when its slot is empty (user 2026-10-22: Top 10 Servers had an intro in the files that
    never got connected; "every video gets its own intro if it has one"). 1) a render in the project's Intro\\ folder,
    2) a HyperFrames intro project whose name words all appear in the title (servers-intro-top10 <-> "Top 10 Minecraft
    Servers"; realms-intro-oct never matches a servers video). None = no intro."""
    p = Path(doc["path"])
    vids = [f for f in (p / "Intro").glob("*.mp4") if "_check" not in f.stem] if (p / "Intro").is_dir() else []
    if vids:
        return str(max(vids, key=lambda f: f.stat().st_mtime))
    norm = lambda t: set(re.sub(r"top\s+(\d+)", r"top\1", t.lower()).replace("-", " ").split())
    title = norm(doc.get("title") or p.name)
    hf = Path(r"{{KIT}}/assets\Graphics\HyperFrames")
    best = None
    for d in (hf.iterdir() if hf.is_dir() else []):
        words = norm(d.name) - {"intro"}
        if "intro" not in d.name.lower() or not words or not words <= title:
            continue
        renders = [f for f in d.glob("**/*.mp4") if "node_modules" not in f.parts and "_check" not in str(f)]
        if renders:
            f = max(renders, key=lambda f: f.stat().st_mtime)
            if not best or len(words) > best[0]:
                best = (len(words), str(f))
    return best[1] if best else None


REMOTE_ACTIONS = ("draft", "final", "all", "revise", "intro")


def pick_machine(doc, machine=None, action="draft"):
    """Where this build runs (laptop first, 2026-10-25): a worker dict, or None = here.
    machine (per build) > settings.machine (per project) > settings.default_machine ("Laptop"). "here"/"local" = this
    machine. "both" = the laptop unless it is busy and this machine is free. Gaming stays here (its 11 GB of assets live
    on the desktop). A worker that can't be reached = build here (fallback)."""
    ws = remote.workers()
    if action not in REMOTE_ACTIONS or not ws or doc["type"] == "gaming":
        return None
    want = str(machine or (doc.get("settings") or {}).get("machine") or store.settings().get("default_machine") or "Laptop").lower()
    if want in ("here", "local", remote.me().lower()):
        return None
    if want == "both":
        w = ws[0]
        if not remote.online(w["name"]):
            return None
        here_busy = any(j.status in ("running", "queued") for j in jobs.JOBS.values())
        return None if remote.busy(w["name"]) and not here_busy else w
    w = remote.worker(want)
    return w if w and remote.online(w["name"]) else None


def remote_step(doc, action, force, w):
    # phases (remote_build.py's own lines mark them, "(N% sent/built/back)" moves the bar): the Queue shows "Uploading to
    # Laptop 47%" instead of a silent "Building on Laptop" while the footage crosses the Wi-Fi (user 2026-10-26)
    n = w["name"]
    phases = [(None, f"Uploading to {n}", f"Uploading to {n}", 0.3, None),
              (r"== building on ", f"Building on {n}", f"Building on {n}", 4.0, None),
              (r"== .+ finished:", f"Bringing back from {n}", f"Bringing back from {n}", 0.2, None)]
    return {"id": "remote", "label": f"Building on {w['name']}", "cwd": doc["path"], "light": True, "force": True, "no_retry": True,
            "phases": phases, "stages": [ph[2] for ph in phases],
            "cmd": [common.python(), "-X", "utf8", str(Path(__file__).parent / "tools" / "remote_build.py"), doc["id"], action, w["name"]]
            + (["--force"] if force else [])
            # the intro unlock goes along: start_build pops it right after this, so the worker never saw it and kept the
            # old intro (remote test prada 2 2026-10-26: "intro: kept as it is (locked ...)" after {"intro": "rebuild"})
            + (["--intro-rebuild"] if doc.get("intro_rebuild") else [])}


def outside_files(doc):
    """files a build reads from outside the project folder (an intro VO in Documents\\Audacity, a recording in an OBS folder)"""
    home = str(Path(doc["path"]))
    out = []
    for v in list((doc.get("slots") or {}).values()) + [doc.get("source")]:
        for p in (v if isinstance(v, list) else [v]):
            if isinstance(p, str) and len(p) > 3 and p[1:3] == ":\\" and not p.startswith(home) and os.path.isfile(p):
                out.append(p)
    return out


REMOTE_PULLED = store.DATA / "remote_pulled.json"


def pull_remote_results(w, wjobs):
    """after each poll of a worker: a build that ran THERE without our "Building on" step (a scheduled one, a fallback while
    this machine was off) and has ended -> bring its files back and log it here, so the draft shows up for review"""
    pulled = set(store.read_json(REMOTE_PULLED, []) or [])
    changed = False
    for j in wjobs:
        if j.get("status") not in ("done", "failed") or j["id"] in pulled:
            continue
        doc = store.load(j.get("project_id") or "")
        rb = store.read_json(Path(doc["path"]) / "work" / "remote_build.json", {}) if doc else {}
        if not doc or rb.get("job") == j["id"] or (j.get("ended") or 0) < time.time() - 2 * 86400:
            pulled.add(j["id"])   # not ours, our own remote step already did it, or too old to matter
            changed = True
            continue
        if jobs.running_for(doc["id"]):
            continue   # our "Building on" step is still bringing it back
        try:
            n, size = remote.sync_from(w, doc["path"])
        except Exception as e:  # noqa: try again next poll
            print("pull remote results:", e, flush=True)
            continue
        pulled.add(j["id"])
        changed = True
        if not n:
            continue   # nothing new: already brought back (tools/laptop_pull.py, an earlier poll) -> no second "Draft ready"
        d = store.load(doc["id"])
        secs = round((j.get("ended") or time.time()) - (j.get("started") or time.time()))
        d.setdefault("builds", []).append({"action": "draft", "when": store.now(), "secs": secs, "status": j["status"],
                                           "machine": w["name"], "minutes": j.get("minutes"),
                                           "steps": [{"id": s.get("id"), "label": s.get("label"), "secs": (j.get("step_secs") or {}).get(s.get("id")),
                                                      "status": s.get("status")} for s in j.get("steps", [])]})
        store.save(d)
        if j["status"] == "done":
            notify.notify("Draft ready to review", f"{d['title']} · built on {w['name']} in {round(secs / 60)} min. Open it in Review + notes.", pid=d["id"])
        else:
            notify.notify("Build failed", f"{d['title']} on {w['name']}: {j.get('error') or 'see its log'}", tg=True)
    if changed:
        store.write_json(REMOTE_PULLED, sorted(pulled)[-500:])


def start_build(doc, action="draft", force=False, pre=None, machine=None):
    if jobs.running_for(doc["id"]):
        raise ApiError("a job is already running for this project")
    r = recipe(doc["type"])
    try:
        r.apply_notes(doc)
    except Exception as e:  # noqa
        pass
    if doc["type"] == "gaming" and not (doc.get("slots") or {}).get("intro"):
        found = find_intro(doc)
        if found:
            doc.setdefault("slots", {})["intro"] = found
    store.save(doc)
    w = pick_machine(doc, machine, action)
    steps = (pre or []) + ([remote_step(doc, action, force, w)] if w else r.job_steps(doc, action, force=force))
    # intro lock (2026-10-24): the unlock is used by this one build; a failed build puts it back (on_done)
    unlock = bool(doc.pop("intro_rebuild", None))
    if unlock:
        store.save(doc)
    log_file = r.paths(doc).get("log")
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    def _snapshot_draft(d, r, keep=15, status="done"):
        """Every built draft is kept as the user saw it (2026-10-23, self-review scoring: rebuilds overwrote the drafts his
        notes were written on, so they could not be used as test cases): work/drafts/<when>/ = the cut list, the report,
        the draft video and the notes open at that moment. The last `keep` per project.
        2026-10-25 (user: "we should be saving drafts so we can study what's going on"): also drafts that FAILED a check
        (the audit), the phone cut list (work/cuts.json: Uber's old drafts could not be replayed without it), the audit /
        QC / intro picks, and one line per draft in the study log."""
        try:
            p = Path(d["path"])
            snap = p / "work" / "drafts" / time.strftime("%Y%m%d-%H%M%S")
            snap.mkdir(parents=True, exist_ok=True)
            for f in (p / "work" / "timeline.json", p / "output" / "report.md", p / "work" / "cuts.json",
                      p / "work" / "draft_audit.json", p / "output" / "draft_audit.md", p / "output" / "intro_report.txt",
                      p / "edit" / "intro_footage.json", p / "edit" / "layout.json", p / "work" / "seams.md"):
                if f.exists():
                    shutil.copy2(f, snap / f.name)
            study_log({"event": "draft", "project": d.get("title"), "id": d.get("id"), "type": d.get("type"),
                       "status": status, "snapshot": str(snap),
                       "audit": [{k: x.get(k) for k in ("kind", "draft", "why", "phrase")} for x in
                                 json.loads((snap / "draft_audit.json").read_text(encoding="utf-8"))]
                       if (snap / "draft_audit.json").exists() else None})
            for o in r.outputs(d):
                if o["kind"] == "draft" and o.get("file") and Path(o["file"]).exists() and Path(o["file"]).stat().st_size < 300e6:
                    shutil.copy2(o["file"], snap / Path(o["file"]).name)
            (snap / "notes.json").write_text(json.dumps(d.get("notes", []), indent=1), encoding="utf-8")
            for old in sorted((p / "work" / "drafts").iterdir())[:-keep]:
                shutil.rmtree(old, ignore_errors=True)
        except Exception:  # noqa: a snapshot never fails a build
            traceback.print_exc()

    def on_done(job):
        d = store.load(doc["id"])
        if not d:
            return
        if job.status == "done":
            for o in r.outputs(d):
                # a screen-recording / trim-only edit ("- EDIT.mp4", "- TRIMMED.mp4") IS the draft (chime sign up bonus
                # 2026-10-23: "Draft ready" went out but the project never reached Ready for your review)
                if (action in ("draft", "all", "revise", "intro") and o["kind"] in ("draft", "trimmed")) or (action == "final" and o["kind"] == "final"):
                    store.add_render(d, o["file"], "draft" if o["kind"] == "trimmed" else o["kind"])
            if action in ("draft", "all", "revise", "intro"):
                _snapshot_draft(d, r)
        elif action in ("draft", "all", "revise", "intro") and job.step_status.get("audit") == "failed":
            _snapshot_draft(d, r, status="failed audit")   # the draft exists, a check said no: still worth studying
        if job.status == "done":
            if action in ("draft", "final"):
                began = time.strftime("%Y-%m-%d %H:%M", time.localtime(job.created))   # notes were read when it was queued
                for n in d["notes"]:   # only notes that were there when the build started made it into this build
                    if n.get("kind") in ("cut", "protect", "broll") and "raw0" in n and n.get("added", "") <= began:
                        n["done"] = True
                        n["status"] = "applied"
                        n["applied_in"] = action
        secs = round((job.ended or time.time()) - (job.started or time.time()) - job.wait_s)   # time in the render queue is not build time
        d.setdefault("builds", []).append({"action": action, "when": store.now(), "secs": secs, "status": job.status, "minutes": round(job.minutes, 1),
                                           "waited": round(job.wait_s),
                                           "steps": [{"id": st["id"], "label": st["label"], "secs": job.step_secs.get(st["id"]), "status": job.step_status.get(st["id"])} for st in job.steps]})
        del d["builds"][:-30]
        if unlock and job.status != "done":
            d["intro_rebuild"] = True
        store.save(d)
        mins = round(secs / 60)
        if action in ("draft", "all", "revise", "intro") and chat.run_active(d):
            return   # a revision run's build: chat.check_run sends the one "Revisions done" when it is truly finished
        if job.status == "done" and action in ("draft", "all") and send_requests(d):
            return   # special requests waiting: the AI applies them first, "Revisions done" is the one message
        failed = [k for k, v in (job.step_status or {}).items() if v == "failed"]
        if action in ("draft", "all") and failed == ["audit"] and send_audit(d):
            return   # the draft audit heard real problems: the AI fixes them before he sees the draft
        # the time he cares about: from pressing Build to the video sitting in Ready for your review, the wait in the render
        # line included (user 2026-10-23: "how long it takes to get there from the initial build")
        total = round(((job.ended or time.time()) - job.created) / 60)
        took = f"{total} min from start to ready (waited {round(job.wait_s / 60)} min in line, built in {mins} min)"
        ready = tracker.stage(d) == "review"
        if job.status == "done" and action in ("draft", "all", "revise", "intro") and not ready:
            notify.toast("Build finished", f"{d['title']}: done, but it is not in Ready for your review ({tracker.stage(d)}). Check the Build tab.")
        elif job.status == "done" and action == "intro":
            notify.notify("Revised intro ready", f"{d['title']} · {took}. Only the intro was rebuilt; the rest of the video is unchanged.", pid=d["id"])
        elif job.status == "done" and action == "revise":
            notify.notify("Revised draft ready", f"{d['title']} · {took}. Watch it in Review + notes; the previous one is kept as DRAFT vN.", pid=d["id"])
        elif job.status == "done" and action in ("draft", "all"):
            notify.notify("Draft ready to review", f"{d['title']} · {took}. Open it in Review + notes.", pid=d["id"])
        elif job.status == "done" and action == "final":
            notify.notify("FINAL rendered", f"{d['title']} · {mins} min. Check it, then send it to Drive.")
        elif job.status == "failed":
            notify.notify("Build failed", f"{d['title']}: {job.error}", tg=True)

    info = media.probe(doc["source"]) if doc.get("source") else None
    minutes = (info["duration"] / 60) if info else 0
    job = jobs.Job(f"{doc['title']}: {action}", doc["id"], steps, log_file=str(log_file) if log_file else None, on_done=on_done,
                   kind=doc["type"], minutes=minutes)
    est = sum(job.weights.values())
    if action == "revise":
        def after_revise(j, doc=doc):
            revs = store.read_json(Path(doc["path"]) / "work" / "revisions.json", []) or []
            v = revs[-1] if revs else {}
            n_cuts, other = len(v.get("cuts") or []), v.get("other") or []
            notify.notify(f"Revision {v.get('n', '')}: notes read", f"{doc['title']} · {n_cuts} cuts placed"
                          + (f", {len(other)} need a hand fix" if other else "") + ". Rebuilding the draft next, after any video already rendering (Transcript → Trim → Privacy → Layout → Graphics → Main video → Join + QC).")
        for st in steps:
            if st["id"] == "revise":
                st["after"] = after_revise
        notify.notify("Revision started", f"{doc['title']} · step 1: Opus turns your notes into cuts (~1 min), step 2: the draft rebuilds (~{max(1, round(est / 60))} min). You get a message after each.")
        jobs.start(job)
        return job
    busy_gpu = jobs.queue_on() and (jobs.GPU["holder"] or jobs.waiting() or jobs._outside_build())
    jobs.start(job)
    if busy_gpu:
        notify.toast("Queued to render", f"{doc['title']} · {action} · #{len(jobs.waiting()) or 1} in line, starts on its own · about {max(1, round(est / 60))} min once it runs")
    else:
        notify.toast("Build started", f"{doc['title']} · {action} · about {max(1, round(est / 60))} min")
    return job


RULE_RE = re.compile(r"\b(always|never|every (single )?(video|time)|from now on|going forward|in general|all (my |the |of the )?videos|"
                     r"again|keeps? happening|for good|as a rule|add (this|that|these|it|them) as (a )?rules?|make (this|it) a rule|"
                     r"like i (said|mentioned)|every one of)\b", re.I)
ONE_RE = re.compile(r"\b(personal preference|preferential|just (for )?this (one|video)|one[- ]time|this is (so |like )?rare|"
                    r"only (for|in) this (one|video)|this time)\b", re.I)
NOTE_STOP = set("the a an and or but so to of in on at for with this that these those it its is are was were be been i im my me you "
                "your we our they them there here just like really actually kind sort going gonna want need should could would can "
                "video videos thing things some more less too very also then than when what where which who how".split())


def note_scope(text, doc):
    """Note sorting (user 2026-10-26: notes turned into shared rules "messed up our whole system"). "video" = a preference
    or a rare moment, fixed ONLY in this project (raw/config.json, raw/studio_extra.json ...). "rule" = he says always /
    never / again, or the same note came up on another video: may change the shared pipeline and then has to pass the
    rule gate (_tools/regress/rule_gate.py). Returns (scope, why)."""
    t = text or ""
    m = ONE_RE.search(t)
    if m:
        return "video", f"he said '{m.group(0)}'"
    m = RULE_RE.search(t)
    if m:
        return "rule", f"he said '{m.group(0)}'"
    words = {w for w in re.findall(r"[a-z][a-z']{3,}", t.lower()) if w not in NOTE_STOP}
    if len(words) >= 3:
        for other in store.all_projects():
            if other.get("id") == doc.get("id"):
                continue
            for n in other.get("notes", []) or []:
                ow = {w for w in re.findall(r"[a-z][a-z']{3,}", (n.get("text") or "").lower()) if w not in NOTE_STOP}
                shared = words & ow
                if len(shared) >= 3 and len(shared) / max(1, len(words | ow)) >= 0.35:
                    return "rule", f"same note on '{other.get('title')}' ({', '.join(sorted(shared)[:4])})"
    return "video", "one video until he says always / again or it comes up on another video"


def api_project_notes(q, body):
    doc = _doc(q)
    if body.get("remove") is not None:
        idx = int(body["remove"])
        if 0 <= idx < len(doc["notes"]):
            doc["notes"].pop(idx)
    for bn in body.get("notes") or []:   # bulk raw-time notes (e.g. "cut all fillers")
        doc["notes"].append({"kind": bn.get("kind", "cut"), "raw0": round(float(bn["raw0"]), 3), "raw1": round(float(bn["raw1"]), 3),
                             "text": bn.get("text") or "cut (bulk)", "added": store.now(), "from": "editor"})
    if body.get("raw0") is not None and body.get("kind") in ("cut", "protect", "broll"):
        n = {"kind": body["kind"], "raw0": round(float(body["raw0"]), 3), "raw1": round(float(body["raw1"]), 3), "text": body.get("text") or f"{body['kind']} (editor selection)",
             "added": store.now(), "from": "editor"}
        if body.get("clip"):
            n["clip"] = body["clip"]
        doc["notes"].append(n)
    elif body.get("text"):
        body["text"] = speech.normalize_times(body["text"])
        n = common.parse_note(body["text"])
        n["added"] = store.now()
        n["kind"] = body.get("kind") or n["kind"]
        try:
            if body.get("applies") in ("rule", "video"):
                n["applies"], n["applies_why"] = body["applies"], "set by hand"
            else:
                n["applies"], n["applies_why"] = note_scope(body["text"], doc)
        except Exception as e:  # noqa: sorting never blocks a note
            n["applies"], n["applies_why"] = "video", f"sorting failed ({type(e).__name__})"
        doc["notes"].append(n)
        n.setdefault("nid", uuid.uuid4().hex[:6])
        if (doc.get("settings") or {}).get("my_type"):   # the type learns it as a category rule (my_style, in the background)
            mystyle.learn_async(dict(doc), dict(n))
        mystyle.record_rule_note(doc, n)
        try:
            recipe(doc["type"]).apply_notes(doc)
        except Exception as e:  # noqa
            n["unresolved"] = f"could not resolve: {e}"
    if body.get("applies_nid") is not None:   # the user flips a note between "this video" and "rule"
        for n in doc["notes"]:
            if n.get("nid") == str(body["applies_nid"]):
                n["applies"] = "rule" if body.get("value") == "rule" else "video"
                n["applies_why"] = "set by hand"
    if body.get("toggle") is not None:   # "run again": back to pending so the next rebuild applies it again
        idx = int(body["toggle"])
        n = doc["notes"][idx]
        n["done"] = not n.get("done")
        n["status"] = "applied" if n["done"] else "pending"
        n.pop("how", None)
    if body.get("status") is not None:   # Claude reports back per revision: {"status": nid, "value": "applied"|"failed", "how": "..."}
        for n in doc["notes"]:
            if n.get("nid") == str(body["status"]):
                n["status"] = body.get("value") or "applied"
                n["done"] = n["status"] == "applied"
                n["applied_in"] = "claude"
                if body.get("how"):
                    n["how"] = str(body["how"])[:400]
                study_log({"event": "note", "project": doc.get("title"), "id": doc.get("id"), "type": doc.get("type"),
                           "nid": n.get("nid"), "from": n.get("from") or "user", "batch": n.get("batch"),
                           "draft_t": n.get("t0"), "text": n.get("text"), "status": n["status"], "how": n.get("how")})
    for n in doc["notes"]:
        n.setdefault("nid", uuid.uuid4().hex[:6])
    return project_view(store.save(doc), full=True)


def revision_batches(doc):
    """The notes grouped by the round they were sent in (user 2026-10-23: "if I give 5 revisions it'll be batch 1, then batch 2
    would have 2"). Notes stamped with "batch" when sent keep it; older notes are grouped by the builds between them: a done
    draft build between two notes starts a new batch. A note nobody has sent yet (pending, no build since) is "next".
    Each batch: n, note indexes, sent, status (working | open | done | next), the draft it built (n-th done draft, when)."""
    notes = doc.get("notes", [])
    builds = [b for b in doc.get("builds", []) if b.get("action") in ("draft", "revise", "all", "final", "intro") and b.get("status") == "done"]
    whens = [b.get("when", "") for b in builds]
    label, c = [], 0
    for b in builds:   # "draft 4" = the 4th draft built; finals are just "final"
        if b.get("action") == "final":
            label.append("final")
        else:
            c += 1
            label.append(f"draft {c}" + (" · intro only" if b.get("action") == "intro" else ""))
    groups, cur, last_added = {}, 0, None
    for i, n in enumerate(notes):
        added = n.get("added", "")
        if n.get("batch"):
            k = int(n["batch"])
        elif n.get("status") in (None, "pending") and not n.get("done") and not any(w > added for w in whens):
            k = "next"
        else:
            if cur == 0 or (last_added is not None and any(last_added < w <= added for w in whens)):
                cur += 1
            k = cur
            last_added = added
        if isinstance(k, int):
            cur = max(cur, k)
        groups.setdefault(k, []).append(i)
    nums = sorted(k for k in groups if k != "next")
    out = []
    for j, k in enumerate(nums):
        idx = groups[k]
        sent = min((notes[i].get("sent") or notes[i].get("added", "")) for i in idx)
        nxt = min((notes[i].get("sent") or notes[i].get("added", "")) for i in groups[nums[j + 1]]) if j + 1 < len(nums) else "9999"
        mine = [(label[c], w) for c, w in enumerate(whens) if sent <= w < nxt]
        sts = [noteStatus_py(notes[i]) for i in idx]
        status = ("working" if "claude" in sts else "open" if any(s in ("failed", "check", "partly", "pending") for s in sts) else "done")
        if status == "open" and not mine and all(s == "pending" for s in sts):
            status = "working"   # exact notes sent with a rebuild that hasn't finished yet
        out.append({"n": k, "notes": idx, "sent": sent, "last_added": max(notes[i].get("added", "") for i in idx), "status": status,
                    "open": sum(s in ("failed", "check", "partly", "pending") for s in sts) if status != "working" else 0,
                    "statuses": sts, "draft": {"label": mine[-1][0], "when": mine[-1][1]} if mine else None})
    if "next" in groups:
        out.append({"n": "next", "notes": groups["next"], "sent": "", "status": "next", "open": len(groups["next"]), "draft": None,
                    "statuses": [noteStatus_py(notes[i]) for i in groups["next"]]})
    return out[::-1]   # newest first


def noteStatus_py(n):
    st = n.get("status") or ("applied" if n.get("done") else "pending")
    if st == "applied" and re.search(r"\bnot done\b", n.get("how") or "", re.I):
        return "partly"   # Claude reported part of it as not done ("NOT done: no on-feet clip exists")
    return st


def stamp_batch(doc, notes):
    """the notes being sent now are one new batch"""
    if not notes:
        return None
    sending = {id(n) for n in notes}
    before = dict(doc, notes=[n for n in doc.get("notes", []) if id(n) not in sending])   # the batches that existed already
    done = [b["n"] for b in revision_batches(before) if b["n"] != "next"]
    k = (max(done) if done else 0) + 1
    for n in notes:
        if not n.get("batch"):
            n["batch"], n["sent"] = k, store.now()
    return k


# Special requests (user 2026-10-23: "notes ahead of time so it saves time in revision ... universal, not just the intro":
# "#1 Mario server: Mario music", "a motion graphic whenever I say MC Realm Hub"). settings.requests is free text from New
# Project / Project settings; every line becomes a text revision note (from "request"). After the first draft builds they go to
# the revision AI as one batch by themselves (on_done -> send_requests), so the first message he gets is the draft WITH them.
# The intro builders also pass the text to the intro director on the first build.
def sync_requests(doc):
    """settings.requests -> request notes. Notes already sent keep their history; unsent ones follow the text."""
    lines = [x.strip(" -•\t") for x in (doc.get("settings", {}).get("requests") or "").splitlines()]
    lines = [x for x in lines if x]
    sent = {n["text"] for n in doc.get("notes", []) if n.get("from") == "request" and n.get("sent")}
    doc["notes"] = [n for n in doc.get("notes", []) if not (n.get("from") == "request" and not n.get("sent"))]
    for t in lines:
        if t not in sent:
            doc["notes"].append({"kind": "text", "text": t, "added": store.now(), "from": "request", "status": "pending",
                                 "nid": uuid.uuid4().hex[:6]})
    return doc


def pending_requests(doc):
    return [n for n in doc.get("notes", []) if n.get("from") == "request" and not n.get("sent") and not n.get("done")]


def send_requests(doc):
    """first draft done + special requests waiting = hand them to the revision AI now (same path as Send revisions)"""
    if (doc.get("settings") or {}).get("requests") and not any(n.get("from") == "request" for n in doc.get("notes", [])):
        doc = store.save(sync_requests(doc))   # typed in before this code was loaded: make the notes now
    n = len(pending_requests(doc))
    if not n or chat.run_active(doc) or jobs.running_for(doc["id"]):
        return False
    try:
        api_rebuild_notes({"id": doc["id"]}, {})
    except Exception:  # noqa: the draft is still there; he can send them by hand
        traceback.print_exc()
        return False
    notify.notify("First draft built: applying your special requests",
                  f"{doc['title']} · {n} request(s) went to the AI. You get one message when the draft has them.")
    return True


STUDY_LOG = Path(r"{{KIT}}/tools\regress\study_log.jsonl")


def study_log(entry):
    """one line per draft built and per revision note reported (user 2026-10-25: "make a log of this stuff"), across every
    project and type: what the checks found, what he asked for, how it was fixed. Read it to find repeat problems."""
    try:
        entry = {"when": store.now(), **entry}
        with STUDY_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:  # noqa: logging never breaks the app
        traceback.print_exc()


def send_audit(doc):
    """A first draft that fails ONLY its draft audit (draft_audit.py: retakes left in, words cut off / doubled at a cut,
    stranded scraps) goes straight to the revision AI with those problems as notes, once per project. 2026-10-25: 11 of
    36 notes on four test videos were cut joins he had to find himself; the top 5 reselling draft sat failed with 9."""
    # 2 rounds: the second carries only problems not sent before (reselling spring 2026-10-25: the first round's fixes
    # rebuilt fine, then the newer self-talk / stub checks found 5 more that one round could never send)
    if doc.get("audit_rounds", 0) >= 2 or chat.run_active(doc) or jobs.running_for(doc["id"]):
        return False
    # user 2026-10-25: "the AI auto re-render is taking way too long ... I'm doing revisions, it's just going to slow me
    # down". settings.audit_to_ai = false: the draft goes straight to him, the audit flags stay in the report for his notes
    # one-take mode (laptop worker, unattended first drafts): the fix round runs while nobody waits on it
    if not (store.settings().get("audit_to_ai", True) or one_take(doc)):
        return False
    try:
        flags = json.loads((Path(doc["path"]) / "work" / "draft_audit.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: no audit file (not a review build)
        return False
    real = [f for f in flags if f.get("kind") != "listen"]
    if not real:
        return False
    known = {n.get("text") for n in doc.get("notes", [])}
    for f in real:
        why = f.get("why") or {"repeat": "a line said twice (retake left in)", "stranded": "a stranded scrap of a bad take",
                               "ending": "the video ends mid-word"}.get(f["kind"], f["kind"])
        text = (f"AUTO-CHECK before the user watched (draft audit, main edit without intro): {why}: \"{f.get('phrase', '')}\". "
                f"Listen at recording {f['src'][0]:.1f}" + (f"-{f['src'][-1]:.1f}" if len(f["src"]) > 1 else "") +
                " s and fix the cut so the sentence is whole and nothing is said twice; if it already sounds right, report "
                "it applied with how = 'checked, fine as is'.")
        if text in known:
            continue
        n = {"kind": "text", "text": text, "added": store.now(), "from": "audit", "status": "pending",
             "nid": uuid.uuid4().hex[:6], "raw0": round(float(f["src"][0]), 2), "raw1": round(float(f["src"][-1]), 2)}
        doc["notes"].append(n)
    doc["audit_rounds"] = doc.get("audit_rounds", 0) + 1
    store.save(doc)
    try:
        api_rebuild_notes({"id": doc["id"]}, {})
    except Exception:  # noqa: the notes are there; he can send them by hand
        traceback.print_exc()
        return False
    notify.toast("Draft audit found problems", f"{doc['title']}: {len(real)} cut problem(s) went to the AI before you watch.")
    return True


def api_chat_run(q, body):
    """A Claude Code chat fixing this project by hand opens a revision run for the notes it works on (body {"nids": [...]},
    or all open revision notes): the studio then stays quiet about intermediate builds and sends ONE "Revisions done"
    when every note is applied/failed and the last draft built + QC'd (user 2026-10-22). {"stop": true} closes it."""
    doc = _doc(q)
    if body.get("stop"):
        data = chat.load(doc)
        if data.get("run"):
            data["run"]["state"], data["run"]["ended"] = "stopped", store.now()
            chat.save(doc, data)
        return {"ok": True}
    nids = body.get("nids") or [n["nid"] for n in doc.get("notes", []) if n.get("kind") == "revision" and n.get("status") not in ("applied", "failed")]
    stamp_batch(doc, [n for n in doc.get("notes", []) if n.get("nid") in nids])
    store.save(doc)
    chat.begin_run(doc, nids, owner="claude-chat")
    return {"ok": True, "nids": nids}


def api_project_sections(q, body):
    doc = _doc(q)
    if doc["type"] != "gaming":
        raise ApiError("sections are a gaming thing")
    secs = [[s["name"], float(s["s"]), float(s["e"])] for s in body["sections"] if s.get("name")]
    secs.sort(key=lambda s: s[1])
    common.write_json(recipe("gaming").paths(doc)["sections"], secs)
    return project_view(store.save(doc), full=True)


def api_project_thumb_from_frame(q, body):
    doc = _doc(q)
    src = body.get("file") or doc.get("source")
    t = float(body.get("t", 1.0))
    r = recipe(doc["type"])
    out_dir = Path(r.paths(doc).get("thumb_dir") or Path(doc["path"]) / "Thumbnail")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "frame.png"
    crop = body.get("crop")
    info = media.probe(src)
    expr = None
    if crop in ("left", "right") and info:
        expr = f"iw/2:ih:{'0' if crop == 'left' else 'iw/2'}:0"
    if not media.frame(src, t, out, w=1920, crop_expr=expr):
        raise ApiError("could not grab the frame")
    doc["slots"]["thumbnail"] = str(out)
    return project_view(store.save(doc), full=True)


def api_description_save(q, body):
    doc = _doc(q)
    path = doc["slots"].get("description") or str(Path(doc["path"]) / "youtube-description.txt")
    Path(path).write_text(body.get("text", ""), encoding="utf-8")
    doc["slots"]["description"] = path
    doc["checklist"]["description"] = bool(body.get("text", "").strip())
    return project_view(store.save(doc), full=True)


def api_drive_send(q, body):
    doc = _doc(q)
    finals = [o for o in recipe(doc["type"]).outputs(doc) if o["kind"] == "final"]
    if not finals:
        raise ApiError("no FINAL render yet (drafts never go to Drive)")
    res = tracker.send_to_drive(doc, finals[-1]["file"], extra=body.get("extra") or [])
    doc["checklist"]["drive"] = True
    # a video on Drive is done: it becomes a completed task on its channel's to-do list
    tt = todo.done_card(doc.get("channel") or "", doc["title"])
    res["todo"] = tt
    doc["checklist"]["ticktick"] = True
    notify.notify("Video done", f"{doc['title']}: on Drive, to-do '{tt['title']}' {tt['status']}.")
    store.save(doc)
    return {"result": res, "project": project_view(store.load(doc["id"]), full=True)}


def api_todo_for_project(q, body):
    """Adds the video as a task on its channel's to-do list."""
    doc = _doc(q)
    notes = body.get("notes") or f"Project folder: {doc['path']}\nType: {doc['type']}"
    res = todo.add(body.get("title") or doc["title"], body.get("channel") or doc["channel"], body.get("due") or doc.get("due"), notes)
    doc["checklist"]["ticktick"] = True
    store.save(doc)
    return {"result": res, "project": project_view(store.load(doc["id"]), full=True)}


def api_chat(q, body):
    doc = _doc(q)
    return chat.status(doc)


def api_chat_send(q, body):
    doc = _doc(q)
    msg = (body.get("text") or "").strip()
    if not msg:
        raise ApiError("empty message")

    def done(d, reply):
        notify.toast("Claude replied", (reply or "")[:120].replace("\n", " ") or d["title"])
    chat.start(doc, msg, on_done=done)
    return chat.status(doc)


# "Done: test video, study it" (right-click, user 2026-10-23): test videos are approved like a real one but never go to
# Drive; Claude writes the approved edit into memory + the type's skill + teach examples, as done by hand for
# lv trainer and dhgate jordan 3
MEMORY_DIR = Path(__file__).resolve().parents[2] / "memory"   # kit: reference edits are noted here
SKILL_DIRS = {"review": Path(os.path.expanduser(r"~\.claude\skills\product-review-edit")),
              "phone": Path(os.path.expanduser(r"~\.claude\skills\phone-tutorial-edit")),
              "gaming": Path(os.path.expanduser(r"~\.claude\skills\gaming-video")),
              "haul": Path(os.path.expanduser(r"~\.claude\skills\haul-edit")),
              "short": Path(os.path.expanduser(r"~\.claude\skills\short-edit"))}
TEACH_DIR = Path(r"{{KIT}}/tools")


def study_message(doc):
    skill = SKILL_DIRS.get(doc["type"])
    return f"""The user approved "{doc['title']}" as a FINISHED TEST VIDEO (right-click "Done: test video, study it" in the Studio).
Studio already ticked approved + final. It must NOT go to Drive and nothing gets rendered again: the newest draft is the final.
Save it as an approved reference edit so future drafts need fewer notes, exactly like the existing ones:
1. Read {MEMORY_DIR}\\dhgate-jordan-3-reference-edit.md and {MEMORY_DIR}\\lv-trainer-reference-edit.md for the format.
2. Gather the facts yourself: the approved file (newest final_intro.mp4 / draft in output\\), ffprobe (length, codec, bitrate), the targets check
   (output\\*targets.md), studio.json notes with their "how" and timestamps, the builds, raw length, intro template. Never guess a number.
3. Write {MEMORY_DIR}\\<slug>-reference-edit.md (if a note for this project exists, update it instead) and add one line to
   {MEMORY_DIR}\\MEMORY.md next to the other reference edits. Say "test, no Drive".
4. Add an entry at the top of "## Reference edits (approved)" in {skill}\\SKILL.md (what it is a reference for, what its rounds taught;
   rules that are missing from the skill go in too, short).
5. If {TEACH_DIR}\\_state\\claude_cache has intro_director / draft_qc calls for this project, add the approved ones with
   python "{TEACH_DIR}\\teach.py" add <task> --from <cache file> [--answer <corrected json>] --title "..." --lesson "...".
6. If the hindsight tools are available, ingest a short summary; if not, skip it.
Reply in 3 short lines: what was saved and where."""


def api_project_test_done(q, body):
    doc = _doc(q)
    if jobs.running_for(doc["id"]):
        raise ApiError("a build is still running on this project; mark it done when the draft is built")
    if not recipe(doc["type"]).outputs(doc):
        raise ApiError("there's no draft to approve yet")
    doc["checklist"].update({"approved": True, "final": True})
    doc["settings"]["test_video"] = True
    store.save(doc)
    save_answer_key(doc)

    def done(d, reply):
        notify.toast("Saved to memory", (reply or "")[:120].replace("\n", " ") or d["title"])
        # the phone has no toast (user 2026-10-25 approves test videos from the phone page): confirm on Telegram too
        import threading
        threading.Thread(target=notify.telegram, args=(f"🧪 <b>Studied: {notify._esc(d['title'])}</b>\nSaved as an approved test reference "
                         f"(no Drive / TickTick).\n{notify._esc((reply or '').strip()[:600])}",), daemon=True).start()
    try:
        chat.start(doc, study_message(doc), on_done=done, add_dirs=[MEMORY_DIR, SKILL_DIRS.get(doc["type"], MEMORY_DIR), TEACH_DIR])
        studying = True
    except RuntimeError:   # Claude is busy on this project: the boxes are ticked, the study can be sent from Ask Claude later
        studying = False
    return {"ok": True, "studying": studying, "project": project_view(store.load(doc["id"]), full=True)}


def api_chat_login(q, body):
    chat.open_login()
    return {"ok": True}


def api_chat_reset(q, body):
    doc = _doc(q)
    chat.reset(doc)
    return chat.status(doc)


def api_notify_test(q, body):
    notify.notify("{{STUDIO_NAME}}", "Notifications are working.")
    return {"ok": True}


def api_external(q, body):
    return {"external": external.describe(_doc(q))}


def api_note_preview(q, body):
    """What a note will do, before it is added (shown live under the note box)."""
    text = speech.normalize_times(body.get("text", ""))
    n = common.parse_note(text) if text.strip() else {"kind": "text"}
    return {"text": text, "note": n}


def api_jobs(q, body):
    return {"jobs": jobs.all_views()}


def api_job(q, body):
    j = jobs.JOBS.get(q["id"])
    if not j:
        raise ApiError("no such job", 404)
    return j.view(frm=int(q.get("from", 0)))


def api_job_cancel(q, body):
    j = jobs.JOBS.get(q["id"])
    if j:
        j.cancel()
    return {"ok": True}


def api_job_move(q, body):
    """render queue order: {"where": "up" | "down" | "top"}"""
    return {"ok": jobs.move(q["id"], (body or {}).get("where", "up")), "queue": jobs.gpu_view()}


def api_machines(q, body):
    """the machines this Studio knows (Build now / Schedule pickers): this one + workers + peers, who is on, who is busy"""
    names = [remote.me()] + [w["name"] for w in remote.workers()] + [p["name"] for p in (store.settings().get("peers") or [])]
    snap = {w["name"]: w for w in remote.snapshot()["workers"]}
    out = [{"name": n, "me": n == remote.me(), "ok": n == remote.me() or bool(snap.get(n, {}).get("ok")),
            "busy": (any(j.status in ("running", "queued") for j in jobs.JOBS.values()) if n == remote.me() else bool(snap.get(n, {}).get("jobs")))}
           for n in dict.fromkeys(names)]
    return {"machines": out, "default": store.settings().get("default_machine") or "Laptop", "me": remote.me()}


def ship_to_workers(doc):
    """a project scheduled (or set to build on a worker) goes there right away, so that machine can build it even if this
    one is off by then"""
    for w in remote.workers():
        if not remote.online(w["name"]):
            continue
        try:
            n, size = remote.sync_to(w, doc["path"], extra=outside_files(doc))
            remote.call(w, "POST", "projects/adopt", {"path": doc["path"]})
            print(f"shipped {doc['title']} to {w['name']}: {n} files, {size / 1e9:.2f} GB", flush=True)
        except Exception as e:  # noqa: it is sent again at build time
            print(f"ship {doc['title']} to {w['name']}: {e}", flush=True)


def api_project_schedule(q, body):
    """{"at": "YYYY-MM-DD HH:MM" (or "YYYY-MM-DDTHH:MM"), "machine": "Laptop"|"Desktop"|"Both", "action": "draft"}"""
    doc = _doc(q)
    at = str(body.get("at") or "").replace("T", " ")[:16]
    try:
        time.strptime(at, "%Y-%m-%d %H:%M")
    except ValueError:
        raise ApiError("pick a date and time")
    machine = body.get("machine") or store.settings().get("default_machine") or "Laptop"
    e = schedule.add(doc, at, machine, body.get("action") or "draft")
    if remote.workers() and doc["type"] != "gaming":
        threading.Thread(target=ship_to_workers, args=(doc,), daemon=True).start()
    return {"item": e, "schedule": schedule.view()}


def api_settings(q, body):
    if body:
        return store.save_settings(body)
    return store.settings()


# ------------------------------------------------------------------ render devices ("Add a device", user 2026-10-29: "it would
# have to walk them through it"). A device = another PC with Studio on it that this one reaches over SSH (remote.py workers).
DEVICE_KEY = Path.home() / ".ssh" / "studio_device"


def api_devices_key(q, body):
    """this PC's key for the walkthrough (made once, no passphrase) + what the other PC needs to know"""
    if not DEVICE_KEY.exists():
        DEVICE_KEY.parent.mkdir(exist_ok=True)
        r = subprocess.run(["ssh-keygen", "-t", "ed25519", "-N", "", "-C", f"studio-{store.settings().get('machine_name') or 'pc'}",
                            "-f", str(DEVICE_KEY)], capture_output=True, text=True, creationflags=media.CREATE_NO_WINDOW)
        if r.returncode or not DEVICE_KEY.exists():
            raise ApiError("Could not make this PC's key (is OpenSSH Client installed?) " + (r.stderr or "")[-200:])
    pub = Path(str(DEVICE_KEY) + ".pub").read_text(encoding="utf-8").strip()
    return {"pub": pub, "studio": str(store.HOME), "machine": store.settings().get("machine_name") or "Desktop",
            "devices": [{"name": w["name"], "ssh": w["ssh"]} for w in remote.workers()]}


def api_devices_add(q, body):
    """test the connection to the other PC, then save it as a render device"""
    name = re.sub(r"[^\w .-]", "", (body.get("name") or "").strip())[:30]
    host = re.sub(r"[^\w.:-]", "", (body.get("host") or "").strip())
    user = re.sub(r"[^\w.\\ -]", "", (body.get("user") or "").strip())
    if not (name and host and user):
        raise ApiError("Fill in the device name, its address and its Windows user name")
    w = {"name": name, "ssh": f"{user}@{host}", "key": "~/.ssh/" + DEVICE_KEY.name, "root": store.HOME.drive + "\\"}
    try:
        remote._ssh(w, "echo ok", timeout=25)
    except Exception as e:  # noqa
        raise ApiError(f"Could not reach {host} as {user}: {str(e).rstrip('.')}. Check that both PCs are on and signed in to Tailscale, and that "
                       "step 3 ran on the other PC as administrator.")
    try:
        found = "studio" in remote._ssh(w, f'if exist "{remote.LOCAL_API}" (echo studio) else (echo none)', timeout=25)
    except Exception:  # noqa
        found = False
    if not found:
        raise ApiError(f"Connected to {host}, but Studio is not at {store.HOME} on it. Install Studio there in the same folder (step 1).")
    ws = [x for x in (store.settings().get("workers") or []) if x.get("name", "").lower() != name.lower()] + [w]
    store.save_settings({"workers": ws})
    remote.start()
    return {"ok": True, "device": {"name": name, "ssh": w["ssh"]}}


def api_browse(q, body):
    """Simple server-side file browser (for browser mode and the music picker)."""
    d = q.get("dir") or ""
    exts = set((q.get("ext") or "").lower().split(",")) - {""}
    if not d:
        s = store.settings()
        roots = [s["roots"]["gaming"], s["roots"]["phone"], s["vo_folder"], s["music_root"]] + list(s["recordings"]) + [s["drive_root"], str(Path.home() / "Downloads"), str(Path.home() / "Desktop")]
        seen, out = set(), []
        for r in roots:
            if r and os.path.isdir(r) and r.lower() not in seen:
                seen.add(r.lower())
                out.append({"name": r, "path": r, "dir": True})
        return {"dir": "", "parent": "", "items": out}
    p = Path(d)
    if not p.is_dir():
        raise ApiError("not a folder")
    items = []
    try:
        for e in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if e.name.startswith((".", "$")) or e.name.lower() in ("system volume information", "desktop.ini"):
                continue
            if e.is_dir():
                items.append({"name": e.name, "path": str(e), "dir": True})
            elif not exts or e.suffix.lower() in exts:
                st = e.stat()
                items.append({"name": e.name, "path": str(e), "dir": False, "size": st.st_size, "mtime": st.st_mtime})
    except PermissionError:
        raise ApiError("no access")
    return {"dir": str(p), "parent": str(p.parent) if p.parent != p else "", "items": items[:800]}


LABELS = {"busy": False}


def api_rename_recording(q, body):
    """Rename a recording (and its OBS .mkv/.mp4 twin + .broll.json sidecar) and fix projects that point at it."""
    src = Path(body["path"])
    name = store.safe_name(body.get("name", "")).strip()
    if not src.exists() or not name:
        raise ApiError("file or name missing")
    renamed = []
    for twin in {src} | {src.with_suffix(ext) for ext in (".mp4", ".mkv", ".mov")}:
        if twin.exists():
            dest = twin.with_name(name + twin.suffix.lower())
            if dest.exists() and dest != twin:
                raise ApiError(f"{dest.name} already exists")
            os.replace(twin, dest)
            renamed.append((str(twin), str(dest)))
            side = Path(str(twin) + ".broll.json")
            if side.exists():
                os.replace(side, Path(str(dest) + ".broll.json"))
    for d in store.all_projects():
        for old, new in renamed:
            if (d.get("source") or "").lower() == old.lower():
                d["source"] = new
                store.save(d)
    return {"renamed": renamed, "path": next((n for o, n in renamed if o.lower() == str(src).lower()), str(src))}


def api_probe(q, body):
    pth = q.get("path", "")
    if not os.path.exists(pth):
        raise ApiError("not found")
    return {"path": pth, "duration": media.cached_duration(pth), "size": os.path.getsize(pth), "label": media.cached_label(pth)}


def api_detect(q, body):
    """Which video type a dropped recording is (gaming / phone / review), with the reasons for the confirm chip."""
    pth = q.get("path", "")
    if not os.path.exists(pth):
        raise ApiError("not found")
    # quick=1: picture + file signals only (~1-2 s) so New Project can show a type at once; the full check follows
    return detect.detect(pth, fresh=q.get("fresh") == "1", quick=q.get("quick") == "1")


def api_recent_recordings(q, body):
    """The latest OBS recordings (6) and the latest Audacity voice-over takes (4) for the New Project screen."""
    s = store.settings()
    used = {(d.get("source") or "").lower() for d in store.all_projects()}
    vids, vo = [], []
    for r in s["recordings"]:
        if os.path.isdir(r):
            for e in Path(r).iterdir():
                if e.is_file() and e.suffix.lower() == ".mp4":   # MP4 only: the OBS .mkv is the same recording before remux
                    st = e.stat()
                    vids.append({"name": e.name, "path": str(e), "size": st.st_size, "mtime": st.st_mtime, "kind": "video",
                                 "used": str(e).lower() in used, "broll": os.path.exists(str(e) + ".broll.json")})
    vids.sort(key=lambda x: -x["mtime"])
    n_v = int(q.get("videos", 6))
    for v in vids[:n_v]:
        v["duration"] = media.cached_duration(v["path"])
        v["label"] = media.cached_label(v["path"])
    missing = [v["path"] for v in vids[:n_v] if v["label"] is None]
    if missing and not LABELS.get("busy"):
        LABELS["busy"] = True

        def work():
            try:
                for pth in missing:
                    media.compute_label(pth)
            finally:
                LABELS["busy"] = False
        threading.Thread(target=work, daemon=True).start()
    if os.path.isdir(s["vo_folder"]):
        for e in Path(s["vo_folder"]).iterdir():
            if e.is_file() and e.suffix.lower() in media.AUDIO_EXT:
                st = e.stat()
                vo.append({"name": e.name, "path": str(e), "size": st.st_size, "mtime": st.st_mtime, "kind": "audio"})
    vo.sort(key=lambda x: -x["mtime"])
    n_a = int(q.get("audio", 8))
    for v in vo[:n_a]:
        v["duration"] = media.cached_duration(v["path"])
    return {"recordings": vids[:n_v], "vo": vo[:n_a], "items": (vids + vo)[:40], "more_recordings": max(0, len(vids) - n_v), "more_vo": max(0, len(vo) - n_a)}


def api_editor(q, body):
    """Everything the Gling-style editor needs: words (raw times), kept ranges, cut list, sections, what to play."""
    doc = _doc(q)
    r = recipe(doc["type"])
    P = r.paths(doc)
    words_path = P.get("words") or P.get("transcript")
    if doc["type"] == "review":
        words_path = P.get("transcript")
    words = store.read_json(words_path, []) if words_path else []
    if isinstance(words, dict):
        words = words.get("words") or []
    words = [{"w": w.get("w") or w.get("word", ""), "s": w.get("s", w.get("start", 0)), "e": w.get("e", w.get("end", 0))} for w in words]
    cuts_doc = store.read_json(P.get("cuts"), None) if P.get("cuts") else None
    keep = common.keep_ranges(P["cuts"]) if P.get("cuts") else None
    cut_list = []
    if isinstance(cuts_doc, dict):
        for c in cuts_doc.get("cuts", []) or []:
            if c.get("why") == "silence":
                continue
            cut_list.append({"s": c.get("s"), "e": c.get("e"), "why": c.get("why", ""), "text": (c.get("text") or "")[:120]})
    info = r.timeline_info(doc)
    if any(a < 0 for a, _ in (info.get("keep") or [])):   # the draft has inserted clips: map draft times through its own timeline
        keep = [tuple(x) for x in info["keep"]]
    outs = project_view(doc)["outputs"]
    src_info = media.probe(doc["source"]) if doc.get("source") else None
    return {"words": words, "keep": keep or [], "cuts": cut_list, "sections": info.get("sections") or [], "offset": info.get("offset", 0.0),
            "duration": (src_info or {}).get("duration", words[-1]["e"] if words else 0), "source": doc.get("source") or "",
            "outputs": outs, "has_words": bool(words), "notes": doc.get("notes", []), "shorts": extras.list_shorts(doc),
            # timeline editor (2026-10-29): music the last build used, draft-time sections of haul/short builds, the slots'
            # B-roll files and the project's caption/transition settings
            "music": info.get("music") or (review_music(doc, info.get("offset", 0.0)) if doc["type"] == "review" else {}), "draft_sections": info.get("haul_sections") or [], "music_used": music_used(doc),
            "broll_files": [f for f in (doc.get("slots") or {}).get("broll", []) or [] if isinstance(f, str)],
            "settings": {k: (doc.get("settings") or {}).get(k) for k in ("captions", "wipe", "transition")}}


def api_transitions(q, body):
    """Section transitions the timeline editor offers: the HyperFrames transition renders + this project's own
    Graphics\\*transition*.mov. Only the gaming pipeline puts wipes between sections today (settings.wipe)."""
    doc = _doc(q) if q.get("id") else None
    items, seen = [], set()

    def add(p, where):
        k = str(p).lower()
        if k in seen:
            return
        seen.add(k)
        items.append({"name": Path(p).stem.replace("-", " ").replace("_", " "), "path": str(p), "where": where})

    auto = ""
    try:
        sys.path.insert(0, str(Path(__file__).parent / "gaming"))
        import glib  # noqa: E402
        hf = glib.ASSETS / "Graphics" / "HyperFrames"
        if hf.is_dir():
            for m in sorted(hf.glob("*/renders/*.mov")):
                if re.search(r"transition|wipe", m.stem, re.I):
                    add(m, "library")
        if doc:
            auto = glib.wipe_for({**doc, "settings": {k: v for k, v in (doc.get("settings") or {}).items() if k != "wipe"}}, doc.get("path"))
    except Exception:  # noqa: the list still shows the project's own files
        pass
    if doc and doc.get("path"):
        g = Path(doc["path"]) / "Graphics"
        if g.is_dir():
            for m in sorted(g.rglob("*.mov")):
                if "transition" in m.stem.lower() and not any(x.lower().startswith("_") for x in m.relative_to(g).parts[:-1]):
                    add(m, "this video")
    return {"items": items, "auto": auto, "chosen": ((doc or {}).get("settings") or {}).get("wipe") or "",
            "applies": (doc or {}).get("type") == "gaming"}


def api_thumbnails(q, body):
    """Every project's thumbnail status, for the Thumbnails view (needed first). Drive is checked first."""
    rows = []
    for d0 in store.all_projects():
        d = store.load(d0["id"]) if tracker.auto_thumb(d0, force=bool(q.get("fresh"))) else d0
        st = tracker.stage(d)
        info = media.probe(d["source"]) if d.get("source") else None
        layout = media.layout_of(info)
        crop = ("right" if d["type"] == "gaming" else "left") if layout == "side-by-side" and not d["slots"].get("thumbnail") else None
        desc = ""
        dp = d["slots"].get("description")
        if dp and os.path.exists(dp):
            try:
                desc = next((l.strip() for l in Path(dp).read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()), "")
            except OSError:
                pass
        opener = media.cached_label(d["source"]) if d.get("source") else ""
        rows.append({"id": d["id"], "title": d["title"], "type": d["type"], "channel": d.get("channel", ""), "due": d.get("due", ""), "stage": st,
                     "done": bool(d["checklist"].get("thumbnail")), "file": d["slots"].get("thumbnail") or "", "preview": d["slots"].get("thumbnail") or d.get("source") or "",
                     "crop": crop, "has_source": bool(d.get("source")), "updated": d.get("updated", ""), "brief": d.get("thumb_brief", ""),
                     "refs": [r_ for r_ in d["slots"].get("thumb_refs", []) if os.path.exists(r_)], "desc": desc[:200], "opener": opener or "", "path": d["path"],
                     "youtube": d.get("links", {}).get("youtube", ""), "from_drive": d.get("thumb_source", "")})
    return {"rows": rows}


def api_thumbnails_export(q, body):
    """Write the designer brief to a file next to the app (the UI also copies it to the clipboard)."""
    text = body.get("text", "")
    out = store.DATA / "thumbnails-brief.md"
    out.write_text(text, encoding="utf-8")
    return {"file": str(out)}


def api_music(q, body):
    root = Path(store.settings()["music_root"])
    sub = q.get("sub") or (next((d.name for d in sorted(root.iterdir()) if d.is_dir() and not d.name.startswith("_")), "") if root.is_dir() else "")
    base = root / sub
    pool = store.read_json(common.GAMING / "music_pool.json", {}) or {}
    vetted = {t["track"].lower() for k in ("general", "pokemon", "shorts") for t in pool.get(k, [])}
    scans = extras.scan_results()
    items = []
    if base.is_dir():
        for e in sorted(base.rglob("*")):
            if e.is_file() and e.suffix.lower() in media.AUDIO_EXT:
                sc = scans.get(str(e)) or {}
                items.append({"name": e.stem, "path": str(e), "folder": str(e.parent.relative_to(root)), "vetted": str(e).lower() in vetted or sc.get("verdict") == "clean",
                              "scan": sc.get("verdict", ""), "words": sc.get("words")})
    folders = [d.name for d in root.iterdir() if d.is_dir() and not d.name.startswith("_")] if root.is_dir() else []
    return {"folders": folders, "sub": sub, "items": items[:1500]}


def api_open(q, body):
    p = body.get("path", "")
    if not p or not os.path.exists(p):
        raise ApiError("path does not exist")
    if body.get("reveal"):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(p)])
    else:
        os.startfile(p)  # noqa
    return {"ok": True}


def api_clipboard(q, body):
    txt = body.get("text", "")
    subprocess.run(["clip"], input=txt.encode("utf-16le"), creationflags=media.CREATE_NO_WINDOW)
    return {"ok": True}


def api_qc(q, body):
    return extras.qc_report(_doc(q))


def api_short_make(q, body):
    doc = _doc(q)
    return extras.make_short(doc, float(body["raw0"]), float(body["raw1"]), body.get("side", "center"), body.get("name", ""))


def api_shorts(q, body):
    return {"shorts": extras.list_shorts(_doc(q))}


def _music_lib():
    sys.path.insert(0, r"{{KIT}}/tools")
    import music_lib
    return music_lib


def api_music_removed(q, body):
    """songs he right-clicked out of the music picker (file names, lower case)"""
    return {"removed": _music_lib().removed()}


def api_music_remove(q, body):
    """{path, undo?}: take a song out of the library / put it back (music_lib.remove; the file stays on disk)"""
    if not body.get("path"):
        raise ValueError("need a song")
    return {"ok": True, "removed": _music_lib().remove(body["path"], undo=bool(body.get("undo")))}


def api_music_scan(q, body):
    return extras.scan_music(body.get("paths") or [])


def api_cards_render(q, body):
    doc = _doc(q)
    if body.get("codes") is not None:
        doc["settings"]["cards_codes"] = body["codes"]
        store.save(doc)
    return extras.render_cards(store.load(doc["id"]))


def api_search(q, body):
    return extras.search(q.get("q", ""))


def api_write_description(q, body):
    doc = _doc(q)
    try:
        return {"text": extras2.write_description(doc)}
    except Exception as e:
        raise ApiError(str(e))


def api_titles(q, body):
    doc = _doc(q)
    try:
        titles = extras2.title_ideas(doc)
    except Exception as e:
        raise ApiError(str(e))
    doc["title_ideas"] = titles
    store.save(doc)
    return {"titles": titles}


def api_frames(q, body):
    try:
        return {"frames": extras2.frame_suggestions(_doc(q))}
    except Exception as e:
        raise ApiError(str(e))


def api_new_recordings(q, body):
    return {"items": extras2.new_recordings()}


def api_cleanup(q, body):
    doc = _doc(q)
    if body.get("run"):
        return extras2.cleanup_run(doc)
    return extras2.cleanup_scan(doc)


def api_stats(q, body):
    return {"stats": extras2.edit_stats(_doc(q))}


def api_report(q, body):
    return extras2.weekly_report()


def api_va(q, body):
    return {"text": extras2.va_pack(_doc(q))}


def api_factory(q, body):
    doc = _doc(q)
    act = body.get("action") if body else None
    try:
        if act == "scan":
            return extras2.factory_scan(doc, int(body.get("n", 8)))
        if act == "titles":
            return extras2.factory_titles(doc)
        if act == "render":
            return extras2.factory_render(doc, body.get("picks") or [], body.get("side", "auto"))
        if act == "package":
            return extras2.factory_gaming_package(doc, body.get("sections"))
    except Exception as e:
        raise ApiError(str(e))
    st = extras2.factory_state(doc)
    st["shorts"] = extras.list_shorts(doc)
    st["has_render"] = bool(extras2._best_render(doc)[0])
    return st


def intro_scope(doc, notes):
    """Intro length (s) when EVERY note of this batch is about the intro, else None (user 2026-10-23: intro-only rebuilds,
    automatic, no tick box). A note counts when its draft time lies inside the intro or it says "intro"; a note with a
    recording time, or with no time and no "intro", may touch the main edit, so the batch gets the full rebuild.
    Review projects with a built intro (VO -> intro/build) only: that is the one pipeline whose intro is a separate step."""
    dur = intro_len(doc)
    if not notes or not dur:
        return None
    return dur if all(note_in_intro(n, dur) for n in notes) else None


def intro_len(doc):
    """Length (s) of the built review intro (with a main edit to join it to), else None."""
    if doc.get("type") != "review":
        return None
    p = Path(doc["path"])
    clip = p / "intro" / "build" / "renders" / "intro.mp4"
    if not clip.exists() or not (p / "output" / "final.mp4").exists():
        return None
    dur = (media.probe(str(clip)) or {}).get("duration") or 0
    return dur if dur >= 3 else None


def note_in_intro(n, dur):
    """A note is about the intro when its draft time lies inside it or it says "intro"."""
    says = re.search(r"\bintro\b", n.get("text") or "", re.I)
    if n.get("raw0") is not None and not says:
        return False
    t0, t1 = n.get("t0"), n.get("t1")
    inside = t0 is not None and t0 < dur and (t1 if t1 is not None else t0) <= dur + 1.0
    # "intro" only rescues a note with no time or one pressed a few seconds late; "after the intro, at 2:40 ..." is
    # about the main edit
    if says and t0 is not None and t0 > dur + 6:
        says = None
    return bool(inside or says)


def api_rebuild_notes(q, body):
    """The single "rebuild with notes" button. Exact notes are applied by the cutter as always; on phone projects, notes the
    app can't turn into a time range (plain words: "2:20 remove 'to'") are handed to revise.py (Opus) first."""
    doc = _doc(q)
    d = defer_build(doc, "notes", body)   # Overnight / a picked time: the whole revision (AI + render) runs then
    if d:
        return d
    text_notes = [n for n in doc.get("notes", []) if n.get("kind") == "text" and not n.get("done")]
    if text_notes:
        # every revision in words goes to Claude (Opus 5.5, Claude Code CLI), who can change cuts, layout, graphics and the
        # intro, rebuilds the draft and marks each revision applied/failed. revise.py could only place cuts, so layout,
        # zoom and card notes were marked done without anything happening (Shein, 2026-10-21). Gaming + review went through
        # interpret_notes.py (cuts only) with the same bug: music / intro / B-roll / graphics notes dropped but shown as
        # applied (dhgate asics + Top 10 Minecraft Servers, 2026-10-22), so all three types take this path now.
        for n in doc["notes"]:
            n.setdefault("nid", uuid.uuid4().hex[:6])
        intro = common.draft_offset(doc, str(Path(doc["path"]) / "edit" / "intro" / "intro.mp4")) if doc["type"] == "phone" else None
        only_intro = intro_scope(doc, text_notes)
        if only_intro:
            intro = only_intro
            for n in text_notes:
                n["scope"] = "intro"
        build_action = "intro" if only_intro else "draft"
        # intro lock (2026-10-24): a full build keeps the built intro unless a note of this batch is about it
        idur = intro_len(doc)
        intro_notes = bool(idur) and any(note_in_intro(n, idur) for n in text_notes)
        if intro_notes and not only_intro:
            doc["intro_rebuild"] = True
        lines = []
        for n in text_notes:
            at = ""
            if n.get("t0") is not None:
                at = f" [draft {media.fmt_t(n['t0'])}" + (f"-{media.fmt_t(n['t1'])}" if n.get("t1") is not None else "") + "]"
            if n.get("raw0") is not None:
                at += f" [recording {n['raw0']:.1f}-{n['raw1']:.1f} s]"
            if n.get("from") == "request":   # written in New Project before any draft: no times, find the moments yourself
                at += (" [SPECIAL REQUEST written before the edit: no time given; find every place it applies from the "
                       "transcript / sections (\"every time I say X\" = every mention), and apply it there]")
            at += " [RULE: may change the shared pipeline; gate it]" if n.get("applies") == "rule" else " [ONE VIDEO: fix only in this project]"
            lines.append(f"- id {n['nid']}{at}: {n['text']}")
            n["status"] = "claude"
        stamp_batch(doc, text_notes + [n for n in doc["notes"] if n.get("kind") != "text" and not n.get("done")])
        store.save(doc)
        port = store.settings().get("port", 8765)
        how = {
            "phone": "For cuts, add entries to work\\extra_cuts.json with edges on measured audio quiet (see the phone-tutorial-edit "
                     "skill). For layout, graphics, zooms, cards, music or the intro, edit the project's edit\\ files or the shared "
                     "phone_edit tools.",
            "gaming": "Use the minecraft-video skill. Exact edits are studio notes (POST /api/project/notes, text like `cut 1:22-1:30`, "
                      "`protect 2:03-2:10`, `broll 3:20 6s <clip>`, `section #5 Name 11:09-15:30`; insert clips per the README). "
                      "Music, cards, transitions, zooms, framing and the intro live in the gaming pipeline "
                      "({{KIT}}/Studio\\app\\gaming\\*.py) and the project's Edit\\ folder; the Top 5 Realms edit is the reference.",
            "review": "Use the product-review-edit skill. Per-project settings are in raw\\config.json; camera/screen switching, B-roll, "
                      "beats and audio are in {{KIT}}/tools\\edit_review.py; the intro is {{KIT}}/Studio\\app\\tools\\review_intro.py.",
            "haul": "Use the haul-edit skill. Cut/protect notes go through studio notes; intro/outro detection, music and the Doug intro "
                    "captions are in {{KIT}}/Studio\\app\\tools\\haul_render.py (settings: music_root, haul_captions, vocabulary); "
                    "clip normalising is tools\\haul_normalise.py.",
            "short": "Use the short-edit skill. A vertical Short (1080x1920) runs the haul pipeline in SHORT mode (tools\\haul_render.py, "
                     "tools\\haul_normalise.py); cut/protect notes go through studio notes; captions = preset doug_v in tools\\captions.py.",
        }.get(doc["type"], "")
        _mt = mystyle.type_of(doc)
        if _mt:   # a custom video type (my_style): its playbook + learned rules come first; notes become rules of the type
            how = (f"This is a '{_mt['name']}' video, the user's own video type built on this pipeline. Its playbook and the rules "
                   f"learned from earlier notes are in {Path(doc['path']) / '_style' / 'rules.md'}: follow them. Fix RULE notes for "
                   f"this type in the type's settings ({mystyle.TYPES / (_mt['slug'] + '.json')}, key \"rules\") or this project's "
                   "settings, never in the shared pipeline code (an update replaces that code; my_style is kept). " + how)
        msg = ("Apply these revisions to the current draft of this project (times are in the draft the user watched, intro included"
               + (f"; the intro is {intro:.1f} s" if intro is not None else "") + "). Read each one as an editor would, fix the cause, "
               "not just the symptom. First read {{KIT}}/tools\\EDIT_RULES.md (every past note as rules; run its section I before you report). Each note is marked ONE VIDEO or RULE (note sorting, user 2026-10-26: some notes turned into shared rules messed up the whole system). ONE VIDEO = a preference or a rare moment: fix it ONLY for this project (raw\\config.json overrides any key of the skill config.json, e.g. joins.air_before / greeting.avatar_center; raw\\studio_extra.json cuts / keeps; raw\\extra_keeps.json; raw\\broll.json; studio.json settings) and NEVER edit the shared pipeline code for it. RULE = he said always / never / again or it came up on another video: build it into the shared pipeline as narrowly as the case allows, add it to the skill + EDIT_RULES.md, and once your build is done and checked, QUEUE the rule gate: POST /api/rule-gate with {\"why\": \"<the note>\", \"pid\": \"" + doc["id"] + "\"}. Do NOT run rule_gate.py yourself and do NOT wait for it (speed, user 2026-10-29: the Mon Clear revision sat ~50 min in the gate after the draft was ready): it replays every approved video + every past note as a Studio background job and messages the user the verdict itself. It only decides whether the laptop gets the new code, never the draft. In your report say the gate is queued and that the laptop keeps the old code until it passes.\n"
               + "\n".join(lines) + "\n\n" + how +
               (f" EVERY revision in this batch is inside the intro (the first {only_intro:.1f} s): change only the intro (his shot "
                "picks go in studio.json settings.intro_pins, see build_intro.apply_pins; the intro tools are in "
                "{{KIT}}/tools\\intro_library) and rebuild with the INTRO-ONLY build, action \"intro\": it keeps "
                "output/final.mp4, re-renders the intro, joins it back on and checks only the intro (~10-15 min instead of ~40). "
                "Only if a fix really needs the main edit too, use action \"draft\" instead." if only_intro else "") +
               (" The intro is LOCKED for this batch (no note is about it): a full build reuses the built intro as it is, "
                "which saves ~8-10 min. Only if your fix really has to change the intro, add \"intro\":\"rebuild\" to the "
                "build request below." if doc["type"] == "review" and idur and not intro_notes else "") +
               # one build per batch (user 2026-10-24, speed): the sp5der batch ran 5 full builds in 2 h and timed out
               " ONE BUILD PER BATCH: make every fix first, check what you can WITHOUT rendering (the cut list / "
               "work\\cuts.json / timeline.json, the transcript around each note, settings and code you changed, a dry run "
               "or unit check of a changed script), then start ONE build. After it, check the draft with frames at each "
               "note's time (ffmpeg -ss <t> -frames:v 1, or check_video.py on a short range), not by building again. A "
               "second build is only for a note the draft shows is still wrong or a build that failed; never a third "
               "without a failed build. Report notes as soon as that one draft shows them fixed."
               " Then rebuild THROUGH THE APP, so the user sees the build progress bar. The app has a render queue (one "
               "video renders at a time, the user may be revising several): do NOT wait for other videos' jobs, just "
               f"curl -X POST http://127.0.0.1:{port}/api/project/run?id={doc['id']} -H \"Content-Type: application/json\" -d '{{\"action\":\"{build_action}\"}}', "
               "then poll GET /api/jobs until that job is done (it may show \"queued\" while it waits its turn in line; that can take "
               "a while, keep polling; do not run pipeline.py yourself), and check the new draft. "
               f"After each revision is done, report it: curl -X POST http://127.0.0.1:{port}/api/project/notes?id={doc['id']} "
               "-H \"Content-Type: application/json\" -d '{\"status\":\"<id>\",\"value\":\"applied\",\"how\":\"one line\"}' "
               "(value \"failed\" + why if you could not; never \"applied\" for something you did not change). Finish with a short "
               "list of what changed and what did not.")

        def chat_done(d0, reply):
            d = store.load(d0["id"])
            for n in d["notes"]:   # anything Claude didn't report on stays visible as "check"
                if n.get("status") == "claude":
                    n["status"] = "check"
            store.save(d)
            # one notification, when the whole batch is really finished (user 2026-10-22: "notified too early"): check_run
            # resumes Claude when it stopped with revisions open or no new draft, and sends "Revisions done" / "need you"
            chat.check_run(d)
        chat.begin_run(doc, [n["nid"] for n in text_notes])
        # a batch of revisions + a ~25 min rebuild + checking it ran past the 30 min chat limit and was stopped mid-job (Shein, 2026-10-21)
        chat.start(doc, msg, on_done=chat_done, timeout=2 * 3600)
        notify.toast("Revisions sent to Claude", f"{doc['title']} · {len(text_notes)} revision(s)")
        return {"mode": "claude", "text_notes": len(text_notes)}
    stamp_batch(doc, [n for n in doc.get("notes", []) if not n.get("done")])
    store.save(doc)
    job = start_build(doc, "draft")
    return {"mode": "draft", "text_notes": 0, "job": job.view()}


def api_revisions(q, body):
    """Phone projects: draft history (output\\*DRAFT*.mp4 + work\\revisions.json), seams.md, and starting a revision."""
    doc = _doc(q)
    if doc["type"] != "phone":
        raise ApiError("revise-draft is for phone projects")
    proj = Path(doc["path"])
    if body and body.get("notes") is not None:
        notes = body["notes"].strip()
        if not notes:
            raise ApiError("write at least one note")
        (proj / "work").mkdir(exist_ok=True)
        (proj / "work" / "revision_notes.txt").write_text(notes + "\n", encoding="utf-8")
        job = start_build(doc, "revise")
        return {"job": job.view()}
    revs = store.read_json(proj / "work" / "revisions.json", []) or []
    drafts = []
    for f in sorted((proj / "output").glob("*DRAFT*.mp4"), key=lambda x: x.stat().st_mtime) if (proj / "output").is_dir() else []:
        import re as _re
        m = _re.search(r"DRAFT v(\d+)", f.name)
        drafts.append({"file": str(f), "name": f.name, "version": int(m.group(1)) if m else None, "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(f.stat().st_mtime)),
                       "size": f.stat().st_size, "duration": media.cached_duration(str(f)), "current": not m and "old" not in f.name.lower()})
    seams = ""
    sp = proj / "work" / "seams.md"
    if sp.exists():
        seams = sp.read_text(encoding="utf-8", errors="replace")[:60000]
    notes_now = ""
    np_ = proj / "work" / "revision_notes.txt"
    if np_.exists():
        notes_now = np_.read_text(encoding="utf-8", errors="replace")
    return {"revisions": revs, "drafts": drafts, "seams": seams, "notes": notes_now}


def api_brief(q, body):
    """A ready-to-paste brief for Claude about this project (for hand-made intros, articles, fixes)."""
    doc = _doc(q)
    r = recipe(doc["type"])
    lines = [f"Project: {doc['title']} ({store.TYPES[doc['type']]['label']}, channel {doc.get('channel') or '?'})",
             f"Folder: {doc['path']}", f"Footage: {doc.get('source') or 'none yet'}"]
    for k in ("intro", "intro_vo", "thumbnail", "description"):
        if doc["slots"].get(k):
            lines.append(f"{k}: {doc['slots'][k]}")
    if doc["slots"].get("broll"):
        lines.append(f"B-roll clips: {len(doc['slots']['broll'])} in {Path(doc['slots']['broll'][0]).parent}")
    outs = r.outputs(doc)
    for o in outs:
        lines.append(f"{o['kind']}: {o['file']}")
    open_notes = [n["text"] for n in doc["notes"] if not n.get("done")]
    if open_notes:
        lines.append("Open notes: " + " | ".join(open_notes))
    lines.append(f"Task: {body.get('task') or 'see notes'}")
    return {"text": "\n".join(lines)}



# ---------------------------------------------------------------- phone review (ui/m.html): one tap = note in + rebuild
# (user 2026-10-24: "text button, and then it should take that text and then add it to your revisions and then start
# rebuilding"). While the project is still busy (a build queued/running, or the revision AI still on the last batch) the
# notes wait as "auto_send" and the auto-send thread sends them the moment it is free, so a second Claude never starts
# on the same project.
def project_busy(doc):
    return bool(jobs.running_for(doc["id"])) or chat.run_active(doc) or chat.activity(doc)["busy"]


def api_phone_send(q, body):
    doc = _doc(q)
    for t in [x.strip() for x in str(body.get("text") or "").split(chr(10)) if x.strip()]:
        api_project_notes(q, {"text": t})
    doc = _doc(q)
    if not [n for n in doc.get("notes", []) if not n.get("done") and n.get("status") in (None, "pending")]:
        raise ApiError("nothing to send")
    if project_busy(doc):
        doc["auto_send"] = True
        store.save(doc)
        return {"queued": True, "project": project_view(doc, full=True)}
    doc.pop("auto_send", None)
    store.save(doc)
    r = api_rebuild_notes(q, {})
    return {"sent": True, "mode": r.get("mode"), "project": project_view(_doc(q), full=True)}


def auto_send_loop(interval=30):
    def loop():
        time.sleep(30)
        while True:
            try:
                for d in store.all_projects():
                    if d.get("auto_send") and not project_busy(d):
                        d.pop("auto_send", None)
                        store.save(d)
                        api_rebuild_notes({"id": d["id"]}, {})
                        notify.toast("Phone revisions sent", f"{d['title']}: the previous batch finished, your phone notes went in.")
            except Exception as e:  # noqa
                print("auto-send:", e, flush=True)
            time.sleep(interval)
    threading.Thread(target=loop, daemon=True).start()

ROUTES = {
    ("GET", "state"): api_state,
    ("GET", "kit/update"): kit_update.api_check,
    ("POST", "kit/update/apply"): kit_update.api_apply,
    ("GET", "stats"): edit_stats.api_get,
    ("POST", "stats/set"): edit_stats.api_set,
    ("POST", "stats/delete"): edit_stats.api_delete,
    ("GET", "hub"): api_hub,
    ("GET", "todo"): api_todo,
    ("GET", "todo/lists"): api_todo_lists,
    ("POST", "todo/add"): api_todo_add,
    ("POST", "todo/complete"): api_todo_complete,
    ("POST", "todo/push"): api_todo_push,
    ("POST", "projects"): api_projects_create,
    ("POST", "projects/adopt"): api_projects_adopt,
    ("GET", "project"): api_project_get,
    ("POST", "project/update"): api_project_update,
    ("POST", "project/test-done"): api_project_test_done,
    ("POST", "project/delete"): api_project_delete,
    ("POST", "project/rename"): api_project_rename,
    ("POST", "project/slot"): api_project_slot,
    ("POST", "project/slot/remove"): api_project_slot_remove,
    ("POST", "project/run"): api_project_run,
    ("POST", "project/chat-run"): api_chat_run,
    ("POST", "project/notes"): api_project_notes,
    ("POST", "project/sections"): api_project_sections,
    ("POST", "project/thumb"): api_project_thumb_from_frame,
    ("POST", "project/description"): api_description_save,
    ("POST", "project/drive"): api_drive_send,
    ("POST", "project/todo"): api_todo_for_project,
    ("POST", "project/brief"): api_brief,
    ("GET", "project/qc"): api_qc,
    ("GET", "project/shorts"): api_shorts,
    ("POST", "project/short"): api_short_make,
    ("POST", "project/cards"): api_cards_render,
    ("POST", "music/scan"): api_music_scan,
    ("GET", "music/removed"): api_music_removed,
    ("POST", "music/remove"): api_music_remove,
    ("GET", "search"): api_search,
    ("POST", "project/write-description"): api_write_description,
    ("POST", "project/titles"): api_titles,
    ("GET", "project/frames"): api_frames,
    ("GET", "new-recordings"): api_new_recordings,
    ("POST", "project/cleanup"): api_cleanup,
    ("GET", "project/stats"): api_stats,
    ("GET", "report"): api_report,
    ("GET", "project/va"): api_va,
    ("GET", "project/revisions"): api_revisions,
    ("POST", "project/revisions"): api_revisions,
    ("POST", "project/rebuild-notes"): api_rebuild_notes,
    ("POST", "project/send-audit"): lambda q, body: {"ok": send_audit(_doc(q))},   # hand the last draft audit to the AI
    ("POST", "project/phone-send"): api_phone_send,
    ("GET", "project/factory"): api_factory,
    ("POST", "project/factory"): api_factory,
    ("GET", "jobs"): api_jobs,
    ("GET", "machines"): api_machines,
    ("GET", "schedule"): lambda q, body: schedule.view(),
    ("POST", "project/schedule"): api_project_schedule,
    ("POST", "schedule/when"): api_schedule_when,
    ("POST", "schedule/cancel"): lambda q, body: {"item": schedule.cancel(body.get("id")), "schedule": schedule.view()},
    ("POST", "schedule/mirror"): lambda q, body: {"item": schedule.upsert(body)},   # the other machine's copy of an entry
    ("POST", "peer/jobs"): lambda q, body: (remote.set_peer(body.get("name"), body.get("jobs")), {"ok": True})[1],
    ("POST", "note-preview"): api_note_preview,
    ("GET", "external"): api_external,
    ("GET", "chat"): api_chat,
    ("POST", "chat/send"): api_chat_send,
    ("POST", "chat/login"): api_chat_login,
    ("POST", "chat/reset"): api_chat_reset,
    ("POST", "notify/test"): api_notify_test,
    ("GET", "job"): api_job,
    ("POST", "job/cancel"): api_job_cancel,
    ("POST", "job/move"): api_job_move,
    ("GET", "settings"): api_settings,
    ("POST", "settings"): api_settings,
    ("GET", "devices/key"): api_devices_key,
    ("POST", "devices/add"): api_devices_add,
    ("GET", "browse"): api_browse,
    ("GET", "recent"): api_recent_recordings,
    ("POST", "recent/rename"): api_rename_recording,
    ("GET", "probe"): api_probe,
    ("GET", "detect"): api_detect,
    ("GET", "editor"): api_editor,
    ("GET", "transitions"): api_transitions,
    ("GET", "thumbnails"): api_thumbnails,
    ("POST", "thumbnails/export"): api_thumbnails_export,
    ("GET", "music"): api_music,
    ("POST", "open"): api_open,
    ("POST", "clipboard"): api_clipboard,
}
ROUTES.update(music_setup.ROUTES)   # kit: Set up your music
ROUTES.update(setup_wizard.ROUTES)   # kit: first-run setup wizard (app/setup_wizard.py)
ROUTES.update(mystyle.ROUTES)   # My video types (my_style: custom types, learned rules, the New video type wizard)
# Export to a video editor (tools/nle_export.py, 2026-10-29): the current cut as Premiere / Resolve XML, FCPXML, EDL or OTIO
sys.path.insert(0, str(Path(__file__).parent / "tools"))
import nle_export  # noqa: E402


def _nle(fn):
    def call(q, body):
        try:
            return fn(q, body)
        except (ValueError, FileNotFoundError) as e:   # "no cut yet", "CapCut can't open it": said as it is
            raise ApiError(str(e))
    return call


ROUTES.update({k: _nle(fn) for k, fn in nle_export.ROUTES.items()})
# Caption fixes (tools/caption_fixes.py, 2026-10-29): the editor's typo fixes + undo of the AI typo pass, and the words /
# caption groups each captioned video showed (project/captions)
import caption_fixes  # noqa: E402
ROUTES.update({k: _nle(fn) for k, fn in caption_fixes.ROUTES.items()})
# Rule gate as a background job (app/gate_bg.py, 2026-10-29): the revision reports the draft first, the gate runs after
import gate_bg  # noqa: E402
ROUTES.update({k: _nle(fn) for k, fn in gate_bg.ROUTES.items()})
# Intro text fixes (tools/intro_text.py, 2026-10-29): double-click the intro's words in the Editor / Watch player, retype
# them; the intro re-renders with the new words (same shots, no AI plan) now or with the next draft
import intro_text  # noqa: E402
ROUTES.update({k: _nle(fn) for k, fn in intro_text.ROUTES.items()})
intro_text.BUILD = lambda doc: start_build(doc, "intro", machine="here")

# Creator tools (overnight 2026-10-29): competitor insights (what's working, gaps, channels) + Claude tools (Title Lab,
# Idea Brainstorm, Comment Miner, Hook Doctor, Repurpose Kit) as background jobs; ui/creator_tools.js
import creator_tools  # noqa: E402
ROUTES.update({k: _nle(fn) for k, fn in creator_tools.ROUTES.items()})



# ------------------------------------------------------------------ who is asking (assistant access, 2026-10-25)
# The user's virtual assistant reviews + revises drafts from her phone (user: "they can watch the video, make revisions,
# rebuild it themselves ... they don't need my approval, they can approve it"). She reaches the Studio through Tailscale
# (the user shares this PC with her Tailscale account); Tailscale Serve adds Tailscale-User-Login to every request.
# No header = this PC itself (the app window) = the owner. settings.owner_logins / settings.assistants =
# [{"name": "...", "login": "her tailscale login", "telegram": <chat id>}].
ASSISTANT_GET = {"state", "project", "jobs", "job", "machines", "schedule", "project/revisions", "chat", "project/caption-fix", "project/captions", "project/intro-text"}
# uploads (user 2026-10-27: "I want her to do the title plus publishing on her own"): type the title + Publish, re-check claims
# no uploads (2026-10-27, user: "she can do the title from the YouTube studio ... I just wanted her to have edit access so
# she can actually edit the video"): titles + publishing happen in YouTube Studio, the final say is his
ASSISTANT_POST = {"project/notes", "project/phone-send", "project/rebuild-notes", "project/run", "project/update", "transcribe",
                  "project/caption-fix",   # caption typo fixes from the editor (2026-10-29)
                  "project/intro-text"}    # ...and the intro's words


def who(headers):
    login = (headers.get("Tailscale-User-Login") or "").strip().lower()
    if not login:
        # came in through Tailscale Serve (it adds X-Forwarded-For) without a login: a shared-in or tagged device, whose
        # requests may carry no identity header. Never the owner (2026-10-27, sharing the PC with the assistant).
        if headers.get("X-Forwarded-For") or headers.get("Tailscale-Funnel-Request"):
            return "nobody", {"login": "?"}
        return "owner", None
    s = store.settings()
    if login in [x.lower() for x in s.get("owner_logins") or ["owner@example.com"]]:
        return "owner", None
    a = next((x for x in s.get("assistants") or [] if (x.get("login") or "").lower() == login), None)
    return ("assistant", a) if a else ("nobody", {"login": login})


def assistant_allowed(role, method, path, q, body):
    if role == "nobody":
        return False, "this Tailscale account has no access to the Studio (ask the owner to add you as an assistant)"
    if not path.startswith("/api/"):
        if path in ("/media", "/thumb", "/file"):   # videos / pictures of projects only
            p = os.path.normcase(os.path.abspath(q.get("path") or ""))
            roots = [os.path.normcase(r) for r in (r"{{PROJECTS_ROOT}}", r"{{GAMING_ROOT}}")]
            return (any(p.startswith(r + os.sep) for r in roots), "not a project file")
        return True, ""   # the UI itself (m.html ...)
    route = path[5:].strip("/")
    if method == "GET":
        return route in ASSISTANT_GET, "not allowed for assistants"
    if route not in ASSISTANT_POST:
        return False, "not allowed for assistants (owner only)"
    if route == "project/run" and (body or {}).get("action", "draft") not in ("draft", "revise", "intro"):
        return False, "assistants can build drafts only"
    if route == "uploads/publish" and (body or {}).get("force"):
        return False, "this video has an open copyright claim: the owner decides"
    if route == "project/update":
        keys = set((body or {}).keys())
        if keys - {"checklist"} or set(((body or {}).get("checklist") or {}).keys()) - {"approved"}:
            return False, "assistants can only approve"
    return True, ""


def after_assistant(person, method, path, q, body):
    """tell the owner what the assistant did that matters (an approval, a publish)"""
    try:
        it = {}   # kit: no uploads
        if it and (body or {}).get("title", "").strip() and it.get("stage") in ("needs_title", "publishing") and it.get("video_id") \
                and (it.get("copyright") or {}).get("state") not in ("claimed", "fixing", "needs_look"):
            d = store.load((body or {}).get("id", ""))
            notify.notify("Published by your assistant", f"{(person or {}).get('name', 'Assistant')} is publishing "
                          f"{d['title'] if d else '?'} as \"{(body or {}).get('title', '')}\".", tg=True, pid=(body or {}).get("id"))
        if path.endswith("project/update") and ((body or {}).get("checklist") or {}).get("approved"):
            d = store.load(q.get("id", ""))
            notify.notify("Approved by your assistant", f"{(person or {}).get('name', 'Assistant')} approved {d['title'] if d else q.get('id')} for upload.",
                          tg=True, pid=q.get("id"))
    except Exception:  # noqa
        traceback.print_exc()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quiet
        if os.environ.get("STUDIO_DEBUG"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        # gzip the big ones (state is ~650 KB every 15 s, ~10x smaller zipped; matters most on the phone over Tailscale)
        gz = len(data) > 16384 and "gzip" in (self.headers.get("Accept-Encoding") or "")
        if gz:
            import gzip
            data = gzip.compress(data, compresslevel=4)
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if gz:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _route(self, method):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        path = u.path
        try:
            role, person = who(self.headers)
            if role != "owner":
                body0 = None
                if role == "assistant" and path == "/api/transcribe":
                    pass   # voice notes: raw audio, handled below like for the owner
                elif method == "POST" and path.startswith("/api/"):
                    n = int(self.headers.get("Content-Length") or 0)
                    body0 = json.loads(self.rfile.read(n) or b"{}") if n else {}
                allowed, why = (True, "") if role == "assistant" and path == "/api/transcribe" else assistant_allowed(role, method, path, q, body0)
                if not allowed:
                    return self._json({"error": why}, 403)
                q["_role"], q["_by"] = role, (person or {}).get("name") or "assistant"
                if body0 is not None:   # the body was read for the check: run the route with it
                    fn = ROUTES.get((method, path[5:].strip("/")))
                    if not fn:
                        raise ApiError("no such route " + path, 404)
                    out = fn(q, body0)
                    after_assistant(person, method, path, q, body0)
                    return self._json(out)
            if path == "/api/transcribe" and method == "POST":   # 🎙 buttons: raw audio in, text out (local Whisper)
                n = int(self.headers.get("Content-Length") or 0)
                data = self.rfile.read(n) if n else b""
                return self._json({"text": speech.transcribe_bytes(data, note_mode=q.get("mode") == "note")})
            if path.startswith("/api/"):
                body = {}
                if method == "POST":
                    n = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(n) or b"{}") if n else {}
                fn = ROUTES.get((method, path[5:].strip("/")))
                if not fn:
                    raise ApiError("no such route " + path, 404)
                return self._json(fn(q, body))
            if path == "/media":
                return self._media(q["path"])
            if path == "/thumb":
                t = float(q["t"]) if q.get("t") else None
                p = media.thumb(q["path"], t=t, w=int(q.get("w", 480)), crop=q.get("crop") or None)
                if not p:
                    return self._json({"error": "no thumb"}, 404)
                return self._file(p, "image/jpeg", cache=True)
            if path == "/file":
                return self._file(q["path"], mimetypes.guess_type(q["path"])[0] or "application/octet-stream")
            # static UI
            rel = "index.html" if path in ("/", "") else path.lstrip("/")
            f = (UI / rel).resolve()
            if UI.resolve() not in f.parents or not f.is_file():
                return self._json({"error": "not found"}, 404)
            return self._file(f, mimetypes.guess_type(str(f))[0] or "application/octet-stream")
        except ApiError as e:
            return self._json({"error": str(e)}, e.code)
        except (ConnectionAbortedError, BrokenPipeError):
            return
        except Exception as e:  # noqa
            traceback.print_exc()
            return self._json({"error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-2000:]}, 500)

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_HEAD(self):
        self._route("GET")

    def _file(self, path, ctype, cache=False):
        path = str(path)
        if not os.path.exists(path):
            return self._json({"error": "not found"}, 404)
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def _media(self, path):
        if not os.path.exists(path):
            return self._json({"error": "not found"}, 404)
        size = os.path.getsize(path)
        ctype = mimetypes.guess_type(path)[0] or "video/mp4"
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                    if m.group(2):
                        end = min(int(m.group(2)), size - 1)
                elif m.group(2):
                    start = max(0, size - int(m.group(2)))
            if start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        length = end - start + 1
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)


def serve(port, block=True):
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    # STUDIO_WORKER=1 (the laptop, 2026-10-25): builds what it is given and runs its schedule, but makes no projects of its own
    # (the desktop's watchers do) and resumes no revision chats (no Claude CLI there)
    worker = bool(os.environ.get("STUDIO_WORKER"))
    if not os.environ.get("STUDIO_TEST"):   # a test copy on a spare port must not watch folders, resume chats or adopt builds
        if not worker:
            extras2.start_watcher()
            auto_send_loop()
            chat.watchdog()   # resumes revision runs that stopped early (or that a closed studio dropped)
        external.start()
        speech.warm()
        schedule.start()
        remote.on_poll(pull_remote_results)
        remote.start()
    httpd.daemon_threads = True
    if block:
        print(f"{{STUDIO_NAME}} API on http://127.0.0.1:{port}", flush=True)
        httpd.serve_forever()
    else:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


if __name__ == "__main__":
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else store.settings()["port"])

"""Intro text fixes from the Editor / Watch player (user 2026-10-29: "why can't I click on the intro text inside my intro?
... double-click on it, type it in, and it'll change it").

studio.json "intro_text_fixes" = [{id, old, new, t, added}], applied in order by intro_library/text_fixes.py: the next
draft re-renders the kept intro with the new words (review_intro retext, same shots, no AI plan), or right away with
POST {"apply": true} (an intro-only build on this PC, ~4-5 min at 60 fps). Product review intros only (intro/build/index.html).

GET  project/intro-text?id=[&video=][&t=]  -> {dur, in_video, fixes, items: [{label, text}]} the intro's words at t
POST project/intro-text?id=  {old, new, t?} add | {undo: id} drop | {apply: true} re-render the intro now"""
import json
import re
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
LIB = Path(r"{{KIT}}/tools\intro_library")
BUILD = None   # server.py: doc -> starts the intro-only build here


def _store():
    sys.path.insert(0, str(APP))
    import store
    return store


def _doc(q):
    doc = _store().load(q.get("id", ""))
    if not doc:
        raise ValueError("no such project")
    return doc


def _intro(doc):
    """(build dir, window.INTRO) of the project's built intro, else (None, None)"""
    b = Path(doc["path"]) / "intro" / "build"
    if doc.get("type") != "review" or not (b / "index.html").exists():
        return None, None
    sys.path.insert(0, str(LIB))
    import text_fixes
    try:
        return b, text_fixes.read_intro(b)
    except Exception:
        return None, None


def _items(I, t):
    """what the intro shows around t: the line being said (its words) and the title"""
    out, W = [], I.get("words") or []
    lines = I.get("lines") or []
    ln = next((x for x in lines if x.get("s", 0) - 0.1 <= t <= x.get("e", 0) + 0.25), None) or \
        min(lines, key=lambda x: abs(x.get("s", 0) - t), default=None)
    if ln:
        a, b = (ln.get("wi") or [None, None])[:2]
        words = [w.get("w", "") for w in W[a:b + 1]] if a is not None else []
        text = re.sub(r"\s+", " ", " ".join(words)).strip() or ln.get("text", "")
        if text:
            out.append({"label": "Words on screen", "text": text, "s": ln.get("s"), "e": ln.get("e")})
    # the title is offered every time: templates also build other words from it (R02's search bar "looking for ...")
    title = str(I.get("title") or "").strip()
    if title:
        out.append({"label": "Intro title (also its search bar / headings)", "text": title})
    return out


def api_get(q, body):
    doc = _doc(q)
    b, I = _intro(doc)
    fixes = doc.get("intro_text_fixes") or []
    if not I:
        return {"dur": 0, "in_video": False, "fixes": fixes, "items": []}
    dur = float(I.get("dur") or 0)
    v = str(q.get("video") or "")
    # the intro is only in the joined videos (final_intro.mp4, preview_intro_540p.mp4), from 0 s
    in_video = not v or "intro" in v.lower()
    t = q.get("t")
    items = _items(I, float(t)) if in_video and t not in (None, "") and float(t) <= dur + 0.2 else []
    return {"dur": dur, "in_video": in_video, "fixes": fixes, "items": items}


def api_post(q, body):
    store = _store()
    doc = _doc(q)
    body = body or {}
    fixes = list(doc.get("intro_text_fixes") or [])
    if body.get("apply"):
        if not _intro(doc)[1]:
            raise ValueError("this project has no built intro yet")
        if not BUILD:
            raise ValueError("close and reopen Studio once to turn this on")
        doc["intro_retext"] = True
        try:
            job = BUILD(doc)
        finally:
            d = store.load(doc["id"])
            d.pop("intro_retext", None)
            store.save(d)
        return {"ok": True, "job": job.view() if hasattr(job, "view") else None}
    if body.get("undo"):
        fixes = [f for f in fixes if f.get("id") != body["undo"]]
    else:
        old, new = str(body.get("old") or "").strip(), str(body.get("new") or "").strip()
        if not old or not new or old == new:
            raise ValueError("need old and new text")
        t = body.get("t")
        fixes.append({"id": f"intro:{int(time.time() * 1000)}", "old": old, "new": new,
                      "t": None if t is None else round(float(t), 2), "added": time.strftime("%Y-%m-%d %H:%M:%S")})
    doc["intro_text_fixes"] = fixes
    store.save(doc)
    return {"ok": True, "fixes": fixes, "applies": "on the next draft, or now with Update the intro"}


ROUTES = {("GET", "project/intro-text"): api_get, ("POST", "project/intro-text"): api_post}

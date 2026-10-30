"""Anonymous edit stats: how the AI's cuts held up, so the kit's cutting gets better for everyone.

On by default (Settings has the off switch, setup says so). Sent once per finished video (when a final render exists) to the
kit's upload-only collector. Numbers only, never words, names, file paths, audio or video:
  video type, raw and final length, how many drafts / finals / revisions / notes, the LENGTHS of cuts the user added
  (the AI missed them) and of parts the user brought back (the AI cut too much), B-roll added, days from start to final,
  and the custom type's settings when the video uses one.
Each kit has a random install id (Studio/data/install_id.txt, kept across updates); "Delete my stats" removes its rows.
"""
import hashlib
import json
import re
import threading
import time
import urllib.request
import uuid

import media
import store

URL = "https://creator-studio-edits.supershifteryt.workers.dev"
SENT = store.DATA / "edit_stats_sent.json"
ID_FILE = store.DATA / "install_id.txt"
_started = False


def enabled():
    return bool(store.settings().get("share_stats", True))


def install_id():
    try:
        v = ID_FILE.read_text(encoding="utf-8").strip()
        if v:
            return v
    except OSError:
        pass
    v = str(uuid.uuid4())
    ID_FILE.write_text(v, encoding="utf-8")
    return v


def _secs(t):
    parts = [float(x) for x in t.split(":")]
    s = 0.0
    for x in parts:
        s = s * 60 + x
    return s


def _span_lengths(notes, kind):
    out = []
    for n in notes:
        if n.get("kind") != kind:
            continue
        m = re.search(r"(\d+(?::\d+){0,2}(?:\.\d+)?)\s*-\s*(\d+(?::\d+){0,2}(?:\.\d+)?)", n.get("text", ""))
        if m:
            length = _secs(m.group(2)) - _secs(m.group(1))
            if 0 < length < 3600:
                out.append(round(length, 1))
    return out


def _duration(path):
    try:
        return round(media.probe(path)["duration"] or 0, 1) if path else 0
    except Exception:
        return 0


def _days(a, b):
    try:
        fmt = "%Y-%m-%d %H:%M"
        return round((time.mktime(time.strptime(b[:16], fmt)) - time.mktime(time.strptime(a[:16], fmt))) / 86400, 1)
    except Exception:
        return None


def summarize(doc):
    """The numbers sent for one finished project (no text from the project ever goes in here)."""
    notes = doc.get("notes") or []
    renders = doc.get("renders") or []
    finals = [r for r in renders if r.get("kind") == "final"]
    raw_s = _duration(doc.get("source"))
    final_s = _duration(finals[-1].get("file")) if finals else 0
    custom = None
    try:
        import custom_types   # the custom video types feature, when this kit has it
        custom = custom_types.type_summary(doc.get("type"))
    except Exception:
        pass
    return {
        "v": 1,
        "type": str(doc.get("type") or "")[:32] if not custom else "custom",
        "custom_type": custom,
        "raw_s": raw_s,
        "final_s": final_s,
        "kept_ratio": round(final_s / raw_s, 3) if raw_s and final_s else None,
        "drafts": sum(1 for r in renders if r.get("kind") == "draft"),
        "finals": len(finals),
        "revisions": sum(1 for n in notes if n.get("kind") == "revision"),
        "notes": sum(1 for n in notes if n.get("kind") == "text"),
        "ai_missed_cuts_s": _span_lengths(notes, "cut"),
        "ai_overcut_s": _span_lengths(notes, "protect"),
        "broll_added": sum(1 for n in notes if n.get("kind") == "broll"),
        "days_to_final": _days(doc.get("created", ""), finals[-1].get("when", "")) if finals else None,
    }


def _post(path, payload):
    req = urllib.request.Request(URL + path, data=json.dumps(payload).encode(), method="POST",
                                 headers={"content-type": "application/json", "user-agent": "creator-studio-kit"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def sweep():
    """Send stats for finished projects not sent yet (or with a newer final since). Quietly retries next time on failure."""
    if not enabled():
        return 0
    sent = store.read_json(SENT, {}) or {}
    me = install_id()
    try:
        ver = str(store.read_json(store.HOME.parent / "KIT_VERSION.json", {}).get("version", ""))
    except Exception:
        ver = ""
    n = 0
    for doc in store.all_projects():
        finals = [r for r in (doc.get("renders") or []) if r.get("kind") == "final"]
        if not finals:
            continue
        key = hashlib.sha256((me + doc["id"]).encode()).hexdigest()[:16]
        if sent.get(key) == len(finals):
            continue
        edit = summarize(doc)
        edit["project"] = key
        try:
            if _post("/v1/edits", {"install_id": me, "kit_version": ver, "video_type": edit["type"], "edit": edit}).get("ok"):
                sent[key] = len(finals)
                n += 1
        except Exception:
            break   # offline / collector down: try again on the next sweep
    store.write_json(SENT, sent)
    return n


def start():
    """Sweep a minute after the Studio opens, then every 6 hours (background, never blocks a build)."""
    global _started
    if _started:
        return
    _started = True

    def loop():
        time.sleep(60)
        while True:
            try:
                sweep()
            except Exception:
                pass
            time.sleep(6 * 3600)
    threading.Thread(target=loop, daemon=True).start()


def api_get(q, body):
    return {"ok": True, "enabled": enabled(), "install_id": install_id(), "sent": len(store.read_json(SENT, {}) or {})}


def api_set(q, body):
    store.save_settings({"share_stats": bool(body.get("enabled"))})
    return api_get(q, body)


def api_delete(q, body):
    try:
        r = _post("/v1/delete", {"install_id": install_id()})
    except Exception as e:
        return {"ok": False, "error": f"Couldn't reach the stats server ({type(e).__name__}). Try again later."}
    store.write_json(SENT, {})
    return {"ok": True, "deleted": r.get("deleted", 0)}


start()

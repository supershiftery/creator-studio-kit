"""Builds started OUTSIDE the app (another Claude session, a terminal, the {{PROJECTS_ROOT}} watcher) for a known project.
A background thread lists python processes every 5 s; a process whose command line runs one of the pipelines on a
project's folder is an external build. Its stage comes from the files it has written since it started (each pipeline
writes known files in a fixed order), its ETA from the app's learned step times. When it ends, a toast says so."""
import fnmatch
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import jobs
import notify
import store

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
STATE = {"procs": [], "t": 0, "seen": {}}   # seen: project id -> info of the run in progress

SCRIPTS = {   # script file -> (kind, label, milestones in write order)
    "pipeline.py": ("phone", "phone_edit pipeline", [
        ("work/words.json", "Transcript"), ("work/cuts.json", "Trim + take review"), ("work/halves.json", "Which half is cam / phone"),
        ("work/privacy.json", "Privacy: finding the address"), ("work/blank_phone.json", "Dead phone screens"),
        ("edit/cut-full-noblur.mp4", "Full-res cut"), ("edit/cut-full.mp4", "Privacy blur"), ("edit/layout.json", "Layout"),
        ("edit/graphics/events.json", "Graphics plan"), ("edit/graphics/renders/*.mov", "Rendering graphics"),
        ("edit/intro/renders/intro.mp4", "Intro"), ("edit/main-draft.mp4", "Main video: compose + music"),
        ("output/* - DRAFT.mp4", "Join intro + main"), ("output/report.md", "Privacy sweep + QC")]),
    "revise.py": ("phone", "Revision: notes → cuts (Opus)", [("work/extra_cuts.json", "Writing the cuts"), ("work/revisions.json", "Saving the revision")]),
    "edit_review.py": ("review", "product review pipeline", [
        ("work/transcript.json", "Transcript"), ("work/analysis.json", "Camera angles"), ("work/cuts.json", "Cuts + sections"),
        ("output/final.mp4", "Rendering"), ("output/preview_540p.mp4", "540p preview"), ("output/report.md", "Report")]),
}
for g in ("prep", "broll", "transcribe", "sections", "cuts", "body", "assemble", "chapters", "shorts"):
    SCRIPTS[f"{g}.py"] = ("gaming", f"gaming: {g}", [])


def _list_procs():
    ps = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | ForEach-Object { "
          "[pscustomobject]@{pid=$_.ProcessId; ppid=$_.ParentProcessId; cmd=$_.CommandLine; t=$_.CreationDate.ToString('o')} } | ConvertTo-Json -Compress")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=CREATE_NO_WINDOW, timeout=20)
    try:
        d = json.loads(r.stdout or "[]")
    except ValueError:
        return []
    return d if isinstance(d, list) else [d]


def _own_pids():
    """pids of the jobs the app started itself (and their children are matched by parent pid)."""
    out = set()
    for j in jobs.JOBS.values():
        p = getattr(j, "proc", None)
        if p is not None and j.status == "running":
            out.add(p.pid)
    return out


def _norm(p):
    return str(p).replace("/", "\\").rstrip("\\").lower()


def match(doc):
    """The external run working on this project, if any."""
    folder = _norm(doc["path"])
    own = _own_pids()
    procs = STATE["procs"]
    by_pid = {p["pid"]: p for p in procs}
    for p in procs:
        cmd = (p.get("cmd") or "")
        low = cmd.replace("/", "\\").lower()
        if folder not in low:
            continue
        script = next((s for s in SCRIPTS if ("\\" + s) in low or ("/" + s) in cmd.lower()), None)
        if not script:
            continue
        # skip the app's own jobs (the job's process or a child of it)
        if p["pid"] in own or p.get("ppid") in own or by_pid.get(p.get("ppid"), {}).get("ppid") in own:
            continue
        # the innermost python (a pipeline can spawn python children): prefer the parent pipeline process
        parent = by_pid.get(p.get("ppid"))
        if parent and folder in (parent.get("cmd") or "").replace("/", "\\").lower() and any(("\\" + s) in (parent.get("cmd") or "").replace("/", "\\").lower() for s in SCRIPTS):
            continue
        return p, script
    return None, None


def describe(doc):
    p, script = match(doc)
    if not p:
        return None
    kind, label, ms = SCRIPTS[script]
    try:
        started = datetime.fromisoformat(p["t"][:26] + p["t"][-6:] if "+" in p["t"][-6:] or "-" in p["t"][-6:] else p["t"]).timestamp()
    except Exception:
        started = time.time()
    root = Path(doc["path"])
    done_idx = -1
    for i, (pat, _) in enumerate(ms):
        for f in root.glob(pat):
            try:
                if f.stat().st_mtime >= started - 1:
                    done_idx = max(done_idx, i)
            except OSError:
                pass
    if ms:
        cur = ms[min(done_idx + 1, len(ms) - 1)][1] if done_idx >= 0 else "Starting (skipping what is up to date)"
        frac = (done_idx + 1) / len(ms)
    else:
        cur, frac = label, 0.0
    elapsed = time.time() - started
    info = jobs  # learned rate: seconds of build per minute of footage
    minutes = 0.0
    try:
        import media
        if doc.get("source"):
            minutes = media.cached_duration(doc["source"]) / 60
    except Exception:
        pass
    est = jobs.rate(kind if script != "revise.py" else "phone", "pipeline" if script in ("pipeline.py", "revise.py") else ("edit" if script == "edit_review.py" else script[:-3])) * max(minutes, 1)
    own = jobs.registry().get(str(p["pid"]))   # started by the app before a restart: re-adopted, not "outside"
    if own:
        started = own.get("started") or started
        elapsed = time.time() - started
    # past its guess the bar slows down but keeps moving (it sat on 95% before), and the ETA follows the same curve
    f = jobs.eased(elapsed, est) if est else 0.0
    pct = max(frac, f)
    eta = elapsed * (1 - f) / max(f, 0.05) if est else 0
    if own:
        label = own.get("title", label).split(": ", 1)[-1]
    out = {"pid": p["pid"], "script": script, "label": label, "step": cur, "step_index": done_idx + 2 if ms else 1, "step_count": len(ms) or 1,
           "started": started, "elapsed_s": round(elapsed), "eta_s": round(eta), "pct": round(pct * 100, 1), "resumed": bool(own)}
    STATE["seen"][doc["id"]] = {"started": started, "label": label, "title": doc["title"], "pid": p["pid"], "own": own}
    return out


def _loop():
    while True:
        try:
            STATE["procs"] = _list_procs()
            STATE["t"] = time.time()
            # finished external runs -> toast (only for runs we saw while they were going)
            for pid_, seen in list(STATE["seen"].items()):
                doc = store.load(pid_)
                if not doc:
                    STATE["seen"].pop(pid_, None)
                    continue
                p, _ = match(doc)
                if p is None:
                    STATE["seen"].pop(pid_, None)
                    import chat   # late import: chat imports jobs/store too
                    quiet = chat.run_active(doc)   # a revision run's build: "Revisions done" is the one notice
                    secs = time.time() - seen["started"]
                    mins = round(secs / 60)
                    own = seen.get("own")
                    if own and own.get("job") in jobs.JOBS:
                        # a build THIS app session is running (finished, failed or cancelled): its own on_done reports it.
                        # Reporting it here too sent "Build ended ... no new render" for a cancelled build (2026-10-22)
                        continue
                    if own:   # the app's own build, re-adopted after a restart: same messages + history as a normal build
                        jobs.registry_drop_pid(seen.get("pid"))
                        action = own.get("title", "").rsplit(": ", 1)[-1]
                        from recipes import get as recipe
                        outs = recipe(doc["type"]).outputs(doc)
                        newest = max((o for o in outs if os.path.exists(o["file"])), key=lambda o: os.path.getmtime(o["file"]), default=None)
                        ok = bool(newest) and os.path.getmtime(newest["file"]) >= seen["started"] - 5
                        doc.setdefault("builds", []).append({"action": action, "when": store.now(), "secs": round(secs), "status": "done" if ok else "unknown",
                                                             "minutes": round(own.get("minutes") or 0, 1), "steps": [], "note": "re-adopted after an app restart"})
                        if ok:
                            store.add_render(doc, newest["file"], newest["kind"])
                        store.save(doc)
                        if ok and action == "final":
                            notify.notify("FINAL rendered", f"{doc['title']} · {mins} min. Check it, then send it to Drive.")
                        elif ok:
                            quiet or notify.notify("Draft ready to review", f"{doc['title']} · built in {mins} min. Open it in the Studio editor.", pid=doc["id"])
                        else:
                            quiet or notify.notify("Build ended", f"{doc['title']} · {action} · {mins} min, but no new render appeared: check the log.")
                    else:
                        quiet or notify.notify("Build finished (outside the app)", f"{seen['title']} · {seen['label']} · {mins} min. Open it in {{STUDIO_NAME}}.")
            # discover new external runs even when nobody has the project open
            for doc in store.all_projects():
                if doc["id"] not in STATE["seen"]:
                    d = describe(doc)
                    if d and not d.get("resumed"):
                        notify.toast("Build started (outside the app)", f"{doc['title']} · {d['label']}")
        except Exception:
            pass
        time.sleep(5)


def start():
    threading.Thread(target=_loop, daemon=True).start()

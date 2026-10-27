"""Per-project chat with Claude, through the Claude Code CLI in print mode (uses your Claude subscription, not API
credits), pinned to Opus 5.5 for revisions. Each project keeps one CLI session (resumed every message) and a
transcript in <project>/studio-chat.json. Claude runs inside the project folder with edit + bash tools allowed, so it
can change sections, add notes, rebuild drafts and fix things itself."""
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import store

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
MODEL = "claude-opus-5-5"
STATE = {}   # project id -> {"busy": bool, "started": t, "error": str}
APP = Path(__file__).resolve().parent
HOME = APP.parent


def claude_exe():
    for c in (os.path.expanduser("~/.local/bin/claude.exe"), os.path.expanduser("~/.local/bin/claude"), "claude"):
        if os.path.exists(c) or c == "claude":
            return c
    return "claude"


def transcript_path(doc):
    return Path(doc["path"]) / "studio-chat.json"


def load(doc):
    return store.read_json(transcript_path(doc), {"session": "", "messages": []}) or {"session": "", "messages": []}


def save(doc, data):
    store.write_json(transcript_path(doc), data)


def system_prompt(doc):
    port = store.settings().get("port", 8765)
    rules = ("Deliverables are H.264 High yuv420p + AAC MP4, never HEVC. Instrumental music only, no vocals or producer tags. "
             "No dates in on-screen graphics. Drafts are half-size; finals only after the user approves. Follow the user's editing rules "
             "in the minecraft-video, phone-tutorial-edit and product-review-edit skills and in your memory notes. "
             # several Claudes fix the SAME shared pipeline for their own video and nobody re-checked the others (2026-10-23:
             # "fixes come back broken"); the regression suite replays every review video's cut decisions in ~5 min
             # 2026-10-24 speed pass: one batch spent 30 of its first 42 min on 5 replays before it even started a build
             "AFTER a change to the shared review pipeline (edit_review.py, joins.py, take_cuts.py, any guard; baseline.json is "
             "the 'before', no replay needed first): START THIS VIDEO'S BUILD FIRST, then run python \"{{KIT}}/tools\\"
             "regress\\regress.py\" --replay WHILE it builds (shadow copies, real projects untouched, ~1-2 min, the replays run in "
             "parallel) and read regress_report.md. Your change is done only with 0 REGRESSION lines and every new 'drift (now "
             "cut)' on an approved video explained; otherwise narrow the rule to your case and replay once more. To find which of "
             "your rules causes a drift, reason from the report's times first; replay with switches off only as a last resort. "
             "Another Claude may be editing the same files: re-read a file right before you edit it.")
    api = (f"The studio API is at http://127.0.0.1:{port}. Useful calls (curl): "
           f"GET /api/project?id={doc['id']} (everything about the project), "
           f"POST /api/project/notes?id={doc['id']} with JSON {{\"text\": \"cut 1:22-1:30\"}} or {{\"kind\":\"cut\",\"raw0\":s,\"raw1\":e,\"text\":\"why\"}} (raw recording seconds), "
           f"POST /api/project/sections?id={doc['id']} with {{\"sections\":[{{\"name\":\"#5 Name\",\"s\":669.0,\"e\":931.7}}]}} (gaming), "
           f"POST /api/project/run?id={doc['id']} with {{\"action\":\"draft\"}} or \"final\" (builds in the background; the user gets a notification when it is ready; "
           f"review: a built intro is reused as it is unless you add \"intro\":\"rebuild\"; one build per revision batch, check with frames, not rebuilds), "
           f"POST /api/project/update?id={doc['id']} with {{\"settings\": {{...}}, \"thumb_brief\": \"...\"}}. GET /api/jobs shows running builds.")
    layout = {"gaming": "Gaming project: work files in Edit\\studio (words.json transcript, sections.json, cuts\\cuts.json, timeline-draft.json), outputs in Edit\\. Pipeline scripts: " + str(APP / "gaming") + " (prep, broll, transcribe, sections, cuts, body, assemble, chapters).",
              "phone": "Phone/app project: raw\\source.mp4, work\\ (words.json, cuts.json, extra_cuts.json), edit\\ (layout.json, graphics\\, intro\\), output\\. Pipeline: {{KIT}}/tools\\phone_edit\\pipeline.py <project>.",
              "review": "Product review project: raw\\camera.mp4 or raw\\edit.xml, raw\\extra_cuts.json, work\\, output\\final.mp4. Pipeline: hermes product-review-edit edit_review.py <project>.",
              "short": "Short project (a raw vertical recording edited as its own Short): raw\\clips\\, raw\\source.mp4 (normalised 1080x1920 60 fps), Edit\\studio\\ (words.json, cuts\\cuts.json, timeline-short.json), '<title> - DRAFT.mp4'. Pipeline: app\\tools\\haul_normalise.py, gaming prep/transcribe/cuts, app\\tools\\haul_render.py (SHORT mode); skill short-edit.",
              "haul": "Haul project (one phone recording, products back to back): raw\\clips\\ (phone clips), raw\\source.mp4 (normalised 1080p60 join), Edit\\studio\\ (words.json, cuts\\cuts.json, haul_structure.json, timeline-haul.json), '<title> - DRAFT.mp4'. Pipeline: app\\tools\\haul_normalise.py, gaming prep/transcribe/cuts, app\\tools\\haul_render.py; skill haul-edit."}[doc["type"]]
    return (f"You are Claude inside {{STUDIO_NAME}}, the user's video app, chatting about ONE project for revisions and drafts. "
            f"Project: '{doc['title']}' ({doc['type']}, channel {doc.get('channel') or '?'}), folder {doc['path']}. {layout} "
            f"Studio app code: {HOME}. {api} {rules} "
            + (f"The user's special requests for this video (written when the project was made; keep them true in every later revision): "
               f"{(doc.get('settings') or {}).get('requests', '').strip()!r}. " if (doc.get("settings") or {}).get("requests", "").strip() else "") +
            "Be concrete and short. When the user asks for a change, make it (edit files / add notes / sections / rebuild through the API) and say what you did and what they should check. "
            "Prefer notes + rebuild over hand-editing render outputs. Never delete footage. Ask only when a choice really matters. "
            "You run headless (claude -p): when your turn ends nothing wakes you up, and background Agents / run_in_background "
            "commands die with you (Top 10 Servers, 2026-10-22: the turn ended 'waiting for the music helper' and the job sat "
            "there). So do every step in the foreground, wait for builds by polling /api/jobs in a loop, and never end your "
            "turn while something you started is still running. If you are stopped anyway, the studio resumes you.")


def ask(doc, message, timeout=1800, add_dirs=()):
    """Blocking: send one message, return the reply. Called from a thread by the server.
    add_dirs: extra folders Claude may write in (the study turn writes memory, skills and teach examples)."""
    pid = doc["id"]
    data = load(doc)
    data["messages"].append({"role": "user", "text": message, "t": store.now()})
    save(doc, data)
    STATE[pid] = {"busy": True, "started": time.time(), "error": "", "steps": []}
    # stream-json: one event per line, so the app can show what Claude is doing while it works (not just "on it…")
    cmd = [claude_exe(), "-p", message, "--model", MODEL, "--output-format", "stream-json", "--verbose", "--permission-mode", "acceptEdits",
           "--allowedTools", "Bash", "Read", "Edit", "Write", "Glob", "Grep", "WebFetch",
           "--add-dir", str(HOME), *[x for d in add_dirs for x in ("--add-dir", str(d))], "--append-system-prompt", system_prompt(doc)]
    if data.get("session"):
        cmd += ["--resume", data["session"]]
    else:
        data["session"] = str(uuid.uuid4())
        cmd += ["--session-id", data["session"]]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    reply, meta = "", {}
    try:
        proc = subprocess.Popen(cmd, cwd=doc["path"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                errors="replace", creationflags=CREATE_NO_WINDOW, env=env, stdin=subprocess.DEVNULL)
        if data.get("run"):   # so a restarted studio sees this turn is still going and doesn't start a second one
            data["run"]["pid"] = proc.pid
            save(doc, data)
        killed = []
        timer = threading.Timer(timeout, lambda: (killed.append(1), proc.kill()))
        timer.start()
        final, other = None, []
        try:
            for line in proc.stdout:
                try:
                    ev = json.loads(line)
                except ValueError:
                    other.append(line)
                    continue
                if ev.get("type") == "result":
                    final = ev
                elif ev.get("type") == "assistant":
                    for b in (ev.get("message") or {}).get("content") or []:
                        _step(pid, b)
        finally:
            timer.cancel()
            proc.wait()
        if killed:
            raise subprocess.TimeoutExpired(cmd, timeout)
        if final is not None:
            j = final
            reply = j.get("result") or ""
            meta = {k: j.get(k) for k in ("session_id", "total_cost_usd", "duration_ms", "num_turns", "subtype")}
            if j.get("session_id"):
                data["session"] = j["session_id"]
            if j.get("is_error") or j.get("subtype", "").startswith("error"):
                reply = reply or f"(claude error: {j.get('subtype')})"
        else:
            reply = "".join(other).strip()[-1500:] or "(no reply)"
        if "Not logged in" in reply or "/login" in reply:
            reply = "The Claude Code CLI on this PC is not signed in yet. Click **Sign in** above (it opens a terminal with `claude auth login`, finish in the browser), then send your message again."
            STATE[pid]["error"] = "login"
    except subprocess.TimeoutExpired:
        reply = "(Claude took longer than the limit and was stopped. Try a smaller ask.)"
    except FileNotFoundError:
        reply = "The `claude` CLI was not found. Install Claude Code (npm i -g @anthropic-ai/claude-code) or add it to PATH."
    data = {**load(doc), "session": data["session"]}   # the run record may have changed while Claude worked
    data["messages"].append({"role": "assistant", "text": reply, "t": store.now(), "meta": meta})
    if data.get("run"):
        data["run"].pop("pid", None)
        data["run"]["last_end"] = store.now()
        if STATE[pid].get("error") == "login":
            data["run"]["blocked"] = "login"
    save(doc, data)
    STATE[pid] = {"busy": False, "started": 0, "error": STATE[pid].get("error", ""), "steps": STATE[pid].get("steps", [])}
    return reply


def _short(s, n=110):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def _step(pid, b):
    """One streamed content block -> a plain-words activity line ("Editing layout.json", "Rebuilding the draft")."""
    kind, inp = b.get("type"), b.get("input") or {}
    if kind == "text" and b.get("text", "").strip():
        line = "💬 " + _short(b["text"], 160)
    elif kind != "tool_use":
        return
    else:
        name, fname = b.get("name", ""), Path(str(inp.get("file_path") or inp.get("path") or "")).name
        cmd = str(inp.get("command") or "")
        if name == "Bash":
            if "pipeline.py" in cmd or "/api/project/run" in cmd:
                line = "🎬 Rebuilding the draft"
            elif "/api/project/notes" in cmd:
                line = "✓ Marking a revision done"
            elif "ffmpeg" in cmd or "ffprobe" in cmd or "check_video" in cmd:
                line = "🎞 " + (_short(inp.get("description"), 90) or "Checking / rendering video")
            else:
                line = "⚙ " + (_short(inp.get("description"), 90) or _short(cmd, 90))
        elif name in ("Edit", "Write", "NotebookEdit"):
            line = "✏ Editing " + (fname or "a file")
        elif name == "Read":
            line = "📖 Reading " + (fname or "a file")
        elif name in ("Grep", "Glob"):
            line = "🔎 Looking through files"
        else:
            line = "• " + name
    st = STATE.get(pid)
    if st is not None:
        st["steps"] = (st.get("steps", []) + [{"t": round(time.time() - st["started"]), "text": line}])[-40:]


def activity(doc):
    """What the revision Claude is doing right now, for the project page (no transcript)."""
    st = STATE.get(doc["id"], {})
    return {"busy": bool(st.get("busy")), "elapsed": round(time.time() - st["started"]) if st.get("busy") else 0,
            "steps": st.get("steps", [])[-8:]}


def start(doc, message, on_done=None, timeout=1800, add_dirs=()):
    if STATE.get(doc["id"], {}).get("busy"):
        raise RuntimeError("Claude is still answering the previous message")

    def work():
        reply = ask(doc, message, timeout=timeout, add_dirs=add_dirs)
        if on_done:
            try:
                on_done(doc, reply)
            except Exception:
                pass
    threading.Thread(target=work, daemon=True).start()


def status(doc):
    st = STATE.get(doc["id"], {"busy": False, "started": 0, "error": ""})
    return {"busy": st["busy"], "elapsed": round(time.time() - st["started"]) if st["busy"] else 0, "login_needed": st.get("error") == "login", "model": MODEL,
            "transcript": load(doc), "steps": st.get("steps", [])[-8:]}


def open_login():
    """Open a console with the CLI's login flow (browser-based) for the user to finish."""
    subprocess.Popen(["cmd", "/k", claude_exe() + " auth login"], creationflags=0x00000010)   # CREATE_NEW_CONSOLE
    return True


# ---- auto-resume ("I don't want to have to keep looking for it", user 2026-10-22) -------------------------------------------
# A revision batch is a "run" kept in studio-chat.json: {"state": "running", "nids": [...], "started", "resumes", "pid"}.
# Claude's turn can end before the work is done (it waited on a background helper, hit the time limit, or ended while its
# rebuild was still going), and a closed studio drops the turn too. The watchdog checks every running run once a minute
# and when a turn ends: once Claude is not answering and no build is running for the project, a run with open revisions
# or no finished draft since it began gets a "continue" message in the same session (it keeps its context), up to
# MAX_RESUMES times. Then the user gets one message: done, or stuck with what is still open.
MAX_RESUMES = 4
_CHECK_LOCK = threading.Lock()


def pid_alive(pid):
    if not pid:
        return False
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259   # STILL_ACTIVE
    except Exception:
        return False


def run_active(doc):
    """True while a revision run is still working on this project. Its builds are steps, not the end: Claude checks each
    draft and may rebuild, so only check_run's "Revisions done" may tell the user the draft is ready (user 2026-10-22:
    "sometimes I'm watching a video that has not been ran through a QC check yet")."""
    return (load(doc).get("run") or {}).get("state") == "running"


def begin_run(doc, nids, owner=None):
    data = load(doc)
    data["run"] = {"state": "running", "nids": list(nids), "started": store.now(), "resumes": 0}
    if owner:
        data["run"]["owner"] = owner
    save(doc, data)


def _continue_message(open_notes, built, failed):
    ids = ", ".join(n["nid"] for n in open_notes) or "none"
    parts = ["The studio resumed you: your last turn ended before this revision batch was finished. You run headless, so "
             "anything you left running in the background (Agents, background commands) is gone; check what it left on disk "
             "and redo what is missing yourself, in the foreground.",
             f"Revisions not reported yet: {ids}." if open_notes else "Every revision is reported.",
             ("No draft has finished building since the revisions started: rebuild it through the app (POST /api/project/run "
              + ("action \"intro\": every revision here is in the intro, so the intro-only build, which keeps the main edit"
                 if open_notes and all(n.get("scope") == "intro" for n in open_notes) else "draft")
              + "; it waits in the render queue if another video is rendering; poll until done) and check it.") if not built else
             "A draft built since then: check it against the revisions with frames at each note's time; build again only "
             "for a note it shows is still wrong (one build per batch)."]
    if failed:
        parts.append(f"The last build FAILED: {failed}. Fix the cause and rebuild.")
    parts.append("Report each revision through /api/project/notes (applied / failed + how), then finish with a short list of "
                 "what changed and what did not. Don't end your turn while a build you started is still running.")
    return " ".join(parts)


def check_run(doc, dry=False):
    """Decide what a revision run needs now: None (nothing / still working), 'resume', 'done' or 'stuck'."""
    import jobs
    import notify
    with _CHECK_LOCK:
        data = load(doc)
        run = data.get("run")
        if not run or run.get("state") != "running":
            return None
        if STATE.get(doc["id"], {}).get("busy") or pid_alive(run.get("pid")) or jobs.running_for(doc["id"]):
            return None   # Claude is answering, or the build it started is still going: look again later
        d = store.load(doc["id"]) or doc
        open_notes = [n for n in d.get("notes", []) if n.get("nid") in run["nids"] and n.get("status") not in ("applied", "failed")]
        # a chat-owned run may open while its build is already going: the latest build counts there
        since = "" if run.get("owner") == "claude-chat" else run["started"]
        mine = [b for b in d.get("builds", []) if b.get("action") in ("draft", "revise", "intro") and b.get("when", "") >= since]
        built = bool(mine) and mine[-1].get("status") == "done"   # the LAST build (with its QC check) finished, not an earlier one
        failed = ""
        if mine and mine[-1].get("status") == "failed":
            failed = next((f"step {s['label']}" for s in mine[-1].get("steps", []) if s.get("status") == "failed"), "see the build log")
        if not open_notes and built and not failed:
            verdict = "done"
        elif run.get("blocked") or run.get("resumes", 0) >= MAX_RESUMES:
            verdict = "stuck"
        else:
            verdict = "resume"
        if dry:
            return verdict
        if verdict == "resume" and run.get("owner") == "claude-chat":
            # notes being fixed by hand in a Claude Code chat (user 2026-10-22: "always update the status inside of the
            # studio, even if we're doing manual edits inside of Claude"; a draft-ready ping came mid-revision): its
            # builds stay quiet and "Revisions done" goes out once every note is reported and the last build passed QC.
            # Never resumed by the studio: the chat is still working on it.
            return None
        if verdict == "resume":
            run["resumes"] = run.get("resumes", 0) + 1
            save(doc, data)
            try:
                start(d, _continue_message(open_notes, built, failed), on_done=lambda dd, r: check_run(dd), timeout=2 * 3600)
            except RuntimeError:
                run["resumes"] -= 1
                save(doc, data)
                return None
            notify.toast("Revisions resumed", f"{d['title']}: Claude stopped early, picking it back up ({run['resumes']}/{MAX_RESUMES})")
            return verdict
        run["state"], run["ended"] = verdict, store.now()
        save(doc, data)
        if verdict == "done":
            # the build time too (user 2026-10-23: "I like to see how long it takes"): the last build + the whole revision
            took = ""
            try:
                lb = [b for b in d.get("builds", []) if b.get("status") == "done"][-1]
                t0 = time.mktime(time.strptime(run["started"], "%Y-%m-%d %H:%M"))
                took = f" {(time.time() - t0) / 60:.0f} min from sending the revisions to ready for review (last build {lb['secs'] / 60:.1f} min)."
            except Exception:
                took = took + "." if took else ""
            notify.notify("Revisions done", f"{d['title']}: every revision is reported and the final draft is built and QC-checked.{took} Open Review + notes.", pid=d["id"])
        else:
            why = "Claude needs signing in" if run.get("blocked") == "login" else f"stopped {run.get('resumes', 0)} times"
            left = ", ".join(_short(n.get("text"), 40) for n in open_notes[:4]) or ("no finished draft" if not built else failed)
            notify.notify("Revisions need you", f"{d['title']}: {why}. Still open: {left}", tg=True)
        return verdict


def watchdog(interval=60):
    """Started once by the server: resumes revision runs a stopped turn or a studio restart left hanging."""
    def loop():
        time.sleep(20)   # let the server come up first
        while True:
            try:
                for d in store.all_projects():
                    if transcript_path(d).exists():
                        check_run(d)
            except Exception as e:  # noqa: one bad project must not kill the loop
                print("chat watchdog:", e, flush=True)
            time.sleep(interval)
    threading.Thread(target=loop, daemon=True).start()


def reset(doc):
    data = load(doc)
    data["session"] = ""
    data.pop("run", None)   # a new conversation has no context to resume
    data["messages"].append({"role": "system", "text": "— new conversation —", "t": store.now()})
    save(doc, data)

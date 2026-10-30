"""The rule gate as a Studio background job (2026-10-29, speed: "what is the revision really doing").

Mon Clear: the draft was built and checked at 15:48, but the revision Claude sat in rule_gate.py check (every approved
video + every past note replayed) until 16:37 before it said anything. The gate only decides whether the laptop gets the
new code; it never changes the draft he is about to watch. So the revision Claude now queues it here and reports right
away; the gate runs after, one at a time, and its verdict comes as its own message (toast + Telegram + the project chat).

    POST /api/rule-gate {"why": "<the note>", "pid": "<project id>"}   -> {"state": "running" | "queued"}
    GET  /api/rule-gate                                                -> {"state", "why", "started", "last"}
A check asked for while one runs is folded into ONE more run on the final code (the gate fails anyway if the code
changed while it ran). A Studio restart drops a running gate; ask again (nothing is committed until a check passes).
"""
import subprocess
import sys
import threading
import time
from pathlib import Path

import notify

GATE = Path(r"{{KIT}}/tools\regress\rule_gate.py")
LOGS = Path(__file__).resolve().parent.parent / "data" / "joblogs"
CREATE_NO_WINDOW = 0x08000000
BELOW_NORMAL = 0x00004000

_LOCK = threading.Lock()
_S = {"state": "idle", "why": [], "pids": [], "started": "", "pending": None, "last": None}


def _run(whys, pids):
    why = " | ".join(dict.fromkeys(whys))[:600] or "pipeline change"
    LOGS.mkdir(parents=True, exist_ok=True)
    log = LOGS / time.strftime("gate-%Y%m%d-%H%M%S.log")
    t0 = time.time()
    try:
        with open(log, "w", encoding="utf-8") as fh:
            code = subprocess.run([sys.executable, "-X", "utf8", str(GATE), "check", why], cwd=str(GATE.parent),
                                  stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  creationflags=CREATE_NO_WINDOW | BELOW_NORMAL).returncode
        out = log.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # noqa: a crash here must still free the gate
        code, out = 2, f"could not run the gate: {e}"
    mins = (time.time() - t0) / 60
    broke = [l.strip()[2:] for l in out.splitlines() if l.strip().startswith("- ")]
    if code == 0:
        title, body = "Rule gate passed", f"The new rules passed every approved video ({mins:.0f} min). The laptop gets them on its next sync."
    else:
        title = "Rule gate failed"
        body = (f"Nothing changed on the laptop ({mins:.0f} min). " + ("; ".join(broke[:3]) if broke else out.strip()[-300:])
                + ". Your draft is not affected.")
    _S["last"] = {"when": time.strftime("%Y-%m-%d %H:%M"), "ok": code == 0, "why": why, "minutes": round(mins, 1),
                  "broke": broke[:10], "log": str(log)}
    try:
        notify.notify(title, body, pid=pids[-1] if pids else None)
    except Exception:
        pass


def _loop(whys, pids):
    while True:
        _run(whys, pids)
        with _LOCK:
            nxt = _S["pending"]
            _S["pending"] = None
            if not nxt:
                _S.update(state="idle", why=[], pids=[], started="")
                return
            whys, pids = nxt
            _S.update(why=whys, pids=pids, started=time.strftime("%Y-%m-%d %H:%M"))


def queue(why, pid=None):
    with _LOCK:
        if _S["state"] == "running":
            w, p = _S["pending"] or ([], [])
            _S["pending"] = (w + [why], p + ([pid] if pid else []))
            return "queued"
        _S.update(state="running", why=[why], pids=[pid] if pid else [], started=time.strftime("%Y-%m-%d %H:%M"))
    threading.Thread(target=_loop, args=([why], [pid] if pid else []), daemon=True).start()
    return "running"


def api_post(q, body):
    why = str(body.get("why") or "").strip()
    if not why:
        raise ValueError("say which note the rule is for: {\"why\": \"...\"}")
    return {"state": queue(why, body.get("pid") or q.get("id"))}


def api_get(q, body):
    return {k: _S[k] for k in ("state", "why", "started", "last")} | {"queued": bool(_S["pending"])}


ROUTES = {("POST", "rule-gate"): api_post, ("GET", "rule-gate"): api_get}

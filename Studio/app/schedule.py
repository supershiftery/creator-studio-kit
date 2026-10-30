"""Scheduled builds (2026-10-25, user: "a schedule option inside the studio ... you can choose what device ... or build it
right now"; "if I turn my desktop off and I scheduled videos for the desktop, it should switch over to the laptop, and vice
versa"). data/schedule.json = [{id, project_id, title, action, at "YYYY-MM-DD HH:MM", machine, state, ran_on, job, note}].

machine = "Laptop" | "Desktop" | "Both"  (Both = the laptop first, the desktop when the laptop is busy; decided at start)
state   = pending -> started -> done | failed ; cancelled ; "taken" (the other machine ran it)

Every entry is kept on BOTH machines (same id). Each Studio's loop (every TICK s) runs a due entry when:
  - it is the target (or "Both" and this is the machine that can reach the other, i.e. the desktop), or
  - the target has been unreachable for FALLBACK_MIN past the time -> it runs here, marked fallback.
The desktop pushes its entries to the laptop (POST schedule/mirror) and reads the laptop's back (GET schedule), so each side
sees the other's states; a project scheduled for the laptop is sent there right away, so the laptop can build it even when
the desktop is off by then."""
import json
import threading
import time
import traceback
import uuid
from datetime import datetime, timedelta

import store

FILE = store.DATA / "schedule.json"
TICK = 30
FALLBACK_MIN = 3
_LOCK = threading.RLock()
_STARTED = False
_PUSHED = {}   # (worker, entry id) -> the copy last sent, so each tick only sends what changed


def load():
    return store.read_json(FILE, []) or []


def save(items):
    store.write_json(FILE, items[-300:])


def get(eid):
    return next((e for e in load() if e["id"] == eid), None)


def upsert(entry):
    with _LOCK:
        items = load()
        for i, e in enumerate(items):
            if e["id"] == entry["id"]:
                # never move a finished entry back (the other side's older copy)
                order = ["pending", "started", "taken", "done", "failed", "cancelled"]
                if order.index(entry.get("state", "pending")) < order.index(e.get("state", "pending")):
                    return e
                items[i] = {**e, **entry}
                save(items)
                return items[i]
        items.append(entry)
        save(items)
        return entry


def add(doc, at, machine="Laptop", action="draft"):
    e = {"id": uuid.uuid4().hex[:8], "project_id": doc["id"], "title": doc["title"], "type": doc["type"], "path": doc["path"],
         "action": action, "at": at, "machine": machine, "state": "pending", "created": store.now(), "made_on": me()}
    return upsert(e)


def cancel(eid):
    e = get(eid)
    if e and e["state"] == "pending":
        e["state"] = "cancelled"
        return upsert(e)
    return e


def me():
    return store.settings().get("machine_name") or "Desktop"


def due(e, now=None):
    now = now or datetime.now()
    try:
        return datetime.strptime(e["at"], "%Y-%m-%d %H:%M") <= now
    except Exception:
        return False


def _mine_now(e):
    """should THIS machine start this due entry now? -> (yes, fallback?)"""
    import remote
    mine = me()
    target = e.get("machine") or "Laptop"
    overdue = datetime.now() - datetime.strptime(e["at"], "%Y-%m-%d %H:%M")
    if target == mine:
        return True, False
    if target == "Both":
        # the machine that can reach the other decides (it sees both queues); the other one only if that one is gone
        if remote.workers():
            return True, False
        other = next((p["name"] for p in (store.settings().get("peers") or [])), None)
        return (other is not None and not remote.online(other) and overdue >= timedelta(minutes=FALLBACK_MIN)), True
    # the target is the other machine: take over only when it has been unreachable for a while past the time
    if overdue >= timedelta(minutes=FALLBACK_MIN) and not remote.online(target):
        return True, True
    return False, False


def _run(e, fallback):
    import server   # late: server imports this module
    doc = store.load(e["project_id"])
    if not doc:
        e.update(state="failed", note=f"the project is not on {me()}")
        return upsert(e)
    # "Both" picks laptop-or-desktop at start; anything else this machine decided to run runs HERE
    machine = "both" if e.get("machine") == "Both" and not fallback else "local"
    try:
        if e.get("action") == "notes":   # a revision batch put off until tonight (Queue page, 2026-10-29): send it now
            out = server.api_rebuild_notes({"id": doc["id"]}, {})
            if not out.get("job"):   # written changes went to the revision AI: it rebuilds; nothing for this entry to watch
                e.update(state="done", ran_on=me(), started=store.now(), ended=store.now(), note="changes sent to the AI; it makes the draft")
                return upsert(e)
            job = server.jobs.JOBS.get(out["job"]["id"])
        else:
            job = server.start_build(doc, e.get("action", "draft"), machine=machine)
        e.update(state="started", ran_on=me(), job=job.id, started=store.now(), fallback=fallback,
                 note=(f"{e.get('machine')} was off, so {me()} built it" if fallback else ""))
    except Exception as err:  # a build already running for it: try again next tick
        if "already running" in str(err):
            return e
        e.update(state="failed", note=str(err)[:200])
    return upsert(e)


def _finish_started():
    """started -> done / failed once its job ended (the job lives on this machine)"""
    import jobs
    for e in load():
        if e.get("state") == "started" and e.get("ran_on") == me() and e.get("job"):
            j = jobs.JOBS.get(e["job"])
            if j and j.status in ("done", "failed", "cancelled"):
                e["state"] = "done" if j.status == "done" else "failed"
                e["ended"] = store.now()
                upsert(e)


def tick():
    with _LOCK:
        _finish_started()
        for e in load():
            if e.get("state") != "pending" or not due(e):
                continue
            yes, fallback = _mine_now(e)
            if yes:
                _run(e, fallback)
        _sync_peers()


def _sync_peers():
    """desktop side: push our entries to each worker, take theirs back (their started/done states win)"""
    import remote
    for w in remote.workers():
        if not remote.online(w["name"]):
            continue
        try:
            for e in remote.call(w, "GET", "schedule", timeout=30).get("items", []):
                ours = any(x["id"] == e["id"] for x in load())
                if not ours:
                    upsert(e)   # scheduled from the worker's own Studio: show it here too (2026-10-26 fallback test)
                elif e.get("ran_on") and e.get("ran_on") != me() and e.get("state") in ("started", "done", "failed"):
                    upsert(e)   # the worker started / finished one of ours (or took it over): its state wins
            for e in load():
                sig = json.dumps(e, sort_keys=True)
                if _PUSHED.get((w["name"], e["id"])) != sig and e.get("created", "") >= (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d"):
                    remote.call(w, "POST", "schedule/mirror", e, timeout=30)
                    _PUSHED[(w["name"], e["id"])] = sig
        except Exception as err:  # noqa: next tick
            print("schedule sync:", err, flush=True)


def _loop():
    time.sleep(15)
    while True:
        try:
            tick()
        except Exception:  # noqa: the scheduler never dies
            traceback.print_exc()
        time.sleep(TICK)


def start():
    global _STARTED
    if _STARTED:
        return
    _STARTED = True
    threading.Thread(target=_loop, name="schedule", daemon=True).start()


def view():
    items = load()
    return {"items": sorted(items, key=lambda e: e["at"], reverse=True)[:60], "me": me()}

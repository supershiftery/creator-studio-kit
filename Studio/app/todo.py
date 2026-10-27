"""To-do list stored locally in data/todo.json (no account or paid app needed).
Lists = Inbox + one per channel from Settings. Same calls the dashboard and To-do page use: snapshot, lists, add, complete, push."""
import uuid
from datetime import date, timedelta

import store

FILE = store.DATA / "todo.json"


def _load():
    return store.read_json(FILE, []) or []


def _save(tasks):
    store.write_json(FILE, tasks)


def lists():
    out = [{"id": "Inbox", "name": "Inbox", "kind": "INBOX"}]
    for ch in store.settings().get("channels", []):
        out.append({"id": ch["name"], "name": ch["name"], "kind": "TASK", "closed": False})
    return out


def snapshot(max_age=45):
    today = date.today()
    rows = []
    for t in _load():
        if t.get("done"):
            continue
        due = t.get("due") or ""
        days = (date.fromisoformat(due) - today).days if due else None
        rows.append({"pid": t.get("list", "Inbox"), "tid": t["id"], "title": t["title"], "list": t.get("list", "Inbox"),
                     "priority": 0, "due": due, "allDay": True, "content": (t.get("notes") or "")[:200], "days": days, "tags": []})
    rows.sort(key=lambda r: (r["due"] or "9999", r["title"]))
    return {"ok": True, "today_date": today.isoformat(), "queued": [], "flushed": 0,
            "overdue": [r for r in rows if r["days"] is not None and r["days"] < 0],
            "today": [r for r in rows if r["days"] == 0],
            "soon": [r for r in rows if r["days"] is not None and 0 < r["days"] <= 7],
            "someday": [r for r in rows if r["days"] is None][:40],
            "total_open": len(rows)}


def invalidate():
    pass


def add(title, list_name=None, due=None, notes=None, **_):
    title = (title or "").strip()
    if not title:
        raise ValueError("empty task")
    task = {"id": uuid.uuid4().hex[:10], "title": title, "list": list_name or "Inbox", "due": (due or "")[:10],
            "notes": notes or "", "created": store.now(), "done": False}
    tasks = _load()
    tasks.append(task)
    _save(tasks)
    return {"ok": True, "task": {"tid": task["id"], "pid": task["list"], "title": title, "due": task["due"]}}


def _update(tid, fn):
    tasks = _load()
    for t in tasks:
        if t["id"] == tid:
            fn(t)
            _save(tasks)
            return t
    raise ValueError("no such task")


def complete(pid, tid):
    _update(tid, lambda t: t.update(done=True, completed=store.now()))
    return {"ok": True}


def push(pid, tid, days):
    target = date.today() + timedelta(days=int(days))
    _update(tid, lambda t: t.update(due=target.isoformat()))
    return {"ok": True, "due": target.isoformat()}


def done_card(channel, title):
    """A finished video = a completed task on its channel's list (an open task with the same title is ticked off)."""
    tasks = _load()
    t = next((t for t in tasks if not t.get("done") and t.get("list") == channel and t["title"].lower() == title.lower()), None)
    if t:
        t.update(done=True, completed=store.now())
        status = "checked off"
    else:
        t = {"id": uuid.uuid4().hex[:10], "title": title, "list": channel or "Inbox", "due": "", "notes": "",
             "created": store.now(), "done": True, "completed": store.now()}
        tasks.append(t)
        status = "added as done"
    _save(tasks)
    return {"ok": True, "tid": t["id"], "title": title, "status": status, "channel": channel}

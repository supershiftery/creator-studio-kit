"""One build of a project on another machine, run as a single step of THIS machine's job (laptop first, 2026-10-25), so
the queue, notifications, build history and the revision AI's polling all work as for a local build, and THIS machine's
GPU stays free (the step is "light").

    python remote_build.py <project_id> <action> <worker> [--force]

1. send the project's new / changed files (+ the intro VO / B-roll it reads from outside the folder) to the worker
2. register it there (projects/adopt keeps the id: same studio.json) and start the build (project/run)
3. print the worker's progress until it ends (its own render queue decides when it starts)
4. bring back what it made (output, work, intro ... never raw / studio.json) and exit 0, or 1 if the build failed there"""
import json
import sys
import time
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
import remote  # noqa: E402
import store   # noqa: E402

POLL = 10


def say(msg):
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def meter(verb):
    """progress(done, total) -> "uploading 3.8 of 8.1 GB (47% sent)" lines, one every 15 s (jobs.py reads the %)"""
    t0, said = time.time(), [0.0]

    def f(done, total):
        if time.time() - said[0] < 15 and done < total:
            return
        said[0] = time.time()
        rate = done / max(1.0, time.time() - t0)
        left = f", ~{(total - done) / rate / 60:.0f} min left" if rate > 0 and done < total else ""
        say(f"{verb} {done / 1e9:.2f} of {total / 1e9:.2f} GB, {rate / 1e6:.0f} MB/s{left} "
            f"({100 * done / max(1, total):.0f}% {'sent' if verb == 'uploading' else 'back'})")
    return f


def outside_files(doc):
    """files a build reads that live outside the project folder (slots pointing at Documents\\Audacity, an OBS folder...)"""
    home = str(Path(doc["path"]))
    out = []
    for v in (doc.get("slots") or {}).values():
        for p in (v if isinstance(v, list) else [v]):
            if isinstance(p, str) and len(p) > 3 and p[1:3] == ":\\" and not p.startswith(home) and Path(p).is_file():
                out.append(p)
    if doc.get("source") and not str(doc["source"]).startswith(home):
        out.append(doc["source"])
    # the approved edits' answer keys ({{KIT}}/tools\approved_cuts.py): the worker's build checks against them
    if Path(APPROVED_KEYS).is_file():
        out.append(APPROVED_KEYS)
    return out


APPROVED_KEYS = r"{{KIT}}/tools\_state\approved_cuts.json"


def main(a):
    pid, action, wname = a[0], a[1], a[2]
    force = "--force" in a
    doc = store.load(pid)
    if not doc:
        sys.exit(f"no project {pid}")
    w = remote.worker(wname)
    if not w:
        sys.exit(f"no worker called {wname} in settings")
    folder = doc["path"]
    t0 = time.time()
    say(f"== sending {doc['title']} to {w['name']}")
    n, size = remote.sync_to(w, folder, extra=outside_files(doc), progress=meter("uploading"))
    say(f"sent {n} files ({size / 1e9:.2f} GB) in {time.time() - t0:.0f} s")
    # the worker's id for this folder (an older worker Studio hashes its resolved C:\Hub path, so it can differ from ours)
    rid = remote.call(w, "POST", "projects/adopt", {"path": folder}).get("id") or pid
    say(f"== building on {w['name']}: {action}" + (f" (its id {rid})" if rid != pid else ""))
    r = remote.call(w, "POST", f"project/run?id={rid}", {"action": action, "force": force,
                                                          **({"intro": "rebuild"} if "--intro-rebuild" in a else {})})
    jid = (r.get("job") or {}).get("id")
    if not jid:
        sys.exit(f"{w['name']} did not start a build: {json.dumps(r)[:300]}")
    last, j = "", {}
    while True:
        time.sleep(POLL)
        try:
            j = remote.call(w, "GET", f"job?id={jid}", timeout=40)
        except Exception as e:  # a blip on the network / the worker's Studio restarting: keep trying for a while
            say(f"(can't reach {w['name']}: {e})")
            if time.time() - t0 > 8 * 3600:
                sys.exit(f"lost {w['name']} for too long")
            continue
        q, pr = j.get("queue") or {}, j.get("progress") or {}
        step = next((s["label"] for s in j.get("steps", []) if s.get("status") == "running"), "")
        line = f"waiting #{q.get('pos')} in {w['name']}'s line" if q.get("state") == "waiting" else f"{step} ({round(pr.get('pct') or 0)}% built)"
        if line != last:
            say(f"{w['name']}: {line}")
            last = line
        if j.get("status") not in ("running", "queued"):
            break
    say(f"== {w['name']} finished: {j.get('status')}{' (' + str(j.get('error')) + ')' if j.get('error') else ''}")
    t1 = time.time()
    # a fresh listing per try: a temp file the worker deletes between listing and copying broke the whole bring-back
    # (reselling 2026-10-26 01:27: the draft was home, the build said "failed" on "tar: : Couldn't visit directory")
    for attempt in range(3):
        try:
            n, size = remote.sync_from(w, folder, progress=meter("bringing back"))
            break
        except RuntimeError as e:
            if attempt == 2:
                raise
            say(f"(bringing back hit {str(e)[:160]}; trying again)")
            time.sleep(10)
    say(f"brought back {n} files ({size / 1e9:.2f} GB) in {time.time() - t1:.0f} s")
    # the worker's step list + times, for the build history here
    steps = [{"label": s.get("label"), "status": s.get("status"), "secs": (j.get("step_secs") or {}).get(s.get("id"))} for s in j.get("steps", [])]
    (Path(folder) / "work").mkdir(exist_ok=True)
    (Path(folder) / "work" / "remote_build.json").write_text(json.dumps({"machine": w["name"], "job": jid, "status": j.get("status"),
                                                                       "steps": steps, "ended": time.strftime("%Y-%m-%d %H:%M")}, indent=1), encoding="utf-8")
    failed = [s["label"] for s in j.get("steps", []) if s.get("status") == "failed"]
    if j.get("status") != "done":
        say(f"FAILED on {w['name']}: {', '.join(failed) or j.get('error') or j.get('status')}")
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])

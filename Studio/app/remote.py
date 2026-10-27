"""Other machines running {{STUDIO_NAME}} (laptop hub, 2026-10-25). The user: "see that this is rendering on the laptop",
then "laptop first, rendering 24/7 ... if a machine is off it falls back to the other one ... both at once sometimes".

settings.workers = [{"name": "Laptop", "ssh": "super@100.x.y.z", "key": "~/.ssh/laptop_hub", "root": "C:\\Hub"}]
    a machine THIS Studio can reach over SSH. Its Studio stays on 127.0.0.1 (no new ports): every call is
    `ssh <worker> python <its Studio>\\app\\tools\\local_api.py ...`. root = where the worker keeps F:\\ (its F: is a subst of
    C:\\Hub, used for tar so paths never depend on the subst).
settings.peers = [{"name": "Desktop", "tailscale": "reviewerspc"}]
    a machine that can reach US but we can't reach it (the desktop has no SSH server): it pushes its job list here
    (POST /api/peer/jobs) and we see whether it is on through `tailscale status`.

Reading:  snapshot() -> {"workers": [{"name","ok","age_s","error","jobs"}]}; job_for(project_id) -> (machine, job view).
Files:    sync_to(worker, folder) / sync_from(worker, folder): only new or changed files move (size + mtime), tar over SSH.
Calls:    call(worker, "POST", "project/run?id=..", body)."""
import base64
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import store

POLL = 10
STALE = 45          # older than this = the machine counts as offline
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
TAR = r"C:\Windows\System32\tar.exe"
LOCAL_API = r"{{KIT}}/Studio\app\tools\local_api.py"   # same path on every machine (F: = the Studio drive)
# folders inside a project that never travel (snapshots / caption backups are per machine; raw is copied once)
NEVER = {"drafts", "__pycache__", "_captions"}

_LOCK = threading.Lock()
_STATE = {}          # machine name -> {"ok", "at", "error", "jobs"}
_PEERS = {}          # name -> {"at", "jobs"} pushed by a machine that can reach us
_STARTED = False


# ------------------------------------------------------------------ settings
def workers():
    return [w for w in (store.settings().get("workers") or []) if w.get("name") and w.get("ssh")]


def worker(name=None):
    ws = workers()
    if name:
        ws = [w for w in ws if w["name"].lower() == str(name).lower()]
    return ws[0] if ws else None


def me():
    return store.settings().get("machine_name") or "Desktop"


def _key(w):
    return os.path.expanduser(w.get("key") or "~/.ssh/id_ed25519")


def _ssh(w, cmd, timeout=60, stdin=None):
    r = subprocess.run(["ssh", "-i", _key(w), "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", w["ssh"], cmd],
                       input=stdin, capture_output=True, timeout=timeout, creationflags=CREATE_NO_WINDOW)
    if r.returncode:
        err = (r.stderr or r.stdout).decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(err[-1][:300] if err else f"ssh exit {r.returncode}")
    return r.stdout.decode("utf-8", "replace")


def _py(w, code, timeout=120):
    """run a small Python program on the worker (base64, so no shell quoting) and return its stdout"""
    b = base64.b64encode(code.encode("utf-8")).decode()
    return _ssh(w, f'python -I -c "import base64;exec(base64.b64decode(\'{b}\').decode())"', timeout=timeout)


def call(w, method, path, body=None, timeout=120):
    w = worker(w) if isinstance(w, str) else w
    arg = base64.b64encode(json.dumps(body).encode()).decode() if body is not None else ""
    out = _ssh(w, f'python -I "{LOCAL_API}" {method} "{path}" {arg}', timeout=timeout)
    return json.loads(out) if out.strip() else {}


# ------------------------------------------------------------------ files
def _root(w, drive):
    """where a local drive's files live on the worker: F: -> its root (C:\\Hub), other drives the same letter"""
    return (w.get("root") or "C:\\Hub") if drive.upper() == "F:" else drive + "\\"


def _walk(folder, skip=NEVER):
    out = {}
    folder = Path(folder)
    for dp, dn, fn in os.walk(folder):
        dn[:] = [d for d in dn if d not in skip]
        for n in fn:
            p = Path(dp) / n
            try:
                st = p.stat()
            except OSError:
                continue
            out[p.relative_to(folder).as_posix()] = [st.st_size, int(st.st_mtime)]
    return out


def remote_listing(w, folder, skip=NEVER):
    drive, rest = os.path.splitdrive(str(folder))
    rfolder = os.path.join(_root(w, drive), rest.lstrip("\\"))
    code = (f"import os,json\nfrom pathlib import Path\nF=Path({rfolder!r});S={sorted(skip)!r};o={{}}\n"
            "if F.is_dir():\n for dp,dn,fn in os.walk(F):\n  dn[:]=[d for d in dn if d not in S]\n  for n in fn:\n"
            "   p=Path(dp)/n\n   try: st=p.stat()\n   except OSError: continue\n"
            "   o[p.relative_to(F).as_posix()]=[st.st_size,int(st.st_mtime)]\nprint(json.dumps(o))")
    return json.loads(_py(w, code, timeout=300).strip().splitlines()[-1])


def _pipe(first, second, progress=None, first_stdin=None):
    """first | second. Without progress the OS pipes them straight through; with it the bytes go through here and
    progress(bytes so far) is called every few seconds (user 2026-10-26: a rebuild sat on "Building on Laptop" for 15 min
    while 8 GB went over Wi-Fi and the laptop looked idle). Returns (rc first, rc second, stderr text)."""
    a = subprocess.Popen(first, stdin=subprocess.PIPE if first_stdin is not None else subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW)
    if first_stdin is not None:
        a.stdin.write(first_stdin)
        a.stdin.close()
    b = subprocess.Popen(second, stdin=subprocess.PIPE if progress else a.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                         creationflags=CREATE_NO_WINDOW)
    errs = {}
    readers = [threading.Thread(target=lambda k, f: errs.__setitem__(k, f.read()), args=(k, f), daemon=True)
               for k, f in (("a", a.stderr), ("b", b.stderr))]
    for t in readers:
        t.start()
    if progress:
        n, said = 0, 0.0
        try:
            while True:
                chunk = a.stdout.read(1 << 20)
                if not chunk:
                    break
                b.stdin.write(chunk)
                n += len(chunk)
                if time.time() - said >= 3:
                    said = time.time()
                    progress(n)
        finally:
            try:
                b.stdin.close()
            except OSError:
                pass
        progress(n)
    else:
        a.stdout.close()
    a.wait()
    b.wait()
    for t in readers:
        t.join(5)
    err = (errs.get("a") or b"").decode("utf-8", "replace") or (errs.get("b") or b"").decode("utf-8", "replace")
    return a.returncode, b.returncode, err


def _by_drive(files):
    out = {}
    for f in files:
        drive, rest = os.path.splitdrive(str(f))
        out.setdefault(drive, []).append(rest.lstrip("\\").replace("\\", "/"))
    return out


def _sftp(w, direction, drive, rels):
    """the files tar can't name: Windows tar reads its file list in the ANSI code page, so a name like
    'TYPE BEAT “ONE PIECE”.mp3' (2026-10-26, a type beat in work/music) fails the whole batch. SFTP speaks UTF-8.
    direction "put" (here -> worker) or "get" (worker -> here); -p keeps the mtimes like tar does."""
    root = _root(w, drive).replace("\\", "/").rstrip("/")
    q = lambda s: '"' + s.replace('"', '\\"') + '"'
    lines = []
    for r in rels:
        here, there = f"{drive}/{r}", f"{root}/{r}"
        if direction == "put":
            parts = there.split("/")
            lines += [f"-mkdir {q('/'.join(parts[:i]))}" for i in range(2, len(parts))]
            lines.append(f"put -p {q(here)} {q(there)}")
        else:
            os.makedirs(os.path.dirname(os.path.join(drive + "\\", r)), exist_ok=True)
            lines.append(f"get -p {q(there)} {q(here)}")
    with tempfile.NamedTemporaryFile("w", suffix=".sftp", delete=False, encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
        batch = fh.name
    try:
        r = subprocess.run(["sftp", "-i", _key(w), "-o", "BatchMode=yes", "-b", batch, w["ssh"]], capture_output=True,
                           creationflags=CREATE_NO_WINDOW)
        if r.returncode:
            raise RuntimeError(f"sftp {direction} failed: {(r.stderr or r.stdout).decode('utf-8', 'replace')[-300:]}")
    finally:
        os.unlink(batch)


def _split_ascii(rels):
    return [r for r in rels if r.isascii()], [r for r in rels if not r.isascii()]


def push(w, files, progress=None):
    """copy local files to the same place on the worker (tar keeps their mtimes). files = absolute local paths.
    progress(bytes sent so far), every few seconds, when given."""
    base = 0
    for drive, rels in _by_drive(files).items():
        rels, odd = _split_ascii(rels)
        if odd:
            _sftp(w, "put", drive, odd)
        if not rels:
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
            fh.write("\n".join(rels) + "\n")
            lst = fh.name
        try:
            rc1, rc2, err = _pipe([TAR, "-c", "-f", "-", "-C", drive + "\\", "-T", lst],
                                  ["ssh", "-i", _key(w), "-o", "BatchMode=yes", w["ssh"], f"{TAR} -x -f - -C {_root(w, drive)}"],
                                  (lambda n, b=base: progress(b + n)) if progress else None)
            if rc1 or rc2:
                raise RuntimeError(f"push failed (tar {rc1}, ssh {rc2}): {err[-300:]}")
        finally:
            os.unlink(lst)
        base += sum(os.path.getsize(os.path.join(drive + "\\", r)) for r in rels if os.path.isfile(os.path.join(drive + "\\", r)))


def pull(w, files, progress=None):
    """copy files back from the worker to the same local paths. files = absolute LOCAL paths."""
    base = 0
    for drive, rels in _by_drive(files).items():
        rels, odd = _split_ascii(rels)
        if odd:
            _sftp(w, "get", drive, odd)
        if not rels:
            continue
        rc1, rc2, err = _pipe(["ssh", "-i", _key(w), "-o", "BatchMode=yes", w["ssh"], f"{TAR} -c -f - -C {_root(w, drive)} -T -"],
                              [TAR, "-x", "-f", "-", "-C", drive + "\\"],
                              (lambda n, b=base: progress(b + n)) if progress else None, first_stdin=("\n".join(rels) + "\n").encode("utf-8"))
        if rc1 or rc2:
            raise RuntimeError(f"pull failed (ssh {rc1}, tar {rc2}): {err[-300:]}")
        base += sum(os.path.getsize(os.path.join(drive + "\\", r)) for r in rels if os.path.isfile(os.path.join(drive + "\\", r)))


def sync_to(w, folder, skip=NEVER, extra=(), progress=None, only_older=False):
    """send what the worker is missing or has older/different (size or mtime). extra = files outside the folder
    (an intro VO in Documents\\Audacity, B-roll elsewhere) that the build reads. progress(sent, total) every few seconds.
    only_older = never replace a file the worker has NEWER (the daytime presync). Returns (n files, bytes)."""
    mine, theirs = _walk(folder, skip), remote_listing(w, folder, skip)
    send = [str(Path(folder) / r) for r, v in mine.items() if theirs.get(r) != v and not (only_older and r in theirs and theirs[r][1] > v[1])]
    for x in extra:
        if x and os.path.isfile(x) and not str(x).upper().startswith("G:") and not str(x).startswith(str(folder)):
            send.append(str(x))   # G: = Google Drive, which the worker has itself
    total = sum(os.path.getsize(f) for f in send)
    if send:
        push(w, send, (lambda n: progress(n, total)) if progress else None)
    return len(send), total


def sync_from(w, folder, skip=NEVER | {"raw"}, keep_local=("studio.json", "studio-chat.json"), progress=None):
    """bring back what the worker made or changed (newer there); the project's own studio.json / chat stay this
    machine's (the notes live here). progress(got, total) every few seconds. Returns (n files, bytes)."""
    mine, theirs = _walk(folder, skip), remote_listing(w, folder, skip)
    get = [r for r, v in theirs.items() if r not in keep_local and (r not in mine or (mine[r] != v and v[1] >= mine[r][1]))]
    total = sum(theirs[r][0] for r in get)
    if get:
        pull(w, [str(Path(folder) / r) for r in get], (lambda n: progress(n, total)) if progress else None)
    return len(get), total


# ------------------------------------------------------------------ what is running where
def _fetch(w):
    return call(w, "GET", "jobs", timeout=25).get("jobs", [])


def _loop():
    while True:
        for w in workers():
            try:
                jobs = _fetch(w)
                rec = {"ok": True, "at": time.time(), "error": "", "jobs": jobs}
            except Exception as e:  # offline / Studio not running there / timeout: keep the last jobs but mark it
                with _LOCK:
                    old = _STATE.get(w["name"], {})
                rec = {"ok": False, "at": old.get("at", 0), "error": str(e)[:160], "jobs": old.get("jobs", [])}
            with _LOCK:
                _STATE[w["name"]] = rec
            if rec["ok"]:
                try:   # let the worker show OUR jobs too (it can't reach us)
                    import jobs as _jobs
                    call(w, "POST", "peer/jobs", {"name": me(), "jobs": _jobs.all_views()}, timeout=25)
                except Exception:
                    pass
                try:
                    _after_poll(w, rec["jobs"])
                except Exception as e:  # noqa
                    print("remote: after poll:", e, flush=True)
        time.sleep(POLL)


_HOOKS = []   # callables (worker, jobs) run after each successful poll (server: pull results of finished remote builds)


def on_poll(fn):
    _HOOKS.append(fn)


def _after_poll(w, jobs):
    for fn in _HOOKS:
        fn(w, jobs)


def start():
    global _STARTED
    if _STARTED or not workers():
        return
    _STARTED = True
    threading.Thread(target=_loop, name="remote-workers", daemon=True).start()


def _live(rec):
    return rec.get("ok") and time.time() - rec.get("at", 0) < STALE


def online(name):
    """True when that machine is reachable now: a worker we poll, or a peer that pushed to us recently / Tailscale says on"""
    start()
    w = worker(name)
    with _LOCK:
        polled = name in _STATE
    if w and not polled:   # right after a start the poller hasn't been round yet: ask once now
        try:
            jobs = _fetch(w)
            with _LOCK:
                _STATE[name] = {"ok": True, "at": time.time(), "error": "", "jobs": jobs}
        except Exception as e:
            with _LOCK:
                _STATE[name] = {"ok": False, "at": 0, "error": str(e)[:160], "jobs": []}
    with _LOCK:
        if name in _STATE:
            return _live(_STATE[name])
        if name in _PEERS and time.time() - _PEERS[name]["at"] < STALE:
            return True
    peer = next((p for p in (store.settings().get("peers") or []) if p.get("name") == name), None)
    return bool(peer and tailscale_online(peer.get("tailscale")))


def tailscale_online(host):
    if not host:
        return False
    try:
        r = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=10, creationflags=CREATE_NO_WINDOW)
        for p in (json.loads(r.stdout).get("Peer") or {}).values():
            if (p.get("HostName") or "").lower() == host.lower() or (p.get("DNSName") or "").lower().startswith(host.lower() + "."):
                return bool(p.get("Online"))
    except Exception:
        pass
    return False


def set_peer(name, jobs):
    with _LOCK:
        _PEERS[name] = {"at": time.time(), "jobs": jobs or []}


def busy(name):
    """the machine is rendering or has a line waiting (for 'Both': use the desktop when the laptop is busy)"""
    with _LOCK:
        rec = _STATE.get(name) or _PEERS.get(name) or {}
        return any(j.get("status") in ("running", "queued") for j in rec.get("jobs", []))


def snapshot():
    start()
    out = []
    with _LOCK:
        for w in workers():
            rec = _STATE.get(w["name"], {})
            active = [j for j in rec.get("jobs", []) if j.get("status") in ("running", "queued")] if _live(rec) else []
            out.append({"name": w["name"], "ok": _live(rec), "age_s": round(time.time() - rec["at"]) if rec.get("at") else None,
                        "error": rec.get("error", ""), "jobs": active})
        for name, rec in _PEERS.items():
            ok = time.time() - rec["at"] < STALE
            out.append({"name": name, "ok": ok, "age_s": round(time.time() - rec["at"]), "error": "" if ok else "not heard from",
                        "jobs": [j for j in rec["jobs"] if j.get("status") in ("running", "queued")] if ok else []})
    return {"workers": out}


def job_for(project_id):
    start()
    with _LOCK:
        recs = list(_STATE.items()) + [(n, {"ok": True, **r}) for n, r in _PEERS.items()]
    for name, rec in recs:
        if not _live(rec):
            continue
        for j in rec.get("jobs", []):
            if j.get("project_id") == project_id and j.get("status") in ("running", "queued"):
                # a remote job that is only our own "Building on <machine>" proxy is shown by the local job already
                return name, j
    return None, None

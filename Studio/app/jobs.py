"""Background jobs: a job is a list of steps; each step runs a subprocess and streams its output into the job log.
Steps are skipped when their outputs are newer than their inputs (unless forced)."""
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
JOBS = {}
LOCK = threading.Lock()
TIMES_FILE = Path(__file__).resolve().parent.parent / "data" / "step-times.json"
# seconds per minute of footage, first guesses; replaced by what previous builds measured
DEFAULT_RATE = {"prep": 0.15, "broll": 0.6, "transcribe": 6.5, "sections": 0.05, "cuts": 1.0, "body": 3.0, "assemble": 1.5, "chapters": 0.05,
                "check": 1.0, "pipeline": 90.0, "main_full": 25.0, "join": 2.0, "copy": 0.05, "edit": 60.0, "broll_plan": 0.5, "sections_only": 0.05}


def _times():
    try:
        return json.loads(TIMES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _record(kind, step_id, secs, minutes):
    if not minutes or secs < 1:
        return
    t = _times()
    arr = t.setdefault(kind, {}).setdefault(step_id, [])
    arr.append(round(secs / minutes, 3))
    del arr[:-8]
    try:
        TIMES_FILE.write_text(json.dumps(t), encoding="utf-8")
    except OSError:
        pass


# ---- render queue (user 2026-10-23: "we can't run multiple videos at once for the render section, but the AI part can go
# ahead"): one build holds the GPU at a time, the rest wait in submission order (status "queued", with their place in line).
# Light steps (the AI turning notes into cuts, the Claude QC review) run without the GPU: a job starts its light steps at
# once and only waits for its turn at the first heavy step, and hands the GPU on once only light steps are left.
# settings.json "render_queue": false turns it off (every build starts at once, like before).
LIGHT_STEPS = {"revise", "claude_qc"}
QUEUE = []                      # job ids in submission order (jobs that have not finished)
QCOND = threading.Condition()
GPU = {"holder": None}          # id of the job rendering now
# A review build that reaches its intro step (a "share_gpu" step) lets the next video in line start (user 2026-10-23: intros
# were where most of the time went, half of it AI calls on the network): it keeps its own pass for the rest of its build, so
# at most two builds overlap, one of them only finishing its intro. settings.json "intro_overlap": false = old behaviour.
SHARE = {"job": None}           # id of the job finishing alongside the holder


def queue_on():
    try:
        import store
        return store.settings().get("render_queue", True) is not False
    except Exception:
        return True


def slots():
    """builds that may render at once (user 2026-10-24: "move fast"; a review build waited ~16 min in line while the PC ran at
    ~40% CPU / 35% GPU). 2 = the second slot is the SHARE pass: a build that gets its turn moves into it at once when it is
    free, so the next one starts. settings.json "render_slots": 1 = one at a time (intro overlap still applies)."""
    try:
        import store
        return max(1, min(2, int(store.settings().get("render_slots", 2))))
    except Exception:
        return 2


def share_on():
    try:
        import store
        return store.settings().get("intro_overlap", True) is not False
    except Exception:
        return True


def _alive(pid):
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value == 259
    except Exception:
        return False


def _created(pid):
    """process start time (epoch s), or None"""
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, int(pid))
        if not h:
            return None
        t = [ctypes.c_ulonglong() for _ in range(4)]
        ok = k.GetProcessTimes(h, *[ctypes.byref(x) for x in t])
        k.CloseHandle(h)
        return t[0].value / 1e7 - 11644473600 if ok else None
    except Exception:
        return None


def _outside_build():
    """a build step still running from before an app restart (re-adopted, not in JOBS) holds the GPU too"""
    for pid, info in registry().items():
        # a light step (the AI, "Building on Laptop" = the laptop's GPU) never holds THIS machine's GPU (2026-10-25: a
        # test Studio's remote step sat in the shared registry and the desktop's real queue waited on it)
        if info.get("light") or str(info.get("step", "")).startswith("Building on "):
            continue
        # a day-old entry is a leftover whose pid Windows may have handed to some other program; so is a process that started
        # after the step did (2026-10-23: a stray bash shell got a dead intro's pid and held the whole queue)
        if info.get("job") not in JOBS and time.time() - (info.get("step_started") or 0) < 86400 and _alive(pid):
            c = _created(pid)
            if c is not None and c > (info.get("step_started") or 0) + 60:
                continue
            return info
    return None


def waiting():
    """jobs waiting for the GPU, in line order"""
    return [JOBS[i] for i in QUEUE if i in JOBS and JOBS[i].wants_gpu and GPU["holder"] != i]


def queue_pos(job):
    w = waiting()
    return w.index(job) + 1 if job in w else 0


def move(job_id, where):
    """reorder the line: where = up | down | top"""
    with QCOND:
        if job_id not in QUEUE:
            return False
        line = [j.id for j in waiting()]
        if job_id not in line:
            return False
        i = line.index(job_id)
        j = {"up": max(0, i - 1), "down": min(len(line) - 1, i + 1), "top": 0}.get(where, i)
        line.insert(j, line.pop(i))
        rest = [x for x in QUEUE if x not in line]
        QUEUE[:] = rest + line
        QCOND.notify_all()
    return True


REGISTRY = Path(__file__).resolve().parent.parent / "data" / "running-processes.json"
LOGDIR = Path(__file__).resolve().parent.parent / "data" / "joblogs"
DETACHED = 0x00000200 if sys.platform == "win32" else 0   # CREATE_NEW_PROCESS_GROUP: a closing app does not take the build with it
_REG_LOCK = threading.Lock()


def registry():
    try:
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _registry_set(pid, info):
    with _REG_LOCK:
        r = registry()
        r[str(pid)] = info
        try:
            REGISTRY.write_text(json.dumps(r), encoding="utf-8")
        except OSError:
            pass


def _registry_drop_job(job_id):
    with _REG_LOCK:
        r = {k: v for k, v in registry().items() if v.get("job") != job_id}
        try:
            REGISTRY.write_text(json.dumps(r), encoding="utf-8")
        except OSError:
            pass


def registry_drop_pid(pid):
    with _REG_LOCK:
        r = registry()
        r.pop(str(pid), None)
        try:
            REGISTRY.write_text(json.dumps(r), encoding="utf-8")
        except OSError:
            pass


def rate(kind, step_id):
    t = _times().get(kind, {}).get(step_id)
    if t:
        return sum(t) / len(t)
    return DEFAULT_RATE.get(step_id, 1.0)


def _phase_key(step_id, ph):
    return f"{step_id}/{ph[1]}"


def _phase_rate(kind, step_id, ph):
    t = _times().get(kind, {}).get(_phase_key(step_id, ph))
    return sum(t) / len(t) if t else (ph[3] if len(ph) > 3 else 1.0)


# ---- live progress (user 2026-10-23: the bar sat on "49%" for 50 min and the ETA was wrong). A step or phase that runs past
# its guessed time no longer freezes at 90% of its share: it eases toward 100% (never reaching it). Where real progress
# exists it wins: ffmpeg -stats "time=" against the output length the step printed, and files a silent pipeline writes in
# a known order (the phase's 5th field, a glob under the step's cwd). The ETA uses this job's measured speed.
STATS_RE = re.compile(r"\btime=(-?\d+):(\d+):(\d+(?:\.\d+)?)\b.*\b(?:speed|bitrate)=")
# a step that says its own % of the running phase (remote_build.py: "(47% sent)", "(30% built)", "(80% back)")
PCT_RE = re.compile(r"\((\d+(?:\.\d+)?)% (?:sent|built|back)\)")
OUTLEN_RES = [   # lines that say how long the video being rendered will be -> seconds
    (re.compile(r"([\d.]+) of [\d.]+ min kept(?:, ([\d.]+)x speed)?"), lambda m: float(m.group(1)) * 60 / float(m.group(2) or 1)),
    (re.compile(r"\d+:\d+(?:\.\d+)? -> (\d+):(\d+(?:\.\d+)?) \("), lambda m: int(m.group(1)) * 60 + float(m.group(2))),
    (re.compile(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)"), lambda m: int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))),
]
STUCK_AFTER = 8 * 60   # no log line, no milestone file and ~no CPU for this long = "may be stuck" (Claude calls wait a few min at 0 CPU)
# Frozen step = killed (user 2026-10-23: the sp5der draft wrote nothing 10:59-11:57 and held the render slot, so 3 videos
# waited behind it). No log line and no file changed under the step's folder for this long -> kill the step; the normal
# retry runs it once more (pipelines resume from their files) and a second freeze fails the build. CPU does not count
# here (a spinning process is still frozen). Light (AI) steps are exempt. settings "stall_kill_min" (0 = off), a step's
# "stall_min" overrides; long footage gets more room (0.75 min per footage minute).
STALL_KILL_MIN = 12   # was 25 (2026-10-24 speed pass: four review builds lost 25-33 min each to a CUDA whisper hang, now
                      # also caught inside whisper_gpu.py; a step that writes no line and no file for 12 min is frozen)


def stall_limit(step, minutes):
    """seconds without a log line or a written file before a step counts as frozen; None = never"""
    if step.get("light") or step["id"] in LIGHT_STEPS:
        return None
    if step.get("stall_min") is not None:
        base = float(step["stall_min"])
    else:
        try:
            import store
            base = float(store.settings().get("stall_kill_min", STALL_KILL_MIN))
        except Exception:
            base = STALL_KILL_MIN
        base = max(base, 0.4 * float(minutes or 0)) if base > 0 else 0
    return base * 60 if base > 0 else None


def newest_write(folder, cap=6000):
    """newest file mtime under a folder (a few levels deep), 0 when unknown"""
    best, n = 0.0, 0
    if not folder or not os.path.isdir(folder):
        return 0.0
    root_depth = folder.rstrip("\\/").count(os.sep)
    for dp, dns, fns in os.walk(folder):
        if dp.count(os.sep) - root_depth >= 4:
            dns[:] = []
        for fn in fns:
            n += 1
            try:
                best = max(best, os.stat(os.path.join(dp, fn)).st_mtime)
            except OSError:
                pass
        if n > cap:
            break
    return best


def eased(spent, est):
    """0..1 of a step/phase guessed to take est seconds: linear to 70%, then slows down but keeps moving (never 1)"""
    if est <= 0:
        return 0.0
    if spent <= 0.7 * est:
        return max(0.0, spent / est)
    return 1.0 - 0.21 * est / spent


def _tree_cpu(pid):
    """CPU seconds used so far by a process and all its children (Windows), None when it cannot be read"""
    try:
        import ctypes
        from ctypes import wintypes
        k = ctypes.windll.kernel32

        class PE(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                        ("szExeFile", ctypes.c_char * 260)]
        k.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        k.OpenProcess.restype = ctypes.c_void_p
        snap = k.CreateToolhelp32Snapshot(2, 0)
        if not snap or snap == ctypes.c_void_p(-1).value:
            return None
        kids = {}
        e = PE()
        e.dwSize = ctypes.sizeof(PE)
        ok = k.Process32First(ctypes.c_void_p(snap), ctypes.byref(e))
        while ok:
            kids.setdefault(e.th32ParentProcessID, []).append(e.th32ProcessID)
            ok = k.Process32Next(ctypes.c_void_p(snap), ctypes.byref(e))
        k.CloseHandle(ctypes.c_void_p(snap))
        tree, todo = [], [int(pid)]
        while todo and len(tree) < 200:
            p = todo.pop()
            tree.append(p)
            todo += [c for c in kids.get(p, []) if c not in tree]
        total = 0.0
        for p in tree:
            h = k.OpenProcess(0x1000, False, p)
            if not h:
                continue
            t = [wintypes.FILETIME() for _ in range(4)]
            if k.GetProcessTimes(ctypes.c_void_p(h), *[ctypes.byref(x) for x in t]):
                total += sum((x.dwHighDateTime << 32 | x.dwLowDateTime) for x in t[2:]) / 1e7
            k.CloseHandle(ctypes.c_void_p(h))
        return total
    except Exception:
        return None


def stale(outputs, inputs):
    outs = [Path(o) for o in outputs]
    if not outs or not all(o.exists() for o in outs):
        return True
    t = min(o.stat().st_mtime for o in outs)
    return any(Path(i).exists() and Path(i).stat().st_mtime > t + 0.5 for i in inputs if i)


class Job:
    def __init__(self, title, project_id=None, steps=None, log_file=None, on_done=None, kind="", minutes=0.0):
        self.id = uuid.uuid4().hex[:8]
        self.title = title
        self.project_id = project_id
        self.steps = steps or []      # [{"id", "label", "cmd": [...], "cwd", "outputs": [], "inputs": [], "force": bool, "env": {}}]
        self.log = []
        self.status = "queued"        # queued | running | done | failed | cancelled
        self.current = None
        self.started = None
        self.ended = None
        self.proc = None
        self.bg = {}   # background (parallel) steps: id -> (proc, started, log, step)
        self.cancel_flag = False
        self.log_file = log_file
        self.on_done = on_done
        self.step_status = {s["id"]: "pending" for s in self.steps}
        self.error = ""
        self.kind, self.minutes = kind, float(minutes or 0)
        self.step_started = {}
        self.created = time.time()
        self.wants_gpu = False   # waiting for its turn in the render queue
        self.has_gpu = False
        self.wait_s = 0.0        # seconds spent in line (not counted as build time)
        self.phase = {}   # step id -> (index into its phases, started at) learned from the step's own log lines (one-script pipelines)
        self.step_secs = {}
        self.live = {}       # step id -> real progress of the ffmpeg render running in it: {"r": 0..1, "base": step fraction when it began, ...}
        self.out_len = {}    # step id -> seconds of video the step said it is rendering
        self.activity = {}   # step id -> {"t": last sign of work, "cpu": (cpu s, at)}
        self.stalled = {}    # step id -> times it was killed for being frozen
        self.measured = [0.0, 0.0]   # [estimated, actual] seconds of the steps/phases finished in this run (the job's speed)
        self.shown_pct, self.shown_at = 0.0, None
        m = max(self.minutes, 1.0)
        # a step with phases is weighted phase by phase (measured seconds per footage minute, else the recipe's guess)
        self.phase_w = {s["id"]: [max(0.02, _phase_rate(kind, s["id"], ph) * m) for ph in s["phases"]] for s in self.steps if s.get("phases")}
        self.weights = {s["id"]: sum(self.phase_w[s["id"]]) if s["id"] in self.phase_w else max(0.02, rate(kind, s["id"]) * m) for s in self.steps}

    def write(self, line):
        line = line.rstrip("\n")
        with LOCK:
            self.log.append(line)
            if len(self.log) > 20000:
                del self.log[:5000]
        if self.log_file:
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass

    def _light(self, step):
        return bool(step.get("light")) or step["id"] in LIGHT_STEPS

    def _take_gpu(self):
        """wait for this job's turn in the render queue; False when it was cancelled while waiting"""
        if self.has_gpu or not queue_on():
            return True
        t0 = time.time()
        said = False
        with QCOND:
            self.wants_gpu = True
            while True:
                if self.cancel_flag:
                    self.wants_gpu = False
                    return False
                line = waiting()
                outside = _outside_build() if GPU["holder"] is None else None
                if GPU["holder"] is None and not outside and line and line[0] is self:
                    GPU["holder"], self.has_gpu, self.wants_gpu = self.id, True, False
                    if slots() >= 2 and SHARE["job"] is None:   # second render slot free: run there, the next one may start
                        SHARE["job"], GPU["holder"] = self.id, None
                        QCOND.notify_all()
                    break
                if not said:
                    self.status = "queued"
                    ahead = GPU["holder"] and JOBS.get(GPU["holder"])
                    self.write(f"-- waiting to render: #{queue_pos(self)} in line" + (f" (rendering now: {ahead.title})" if ahead else
                               f" (an earlier build is still running: {outside.get('title')})" if outside else ""))
                    said = True
                QCOND.wait(timeout=2)
        self.wait_s += time.time() - t0
        self.status = "running"
        if said:
            self.write(f"-- your turn after {(time.time() - t0) / 60:.1f} min in line")
        return True

    def _share_gpu(self):
        """hand the queue on but keep running (see SHARE); only one build shares at a time"""
        with QCOND:
            if GPU["holder"] != self.id or SHARE["job"] not in (None, self.id):
                return
            SHARE["job"], GPU["holder"] = self.id, None
            QCOND.notify_all()
            line = waiting()
        if line:
            self.write("-- the next video can start now; this one finishes its intro alongside it")

    def _give_gpu(self):
        with QCOND:
            if GPU["holder"] == self.id:
                GPU["holder"] = None
            if SHARE["job"] == self.id:
                SHARE["job"] = None
                # the build rendering now may already be in its own intro (it could not share while this one did): pass on now
                h = JOBS.get(GPU["holder"]) if GPU["holder"] else None
                cur = h and next((st for st in h.steps if st["id"] == h.current), None)
                if h and slots() >= 2:   # two render slots: the build rendering now moves over, the next in line starts
                    SHARE["job"], GPU["holder"] = h.id, None
                elif cur and cur.get("share_gpu") and h.step_status.get(cur["id"]) == "running" and share_on():
                    SHARE["job"], GPU["holder"] = h.id, None
                    h.write("-- the next video can start now; this one finishes its intro alongside it")
            self.has_gpu = False
            self.wants_gpu = False
            QCOND.notify_all()

    def run(self):
        self.status, self.started = "running", time.time()
        self.write(f"== {self.title} ({time.strftime('%H:%M:%S')})")
        try:
            for k, step in enumerate(self.steps):
                if self.cancel_flag:
                    self.status = "cancelled"
                    break
                self.current = step["id"]
                if not step.get("force") and step.get("outputs") and not stale(step["outputs"], step.get("inputs", [])):
                    self.step_status[step["id"]] = "skipped"
                    self.write(f"-- {step['label']}: up to date, skipped")
                    continue
                if self._light(step):
                    if self.has_gpu and not self.bg and all(self._light(s) for s in self.steps[k:]):
                        self._give_gpu()   # only AI steps left: the next video can start rendering
                elif not self._take_gpu():
                    self.status = "cancelled"
                    break
                if step.get("share_gpu") and self.has_gpu and queue_on() and share_on():
                    self._share_gpu()
                # parallel steps (user 2026-10-22: faster first builds): "background": True starts the step and moves on;
                # a later step with "wait_for": [ids] waits for it (e.g. the CPU B-roll scan runs while the GPU transcribes)
                if step.get("background"):
                    self._start_bg(step)
                    continue
                for wid in step.get("wait_for", []):
                    if not self._wait_bg(wid):
                        self.status, self.error = "failed", f"{wid} failed"
                        break
                if self.status == "failed":
                    self.write(f"!! {self.error}")
                    break
                self.step_status[step["id"]] = "running"
                self.write(f"-- {step['label']}")
                t0 = time.time()
                self.step_started[step["id"]] = t0
                rc = self._run_cmd(step)
                # a failed step gets one more try before the build fails (user 2026-10-22: "if a render fails, try it again"):
                # GPU / ffmpeg / HyperFrames hiccups pass on a rerun, and the pipelines resume from the files already made.
                # The first try's log is kept as <log>.try1.
                if rc != 0 and not self.cancel_flag and not step.get("no_retry"):
                    logp = LOGDIR / f"{self.id}-{step['id'].replace(':', '_')}.log"
                    try:
                        os.replace(logp, str(logp) + ".try1")
                    except OSError:
                        pass
                    self.write(f"!! {step['label']} " + ("froze" if self.stalled.get(step["id"]) else f"failed (exit {rc})") + "; trying it once more")
                    rc = self._run_cmd(step)
                if self.cancel_flag:
                    self.step_status[step["id"]] = "cancelled"
                    self.status = "cancelled"
                    break
                if rc != 0:
                    self.step_secs[step["id"]] = round(time.time() - t0, 1)
                    self.step_status[step["id"]] = "failed"
                    self.status = "failed"
                    self.error = f"{step['label']} " + ("froze twice (nothing written)" if self.stalled.get(step["id"], 0) >= 2 else f"failed (exit {rc})")
                    self.write(f"!! {self.error}")
                    break
                self.step_status[step["id"]] = "done"
                self.step_secs[step["id"]] = round(time.time() - t0, 1)
                self.write(f"   done in {(time.time() - t0) / 60:.1f} min")
                _record(self.kind, step["id"], time.time() - t0, self.minutes)
                if step["id"] not in self.phase_w:   # (a phased step adds its phases one by one in _end_phase)
                    self._measure(self.weights[step["id"]], time.time() - t0)
                if callable(step.get("after")):
                    try:
                        step["after"](self)
                    except Exception as e:  # noqa
                        self.write(f"   (after-step hook: {e})")
            else:
                for wid in list(self.bg):   # a background step nothing waited for still has to finish
                    if not self._wait_bg(wid):
                        self.status, self.error = "failed", f"{wid} failed"
                        break
                else:
                    self.status = "done"
        except Exception as e:  # noqa
            self.status, self.error = "failed", str(e)
            self.write(f"!! {e}")
        self._give_gpu()
        with QCOND:
            if self.id in QUEUE:
                QUEUE.remove(self.id)
            QCOND.notify_all()
        self.ended = time.time()
        _registry_drop_job(self.id)
        self.write(f"== {self.status} ({(self.ended - self.started) / 60:.1f} min)")
        if self.on_done:
            try:
                self.on_done(self)
            except Exception as e:  # noqa
                self.write(f"!! on_done: {e}")

    def _start_bg(self, step):
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", PYTHONUNBUFFERED="1")
        env.update(step.get("env") or {})
        LOGDIR.mkdir(parents=True, exist_ok=True)
        logp = LOGDIR / f"{self.id}-{step['id'].replace(':', '_')}.log"
        fh = open(logp, "w", encoding="utf-8", errors="replace")
        proc = subprocess.Popen(step["cmd"], cwd=step.get("cwd") or None, env=env, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                shell=isinstance(step["cmd"], str), creationflags=CREATE_NO_WINDOW | DETACHED)
        fh.close()
        _registry_set(proc.pid, {"job": self.id, "project_id": self.project_id, "title": self.title, "step": step["label"],
                                 "started": self.started, "step_started": time.time(), "kind": self.kind, "minutes": self.minutes, "log": str(logp),
                                 "light": self._light(step)})
        self.bg[step["id"]] = (proc, time.time(), logp, step)
        self.step_status[step["id"]] = "running"
        self.step_started[step["id"]] = time.time()
        self.write(f"-- {step['label']} (running alongside the next steps)")

    def _wait_bg(self, sid):
        """wait for a background step, copy its log in, record it like a normal step; False when it failed"""
        if sid not in self.bg:
            return True
        proc, t0, logp, step = self.bg.pop(sid)
        while proc.poll() is None:
            if self.cancel_flag:
                self._kill(proc)
                self.step_status[sid] = "cancelled"
                return False
            time.sleep(0.3)
        try:
            for line in open(logp, encoding="utf-8", errors="replace").read().splitlines():
                if line.strip():
                    self.write("   [" + sid + "] " + line)
        except OSError:
            pass
        secs = time.time() - t0
        self.step_secs[sid] = round(secs, 1)
        if proc.returncode != 0:
            self.step_status[sid] = "failed"
            self.write(f"!! {step['label']} failed (exit {proc.returncode})")
            return False
        self.step_status[sid] = "done"
        self.write(f"   {step['label']} done in {secs / 60:.1f} min (in parallel)")
        _record(self.kind, sid, secs, self.minutes)
        self._measure(self.weights[sid], secs)
        return True

    def _measure(self, est, actual):
        """a step/phase finished: est vs actual seconds feed the job's speed (used for the ETA of what is left)"""
        if est > 0 and actual > 0:
            self.measured[0] += est
            self.measured[1] += actual

    def speed(self):
        """actual / estimated time of the work finished so far in this build (1 = as guessed); trusted after ~1 min of it"""
        est, act = self.measured
        now = time.time()
        for sid, st in self.step_status.items():   # the running step/phase counts too once it runs past its guess
            if st != "running":
                continue
            if sid in self.phase_w:
                k, t0 = self.phase.get(sid) or (0, self.step_started.get(sid, now))
                w = self.phase_w[sid][k]
            else:
                t0, w = self.step_started.get(sid, now), self.weights[sid]
            if now - t0 > w:   # (at half weight: one phase that hangs should not triple the whole ETA at once)
                est += 0.5 * w * eased(now - t0, w)
                act += 0.5 * (now - t0)
        if est < 60 and act < 60:
            return 1.0
        f = act / max(est, 1.0)
        trust = min(1.0, max(est, act) / 300.0)   # a single short step says little; 5 min of finished work says a lot
        return max(0.4, min(3.0, 1.0 + (f - 1.0) * trust))

    @staticmethod
    def _kill(p):
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, creationflags=CREATE_NO_WINDOW)
            else:
                p.kill()
        except Exception:
            pass

    def _run_cmd(self, step):
        cmd = step["cmd"]
        # pythonw has no console, so every ffmpeg/python the step starts pops up its own console window (flashing all build long).
        # python.exe + CREATE_NO_WINDOW gets one hidden console that all the children share.
        if not isinstance(cmd, str) and cmd and str(cmd[0]).lower().endswith("pythonw.exe"):
            con = str(cmd[0])[:-len("pythonw.exe")] + "python.exe"
            if os.path.exists(con):
                cmd = [con] + list(cmd[1:])
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        # print() to a log FILE is block-buffered: edit_review's phase lines only arrived at the very end, so the progress
        # bar sat at 3.7% for the whole build (dhgate rick owens 2026-10-22). Unbuffered = live phases + log.
        env["PYTHONUNBUFFERED"] = "1"
        env.update(step.get("env") or {})
        self.write("   $ " + (cmd if isinstance(cmd, str) else " ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd)))
        # the step writes to a log FILE, never a pipe to this app: when the app restarts, a pipe breaks and the build dies on
        # its next print (lost the Shein draft at 14:59, 2026-10-21). With a file it keeps running and a new app re-adopts it.
        LOGDIR.mkdir(parents=True, exist_ok=True)
        logp = LOGDIR / f"{self.id}-{step['id'].replace(':', '_')}.log"
        fh = open(logp, "w", encoding="utf-8", errors="replace")
        self.proc = subprocess.Popen(cmd, cwd=step.get("cwd") or None, env=env, stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                     shell=isinstance(cmd, str), creationflags=CREATE_NO_WINDOW | DETACHED)
        fh.close()
        _registry_set(self.proc.pid, {"job": self.id, "project_id": self.project_id, "title": self.title, "step": step["label"],
                                      "started": self.started, "step_started": time.time(), "kind": self.kind, "minutes": self.minutes, "log": str(logp),
                                      "light": self._light(step)})
        phases = step.get("phases") or []
        sid = step["id"]
        t_start = time.time()
        self.live.pop(sid, None)
        self.out_len.pop(sid, None)
        act = self.activity[sid] = {"t": t_start, "cpu": None, "stuck_s": 0, "io": t_start}
        stats_said = [0.0]
        limit = stall_limit(step, self.minutes)
        scan = [0.0, 0.0]   # last folder scan, newest write seen

        def feed(line):
            now = time.time()
            act["t"] = act["io"] = now
            m = STATS_RE.search(line)
            if m:   # ffmpeg -stats: real progress of the render running in this step
                self._live_time(sid, int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)))
                if now - stats_said[0] < 30:   # (a stats line every half second would flood the log)
                    return
                stats_said[0] = now
            elif PCT_RE.search(line):
                self._live_frac(sid, float(PCT_RE.search(line).group(1)) / 100)
            else:
                for rx, secs in OUTLEN_RES:
                    mm = rx.search(line)
                    if mm and (rx.pattern.startswith("Duration") is False or sid not in self.out_len):
                        try:
                            self.out_len[sid] = secs(mm)
                        except (ValueError, ZeroDivisionError):
                            pass
                        break
            self.write("   " + line)
            cur = self.phase.get(sid)
            for i, ph in enumerate(phases):
                if i > (cur[0] if cur else -1) and ph[0] and re.search(ph[0], line):
                    self._to_phase(step, i, now)
                    break

        def look(now):
            """files the step writes in a known order mark its phases (a pipeline that prints nothing for 40 min)"""
            cur = self.phase.get(sid)
            for i in range(len(phases) - 1, (cur[0] if cur else -1), -1):
                glob = phases[i][4] if len(phases[i]) > 4 else None
                if not glob:
                    continue
                try:
                    hit = any(f.stat().st_mtime >= t_start - 1 for f in Path(step.get("cwd") or ".").glob(glob))
                except OSError:
                    hit = False
                if hit:
                    act["t"] = now
                    self._to_phase(step, i, now)
                    break
            c = _tree_cpu(self.proc.pid) if self.proc else None
            if c is not None:
                if act["cpu"] is None or c - act["cpu"][0] > 2.0:   # > 2 CPU-seconds since the last mark = working
                    if act["cpu"] is not None:
                        act["t"] = max(act["t"], now)
                    act["cpu"] = (c, now)
            act["stuck_s"] = round(now - act["t"]) if now - act["t"] > STUCK_AFTER else 0
            if act["stuck_s"] and not act.get("said"):
                act["said"] = True
                self.write(f"!! no output, no new files and no CPU use for {(now - act['t']) / 60:.0f} min: this step may be stuck (it keeps running; cancel it if it does not move)")
            elif not act["stuck_s"] and act.get("said"):
                act["said"] = False
                self.write("   (moving again)")
            if limit and self.proc and not act.get("killed"):
                if now - scan[0] > min(60, limit / 3):
                    scan[0] = now
                    w = newest_write(step.get("cwd"))
                    if w > scan[1]:
                        scan[1] = w
                        act["io"] = max(act["io"], min(w, now))
                if now - act["io"] > limit:
                    act["killed"] = True
                    mins = (now - act["io"]) / 60
                    self.write(f"!! frozen: no log line and no file written for {mins:.0f} min; stopping this step so it can be tried again")
                    try:
                        import notify
                        notify.notify("Render froze", f"{self.title}: {step['label']} wrote nothing for {mins:.0f} min. Stopped it; "
                                      + ("trying it once more." if not step.get("no_retry") and not self.stalled.get(sid) else "the build failed."))
                    except Exception:
                        pass
                    self.stalled[sid] = self.stalled.get(sid, 0) + 1
                    self._kill(self.proc)
        with open(logp, "r", encoding="utf-8", errors="replace") as rd:
            buf = ""
            looked = 0.0
            while True:
                chunk = rd.read()
                if chunk:
                    buf += chunk
                    *lines, buf = re.split(r"\r?\n|\r", buf)
                    for line in lines:
                        if line.strip():
                            feed(line)
                elif self.proc.poll() is not None:
                    rest = rd.read()
                    for line in re.split(r"\r?\n|\r", buf + rest):
                        if line.strip():
                            feed(line)
                    break
                else:
                    time.sleep(0.3)
                if time.time() - looked > 5:
                    looked = time.time()
                    try:
                        look(looked)
                    except Exception:
                        pass
        rc = self.proc.returncode
        self.proc = None
        act["stuck_s"] = 0
        if rc == 0:   # (no marker seen at all = a resumed run that had nothing to do, or a silent one: no phase time to learn)
            self._end_phase(step, time.time(), learn=sid in self.phase)
        return rc

    def _live_time(self, sid, t):
        """an ffmpeg stats line said it has written t seconds of output"""
        total = self.out_len.get(sid) or max(self.minutes, 0.1) * 60
        lv = self.live.get(sid)
        if lv is None or t + 1 < lv["t"]:   # a new ffmpeg run in this step starts from where the step's bar is now
            base = self._step_frac(sid) if lv is None else lv["base"] + (1 - lv["base"]) * lv["r"]
            lv = self.live[sid] = {"base": min(0.95, base), "r": 0.0, "t": 0.0, "phase": (self.phase.get(sid) or (0,))[0], "at": time.time()}
        lv["t"] = t
        lv["r"] = max(lv["r"], min(0.99, t / total)) if total > 0 else lv["r"]

    def _live_frac(self, sid, r):
        """the step said r (0..1) of its running phase is done"""
        lv = self.live.get(sid)
        if lv is None:
            lv = self.live[sid] = {"base": 0.0, "r": 0.0, "t": 0.0, "phase": (self.phase.get(sid) or (0,))[0], "at": time.time()}
        lv["r"] = max(lv["r"], min(0.99, r))

    def _to_phase(self, step, i, now):
        cur = self.phase.get(step["id"])
        # a jump over phases (a file marker that skipped some) is not a clean time for one phase: not learned
        self._end_phase(step, now, learn=i == (cur[0] if cur else 0) + 1)
        self.phase[step["id"]] = (i, now)
        self.live.pop(step["id"], None)

    def _end_phase(self, step, now, learn=True):
        """the running phase just finished: remember how long it took per footage minute for the next estimate"""
        # phase 0 has no marker of its own: it runs from the step's start
        cur = self.phase.get(step["id"]) or (0, self.step_started.get(step["id"])) if step.get("phases") else None
        if cur and cur[1]:
            if learn:
                _record(self.kind, _phase_key(step["id"], step["phases"][cur[0]]), now - cur[1], self.minutes)
            self._measure(self.phase_w[step["id"]][cur[0]], now - cur[1])

    def _step_frac(self, sid):
        """0..1 of the running step (or of its running phase, for a phased step) done, by the best signal there is"""
        now = time.time()
        if sid in self.phase_w:
            k, t0 = self.phase.get(sid) or (0, self.step_started.get(sid, now))
            w = self.phase_w[sid][k]
        else:
            k, t0, w = 0, self.step_started.get(sid, now), self.weights[sid]
        f = eased(now - t0, w)
        lv = self.live.get(sid)
        if lv and lv.get("phase", 0) == k:   # the ffmpeg render's own time= beats the guess
            f = lv["base"] + (1 - lv["base"]) * lv["r"] * 0.98
        return min(f, 0.995)

    def _left_of_running(self, sid):
        """seconds the running step/phase still needs: from the render's own speed when there is one, else from the guess"""
        now = time.time()
        if sid in self.phase_w:
            k, t0 = self.phase.get(sid) or (0, self.step_started.get(sid, now))
            w = self.phase_w[sid][k]
        else:
            k, t0, w = 0, self.step_started.get(sid, now), self.weights[sid]
        spent = max(0.0, now - t0)
        f = self._step_frac(sid)
        lv = self.live.get(sid)
        if lv and lv.get("phase", 0) == k and lv["r"] > 0.02 and now - lv["at"] > 15:
            return (now - lv["at"]) * (1 - lv["r"]) / lv["r"]   # the render's measured speed
        if spent <= 0.7 * w:
            return (w - spent) * self.speed()
        return max(spent * (1 - f) / max(f, 0.05), (1 - f) * w * self.speed())

    def cancel(self):
        self.cancel_flag = True
        for proc, *_ in list(self.bg.values()):
            self._kill(proc)
        p = self.proc
        if p:
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, creationflags=CREATE_NO_WINDOW)
                else:
                    p.kill()
            except Exception:
                pass

    def progress(self):
        """0..1 done by estimated time, seconds elapsed, seconds left, the running step and its index."""
        total = sum(self.weights.values()) or 1.0
        done = 0.0
        left = 0.0        # seconds still to go: the running step/phase from its own pace, the rest from the guesses x this job's speed
        pending = 0.0
        run_left = 0.0
        cur, idx = None, 0
        now = time.time()
        stuck = 0
        live = False
        for i, s in enumerate(self.steps):
            st = self.step_status[s["id"]]
            w = self.weights[s["id"]]
            if st in ("done", "skipped"):
                done += w
            elif st == "running":
                cur, idx = s, i
                f = self._step_frac(s["id"])
                if s["id"] in self.phase_w:
                    pw = self.phase_w[s["id"]]
                    k = (self.phase.get(s["id"]) or (0,))[0]
                    # phases before the current one are finished (or skipped because a resumed run already had them)
                    done += sum(pw[:k]) + f * pw[k]
                    pending += sum(pw[k + 1:])
                else:
                    done += f * w
                run_left = max(run_left, self._left_of_running(s["id"]))   # parallel steps overlap: the longest one counts
                stuck = max(stuck, (self.activity.get(s["id"]) or {}).get("stuck_s", 0))
                live = live or s["id"] in self.live
            elif st == "pending":
                pending += w
        left += run_left + pending * self.speed()
        if self.status in ("done",):
            done = total
        elapsed = (self.ended or now) - (self.started or now) if self.started else 0
        if self.status != "running":
            left = 0.0
        label = cur["label"] if cur else ""
        n_idx, n_count = (idx + 1 if cur else len(self.steps)), len(self.steps)
        if cur and cur.get("stages"):
            # a one-script pipeline counts its own stages: "step 3/8: Privacy blur"
            stages = cur["stages"]
            ph = self.phase.get(cur["id"])
            pdef = cur["phases"][ph[0] if ph else 0]
            label = pdef[1] if ph else "Starting"
            n_idx, n_count = stages.index(pdef[2]) + 1 if pdef[2] in stages else 1, len(stages)
        pct = 100 * done / total
        if self.status == "running" and self.started:
            # by time too: work done so far vs the (speed-corrected) time left. A phase guessed at 20 s that runs 15 min is a
            # sliver of the step weights, but by time the bar keeps moving with the clock (sp5der 2026-10-23: 28% for 50 min)
            work = max(0.0, now - self.started - self.wait_s)
            if work + left > 0:
                pct = max(pct, 100 * work / (work + left))
        if self.status == "running":
            # never backwards (the ETA grew, a new render inside the step) and never 100 before the end; while the estimate is
            # behind what was shown the bar creeps on (~1% of what is left per minute) instead of freezing
            dt = min(60.0, now - (self.shown_at or now))
            creep = self.shown_pct + (99.0 - self.shown_pct) * dt / 6000.0
            pct = min(max(pct, creep), 99.0)
            self.shown_pct, self.shown_at = pct, now
        out = {"pct": round(pct, 1), "elapsed_s": round(elapsed), "eta_s": round(left), "step": label,
               "step_index": n_idx, "step_count": n_count}
        if self.status == "running":
            out["speed"] = round(self.speed(), 2)
            if live:
                out["live"] = True        # the % of the running step comes from the render itself
            if stuck:
                out["stuck_s"] = stuck    # no output, no files, no CPU for this long
        return out

    def view_steps(self):
        """the steps for the progress segments; a one-script pipeline shows its own stages instead of one long block"""
        out = []
        for s in self.steps:
            st = self.step_status[s["id"]]
            if not s.get("stages"):
                out.append({"id": s["id"], "label": s["label"], "status": st})
                continue
            ph = self.phase.get(s["id"])
            cur_stage = s["phases"][ph[0]][2] if ph else (s["stages"][0] if st == "running" else None)
            ci = s["stages"].index(cur_stage) if cur_stage in s["stages"] else -1
            for i, name in enumerate(s["stages"]):
                if st in ("done", "skipped"):
                    ss = st
                elif st == "pending":
                    ss = "pending"
                else:
                    ss = "done" if i < ci else (st if i == ci else "pending")
                out.append({"id": f"{s['id']}:{i}", "label": name, "status": ss})
        return out

    def view(self, frm=0):
        with LOCK:
            lines = self.log[frm:]
            total = len(self.log)
        return {"id": self.id, "title": self.title, "project_id": self.project_id, "status": self.status, "current": self.current, "progress": self.progress(),
                "step_secs": self.step_secs, "minutes": round(self.minutes, 1),
                "started": self.started, "ended": self.ended, "steps": self.view_steps(),
                "log": lines, "log_from": frm, "log_total": total, "error": self.error,
                "queue": self.queue_view()}

    def est_left(self):
        """estimated seconds this job still needs (all of it while it waits)"""
        if self.status in ("done", "failed", "cancelled"):
            return 0
        if self.status == "running" and self.has_gpu:
            return self.progress()["eta_s"]
        return sum(w for s, w in ((s, self.weights[s["id"]]) for s in self.steps) if self.step_status[s["id"]] in ("pending", "running"))

    def queue_view(self):
        """render-queue state: rendering | waiting (#pos, est. seconds until its turn) | ai (light step, no GPU needed yet)"""
        if self.status not in ("queued", "running"):
            return None
        if self.has_gpu:
            return {"state": "rendering"}
        if self.wants_gpu:
            line = waiting()
            ahead = (JOBS[GPU["holder"]].est_left() if GPU["holder"] in JOBS else 0) + sum(j.est_left() for j in line[:line.index(self)] if j is not self) if self in line else 0
            return {"state": "waiting", "pos": queue_pos(self), "of": len(line), "wait_s": round(ahead)}
        cur = next((s for s in self.steps if s["id"] == self.current), None)
        if cur and self._light(cur) and self.status == "running":
            return {"state": "ai", "step": cur["label"]}
        return {"state": "rendering" if not queue_on() and self.status == "running" else "starting"}


def start(job):
    JOBS[job.id] = job
    with QCOND:
        QUEUE.append(job.id)
    threading.Thread(target=job.run, daemon=True).start()
    return job


def gpu_view():
    """the whole render queue for the Queue page: who renders now, who waits (in order)"""
    with QCOND:
        holder = JOBS.get(GPU["holder"]) if GPU["holder"] else None
        line = waiting()
    return {"on": queue_on(), "rendering": holder.id if holder else None, "waiting": [j.id for j in line],
            "outside": _outside_build() if not holder else None}


def running_for(project_id):
    return [j for j in JOBS.values() if j.project_id == project_id and j.status in ("queued", "running")]


def all_views():
    return [j.view(frm=max(0, len(j.log) - 3)) for j in sorted(JOBS.values(), key=lambda j: j.started or 0, reverse=True)]

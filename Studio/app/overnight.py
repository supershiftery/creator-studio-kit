"""Overnight lab: edits old Drive footage while the user sleeps, one video at a time, after any build already running.

    python overnight.py plan [--n 5]   pick tonight's videos (different channels, intro audio required) -> data/overnight/<date>.json
    python overnight.py prep           copy them off Drive + normalise to 3840x1080 H.264 (what the pipelines expect)
    python overnight.py run            plan + prep if needed, then create each as a Studio project and wait for its draft; morning report
    python overnight.py report         (re)write the morning report for tonight's plan

Drive is only read. Copies live in {{PROJECTS_ROOT}}\\_overnight\\staging until the project has its own raw\\ copy, then go.
State (what was already done, which channel went last) is data/overnight/state.json, so nothing is edited twice.
"""
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent
DATA = APP.parent / "data" / "overnight"
DATA.mkdir(parents=True, exist_ok=True)
STATE = DATA / "state.json"
DRIVE_RAW = Path(r"{{DRIVE_RAW}}")
LAB = Path(r"{{PROJECTS_ROOT}}\_overnight")
STAGING, REPORTS, LOGS = LAB / "staging", LAB / "reports", LAB / "logs"
API = "http://127.0.0.1:8765/api/"
STOP_STARTING_AT = "07:30"     # no new build starts after this; the user reviews in the morning

# Drive folder -> (Studio channel, project type). Anything not listed is a product review under its own name.
def _channels():
    try:
        s = json.loads((Path(__file__).resolve().parent.parent / "data" / "settings.json").read_text(encoding="utf-8"))
    except Exception:
        s = {}
    return {c.get("drive") or c["name"]: (c["name"], (c.get("types") or ["review"])[0]) for c in s.get("channels", [])}


CHANNELS = _channels()
PRIORITY = list(CHANNELS)   # Drive folders in the order they are listed in Settings
SKIP_CHANNELS = {"Short Form", "Untitled"}
VIDEO, AUDIO = {".mp4", ".mov", ".mkv"}, {".wav", ".m4a", ".mp3"}
MAIN_MIN = 700e6               # smaller videos are extras (B-roll, fixes, on-body clips)
INTRO_MAX = 60e6               # a 250 MB+ wav is a full-length mic recording, not an intro VO

LOG_FILE = None


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    if LOG_FILE:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def read_json(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(p, data):
    Path(p).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def tonight():
    # a run that starts after midnight belongs to the night before it, so plan/prep/run share one file
    return time.strftime("%Y-%m-%d", time.localtime(time.time() - 8 * 3600))


def api(path, body=None, timeout=60):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------- picking ----------

def part_no(name):
    m = re.search(r"part\s*(\d+)", name, re.I)
    return int(m.group(1)) if m else 0


def rec_start(f):
    """Recording start: the OBS file name ("2025-12-16 07-41-25") when it has one, else modified time minus duration."""
    m = re.search(r"(20\d\d)-(\d\d)-(\d\d)[ _T](\d\d)-(\d\d)-(\d\d)", f.name)
    return time.mktime(tuple(int(x) for x in m.groups()) + (0, 0, -1)) if m else f.stat().st_mtime - duration(f)


def scan_project(folder):
    """What one Drive project folder holds, or None when it isn't something we can run unattended yet."""
    files = [f for f in folder.rglob("*") if f.is_file() and f.name.lower() != "desktop.ini"]
    sized = [(f, f.stat().st_size) for f in files]
    intros = [f for f, s in sized if f.suffix.lower() in AUDIO and 1e6 < s < INTRO_MAX]
    parts = [f for f, s in sized if f.suffix.lower() in VIDEO and part_no(f.name)]
    mains = parts or [f for f, s in sized if f.suffix.lower() in VIDEO and s >= MAIN_MIN]
    extras = [f for f, s in sized if f.suffix.lower() in VIDEO and f not in mains]
    if len(intros) != 1 or not mains or any(m.name.lower() in EDITED for m in mains):
        return None
    if len(mains) > 1:
        if not all(part_no(m.name) for m in mains):
            return None    # several big recordings without "part N" names: which is the video is a judgement call
        mains.sort(key=lambda m: part_no(m.name))
    elif not parts:
        # a smaller second recording with the main's side-by-side size (an OBS continuation, "2025-12-16 07-41-25.mp4") is
        # the rest of the video, not B-roll: joined after the main by recording start (lv trainer 2026-10-23)
        ref = probe(mains[0])
        cont = [f for f in extras if f.suffix.lower() in VIDEO and probe(f)[1:] == ref[1:] and ref[1] and ref[1] / ref[2] >= 2.5
                and duration(f) >= 30]
        cont.sort(key=lambda f: rec_start(f))
        mains += cont
        extras = [f for f in extras if f not in cont]
    return {"drive": str(folder), "title": folder.name.strip(), "intro": str(intros[0]), "mains": [str(m) for m in mains],
            "broll": [str(e) for e in extras], "bytes": sum(s for f, s in sized if str(f) in map(str, mains))}


def edited_sources():
    """Recording names already edited by hand or by Studio (raw\\source*.txt / source.concat.txt name the originals)."""
    names = set()
    for txt in list(Path(r"{{PROJECTS_ROOT}}").glob("*/raw/source*.txt")) + list(Path(r"{{PROJECTS_ROOT}}").glob("*/studio.json")):
        for line in txt.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.search(r"([^\\/']+\.(?:mp4|mov|mkv))", line, re.I)
            if m:
                names.add(m.group(1).lower())
    return names


EDITED = edited_sources()


def existing_titles():
    try:
        return {p["title"].lower() for p in api("state")["projects"]}
    except Exception:
        return set()


def plan(n=5):
    out = DATA / f"{tonight()}.json"
    if out.exists():
        return read_json(out, {})
    state = merged_state()
    # "skip" = folders the user ruled out (e.g. dead mic for part of it), with the reason
    done, have = set(state["done"]) | set(state.get("skip", {})), existing_titles() | set(read_json(KNOWN, {}).get("titles", []))
    by_channel = {}
    for ch in sorted(DRIVE_RAW.iterdir()):
        if not ch.is_dir() or ch.name in SKIP_CHANNELS:
            continue
        for proj in sorted(ch.iterdir()):
            if proj.is_dir() and str(proj) not in done and proj.name.strip().lower() not in have:
                info = scan_project(proj)
                if info:
                    info["channel"], info["type"] = CHANNELS.get(ch.name, (ch.name, "review"))
                    by_channel.setdefault(ch.name, []).append(info)
    # channels that went longest ago first (never-run ones first, active channels before retired ones), smallest recording within a channel
    order = sorted(by_channel, key=lambda c: (state["channel_last"].get(c, ""), PRIORITY.index(c) if c in PRIORITY else len(PRIORITY)))
    picks = [min(by_channel[c], key=lambda i: i["bytes"]) for c in order[:n]]
    doc = {"night": tonight(), "planned": time.strftime("%Y-%m-%d %H:%M"), "videos": picks,
           "eligible": {c: len(v) for c, v in by_channel.items()}, "machine": machine()}
    write_json(out, doc)
    return doc


# The laptop runs the lab every night on its own (user 2026-10-26: "I just wanted to be where I can turn off my computer").
# Its own {{PROJECTS_ROOT}} and Studio only hold what it built, so the desktop sends what IT knows (presync.py writes
# desktop_known.json every 30 min): Drive folders done or skipped there, its project titles, recordings already edited.
KNOWN = DATA / "desktop_known.json"


def machine():
    try:
        return json.loads((APP.parent / "data" / "settings.json").read_text(encoding="utf-8")).get("machine_name") or "Desktop"
    except Exception:
        return "Desktop"


def merged_state():
    """this machine's state.json + the other machine's done / skip / channel_last (the later run per channel counts)"""
    state = read_json(STATE, {"done": [], "channel_last": {}})
    known = read_json(KNOWN, {})
    state["done"] = sorted(set(state["done"]) | set(known.get("done", [])))
    state["skip"] = {**known.get("skip", {}), **state.get("skip", {})}
    for ch, t in (known.get("channel_last") or {}).items():
        state["channel_last"][ch] = max(t, state["channel_last"].get(ch, ""))
    EDITED.update(n.lower() for n in known.get("edited", []))
    return state


def desktop_known():
    """what this machine knows, for the other one's merged_state()"""
    state = read_json(STATE, {"done": [], "channel_last": {}})
    return {"from": machine(), "at": time.strftime("%Y-%m-%d %H:%M"), "done": state["done"], "skip": state.get("skip", {}),
            "channel_last": state["channel_last"], "titles": sorted(existing_titles()), "edited": sorted(edited_sources())}


def add_project(pid):
    """An existing Studio project (footage + notes already in it) as tonight's FIRST video: built back to back with the rest.
    Added 2026-10-21 for Top 10 Minecraft Servers (the user needed the GPU for recording until the lab ran)."""
    doc = plan()
    p = api(f"project?id={pid}")
    doc["videos"] = [v for v in doc["videos"] if v.get("studio_project") != pid]
    doc["videos"].insert(0, {"studio_project": pid, "title": p["title"], "channel": p.get("channel", ""), "type": p["type"],
                             "drive": p.get("source") or p["path"], "project_path": p["path"]})
    write_json(DATA / f"{doc['night']}.json", doc)
    return doc["videos"][0]


def add(drive_channel):
    """One more video for tonight from a Drive channel folder (the next smallest not planned, done or skipped)."""
    doc = plan()
    state = merged_state()   # (the laptop: + what the desktop already did)
    taken = set(state["done"]) | set(state.get("skip", {})) | {v["drive"] for v in doc["videos"]}
    have = existing_titles() | set(read_json(KNOWN, {}).get("titles", []))
    cands = []
    for proj in sorted((DRIVE_RAW / drive_channel).iterdir()):
        if proj.is_dir() and str(proj) not in taken and proj.name.strip().lower() not in have:
            info = scan_project(proj)
            if info:
                info["channel"], info["type"] = CHANNELS.get(drive_channel, (drive_channel, "review"))
                cands.append(info)
    if not cands:
        raise SystemExit(f"nothing left to run in {drive_channel}")
    pick = min(cands, key=lambda i: i["bytes"])
    doc["videos"].append(pick)
    write_json(DATA / f"{doc['night']}.json", doc)
    return pick


# ---------- copying off Drive ----------

def ffmpeg():
    return shutil.which("ffmpeg") or "ffmpeg"


def probe(path):
    r = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height",
                        "-of", "json", str(path)], capture_output=True, text=True)
    s = (json.loads(r.stdout or "{}").get("streams") or [{}])[0]
    return s.get("codec_name"), s.get("width"), s.get("height")


def normalise(src, dest):
    """3840x1080 H.264 as recorded now. Older 5120x1440 HEVC recordings are the same side-by-side layout, just bigger."""
    codec, w, h = probe(src)
    if (codec, w, h) == ("h264", 3840, 1080):
        log(f"  copy {Path(src).name}")
        shutil.copy2(src, dest)
        return
    log(f"  convert {Path(src).name} ({codec} {w}x{h} -> h264 3840x1080)")
    tmp = dest.with_suffix(".part.mp4")
    subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(src), "-map", "0:v:0", "-map", "0:a",
                    "-vf", "scale=3840:1080:flags=lanczos", "-c:v", "h264_nvenc", "-preset", "p5", "-cq", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "copy", "-movflags", "+faststart", str(tmp)], check=True)
    tmp.replace(dest)


def duration(path):
    r = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def prep_one(v):
    t0 = time.time()
    d = STAGING / re.sub(r'[<>:"/\\|?*]', "", v["title"])
    d.mkdir(parents=True, exist_ok=True)
    main = d / "main.mp4"
    if not main.exists():
        if len(v["mains"]) == 1:
            normalise(v["mains"][0], main)
        else:
            parts = []
            for i, m in enumerate(v["mains"], 1):
                p = d / f"part{i}.mp4"
                if not p.exists():
                    normalise(m, p)
                parts.append(p)
            lst = d / "parts.txt"
            lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
            subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-map", "0", "-c", "copy", str(main)], check=True)
            for p in parts:
                p.unlink()
    intro = d / ("intro" + Path(v["intro"]).suffix.lower())
    if not intro.exists():
        shutil.copy2(v["intro"], intro)
    broll = []
    for b in v["broll"]:
        t = d / "broll" / Path(b).name
        t.parent.mkdir(exist_ok=True)
        if not t.exists():
            shutil.copy2(b, t)
        broll.append(str(t))
    v["staged"] = {"dir": str(d), "main": str(main), "intro": str(intro), "broll": broll}
    v["footage_min"] = round(duration(main) / 60, 1)
    v["prep_min"] = round((time.time() - t0) / 60, 1)
    return v


def prep(doc):
    for v in doc["videos"]:
        if not v.get("staged") and not v.get("studio_project"):
            log(f"prep: {v['title']} ({v['channel']})")
            try:
                prep_one(v)
            except Exception as e:
                v["error"] = f"copy/convert failed: {e}"
                log(f"  FAILED {e}")
            write_json(DATA / f"{doc['night']}.json", doc)
    return doc


# ---------- building ----------

def studio_up():
    try:
        api("jobs", timeout=10)
        return True
    except Exception:
        return False


def ensure_studio():
    if studio_up():
        return
    log("Studio is not running; starting it")
    pyw = Path(sys.executable).with_name("pythonw.exe")
    env = dict(os.environ)
    if machine() != "Desktop":
        env["STUDIO_WORKER"] = "1"   # the laptop's Studio is a worker: no folder watchers of its own (the desktop's)
    subprocess.Popen([str(pyw if pyw.exists() else sys.executable), "-X", "utf8", str(APP / "main.py")]
                     + (["--serve"] if env.get("STUDIO_WORKER") else []), cwd=str(APP.parent),
                     creationflags=0x00000008, env=env)   # DETACHED_PROCESS
    for _ in range(40):
        time.sleep(3)
        if studio_up():
            return
    raise RuntimeError("Studio did not start")


def busy(project_id=None):
    jobs = api("jobs")["jobs"]
    return [j for j in jobs if j["status"] in ("queued", "running") and (project_id is None or j["project_id"] == project_id)]


def too_late():
    return time.strftime("%H:%M") >= STOP_STARTING_AT and time.strftime("%H:%M") < "18:00"


def build_one(v):
    st = v.get("staged")
    if v.get("studio_project"):   # already a Studio project: just build its draft
        pid = v["project_id"] = v["studio_project"]
        p = api(f"project?id={pid}")
        if not v.get("footage_min") and p.get("source"):
            v["footage_min"] = round(duration(p["source"]) / 60, 1)
        api(f"project/run?id={pid}", {"action": "draft"})
        log(f"  project {pid} draft building")
    else:
        if not v.get("footage_min"):
            v["footage_min"] = round(duration(st["main"]) / 60, 1)
        # no intro self-check fix rounds (user 2026-10-25: the AI re-render loops slow everything down; he judges the intro)
        proj = api("projects", {"title": v["title"], "type": v["type"], "channel": v["channel"],
                                "settings": {"overnight": v["drive"], "intro_check": False, "machine": "here"}})
        pid = v["project_id"] = proj["id"]
        v["project_path"] = proj["path"]
        slot = "intro_vo" if v["type"] == "phone" else "intro"
        api(f"project/slot?id={pid}", {"slot": slot, "path": st["intro"]})
        if st["broll"]:
            api(f"project/slot?id={pid}", {"slot": "broll", "files": st["broll"]}, timeout=600)
        api(f"project/slot?id={pid}", {"slot": "main", "path": st["main"]}, timeout=1800)   # the copy into raw\ starts the draft build
        log(f"  project {pid} created, draft building")
    t0 = time.time()
    v["build_started"] = time.strftime("%H:%M")
    time.sleep(20)
    while busy(pid):
        time.sleep(30)
    v["build_ended"] = time.strftime("%H:%M")
    v["build_min"] = round((time.time() - t0) / 60, 1)
    p = api(f"project?id={pid}")
    b = (p.get("builds") or [{}])[-1]
    v["build_status"] = b.get("status", "unknown")
    v["build_steps"] = [(s.get("label"), round((s.get("secs") or 0) / 60, 1)) for s in b.get("steps", [])]
    log(f"  build {v['build_status']} in {v['build_min']} min")
    if st:
        shutil.rmtree(st["dir"], ignore_errors=True)   # the project has its own copies now


REPAIR_MAX_MIN = 30


def repair(v):
    """A failed overnight build goes to Claude BEFORE its one retry (user 2026-10-26: "if it fails, then Claude should
    automatically fix it" ... "overnight should be okay, since I'm not on my computer"; daytime revisions never get this).
    Claude finds the cause in the build log and fixes it in the shared pipeline, never by switching a check off; the
    runner then rebuilds once (the existing retry). The retry used to rerun the same code into the same failure."""
    pid = v["project_id"]
    try:
        p = api(f"project?id={pid}")
        b = (p.get("builds") or [{}])[-1]
        step = next((s.get("label") for s in b.get("steps", []) if s.get("status") == "failed"), None) or v.get("error") or "unknown"
        logf = Path(p.get("path") or v.get("project_path") or "") / "output" / "studio.log"
        tail = logf.read_text(encoding="utf-8", errors="replace")[-6000:] if logf.is_file() else "(no output/studio.log)"
        msg = (f"OVERNIGHT REPAIR. The overnight draft build of this project failed at step: {step}.\n"
               f"Last part of output/studio.log:\n{tail}\n\n"
               "Find the CAUSE and fix it so this and every other video builds: a missing tool or path on this machine, a "
               "crash in a script, an AI step that got no answer. Fix it in the shared pipeline code/config (keep a .bak copy "
               "of any file you change, and add a one-line comment why). NEVER fix it by switching a check off, lowering a "
               "guard, or editing this video's cuts or raw files. If it was a BUILD STOPPED by the approved-edit guard, find "
               "which step moved the cuts and fix that step. Do NOT start a build yourself: the overnight runner rebuilds once "
               "as soon as you reply. Reply in two lines: CAUSE: ... / FIX: ... (or CAN'T FIX: why).")
        api(f"chat/send?id={pid}", {"text": msg})
        log(f"  repair: Claude is looking at the failed step ({step})")
        t0 = time.time()
        time.sleep(20)
        while time.time() - t0 < REPAIR_MAX_MIN * 60 and not too_late():
            st = api(f"chat?id={pid}")
            if not st.get("busy"):
                break
            time.sleep(30)
        st = api(f"chat?id={pid}")
        reply = next((m.get("text", "") for m in reversed((st.get("transcript") or {}).get("messages") or []) if m.get("role") == "assistant"), "")
        v["repair"] = {"step": step, "min": round((time.time() - t0) / 60, 1), "reply": reply[-600:],
                       "status": "timed out" if st.get("busy") else "answered"}
        log(f"  repair {v['repair']['status']} in {v['repair']['min']} min: {reply[-200:]!r}")
    except Exception as e:  # noqa: a repair that can't run still leaves the plain retry
        v["repair"] = {"status": f"could not start: {e}"}
        log(f"  repair could not start: {e}")


def run(n=5):
    global LOG_FILE
    LOGS.mkdir(parents=True, exist_ok=True)
    LOG_FILE = LOGS / f"{tonight()}.log"
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)   # keep the PC awake while this runs
    doc = plan(n)
    log(f"night {doc['night']}: {[v['title'] for v in doc['videos']]}")
    doc["run_started"] = time.strftime("%Y-%m-%d %H:%M")
    run_t0 = time.time()
    prep(doc)
    ensure_studio()
    state = read_json(STATE, {"done": [], "channel_last": {}})
    for v in doc["videos"]:
        if v.get("project_id") or v.get("error"):
            continue
        ensure_studio()   # a hidden Studio quits ~30 s after its last build, so it may be gone between videos
        # no waiting for other builds: Studio's render queue runs one GPU build at a time anyway. Night 2026-10-24 the
        # user's 3:30 AM revision rebuilds kept video 5 out of the queue ("only four videos are in the queue")
        waited = time.time()
        if too_late():
            v["error"] = "not started: ran out of night (other builds were running)"
            log(v["error"])
            continue
        v["waited_min"] = round((time.time() - waited) / 60, 1)
        log(f"build: {v['title']} ({v['channel']}, {v['type']})")
        try:
            build_one(v)
        except Exception as e:
            v["error"] = f"build failed to start: {e}"
            log(f"  FAILED {e}")
        # one retry (user 2026-10-22: "if a render fails, try it again"). Night 2026-10-21 lost yeezy slides to a Studio
        # that died mid-build (connection refused) and the coupons draft to one failed step. Jobs already retry a failed
        # step once; this covers a dead Studio or a build that still failed, on the project that already exists.
        if v.get("project_id") and (v.get("error") or v.get("build_status") != "done") and not too_late():
            repair(v)
            log(f"  retrying {v['title']} once")
            v["first_try"] = v.pop("error", None) or v.get("build_status")
            v["studio_project"] = v["project_id"]
            try:
                ensure_studio()
                build_one(v)
            except Exception as e:
                v["error"] = f"retry failed: {e}"
                log(f"  retry FAILED {e}")
        state["done"].append(v["drive"])
        state["channel_last"][Path(v["drive"]).parent.name] = time.strftime("%Y-%m-%d %H:%M")
        write_json(STATE, state)
        write_json(DATA / f"{doc['night']}.json", doc)
    doc["run_ended"] = time.strftime("%Y-%m-%d %H:%M")
    doc["run_min"] = round((time.time() - run_t0) / 60, 1)
    write_json(DATA / f"{doc['night']}.json", doc)
    report(doc)
    ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


# ---------- morning report ----------

def draft_of(v):
    p = Path(v.get("project_path", ""))
    if v["type"] == "gaming":
        title = re.sub(r'[<>:"/\\|?*]', "", v["title"]).strip()
        return p / "Edit" / f"{title} draft.mp4"
    if v["type"] == "phone":
        return p / "output" / f"{p.name} - DRAFT.mp4"
    withintro = p / "output" / "preview_intro_540p.mp4"   # tools\review_intro.py (2026-10-21)
    return withintro if withintro.exists() else p / "output" / "preview_540p.mp4"


def report(doc=None):
    doc = doc or read_json(DATA / f"{tonight()}.json", None)
    if not doc:
        print("no plan for tonight")
        return
    REPORTS.mkdir(parents=True, exist_ok=True)
    lines = [f"# Overnight lab — night of {doc['night']}", ""]
    tg = [f"🌙 <b>Overnight lab</b> ({doc['night']})"]
    ok = 0
    # the timing table first: how long each video took to edit, next to how long its footage is
    lines += ["## How long each edit took", "", "| Video | Channel | Footage | Edit (build) | Ran | Result |", "|---|---|---|---|---|---|"]
    for v in doc["videos"]:
        d = draft_of(v) if v.get("project_path") else None
        v["_good"] = good = bool(d and d.exists() and v.get("build_status") == "done")
        status = "draft ready" if good else (v.get("error") or f"build {v.get('build_status', 'not run')}")
        if v.get("first_try"):
            status += f" (2nd try; 1st: {str(v['first_try'])[:80]})"
        if v.get("repair"):
            status += f" — Claude repair ({v['repair'].get('status')}): {(v['repair'].get('reply') or '').strip()[-160:]}"
        ran = f"{v['build_started']}–{v['build_ended']}" if v.get("build_ended") else "-"
        lines.append(f"| {v['title']} | {v['channel']} | {v.get('footage_min', '?')} min | {str(v['build_min']) + ' min' if v.get('build_min') else '-'} | {ran} | {status} |")
    built = [v for v in doc["videos"] if v.get("build_min")]
    if built:
        lines += ["", f"Total edit time {round(sum(v['build_min'] for v in built), 1)} min for {round(sum(v.get('footage_min') or 0 for v in built), 1)} min of footage"
                  + (f"; whole night {doc['run_min']} min ({doc['run_started']} → {doc['run_ended']}, incl. copying and waiting for other builds)." if doc.get("run_min") else ".")]
    lines.append("")
    for v in doc["videos"]:
        d = draft_of(v) if v.get("project_path") else None
        good = v.pop("_good")
        ok += good
        status = "draft ready" if good else (v.get("error") or f"build {v.get('build_status', 'not run')}")
        if v.get("first_try"):
            status += f" (2nd try; 1st: {str(v['first_try'])[:80]})"
        if v.get("repair"):
            status += f" — Claude repair ({v['repair'].get('status')}): {(v['repair'].get('reply') or '').strip()[-160:]}"
        lines += [f"## {v['title']}", f"- Channel: {v['channel']} · type: {v['type']}",
                  f"- Status: **{status}**" + (f" · edit took {v.get('build_min')} min for {v.get('footage_min', '?')} min of footage" if v.get("build_min") else ""),
                  f"- Waited for other builds: {v['waited_min']} min" if v.get("waited_min") else None,
                  f"- Copy off Drive: {v['prep_min']} min" if v.get("prep_min") else None,
                  ("- Steps: " + ", ".join(f"{l} {m} min" for l, m in v["build_steps"])) if v.get("build_steps") else None,
                  f"- Draft: {d}" if good else None, f"- Project: {v.get('project_path', '-')}", f"- Drive source: {v['drive']}"]
        irep = Path(v.get("project_path", "")) / "output" / "intro_report.txt"
        if v["type"] == "review" and irep.exists():
            lines.append("- Intro: " + irep.read_text(encoding="utf-8", errors="replace").splitlines()[0])
        rep = Path(v.get("project_path", "")) / "output" / "report.md"
        if rep.exists():
            lines += ["", "<details><summary>pipeline report</summary>", "", rep.read_text(encoding="utf-8", errors="replace")[:4000], "", "</details>"]
        lines.append("")
        took = f" · {v['build_min']} min edit / {v.get('footage_min', '?')} min footage" if v.get("build_min") else ""
        tg.append(f"{'✅' if good else '⚠️'} {v['title']} ({v['channel']}): {status}{took}")
    lines += ["## Eligible backlog (have an intro VO)", ""] + [f"- {c}: {k}" for c, k in sorted(doc.get("eligible", {}).items())]
    out = REPORTS / f"{doc['night']}.md"
    out.write_text("\n".join(l for l in lines if l is not None), encoding="utf-8")
    if doc.get("run_min"):
        tg.append(f"⏱ Night: {doc['run_min']} min ({doc['run_started'][-5:]} → {doc['run_ended'][-5:]})")
    tg.append(f"{ok}/{len(doc['videos'])} drafts ready — open them in {{STUDIO_NAME}} → Projects.")
    print(out)
    try:
        if ok:
            api("todo/add", {"title": f"Review {ok} overnight draft{'s' if ok > 1 else ''} in {{STUDIO_NAME}}", "due": time.strftime("%Y-%m-%d")})
    except Exception as e:
        log(f"report notify failed: {e}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 5
    if cmd == "plan":
        print(json.dumps(plan(n), indent=1, ensure_ascii=False))
    elif cmd == "prep":   # the laptop's afternoon task: pick tonight's videos and copy them off Drive before 1 AM
        LOGS.mkdir(parents=True, exist_ok=True)
        LOG_FILE = LOGS / f"{tonight()}.log"
        log(f"prep on {machine()}")
        prep(plan(n))
    elif cmd == "add-project":
        print(json.dumps(add_project(sys.argv[2]), indent=1, ensure_ascii=False))
    elif cmd == "add":
        print(json.dumps(add(sys.argv[2]), indent=1, ensure_ascii=False))
        prep(plan())
    elif cmd == "report":
        report()
    else:
        run(n)

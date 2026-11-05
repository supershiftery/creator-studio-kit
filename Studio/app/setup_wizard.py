"""First-run setup wizard (kit): the step-by-step "installer" that opens inside the Studio window the first time it starts.

Welcome -> what's installed (each problem has a plain-English fix button) -> where recordings live -> where projects go ->
music library -> captions default -> channel name (optional) -> apply -> done.

Apply writes setup/answers.json and runs configure.py (fills the kit's {{ }} paths, writes Studio/data/settings.json, makes
the folders), then saves the wizard's own settings (captions_default, setup_done). configure.py rewrites the Studio's own code
files, so the Studio restarts itself after it (the page reloads by itself). Settings -> Setup -> Run setup again re-opens it.
Fixes (FFmpeg, Python packages, Node, Claude Code) run hidden, one at a time; signing in to Claude opens its own window.
"""
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import jobs
import store

KIT = Path(__file__).resolve().parents[2]
SETUP = KIT / "setup"
ANSWERS = SETUP / "answers.json"
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
NEW_CONSOLE = 0x00000010 if sys.platform == "win32" else 0
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
DETACHED = 0x00000008 if sys.platform == "win32" else 0
TOKEN = "{{" + "KIT" + "}}"   # split, so configure.py never fills this file's own check in
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus"}
CAPTIONS = ("all", "bookends", "off")
# import name -> what it's for (setup/requirements.txt has the full list; these are the ones the Studio can't start a build without)
PACKAGES = {"numpy": "numpy", "cv2": "opencv", "PIL": "pillow", "faster_whisper": "faster-whisper", "mediapipe": "mediapipe",
            "webview": "pywebview", "playwright": "playwright"}

FINISH_PROMPT = ("Read MASTER PROMPT.md in this folder and follow everything under its line. The Studio's setup wizard already "
                 "installed everything and saved my folders, captions default and channel name (Studio/data/settings.json, "
                 "setup/answers.json, configure.py has run): don't ask those again. Start with Phase 0, then Phase 2 from "
                 "'Then adapt the kit to me'.")
_fix = {"name": "", "proc": None, "log": None, "ok": None, "msg": ""}
_gpu = {"v": None}
_auth_memo = {"t": 0, "v": None}
_signin = {"proc": None, "state": "idle", "url": "", "msg": "", "out": [], "email": ""}


# ------------------------------------------------------------------------------------------------ helpers
def _home():
    return Path.home()


def refresh_path():
    """Programs installed while the Studio runs only show up in NEW processes: re-read PATH from Windows (no restart needed)."""
    if sys.platform != "win32":
        return
    try:
        import winreg
        parts = []
        for hive, key in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                          (winreg.HKEY_CURRENT_USER, "Environment")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    parts.append(os.path.expandvars(winreg.QueryValueEx(k, "Path")[0]))
            except OSError:
                pass
        extra = [str(_home() / ".local" / "bin"), os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links")]
        seen, out = set(), []
        for p in ";".join(parts + extra + [os.environ.get("PATH", "")]).split(";"):
            if p and p.lower() not in seen:
                seen.add(p.lower())
                out.append(p)
        os.environ["PATH"] = ";".join(out)
    except Exception:
        pass


def _which(cmd):
    return shutil.which(cmd) or (str(_home() / ".local" / "bin" / f"{cmd}.exe") if (_home() / ".local" / "bin" / f"{cmd}.exe").exists() else None)


def _auth():
    """Claude Code's own answer ({"loggedIn", "email", ...}). Asking it beats looking for its files: a leftover file from an
    old sign-in used to count as signed in. An old Claude Code without `auth status` falls back to the files."""
    now = time.time()
    if now - _auth_memo["t"] < 3:
        return _auth_memo["v"]
    v = None
    exe = _which("claude")
    if exe:
        try:
            r = subprocess.run([exe, "auth", "status", "--json"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=20, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
            v = json.loads(r.stdout)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            v = None
    if not isinstance(v, dict) or "loggedIn" not in v:
        v = {"loggedIn": _signed_in_files()}
    _auth_memo.update(t=now, v=v)
    return v


def _signed_in_files():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    if (_home() / ".claude" / ".credentials.json").exists():
        return True
    try:
        return bool(json.loads((_home() / ".claude.json").read_text(encoding="utf-8")).get("oauthAccount"))
    except (OSError, ValueError):
        return False


def _signed_in():
    return bool(_auth().get("loggedIn"))


# ------------------------------------------------------------------------------------------------ Claude sign-in
# 2026-11-04, a tester could not sign in: the button opened Claude's whole first-run screen in a black window (theme, login menu,
# trust question) and left them to find their way. Now the wizard runs `claude auth login` itself with no window: the browser opens,
# they click Authorize, and this notices by itself. A sign-in link + a box for the code are there when the browser doesn't open.
# Signed in is then proved with one tiny real question, so an account with no paid plan says so here and not on the first build.
PLAN_MSG = "You're signed in, but this Claude account can't use Claude Code. It needs a Pro or Max plan: upgrade at claude.ai, or use another account."


def _signin_set(**kw):
    _signin.update(kw)


def _prove_claude(exe):
    """one tiny real question: (works, what to tell them)"""
    try:
        r = subprocess.run([exe, "-p", "Reply with the word OK", "--model", "haiku", "--max-turns", "1", "--no-session-persistence",
                            "--tools", "", "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands", "--output-format", "json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90,
                           creationflags=NO_WINDOW, stdin=subprocess.DEVNULL, cwd=str(KIT))
    except subprocess.TimeoutExpired:
        return True, ""   # slow is not "can't": the first build will tell
    except OSError as e:
        return False, f"Couldn't start Claude: {e}"
    try:
        d = json.loads(r.stdout)
        text, bad = str(d.get("result") or ""), bool(d.get("is_error"))
    except ValueError:
        text, bad = (r.stdout or r.stderr or "").strip(), r.returncode != 0
    if not bad:
        return True, ""
    if re.search(r"subscription|upgrade|plan|credit|billing|access", text, re.I):
        return False, PLAN_MSG
    return False, "Claude answered with a problem: " + text[-200:]


def _signin_watch(p, exe):
    t0 = time.time()
    while time.time() - t0 < 900:
        if p is not _signin.get("proc"):
            return   # cancelled or started again
        _auth_memo["t"] = 0
        if _signed_in():
            break
        if p.poll() is not None:
            time.sleep(1)
            _auth_memo["t"] = 0
            if _signed_in():
                break
            if not _signin["url"]:   # a Claude Code too old for `auth login`: its own first-run screen is the only way
                subprocess.Popen([exe], cwd=str(KIT), creationflags=NEW_CONSOLE)
                return _signin_set(state="window", msg="Sign in in the window that opened. This page turns green by itself.")
            return _signin_set(state="failed", msg=("".join(_signin["out"]).strip().splitlines() or ["Sign-in stopped."])[-1][:200])
        time.sleep(2)
    else:
        try:
            p.kill()
        except OSError:
            pass
        return _signin_set(state="failed", msg="Sign-in timed out. Try again.")
    _signin_set(state="checking", msg="")
    ok, msg = _prove_claude(exe)
    _signin_set(state="ok" if ok else "failed", msg=msg, email=_auth().get("email") or "")


def signin_start(switch=False):
    refresh_path()
    exe = _which("claude")
    if not exe:
        return {"ok": False, "msg": "Install Claude Code first."}
    signin_cancel()
    if switch:
        subprocess.run([exe, "auth", "logout"], capture_output=True, timeout=30, creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
    _auth_memo["t"] = 0
    p = subprocess.Popen([exe, "auth", "login", "--claudeai"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         creationflags=NO_WINDOW, cwd=str(KIT))
    _signin_set(proc=p, state="waiting", url="", msg="", out=[], email="")

    def read():
        buf = b""
        while True:
            c = p.stdout.read(1)
            if not c:
                return
            buf += c
            if c in b"\n> ":
                t = buf.decode("utf-8", "replace")
                if p is _signin.get("proc"):
                    _signin["out"] = (_signin["out"] + [t])[-40:]
                    m = re.search(r"https://\S+", "".join(_signin["out"]))
                    if m and c in b"\n":
                        _signin["url"] = m.group(0)
                    if re.search(r"invalid code", "".join(_signin["out"][-6:]), re.I):
                        _signin["msg"] = "That code didn't work. Copy the whole code from the page and try again."
                buf = b""
    threading.Thread(target=read, daemon=True).start()
    threading.Thread(target=_signin_watch, args=(p, exe), daemon=True).start()
    return {"ok": True}


def signin_cancel():
    p = _signin.get("proc")
    _signin_set(proc=None, state="idle", msg="")
    if p and p.poll() is None:
        try:
            p.kill()
        except OSError:
            pass


def api_signin(q, body):
    if q is not None and not body:   # GET: where it stands
        return {k: _signin.get(k) for k in ("state", "url", "msg", "email")}
    act = body.get("action")
    if act == "start":
        return signin_start()
    if act == "switch":
        return signin_start(switch=True)
    if act == "cancel":
        signin_cancel()
        return {"ok": True}
    if act == "open":
        if _signin.get("url"):
            os.startfile(_signin["url"])  # noqa
        return {"ok": bool(_signin.get("url"))}
    if act == "code":
        p, code = _signin.get("proc"), (body.get("code") or "").strip()
        if not (p and p.poll() is None and code):
            return {"ok": False, "msg": "Press Sign in first."}
        _signin.update(msg="", out=[])
        p.stdin.write((code + "\n").encode())
        p.stdin.flush()
        return {"ok": True}
    return {"ok": False, "msg": "Unknown action."}


def _hyperframes():
    """npx keeps HyperFrames in its cache once SETUP ran `npx --yes hyperframes --version`"""
    if _which("hyperframes"):
        return True
    cache = Path(os.environ.get("LOCALAPPDATA", str(_home() / "AppData" / "Local"))) / "npm-cache" / "_npx"
    return any(cache.glob("*/node_modules/hyperframes/package.json"))


WHISPER = ("small.en", "medium.en")


def _whisper_models():
    """the speech-to-text models SETUP downloads (faster-whisper keeps them in the Hugging Face cache)"""
    hub = Path(os.environ.get("HF_HOME", str(_home() / ".cache" / "huggingface"))) / "hub"
    return [m for m in WHISPER if not any(hub.glob(f"models--Systran--faster-whisper-{m}/snapshots/*/model.bin"))]


def _gpu_name():
    if _gpu["v"] is None:
        try:
            out = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=8, creationflags=NO_WINDOW).stdout
            _gpu["v"] = out.strip().splitlines()[0].split(" (UUID")[0].split(": ", 1)[-1] if out.strip() else ""
        except Exception:
            _gpu["v"] = ""
    return _gpu["v"]


def configured():
    """configure.py has run on this kit (the older Claude-led setup counts too)."""
    return (SETUP / "_pristine").exists() and ANSWERS.exists() and TOKEN not in (KIT / "Studio" / "app" / "server.py").read_text(
        encoding="utf-8", errors="replace")


def _real(p):
    """A path setting that is filled in (not a {{TOKEN}} of an unconfigured kit)."""
    return str(p or "") if p and "{{" not in str(p) else ""


def _count(folder, ext, depth=1):
    n, newest = 0, 0
    try:
        for e in os.scandir(folder):
            if e.is_file() and os.path.splitext(e.name)[1].lower() in ext:
                n += 1
                newest = max(newest, e.stat().st_mtime)
            elif depth and e.is_dir() and not e.name.startswith((".", "_", "$")):
                a, b = _count(e.path, ext, depth - 1)
                n, newest = n + a, max(newest, b)
    except OSError:
        pass
    return n, newest


def _free_gb(p):
    try:
        return round(shutil.disk_usage(Path(p).anchor or p).free / 1e9)
    except OSError:
        return None


def _obs_folders():
    """Where OBS saves recordings (its profile settings), when OBS is installed."""
    out = []
    for ini in (Path(os.environ.get("APPDATA", "")) / "obs-studio" / "basic" / "profiles").glob("*/basic.ini"):
        try:
            for line in ini.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.split("=", 1)[0].strip() in ("FilePath", "RecFilePath") and "=" in line:
                    v = line.split("=", 1)[1].strip()
                    if v and Path(v).is_dir():
                        out.append(str(Path(v)))
        except OSError:
            pass
    return out


def _drives():
    if sys.platform != "win32":
        return [Path("/")]
    import string
    return [Path(f"{d}:\\") for d in string.ascii_uppercase if d not in "AB" and Path(f"{d}:\\").exists()]


# ------------------------------------------------------------------------------------------------ suggestions
def suggest_recordings(current=""):
    h = _home()
    current = str(Path(current)) if current else ""
    cands = [current] + _obs_folders() + [str(h / "Videos"), str(h / "Videos" / "Captures"), str(h / "OneDrive" / "Videos"),
                                         str(h / "Desktop"), str(h / "Downloads")]
    seen, out = set(), []
    for c in cands:
        if not c or c.lower() in seen or not Path(c).is_dir():
            continue
        seen.add(c.lower())
        n, newest = _count(c, VIDEO_EXT)
        if not n and c != current and Path(c) != h / "Videos":   # an empty Desktop / Captures folder is no help
            continue
        out.append({"path": str(Path(c)), "videos": n, "newest": newest, "obs": c in _obs_folders()})
    # the folder with the newest videos first (that's where the recorder saves), then the most videos
    out.sort(key=lambda x: (x["path"] != current, -(x["newest"] > 0), -x["newest"], -x["videos"]))
    return out[:6]


def suggest_projects(current=""):
    if current:
        return current
    best, free = None, 0
    for d in _drives():
        f = _free_gb(d) or 0
        if d.anchor.upper().startswith("C:") or f < 50:
            continue
        if f > free:
            best, free = d, f
    return str(best / "Video Projects") if best and free > (_free_gb(_home()) or 0) else str(_home() / "Videos" / "Creator Studio Projects")


def suggest_music(current=""):
    h = _home()
    current = str(Path(current)) if current else ""
    cands = [current, str(h / "Music")]
    out = []
    for c in cands:
        if c and Path(c).is_dir() and c.lower() not in [o["path"].lower() for o in out]:
            n, _ = _count(c, AUDIO_EXT, 2)
            out.append({"path": str(Path(c)), "tracks": n})
    new = current or str(h / "Music" / "Studio Music")
    return {"new": new, "new_exists": Path(new).is_dir(), "existing": out}


# ------------------------------------------------------------------------------------------------ checks
def checks():
    refresh_path()
    missing = [pip for mod, pip in PACKAGES.items() if importlib.util.find_spec(mod) is None]
    claude = _which("claude")
    gpu = _gpu_name()
    has_winget = bool(_which("winget"))
    missing_models = _whisper_models()
    return [
        {"id": "python", "label": "Python", "ok": True, "detail": f"Python {sys.version.split()[0]} is running the Studio."},
        {"id": "packages", "label": "Studio add-ons (Python packages)", "ok": not missing,
         "detail": "All there." if not missing else f"Missing: {', '.join(missing)}. The cutter, speech-to-text and face finder need them.",
         "fix": "Install them" if missing else ""},
        {"id": "ffmpeg", "label": "FFmpeg (reads and writes video)", "ok": bool(_which("ffmpeg") and _which("ffprobe")),
         "detail": "Installed." if _which("ffmpeg") and _which("ffprobe") else "Not found. Every edit needs it.",
         "fix": "" if _which("ffmpeg") else ("Install FFmpeg" if has_winget else "Get the Windows installer")},
        {"id": "git", "label": "Git (Claude Code needs it on Windows)", "ok": bool(_which("git")),
         "detail": "Installed." if _which("git") else "Not found. Claude Code won't start without it.",
         "fix": "" if _which("git") else ("Install Git" if has_winget else "Get the Windows installer")},
        {"id": "node", "label": "Node.js (makes animated intros)", "ok": bool(_which("node") and _which("npx")),
         "detail": "Installed." if _which("node") else "Not found. Without it your videos get no animated intro.",
         "fix": "" if _which("node") else ("Install Node.js" if has_winget else "Get the Windows installer")},
        {"id": "hyperframes", "label": "HyperFrames (the intro maker)", "ok": bool(_which("node")) and _hyperframes(),
         "detail": ("Installed." if _hyperframes() else "Not downloaded yet. Intros need it.") if _which("node") else "Install Node.js first.",
         "fix": "Download it" if _which("node") and not _hyperframes() else ""},
        {"id": "whisper", "label": "Speech-to-text models (finds every word you say)", "ok": not missing_models,
         "detail": "Downloaded." if not missing_models else f"Missing: {', '.join(missing_models)} (about 2 GB, a one-time download). "
                   "Cutting, captions and the music check need them.",
         "fix": "Download them" if missing_models and "faster-whisper" not in missing else ""},
        {"id": "claude", "label": "Claude Code (the AI editor)", "ok": bool(claude),
         "detail": "Installed." if claude else "Not found. Claude plans intros, checks drafts and makes your notes happen.",
         "fix": "" if claude else "Install Claude Code"},
        {"id": "signin", "label": "Signed in to Claude", "ok": bool(claude) and _signed_in(),
         "detail": (f"Signed in{' as ' + _auth().get('email') if _auth().get('email') else ''}." if _signed_in()
                    else "One click: your browser opens, you press Authorize, done. You need a Claude Pro or Max plan.") if claude
         else "Install Claude Code first.", "fix": "Sign in" if claude and not _signed_in() else ""},
        {"id": "gpu", "label": "NVIDIA graphics card", "ok": True, "info": True,
         "detail": f"{gpu}: fast renders." if gpu else "None found. Videos still render, just slower (Claude switches the settings at the end)."},
    ]


def _fix_running():
    p = _fix["proc"]
    return p is not None and p.poll() is None


def _fix_cmd(name):
    py = sys.executable.replace("pythonw.exe", "python.exe")
    wg = ["winget", "install", "-e", "--accept-package-agreements", "--accept-source-agreements", "--silent", "--id"]
    return {"packages": [py, "-m", "pip", "install", "-r", str(SETUP / "requirements.txt")],
            "ffmpeg": wg + ["Gyan.FFmpeg"],
            "node": wg + ["OpenJS.NodeJS.LTS"],
            "git": wg + ["Git.Git"],
            "hyperframes": ["cmd", "/c", "npx", "--yes", "hyperframes", "--version"],
            "whisper": [py, "-c", "from faster_whisper import WhisperModel; [WhisperModel(m, device='cpu', compute_type='int8') "
                                  f"for m in {WHISPER!r}]; print('whisper ok')"],
            "claude": ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "irm https://claude.ai/install.ps1 | iex"],
            }.get(name)


def _watch(name):
    p = _fix["proc"]
    p.wait()
    refresh_path()
    ok = next((c["ok"] for c in checks() if c["id"] == name), p.returncode == 0)
    msg = ""
    if not ok:
        try:
            msg = (SETUP / "wizard_fix.log").read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1][:240]
        except (OSError, IndexError):
            msg = f"It stopped with code {p.returncode}."
    _fix.update(ok=ok, msg=msg)


# ------------------------------------------------------------------------------------------------ API
def status():
    s = store.settings()
    rec = (_real((s.get("recordings") or [""])[0]))
    proj = _real((s.get("roots") or {}).get("phone"))
    music = _real(s.get("music_root"))
    chans = [c.get("name", "") for c in s.get("channels") or [] if "{{" not in c.get("name", "") and c.get("name") != "My videos"]
    cap = s.get("captions_default") or {}
    return {
        "done": bool(s.get("setup_done")) or configured(),   # a kit set up the older way (Claude + configure.py) counts
        "configured": configured(),
        "after": s.get("setup_after") or {},
        "answers": {"recordings": rec, "projects_root": proj, "music_root": music,
                    "captions": cap.get("where", "off") if cap else "off", "channel": chans[0] if len(chans) == 1 else "",
                    "channels": chans},
        "fix": {"name": _fix["name"], "running": _fix_running(), "ok": _fix["ok"], "msg": _fix["msg"]},
    }


def api_status(q, body):
    return status()


def api_checks(q, body):
    return {"checks": checks(), "fix": status()["fix"]}


def api_suggest(q, body):
    a = status()["answers"]
    free = lambda p: _free_gb(p)
    proj = suggest_projects(a["projects_root"])
    return {"recordings": suggest_recordings(a["recordings"]), "projects_root": proj, "projects_free": free(proj),
            "home_free": free(_home()), "music": suggest_music(a["music_root"])}


def api_fix(q, body):
    name = body.get("name", "")
    if name == "signin":   # no window: the browser opens, api_signin reports back
        return dict(signin_start(), signin=True)
    if name == "claude_finish":   # the Done screen: Claude adapts the rest (skills, no-NVIDIA renders, style) in its own window
        refresh_path()
        exe = _which("claude")
        if not exe:
            return {"ok": False, "msg": "Install Claude Code first (Settings -> Setup -> Check what's installed)."}
        subprocess.Popen([exe, FINISH_PROMPT], cwd=str(KIT), creationflags=NEW_CONSOLE)
        return {"ok": True, "window": True}
    if name in ("ffmpeg", "node", "git") and not _which("winget"):   # no Windows installer (winget): the Store's App Installer brings it
        os.startfile("ms-windows-store://pdp/?productid=9NBLGGH4NNS1")  # noqa
        return {"ok": True, "window": True, "msg": "The Microsoft Store opened on App Installer: click Get or Update, then come back "
                                                   "and click the fix button again."}
    cmd = _fix_cmd(name)
    if not cmd:
        return {"ok": False, "msg": "Unknown fix."}
    if _fix_running():
        return {"ok": False, "msg": f"Still installing {_fix['name']}. One at a time."}
    log = open(SETUP / "wizard_fix.log", "w", encoding="utf-8")
    refresh_path()
    _fix.update(name=name, ok=None, msg="", log=log,
                proc=subprocess.Popen(cmd, cwd=str(KIT), stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW))
    threading.Thread(target=_watch, args=(name,), daemon=True).start()
    return {"ok": True}


def _mkdir(p, what):
    try:
        Path(p).mkdir(parents=True, exist_ok=True)
        return None
    except OSError as e:
        return f"Couldn't make the {what} folder {p}: {e.strerror or e}. Pick another place."


def api_apply(q, body):
    rec = str(body.get("recordings") or "").strip()
    proj = str(body.get("projects_root") or "").strip()
    music = str(body.get("music_root") or "").strip()
    where = body.get("captions") if body.get("captions") in CAPTIONS else "off"
    channel = str(body.get("channel") or "").strip()[:60]
    for p, what in ((rec, "recordings"), (proj, "projects"), (music, "music")):
        if not p:
            return {"ok": False, "msg": f"Pick a {what} folder first."}
        err = _mkdir(p, what)
        if err:
            return {"ok": False, "msg": err}
    if any(j.status in ("queued", "running") for j in jobs.JOBS.values()):
        return {"ok": False, "msg": "A video is building. Let it finish (or stop it on the Queue page), then click Finish again."}

    try:
        a = json.loads(ANSWERS.read_text(encoding="utf-8")) if ANSWERS.exists() else {}
    except ValueError:
        a = {}
    old_proj = a.get("projects_root")
    a.update(recordings=rec, projects_root=proj, music_root=music)
    a.setdefault("studio_name", "Creator Studio")
    if not a.get("gaming_root") or a.get("gaming_root") == old_proj:
        a["gaming_root"] = proj
    types = list(store.TYPES)
    chans = [c for c in a.get("channels") or [] if not c.get("_wizard")]
    if channel:   # the wizard's one channel; channels Claude set up with you stay as they are
        a["channels"] = [{"name": channel, "types": types, "per_week": 2, "_wizard": True}] + [
            c for c in chans if c["name"].lower() != channel.lower()]
    elif not chans:
        a["channels"] = [{"name": "My videos", "types": types, "per_week": 2, "_wizard": True}]
    else:
        a["channels"] = chans
    a.pop("_note", None)
    SETUP.mkdir(parents=True, exist_ok=True)
    ANSWERS.write_text(json.dumps(a, indent=1, ensure_ascii=False), encoding="utf-8")

    py = sys.executable.replace("pythonw.exe", "python.exe")
    r = subprocess.run([py, "-X", "utf8", str(KIT / "configure.py")], cwd=str(KIT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=600, creationflags=NO_WINDOW)
    (SETUP / "wizard_configure.log").write_text(r.stdout + r.stderr, encoding="utf-8")
    if r.returncode:
        return {"ok": False, "msg": "Filling in your folders failed: " + ((r.stderr or r.stdout).strip().splitlines() or ["?"])[-1][:300]
                + " (full log: setup/wizard_configure.log)"}

    store.save_settings({"captions_default": {"on": where != "off", "where": where, "style": "bold"}, "setup_done": True,
                         "setup_after": {"show_done": True, "music_find": bool(body.get("music_find")), "when": time.time()}})
    threading.Timer(1.0, restart).start()   # configure.py rewrote the Studio's own code: start it again so it uses your folders
    return {"ok": True, "restart": True}


def api_after(q, body):
    """the page took the after-restart steps (Done screen, music search): forget them"""
    store.save_settings({"setup_after": {"show_done": False, "music_find": False}})   # (save_settings merges dicts)
    return {"ok": True}


def restart():
    """Start the Studio again the same way it was started (window / --browser / --serve), once this one has let go of the port."""
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else store.settings().get("port", 8765)
    main = Path(__file__).resolve().parent / "main.py"
    args = [sys.executable, "-X", "utf8", str(main)] + [a for a in sys.argv[1:] if a != "--browser"] + (
        ["--serve"] if "--browser" in sys.argv else [])   # browser mode: the page reloads itself, no second tab
    waiter = ("import socket,subprocess,sys,time\n"
              "for _ in range(150):\n"
              "    s=socket.socket()\n"
              f"    if s.connect_ex(('127.0.0.1',{int(port)}))!=0: break\n"
              "    s.close(); time.sleep(0.2)\n"
              f"subprocess.Popen({args!r}, cwd={str(main.parent)!r}, creationflags={NO_WINDOW if '--serve' in args else 0})\n")
    subprocess.Popen([sys.executable, "-c", waiter], cwd=str(main.parent), creationflags=DETACHED | NO_WINDOW,
                     close_fds=True)
    os._exit(0)


ROUTES = {
    ("GET", "setup/wizard"): api_status,
    ("GET", "setup/wizard/checks"): api_checks,
    ("GET", "setup/wizard/suggest"): api_suggest,
    ("POST", "setup/wizard/fix"): api_fix,
    ("GET", "setup/wizard/signin"): api_signin,
    ("POST", "setup/wizard/signin"): api_signin,
    ("POST", "setup/wizard/apply"): api_apply,
    ("POST", "setup/wizard/after"): api_after,
}

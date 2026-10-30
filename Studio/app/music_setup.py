"""Set up your music, from inside the Studio (kit): the "Set up your music" card on Projects + the Music card in Settings.

Find and organise run tools/music_kit.py in its own hidden process (the Whisper vocal check is heavy, and it waits while a
Studio build renders, so it must not be a Studio job itself). Progress, the found list and the report live in
<music library>/_setup/.
"""
import json
import subprocess
import sys
from pathlib import Path

import store

KIT = Path(__file__).resolve().parents[2]
TOOLS = KIT / "tools"
sys.path.insert(0, str(TOOLS))
import music_kit  # noqa: E402

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_proc = {"p": None}


class MusicError(Exception):
    pass


def _running():
    p = _proc["p"]
    return p is not None and p.poll() is None


def _start(*args):
    if _running():
        raise MusicError("Music setup is already running.")
    py = sys.executable.replace("pythonw.exe", "python.exe")
    d = music_kit.setup_dir()
    music_kit.progress(state="finding" if args[0] == "find" else "organising", msg="Starting…", done=0, total=0, current="")
    log = open(d / f"{args[0]}.log", "w", encoding="utf-8")
    _proc["p"] = subprocess.Popen([py, "-X", "utf8", str(TOOLS / "music_kit.py"), *args], cwd=str(TOOLS), stdout=log,
                                  stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
    _proc["auto"] = False
    return {"ok": True}


def api_status(q, body):
    s = music_kit.status()
    s["running"] = _running()
    if s["running"] and _proc.get("auto") and s["progress"].get("state") == "found":   # auto: find done, sorting starts next
        s["progress"].update(state="organising", msg="Starting to sort your music…", done=0, total=s["progress"].get("found", 0))
    if not s["running"] and s["progress"].get("state") in ("finding", "organising") and _proc["p"] is not None:
        s["progress"]["state"] = "error"   # the process ended without saying it was done
        log = music_kit.setup_dir() / ("auto.log" if _proc.get("auto") else "find.log" if s["progress"].get("total") == 0 else "organise.log")
        try:
            s["progress"]["msg"] = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1][:300]
        except (OSError, IndexError):
            pass
    return s


def api_find(q, body):
    args = ["find"]
    for p in body.get("places") or []:
        args += ["--place", p]
    return _start(*args)


def start_auto():
    """Find the music on this PC and sort ALL of it, no list to tick (user 2026-10-29: "it can just automatically grab their
    music"). Instrumentals only: organise's vocal / producer-tag check still leaves out anything with words."""
    if _running():
        raise MusicError("Music setup is already running.")
    py = sys.executable.replace("pythonw.exe", "python.exe")
    mk = str(TOOLS / "music_kit.py")
    music_kit.progress(state="finding", msg="Starting…", done=0, total=0, current="")
    chain = ("import subprocess, sys\n"
             f"a = [{py!r}, '-X', 'utf8', {mk!r}]\n"
             f"r = subprocess.call(a + ['find'], creationflags={NO_WINDOW})\n"
             f"sys.exit(r or subprocess.call(a + ['organise', '--all'], creationflags={NO_WINDOW}))\n")
    log = open(music_kit.setup_dir() / "auto.log", "w", encoding="utf-8")
    _proc["p"] = subprocess.Popen([py, "-c", chain], cwd=str(TOOLS), stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
    _proc["auto"] = True
    return {"ok": True}


def api_auto(q, body):
    return start_auto()


def api_remove(q, body):
    """right-click a track -> Remove from library: never picked again; the setup's link / copy goes, your original stays"""
    if not body.get("path"):
        raise MusicError("No track.")
    return music_kit.remove(body["path"])


def api_mood(q, body):
    """right-click a track -> Mood -> <mood>: moved to that mood folder and kept there"""
    try:
        return music_kit.set_mood(body.get("path", ""), body.get("mood", ""))
    except (ValueError, OSError) as e:
        raise MusicError(f"Couldn't change its mood: {e}")


def api_restore(q, body):
    r = music_kit.restore(body.get("name", ""))
    if r.get("reindex") and not _running():   # a link came back: music_lib analyses it + its vocal check (only that track)
        py = sys.executable.replace("pythonw.exe", "python.exe")
        subprocess.Popen([py, "-X", "utf8", "-c", "import music_lib; music_lib.build_index(scan=True)"], cwd=str(TOOLS),
                         creationflags=NO_WINDOW)
    return r


def api_found(q, body):
    f = music_kit.setup_dir() / "found.json"
    if not f.exists():
        return {"folders": [], "files": 0}
    found = json.loads(f.read_text(encoding="utf-8"))
    return {"folders": music_kit.by_folder(found), "files": len(found.get("files", [])), "minutes": found.get("minutes", 0),
            "skipped": found.get("skipped", {}), "places": found.get("places", []), "when": found.get("when")}


def api_organise(q, body):
    paths = body.get("paths") or []
    if not paths:
        raise MusicError("Pick at least one track.")
    sel = music_kit.setup_dir() / "selection.json"
    sel.write_text(json.dumps(paths, ensure_ascii=False), encoding="utf-8")
    return _start("organise", "--sel", str(sel), *(["--copy"] if body.get("mode") == "copy" else []))


def api_report(q, body):
    p = music_kit.setup_dir() / "report.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def api_settings(q, body):
    patch = {}
    if "music_root" in body and str(body["music_root"]).strip():
        patch["music_root"] = str(body["music_root"]).strip()
    if "music_extra_roots" in body:
        patch["music_extra_roots"] = [str(x).strip() for x in body["music_extra_roots"] or [] if str(x).strip()]
    if "dismissed" in body:
        patch["music_setup_dismissed"] = bool(body["dismissed"])
    store.save_settings(patch)
    return api_status(q, body)


ROUTES = {
    ("GET", "music/setup"): api_status,
    ("POST", "music/setup/find"): api_find,
    ("GET", "music/setup/found"): api_found,
    ("POST", "music/setup/organise"): api_organise,
    ("GET", "music/setup/report"): api_report,
    ("POST", "music/setup/settings"): api_settings,
    ("POST", "music/setup/auto"): api_auto,
    ("POST", "music/library/remove"): api_remove,
    ("POST", "music/library/mood"): api_mood,
    ("POST", "music/library/restore"): api_restore,
}

"""Kit updates from inside the Studio: "Update available" + one-click update.

The newest kit lives in a GitHub repo (KIT_VERSION.json "update_repo"). setup/update_key.json (only in the zip the kit's owner
sends, never in the repo) holds a read-only key for it, so nobody needs a GitHub account. Updating starts update.py in its own
window and closes the Studio: update.py downloads the new version, updates this kit (keeping your setup) and reopens the Studio.
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import jobs

KIT = Path(__file__).resolve().parents[2]
_cache = {"t": 0, "res": None}


def _read(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return {}


def source():
    """(repo "owner/name", read-only key or "") or (None, None) when this kit has no update address."""
    ver = _read(KIT / "KIT_VERSION.json")
    key = _read(KIT / "setup" / "update_key.json")
    repo = key.get("repo") or ver.get("update_repo")
    return (repo, key.get("token", "")) if repo else (None, None)


def fetch(path, repo, token, timeout=20):
    """One file (or the whole repo as a zip with path=None) from the repo's main branch."""
    base = os.environ.get("KIT_UPDATE_API", "https://api.github.com")   # override only for testing the updater
    url = f"{base}/repos/{repo}/contents/{path}?ref=main" if path else f"{base}/repos/{repo}/zipball/main"
    h = {"Accept": "application/vnd.github.raw", "User-Agent": "creator-studio-kit", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = "Bearer " + token
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout)


def check(force=False):
    if not force and _cache["res"] and time.time() - _cache["t"] < 6 * 3600:
        return _cache["res"]
    cur = _read(KIT / "KIT_VERSION.json")
    res = {"current": cur.get("version", 1), "released": cur.get("released", ""), "available": False}
    repo, token = source()
    if not repo:
        res["error"] = "This kit has no update address. Ask whoever sent it for the newest zip."
        return res
    try:
        latest = json.loads(fetch("KIT_VERSION.json", repo, token).read().decode("utf-8"))
    except Exception as e:
        res["error"] = "Couldn't reach the update server" + (" (the update key was turned off)" if "401" in str(e) or "404" in str(e) else "") + "."
        return res
    res.update(latest=latest.get("version", 1), latest_released=latest.get("released", ""),
               changes=latest.get("changes", []), available=latest.get("version", 1) > res["current"])
    _cache.update(t=time.time(), res=res)
    return res


def api_check(q, body):
    return check(force=q.get("force") == "1")


def api_apply(q, body):
    busy = [j for j in jobs.JOBS.values() if j.status in ("queued", "running")]
    if busy:
        return {"ok": False, "error": f"{len(busy)} build(s) still running. Let them finish (or stop them), then update."}
    flags = 0x00000010 if sys.platform == "win32" else 0   # CREATE_NEW_CONSOLE: the update shows its own window
    subprocess.Popen([sys.executable.replace("pythonw.exe", "python.exe"), "-X", "utf8", str(KIT / "update.py"), "--from-app",
                      "--restart"], cwd=str(KIT), creationflags=flags)
    threading.Timer(1.5, lambda: os._exit(0)).start()   # close the Studio so its files can be replaced
    return {"ok": True}

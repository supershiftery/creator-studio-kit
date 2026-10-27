"""Start a Studio build from Task Scheduler (e.g. a project to draft overnight before the overnight lab runs).
python build_at.py <project id> [draft|final]
Starts Studio if it isn't running, then POSTs project/run. The overnight lab waits for builds already running."""
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:%d/api/" % int(os.environ.get("STUDIO_PORT", "8765"))
pid = sys.argv[1]
action = sys.argv[2] if len(sys.argv) > 2 else "draft"
LOG = APP.parent / "data" / "joblogs" / f"build_at-{pid}.log"


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n")


def up():
    try:
        urllib.request.urlopen(API + "jobs", timeout=5)
        return True
    except Exception:
        return False


if not up():
    log("Studio is not running; starting it")
    pyw = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen([str(pyw if pyw.exists() else sys.executable), "-X", "utf8", str(APP / "main.py")], cwd=str(APP.parent),
                     creationflags=0x00000008)   # DETACHED_PROCESS
    for _ in range(40):
        time.sleep(3)
        if up():
            break
    else:
        log("Studio did not start")
        sys.exit(1)
req = urllib.request.Request(API + f"project/run?id={pid}", data=json.dumps({"action": action}).encode(),
                             headers={"Content-Type": "application/json"})
job = json.load(urllib.request.urlopen(req, timeout=60))["job"]
log(f"started {job['title']} ({job['id']}): {job['status']}")

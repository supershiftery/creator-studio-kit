"""Drop-folder automation. Usage: pythonw watcher.py "{{PROJECTS_ROOT}}"

- A video dropped in the top of the folder gets its own project folder (<folder>\\<video name>\\raw\\camera.mp4),
  is edited straight away (pacing cuts off: it's already cut in Gling), and a notification shows the B-roll shot list.
- Clips dropped in a project's raw\\broll folder (named by slot: 3.mov, 5.mov...) trigger a re-render with the B-roll.
- Waits for files to stop growing before touching them. One render at a time. Log: <folder>\\_watcher\\watcher.log
"""
import json, os, re, shutil, subprocess, sys, time, traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import no_console_flash  # noqa: E402,F401  # hides every console window the jobs below start (pythonw: no console of its own)

HERE = Path(__file__).resolve().parent
PY = Path(sys.executable).with_name("python.exe")  # console python for the edit (pythonw has no stdout)
VIDEO = {".mp4", ".mov", ".mkv", ".m4v"}
EDITLIST = {".xml", ".fcpxml"}  # Gling edit lists: point at the original file (all audio tracks)
AUDIO = {".wav", ".mp3", ".m4a"}
PHONE_DIR = "Phone Videos"  # phone/app tutorial lane: <inbox>/Phone Videos/<name>.mp4 [+ "<name> intro.wav"]
PHONE_PIPELINE = Path(r"{{KIT}}/tools/phone_edit/pipeline.py")
POLL, SETTLE = 10, 30  # seconds between scans; seconds a file must stay unchanged before use
FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DRIVE_ROOT = Path(r"{{DRIVE_FINISHED}}")  # Google Drive for Desktop mount: <Channel>\<Video title>\ inside


class Watcher:
    def __init__(self, inbox: Path):
        self.inbox = inbox
        self.home = inbox / "_watcher"
        self.home.mkdir(exist_ok=True)
        self.log_path = self.home / "watcher.log"
        self.state_path = self.home / "state.json"
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {"broll": {}}
        (inbox / PHONE_DIR).mkdir(exist_ok=True)
        self.seen = {}  # path -> (size, mtime, first time unchanged)

    # ------------------------------------------------------------ utils
    def log(self, msg):
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def save(self):
        self.state_path.write_text(json.dumps(self.state, indent=2))

    def settled(self, p: Path) -> bool:
        """True once the file (or folder signature) has not changed for SETTLE seconds."""
        try:
            st = p.stat()
        except OSError:
            return False
        sig = (st.st_size, st.st_mtime)
        old = self.seen.get(str(p))
        now = time.time()
        if not old or old[:2] != sig:
            self.seen[str(p)] = (*sig, now)
            return False
        if now - old[2] < SETTLE:
            return False
        try:  # still being written by another program?
            with open(p, "ab"):
                pass
        except OSError:
            return False
        return True

    def notify(self, title, text, open_path=None):
        launch = f' activationType="protocol" launch="{Path(open_path).as_uri()}"' if open_path else ""
        xml = (f'<toast{launch}><visual><binding template="ToastGeneric"><text>{_x(title)}</text>'
               f'<text>{_x(text)}</text></binding></visual></toast>')
        ps = ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
              "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null;"
              "$x = New-Object Windows.Data.Xml.Dom.XmlDocument; $x.LoadXml($env:TOAST_XML);"
              "$t = [Windows.UI.Notifications.ToastNotification]::new($x);"
              "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
              "'{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe').Show($t)")
        try:
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], env={**os.environ, "TOAST_XML": xml},
                           creationflags=FLAGS, timeout=30, capture_output=True)
        except Exception as e:  # a missed notification must never stop the watcher
            self.log(f"notification failed: {e}")

    def upload_to_drive(self, project: Path):
        """Copy output/final.mp4 into its own video folder under the channel in Google Drive (Drive for Desktop
        syncs it): <Channel>\\<project>\\<project>.mp4."""
        final = project / "output" / "final.mp4"
        if not final.exists():
            self.log(f"upload skipped, no final.mp4 in {project.name}")
            return
        channel = detect_channel(project)
        if not channel:
            channel = "_Unknown Channel"
            self.log(f"channel name not found in first 30s of {project.name}; using {channel}")
        dest_dir = DRIVE_ROOT / channel / project.name
        dest = dest_dir / f"{project.name}.mp4"
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            self.notify("Uploading", f"{project.name}: copying to Drive ({channel})...")
            shutil.copy2(final, dest)  # Drive for Desktop picks it up and syncs
            self.log(f"uploaded {project.name} -> {dest}")
            self.notify(f"{project.name} is on Google Drive", f"{channel}\\{project.name}\\{dest.name} — Drive is syncing it now.")
        except Exception as e:
            self.log(f"upload failed {project.name}: {e}")
            self.notify("Drive upload failed", f"{project.name}: {e}. Video is at {final}")

    def run_edit(self, project: Path, *extra):
        r = subprocess.run([str(PY), str(HERE / "edit_review.py"), str(project), *extra], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", creationflags=FLAGS)
        tail = "\n".join(l for l in (r.stdout + r.stderr).splitlines() if not re.search(r"W0000|I0000|INFO:|WARNING: Logging", l))[-1500:]
        self.log(f"edit_review {' '.join(extra) or '(render)'} -> exit {r.returncode}\n{tail}")
        if r.returncode != 0:
            raise RuntimeError(tail.strip().splitlines()[-1] if tail.strip() else "edit failed")
        return r.stdout

    # ------------------------------------------------------------ new videos
    def new_xml_project(self, xml: Path):
        """A Gling edit list dropped in the inbox: original media comes from the XML itself."""
        sys.path.insert(0, str(HERE)) if str(HERE) not in sys.path else None
        import xml_cuts
        try:
            media, kept = xml_cuts.parse(xml)
        except Exception as e:
            self.log(f"bad XML {xml.name}: {e}")
            self.notify("XML not usable", f"{xml.name}: {e}", self.log_path)
            return
        if not media.exists():
            self.log(f"{xml.name}: original not found: {media}")
            self.notify("Original video not found", f"{xml.name} points to {media} — not on disk.", self.log_path)
            return
        w, h = _probe(media)
        name = re.sub(r'[<>:\"/\\\\|?*]', "_", xml.stem).strip() or "video"
        project = self.inbox / name
        n = 2
        while project.exists():
            project = self.inbox / f"{name} ({n})"
            n += 1
        (project / "raw" / "broll").mkdir(parents=True)
        (project / "output").mkdir()
        shutil.move(str(xml), project / "raw" / "edit.xml")
        (project / "raw" / "config.json").write_text(json.dumps({"pacing": {"enabled": False}}, indent=2) + "\n")
        (project / "raw" / "source.txt").write_text(f"{xml.name}\\n{media} ({w}x{h})\\n{len(kept)} kept ranges from the XML\\nadded {time.strftime('%Y-%m-%d %H:%M')}\\n")
        self.log(f"new XML project {project.name}: {xml.name} -> {media} ({w}x{h}, {len(kept)} ranges)")
        self.notify("Editing started", f"{project.name}: editing from the XML cut list (original file, both mics).")
        self.run_edit(project, "--broll-plan")
        self.run_edit(project)
        slots = json.loads((project / "work" / "broll_plan.json").read_text())
        self.state["broll"][str(project)] = _broll_sig(project)
        self.save()
        req = project / "output" / "broll_requests.md"
        self.notify(f"{project.name} is edited",
                    f"Uploading to Drive now. {len(slots)} B-roll moments if you want them — drop clips in raw\\\\broll named by slot (1.mov, 2.mov...) anytime and I'll re-render and replace it. Shot list below.",
                    req if req.exists() else project / "output")
        self.upload_to_drive(project)
        self.state.setdefault("uploaded", {})[str(project)] = True
        self.save()

    def new_project(self, video: Path):
        w, h = _probe(video)
        name = re.sub(r'[<>:"/\\|?*]', "_", video.stem).strip() or "video"
        project = self.inbox / name
        n = 2
        while project.exists():
            project = self.inbox / f"{name} ({n})"
            n += 1
        (project / "raw" / "broll").mkdir(parents=True)
        (project / "output").mkdir()
        shutil.move(str(video), project / "raw" / "camera.mp4")  # same drive: instant rename
        (project / "raw" / "config.json").write_text(json.dumps({"pacing": {"enabled": False}}, indent=2) + "\n")
        (project / "raw" / "source.txt").write_text(f"{video.name}\n{w}x{h}\nadded {time.strftime('%Y-%m-%d %H:%M')}\n")
        self.log(f"new project {project.name} from {video.name} ({w}x{h})")
        if not w or w / max(h, 1) < 3:
            msg = f"{video.name} is {w}x{h}, not the side-by-side two-camera layout (e.g. 3840x1080). Not edited."
            (project / "output" / "report.md").write_text(f"# Edit report\n\n## Check these (1)\n\n- {msg}\n")
            self.notify("Video not edited", msg, project / "output" / "report.md")
            return
        self.notify("Editing started", f"{project.name}: editing now (about a minute or two).")
        self.run_edit(project, "--broll-plan")
        self.run_edit(project)
        slots = json.loads((project / "work" / "broll_plan.json").read_text())
        self.state["broll"][str(project)] = _broll_sig(project)
        self.save()
        req = project / "output" / "broll_requests.md"
        self.notify(f"{project.name} is edited",
                    f"Uploading to Drive now. {len(slots)} B-roll moments if you want them — drop clips in raw\\broll named by slot (1.mov, 2.mov...) anytime and I'll re-render and replace it. Shot list below.",
                    req if req.exists() else project / "output")
        self.upload_to_drive(project)
        self.state.setdefault("uploaded", {})[str(project)] = True
        self.save()

    # ------------------------------------------------------------ b-roll drops
    def check_broll(self, project: Path):
        sig = _broll_sig(project)
        if sig == self.state["broll"].get(str(project)):
            return
        folder = project / "raw" / "broll"
        files = [p for p in folder.iterdir() if p.is_file()] + [project / "raw" / "broll.json"]
        if not all(self.settled(p) for p in files if p.exists()):
            return  # still copying
        self.log(f"b-roll changed in {project.name}: {[n for n, *_ in sig]}")
        self.notify("Adding B-roll", f"{project.name}: re-rendering with your clips.")
        self.run_edit(project)
        self.state["broll"][str(project)] = sig
        self.save()
        report = (project / "output" / "report.md").read_text(encoding="utf-8")
        m = re.search(r"B-roll: (\d+) of (\d+)", report)
        checks = re.search(r"## Check these \((\d+)\)", report)
        self.notify(f"{project.name}: B-roll added",
                    f"{m.group(1)} of {m.group(2)} B-roll slots filled. Replacing the Drive copy with the new render. {checks.group(1) if checks else 0} items to check. Click to watch.",
                    project / "output" / "final.mp4")
        self.upload_to_drive(project)
        self.state.setdefault("uploaded", {})[str(project)] = True
        self.save()

    # ------------------------------------------------------------ skip b-roll
    def check_skip(self, project: Path):
        """A raw/skip_broll file means: finish without B-roll, upload as-is."""
        marker = project / "raw" / "skip_broll"
        if not marker.exists() or self.state.get("uploaded", {}).get(str(project)):
            return
        self.log(f"b-roll skipped for {project.name}")
        self.state.setdefault("uploaded", {})[str(project)] = True  # before upload: no double-send on failure
        self.save()
        self.upload_to_drive(project)

    # ------------------------------------------------------------ phone videos lane
    def run_phone(self, project: Path):
        has_intro = any(p.name.startswith("intro.") for p in (project / "raw").iterdir())
        self.notify("Phone video: editing started",
                    f"{project.name}: trim, blur, layout, graphics, music{', intro' if has_intro else ''}. About 30-60 min.")
        out = project / "output"
        out.mkdir(exist_ok=True)
        with open(out / "pipeline_stdout.log", "a", encoding="utf-8") as f:
            r = subprocess.run([str(PY), str(PHONE_PIPELINE), str(project)], stdout=f, stderr=subprocess.STDOUT, creationflags=FLAGS)
        if r.returncode:
            raise RuntimeError(f"phone pipeline failed (code {r.returncode}), see output/pipeline_stdout.log")
        draft = next(out.glob("* - DRAFT.mp4"), None)
        rep = (out / "report.md").read_text(encoding="utf-8") if (out / "report.md").exists() else ""
        self.notify(f"{project.name}: draft ready", rep[:300] or "Draft rendered.", draft or out)

    def _phone_try(self, project: Path):
        try:
            self.run_phone(project)
        except Exception as e:
            self.log(f"FAILED phone {project.name}: {e}\n{traceback.format_exc()}")
            self.notify("Phone video edit failed", f"{project.name}: {e}", self.log_path)

    def scan_phone(self):
        lane = self.inbox / PHONE_DIR
        files = [p for p in sorted(lane.iterdir()) if p.is_file() and not p.name.startswith((".", "~"))]
        videos = [p for p in files if p.suffix.lower() in VIDEO]
        audios = [p for p in files if p.suffix.lower() in AUDIO]
        for v in videos:
            if not self.settled(v):
                continue
            intro = next((a for a in audios if a.stem.lower().startswith(v.stem.lower()) and "intro" in a.stem.lower()), None)
            if intro is None and len(videos) == 1 and len(audios) == 1:
                intro = audios[0]
            if intro is not None and not self.settled(intro):
                continue  # wait for the intro to finish copying too
            name = re.sub(r'[<>:"/\\|?*]', "_", v.stem).strip() or "video"
            project, n = self.inbox / name, 2
            while project.exists():
                project, n = self.inbox / f"{name} ({n})", n + 1
            (project / "raw").mkdir(parents=True)
            shutil.move(str(v), project / "raw" / "source.mp4")
            if intro is not None:
                shutil.move(str(intro), project / "raw" / f"intro{intro.suffix.lower()}")
                audios.remove(intro)
            self.state.setdefault("phone", {})[str(project)] = time.strftime("%Y-%m-%d %H:%M")
            self.save()
            self.log(f"phone project {project.name} (intro: {intro is not None})")
            self._phone_try(project)
        for a in audios:  # an intro dropped later for a video that is already a project
            if "intro" not in a.stem.lower() or not self.settled(a):
                continue
            base = re.sub(r"(?i)\s*intro\s*$", "", a.stem).strip()
            project = self.inbox / base
            if (project / "raw" / "source.mp4").exists():
                for old in (project / "raw").glob("intro.*"):
                    old.unlink()
                shutil.move(str(a), project / "raw" / f"intro{a.suffix.lower()}")
                self.log(f"intro added to {project.name}")
                self._phone_try(project)

    # ------------------------------------------------------------ loop
    def scan(self):
        try:
            self.scan_phone()
        except Exception:
            self.log("phone lane error\n" + traceback.format_exc())
        for p in sorted(self.inbox.iterdir()):
            if p.is_file() and p.suffix.lower() in EDITLIST and not p.name.startswith((".", "~")) and self.settled(p):
                try:
                    self.new_xml_project(p)
                except Exception as e:
                    self.log(f"FAILED {p.name}: {e}\n{traceback.format_exc()}")
                    self.notify("Edit failed", f"{p.stem}: {e}. See _watcher\\watcher.log", self.log_path)
        for p in sorted(self.inbox.iterdir()):
            if p.is_file() and p.suffix.lower() in VIDEO and not p.name.startswith((".", "~")) and self.settled(p):
                try:
                    self.new_project(p)
                except Exception as e:
                    self.log(f"FAILED {p.name}: {e}\n{traceback.format_exc()}")
                    self.notify("Edit failed", f"{p.stem}: {e}. See _watcher\\watcher.log", self.log_path)
        for project in sorted(self.inbox.iterdir()):
            if project.is_dir() and str(project) in self.state["broll"] and (project / "raw" / "broll").is_dir():
                try:
                    self.check_skip(project)
                    self.check_broll(project)
                except Exception as e:
                    self.state["broll"][str(project)] = _broll_sig(project)  # don't retry a broken clip forever
                    self.save()
                    self.log(f"FAILED b-roll {project.name}: {e}\n{traceback.format_exc()}")
                    self.notify("B-roll render failed", f"{project.name}: {e}. See _watcher\\watcher.log", self.log_path)

    def run(self):
        self.log(f"watching {self.inbox}")
        while True:
            try:
                self.scan()
            except Exception:
                self.log("scan error\n" + traceback.format_exc())
            time.sleep(POLL)


CHANNEL_ALIASES = {  # Whisper manglings -> real channel folder name (normalized: lowercase, no spaces). Setup fills this.
}


def detect_channel(project: Path):
    """Channel name from the spoken intro. He opens 'hey guys <ChannelName> here' — anchor on
    'here'. The window starts a little before the first kept cut (XML projects: the transcript
    covers the whole original incl. pre-roll and false takes, so the LAST intro take wins).
    Aliases are checked before filler truncation; 'hey guys' repeats are re-anchored."""
    import difflib
    t = project / "work" / "transcript.json"
    if not t.exists():
        return None
    try:
        words = json.loads(t.read_text(encoding="utf-8"))
    except Exception:
        return None
    t0 = 0.0
    cuts = project / "work" / "cuts.json"
    if cuts.exists():
        try:
            kept = json.loads(cuts.read_text(encoding="utf-8"))["kept"]
            if kept and kept[0][0] > 1:
                t0 = max(0.0, kept[0][0] - 15)
        except Exception:
            pass
    text = " ".join(str(w.get("w", "")) for w in words if t0 <= w.get("s", -1) < t0 + 45).lower()
    text = re.sub(r"[^a-z0-9\s'\-&]", " ", text)
    text = re.sub(r"\s+", " ", text)
    candidates = []
    for pat in (r"hey guys\s+([a-z0-9][a-z0-9'\-& ]{1,30}?)\s+here\b",
                r"(?:it s|its|this is)\s+([a-z0-9][a-z0-9'\-& ]{1,40})",
                r"welcome(?: back)? to\s+([a-z0-9][a-z0-9'\-& ]{1,40})"):
        for m in re.finditer(pat, text):
            cand = m.group(1)
            if "hey guys" in cand:  # doubled intro take: keep the last anchor
                cand = cand.split("hey guys")[-1]
            norm = re.sub(r"\s+", "", cand.strip("-&' ").lower())
            if norm in CHANNEL_ALIASES:  # exact alias before any truncation
                return CHANNEL_ALIASES[norm]
            cand = re.split(r"\b(?:and|today|we re|we|welcome|back|guys|so|another|got|the|a|an)\b", cand)[0]
            cand = " ".join(cand.split()[:4]).strip("-&' ")
            if len(cand) >= 3 and cand.lower() != "hey":
                candidates.append(cand)
    if not candidates:
        return None
    name = candidates[-1]  # later take = the real one
    norm = re.sub(r"\s+", "", name.lower())
    if norm in CHANNEL_ALIASES:
        return CHANNEL_ALIASES[norm]
    if DRIVE_ROOT.exists():  # reuse an existing channel folder if it's a close match
        for d in DRIVE_ROOT.iterdir():
            if d.is_dir() and not d.name.startswith(("_", ".")):
                if difflib.SequenceMatcher(None, norm, re.sub(r"\s+", "", d.name.lower())).ratio() >= 0.75:
                    return d.name
    return name.title()


def _x(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _probe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True, creationflags=FLAGS)
    try:
        w, h = r.stdout.strip().split(",")[:2]
        return int(w), int(h)
    except ValueError:
        return 0, 0


def _broll_sig(project: Path):
    items = []
    for p in sorted((project / "raw" / "broll").glob("*")) + [project / "raw" / "broll.json"]:
        if p.is_file():
            st = p.stat()
            items.append([p.name, st.st_size, int(st.st_mtime)])
    return items


def _single_instance(home: Path):
    lock = home / "watcher.pid"
    if lock.exists():
        try:
            pid = int(lock.read_text())
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, creationflags=FLAGS).stdout
            if str(pid) in out and "python" in out.lower():
                sys.exit(0)  # already running
        except ValueError:
            pass
    lock.write_text(str(os.getpid()))


if __name__ == "__main__":
    inbox = Path(sys.argv[1] if len(sys.argv) > 1 else r"{{PROJECTS_ROOT}}")
    w = Watcher(inbox)
    _single_instance(w.home)
    w.run()

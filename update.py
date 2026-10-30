"""Update an installed Creator Studio Kit to this version, keeping your setup.

    In the Studio: Settings -> Updates -> Update now (or double-click UPDATE.cmd in your kit): downloads the newest version.
    From a new zip: unzip it somewhere else and double-click UPDATE.cmd in THAT folder (or: python update.py "D:\\your\\kit").

It finds your installed kit, backs it up, copies in the new files and fills them in with your saved answers again.
Kept as they are: your setup answers, Studio settings + projects list, promo codes, privacy terms, everything in my_style
(your own video types, the rules your notes taught them, the AI director's taught examples), the model choice, and anything
you added yourself. Files you (or Claude) changed by hand are backed up,
replaced by the new version and listed in setup/LOCAL CHANGES.md: paste UPDATE PROMPT.md into Claude Code afterwards and
Claude puts those changes back on top of the new version.
"""
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from pathlib import Path

NEW = Path(__file__).resolve().parent
MARKER = Path.home() / ".creator-studio-kit.json"
# never copied over, never deleted: your data
PROTECT_PREFIX = ("Studio/data/", "setup/_pristine/", "setup/answers.json", "setup/LOCAL CHANGES.md", "setup/update_key.json",
                  "_update_backups/", "_update_source/",
                  "tools/_state/", "tools/privacy_templates/", "memory/", "watcher/",
                  "my_style/")   # everything you taught: your video types, their learned rules, taught examples
PROTECT = {"tools/phone_edit/codes.json", "tools/privacy_terms.json", "tools/intro_library/kit/fonts/SegoeEmoji.ttf"}
KEEP_THEIRS = {"tools/brain.json"}   # your model choice wins over the new default


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def protected(rel):
    return rel in PROTECT or rel.startswith(PROTECT_PREFIX) or rel.startswith("tools/teach/examples/")


def is_kit(p):
    p = Path(p)
    return (p / "configure.py").exists() and (p / "Studio" / "app" / "server.py").exists()


def find_installed():
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        return Path(sys.argv[1].strip('"'))
    if MARKER.exists():
        try:
            p = Path(json.loads(MARKER.read_text(encoding="utf-8"))["kit"])
            if is_kit(p) and p.resolve() != NEW:
                return p
        except Exception:
            pass
    found = []
    roots = [Path.home(), Path.home() / "Documents", Path.home() / "Desktop"] + \
            [Path(f"{d}:\\") for d in "CDEFGHIJ" if Path(f"{d}:\\").exists()]
    for r in roots:
        try:
            for c in r.iterdir():
                if c.is_dir() and c.resolve() != NEW and is_kit(c) and (c / "setup" / "answers.json").exists():
                    found.append(c)
        except OSError:
            pass
    found = list(dict.fromkeys(found))
    if len(found) == 1:
        return found[0]
    if found:
        print("Found more than one installed kit:")
        for i, f in enumerate(found, 1):
            print(f"  {i}. {f}")
        ans = input("Which one do you want to update? Type its number: ").strip()
        return found[int(ans) - 1]
    ans = input("Where is your installed kit? Paste its folder path (the one with configure.py in it): ").strip().strip('"')
    return Path(ans)


def studio_running(kit):
    port = 8765
    try:
        port = int(json.loads((kit / "Studio" / "data" / "settings.json").read_text(encoding="utf-8")).get("port") or port)
    except Exception:
        pass
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def load_configure(folder):
    import importlib.util
    spec = importlib.util.spec_from_file_location("kit_configure", folder / "configure.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def shipped_hashes(old, cfg_old):
    """What every file of the OLD version looked like right after setup, to tell your own edits apart."""
    man = old / "manifest.json"
    if man.exists():
        files = json.loads(man.read_text(encoding="utf-8"))["files"]
    else:   # version 1 had no manifest: this update carries a copy of it
        files = json.loads((NEW / "setup" / "manifests" / "v1.json").read_text(encoding="utf-8"))["files"]
    filled = {}
    ans = old / "setup" / "answers.json"
    pristine = old / "setup" / "_pristine"
    if ans.exists() and pristine.exists():
        v = cfg_old.values(json.loads(ans.read_text(encoding="utf-8")))
        for src in pristine.rglob("*"):
            if src.is_file():
                t = src.read_text(encoding="utf-8", errors="replace")
                for k in sorted(cfg_old.TOKENS, key=len, reverse=True):
                    t = t.replace("{{" + k + "}}", v[k])
                filled[src.relative_to(pristine).as_posix()] = hashlib.sha256(t.encode("utf-8")).hexdigest()
    return files, filled


def download(dst):
    """The newest kit from GitHub (KIT_VERSION.json update_repo + setup/update_key.json) into dst/. Returns its KIT_VERSION."""
    sys.path.insert(0, str(NEW / "Studio" / "app"))
    import kit_update
    repo, token = kit_update.source()
    if not repo:
        raise RuntimeError("this kit has no update address; ask whoever sent it for the newest zip")
    print("Downloading the newest kit ...")
    tmp = dst.with_suffix(".zip")
    with kit_update.fetch(None, repo, token, timeout=120) as r, open(tmp, "wb") as f:
        total, got = int(r.headers.get("Content-Length") or 0), 0
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
            got += len(b)
            print(f"\r  {got / 1e6:.0f} MB" + (f" of {total / 1e6:.0f} MB" if total else ""), end="", flush=True)
    print()
    shutil.rmtree(dst, ignore_errors=True)
    with zipfile.ZipFile(tmp) as z:
        top = z.namelist()[0].split("/")[0] + "/"   # GitHub puts everything in "<owner>-<repo>-<commit>/"
        for m in z.infolist():
            if m.filename.startswith(top) and not m.is_dir():
                out = dst / m.filename[len(top):]
                out.parent.mkdir(parents=True, exist_ok=True)
                with z.open(m) as a, open(out, "wb") as b:
                    shutil.copyfileobj(a, b)
    tmp.unlink()
    return json.loads((dst / "KIT_VERSION.json").read_text(encoding="utf-8"))


def self_update():
    """Run inside an installed kit (Studio "Update now" or UPDATE.cmd there): download the newest version, update from it."""
    store = NEW / "Studio" / "app" / "store.py"
    if store.exists() and "{{KIT}}" in store.read_text(encoding="utf-8", errors="replace"):
        # a new zip was unzipped over this kit: the files are new but not filled in yet
        sys.exit(subprocess.run([sys.executable, "-X", "utf8", str(NEW / "update.py"), str(NEW)]).returncode)
    for _ in range(60):   # the Studio closes itself after "Update now"; give it a moment
        if not studio_running(NEW):
            break
        time.sleep(1)
    else:
        sys.exit("The Studio is still open. Close it, then run UPDATE.cmd in your kit folder.")
    cur = json.loads((NEW / "KIT_VERSION.json").read_text(encoding="utf-8")).get("version", 1) if (NEW / "KIT_VERSION.json").exists() else 1
    try:
        latest = download(NEW / "_update_source")
    except Exception as e:
        print(f"Couldn't download the update: {e}")
        restart(NEW)
        input("Press Enter to close.")
        sys.exit(1)
    if latest["version"] <= cur and "--force" not in sys.argv:
        print(f"You already have the newest version ({cur}).")
        shutil.rmtree(NEW / "_update_source", ignore_errors=True)
        restart(NEW)
        return
    code = subprocess.run([sys.executable, "-X", "utf8", str(NEW / "_update_source" / "update.py"), str(NEW)]).returncode
    shutil.rmtree(NEW / "_update_source", ignore_errors=True)
    restart(NEW)
    if code:
        input("\nThe update stopped (see above). Your backup is in _update_backups. Press Enter to close.")
        sys.exit(code)


def restart(kit):
    if "--restart" in sys.argv:
        print("Opening the Studio again ...")
        pyw = Path(sys.executable).with_name("pythonw.exe")   # same as Studio.cmd, without leaving a console window open
        subprocess.Popen([str(pyw if pyw.exists() else sys.executable), "-X", "utf8", str(kit / "Studio" / "app" / "main.py")],
                         cwd=str(kit / "Studio"), creationflags=0x00000008 if sys.platform == "win32" else 0)   # DETACHED_PROCESS
        time.sleep(3)


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("-"):
        if (NEW / "setup" / "answers.json").exists():   # started inside an installed kit: update it from GitHub
            self_update()
            return
    print(f"Creator Studio Kit updater - new version in {NEW}\n")
    new_ver = json.loads((NEW / "KIT_VERSION.json").read_text(encoding="utf-8"))
    old = find_installed().resolve()
    if not is_kit(old):
        sys.exit(f"{old} is not an installed kit (no configure.py / Studio). Nothing changed.")
    in_place = old == NEW
    old_ver = {"version": 1}
    if (old / "KIT_VERSION.json").exists() and not in_place:
        old_ver = json.loads((old / "KIT_VERSION.json").read_text(encoding="utf-8"))
    print(f"Installed kit: {old}  (version {old_ver['version']})  ->  version {new_ver['version']}")
    if not (old / "setup" / "answers.json").exists():
        sys.exit("That kit was never set up (no setup/answers.json). Set it up with MASTER PROMPT.md instead of updating.")
    if studio_running(old):
        sys.exit("The Studio is open. Close it (and any build it is running), then run the update again. Nothing changed.")

    if in_place:
        # the zip was unzipped over the old kit: the files are already new, only the fill-in is left
        print("The new files are already in this folder (unzipped over the old kit). Filling them in again.")
        shutil.rmtree(old / "setup" / "_pristine", ignore_errors=True)
        run_configure(old)
        finish(old, new_ver, [], None)
        return

    cfg_old = load_configure(old)
    shipped, filled = shipped_hashes(old, cfg_old)
    new_files = json.loads((NEW / "manifest.json").read_text(encoding="utf-8"))["files"]

    # 1. what did you change yourself?
    local = []
    for rel, h in shipped.items():
        p = old / rel
        if protected(rel) or rel in KEEP_THEIRS or not p.is_file() or rel in ("manifest.json", "KIT_VERSION.json"):
            continue
        cur = sha(p)
        if cur != h and cur != filled.get(rel):
            local.append(rel)

    # 2. back up everything the update touches
    bdir = old / "_update_backups"
    bdir.mkdir(exist_ok=True)
    bzip = bdir / f"before v{new_ver['version']} {time.strftime('%Y-%m-%d %H-%M')}.zip"
    with zipfile.ZipFile(bzip, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in sorted(set(shipped) | set(new_files)):
            p = old / rel
            if p.is_file():
                z.write(p, rel)
        for p in (old / "setup" / "answers.json", old / "Studio" / "data" / "settings.json"):
            if p.exists():
                z.write(p, p.relative_to(old).as_posix())
    print(f"Backup: {bzip}")

    # 3. copy the new version in
    copied = 0
    for rel in new_files:
        if protected(rel) or (rel in KEEP_THEIRS and (old / rel).exists()):
            continue
        d = old / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(NEW / rel, d)
        copied += 1
    # 4. files the new version dropped (only when you never changed them)
    removed = 0
    for rel in shipped:
        if rel not in new_files and not protected(rel) and rel not in local and (old / rel).is_file():
            (old / rel).unlink()
            removed += 1
    print(f"Copied {copied} files, removed {removed} old ones.")

    # 5. fill the new files in with your answers
    shutil.rmtree(old / "setup" / "_pristine", ignore_errors=True)
    run_configure(old)
    for f in ("manifest.json", "KIT_VERSION.json"):   # last: a failed update still says the old version
        shutil.copy2(NEW / f, old / f)
    finish(old, new_ver, local, bzip)


def run_configure(kit):
    r = subprocess.run([sys.executable, "-X", "utf8", str(kit / "configure.py"), "--update"], cwd=str(kit))
    if r.returncode:
        sys.exit("configure.py failed (see above). Your backup is in _update_backups. Ask Claude to look at it.")


def finish(kit, new_ver, local, bzip):
    # an updated kit was set up already (answers.json): the Studio's first-run setup wizard (v4) must not open for it
    sf = kit / "Studio" / "data" / "settings.json"
    try:
        s = json.loads(sf.read_text(encoding="utf-8")) if sf.exists() else {}
        if not s.get("setup_done"):
            s["setup_done"] = True
            sf.parent.mkdir(parents=True, exist_ok=True)
            sf.write_text(json.dumps(s, indent=2), encoding="utf-8")
    except (OSError, ValueError) as e:
        print(f"(couldn't mark setup as done: {e})")
    if local:
        lines = [f"# Local changes found during the update to version {new_ver['version']}", "",
                 "These files were changed on this PC after setup (by you or by Claude). The update replaced them with the new",
                 f"version; your changed copies are in `{bzip.relative_to(kit) if bzip else '_update_backups'}`.",
                 "Paste UPDATE PROMPT.md into Claude Code in this folder and Claude puts your changes back on top of the new version.", ""]
        lines += [f"- `{rel}`" for rel in local]
        (kit / "setup" / "LOCAL CHANGES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        (kit / "setup" / "LOCAL CHANGES.md").unlink(missing_ok=True)
    print(f"\nUpdated to version {new_ver['version']} ({new_ver.get('released', '')}). What's new:")
    for c in new_ver.get("changes", []):
        print(f"  - {c}")
    if local:
        print(f"\n{len(local)} file(s) you had changed are listed in setup/LOCAL CHANGES.md.")
    print("\nNext: open Claude Code in your kit folder and paste UPDATE PROMPT.md (it checks the update and puts back your own changes).")
    print("You can delete the folder you unzipped the update into afterwards.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nStopped. If it stopped half-way, your backup is in _update_backups.")

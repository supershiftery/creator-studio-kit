"""Fill this kit in for YOUR machine and channels.

    python configure.py                      reads setup/answers.json (Claude writes it with you during setup)
    python configure.py --check              only lists what is still unfilled
    python configure.py --update             after update.py: fills the new files in, keeps your Studio settings as they are

Every file in the kit that needs your paths or names holds a {{TOKEN}}. The first run saves a pristine copy of those files
in setup/_pristine/, so you can change an answer and run this again at any time: it always starts from the pristine copy.
It also writes Studio/data/settings.json (folders + channels), creates your folders and copies the emoji font from Windows.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parent
SETUP = KIT / "setup"
PRISTINE = SETUP / "_pristine"
ANSWERS = SETUP / "answers.json"
TEXT_EXT = {".py", ".js", ".html", ".css", ".md", ".json", ".cmd", ".ps1", ".txt", ".sh", ".csv"}
SKIP_FILES = {"configure.py", "update.py", "START HERE.md", "MASTER PROMPT.md", "SETUP QUESTIONS.md", "EDITING PLAYBOOK.md",
              "EYE TRAINING.md", "UPDATE PROMPT.md", "LOCAL CHANGES.md", "answers.example.json", "answers.json"}
# only these are ours; the intro templates use other {{X}} placeholders of their own, which must stay
TOKENS = ["KIT", "HOME", "STUDIO_NAME", "PROJECTS_ROOT", "GAMING_ROOT", "MUSIC_ROOT", "RECORDINGS", "VO_FOLDER",
          "DRIVE_ROOT", "DRIVE_FINISHED", "DRIVE_RAW", "WEBSITE", "LISTING_SITE",
          "GAMING_CHANNEL", "PHONE_CHANNEL", "REVIEW_CHANNEL", "PHONE_CHANNEL_RX", "REVIEW_CHANNEL_RX"]
PATH_TOKENS = {"KIT", "HOME", "PROJECTS_ROOT", "GAMING_ROOT", "MUSIC_ROOT", "RECORDINGS", "VO_FOLDER", "DRIVE_ROOT",
               "DRIVE_FINISHED", "DRIVE_RAW"}


def fwd(p):
    """Forward slashes: safe inside any Python/JS/JSON string (a backslash path can turn into escape codes)."""
    return str(p).replace("\\", "/").rstrip("/")


def values(a):
    home = Path.home()
    chans = a.get("channels") or []
    first = lambda t, d: next((c["name"] for c in chans if t in c.get("types", [])), d)
    v = {
        "KIT": fwd(KIT), "HOME": fwd(home),
        "STUDIO_NAME": a.get("studio_name") or "Creator Studio",
        "PROJECTS_ROOT": fwd(a.get("projects_root") or "D:/Video Projects"),
        "GAMING_ROOT": fwd(a.get("gaming_root") or a.get("projects_root") or "D:/Video Projects"),
        "MUSIC_ROOT": fwd(a.get("music_root") or "D:/Music"),
        "RECORDINGS": fwd(a.get("recordings") or home / "Videos"),
        "VO_FOLDER": fwd(a.get("vo_folder") or home / "Documents" / "Voiceovers"),
        "DRIVE_ROOT": fwd(a.get("drive_root") or "G:/My Drive"),
        "WEBSITE": a.get("website") or "your-site.com",
        "LISTING_SITE": a.get("listing_site") or a.get("website") or "your-site.com",
        "GAMING_CHANNEL": first("gaming", "Gaming Channel"),
        "PHONE_CHANNEL": first("phone", "App Channel"),
        "REVIEW_CHANNEL": first("review", "Review Channel"),
    }
    v["DRIVE_FINISHED"] = fwd(a.get("drive_finished") or f"{v['DRIVE_ROOT']}/Finished videos")
    v["DRIVE_RAW"] = fwd(a.get("drive_raw") or f"{v['DRIVE_ROOT']}/Raw Videos")
    for k in ("PHONE", "REVIEW"):
        names = [c["name"] for c in chans if k.lower() in c.get("types", [])] or [v[f"{k}_CHANNEL"]]
        v[f"{k}_CHANNEL_RX"] = "(?:" + "|".join(re.escape(n.lower()).replace(" ", " ?") for n in names) + ")"
    return v


def text_files():
    for dp, dn, fn in os.walk(KIT):
        if "_pristine" in dp or "node_modules" in dp or "_update_backups" in dp or "_update_source" in dp:
            continue
        for f in fn:
            p = Path(dp) / f
            if p.suffix.lower() in TEXT_EXT and f not in SKIP_FILES:
                yield p


def snapshot():
    """First run: keep the token-bearing originals so later runs can start clean."""
    if PRISTINE.exists():
        return
    rx = re.compile(r"\{\{(?:" + "|".join(TOKENS) + r")\}\}")
    n = 0
    for p in text_files():
        t = p.read_text(encoding="utf-8", errors="replace")
        if rx.search(t):
            dst = PRISTINE / p.relative_to(KIT)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
            n += 1
    print(f"saved {n} pristine files")


def apply(v):
    n = 0
    for src in PRISTINE.rglob("*"):
        if not src.is_file():
            continue
        t = src.read_text(encoding="utf-8", errors="replace")
        for k in sorted(TOKENS, key=len, reverse=True):   # PHONE_CHANNEL_RX before PHONE_CHANNEL
            t = t.replace("{{" + k + "}}", v[k])
        dst = KIT / src.relative_to(PRISTINE)
        dst.write_text(t, encoding="utf-8", newline="")
        n += 1
    print(f"filled {n} files")


def settings(a, v, update=False):
    p = KIT / "Studio" / "data" / "settings.json"
    s = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    new = {
        "roots": {"gaming": v["GAMING_ROOT"], "phone": v["PROJECTS_ROOT"], "review": v["PROJECTS_ROOT"]},
        "drive_root": v["DRIVE_FINISHED"], "recordings": [v["RECORDINGS"]], "vo_folder": v["VO_FOLDER"],
        "music_root": v["MUSIC_ROOT"], "competitor_tracker": v["KIT"] + "/integrations/competitor-tracker",
        "channels": [{"name": c["name"], "types": c.get("types", ["review"]), "per_week": c.get("per_week", 2),
                      "drive": c.get("drive", c["name"]), **({"fillers": c["fillers"]} if c.get("fillers") else {})}
                     for c in a.get("channels", [])],
    }
    if update and s:   # an update never undoes what you changed in Studio -> Settings; it only adds settings that are new
        new = {k: val for k, val in new.items() if k not in s}
    s.update(new)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(s, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {p}")


def folders(v):
    for k in ("PROJECTS_ROOT", "GAMING_ROOT", "MUSIC_ROOT", "VO_FOLDER"):
        try:
            Path(v[k]).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"  could not create {v[k]}: {e}")
    for sub in ("Type Beats", "Lo-Fi", "Game Music", "Shorts", "_rejected (vocals or tags)"):
        Path(v["MUSIC_ROOT"], sub).mkdir(parents=True, exist_ok=True)
    (Path(v["PROJECTS_ROOT"]) / "Phone Videos").mkdir(parents=True, exist_ok=True)


def personal_files():
    """Your codes + privacy terms start from the shipped examples once and are never overwritten after that."""
    for rel in ("tools/phone_edit/codes.json", "tools/privacy_terms.json"):
        dst = KIT / rel
        ex = dst.with_name(dst.stem + ".example.json")
        if not dst.exists() and ex.exists():
            shutil.copy2(ex, dst)


def remember():
    """Lets update.py find this kit next time."""
    try:
        (Path.home() / ".creator-studio-kit.json").write_text(json.dumps({"kit": str(KIT)}), encoding="utf-8")
    except OSError:
        pass


def emoji_font():
    dst = KIT / "tools" / "intro_library" / "kit" / "fonts" / "SegoeEmoji.ttf"
    src = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "seguiemj.ttf"
    if not dst.exists() and src.exists():
        shutil.copy2(src, dst)
        print("copied the Windows emoji font into the intro kit")


def gpu():
    try:
        out = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        out = ""
    print(("NVIDIA GPU found: " + out.splitlines()[0]) if out else
          "NO NVIDIA GPU found: the pipelines encode with h264_nvenc. Ask Claude to switch them to libx264 (see MASTER PROMPT, phase 2).")


def main():
    if "--check" in sys.argv:
        rx = re.compile(r"\{\{(?:" + "|".join(TOKENS) + r")\}\}")
        left = [str(p.relative_to(KIT)) for p in text_files() if rx.search(p.read_text(encoding="utf-8", errors="replace"))]
        print(f"{len(left)} files still have unfilled tokens" + (":\n  " + "\n  ".join(left[:40]) if left else ""))
        return
    if not ANSWERS.exists():
        sys.exit(f"Missing {ANSWERS}. Copy setup/answers.example.json to setup/answers.json and fill it in (Claude does this with you).")
    a = json.loads(ANSWERS.read_text(encoding="utf-8"))
    v = values(a)
    snapshot()
    apply(v)
    settings(a, v, update="--update" in sys.argv)
    folders(v)
    personal_files()
    emoji_font()
    remember()
    gpu()
    print("done. Start the studio with Studio\\Studio.cmd")


if __name__ == "__main__":
    main()

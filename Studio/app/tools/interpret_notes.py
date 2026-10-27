"""Claude reads your notes-in-your-own-words and turns them into exact cut / protect notes (gaming + product review;
phone projects use phone_edit\\revise.py for the same job).   python interpret_notes.py <project id> <notes.json>

notes.json: [{"text": "note 1:12-1:19: there's a weird animation here, take it out", "t0": 72.0, "t1": 79.0}]  (DRAFT times)
For every note it sends Opus 5.5 the draft transcript around the note's times (word-level, draft time), asks for exact
ranges whose edges sit on word boundaries, and posts them back to the studio as normal notes ("cut 1:12.4-1:19.0 …"),
so the cutter applies them on the rebuild that follows this step."""
import json
import os
import re
import subprocess
import sys
import urllib.request

API = "http://127.0.0.1:%d/api/" % int(os.environ.get("STUDIO_PORT", "8765"))
pid, notes_path = sys.argv[1], sys.argv[2]
notes = json.load(open(notes_path, encoding="utf-8"))
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def get(path):
    return json.load(urllib.request.urlopen(API + path, timeout=60))


def post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=60))


def fmt(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


ed = get(f"editor?id={pid}")
keep, offset = [tuple(k) for k in ed["keep"]], float(ed.get("offset") or 0)


def to_draft(t):
    if not keep:
        return t + offset
    acc = offset
    for a, b in keep:
        if t < a - 0.02:
            return None
        if t <= b + 0.02:
            return acc + max(0.0, t - a)
        acc += b - a
    return None


words = []
for w in ed["words"]:
    s, e = to_draft(w["s"]), to_draft(w["e"])
    if s is not None and e is not None:
        words.append((round(s, 2), round(e, 2), w["w"]))
blocks = []
for i, n in enumerate(notes):
    t0 = n.get("t0")
    t1 = n.get("t1") if n.get("t1") is not None else (t0 + 8 if t0 is not None else None)
    if t0 is None:
        m = re.findall(r"(\d+):(\d{2}(?:\.\d+)?)", n["text"])
        if m:
            t0 = int(m[0][0]) * 60 + float(m[0][1])
            t1 = int(m[-1][0]) * 60 + float(m[-1][1]) if len(m) > 1 else t0 + 8
    if t0 is None:
        blocks.append(f"NOTE {i}: {n['text']}\n(no time given: answer action \"none\")")
        continue
    ctx = [f"[{s:.2f}-{e:.2f}] {w}" for s, e, w in words if t0 - 15 <= s <= t1 + 15]
    blocks.append(f"NOTE {i} (the creator marked {fmt(t0)} to {fmt(t1)}): {n['text']}\nTranscript around it (draft seconds, one word per line):\n" + "\n".join(ctx))
prompt = ("You are editing a YouTube video with its creator. They watched the draft and left the notes below (times are DRAFT times; "
          "the marked range is when they pressed the button and when they said the thing ends, so it is approximate). For each note decide "
          "what to do to the draft: \"cut\" (remove a stretch), \"protect\" (the cutter must keep it), or \"none\" (not a timeline change, e.g. music, "
          "graphics, colour; put the instruction in why). For cut/protect give exact t0/t1 in draft seconds: when the note is about speech, put both "
          "edges on word boundaries from the transcript (start of the first removed word, end of the last removed word) and keep the sentences on both "
          "sides whole; when it is about a visual (an animation, transition, glitch, dead screen) with no speech to anchor on, use the marked range. "
          "Never cut more than the note asks for. Reply with ONLY a JSON list: [{\"note\": 0, \"action\": \"cut\", \"t0\": 72.4, \"t1\": 79.0, \"why\": \"short reason\"}].\n\n"
          + "\n\n".join(blocks))
if os.environ.get("STUDIO_DRY"):
    print(prompt[:3000])
    sys.exit(0)
exe = next((c for c in (os.path.expanduser("~/.local/bin/claude.exe"), os.path.expanduser("~/.local/bin/claude")) if os.path.exists(c)), "claude")
print(f"asking Opus about {len(notes)} note(s)", flush=True)
r = subprocess.run([exe, "-p", prompt, "--model", "claude-opus-5-5", "--output-format", "json", "--max-turns", "1", "--no-session-persistence", "--tools", "", "--setting-sources", "", "--strict-mcp-config", "--disable-slash-commands"],
                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600, creationflags=CREATE_NO_WINDOW, stdin=subprocess.DEVNULL)
try:
    out = json.loads(r.stdout).get("result", "")
except ValueError:
    sys.exit("claude did not answer: " + (r.stdout or r.stderr)[-500:])
if "Not logged in" in out:
    sys.exit("the Claude Code CLI is not signed in")
m = re.search(r"\[.*\]", out, re.S)
plan = json.loads(m.group(0)) if m else []
added = 0
for a in plan:
    act = (a.get("action") or "none").lower()
    src = notes[int(a.get("note", 0))]["text"] if str(a.get("note", "")).isdigit() and int(a["note"]) < len(notes) else ""
    if act in ("cut", "protect") and a.get("t1", 0) > a.get("t0", 0):
        text = f"{act} {fmt(float(a['t0']))}-{fmt(float(a['t1']))} — {a.get('why', '')} (from: {src[:80]})"
        post(f"project/notes?id={pid}", {"text": text})
        added += 1
        print(f"  {act} {fmt(float(a['t0']))}-{fmt(float(a['t1']))}  {a.get('why', '')}", flush=True)
    else:
        print(f"  not a cut: {a.get('why', '')}  ({src[:60]})", flush=True)
print(f"{added} exact note(s) added; the rebuild applies them")

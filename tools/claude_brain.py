"""The editor's brain at the judgment points of the edit pipelines: Claude, through the Claude Code CLI you already
sign in to (your own Claude plan; no API key, no other AI service).

    from claude_brain import ask
    plan = ask("intro_director", prompt, images=[png, ...], model="opus")   # parsed JSON, or None

The pipelines stay rule-based; the brain only answers the questions rules get wrong (what each intro line should SHOW,
is this picture really the thing, is this QC flag a real mistake).

The CLI is called lean (no CLAUDE.md, memory, hooks, skills or MCP: ~1-5k tokens a call instead of ~150k), one turn, no
tools. Models per role are in tools/brain.json ("opus" for the intro plan, "sonnet" for checks).
Teaching (teach.py): every prompt starts with the reasoning playbook for the task (teach/playbook.md) and worked
examples of approved decisions (teach/examples/<task>/*.json): how a new editor is taught.
Every answer is CACHED (same task + prompt + images = no new call) and LOGGED (_state/claude_ledger.jsonl).
CLAUDE_BRAIN=0 (or the AI director box off in a project) turns it off; any failure (not signed in, offline, plan limit)
returns None and the caller keeps its rule-based result.
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "_state")
CACHE = os.path.join(STATE, "claude_cache")
LEDGER = os.path.join(STATE, "claude_ledger.jsonl")
TEACH = os.path.join(HERE, "teach")
# everything the user teaches lives in <kit>/my_style (updates never touch it): taught examples + their own video types
MY_STYLE = os.environ.get("STUDIO_MY_STYLE") or os.path.join(os.path.dirname(HERE), "my_style")
EXAMPLES = os.path.join(MY_STYLE, "examples")
OLD_EXAMPLES = os.path.join(TEACH, "examples")
CONFIG = os.path.join(HERE, "brain.json")
DEFAULTS = {
    "claude": {"opus": "claude-opus-5-5", "sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5"},
    "examples_per_prompt": 2,
}
SYSTEM = ("You are the senior video editor working inside an automated editing pipeline for a YouTube creator. "
          "You get exact data (transcripts with times, clip lists, descriptions of contact sheets) and answer ONLY with the JSON "
          "asked for, no prose around it. Never invent facts, prices or quotes the creator did not say. "
          "House rules: no dates/years/months on screen, no emojis, instrumental music only, never show private info.")
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def config():
    c = json.loads(json.dumps(DEFAULTS))
    try:
        user = json.load(open(CONFIG, encoding="utf-8"))
        for k, v in user.items():
            c[k] = {**c[k], **v} if isinstance(v, dict) and isinstance(c.get(k), dict) else v
    except (OSError, ValueError):
        pass
    return c


def enabled():
    return os.environ.get("CLAUDE_BRAIN", "1") not in ("0", "off", "false", "no")


def _log(rec):
    try:
        os.makedirs(STATE, exist_ok=True)
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass


def parse_json(text):
    """The first JSON object/list in the answer (models sometimes wrap it in ```json fences or think out loud first)."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    text = re.sub(r"```(?:json)?", "", text).strip()
    for pat in (r"\{.*\}", r"\[.*\]"):
        m = re.search(pat, text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------- teaching (playbook + worked examples)
def playbook(task):
    """The playbook section for this task (## <task>) plus the general section (## all)."""
    try:
        txt = open(os.path.join(TEACH, "playbook.md"), encoding="utf-8").read()
    except OSError:
        return ""
    keep, cur = [], None
    for line in txt.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip().split()[0].lower()
        if cur in ("all", task):
            keep.append(line)
    return "\n".join(keep).strip()


def migrate_examples():
    """Kits before v4 kept taught examples in tools/teach/examples: copy them into my_style/examples once (the old folder
    stays as it was, so nothing is lost if this runs half-way)."""
    mark = os.path.join(EXAMPLES, ".moved")
    if os.path.exists(mark) or not os.path.isdir(OLD_EXAMPLES):
        return
    import shutil
    for root, _, files in os.walk(OLD_EXAMPLES):
        for f in files:
            src = os.path.join(root, f)
            dst = os.path.join(EXAMPLES, os.path.relpath(src, OLD_EXAMPLES))
            if not os.path.exists(dst):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
    os.makedirs(EXAMPLES, exist_ok=True)
    open(mark, "w").write("taught examples copied here from tools/teach/examples\n")


def type_brief():
    """A build of the user's own video type (STUDIO_MY_TYPE, set by the Studio): its playbook + the rules learned from notes."""
    slug = os.environ.get("STUDIO_MY_TYPE")
    if not slug:
        return ""
    parts = []
    try:
        parts.append(open(os.path.join(MY_STYLE, "types", slug + ".md"), encoding="utf-8").read().strip())
    except OSError:
        pass
    try:
        t = json.load(open(os.path.join(MY_STYLE, "types", slug + ".json"), encoding="utf-8"))
        rules = [f"- [{r.get('category', 'other')}] {r['text']}" for r in t.get("rules") or [] if not r.get("off")]
        if rules:
            parts.append("Rules learned from the creator's revision notes on this type (always follow them):\n" + "\n".join(rules))
    except (OSError, ValueError, KeyError):
        pass
    return "\n\n".join(p for p in parts if p)


def examples(task, n=None):
    migrate_examples()
    d = os.path.join(EXAMPLES, task)
    if not os.path.isdir(d):
        return []
    files = sorted((os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json")), key=os.path.getmtime, reverse=True)
    out = []
    for f in files[: n if n is not None else config()["examples_per_prompt"]]:
        try:
            out.append(json.load(open(f, encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return out


def lesson(task):
    """Playbook + worked examples as one block to put before the real question."""
    parts = []
    tb = type_brief()
    if tb:
        parts.append("THIS VIDEO IS THE CREATOR'S OWN VIDEO TYPE. Its style comes first:\n" + tb)
    pb = playbook(task)
    if pb:
        parts.append("HOW TO THINK ABOUT THIS (the senior editor's playbook):\n" + pb)
    for k, ex in enumerate(examples(task), 1):
        parts.append(f"WORKED EXAMPLE {k} ({ex.get('title', '')}), an approved decision. Study the reasoning, don't copy the answer.\n"
                     f"--- input ---\n{ex['input']}\n--- approved answer ---\n{json.dumps(ex['output'], ensure_ascii=False)}"
                     + (f"\n--- why it is right ---\n{ex['lesson']}" if ex.get("lesson") else ""))
    if parts:
        parts.append("NOW THE REAL TASK. Think it through the same way, then reply with only the JSON.")
    return "\n\n".join(parts)


# ---------------------------------------------------------------- Claude CLI (lean)
def _claude(prompt, images, model, timeout, say, task):
    model_id = config()["claude"].get(model, model)
    blocks = []
    for p in images or ():
        mt = "image/png" if p.lower().endswith(".png") else "image/jpeg"
        blocks.append({"type": "image", "source": {"type": "base64", "media_type": mt, "data": base64.b64encode(open(p, "rb").read()).decode()}})
    blocks.append({"type": "text", "text": prompt})
    exe = next((x for x in (os.path.expanduser("~/.local/bin/claude.exe"), os.path.expanduser("~/.local/bin/claude")) if os.path.exists(x)), "claude")
    cmd = [exe, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--model", model_id,
           "--max-turns", "1", "--no-session-persistence", "--tools", "", "--setting-sources", "", "--strict-mcp-config",
           "--disable-slash-commands", "--system-prompt", SYSTEM]
    t0 = time.time()
    try:
        r = subprocess.run(cmd, input=json.dumps({"type": "user", "message": {"role": "user", "content": blocks}}) + "\n", capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as e:
        say(f"brain ({task}): claude gave no answer ({e})")
        return None
    res = None
    for line in r.stdout.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") == "result":
            res = d
    if not res or res.get("is_error") or "Not logged in" in (res.get("result") or ""):
        say(f"brain ({task}): claude failed ({((res or {}).get('result') or r.stderr or r.stdout)[-200:].strip()})")
        return None
    u = res.get("usage") or {}
    tokens = sum(u.get(k, 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    _log({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "task": task, "role": "brain", "model": model_id, "cached": False, "in": tokens,
          "out": u.get("output_tokens", 0), "usd": res.get("total_cost_usd"), "s": round(time.time() - t0, 1), "images": len(images or ())})
    say(f"brain ({task}, {model_id}): {tokens} in / {u.get('output_tokens', 0)} out, ${res.get('total_cost_usd') or 0:.3f}, {time.time() - t0:.0f} s")
    return res.get("result") or ""


# ---------------------------------------------------------------- the one entry point
def ask(task, prompt, images=(), model="sonnet", timeout=300, raw=False, say=print, backend=None):
    """One cached judgment call. model: "opus" / "sonnet" / "haiku" (brain.json maps them to model ids).
    backend is accepted for callers written for other backends and ignored: the kit always asks Claude.
    Returns the parsed JSON (or the text when raw=True), None when off/failed."""
    if not enabled():
        return None
    images = [p for p in images or () if p and os.path.exists(p)]
    h = hashlib.sha256((f"{task}|claude|{model}|{SYSTEM}|{prompt}" + (f"|{type_brief()}" if type_brief() else "")).encode())
    for p in images:
        h.update(open(p, "rb").read())
    cp = os.path.join(CACHE, f"{task}-{h.hexdigest()[:20]}.json")
    if os.path.exists(cp):
        text = json.load(open(cp, encoding="utf-8"))["text"]
        _log({"t": time.strftime("%Y-%m-%d %H:%M:%S"), "task": task, "backend": "claude", "cached": True})
        return text if raw else parse_json(text)
    lp = lesson(task)
    text = _claude((lp + "\n\n" + prompt) if lp else prompt, images, model, timeout, say, task)
    if text is None:
        say(f"brain ({task}): no answer; keeping the rule-based result")
        return None
    out = text if raw else parse_json(text)
    if out is not None:   # only good answers are cached; a garbled one is asked again next time
        os.makedirs(CACHE, exist_ok=True)
        json.dump({"task": task, "backend": "claude", "model": model, "t": time.strftime("%Y-%m-%d %H:%M:%S"), "prompt": prompt,
                   "images": images, "seen": None, "text": text}, open(cp, "w", encoding="utf-8"), indent=1)
    else:
        say(f"brain ({task}): Claude answered without usable JSON; keeping the rule-based result")
    return out


def ledger(days=7):
    """Calls over the last `days` days: {task: {"calls", "cached", "usd", "models"}}."""
    out, cut = {}, time.time() - days * 86400
    try:
        for line in open(LEDGER, encoding="utf-8"):
            d = json.loads(line)
            if time.mktime(time.strptime(d["t"], "%Y-%m-%d %H:%M:%S")) < cut:
                continue
            o = out.setdefault(d["task"], {"calls": 0, "cached": 0, "usd": 0.0, "models": {}})
            o["cached" if d.get("cached") else "calls"] += 1
            o["usd"] += d.get("usd") or 0
            if d.get("model") and not d.get("cached"):
                o["models"][d["model"]] = o["models"].get(d["model"], 0) + 1
    except (OSError, ValueError):
        pass
    return out


def contact_sheet(items, out_png, cols=4, w=360):
    """items: [(image or video path, seconds or None, label[, ffmpeg crop filter])] -> one labelled PNG grid (one image =
    one cheap look)."""
    from PIL import Image, ImageDraw, ImageFont
    import io
    h = w * 9 // 16
    rows = (len(items) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * (h + 28)), (20, 20, 20))
    dr = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    for n, it in enumerate(items):
        src, t, label = it[:3]
        vf = (it[3].rstrip(",") + ",") if len(it) > 3 and it[3] else ""
        x, y = (n % cols) * w, (n // cols) * (h + 28)
        try:
            if t is None and not src.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".m4v")):
                im = Image.open(src).convert("RGB")
            else:
                raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t or 0:.2f}", "-i", src, "-frames:v", "1", "-vf", f"{vf}scale={w}:{h}:force_original_aspect_ratio=decrease",
                                      "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, creationflags=CREATE_NO_WINDOW).stdout
                im = Image.open(io.BytesIO(raw)).convert("RGB")
            im.thumbnail((w, h))
            sheet.paste(im, (x + (w - im.width) // 2, y + (h - im.height) // 2))
        except Exception:
            dr.text((x + 8, y + h // 2), "(no frame)", fill=(200, 80, 80), font=font)
        dr.text((x + 6, y + h + 5), str(label)[:44], fill=(240, 240, 240), font=font)
    sheet.save(out_png)
    return out_png


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "ledger":
        print(json.dumps(ledger(int(sys.argv[2]) if len(sys.argv) > 2 else 7), indent=1))
    else:
        print(ask("selftest", 'Reply with {"ok": true}', model="haiku"))

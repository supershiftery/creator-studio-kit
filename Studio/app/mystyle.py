"""My video types (2026-10-29): video types the user teaches the Studio, and the rules their revision notes turned into.

Everything a user teaches lives in ONE folder that updates never touch (the kit's update.py protects `my_style/`):

    my_style/
      types/<slug>.json     a custom type: base pipeline, the style measured from their example videos, the project settings
                            that style becomes, and the rules learned from revision notes (each removable)
      types/<slug>.md       a short playbook for the type (what Claude writes after looking at the examples)
      examples/<task>/      the AI director's taught examples (tools/teach.py; moved here from tools/teach/examples)
      rules.json            notes marked "rule" on any project, as category rules
      _work/                analysis frames + status while the New video type wizard runs

A project of a custom type is a project of its BASE type (store type: phone / review / haul / short / gaming) with
settings.my_type = <slug>. Before every build sync() writes the type's settings into the project (keys the user set on the
project by hand win), so a rule learned from a note on one video is followed by the next build of every video of that type.

type_summary() is the only thing the anonymous edit-stats sender may read: base type, layout, pace numbers, captions on/off,
music mood and the number of rules. No names, words or file paths.
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import store

APP = Path(__file__).resolve().parent
_KIT = APP.parents[1]
# the kit keeps it next to configure.py (<kit>/my_style); the original studio keeps it in its own folder
ROOT = Path(os.environ.get("MY_STYLE_ROOT") or store.settings().get("my_style_root") or (_KIT / "my_style" if (_KIT / "configure.py").exists() else APP.parent / "my_style"))
TYPES = ROOT / "types"
WORK = ROOT / "_work"
RULES = ROOT / "rules.json"
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# wizard base -> (store type, project settings that pick the pipeline). "talking" = the general trim edit (recipes/trim.py)
BASES = {
    "talking": ("phone", {"trim_only": True, "general": True}),
    "review": ("review", {}),
    "phone": ("phone", {}),
    "haul": ("haul", {}),
    "short": ("short", {}),
    "gaming": ("gaming", {}),
}
BASE_LABELS = {"talking": "Talking / trim", "review": "Product review", "phone": "Phone / app tutorial", "haul": "Haul",
               "short": "Short (vertical)", "gaming": "Gaming"}
LAYOUTS = ("1cam", "2cam", "screen_cam", "vertical", "no_face")
CATEGORIES = ("pacing", "pauses", "camera", "zooms", "captions", "music", "text", "transitions", "intro", "sections", "audio", "other")
# project settings a type (or a learned rule) may set: what the pipelines read (recipes/__init__.flags, gaming/assemble,
# tools/haul_render, tools/captions ...). Anything else a rule says goes to Claude as words (the type's rules block).
SETTING_KEYS = {
    "pauses": "natural | tight (jump-cut pacing: take_cuts.py)",
    "fillers": "auto | light | heavy (filler words cut)",
    "captions": '{"on": true|false, "style": "<caption preset>"}',
    "music": "false = no music bed",
    "music_bed_lufs": "music bed loudness, e.g. -36 (quiet) .. -28 (loud)",
    "music_mood": "chill | upbeat | hype | dark | cinematic | lo-fi",
    "wipe": "off = no section transition graphic (gaming)",
    "wipe_sfx": "off = no whoosh on section changes",
    "short_zoom": "false = no punch-in zooms (Shorts), or a zoom factor like 1.15",
    "short_cards": "false = no text cards (Shorts)",
    "short_hook": "false = no hook headline (Shorts)",
    "turn_follow": "cut | zoom | off: when the speaker turns their head on one camera",
    "intro_tight": "true = end the intro right after its last word",
}
_LOCK = threading.Lock()


def _read(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(p, data):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    # Windows refuses the swap while anyone has the file open: the Train screen reads status.json every 2 s, and that failure
    # killed a training run at 80% (2026-11-04)
    for n in range(40):
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            if n == 39:
                raise
            time.sleep(0.25)


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:40] or "my-type"


# ---------------------------------------------------------------- types
def list_types():
    out = []
    for p in sorted(TYPES.glob("*.json")) if TYPES.is_dir() else []:
        t = _read(p)
        if t and t.get("slug"):
            out.append(t)
    return out


def load_type(slug):
    t = _read(TYPES / f"{slugify(slug)}.json")
    if not t:
        raise ValueError(f"no video type '{slug}'")
    return t


def save_type(t):
    t["updated"] = time.strftime("%Y-%m-%d %H:%M")
    with _LOCK:
        _write(TYPES / f"{t['slug']}.json", t)
    return t


def playbook(slug):
    p = TYPES / f"{slugify(slug)}.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def new_type(name, base, style=None, playbook_md="", examples=0, raw=False):
    if base not in BASES:
        raise ValueError(f"base must be one of {', '.join(BASES)}")
    slug = slugify(name)
    n = 2
    while (TYPES / f"{slug}.json").exists():
        slug = f"{slugify(name)}-{n}"
        n += 1
    t = {"name": name.strip(), "slug": slug, "base": base, "created": time.strftime("%Y-%m-%d %H:%M"),
         "style": style or {}, "rules": [], "examples": examples, "raw_example": bool(raw)}
    t["settings"] = style_settings(t)
    save_type(t)
    if playbook_md:
        (TYPES / f"{slug}.md").write_text(playbook_md.strip() + "\n", encoding="utf-8")
    return t


def delete_type(slug):
    import shutil
    for ext in (".json", ".md"):
        (TYPES / f"{slugify(slug)}{ext}").unlink(missing_ok=True)
    shutil.rmtree(TYPES / slugify(slug), ignore_errors=True)


# ---------------------------------------------------------------- the type's own pieces (assets): start / end / logo / music / use
ROLES = {"start": "At the start of every video", "end": "At the end of every video", "logo": "Logo in the corner",
         "music": "Music to use", "use": "Use it where it fits"}


def add_asset(slug, src, role="use", dur=None, note=""):
    """Copy a file into my_style/types/<slug>/assets and record its role. start / end / logo go into every build
    (tools/style_bookends.py); music / use reach Claude through the type's brief."""
    import shutil
    if role not in ROLES:
        role = "use"
    t = load_type(slug)
    d = TYPES / t["slug"] / "assets"
    d.mkdir(parents=True, exist_ok=True)
    name = Path(src).name
    dst = d / name
    n = 2
    while dst.exists() and Path(src).resolve() != dst.resolve():
        dst = d / f"{Path(name).stem} ({n}){Path(name).suffix}"
        n += 1
    if Path(src).resolve() != dst.resolve():
        shutil.copy2(src, dst)
    with _LOCK:
        t = load_type(slug)
        t.setdefault("assets", []).append({"file": dst.name, "role": role, **({"dur": float(dur)} if dur else {}),
                                           **({"note": note[:200]} if note else {})})
        _write(TYPES / f"{t['slug']}.json", t)
    return t


def remove_asset(slug, file):
    with _LOCK:
        t = load_type(slug)
        t["assets"] = [a for a in t.get("assets") or [] if a.get("file") != file]
        _write(TYPES / f"{t['slug']}.json", t)
    (TYPES / t["slug"] / "assets" / file).unlink(missing_ok=True)
    return t


def opening_card(text, out_png, vertical=False):
    """A clean text card (the scripture / quote / disclaimer a creator always opens with): white text centred on black."""
    from PIL import Image, ImageDraw, ImageFont
    W, H = (1080, 1920) if vertical else (1920, 1080)
    im = Image.new("RGB", (W, H), (8, 8, 10))
    dr = ImageDraw.Draw(im)
    fp = APP / "fonts" / "Poppins-Medium.ttf"
    size = 64 if not vertical else 58
    while True:
        font = ImageFont.truetype(str(fp), size) if fp.exists() else ImageFont.load_default()
        lines = []
        for para in text.strip().splitlines():
            cur = ""
            for w in para.split():
                test = (cur + " " + w).strip()
                if dr.textlength(test, font=font) > W * 0.78 and cur:
                    lines.append(cur)
                    cur = w
                else:
                    cur = test
            lines.append(cur)
        lh = int(size * 1.35)
        if len(lines) * lh < H * 0.7 or size <= 30:
            break
        size -= 4
    y = (H - len(lines) * lh) // 2
    for ln in lines:
        dr.text(((W - dr.textlength(ln, font=font)) / 2, y), ln, font=font, fill=(240, 240, 240))
        y += lh
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    im.save(out_png)
    return out_png


def with_bookends(doc, action, steps, qc_ids):
    """Build steps of a custom-type project: its start / end / logo pieces go on the render right before the QC check."""
    t = type_of(doc)
    if not t or action not in ("draft", "final", "all", "revise", "intro"):
        return steps
    if not any(a.get("role") in ("start", "end", "logo") for a in t.get("assets") or []):
        return steps
    i = next((n for n, st in enumerate(steps) if st.get("id") in qc_ids), None)
    video = next((c for c in (steps[i].get("cmd") or []) if str(c).lower().endswith(".mp4")), None) if i is not None else None
    if not video:
        return steps
    py = store.settings().get("python") or sys.executable
    st = {"id": "style_pieces", "label": f"{t['name']}: opening / ending / logo", "cwd": doc["path"], "force": True,
          "cmd": [py, "-X", "utf8", str(APP / "tools" / "style_bookends.py"), doc["path"], str(video)],
          "env": dict(steps[i].get("env") or {})}
    return steps[:i] + [st] + steps[i:]


def style_settings(t):
    """The measured style -> project settings the base pipeline reads. Only what the examples showed clearly."""
    st, base = t.get("style") or {}, t.get("base")
    out = {}
    pace = st.get("pace") or {}
    if pace.get("tightness") in ("tight", "natural"):
        out["pauses"] = pace["tightness"]
    elif pace.get("tightness") == "loose":
        out["pauses"] = "natural"
    cap = st.get("captions") or {}
    if "on" in cap:
        out["captions"] = {"on": bool(cap["on"]), **({"style": cap["style"]} if cap.get("on") and cap.get("style") else {})}
    mus = st.get("music") or {}
    if mus.get("on") is False:
        out["music"] = False
    elif mus.get("on"):
        if mus.get("mood"):
            out["music_mood"] = mus["mood"]
        lvl = {"low": -38.0, "medium": -34.0, "high": -30.0}.get(mus.get("energy"))
        if lvl:
            out["music_bed_lufs"] = lvl
    zo = st.get("zooms") or {}
    turn = st.get("head_turns") or {}
    if turn.get("follow") in ("cut", "zoom"):
        out["turn_follow"] = turn["follow"]
    if base == "short":
        if zo.get("on") is False:
            out["short_zoom"] = False
        if st.get("text_on_screen") in ("none",):
            out["short_cards"] = False
        if st.get("intro") in ("none", "cold_open"):
            out["short_hook"] = False
    if base == "gaming":
        # a custom gaming type is not a Top-N server list: no server transition / whoosh unless their examples wipe
        if st.get("transitions") != "wipe":
            out["wipe"] = "off"
            out["wipe_sfx"] = "off"
    if st.get("intro") in ("cold_open", "none"):
        out["intro_tight"] = True
    return out


def effective_settings(t):
    """style settings, then every learned rule's settings in the order they were learned (a newer rule wins)."""
    s = dict(t.get("settings") or style_settings(t))
    for r in t.get("rules") or []:
        if r.get("off"):
            continue
        for k, v in (r.get("settings") or {}).items():
            if k in SETTING_KEYS:
                s[k] = v
    return s


def rules_text(t):
    """The type's rules in words, for Claude (revisions, the AI director)."""
    lines = [f"- [{r.get('category', 'other')}] {r['text']}" for r in t.get("rules") or [] if not r.get("off")]
    return "\n".join(lines)


# ---------------------------------------------------------------- projects of a custom type
def type_of(doc):
    slug = ((doc or {}).get("settings") or {}).get("my_type")
    if not slug:
        return None
    try:
        return load_type(slug)
    except ValueError:
        return None


def matches(det):
    """Custom types that fit a detect() result: same base pipeline, same camera layout when both are known."""
    kind = det.get("type")
    kind = "talking" if kind == "other" else kind
    out = []
    for t in list_types():
        base_ok = t["base"] == kind or BASES[t["base"]][0] == kind
        lay = (t.get("style") or {}).get("layout")
        cam_ok = not lay or det.get("camera") in (None, "unknown", lay)
        if base_ok and cam_ok or (lay and det.get("camera") == lay and det.get("confidence") == "low"):
            out.append({"slug": t["slug"], "name": t["name"], "base": t["base"], "layout": lay})   # layout: New Project only picks a style that clearly fits
    return out


def create_settings(slug):
    """New Project with a custom type: (store type, settings to start the project with)."""
    t = load_type(slug)
    vtype, base = BASES[t["base"]]
    eff = effective_settings(t)
    return vtype, {**base, **eff, "my_type": t["slug"], "_style": eff}


def sync(doc, save=True):
    """Before a build: the type's current settings (style + every learned rule) go into the project. A setting the user
    changed on this project by hand (not what the type put there last time) stays as they set it. settings._style = what
    the type applied. Writes <project>/_style/rules.md for Claude."""
    t = type_of(doc)
    if not t:
        return doc
    s = doc.setdefault("settings", {})
    eff = effective_settings(t)
    applied = dict(s.get("_style") or {})
    hand = {k for k in s if k in applied and s[k] != applied[k]}
    for k in applied:
        if k not in eff and k in s and k not in hand:   # a removed rule: its setting goes too
            s.pop(k, None)
    for k, v in eff.items():
        if k not in hand and (k not in s or k in applied):
            s[k] = v
    s.update({k: v for k, v in BASES[t["base"]][1].items() if k not in s})
    s["_style"] = {k: v for k, v in eff.items() if k not in hand}
    try:
        d = Path(doc["path"]) / "_style"
        d.mkdir(exist_ok=True)
        (d / "rules.md").write_text(brief(t), encoding="utf-8")
    except OSError:
        pass
    if save:
        store.save(doc)
    return doc


def brief(t):
    """The type in words: playbook + learned rules (what Claude reads before revising or directing a video of this type)."""
    parts = [f"# Video type: {t['name']} (built on the {BASE_LABELS.get(t['base'], t['base'])} pipeline)"]
    pb = playbook(t["slug"])
    if pb:
        parts.append(pb.strip())
    rt = rules_text(t)
    if rt:
        parts.append("## Rules learned from revision notes (follow them on every video of this type)\n" + rt)
    pieces = t.get("assets") or []
    if pieces:
        d = TYPES / t["slug"] / "assets"
        parts.append("## The type's own pieces (start / end / logo are added automatically by the style_pieces build step)\n" +
                     "\n".join(f"- {ROLES.get(a['role'], a['role'])}: {d / a['file']}" + (f" ({a['note']})" if a.get("note") else "")
                               for a in pieces))
    return "\n\n".join(parts) + "\n"


def env(doc):
    """Environment for every build step of a custom-type project (claude_brain reads it to put the type's brief first)."""
    t = type_of(doc)
    if not t:
        return {}
    return {"STUDIO_MY_TYPE": t["slug"], "STUDIO_MY_STYLE": str(ROOT)}


# ---------------------------------------------------------------- learning from revision notes
LEARN_PROMPT = """You keep the style rules of a video editor's custom video type "{name}" (built on the {base} pipeline).
A revision note was just written on one video of this type. Turn it into ONE rule for the whole type: a CATEGORY rule
about the kind of moment (e.g. "cut every pause longer than half a second", "no captions during the product close-ups"),
never about this one video's times, names or words. If the note only fixes a one-off mistake in this video (a wrong take,
a typo, one bad frame) answer {{"rule": null}}.

Rules the type already has:
{rules}

The note: "{note}"

Project settings you may set when the rule maps onto one (leave "settings" empty otherwise):
{keys}

Answer with JSON only: {{"rule": "<one sentence, imperative>", "category": "<one of {cats}>", "settings": {{...}},
"replaces": <index of an existing rule this one updates, or null>}}"""

# without Claude: the common notes as category rules (the same shapes the prompt asks for)
FALLBACK = [
    (r"\b(no|remove|without|turn off|drop)\b.*\bcaptions?\b|\bcaptions?\b.*\b(off|remove|gone)\b",
     "captions", "No captions on this type of video.", {"captions": {"on": False}}),
    (r"\b(add|want|need|turn on)\b.*\bcaptions?\b", "captions", "Burn captions into every video of this type.", {"captions": {"on": True}}),
    (r"\b(no|remove|without|drop)\b.*\bmusic\b", "music", "No music bed on this type of video.", {"music": False}),
    (r"\bmusic\b.*\b(too loud|lower|quieter|softer|down)\b", "music", "Keep the music bed quieter under the voice.", {"music_bed_lufs": -38.0}),
    (r"\bmusic\b.*\b(louder|up|more)\b", "music", "Make the music bed louder.", {"music_bed_lufs": -30.0}),
    (r"\b(pauses?|gaps?|dead air|silence|faster|tighter|too slow|drag)\b", "pauses", "Cut pauses tight: jump-cut pacing.", {"pauses": "tight"}),
    (r"\b(too (fast|choppy|tight)|breathe|let it breathe|keep (the )?pauses)\b", "pauses", "Keep natural pauses; don't over-tighten.", {"pauses": "natural"}),
    (r"\b(no|remove|too many|less)\b.*\bzooms?\b", "zooms", "Fewer zooms: only punch in on key moments.", {"short_zoom": False}),
    (r"\b(turn|look)s?\b.*\b(other|side) (camera|angle)\b|\bwhen i turn\b", "camera",
     "When the speaker turns their head, cut to the other angle.", {"turn_follow": "cut"}),
    (r"\b(no|remove|without)\b.*\b(transition|wipe|whoosh)s?\b", "transitions", "No transition graphics or whooshes between sections.",
     {"wipe": "off", "wipe_sfx": "off"}),
    (r"\b(filler|um+|uh+|like,)\b", "pacing", "Cut filler words hard.", {"fillers": "heavy"}),
]


def _ask_claude(prompt, timeout=180):
    try:
        import extras2
        return extras2.ask_once(prompt, timeout=timeout)
    except Exception:  # noqa: no Claude, no sign-in: the fallback rules
        return None


def learn(doc, note):
    """A revision note on a custom-type project -> a category rule in the type's file. Returns the rule (or None)."""
    t = type_of(doc)
    text = (note or {}).get("text", "").strip()
    if not t or not text or (note or {}).get("from") == "editor":
        return None
    rule = None
    out = _ask_claude(LEARN_PROMPT.format(name=t["name"], base=BASE_LABELS.get(t["base"], t["base"]), note=text,
                                          rules="\n".join(f"{i}. [{r.get('category')}] {r['text']}" for i, r in enumerate(t["rules"])) or "(none yet)",
                                          keys="\n".join(f"- {k}: {v}" for k, v in SETTING_KEYS.items()), cats=" | ".join(CATEGORIES)))
    if out:
        m = re.search(r"\{.*\}", out, re.S)
        try:
            j = json.loads(m.group(0)) if m else None
        except ValueError:
            j = None
        if j is not None:
            if not j.get("rule"):
                return None
            rule = {"text": str(j["rule"])[:300], "category": j.get("category") if j.get("category") in CATEGORIES else "other",
                    "settings": {k: v for k, v in (j.get("settings") or {}).items() if k in SETTING_KEYS},
                    "replaces": j.get("replaces"), "how": "claude"}
    if rule is None:
        low = text.lower()
        for rx, cat, rtext, sett in FALLBACK:
            if re.search(rx, low):
                rule = {"text": rtext, "category": cat, "settings": dict(sett), "replaces": None, "how": "pattern"}
                break
    if rule is None:
        return None
    return add_rule(t["slug"], rule, nid=note.get("nid"))


def add_rule(slug, rule, nid=None):
    with _LOCK:
        t = load_type(slug)
        rules = t.setdefault("rules", [])
        rep = rule.pop("replaces", None)
        same = next((r for r in rules if r.get("category") == rule.get("category") and r.get("settings") and r.get("settings") == rule.get("settings")), None)
        if isinstance(rep, int) and 0 <= rep < len(rules):
            same = rules[rep]
        if same:   # the same lesson again: one rule, seen more often (and worded the newer way)
            same.update(text=rule["text"], settings=rule.get("settings") or same.get("settings") or {}, seen=same.get("seen", 1) + 1,
                        how=rule.get("how") or same.get("how"),
                        last=time.strftime("%Y-%m-%d %H:%M"))
            same.pop("off", None)
            r = same
        else:
            r = {"id": os.urandom(3).hex(), "added": time.strftime("%Y-%m-%d %H:%M"), "seen": 1, **rule}
            rules.append(r)
        if nid:
            r.setdefault("notes", [])
            if nid not in r["notes"]:
                r["notes"].append(nid)
        t["updated"] = time.strftime("%Y-%m-%d %H:%M")
        _write(TYPES / f"{t['slug']}.json", t)
    return r


def remove_rule(slug, rid):
    with _LOCK:
        t = load_type(slug)
        t["rules"] = [r for r in t.get("rules") or [] if r.get("id") != rid]
        _write(TYPES / f"{t['slug']}.json", t)
    return t


def learn_async(doc, note):
    threading.Thread(target=lambda: _safe(learn, doc, note), daemon=True, name="my-style-learn").start()


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception as e:  # noqa: learning never breaks a note
        print(f"my_style: {fn.__name__} failed: {type(e).__name__}: {e}")


def record_rule_note(doc, note):
    """A note marked "rule" on any project: kept in my_style/rules.json (category rules, survives updates)."""
    if (note or {}).get("applies") != "rule" or not note.get("text"):
        return
    with _LOCK:
        d = _read(RULES, {"rules": []})
        if any(r.get("nid") == note.get("nid") for r in d["rules"]):
            return
        d["rules"].append({"nid": note.get("nid"), "type": doc.get("type"), "my_type": (doc.get("settings") or {}).get("my_type"),
                           "text": note["text"][:400], "added": time.strftime("%Y-%m-%d %H:%M")})
        _write(RULES, d)


# ---------------------------------------------------------------- anonymous summary (for the edit-stats sender)
def type_summary():
    """Non-personal settings of every custom type: no names, words, rule text or file paths."""
    out = []
    for t in list_types():
        st = t.get("style") or {}
        pace = st.get("pace") or {}
        eff = effective_settings(t)
        cap = eff.get("captions") if isinstance(eff.get("captions"), dict) else {}
        out.append({
            "base": t.get("base"),
            "layout": st.get("layout") if st.get("layout") in LAYOUTS else None,
            "pace": {k: (round(float(pace[k]), 2) if isinstance(pace.get(k), (int, float)) else None)
                     for k in ("avg_shot_s", "cuts_per_min", "pauses_per_min", "median_pause_s")},
            "tightness": pace.get("tightness") if pace.get("tightness") in ("tight", "natural", "loose") else None,
            "captions_on": bool(cap.get("on")) if cap else None,
            "music_on": eff.get("music") is not False,
            "music_mood": eff.get("music_mood") if eff.get("music_mood") in ("chill", "upbeat", "hype", "dark", "cinematic", "lo-fi") else None,
            "rules": len([r for r in t.get("rules") or [] if not r.get("off")]),
            "examples": int(t.get("examples") or 0),
        })
    return out


# ---------------------------------------------------------------- the New video type wizard (analysis runs in tools/style_learn.py)
def _status_path(job):
    return WORK / job / "status.json"


KINDS = ("finished", "raw", "reference", "project", "asset")


def guess_kind(path):
    """What a dropped file most likely is (the Train screen shows it and lets the user change it)."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext in (".prproj", ".wfp", ".fcpxml", ".xml", ".edl", ".otio", ".kdenlive", ".mlt", ".drp", ".drt", ".veg") or \
            p.name.lower() in ("draft_content.json", "draft_info.json"):
        return "project"
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp3", ".wav", ".m4a", ".flac", ".ttf", ".otf"):
        return "asset"
    return "finished"


def past_projects():
    """Studio projects with a render to learn from (newest first): [{id, title, type, file, kind, notes}]."""
    out = []
    for d in store.all_projects():
        rs = [r for r in d.get("renders") or [] if r.get("path") and os.path.exists(r["path"])]
        best = next((r for r in reversed(rs) if r.get("kind") == "final"), None) or (rs[-1] if rs else None)
        if best:
            out.append({"id": d["id"], "title": d.get("title"), "type": d.get("type"), "my_type": (d.get("settings") or {}).get("my_type"),
                        "file": best["path"], "kind": best.get("kind"),
                        "notes": len([n for n in d.get("notes") or [] if n.get("kind") == "text"])})
    return out[:80]


def start_analysis(name, base, items=None, past=None, wishes="", opening_text="", slug=None, examples=None, raw=None, links=None):
    """Train: a name + what the videos are closest to + anything the user drops (items: [{path, kind, note, role}]),
    projects already made in the Studio (ids: their render is a finished example, their notes become rules), wishes in
    their own words, an opening text card. slug = teach an existing type more."""
    if slug:
        t0 = load_type(slug)
        name, base = t0["name"], t0["base"]
    # "auto" (2026-11-04, testers don't know which type they make): style_learn works it out from what it sees, name too
    if base != "auto" and base not in BASES:
        raise ValueError("pick what your videos are closest to")
    links = [str(u).strip() for u in links or [] if str(u).strip()]
    items = [dict(i) for i in items or [] if i and i.get("path")]
    items += [{"path": p, "kind": "finished"} for p in examples or [] if p] + ([{"path": raw, "kind": "raw"}] if raw else [])
    for i in items:
        if not os.path.isfile(i["path"]):
            raise ValueError(f"file not found: {i['path']}")
        if i.get("kind") not in KINDS:
            i["kind"] = guess_kind(i["path"])
    past_notes = []
    known = {p["id"]: p for p in past_projects()} if past else {}
    for pid in past or []:
        d = store.load(pid)
        if not d:
            continue
        if pid in known and len([i for i in items if i["kind"] == "finished"]) < 5:
            items.append({"path": known[pid]["file"], "kind": "finished", "from_project": d.get("title")})
        past_notes += [n["text"] for n in d.get("notes") or [] if n.get("kind") == "text" and n.get("text") and n.get("from") != "editor"]
    if len([i for i in items if i["kind"] == "finished"]) > 5:
        raise ValueError("5 finished videos are plenty: take a few out")
    if not (items or links or past_notes or (wishes or "").strip() or (opening_text or "").strip()):
        raise ValueError("give it something to learn from: a finished video, a project file, a past project or a few words")
    job = f"{slugify(name or 'style')}-{time.strftime('%H%M%S')}"
    d = WORK / job
    d.mkdir(parents=True, exist_ok=True)
    _write(d / "request.json", {"name": name, "base": base, "items": items, "links": links, "past_notes": past_notes[:60], "wishes": wishes or "",
                                "opening_text": opening_text or "", "slug": slug or ""})
    _write(_status_path(job), {"state": "running", "step": "starting", "pct": 0})
    py = store.settings().get("python") or sys.executable
    subprocess.Popen([py, "-X", "utf8", str(APP / "tools" / "style_learn.py"), str(d)], cwd=str(APP),
                     creationflags=CREATE_NO_WINDOW, stdin=subprocess.DEVNULL,
                     stdout=open(d / "log.txt", "w", encoding="utf-8"), stderr=subprocess.STDOUT)
    return {"job": job}


# ---------------------------------------------------------------- API
def api_types(q, body):
    return {"types": [dict(t, playbook=playbook(t["slug"])) for t in list_types()], "bases": BASE_LABELS, "root": str(ROOT),
            "categories": CATEGORIES, "roles": ROLES}


def api_type(q, body):
    t = load_type(q.get("slug") or body.get("slug"))
    if body.get("delete"):
        delete_type(t["slug"])
        return {"deleted": t["slug"]}
    if body.get("remove_rule"):
        t = remove_rule(t["slug"], body["remove_rule"])
    if body.get("add_rule"):
        add_rule(t["slug"], {"text": str(body["add_rule"])[:300], "category": body.get("category") if body.get("category") in CATEGORIES else "other",
                             "settings": {k: v for k, v in (body.get("settings") or {}).items() if k in SETTING_KEYS}, "how": "by hand"})
        t = load_type(t["slug"])
    if body.get("name"):
        t["name"] = str(body["name"])[:60]
        save_type(t)
    if body.get("playbook") is not None:
        (TYPES / f"{t['slug']}.md").write_text(str(body["playbook"]), encoding="utf-8")
    return dict(t, playbook=playbook(t["slug"]), effective=effective_settings(t))


def api_wizard_start(q, body):
    return start_analysis((body.get("name") or "").strip(), body.get("base") or "auto", body.get("items"), body.get("past"),
                          body.get("wishes") or "", body.get("opening_text") or "", body.get("slug") or None,
                          body.get("examples"), body.get("raw") or None, body.get("links"))


def api_past(q, body):
    return {"projects": past_projects()}


def api_guess(q, body):
    """Dropped files: what each one is; a project file is opened right away, so "export it from Resolve first" shows at once."""
    out = []
    for p in body.get("paths") or []:
        it = {"path": p, "kind": guess_kind(p)}
        if it["kind"] == "project":
            try:
                sys.path.insert(0, str(APP / "tools"))
                import project_import
                pj = project_import.read(p)
                it["info"] = f"{pj['tool']}: {pj['clips']} clips" + (f", a cut every {pj['avg_clip_s']} s" if pj.get("avg_clip_s") else "")
            except Exception as e:  # noqa: the reason is the message
                it["warn"] = str(e)
        out.append(it)
    return {"items": out}


def api_asset(q, body):
    slug = body.get("slug")
    if body.get("remove"):
        return remove_asset(slug, body["remove"])
    if body.get("role") and body.get("file"):   # change a piece's role
        with _LOCK:
            t = load_type(slug)
            for a in t.get("assets") or []:
                if a["file"] == body["file"]:
                    a["role"] = body["role"] if body["role"] in ROLES else "use"
            _write(TYPES / f"{t['slug']}.json", t)
        return t
    if body.get("path"):
        return add_asset(slug, body["path"], body.get("role") or "use", body.get("dur"), body.get("note") or "")
    raise ValueError("nothing to do")


def api_wizard_status(q, body):
    st = _read(_status_path(q.get("job", "")), None)
    if st is None:
        raise ValueError("no such analysis")
    return st


def api_summary(q, body):
    return {"types": type_summary()}


ROUTES = {
    ("GET", "mystyle/types"): api_types,
    ("GET", "mystyle/type"): api_type,
    ("POST", "mystyle/type"): api_type,
    ("POST", "mystyle/wizard"): api_wizard_start,
    ("GET", "mystyle/wizard"): api_wizard_status,
    ("GET", "mystyle/summary"): api_summary,
    ("GET", "mystyle/past"): api_past,
    ("POST", "mystyle/guess"): api_guess,
    ("POST", "mystyle/asset"): api_asset,
}

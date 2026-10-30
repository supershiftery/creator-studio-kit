"""Caption word fixes (user 2026-10-29, a friend testing the kit: "best Cobblemont server on Bedrock" was burned in as heard).
Runs on the Whisper words right before a caption renderer lays them out (captions.py run, trim_render.py, haul_render.py):

1. AI typo pass: Claude (claude_brain.ask, the AI director's path) reads the words with the project's title, type, channel and
   vocabulary and returns ONLY real fixes: misheard names ("Cobblemont" -> "Cobblemon", "better Rock" -> "Bedrock") and words
   that don't exist. Never a rewording, grammar fix or filler cut. Guarded here too (a fix must look/sound like the old
   word or be a project name). Off with settings.captions.ai_fix = false or the AI director off (settings.claude = false).
2. Manual fixes from the editor: studio.json "caption_fixes" (POST project/caption-fix). {t, old, new, all}: the word(s)
   matching `old` nearest draft time t (within 3 s), or every occurrence when all = true. Applied after the AI pass, so
   `old` is what the user saw in the draft. Studio.json (not _captions) because it travels to the laptop with the project.
3. Undo: every change is logged with an id; POST project/caption-fix {"undo": id} drops a manual fix or puts the AI pair
   on studio.json "caption_ai_reject" so the AI never makes it again ({"allow": id} takes that back).

Word timings are kept (a fix spanning several words takes their whole span, split by length). What was shown is written to
<project>/captions.json (per video name: words, caption groups, changes) for the editor (GET project/captions)."""
import difflib
import hashlib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, r"{{KIT}}/tools")
APP = Path(__file__).resolve().parents[1]
SHOWN = "captions.json"


def norm(w):
    return re.sub(r"[^\w]", "", w.lower())


def _tail(w):
    m = re.search(r"[.,!?;:]+$", w)
    return m.group(0) if m else ""


def _replace(words, i, n, new):
    """words[i:i+n] -> the words of `new`, spread over their time span by length; keeps the old trailing punctuation"""
    old = words[i:i + n]
    toks = new.split() or [new]
    tail = _tail(old[-1]["w"])
    if tail and not _tail(toks[-1]):
        toks[-1] += tail
    s, e = old[0]["s"], old[-1]["e"]
    tot = sum(len(t) for t in toks) or 1
    out, at = [], s
    for t in toks:
        d = (e - s) * len(t) / tot
        out.append({**old[0], "w": t, "s": round(at, 3), "e": round(at + d, 3)})
        at += d
    out[-1]["e"] = e
    return words[:i] + out + words[i + n:]


def _find(words, old, lo=0, hi=None):
    """start indexes where the words spell `old` (punctuation / case ignored; "cobble mon" also matches "cobblemon")"""
    target = norm(old.replace(" ", ""))
    hi = len(words) if hi is None else hi
    hits = []
    for i in range(max(0, lo), min(len(words), hi)):
        acc = ""
        for n in range(1, 5):
            if i + n > len(words):
                break
            acc += norm(words[i + n - 1]["w"])
            if acc == target:
                hits.append((i, n))
                break
            if not target.startswith(acc):
                break
    return hits


def fix_id(source, old, new):
    return f"{source}:{norm(old.replace(' ', ''))}>{re.sub(r'[.,!?;:]+$', '', new.strip())}"


# ---------------------------------------------------------------- manual fixes
def apply_manual(words, fixes, changes):
    for f in fixes or []:
        old, new = (f.get("old") or "").strip(), (f.get("new") or "").strip()
        if not old or not new:
            continue
        hits = _find(words, old)
        if not f.get("all"):
            t = f.get("t")
            hits = sorted((h for h in hits if t is None or abs(words[h[0]]["s"] - float(t)) <= 3.0),
                          key=lambda h: abs(words[h[0]]["s"] - float(t or 0)))[:1]
        for i, n in reversed(hits):   # from the end so earlier indexes stay valid
            s, was = words[i]["s"], " ".join(x["w"] for x in words[i:i + n])
            words = _replace(words, i, n, new)
            changes.append({"id": f.get("id") or fix_id("manual", old, new), "source": "manual", "s": s, "old": was, "new": new})
    return words


# ---------------------------------------------------------------- AI typo pass
PROMPT = """You check burned-in video captions made by speech-to-text (Whisper) for misheard words.
Video: "{title}" ({vtype} video{channel}). Names that belong to this video: {vocab}.

Below is the transcript. Every line starts with the number of its first word in [brackets]; count on from there.
Find ONLY real transcription mistakes:
- a name, brand, game, mod, server or product heard wrong or split up ("Cobblemont" -> "Cobblemon", "cobble mon" -> "Cobblemon",
  "better Rock" -> "Bedrock" in "Minecraft better Rock"),
- a word that does not exist or makes no sense where it is and clearly sounds like the right word.
NEVER reword, rephrase, fix grammar, change slang ("gonna", "ya"), remove filler words or repeats, or change numbers that could
be right. Lowercase names are fine to capitalise only as part of a real fix. When unsure, leave it out.

Return JSON only: {{"fixes": [{{"i": <number of the first wrong word>, "n": <how many words it replaces, usually 1>,
"old": "<the wrong words exactly as written>", "new": "<the right text>", "why": "<3-6 words>"}}]}}  (empty list = nothing to fix)

{text}"""


def _lines(words, i0, i1, per=12):
    return "\n".join(f"[{i}] " + " ".join(x["w"] for x in words[i:min(i + per, i1)]) for i in range(i0, i1, per))


def _sane(old, new, terms):
    """a real fix looks or sounds like the old words, or is one of the video's own names; never a rewrite"""
    a, b = norm(old.replace(" ", "")), norm(new.replace(" ", ""))
    if not a or not b or a == b and old.strip() == new.strip():
        return False
    if len(new.split()) > len(old.split()) + 1:
        return False
    if b in terms or any(b in t or t in b for t in terms if len(t) >= 5):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.5


def ai_pass(words, doc, changes, say=print, chunk=500):
    S = doc.get("settings") or {}
    cap = S.get("captions") if isinstance(S.get("captions"), dict) else {}
    if not words or cap.get("ai_fix") is False or S.get("claude") is False:
        return words
    try:
        import claude_brain as B
    except Exception as e:  # noqa
        say(f"caption typo pass skipped ({type(e).__name__})")
        return words
    vocab = [v for v in (S.get("vocabulary") or []) if v]
    terms = {norm(t) for t in vocab + re.findall(r"[A-Za-z][\w'-]{3,}", doc.get("title") or "")}
    reject = {r.lower() for r in doc.get("caption_ai_reject") or []}
    ch = doc.get("channel") or ""
    found = []
    for i0 in range(0, len(words), chunk):
        i1 = min(len(words), i0 + chunk)
        prompt = PROMPT.format(title=doc.get("title") or "", vtype=doc.get("type") or "", channel=f", channel {ch}" if ch else "",
                               vocab=", ".join(vocab) or "(none listed)", text=_lines(words, i0, i1))
        ans = B.ask("caption_typos", prompt, model="sonnet", timeout=180, say=say)
        for f in (ans or {}).get("fixes", []) if isinstance(ans, dict) else []:
            try:
                i, old, new = int(f.get("i")), str(f.get("old") or "").strip(), str(f.get("new") or "").strip()
            except (TypeError, ValueError):
                continue
            hits = _find(words, old, i - 8, i + 9)   # the model's count can be a few words off
            if not hits or not _sane(old, new, terms) or fix_id("ai", old, new).lower() in reject:
                continue
            j, n = min(hits, key=lambda h: abs(h[0] - i))
            found.append((j, n, new, f.get("why") or ""))
    for j, n, new, why in sorted(set(found), key=lambda x: -x[0]):   # from the end: indexes stay valid
        was = " ".join(x["w"] for x in words[j:j + n])
        if norm(was.replace(" ", "")) == norm(new.replace(" ", "")) and was.split()[0][:1].isupper():
            continue   # only a case change on an already capitalised word
        s = words[j]["s"]
        words = _replace(words, j, n, new)
        changes.append({"id": fix_id("ai", was, new), "source": "ai", "s": s, "old": was, "new": new, "why": why})
    if found:
        say(f"captions: AI typo pass fixed {sum(c['source'] == 'ai' for c in changes)} words: "
            + ", ".join(f"{c['old']} -> {c['new']}" for c in changes if c["source"] == "ai")[:400])
    return words


def apply(words, doc, say=print):
    """the fixed words + the change log; words are never edited in place"""
    words = [dict(w) for w in words]
    changes = []
    words = ai_pass(words, doc, changes, say=say)
    words = apply_manual(words, doc.get("caption_fixes"), changes)
    changes.sort(key=lambda c: c["s"])
    return words, changes


def signature(doc):
    """changes when the user's fixes / rejects / AI setting change: a burned render must then be redone"""
    S = doc.get("settings") or {}
    cap = S.get("captions") if isinstance(S.get("captions"), dict) else {}
    return hashlib.md5(json.dumps([doc.get("caption_fixes") or [], doc.get("caption_ai_reject") or [], cap.get("ai_fix"),
                                   S.get("claude")], sort_keys=True).encode()).hexdigest()[:12]


def record(proj, video_name, words, groups, changes, style, offset=0.0):
    """<project>/captions.json[video_name] = what the editor draws: words + caption groups in that video's own time"""
    f = Path(proj) / SHOWN
    try:
        allv = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except ValueError:
        allv = {}
    sh = lambda t: round(t + offset, 3)   # noqa: E731
    allv[video_name] = {"style": style, "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "words": [{"w": w["w"], "s": sh(w["s"]), "e": sh(w["e"])} for w in words],
                        "groups": [{**g, "s": sh(g["s"]), "e": sh(g["e"])} for g in groups],
                        "changes": [{**c, "s": sh(c["s"])} for c in changes]}
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(allv, ensure_ascii=False), encoding="utf-8")
    tmp.replace(f)


# ---------------------------------------------------------------- API (server.py ROUTES)
def _store():
    sys.path.insert(0, str(APP))
    import store
    return store


def api_get(q, body):
    """GET project/caption-fix?id= -> manual fixes, AI rejects; GET project/captions?id=[&video=] -> shown words + groups"""
    store = _store()
    doc = store.load(q.get("id", ""))
    if not doc:
        raise ValueError("no such project")
    return {"fixes": doc.get("caption_fixes") or [], "ai_reject": doc.get("caption_ai_reject") or []}


def api_captions(q, body):
    store = _store()
    doc = store.load(q.get("id", ""))
    if not doc:
        raise ValueError("no such project")
    f = Path(doc["path"]) / SHOWN
    allv = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    v = q.get("video")
    if v:
        return {"video": v, **(allv.get(v) or {"words": [], "groups": [], "changes": []})}
    return {"videos": {k: {"style": x.get("style"), "at": x.get("at"), "words": len(x.get("words", [])),
                           "changes": x.get("changes", [])} for k, x in allv.items()}}


def api_post(q, body):
    """POST project/caption-fix?id= {old, new, t?, all?} add | {undo: id} drop a manual fix / reject an AI fix |
    {remove: id} drop a manual fix | {allow: id} let an undone AI fix happen again. Applies on the next build's captions."""
    store = _store()
    doc = store.load(q.get("id", ""))
    if not doc:
        raise ValueError("no such project")
    body = body or {}
    fixes = list(doc.get("caption_fixes") or [])
    rej = list(doc.get("caption_ai_reject") or [])
    uid = body.get("undo") or body.get("remove")
    if body.get("allow"):   # take an undone AI fix back (the AI may make it again)
        rej = [r for r in rej if r != body["allow"]]
    elif uid:
        if uid.startswith("ai:"):
            if uid not in rej:
                rej.append(uid)
        else:
            fixes = [f for f in fixes if f.get("id") != uid]
    else:
        old, new = str(body.get("old") or "").strip(), str(body.get("new") or "").strip()
        if not old or not new or old == new:
            raise ValueError("need old and new text")
        t = body.get("t")
        f = {"id": f"manual:{int(time.time() * 1000)}", "old": old, "new": new, "all": bool(body.get("all")),
             "t": None if t is None else round(float(t), 2), "added": time.strftime("%Y-%m-%d %H:%M:%S")}
        if body.get("video"):
            f["video"] = body["video"]
        fixes = [x for x in fixes if not (norm(x["old"]) == norm(old) and x.get("t") == f["t"] and x.get("all") == f["all"])] + [f]
    doc["caption_fixes"], doc["caption_ai_reject"] = fixes, rej
    store.save(doc)
    return {"ok": True, "fixes": fixes, "ai_reject": rej, "applies": "on the next build's captions"}


ROUTES = {("GET", "project/caption-fix"): api_get, ("POST", "project/caption-fix"): api_post,
          ("GET", "project/captions"): api_captions}


if __name__ == "__main__":   # python caption_fixes.py <project dir> <words.json> [i0 i1]: dry run, prints the changes
    proj, wf = Path(sys.argv[1]), sys.argv[2]
    doc = json.loads((proj / "studio.json").read_text(encoding="utf-8"))
    ws = json.loads(Path(wf).read_text(encoding="utf-8"))
    ws = ws["words"] if isinstance(ws, dict) else ws
    if len(sys.argv) > 4:
        ws = ws[int(sys.argv[3]):int(sys.argv[4])]
    _, ch = apply(ws, doc)
    print(json.dumps(ch, indent=1, ensure_ascii=False))

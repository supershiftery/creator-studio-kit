"""Creator tools (overnight build 2026-10-29, user: "build out new tools that you think YouTubers would actually have a benefit
from ... speed up their work, get video ideas and overall make their life easier").

Channel tools tiles -> ui/creator_tools.js. Two kinds:

  Competitor insights (no AI, instant): read the competitor tracker's data (tracker_data.json, the laptop's copy when newer)
    insights(niche, days)  what's working: title words / title styles that beat the channel's usual views, outliers on topics
                           you haven't made yet ("gaps"), and the tracked channels table (who is heating up)
  Claude tools (background jobs, ~30-90 s each, cached by claude_brain so the same input never costs twice):
    title_lab      a topic -> 10 titles scored against what wins in the niche + thumbnail text + thumbnail concepts
    brainstorm     a niche/channel -> 10 video ideas from this month's outliers, gaps and your own past titles
    comment_miner  a YouTube link -> the top ~300 comments read for questions, requests, complaints = video ideas
    hook_doctor    a project -> its opening (first 45 s of the transcript) graded, with problems and a rewritten hook
    repurpose      a project -> community post, pinned comment, X thread, Short ideas with times, TikTok caption

Every finished job is saved in data/creator_tools/<id>.json (History in the UI).

    GET  tools/insights?niche=&days=     GET  tools/meta (niches, channels, projects with a transcript)
    POST tools/run {tool, input} -> {id}  GET  tools/job?id=   GET tools/history   POST tools/forget {id}
"""
import json
import math
import re
import subprocess
import sys
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path

import store

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
OUT = DATA / "creator_tools"
BOT_DIR = Path(r"{{KIT}}")
TRACKERS = [BOT_DIR / "tracker_data.json", DATA / "tracker_data_laptop.json"]
TOOLS_DIR = Path(r"{{KIT}}/tools")
DAY = 86400
NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
JOBS = {}
LOCK = threading.Lock()
STOP = set("""a an the and or but of to in on for with my your our is are was be this that it its i me we you how what why
when who vs at by from as so do does did not no yes all any one new get got just than then there here up out about into
over more most very really can will would should could have has had s t video videos""".split())
FILLERS = {"um", "uh", "erm", "like", "basically", "literally", "actually", "so", "yeah", "okay", "ok", "right"}


# ------------------------------------------------------------------ tracker data (cached by file time)
_TD = {"key": None, "data": None}


def _hidden():
    """what he hid on the Competitors page (ideas.hide): those never count here either"""
    try:
        h = json.loads((DATA / "competitors_hidden.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set(), set()
    return set(h.get("videos") or []), set(h.get("channels") or [])


def tracker():
    """the newest competitor tracker data (desktop or laptop copy), parsed once per file change, minus what he hid"""
    d = _tracker()
    hv, hc = _hidden()
    if not hv and not hc:
        return d
    return dict(d, videos={k: v for k, v in d.get("videos", {}).items() if k not in hv and v.get("channel_id") not in hc},
                channels={k: v for k, v in d.get("channels", {}).items() if k not in hc})


def _tracker():
    best, key = None, None
    for f in TRACKERS:
        try:
            m = f.stat().st_mtime
        except OSError:
            continue
        if best is None or m > key[1]:
            best, key = f, (str(f), m)
    if best is None:
        return {"videos": {}, "channels": {}, "outliers": {}}
    if _TD["key"] != key:
        try:
            _TD.update(key=key, data=json.loads(best.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return _TD["data"] or {"videos": {}, "channels": {}, "outliers": {}}
    return _TD["data"]


def terms(title):
    """the words (and two-word phrases) of a title that carry meaning"""
    # plain numbers and versions ("2026", "26", "1.21") say nothing about the topic
    toks = [t for t in re.findall(r"[a-z0-9$]+(?:'[a-z]+)?", title.lower()) if t not in STOP and len(t) > 1 and not t.isdigit()]
    return set(toks) | {f"{a} {b}" for a, b in zip(toks, toks[1:])}


STYLES = [
    ("Number in the title", lambda t: bool(re.search(r"\d", t))),
    ("A price ($)", lambda t: "$" in t),
    ("A question", lambda t: "?" in t),
    ("A WORD IN CAPS", lambda t: bool(re.search(r"\b[A-Z]{3,}\b", t))),
    ("Speaks as I / my", lambda t: bool(re.search(r"\b(i|i'm|my|me)\b", t.lower()))),
    ("Top N list", lambda t: bool(re.search(r"\btop\s*\d+", t, re.I))),
    ("Versus (vs)", lambda t: bool(re.search(r"\bvs\.?\b|\bversus\b", t, re.I))),
    ("Short (under 40 letters)", lambda t: len(t) < 40),
    ("Long (over 70 letters)", lambda t: len(t) > 70),
    ("Brackets ( ) or [ ]", lambda t: bool(re.search(r"[\(\[]", t))),
    ("Emoji", lambda t: bool(re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", t))),
    ("Says 'worth it' / 'scam' / 'legit'", lambda t: bool(re.search(r"worth it|scam|legit|fake|real or", t, re.I))),
]


def _mine_titles():
    out = []
    for d in store.all_projects():
        out.append(d.get("title", ""))
    return out


def insights(niche="", days=90):
    """what wins in a niche: title words + title styles by how far they beat each channel's usual views"""
    data = tracker()
    now = time.time()
    vids, chans, outl = data.get("videos", {}), data.get("channels", {}), data.get("outliers", {}) or {}
    rows = []
    for vid, v in vids.items():
        if v.get("kind", "long") != "long" or (niche and v.get("niche") != niche):
            continue
        pub = v.get("published") or v.get("first_seen")
        if not pub or now - pub > days * DAY:
            continue
        ch = chans.get(v.get("channel_id"), {})
        med = ch.get("median") or 0
        if not med or not v.get("views"):
            continue
        rows.append({"id": vid, "title": v.get("title", ""), "views": v["views"], "x": v["views"] / med, "channel": ch.get("name", ""),
                     "subs": ch.get("subs"), "pub": pub, "outlier": vid in outl, "niche": v.get("niche")})
    base = math.exp(sum(math.log(max(r["x"], 0.01)) for r in rows) / len(rows)) if rows else 1
    # title words: geometric mean of "times usual" for videos with the word, against the niche as a whole
    by = defaultdict(list)
    for r in rows:
        for t in terms(r["title"]):
            by[t].append(r)
    words = []
    need = max(4, len(rows) // 60)
    for t, rs in by.items():
        chans_n = len({r["channel"] for r in rs})
        if len(rs) < need or chans_n < 2:   # one channel's habit isn't a pattern
            continue
        g = math.exp(sum(math.log(max(r["x"], 0.01)) for r in rs) / len(rs)) / base
        words.append({"term": t, "lift": round(g, 2), "videos": len(rs), "channels": chans_n,
                      "outliers": sum(r["outlier"] for r in rs), "example": max(rs, key=lambda r: r["x"])["title"]})
    # drop a single word when its two-word phrase says the same with the same videos
    pairs = {(w["videos"], w["lift"]): w["term"] for w in words if " " in w["term"]}
    words = [w for w in words if " " in w["term"] or w["term"] not in pairs.get((w["videos"], w["lift"]), "").split()]
    words.sort(key=lambda w: (-w["lift"], -w["videos"]))
    win = [w for w in words if w["lift"] >= 1.15][:20]
    weak = sorted([w for w in words if w["lift"] <= 0.8], key=lambda w: w["lift"])[:10]
    styles = []
    for name, fn in STYLES:
        yes = [r for r in rows if fn(r["title"])]
        no = [r for r in rows if not fn(r["title"])]
        if len(yes) < 5 or len(no) < 5:
            continue
        gy = math.exp(sum(math.log(max(r["x"], 0.01)) for r in yes) / len(yes))
        gn = math.exp(sum(math.log(max(r["x"], 0.01)) for r in no) / len(no))
        styles.append({"style": name, "lift": round(gy / gn, 2), "videos": len(yes), "share": round(len(yes) / len(rows), 2)})
    styles.sort(key=lambda s: -s["lift"])
    # gaps: this month's outliers on topics none of your projects' titles share
    mine = [terms(t) for t in _mine_titles()]
    gaps = []
    for r in sorted((r for r in rows if r["outlier"] and now - r["pub"] <= 30 * DAY), key=lambda r: -r["x"]):
        tt = {t for t in terms(r["title"]) if " " not in t}
        if not tt:
            continue
        best = max((len(tt & m) / len(tt) for m in mine), default=0)
        if best < 0.34:
            gaps.append({"id": r["id"], "title": r["title"], "views": r["views"], "x": round(r["x"], 1), "channel": r["channel"],
                         "thumb": f"https://i.ytimg.com/vi/{r['id']}/mqdefault.jpg", "url": f"https://www.youtube.com/watch?v={r['id']}"})
        if len(gaps) >= 12:
            break
    return {"niche": niche, "days": days, "videos": len(rows), "channels_n": len({r["channel"] for r in rows}),
            "words": win, "weak": weak, "styles": styles, "gaps": gaps, "channels": channel_table(niche),
            "last_scan": data.get("last_scan"), "niches": sorted({v.get("niche") for v in vids.values() if v.get("niche")})}


def channel_table(niche=""):
    """the tracked channels: size, usual views, uploads + outliers in the last 30 days, heating up or cooling down"""
    data = tracker()
    now = time.time()
    vids, chans, outl = data.get("videos", {}), data.get("channels", {}), data.get("outliers", {}) or {}
    per = defaultdict(list)
    for vid, v in vids.items():
        if v.get("kind", "long") == "long":
            per[v.get("channel_id")].append((vid, v))
    out = []
    for cid, ch in chans.items():
        if niche and ch.get("niche") != niche:
            continue
        vs = per.get(cid, [])
        recent = [v for _, v in vs if (v.get("published") or 0) >= now - 30 * DAY]
        med = ch.get("median") or 0
        hot = None
        if recent and med:
            rv = sorted(v.get("views") or 0 for v in recent)
            hot = round(rv[len(rv) // 2] / med, 2)   # recent median vs the channel's usual: >1 = heating up
        last = max((v.get("published") or 0 for _, v in vs), default=0)
        out.append({"name": ch.get("name", ""), "handle": ch.get("handle", ""), "niche": ch.get("niche", ""), "subs": ch.get("subs"),
                    "median": med, "uploads30": len(recent), "outliers30": sum(1 for vid, v in vs if vid in outl and (v.get("published") or 0) >= now - 30 * DAY),
                    "trend": hot, "last_upload_days": round((now - last) / DAY, 1) if last else None,
                    "url": f"https://www.youtube.com/{ch['handle']}" if str(ch.get("handle", "")).startswith("@") else f"https://www.youtube.com/channel/{cid}"})
    out.sort(key=lambda r: (-(r["outliers30"]), -(r["trend"] or 0)))
    return out


# ------------------------------------------------------------------ Claude tools (background jobs)
def _brain():
    sys.path.insert(0, str(TOOLS_DIR))
    import claude_brain
    return claude_brain


def _doc(pid):
    d = store.load(pid or "")
    if not d:
        raise ValueError("pick a project")
    return d


def _words(doc):
    """the words as the EDITED video says them (draft times), when the project has a cut; else the raw recording's.
    Returns (words, "edit" | "raw")."""
    import extras
    words = extras.words_of(doc)
    try:
        from recipes import common, get as recipe
        P = recipe(doc["type"]).paths(doc)
        keep = common.keep_ranges(P["cuts"]) if P.get("cuts") and Path(P["cuts"]).exists() else None
    except Exception:
        keep = None
    if not keep or not words:
        return words, "raw"
    out, at = [], 0.0
    for a, b in sorted(keep):
        if a < 0 or b <= a:   # inserted clips (negative ranges) have no words of his
            continue
        for w in words:
            if a <= w["s"] < b:
                out.append({"w": w["w"], "s": at + w["s"] - a, "e": at + min(w["e"], b) - a})
        at += b - a
    return (out, "edit") if len(out) > 20 else (words, "raw")


def _fmt(t):
    t = max(0, float(t or 0))
    return f"{int(t // 60)}:{int(t % 60):02d}"


def _niche_examples(niche, n=25):
    data = tracker()
    vids, chans, outl = data.get("videos", {}), data.get("channels", {}), data.get("outliers", {}) or {}
    rows = []
    for vid in outl:
        v = vids.get(vid)
        if not v or v.get("kind", "long") != "long" or (niche and v.get("niche") != niche):
            continue
        rows.append((v.get("subs_x") or 0, v.get("title", ""), v.get("views"), chans.get(v.get("channel_id"), {}).get("name", "")))
    rows.sort(reverse=True)
    return [f"- {t}  ({v or 0:,} views, {s}x subs, {c})" for s, t, v, c in rows[:n]]


def t_title_lab(inp, say):
    topic = (inp.get("topic") or "").strip()
    if not topic:
        raise ValueError("type what the video is about")
    niche = inp.get("niche") or ""
    ins = insights(niche, 90) if niche else {"words": [], "styles": []}
    ex = _niche_examples(niche)
    say("Asking Claude for titles (about a minute)")
    prompt = f"""You are a YouTube packaging expert (titles + thumbnails). Write titles for this video.

VIDEO: {topic}
CHANNEL: {inp.get('channel') or 'unknown'}   NICHE: {niche or 'general'}
{('NOTES FROM THE CREATOR: ' + inp['notes']) if inp.get('notes') else ''}

What is winning in this niche right now (competitor outliers, views vs subscribers):
{chr(10).join(ex) or '(no tracker data for this niche)'}

Title words that beat the niche's usual views: {', '.join(f"{w['term']} ({w['lift']}x)" for w in ins['words'][:12]) or 'n/a'}
Title styles that beat it: {', '.join(f"{s['style']} ({s['lift']}x)" for s in ins['styles'][:6]) or 'n/a'}

Rules: under 60 characters when you can; curiosity without lying; no clickbait the video can't pay off; plain words a viewer
would search or click; vary the angles (result, price, mistake, comparison, challenge, story).
Answer ONLY JSON:
{{"titles": [{{"title": "...", "score": 1-10, "angle": "price|result|story|mistake|comparison|challenge|question|other", "why": "one short line"}}] (10, best first),
 "thumb_text": ["2-4 word thumbnail text", ... 6],
 "thumb_ideas": [{{"concept": "what the thumbnail shows", "why": "..."}}, ... 3],
 "avoid": ["one line on what NOT to do for this video", ... 2]}}"""
    r = _brain().ask("tool_title_lab", prompt, model="sonnet", timeout=240, say=say)
    if not r:
        raise RuntimeError("Claude didn't answer. Try again in a minute")
    return r


def t_brainstorm(inp, say):
    niche = inp.get("niche") or ""
    ins = insights(niche, 60)
    mine = [d.get("title", "") for d in sorted(store.all_projects(), key=lambda d: d.get("updated", ""), reverse=True)
            if not inp.get("channel") or d.get("channel") == inp.get("channel")][:40]
    say("Asking Claude for video ideas (about a minute)")
    prompt = f"""You are a YouTube strategist. Suggest 10 video ideas this creator should make NEXT.

CHANNEL: {inp.get('channel') or 'unknown'}   NICHE: {niche or 'general'}
{('WHAT THEY WANT: ' + inp['notes']) if inp.get('notes') else ''}

Their own recent videos (don't repeat these, but build on what they're good at):
{chr(10).join('- ' + t for t in mine) or '(none)'}

Competitor outliers in the niche (views far above the channel's normal):
{chr(10).join(_niche_examples(niche, 30)) or '(none)'}

Outliers on topics they have NOT made yet:
{chr(10).join(f"- {g['title']} ({g['views']:,} views, {g['x']}x usual, {g['channel']})" for g in ins['gaps']) or '(none)'}

Winning title words: {', '.join(w['term'] for w in ins['words'][:15]) or 'n/a'}

Each idea must be filmable by one creator this week. Prefer proven demand (an outlier exists) + a fresh angle.
Answer ONLY JSON:
{{"ideas": [{{"title": "a ready-to-use title", "hook": "the first sentence of the video", "why": "the proof it will work (name the outlier/pattern)",
  "effort": "low|medium|high", "format": "review|list|tutorial|challenge|story|comparison|other"}}] (10, best first)}}"""
    r = _brain().ask("tool_brainstorm", prompt, model="sonnet", timeout=300, say=say)
    if not r:
        raise RuntimeError("Claude didn't answer. Try again in a minute")
    return r


def _yt_id(url):
    m = re.search(r"(?:v=|youtu\.be/|shorts/|live/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else (url if re.fullmatch(r"[A-Za-z0-9_-]{11}", url or "") else None)


def t_comment_miner(inp, say):
    vid = _yt_id((inp.get("url") or "").strip())
    if not vid:
        raise ValueError("paste a YouTube video link")
    say("Reading the comments (up to 300, top first)")
    r = subprocess.run(_ytdlp() + ["--skip-download", "--write-comments", "--no-warnings", "-J",
                        "--extractor-args", "youtube:max_comments=300,all,30,0;comment_sort=top",
                        f"https://www.youtube.com/watch?v={vid}"], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=240, creationflags=NO_WINDOW)
    if r.returncode:
        raise RuntimeError("couldn't read that video: " + (r.stderr.strip().splitlines() or ["yt-dlp failed"])[-1][:200])
    info = json.loads(r.stdout)
    cm = [c for c in (info.get("comments") or []) if (c.get("text") or "").strip()]
    if not cm:
        raise RuntimeError("that video has no comments to read (or they're turned off)")
    cm.sort(key=lambda c: -(c.get("like_count") or 0))
    lines = [f"[{c.get('like_count') or 0} likes] {re.sub(r'\\s+', ' ', c['text'])[:300]}" for c in cm[:300]]
    say(f"Read {len(cm)} comments. Asking Claude what viewers want (about a minute)")
    prompt = f"""Read these YouTube comments and tell the creator what their viewers want.

VIDEO: {info.get('title')}  by {info.get('channel')}  ({info.get('view_count') or 0:,} views)

COMMENTS (most liked first):
{chr(10).join(lines)}

Answer ONLY JSON:
{{"summary": "2 sentences: the mood of the comments",
 "video_ideas": [{{"title": "a video title that answers a demand", "demand": "what viewers asked for", "count": how many comments ask this, "quote": "one real comment"}}] (up to 8, most asked first),
 "questions": [{{"question": "...", "count": n}}] (up to 8),
 "complaints": [{{"issue": "...", "count": n}}] (up to 5),
 "loved": ["what people praised", ...] (up to 5),
 "reply_to": [{{"comment": "a comment worth replying to (exact text)", "why": "..."}}] (up to 3)}}"""
    out = _brain().ask("tool_comment_miner", prompt, model="sonnet", timeout=300, say=say)
    if not out:
        raise RuntimeError("Claude didn't answer. Try again in a minute")
    out["video"] = {"title": info.get("title"), "channel": info.get("channel"), "views": info.get("view_count"),
                    "comments_read": len(cm), "url": f"https://www.youtube.com/watch?v={vid}",
                    "thumb": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"}
    return out


def opening_stats(words, title):
    """numbers about the first 45 s: words per minute, fillers, when the topic (title words) is first said"""
    first = [w for w in words if w["s"] <= 45]
    if not first:
        return {}
    span = max(1.0, first[-1]["e"] - first[0]["s"])
    toks = [re.sub(r"[^a-z0-9']", "", w["w"].lower()) for w in first]
    tt = {t for t in terms(title) if " " not in t and len(t) > 2}
    topic_at = next((w["s"] for w, t in zip(first, toks) if t in tt), None)
    return {"wpm": round(len(first) / span * 60), "fillers": sum(t in FILLERS for t in toks),
            "first_word_at": round(first[0]["s"], 1), "topic_at": round(topic_at, 1) if topic_at is not None else None,
            "words": len(first)}


def t_hook_doctor(inp, say):
    doc = _doc(inp.get("project"))
    words, src = _words(doc)
    if not words:
        raise ValueError("this project has no transcript yet (build a draft once)")
    st = opening_stats(words, doc.get("title", ""))
    st["from"] = src
    text = " ".join(f"[{_fmt(w['s'])}] {w['w']}" if i % 12 == 0 else w["w"] for i, w in enumerate(w for w in words if w["s"] <= 60))
    say("Asking Claude to grade the opening (about a minute)")
    prompt = f"""You are a YouTube retention editor. Grade this video's OPENING (the first 30-60 seconds decide if people stay).

TITLE: {doc.get('title')}
CHANNEL: {doc.get('channel') or ''}   TYPE: {doc.get('type')}
NUMBERS: {json.dumps(st)}  (wpm = words per minute; topic_at = seconds until a title word is first said)
TRANSCRIPT OF THE FIRST 60 SECONDS ({"the edited video (retakes already cut; any intro graphic plays before this)" if src == "edit" else "raw recording, not edited yet: ignore retakes, they get cut"}; [m:ss] = time):
{text}

Judge: does it confirm the title's promise fast, give a reason to stay, avoid a slow intro / channel plug / filler?
Answer ONLY JSON:
{{"grade": "A|B|C|D|F", "score": 0-100, "verdict": "one sentence",
 "works": ["what's good", ...] (up to 3),
 "problems": [{{"at": "m:ss", "issue": "what loses viewers here", "fix": "what to do"}}] (up to 5),
 "start_at": "m:ss where the video should really start (or 0:00)",
 "new_hooks": ["a rewritten first 1-2 sentences, ready to say", ... 3],
 "open_loop": "one line to tease something later in the video"}}"""
    out = _brain().ask("tool_hook_doctor", prompt, model="sonnet", timeout=240, say=say)
    if not out:
        raise RuntimeError("Claude didn't answer. Try again in a minute")
    out["stats"], out["project"] = st, {"id": doc["id"], "title": doc.get("title")}
    return out


def t_repurpose(inp, say):
    doc = _doc(inp.get("project"))
    words, src = _words(doc)
    if not words:
        raise ValueError("this project has no transcript yet (build a draft once)")
    # the whole talk, marked every ~15 words with its time, capped so a long video stays a normal-size question
    parts, last = [], -99
    for w in words:
        if w["s"] - last >= 15:
            parts.append(f"\n[{_fmt(w['s'])}]")
            last = w["s"]
        parts.append(w["w"])
    text = " ".join(parts)[:24000]
    say("Asking Claude to turn the video into posts (about a minute)")
    prompt = f"""Turn this YouTube video into ready-to-post content for other platforms. Keep the creator's voice and facts;
invent nothing that isn't in the transcript.

TITLE: {doc.get('title')}
CHANNEL: {doc.get('channel') or ''}
TRANSCRIPT ([m:ss] = time in the {"edited video, not counting the intro" if src == "edit" else "raw recording"}):
{text}

Answer ONLY JSON:
{{"community_post": "a YouTube community post (under 400 characters) that makes people watch",
 "pinned_comment": "a pinned comment that starts a conversation (a question)",
 "x_thread": ["tweet 1", "tweet 2", ...] (4-6, each under 270 characters),
 "shorts": [{{"title": "Short title", "start": "m:ss", "end": "m:ss", "why": "why this moment works alone"}}] (3-5, 20-55 s each),
 "tiktok_caption": "caption with 4-6 hashtags",
 "chapters": [{{"at": "m:ss", "title": "chapter name"}}] (4-8, first at 0:00; times are in the raw recording),
 "tags": ["search tag", ...] (10-15)}}"""
    out = _brain().ask("tool_repurpose", prompt, model="sonnet", timeout=300, say=say)
    if not out:
        raise RuntimeError("Claude didn't answer. Try again in a minute")
    out["project"] = {"id": doc["id"], "title": doc.get("title")}
    out["times"] = "edit" if src == "edit" else "raw"
    return out


def t_planner(inp, say):
    idea = (inp.get("idea") or "").strip()
    if not idea:
        raise ValueError("type the video idea or title")
    niche = inp.get("niche") or ""
    ex = _niche_examples(niche, 12)
    mine = [d.get("title", "") for d in sorted(store.all_projects(), key=lambda d: d.get("updated", ""), reverse=True)
            if not inp.get("channel") or d.get("channel") == inp.get("channel")][:12]
    say("Asking Claude for a filming plan (about a minute)")
    prompt = f"""You are a YouTube producer. Plan this video so one creator can film it today, talking to camera.

VIDEO IDEA: {idea}
CHANNEL: {inp.get('channel') or 'unknown'}   NICHE: {niche or 'general'}   TARGET LENGTH: {inp.get('length') or '8-12 minutes'}
{('NOTES: ' + inp['notes']) if inp.get('notes') else ''}
Their recent videos (match their style): {'; '.join(mine) or 'n/a'}
What wins in the niche right now:
{chr(10).join(ex) or '(no tracker data)'}

The edit adds a short motion-graphics INTRO made from a 15-25 second voice-over the creator records separately, then the
talking video. Write that voice-over too: punchy, spoken English, no "hey guys", ends by handing over to the video.
Answer ONLY JSON:
{{"title": "the best title for it", "promise": "the one thing the viewer gets, in one line",
 "intro_vo": "the 15-25 s intro voice-over script",
 "hook": "the first 2 sentences on camera, right after the intro",
 "outline": [{{"part": "part name", "minutes": approx minutes, "points": ["talking point", ...], "show": "what to show on camera"}}] (4-8 parts),
 "broll": ["a shot to film (close-up, screen recording, product detail...)", ...] (6-10),
 "thumbnail_moment": "the exact moment / pose / object to capture for the thumbnail",
 "open_loop": "something to tease early and pay off near the end",
 "ending": "how to end (call to action that fits)",
 "checklist": ["thing to prepare before filming", ...] (4-8)}}"""
    out = _brain().ask("tool_planner", prompt, model="sonnet", timeout=300, say=say)
    if not out:
        raise RuntimeError("Claude didn't answer. Try again in a minute")
    return out


def plan_md(r):
    """a Video Planner result as a plain checklist file for the project folder"""
    L = [f"# {r.get('title', '')}", "", r.get("promise", ""), "", "## Intro voice-over (record as the intro VO)", "", r.get("intro_vo", ""), "",
         "## First words on camera", "", r.get("hook", ""), "", "## Outline", ""]
    for o in r.get("outline") or []:
        L.append(f"### {o.get('part', '')} (~{o.get('minutes', '?')} min)")
        L += [f"- {x}" for x in o.get("points") or []]
        if o.get("show"):
            L.append(f"- Show: {o['show']}")
        L.append("")
    L += ["## B-roll to film", ""] + [f"- [ ] {x}" for x in r.get("broll") or []] + [""]
    L += ["## Thumbnail moment", "", r.get("thumbnail_moment", ""), "", "## Tease early, pay off later", "", r.get("open_loop", ""), "",
          "## Ending", "", r.get("ending", ""), "", "## Before you film", ""] + [f"- [ ] {x}" for x in r.get("checklist") or []]
    return "\n".join(L) + "\n"


def save_plan(pid, jid):
    """Video Planner 'Start this video': the plan goes into the new project's folder as Filming plan.md"""
    doc = _doc(pid)
    j = job(jid)
    if j.get("tool") != "planner" or not j.get("result"):
        raise ValueError("that isn't a finished plan")
    f = Path(doc["path"]) / "Filming plan.md"
    f.write_text(plan_md(j["result"]), encoding="utf-8")
    doc.setdefault("settings", {})["plan_file"] = str(f)
    store.save(doc)
    return {"ok": True, "file": str(f)}


def feed(niche="", n=11):
    """recent outliers of the niche, shaped like YouTube feed cards (Thumbnail Check puts yours among them)"""
    data = tracker()
    now = time.time()
    vids, chans, outl = data.get("videos", {}), data.get("channels", {}), data.get("outliers", {}) or {}
    rows = []
    for vid in outl:
        v = vids.get(vid)
        if not v or v.get("kind", "long") != "long" or (niche and v.get("niche") != niche):
            continue
        pub = v.get("published") or v.get("first_seen") or now
        rows.append({"id": vid, "title": v.get("title", ""), "channel": chans.get(v.get("channel_id"), {}).get("name", ""),
                     "views": v.get("views"), "age": round((now - pub) / DAY, 1), "thumb": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"})
    rows.sort(key=lambda r: r["age"])
    return {"items": rows[:n]}


def upload(data, name=""):
    """an image dropped on Thumbnail Check (data: URL) -> a file the Claude check can look at"""
    import base64
    m = re.match(r"data:image/(png|jpe?g|webp);base64,(.+)", data or "", re.S)
    if not m:
        raise ValueError("drop a PNG, JPG or WEBP image")
    d = OUT / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}.{m.group(1).replace('jpeg', 'jpg')}"
    f.write_bytes(base64.b64decode(m.group(2)))
    return {"path": str(f)}


def t_thumb_check(inp, say):
    img = Path(inp.get("image") or "")
    if not img.is_file():
        raise ValueError("pick a project with a thumbnail, or drop an image")
    from PIL import Image
    small = OUT / "uploads" / (img.stem + "-feed.png")
    small.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(img).convert("RGB")
    im.resize((246, round(246 * im.height / im.width))).save(small)   # about the size it shows in a YouTube feed
    others = feed(inp.get("niche") or "", 11)["items"]
    say("Asking Claude to look at the thumbnail (about a minute)")
    prompt = f"""You are a YouTube thumbnail expert. Image 1 is the creator's thumbnail at full size; image 2 is the SAME
thumbnail at the size people see it in a feed (246 px wide). Judge it for click-through.

TITLE IT GOES WITH: {inp.get('title') or '(not given)'}
NICHE: {inp.get('niche') or 'general'}
It competes in the feed with these videos: {'; '.join(o['title'] for o in others[:8]) or 'n/a'}

Check: is it readable at feed size, one clear focal point, 3 words of text or fewer, strong contrast, a face/emotion if it
helps, curiosity that the title completes (not repeats), does it stand out from the competing videos?
Answer ONLY JSON:
{{"score": 0-100, "verdict": "one sentence", "small_size": "what you can and can't read at feed size",
 "works": ["...", ...] (up to 3), "fixes": [{{"fix": "a concrete change", "why": "..."}}] (up to 4, most important first),
 "text_ideas": ["2-4 word thumbnail text", ...] (3)}}"""
    out = _brain().ask("tool_thumb_check", prompt, images=[str(img), str(small)], model="sonnet", timeout=300, say=say)
    if not out:
        raise RuntimeError("Claude didn't answer. Try again in a minute")
    out["image"] = str(img)
    return out


# ---------------------------------------------------------------- YouTube Downloader (user 2026-10-31: "download YouTube
# videos, such as an MP3 file, an MP4 file, and even the whole playlist"). No AI: yt-dlp + FFmpeg, progress in the job log.
CUR = threading.local()   # the job id of the tool running on this thread (so Cancel can find its yt-dlp)
PROCS = {}
STOP = set()   # jobs the user cancelled
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _ytdlp():
    """the yt-dlp command: the program if it's installed, else the Python package (installed on first use in the kit)"""
    import shutil
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    if subprocess.run([sys.executable, "-c", "import yt_dlp"], capture_output=True, creationflags=NOWIN).returncode:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "yt-dlp"], capture_output=True, text=True, creationflags=NOWIN)
        if r.returncode:
            raise RuntimeError("couldn't install yt-dlp: " + (r.stderr.strip().splitlines() or ["pip failed"])[-1][:200])
    return [sys.executable, "-m", "yt_dlp"]


def download_folder():
    return str(store.settings().get("download_folder") or Path.home() / "Downloads" / "Studio Downloads")


SITES = (("youtube", r"youtube\.com|youtu\.be"), ("tiktok", r"tiktok\.com"), ("instagram", r"instagram\.com"))


def site(url):
    return next((n for n, rx in SITES if re.search(rx, url or "", re.I)), "")


def _is_list(url):
    """a link that is a list of videos: a playlist, a channel / profile page (a watch?v=…&list=… link asks in the popup)"""
    return bool(re.search(r"[?&]list=|/playlist\b|youtube\.com/(@[^/]+|c/|channel/|user/)[^?]*$|tiktok\.com/@[^/]+/?(\?|$)", url or "", re.I))


def probe(url):
    """what a link holds before downloading: one video, or a list (title + every entry) for the pick-the-videos popup"""
    url = (url or "").strip()
    if not re.match(r"https?://", url):
        raise ValueError("paste a link (https://…)")
    if not site(url):
        raise ValueError("that isn't a YouTube, TikTok or Instagram link")
    if "list=" not in url and not _is_list(url):
        return {"playlist": False, "site": site(url)}
    r = subprocess.run(_ytdlp() + ["--encoding", "utf-8", "--flat-playlist", "--yes-playlist", "-J", "--no-warnings", "--playlist-end", "1000", url],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, creationflags=NOWIN)
    try:
        d = json.loads(r.stdout)
    except ValueError:
        raise RuntimeError("couldn't read that link: " + (r.stderr.strip().splitlines() or ["no answer"])[-1][:200])
    es = [e for e in d.get("entries") or [] if e]
    if not es:
        return {"playlist": False, "site": site(url)}
    v = re.search(r"[?&]v=([\w-]{11})", url)
    return {"playlist": True, "site": site(url), "title": d.get("title") or "Playlist", "this_video": v.group(1) if v else "",
            "entries": [{"n": i + 1, "id": e.get("id"), "title": e.get("title") or e.get("id"), "duration": e.get("duration")}
                        for i, e in enumerate(es)]}


def _h264(f, say):
    """TikTok / Instagram only have their 1080p in H.265, which a lot of Windows players and editors can't open: re-encode
    to H.264 (seconds for a clip). YouTube up to 1080p is H.264 already."""
    try:
        c = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0", f],
                           capture_output=True, text=True, creationflags=NOWIN).stdout.strip()
    except OSError:
        return f
    if not c or c == "h264":
        return f
    say("Making it H.264 so it plays everywhere…")
    tmp = f[:-4] + ".h264.mp4"
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", f, "-map", "0", "-c:v", "libx264", "-crf", "18", "-preset", "veryfast",
                        "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", tmp], capture_output=True, creationflags=NOWIN)
    if r.returncode or not Path(tmp).exists():
        Path(tmp).unlink(missing_ok=True)
        return f
    Path(tmp).replace(f)
    return f


def t_download(inp, say):
    url = (inp.get("url") or "").strip()
    if not re.match(r"https?://", url):
        raise ValueError("paste a link (https://…)")
    where = site(url)
    kind = "mp3" if inp.get("kind") == "mp3" else "mp4"
    q = str(inp.get("quality") or "1080")
    playlist = bool(inp.get("playlist"))
    folder = Path(inp.get("folder") or download_folder())
    folder.mkdir(parents=True, exist_ok=True)
    job = JOBS.get(getattr(CUR, "jid", ""), {})
    prog = job.setdefault("progress", {"pct": 0, "item": 0, "total": 0, "done": 0, "title": ""})
    # TikTok / Instagram titles are the caption + hashtags: name the file by the account and the start of the caption
    base = "%(title).90s" if where == "youtube" else "%(uploader)s - %(title).60s"
    name = f"%(playlist_title)s/%(playlist_index)03d - {base}.%(ext)s" if playlist else f"{base}.%(ext)s"
    cmd = _ytdlp() + ["--encoding", "utf-8", "--newline", "--progress", "--no-warnings", "--windows-filenames", "--trim-filenames", "150", "--no-mtime",
                      "--yes-playlist" if playlist else "--no-playlist", "-P", str(folder), "-o", name,
                      "--progress-template", "download:PROG %(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
                      "--print", "before_dl:TITLE %(title)s", "--print", "after_move:FILE %(filepath)s"]
    if playlist:
        cmd += ["--print", "before_dl:LIST %(playlist_title)s|%(playlist_index)s|%(n_entries)s", "--ignore-errors"]
        if inp.get("items"):
            cmd += ["--playlist-items", ",".join(str(int(i)) for i in inp["items"])]
            prog["total"] = len(inp["items"])
    if inp.get("cookies") in ("edge", "firefox", "chrome", "brave"):
        cmd += ["--cookies-from-browser", inp["cookies"]]
    if kind == "mp3":
        cmd += ["-f", "ba/b", "-x", "--audio-format", "mp3", "--audio-quality", "0", "--embed-metadata", "--embed-thumbnail"]
    else:
        # highest picture up to the chosen size, H.264 + AAC first so it plays everywhere and drops straight into an edit
        res = "" if q == "best" else f"res:{q},"
        cmd += ["-S", f"{res}vcodec:h264,acodec:aac", "--merge-output-format", "mp4", "--embed-metadata"]
    cmd.append(url)
    say("Starting…")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                         creationflags=NOWIN)
    PROCS[CUR.jid] = p
    if CUR.jid in STOP:
        cancel(CUR.jid)
    files, errs, title, last = [], [], "", 0
    try:
        for line in p.stdout:
            line = line.strip()
            if line.startswith("LIST "):
                lt, idx, n = (line[5:].split("|") + ["", "", ""])[:3]
                inp["title"] = lt or inp.get("title")
                prog["item"] += 1
                if not inp.get("items") and n.isdigit():
                    prog["total"] = int(n)
            elif line.startswith("TITLE "):
                title = prog["title"] = line[6:]
                prog["pct"] = 0
                if not playlist:
                    inp["title"] = title
            elif line.startswith("FILE "):
                f = line[5:]
                files.append(_h264(f, say) if kind == "mp4" and where != "youtube" else f)
                prog["done"] = len(files)
            elif line.startswith("PROG ") and time.time() - last > 0.5:
                last = time.time()
                pct, speed, eta = (line[5:].split("|") + ["", ""])[:3]
                try:
                    prog["pct"] = float(pct.strip().rstrip("%"))
                except ValueError:
                    pass
                at = f"{prog['item']} of {prog['total']}: " if prog["total"] else ""
                say(f"{at}{title} · {pct.strip()} · {speed.strip()} · {eta.strip()} left")
            elif line.startswith("[ExtractAudio]") or line.startswith("[Merger]"):
                say(("Making the MP3: " if kind == "mp3" else "Joining picture + sound: ") + title)
            elif line.startswith("ERROR:"):
                errs.append(line[6:].strip())
        p.wait()
    finally:
        PROCS.pop(CUR.jid, None)
    if getattr(p, "cancelled", False) or CUR.jid in STOP:
        STOP.discard(CUR.jid)
        raise RuntimeError(f"Cancelled. {len(files)} file(s) finished before that are in the folder")
    if not files:
        msg = errs[-1] if errs else "the download stopped"
        if re.search(r"login|log in|sign in|rate-limit|cookies", msg, re.I):
            job["needs_login"] = True
            msg = {"instagram": "Instagram wants you signed in for this one.",
                   "tiktok": "TikTok wants you signed in for this one."}.get(where, "YouTube wants a signed-in account for this one.") + \
                " Sign in on that site in your browser, then press “Try with my browser sign-in”."
        raise RuntimeError(msg[:300])
    return {"files": files, "folder": str(folder), "kind": kind, "playlist": playlist, "site": where,
            "failed": errs[:20], "title": inp.get("title") or title}


def cancel(jid):
    STOP.add(jid)   # also stops one that hasn't started yt-dlp yet (the first second) or is between steps
    p = PROCS.get(jid)
    if p and p.poll() is None:
        p.cancelled = True
        r = subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True, creationflags=NOWIN)
        if r.returncode and p.poll() is None:
            p.kill()
    return {"ok": True}


def set_download_folder(path):
    store.save_settings({"download_folder": path or ""})
    return {"folder": download_folder()}


TOOLS = {"planner": ("Video Planner", t_planner), "title_lab": ("Title Lab", t_title_lab), "thumb_check": ("Thumbnail Check", t_thumb_check), "brainstorm": ("Idea Brainstorm", t_brainstorm),
         "comment_miner": ("Comment Miner", t_comment_miner), "hook_doctor": ("Hook Doctor", t_hook_doctor),
         "repurpose": ("Repurpose Kit", t_repurpose), "download": ("Video Downloader", t_download)}


def _save(job):
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / f"{job['id']}.json.tmp"
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(OUT / f"{job['id']}.json")


def run(tool, inp):
    if tool not in TOOLS:
        raise ValueError("unknown tool")
    jid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    job = {"id": jid, "tool": tool, "name": TOOLS[tool][0], "input": inp or {}, "state": "running", "log": [],
           "started": time.time(), "result": None, "error": ""}
    with LOCK:
        JOBS[jid] = job

    def say(msg):
        job["log"] = (job["log"] + [str(msg)])[-12:]

    def go():
        CUR.jid = jid
        try:
            job["result"] = TOOLS[tool][1](job["input"], say)
            job["state"] = "done"
        except Exception as e:   # shown to the user as is
            job["state"], job["error"] = "error", str(e)
        job["took"] = round(time.time() - job["started"], 1)
        if job["state"] == "done" or tool == "download":
            _save(job)
    threading.Thread(target=go, name=f"tool-{tool}", daemon=True).start()
    return {"id": jid}


def job(jid):
    j = JOBS.get(jid)
    if j:
        return j
    f = OUT / f"{jid}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    raise ValueError("no such result")


def label(j):
    i = j.get("input") or {}
    if i.get("project"):
        d = store.load(i["project"])
        return (d or {}).get("title") or i["project"]
    return i.get("idea") or i.get("topic") or i.get("title") or i.get("url") or (Path(i["image"]).name if i.get("image") else "") or i.get("niche") or i.get("channel") or ""


def _dl_row(j):
    """what the downloads list shows for one download: state, progress, files, why it failed"""
    r, i = j.get("result") or {}, j.get("input") or {}
    return {"state": j.get("state"), "progress": j.get("progress"), "log": (j.get("log") or [""])[-1:], "error": j.get("error", ""),
            "needs_login": j.get("needs_login", False), "kind": r.get("kind") or i.get("kind"), "site": r.get("site") or site(i.get("url", "")),
            "files": len(r.get("files") or []), "folder": r.get("folder") or i.get("folder"),
            "first": next((f for f in (r.get("files") or [])[:1] if Path(f).exists()), ""),
            "failed": len(r.get("failed") or [])}


def history(tool=""):
    out = []
    if OUT.exists():
        for f in sorted(OUT.glob("*.json"), reverse=True)[:200]:
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if tool and j.get("tool") != tool:
                continue
            out.append({"id": j["id"], "tool": j["tool"], "name": j.get("name"), "label": label(j), "started": j.get("started"), "took": j.get("took"),
                        **(_dl_row(j) if j.get("tool") == "download" else {})})
    running = [{"id": j["id"], "tool": j["tool"], "name": j["name"], "label": label(j), "started": j["started"], "running": True,
                **(_dl_row(j) if j.get("tool") == "download" else {})}
               for j in JOBS.values() if j["state"] == "running" and (not tool or j["tool"] == tool)]
    return {"items": running + out}


def forget(jid):
    JOBS.pop(jid, None)
    (OUT / f"{jid}.json").unlink(missing_ok=True)
    return {"ok": True}


def meta():
    data = tracker()
    s = store.settings()
    projects = []
    import extras
    for d in sorted(store.all_projects(), key=lambda d: d.get("updated", ""), reverse=True):
        try:
            P = extras.recipe(d["type"]).paths(d)
            wp = P.get("transcript") if d["type"] == "review" else P.get("words")
            has = bool(wp) and Path(wp).exists()
        except Exception:
            has = False
        th = ((d.get("slots") or {}).get("thumbnail") or "")
        projects.append({"id": d["id"], "title": d.get("title"), "channel": d.get("channel"), "type": d.get("type"), "transcript": has,
                         "thumbnail": th if th and Path(th).is_file() else ""})
    # his own uploaded videos (Uploads tab video ids + YouTube links on projects): one-click picks for Comment Miner
    mine, seen = [], set()
    try:
        up = json.loads((DATA / "uploads.json").read_text(encoding="utf-8")).get("items", {})
    except (OSError, ValueError):
        up = {}
    for d in store.all_projects():
        vid = (up.get(d["id"]) or {}).get("video_id") or _yt_id((d.get("links") or {}).get("youtube") or "")
        if vid and vid not in seen:
            seen.add(vid)
            mine.append({"title": d.get("title"), "url": f"https://www.youtube.com/watch?v={vid}"})
    return {"my_videos": mine, "niches": sorted({v.get("niche") for v in data.get("videos", {}).values() if v.get("niche")}),
            "channels": [c.get("name") for c in s.get("channels") or [] if c.get("name")], "projects": projects,
            "last_scan": data.get("last_scan"), "tools": {k: v[0] for k, v in TOOLS.items()}}


ROUTES = {
    ("GET", "tools/insights"): lambda q, b: insights(q.get("niche", ""), int(q.get("days") or 90)),
    ("GET", "tools/meta"): lambda q, b: meta(),
    ("POST", "tools/run"): lambda q, b: run((b or {}).get("tool"), (b or {}).get("input")),
    ("GET", "tools/job"): lambda q, b: job(q.get("id", "")),
    ("GET", "tools/history"): lambda q, b: history(q.get("tool", "")),
    ("POST", "tools/forget"): lambda q, b: forget((b or {}).get("id", "")),
    ("GET", "tools/feed"): lambda q, b: feed(q.get("niche", ""), int(q.get("n") or 11)),
    ("POST", "tools/save-plan"): lambda q, b: save_plan((b or {}).get("project", ""), (b or {}).get("job", "")),
    ("GET", "tools/dl-probe"): lambda q, b: probe(q.get("url", "")),
    ("POST", "tools/cancel"): lambda q, b: cancel((b or {}).get("id", "")),
    ("GET", "tools/download-folder"): lambda q, b: {"folder": download_folder()},
    ("POST", "tools/download-folder"): lambda q, b: set_download_folder((b or {}).get("folder", "")),
    ("POST", "tools/upload"): lambda q, b: upload((b or {}).get("data", ""), (b or {}).get("name", "")),
}

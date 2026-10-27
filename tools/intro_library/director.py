"""Claude as the intro director (2026-10-22): the rules in build_intro.py split the VO into lines and pick clips/pictures by
keyword, which put "some weird pictures" in the first Cartier intro. One Opus call per intro now decides what every line
SHOWS, looking at the real clips (one contact sheet), and one cheap Sonnet call checks every picture before it is used.

    direct(kind, title, product, L, footage, slot_lines, out, template) -> {line index: decision} or {}
    check_pictures(L, out, product) -> drops/replaces pictures that are not the thing the line names

decision: {"show": "footage", "clips": [footage indices]} | {"show": "picture", "query": "...", "kind": "photo|logo",
           "word": "Kia"} | {"show": "stock", "query": "airport security"} | {"show": "type"}
Answers are cached by claude_brain (same VO + clips = no new call). Without Claude it returns {} and the rules decide.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import claude_brain as B   # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def _rules(kind):
    p = os.path.join(HERE, "director_rules.md")
    if not os.path.exists(p):
        return ""
    txt = open(p, encoding="utf-8").read()
    keep, cur = [], None
    for line in txt.splitlines():
        if line.startswith("## "):
            cur = line[3:].split()[0].lower()
        if cur in (None, "all", kind):
            keep.append(line)
    return "\n".join(keep)


def _crop_vf(f):
    crop = {"right": "crop=iw/2:ih:iw/2:0,", "left": "crop=iw/2:ih:0:0,"}.get(f.get("crop", ""), "")
    if f.get("crop") == "phone":
        crop = f"crop={f.get('box', '504:1080:2628:0')},"
    return crop


def footage_sheet(footage, out):
    """One frame from the middle of each clip moment, labelled with its index, as Claude will refer to it."""
    items = [(f["src"], float(f.get("t", 0)) + 1.0, f"#{k} {f.get('tag', '')}{' (own)' if f.get('own') else ''}", _crop_vf(f) + "scale=1920:1080" + (f.get("vf") or ""))
             for k, f in enumerate(footage[:24])]
    return B.contact_sheet(items, os.path.join(out, "director_footage.png"))


def wishes(kind, requests, tpls, music, title, say=print):
    """The user's special requests (Studio New Project box, 2026-10-23) -> what they ask of the intro as a whole:
    {"template": id|"", "title": text|"", "music": path|""}. Only things the requests really ask for; the rest stays automatic.
    The line-by-line asks ("show the Gucci logo when I say Gucci") go to direct() with the same text."""
    if not (requests or "").strip() or not B.enabled():
        return {}
    tl = "\n".join(f"{t['id']}: {t.get('name', '')} - {t.get('blurb', '')[:140]}" for t in tpls if t.get("status", "ready") == "ready")
    ml = "\n".join(f"{k}: {os.path.basename(m)}" for k, m in enumerate(music))
    prompt = f"""The creator wrote special requests for a {kind} video before it was edited. Some may be about the intro.

Video title: "{title}"
REQUESTS
{requests.strip()}

INTRO STYLES (templates)
{tl}

INTRO MUSIC TRACKS
{ml}

Answer only what the requests clearly ask of the INTRO: a style they name or describe, the exact on-screen title they want,
a music track they name or describe. Ignore requests about the rest of the video. Leave a field empty when nothing asks for it.
Reply with ONLY JSON: {{"template":"<id or empty>","title":"<title text or empty>","music":<track index or null>,"why":"<10 words>"}}"""
    ans = B.ask("intro_wishes", prompt, model="sonnet", say=say)
    if not isinstance(ans, dict):
        return {}
    ids = {t["id"] for t in tpls if t.get("status", "ready") == "ready"}
    out = {"template": ans.get("template") if ans.get("template") in ids else "", "title": (ans.get("title") or "").strip()[:80], "music": ""}
    if isinstance(ans.get("music"), int) and 0 <= ans["music"] < len(music):
        out["music"] = music[ans["music"]]
    say(f"requests -> intro: {json.dumps(out)}  ({ans.get('why', '')})")
    return out


def direct(kind, title, product, L, footage, slot_lines, out, template="", say=print, requests=""):
    if not B.enabled():
        return {}
    footage = footage or []
    req = (f"\nTHE CREATOR'S SPECIAL REQUESTS (written before the edit; follow the ones about the intro over the RULES below, "
           f"ignore the ones about the rest of the video)\n{requests.strip()}\n" if (requests or "").strip() else "")
    lines = "\n".join(f"L{i} [{ln['s']:.1f}-{ln['e']:.1f}s] role={ln['role']}{' SLOT' if i in slot_lines else ''}: {ln['text']}" for i, ln in enumerate(L))
    clips = "\n".join(f"#{k}: tag={f.get('tag', '')} kind={f.get('kind', '')}{' own-broll' if f.get('own') else ''}"
                      f"{' crop=' + f['crop'] if f.get('crop') else ''}{' meant-for=' + json.dumps(f['for']) if f.get('for') else ''}"
                      for k, f in enumerate(footage[:24]))
    prompt = f"""Plan what each line of this {kind} video intro shows on screen.

Video: "{title}"  (product: {product or 'n/a'})  template: {template}
The VO is split into lines. Lines marked SLOT get a full-screen footage/picture slot under the captions; the others are
the template's own text-only look (still answer them: "type" or a picture that pops in).

LINES
{lines}

CLIPS (the creator's own footage; the attached image shows one frame of each, labelled #index)
{clips or '(none)'}
{req}
RULES
{_rules(kind)}

For EVERY line choose one:
- {{"show":"footage","clips":[indices in preference order]}}  one of the creator's clips (look at the frames: only clips that really show what the line says; never a frame with a face talking)
- {{"show":"picture","query":"<precise Wikimedia Commons search, e.g. 'Cartier Santos watch' or 'Kia Sportage car'>","kind":"photo|logo","word":"<the word in the line it lands on>"}}  a real photo of a named thing the clips don't show
- {{"show":"stock","query":"<2-3 word stock video search>"}}  generic action/place B-roll (travel, shopping, delivery), at most 3 per intro
- {{"show":"type"}}  kinetic type only

Reply with ONLY JSON: {{"lines":[{{"i":0,"show":"...", ..., "why":"<8 words>"}}, ...], "notes":"<one sentence on the intro as a whole>"}}"""
    imgs = [footage_sheet(footage, out)] if footage else []
    # kept so an approved (or corrected) plan can become a teaching example: teach.py add intro_director <out>
    open(os.path.join(out, "director_prompt.txt"), "w", encoding="utf-8").write(prompt)
    ans = B.ask("intro_director", prompt, images=imgs, model="opus", say=say)
    if not isinstance(ans, dict):
        return {}
    plan = {}
    for d in ans.get("lines") or []:
        try:
            i = int(d.get("i"))
        except (TypeError, ValueError):
            continue
        if not 0 <= i < len(L):
            continue
        show = d.get("show")
        if show == "footage":
            ks = [int(k) for k in d.get("clips") or [] if str(k).isdigit() and int(k) < len(footage)]
            if ks:
                plan[i] = {"show": "footage", "clips": ks, "why": d.get("why", "")}
        elif show in ("picture", "stock") and (d.get("query") or "").strip():
            plan[i] = {"show": show, "query": d["query"].strip(), "kind": d.get("kind") if d.get("kind") in ("photo", "logo") else "photo",
                       "word": d.get("word") or "", "why": d.get("why", "")}
        elif show == "type":
            plan[i] = {"show": "type", "why": d.get("why", "")}
    json.dump({"plan": {str(k): v for k, v in plan.items()}, "notes": ans.get("notes", "")}, open(os.path.join(out, "director.json"), "w"), indent=1)
    say(f"director: {len(plan)}/{len(L)} lines planned  ({ans.get('notes', '')[:120]})")
    for i, d in sorted(plan.items()):
        say(f"  L{i} {d['show']:8} {d.get('query') or d.get('clips') or ''}  - {d.get('why', '')}")
    return plan


def check_pictures(L, out, product="", say=print):
    """Look at every picture the intro will use (one sheet, one Sonnet call); a wrong one is replaced by Claude's better
    query once, else dropped. A picture that isn't provably the thing is worse than no picture."""
    import pics as P
    have = [(i, k, p) for i, ln in enumerate(L) for k, p in enumerate(ln.get("pics") or [])]
    if not have or not B.enabled():
        return
    items = [(os.path.join(out, p["src"]), None, f"P{n} L{i}: {p.get('label', '')}") for n, (i, k, p) in enumerate(have)]
    sheet = B.contact_sheet(items, os.path.join(out, "director_pics.png"), cols=min(4, len(items)))
    listing = "\n".join(f"P{n}: line L{i} \"{L[i]['text']}\" -> picture meant to show: {p.get('label', '')}" for n, (i, k, p) in enumerate(have))
    prompt = f"""These pictures will pop up in a video intro (product: {product or 'n/a'}). The attached sheet shows each one, labelled P<n>.

{listing}

For each picture: is it clearly and literally the thing the line names (right brand, right kind of object, decent quality,
not a map/diagram/unrelated place, no big dates or watermarks)? Ordinary public photo details (a car's license plate,
street background, people far away) are fine; reject only a picture a viewer would find wrong, confusing or ugly.
When it is not ok, ALWAYS give a better query. Reply with ONLY JSON:
{{"pics":[{{"n":0,"ok":true}}, {{"n":1,"ok":false,"why":"<short>","query":"<better Wikimedia Commons search or empty>"}}]}}"""
    ans = B.ask("intro_picture_check", prompt, images=[sheet], model="sonnet", say=say)
    if not isinstance(ans, dict):
        return
    bad = {int(d["n"]): d for d in ans.get("pics") or [] if str(d.get("n", "")).isdigit() and d.get("ok") is False}
    for n, d in sorted(bad.items(), reverse=True):
        if n >= len(have):
            continue
        i, k, p = have[n]
        new = P.fetch(d["query"], p.get("kind", "photo")) if d.get("query") else None
        if new:
            import shutil
            name = os.path.basename(new["file"])
            shutil.copy(new["file"], os.path.join(out, "assets", "pics", name))
            L[i]["pics"][k] = dict(p, src="assets/pics/" + name)
            say(f"picture check: L{i} '{p.get('label')}' replaced ({d.get('why', '')}) -> {d['query']}")
        else:
            del L[i]["pics"][k]
            say(f"picture check: L{i} '{p.get('label')}' dropped ({d.get('why', '')})")
        if not L[i]["pics"]:
            L[i].pop("pics")

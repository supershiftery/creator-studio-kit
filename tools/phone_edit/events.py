"""Auto graphics plan for a phone-tutorial cut (the Uber Eats edit, approved style, made generic).
Usage: python events.py <work/cuts.json> <work/words.json> <edit dir>
Writes <edit>/graphics/batch.json (render rows) + events.json (name, t, dur, kind) and downloads app icons.
Rules (from the hand-made Uber Eats edit):
  - section = a cue phrase ("first method", "next method", "next app", "another method", "next up", "last but not least")
    -> brand wipe 0.35 s before + METHOD n title (named after the first app said in the next 25 s)
  - first mention of each app -> app card (real App Store icon)
  - "code" said inside an app's section, and that app has a code in codes.json -> code card (again if said 30+ s later)
  - "$N" / "N %" -> stat pop (12 s apart at most, max 10)
  - first "subscrib" -> subscribe pop; last "but anyways guys" -> end card with every code used; subscribe at the very end
"""
import json, os, re, sys, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APPS = {k: v for k, v in json.load(open(os.path.join(HERE, "apps.json"))).items() if not k.startswith("_")}
CODES = {k: v for k, v in json.load(open(os.path.join(HERE, "codes.json"))).items() if not k.startswith("_")}
norm = lambda s: re.sub(r"[^a-z0-9$%. ]", "", s.lower()).strip()
CUES = ["first method", "next method", "another method", "next app", "next up", "last but not least", "for our next", "secret method"]
# the talk-to-camera opening hands over to the walkthrough ("let's go ahead and dive right into this") and the walkthrough
# hands over to the outro ("anyways guys, that's pretty much it"): each gets a plain wipe + swoosh and its own music
# section (user, dhgate coupons 2026-10-22: one beat ran under the whole video, no transitions)
DIVE = ["dive right in", "dive into", "jump right in", "jump into", "get right into", "get into it", "get started", "without further ado"]
OUTRO = ["but anyways guys", "anyways guys", "that's pretty much it", "thats pretty much it", "that's it for today", "thats it for today"]


NOT_NAME = {"first", "second", "third", "fourth", "fifth", "next", "last", "final", "another", "other", "this", "that", "same",
            "one", "best", "easiest", "main", "secret", "new"}


def method_name(ow, t, back=3.0, ahead=15.0):
    """the method he NAMES at a section start ("which is gonna be the new account method" -> "New Account"), else None.
    Uber codes october 2026-10-25: the METHOD 2 card said "Method 2" (no new app named), METHOD 1 the app's name, and the
    user: "the transition didn't transition me into the new account method"."""
    near = [x for x in ow if t - back <= x["o"] <= t + ahead]
    toks = [re.sub(r"[^a-z0-9']", "", x["w"].lower()) for x in near]
    for i, tk in enumerate(toks):
        if tk not in ("method", "methods") or i == 0:
            continue
        name = []
        for j in range(i - 1, max(-1, i - 4), -1):
            if toks[j] in ("the", "a", "our", "this", "my", "") or near[j]["w"][-1:] in ".,!?":
                break
            name.insert(0, toks[j])
        if name and not (len(name) == 1 and name[0] in NOT_NAME) and not any(w in ("first", "next", "second", "third", "last", "another") for w in name):
            return " ".join(w.capitalize() for w in name)
    return None


def out_words(cuts, words):
    K = cuts["keep"]
    res = []
    for w in words:
        acc = 0.0
        for s, e in K:
            if s - 0.05 <= w["s"] < e:
                res.append({"w": w["w"], "o": round(acc + max(0, w["s"] - s), 2)})
                break
            acc += e - s
    return res, sum(e - s for s, e in K)


def find_all(ow, phrase):
    p = phrase.split()
    toks = [norm(x["w"]) for x in ow]
    return [i for i in range(len(toks) - len(p) + 1) if all(toks[i + k].startswith(p[k]) for k in range(len(p)))]


def app_hits(ow):
    hits = []
    for key, a in APPS.items():
        for al in a["aliases"]:
            hits += [(ow[i]["o"], key) for i in find_all(ow, al)]
    return sorted(set(hits))


def icon(key, folder):
    path = os.path.join(folder, f"icon-{key.replace(' ', '')}.jpg")
    if not os.path.exists(path):
        q = urllib.parse.quote(APPS[key]["search"])
        with urllib.request.urlopen(f"https://itunes.apple.com/search?term={q}&entity=software&limit=1", timeout=20) as r:
            url = json.load(r)["results"][0]["artworkUrl512"]
        urllib.request.urlretrieve(url, path)
    return os.path.basename(path)


def plan(cuts_path, words_path, edit_dir):
    ow, dur = out_words(json.load(open(cuts_path)), json.load(open(words_path)))
    json.dump(ow, open(os.path.join(edit_dir, "out_words.json"), "w"))
    gdir = os.path.join(edit_dir, "graphics")
    os.makedirs(os.path.join(gdir, "assets"), exist_ok=True)
    hits = app_hits(ow)
    ev = []
    add = lambda name, t, v: ev.append((name, round(max(0.0, t), 2), v))
    # subscribe
    sub = find_all(ow, "subscrib")
    if sub:
        add("subscribe", ow[sub[0]]["o"] - 0.6, {"kind": "subscribe", "x": 90, "y": 880, "dur": 4})
    # sections
    starts = sorted({ow[i]["o"] for c in CUES for i in find_all(ow, c)})
    # codes read off the screen (screen_codes.py): one card per code. Inside a run of codes "next code" is not a new
    # section, so no METHOD wipe lands between two codes (Shein 2:00: a METHOD 1 wipe cut in mid-list)
    sc_path = os.path.join(edit_dir, "screen_codes.json")
    scodes = json.load(open(sc_path, encoding="utf-8")) if os.path.exists(sc_path) else []
    if len(scodes) >= 2:
        r0, r1 = scodes[0]["said"] - 5, scodes[-1]["said"] + 12
        starts = [s for s in starts if not (r0 <= s <= r1)]
    first_app = next((t for t, k in hits if t > 15 and not APPS[k].get("no_card")), None)
    # the dive-in hand-over (first 2 min only): the wipe covers the seam right after the cue sentence
    dive_i = sorted(i + len(c.split()) for c in DIVE for i in find_all(ow, c) if ow[i]["o"] < min(120, dur * 0.5))
    dive_t = None
    if dive_i:
        j = dive_i[0]
        k = 0   # finish the cue sentence ("dive right into | this"): stop at punctuation, a capitalised new sentence or a pause
        while j < len(ow) - 1 and k < 4 and not ow[j - 1]["w"].endswith((".", "!", "?", ",")) and ow[j]["o"] - ow[j - 1]["o"] < 0.6                 and not (ow[j]["w"][:1].isupper() and ow[j]["w"].rstrip(".,") not in ("I", "I'm", "I'll", "I've")):
            j, k = j + 1, k + 1
        dive_t = ow[min(j, len(ow) - 1)]["o"] - 0.2
    # a lone first-app section right after the dive-in would be a second wipe on the same hand-over (and a METHOD 1 pill
    # with no method 2): the dive-in wipe is that section change
    if first_app and (not starts or starts[0] - first_app > 20) and not (dive_t and -5 < first_app - dive_t < 30):
        starts = [max(15.0, first_app - 1.0)] + starts
    secs = []
    for t in starts:
        if secs and t - secs[-1] < 25:
            continue
        secs.append(t)
    # the wipe lands on the HAND-OVER, not on the cue words (Uber codes october 2026-10-25, 1:16: "transition swipes too
    # early": the METHOD 2 wipe ran over "let's move on to the next method" and the new section's picture came 1.2 s
    # later, on the cut). Finish the cue sentence; when a cut follows it before his next sentence (within 4 s), the section
    # starts ON that cut (the wipe covers it), else right after the cue's last word.
    seams = []
    acc = 0.0
    for s_, e_ in json.load(open(cuts_path))["keep"]:
        acc += e_ - s_
        seams.append(round(acc, 2))

    def hand_over(t):
        i = next((i for i, x in enumerate(ow) if x["o"] >= t - 0.01), None)
        if i is None:
            return t
        j, k = i, 0
        while j < len(ow) - 1 and k < 6 and not ow[j]["w"].endswith((".", "!", "?", ",")) and ow[j + 1]["o"] - ow[j]["o"] < 0.6 \
                and not (ow[j + 1]["w"][:1].isupper() and ow[j + 1]["w"].rstrip(".,") not in ("I", "I'm", "I'll", "I've")):
            j, k = j + 1, k + 1
        nxt = ow[j + 1]["o"] if j + 1 < len(ow) else ow[j]["o"] + 0.6
        sm = next((s for s in seams if ow[j]["o"] < s <= nxt + 0.05 and s - t <= 4.0), None)
        return sm if sm is not None else min(nxt, ow[j]["o"] + 0.45)
    sec_app = []
    prev_k = None
    for n, t in enumerate(secs, 1):
        t = hand_over(t)
        # title = first app said in the next 25 s that differs from the previous section's app ("Uber One" after "Uber Eats")
        k = next((k for tt, k in hits if t - 3 <= tt <= t + 25 and k != prev_k), None)
        prev_k = k
        sec_app.append((t, k))
        a = APPS.get(k, {"name": f"Method {n}", "accent": "#06C167"})
        add(f"wipe{n}", t - 0.35, {"kind": "wipe", "accent": a["accent"], "accent2": "#ffffff", "dur": 1.2})
        add(f"method{n}", t, {"kind": "method", "x": 90, "y": 70, "dur": 3.6, "accent": a["accent"], "pill": f"METHOD {n}",
                              "title": method_name(ow, t) or a["name"]})
    main_k = max(APPS, key=lambda k: sum(1 for _, kk in hits if kk == k)) if hits else None
    tr_acc = APPS[main_k]["accent"] if main_k else "#ff5a7a"
    if dive_t and not any(abs(t - dive_t) < 10 for t in secs):
        add("wipe-dive", dive_t - 0.35, {"kind": "wipe", "accent": tr_acc, "accent2": "#ffffff", "dur": 1.2})
    outro_c = sorted(ow[i]["o"] for c in OUTRO for i in find_all(ow, c) if ow[i]["o"] > dur * 0.6 and dur - ow[i]["o"] > 6)
    if outro_c:
        # the first outro cue of the last block ("anyways guys | that's pretty much it" counts once)
        ot = outro_c[-1]
        while any(ot - 8 < t < ot for t in outro_c):
            ot = max(t for t in outro_c if ot - 8 < t < ot)
        if not any(abs(t - ot) < 10 for t in secs):
            add("wipe-outro", ot - 0.15 - 0.35, {"kind": "wipe", "accent": tr_acc, "accent2": "#ffffff", "dur": 1.2})
    # app cards (first mention)
    seen = set()
    for t, k in hits:
        if k in seen or APPS[k].get("no_card") or t < 15:
            continue
        seen.add(k)
        a = APPS[k]
        add(f"app-{k.replace(' ', '')}", t - 0.1, {"kind": "app", "x": 90, "y": 760, "dur": 4.4, "accent": a["accent"],
                                                   "icon": icon(k, os.path.join(gdir, "assets")), "name": a["name"], "store": a["store"]})
    # code cards
    def section_app(t):
        k = None
        for st, kk in sec_app:
            if st - 1 <= t:
                k = kk
        return k
    outro_i = find_all(ow, "but anyways guys") or find_all(ow, "anyways guys")
    outro_t = ow[outro_i[-1]]["o"] if outro_i else dur
    used, last = [], {}
    for i in find_all(ow, "code"):
        t = ow[i]["o"]
        if t >= outro_t - 2:
            continue  # no code cards in the outro (the end card lists them)
        k = section_app(t)
        if k is None:  # before the first section: the nearest app mentioned in the last 40 s
            k = next((kk for tt, kk in reversed(hits) if t - 40 <= tt <= t), None)
        if k not in CODES or t - last.get(k, -99) < 30:
            continue
        last[k] = t
        c = CODES[k]
        if k not in used:
            used.append(k)
        add(f"code-{k.replace(' ', '')}-{len(ev)}", t - 0.2, {"kind": "code", "x": 90, "y": 720, "dur": 7.4,
            "accent": APPS[k]["accent"], "label": c["label"], "code": c["code"], "sub": c["sub"]})
    main_app = max(APPS, key=lambda k: sum(1 for _, kk in hits if kk == k)) if hits else None
    for n_, c in enumerate(scodes):
        nxt = scodes[n_ + 1]["said"] if n_ + 1 < len(scodes) else c["said"] + 9
        app_name = (c.get("app") or (APPS[main_app]["name"] if main_app else "")).upper()
        add(f"scode-{n_}", c["said"] - 0.1, {"kind": "code", "x": 90, "y": 720, "dur": round(max(4.0, min(7.4, nxt - c["said"] - 0.4)), 2),
            "accent": APPS[main_app]["accent"] if main_app else "#ff5a7a", "label": f"{app_name} PROMO CODE".strip(),
            "code": c["code"], "sub": c.get("sub") or "", "nth": f"CODE {n_ + 1} OF {len(scodes)}" if len(scodes) >= 3 else ""})
    # stats
    stats, lastt = 0, -99
    for i, w in enumerate(ow):
        m = re.match(r"^\$?(\d[\d,.]*)(%)?", w["w"])
        if not m or not (w["w"].startswith("$") or (i + 1 < len(ow) and ow[i + 1]["w"].startswith("%")) or m.group(2)):
            continue
        t = w["o"]
        if t - lastt < 12 or stats >= 8 or t < 15 or any(x[1] - 1.5 <= t <= x[1] + x[2]["dur"] + 0.5 for x in ev if x[2]["kind"] in ("code", "method", "app")):
            continue
        big = w["w"].rstrip(".,") + ("%" if i + 1 < len(ow) and ow[i + 1]["w"].startswith("%") else "")
        cap = " ".join(x["w"] for x in ow[i + 1:i + 5] if x["w"] != "%").strip(".,")
        add(f"stat-{stats}", t - 0.1, {"kind": "stat", "x": 90, "y": 800, "dur": 3.6, "accent": "#ffc93c", "big": big, "cap": cap[:38]})
        stats += 1
        lastt = t
    # end card + final subscribe
    outro = find_all(ow, "but anyways guys") or find_all(ow, "anyways guys")
    if outro and used:
        t = ow[outro[-1]]["o"] + 4.5
        rows = [CODES[k]["code"] for k in used][:3]
        add("end", min(t, dur - 8.5), {"kind": "end", "x": 60, "y": 470, "scale": 0.92, "dur": 7.9,
                                      "r1": rows[0] if len(rows) > 0 else "", "r2": rows[1] if len(rows) > 1 else "",
                                      "r3": rows[2] if len(rows) > 2 else "",
                                      "n1": APPS[used[0]]["name"] if len(used) > 0 else "", "n2": APPS[used[1]]["name"] if len(used) > 1 else "",
                                      "n3": APPS[used[2]]["name"] if len(used) > 2 else "",
                                      **{f"i{j + 1}": icon(k, os.path.join(gdir, "assets")) for j, k in enumerate(used[:3])}})
    add("subscribe-end", dur - 7.5, {"kind": "subscribe", "x": 90, "y": 880, "dur": 5.5})
    for _, _, v in ev:  # phone picture-in-picture sits on the LEFT (user's normal style) -> cards go on the right
        if v["kind"] in ("code", "app", "stat", "method", "subscribe"):
            v["ax"], v["x"] = "right", 90
    # an app / stat card never lands on a code card (Shein 1:45: the SHEIN app card covered the SHEIN2024 card)
    codes_on = [(t, t + v["dur"]) for n, t, v in ev if v["kind"] == "code"]
    ev[:] = [x for x in ev if x[2]["kind"] not in ("app", "stat") or not any(a - 0.5 < x[1] + x[2]["dur"] and x[1] < b for a, b in codes_on)]
    ev.sort(key=lambda x: x[1])
    rows = [dict(v, outputPath=f"renders/{n}.mov") for n, t, v in ev]
    # build_main always opens the main video on wipe1 (the intro's closing wipe); a video with no sections found
    # (old DHgate coupons recording, overnight 2026-10-22) had none and the draft failed. Render it, not as an event.
    if not any(n == "wipe1" for n, _, _ in ev):
        rows.append({"kind": "wipe", "accent": APPS[main_app]["accent"] if main_app else "#ff5a7a", "accent2": "#ffffff",
                     "dur": 1.2, "outputPath": "renders/wipe1.mov"})
    json.dump(rows, open(os.path.join(gdir, "batch.json"), "w"), indent=1)
    json.dump([{"name": n, "t": t, "dur": v["dur"], "kind": v["kind"]} for n, t, v in ev], open(os.path.join(gdir, "events.json"), "w"), indent=1)
    print(f"{len(ev)} graphics: {len(secs)} sections, apps {sorted(seen)}, codes for {used}, {stats} stats")
    return ev


if __name__ == "__main__":
    plan(sys.argv[1], sys.argv[2], sys.argv[3])

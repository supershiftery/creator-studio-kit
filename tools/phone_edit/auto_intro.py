"""Automatic VO-driven intro (HyperFrames) for a phone-tutorial video. Same recipe as the hand-made Uber Eats intro:
one scene per VO sentence (key words big, $ amounts slam red, app names pop with their real App Store icon),
blackout + bass drop on the turn line ("in today's video"), title slam on "let's go", green wipe out into the main video.
Usage: python auto_intro.py <intro vo audio> <title text> <out dir> [--music track.mp3]
Then: npx hyperframes render (done by pipeline.py)."""
import json, os, re, shutil, subprocess, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from events import APPS, icon  # noqa: E402

SFX = r"{{KIT}}/assets/Graphics/HyperFrames/servers-intro-oct/assets/sfx"
DEFAULT_MUSIC = r"{{MUSIC_ROOT}}/Type Beats/Drake/Drake Type Beat - Family Matters (ECHOBEATS).mp3"  # clean, no tags; the distorted hard-trap beat sounded "stacked"
STOP = set("a an the and or but so to of in on for at it its it's is are was be i i'm you your you're we our they this that these with as "
           "if just like um uh yeah okay gonna going go get got do does have has can will would very really one of those then some "
           "when start up all way out over here".split())


def transcribe(path):
    from faster_whisper import WhisperModel
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    m = WhisperModel("small.en", device="cpu", compute_type="int8")
    return [{"w": x.word.strip(), "s": round(x.start, 2), "e": round(x.end, 2)} for s in m.transcribe(a, word_timestamps=True)[0] for x in s.words]


def find_drop(track):
    """Return (break_start, drop) in the track: the first >= 6 s stretch with no bass after 20 s, and where the bass returns."""
    import scipy.signal as ss
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", track, "-t", "120", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    b, aa = ss.butter(4, 150 / 4000)
    bass = ss.lfilter(b, aa, a)
    w = 4000
    eb = np.array([20 * np.log10(np.sqrt((bass[i:i + w] ** 2).mean()) + 1e-9) for i in range(0, len(a) - w, w)])
    low = eb < np.median(eb) - 12
    i = 40
    while i < len(low):
        if low[i]:
            j = i
            while j < len(low) and low[j]:
                j += 1
            if (j - i) * 0.5 >= 6:
                return i * 0.5, j * 0.5
            i = j
        i += 1
    return 0.0, 16.0


def steady_start(track, need):
    """First point after 4 s where the bass stays present (no break, no build) for `need` seconds."""
    import scipy.signal as ss
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", track, "-t", "150", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    b, aa = ss.butter(4, 150 / 4000)
    bass = ss.lfilter(b, aa, a)
    w = 4000
    eb = np.array([20 * np.log10(np.sqrt((bass[i:i + w] ** 2).mean()) + 1e-9) for i in range(0, len(a) - w, w)])
    ok = eb > np.median(eb) - 8
    n = int(need * 2)
    for i in range(8, len(ok) - n):
        if ok[i:i + n].mean() > 0.93:
            return i * 0.5
    return 6.0


def lufs(path, ss_, t, vol=1.0):
    e = subprocess.run(["ffmpeg", "-v", "info", "-ss", str(ss_), "-t", str(t), "-i", path, "-af", f"volume={vol},ebur128", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace").stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", e)
    return float(m[-1]) if m else -14.0


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# what the intro's cart + receipt show: food apps vs shopping apps (apps.json "kind": "shop"); a Shein intro with a pizza
# order would make no sense (2026-10-21)
KITS = {
    "food": {"cards": [("P", "#e4002b", "Pizza Place", "2 items"), ("W", "#00843d", "Wing Spot", "1 item &#183; $12.99"), ("B", "#a81612", "Burger Bar", "2 items &#183; $18.40")],
             "lines": [("Large Pepperoni Pizza", 14.99, 0), ("Garlic Knots", 5.49, 0), ("Service fee", 3.20, 1), ("Delivery fee", 3.99, 1), ("Taxes &amp; other fees", 3.51, 1)],
             "sub": "JUST TO GET IT DELIVERED"},
    "shop": {"cards": [("D", "#111", "Satin Midi Dress", "1 item &#183; $24.99"), ("J", "#3b5bdb", "Wide-Leg Jeans", "1 item &#183; $21.49"), ("S", "#e8590c", "Chunky Sneakers", "1 item &#183; $32.00")],
             "lines": [("Satin Midi Dress", 24.99, 0), ("Wide-Leg Jeans", 21.49, 0), ("Chunky Sneakers", 32.00, 0), ("Shipping", 7.99, 1), ("Taxes", 6.27, 1)],
             "sub": "FOR ONE ORDER"},
}


def build(vo, title, out, music=DEFAULT_MUSIC):
    os.makedirs(os.path.join(out, "assets", "sfx"), exist_ok=True)
    words = transcribe(vo)
    json.dump(words, open(os.path.join(out, "vo-words.json"), "w"))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", vo, "-af", "loudnorm=I=-17:TP=-1.5", "-ar", "48000",
                    os.path.join(out, "assets", "vo-norm.wav")], check=True)
    for f in ("whoosh-short.mp3", "ping.mp3", "click.mp3", "glitch-1.mp3"):
        shutil.copy(os.path.join(SFX, f), os.path.join(out, "assets", "sfx", f))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", os.path.join(SFX, "impact-bass-2.mp3"), "-t", "0.9", "-af", "afade=t=out:st=0.45:d=0.45",
                    os.path.join(out, "assets", "sfx", "drop-short.wav")], check=True)
    shutil.copy(r"{{KIT}}/review_pipeline/assets/sfx_register.wav", os.path.join(out, "assets", "sfx", "register.wav"))
    shutil.copy(music, os.path.join(out, "assets", "music.mp3"))
    end_t = words[-1]["e"] + 0.5
    toks = [re.sub(r"[^a-z0-9$%']", "", w["w"].lower()) for w in words]
    # turn line + "let's go"
    turn = next((words[i]["s"] for i in range(len(toks) - 1) if toks[i] == "in" and toks[i + 1].startswith("today")), end_t * 0.62)
    go = next((words[i]["s"] for i in range(len(toks) - 1) if toks[i] in ("let's", "lets") and toks[i + 1].startswith("go")), end_t - 1.2)
    dur = round(max(go + 1.8, end_t + 0.3), 2)
    # Designed scenes, not captions (user 2026-10-21: "the whole intro is missing motion graphics"; the old version showed
    # stripped key words like "WHAT TOLD PAYING LOT"). Same kit as the approved Uber Eats intro, placed on the VO's words.
    def at(pattern, lo=0.0, hi=None, last=False):
        hits = [words[i]["s"] for i in range(len(toks)) if re.fullmatch(pattern, toks[i]) and words[i]["s"] >= lo and (hi is None or words[i]["s"] < hi)]
        return (hits[-1] if last else hits[0]) if hits else None
    apps_said = [k for k, a in APPS.items() if any(al in " ".join(toks) for al in a["aliases"])]
    icons = {k: icon(k, os.path.join(out, "assets")) for k in apps_said if not APPS[k].get("no_card")}
    main_app = next(iter(icons), None)
    accent = APPS[main_app]["accent"] if main_app else "#06C167"
    # problem half: "deals" (looks cheap) until the money sentence, then the cart + receipt adding up to a slam
    money_t = at(r"pay|paying|paid|price|prices|fees?|expensive|cost|costs|more|\$\d.*", 0, turn)
    sent_starts = [words[0]["s"]] + [words[i + 1]["s"] for i in range(len(words) - 1) if words[i]["w"][-1:] in ".!?" and words[i + 1]["s"] < turn]
    cart0 = max([s for s in sent_starts if money_t is not None and s <= money_t] or [0.0])
    if cart0 < 1.6:  # too short for a deals scene: the cart opens the intro
        cart0, deals = 0.0, None
    else:
        deals = [0.0, round(cart0, 2)]
    slam = at(r"more|expensive|fees?|have|crazy|insane|\$\d.*", cart0, turn - 0.5, last=True) or turn - 1.3
    slam = max(slam, cart0 + 1.8)
    lines = [round(cart0 + 0.6 + k * (slam - 0.5 - cart0 - 0.6) / 4, 2) for k in range(5)]
    # turn half: secret methods -> the price struck to $0 + FREE stamp -> friends doing it again and again -> title
    methods = at(r"methods?|ways?|tricks?|hacks?", turn, go) or turn + 0.7
    secret = at(r"secret", turn, go) or methods + 0.5
    free = at(r"free|100", turn, go) or go - 2.5
    friends = at(r"friends?|everyone|people", free + 0.6, go)
    again = at(r"over|again|every|times", (friends or free) + 0.5, go)
    T = {"deals": deals, "dealsTxt": round(min(at(r"convenient|cheap|easy", 0, cart0) or 1.6, cart0 - 0.8) if deals else 0, 2),
         "cart": [round(cart0, 2)], "lines": lines, "slam": round(slam, 2), "turn": round(turn, 2), "go": round(go, 2),
         "methods": round(methods, 2), "secret": round(max(secret, methods + 0.4), 2), "free": round(max(free, turn + 1.0), 2),
         "friends": round(friends, 2) if friends else None, "again": round(again, 2) if again else None}
    others = [k for k in icons if k != main_app][:4]
    pos = [(330, 520), (1420, 640), (1500, 120), (260, 90)]
    other_html = "".join(f'<div class="ap" style="left:{pos[i][0]}px;top:{pos[i][1]}px"><img src="assets/{icons[k]}" /></div>' for i, k in enumerate(others))
    sfx_tags = [f'      <audio id="s-reg" src="assets/sfx/register.wav" data-start="{T["slam"] - 0.02:.2f}" data-duration="1.2" data-track-index="15" data-volume="0.3"></audio>',
                f'      <audio id="s-free" src="assets/sfx/click.mp3" data-start="{T["free"]:.2f}" data-duration="0.36" data-track-index="12" data-volume="0.26"></audio>']
    js = []
    html_sc = []
    m_lab = APPS[main_app].get("intro_methods", ["PROMO CODES", "REFERRAL $$$", "FREE TRIAL"]) if main_app else ["PROMO CODES", "REFERRAL $$$", "FREE TRIAL"]
    tl_title = esc(title.upper())
    # music: ONE steady section of the beat the whole way (user rule 2026-10-20: no "half and half" break->drop trick and
    # no build/riser into a drop in phone-video intros). Only a quarter-second music gap at the blackout on the turn line.
    m_start = steady_start(music, dur + 2)
    drop = m_start + turn  # music continues where it left off after the gap
    bed = 10 ** ((-31 - lufs(music, m_start, dur)) / 20)  # same bed level as the main video (-31 LUFS), one steady clip
    json.dump({"track": music, "end": round(m_start + dur, 2)}, open(os.path.join(os.path.dirname(out.rstrip("/\\")), "intro_music.json"), "w"))
    bed2 = 10 ** ((-33.5 - lufs(music, drop, 6)) / 20)
    sw_vol = 10 ** ((-29.5 - lufs(music, m_start + go, 1.8)) / 20)
    html = open(os.path.join(HERE, "templates", "intro", "auto_intro.html"), encoding="utf-8").read()
    wipe_t = dur - 0.6
    free_t = next((words[i]["s"] for i in range(len(toks)) if toks[i] in ("free", "100") and words[i]["s"] > turn), turn + 2.5)
    # pre-mix the intro beat: one steady section at the bed level, fading out under the closing wipe (user v6: the intro
    # music fades out and the main video starts a different beat)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{m_start:.2f}", "-t", f"{dur:.2f}", "-i", music, "-af",
                    f"volume={bed:.4f},afade=t=out:st={max(0, dur - 1.4):.2f}:d=1.4", "-ar", "48000",
                    os.path.join(out, "assets", "music-intro.wav")], check=True)
    # unknown app: guess from the VO (a DHgate VO fell back to the food kit and showed "Pizza Place", 2026-10-22); an app's
    # own intro_items / intro_fees (apps.json) replace the generic lines
    vo_text = " ".join(toks)
    guess = "food" if re.search(r"(food|restaurants?|deliver(y|ed)|pizza|burgers?|meals?|eats|groceries|dinner|lunch|takeout|hungry)", vo_text) else "shop"
    kit = dict(KITS.get((APPS[main_app].get("kind") if main_app else None) or guess, KITS["shop"]))
    if main_app and APPS[main_app].get("intro_items"):
        its = APPS[main_app]["intro_items"]
        kit["cards"] = [(n[0], APPS[main_app]["accent"], n, f"1 item &#183; ${p:.2f}") for n, p in its]
        kit["lines"] = [(n, p, 0) for n, p in its] + [(n, p, 1) for n, p in APPS[main_app].get("intro_fees", [])]
    steps, run = [], 0.0
    for _, price, _ in kit["lines"]:
        run += price
        steps.append(round(run, 2))
    cards = "\n            ".join(f'<div class="cu-card" id="cc{i + 1}"><div class="cu-logo" style="background:{c}">{l}</div><div><div class="cu-n">{n}</div>'
                                   f'<div class="cu-m">{m}</div></div></div>' for i, (l, c, n, m) in enumerate(kit["cards"]))
    receipt = "\n          ".join(f'<div class="r-l{" fee" if fee else ""}" id="l{i + 1}"><span>{n}</span><span>${p:.2f}</span></div>'
                                  for i, (n, p, fee) in enumerate(kit["lines"]))
    html = (html.replace("{{CART_CARDS}}", cards).replace("{{RECEIPT}}", receipt).replace("{{STEPS}}", json.dumps(steps))
                .replace("{{BIG}}", f"${int(steps[-1])}").replace("{{TOTAL}}", f"${steps[-1]:.2f}").replace("{{BIG_SUB}}", kit["sub"]))
    html = (html.replace("{{TIMES}}", json.dumps(T)).replace("{{SLAM}}", f"{T['slam']:.2f}").replace("{{OTHER_APPS}}", other_html)
                .replace("{{APP_NAME}}", esc(APPS[main_app]["name"].upper()) if main_app else tl_title)
                .replace("{{M1}}", esc(m_lab[0])).replace("{{M2}}", esc(m_lab[1])).replace("{{M3}}", esc(m_lab[2])))
    html = (html.replace("{{WIPE_T}}", f"{wipe_t:.2f}").replace("{{FREE_T}}", f"{free_t:.2f}").replace("{{SFX_TAGS}}", "\n".join(sfx_tags))
                .replace("{{MUS2_DUR}}", f"{go - turn - 0.24:.2f}").replace("{{MUS3_DUR}}", f"{dur - go:.2f}")
                .replace("{{DUR}}", f"{dur:.2f}").replace("{{ACCENT}}", accent).replace("{{SCENES}}", "\n".join(html_sc))
                .replace("{{TITLE}}", tl_title).replace("{{ICON}}", f"assets/{icons[main_app]}" if main_app else "")
                .replace("{{TURN}}", f"{turn:.2f}").replace("{{GO}}", f"{go:.2f}").replace("{{VO_DUR}}", f"{end_t:.2f}")
                .replace("{{M_START}}", f"{m_start:.2f}").replace("{{M2}}", f"{drop + 0.24:.2f}").replace("{{M3}}", f"{m_start + go:.2f}")
                .replace("{{BED}}", f"{bed:.3f}").replace("{{BED2}}", f"{bed2:.3f}").replace("{{SWELL}}", f"{sw_vol:.3f}")
                .replace("{{JS}}", "\n      ".join(js)))
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(html)
    for f in ("package.json", "hyperframes.json"):
        shutil.copy(os.path.join(HERE, "templates", "graphics", f), os.path.join(out, f))
    print(f"auto intro: scenes {T}, dur {dur}s, apps {list(icons)}, music from {m_start}s")
    return dur


if __name__ == "__main__":
    a = sys.argv[1:]
    m = a[a.index("--music") + 1] if "--music" in a else None
    if not m:   # the whole {{MUSIC_ROOT}} library, fitted to this video and not used by the channel's last 15 videos (music_lib.py)
        try:
            sys.path.insert(0, os.path.dirname(HERE))
            import music_lib
            m = (music_lib.pick_for(a[2], kind="phone", n=1, title=a[1], min_len=20, role="intro") or [None])[0]
        except Exception as e:
            print(f"music_lib skipped: {type(e).__name__}: {str(e)[:160]}")
    build(a[0], a[1], a[2], m or DEFAULT_MUSIC)

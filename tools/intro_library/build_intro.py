"""Intro Library builder: one VO + one template -> a HyperFrames intro project (and optionally the rendered MP4).

    python build_intro.py --type review --template R01 --vo "C:/.../dhgate moncler.wav" --title "DHGATE MONCLER" --out <dir> [--render]
    python build_intro.py --type phone --template auto ...        (auto = least-recently-used template of that type)
    python build_intro.py --list [--type gaming]

Types and their house rules (memory: minecraft-intro-recipe, watch-to-end-sfx, phone-video-edit-feedback, no-vocal-music):
  gaming  problem half -> 0.26 s blackout + music gap -> DROP on the turn line with ONE 808 hit; game music (never Minecraft's own);
          bed about -34 LUFS; "GAMEPLAY GOES HERE" slots; "watch to the very end" = XP fill + ding.
  phone   ONE steady beat section the whole way (no break/drop, no 808, never pauses), bed -31 LUFS, fades out under the
          closing wipe; cash register on $ slams; no risers/whooshes; designed UI, no blurred screen recordings.
  review  ({{REVIEW_CHANNEL}} / DHgate) cold-open VO over product B-roll + word-by-word kinetic type (the user's own
          reference intros); one steady type beat, bed -30 LUFS; register on the price; swoosh + soft notification ding on
          "watch to the end" (the XP fill is gaming-only, 2026-10-22). No generic cash stock on price lines.
No dates/years/months in any graphic: titles are stripped of them. Output is always H.264 High yuv420p + AAC.
"""
import argparse, hashlib, json, os, pickle, re, shutil, subprocess, sys, time

try:   # template names carry arrows/accents; a cp1252 console must not crash a build
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "kit")
TPL = os.path.join(HERE, "templates")
STATE = os.path.join(HERE, "_state")
PY = sys.executable
HF = "npx --yes hyperframes@0.8.180"
# intro frame rate: 60 when the video it opens is 60 fps (watch spreadsheet 2026-10-24: "it still feels jittery": a 30 fps
# intro inside a 60 fps video glides at half the rate of everything after it). review_intro sets INTRO_FPS.
IFPS = int(os.environ.get("INTRO_FPS", "30") or 30)

FONTS = [("Poppins", "Poppins-Medium", 500, "normal"), ("Poppins", "Poppins-Bold", 700, "normal"), ("Poppins", "Poppins-ExtraBold", 800, "normal"),
         ("Poppins", "Poppins-Black", 900, "normal"), ("Poppins", "Poppins-BoldItalic", 700, "italic"), ("Poppins", "Poppins-ExtraBoldItalic", 800, "italic"),
         ("Bebas", "BebasNeue-Regular", 400, "normal"), ("Anton", "Anton-Regular", 400, "normal"), ("ArchivoBlack", "ArchivoBlack-Regular", 400, "normal"),
         ("SpaceMono", "SpaceMono-Bold", 700, "normal"), ("PressStart", "PressStart2P-Regular", 400, "normal"), ("Marker", "PermanentMarker-Regular", 400, "normal"),
         ("Typewriter", "SpecialElite-Regular", 400, "normal"), ("VT323", "VT323-Regular", 400, "normal"), ("Silkscreen", "Silkscreen-Regular", 400, "normal"),
         ("Silkscreen", "Silkscreen-Bold", 700, "normal"), ("Caveat", "Caveat", "100 900", "normal"), ("Monoton", "Monoton-Regular", 400, "normal"),
         ("Bungee", "Bungee-Regular", 400, "normal"), ("RubikMono", "RubikMonoOne-Regular", 400, "normal"), ("Playfair", "PlayfairDisplay", "400 900", "normal"),
         ("Playfair", "PlayfairDisplay-Italic", "400 900", "italic"), ("Oswald", "Oswald", "200 700", "normal"), ("Inter", "Inter", "100 900", "normal"),
         ("Unbounded", "Unbounded", "200 900", "normal"), ("DMSerif", "DMSerifDisplay-Regular", 400, "normal"), ("Bowlby", "BowlbyOneSC-Regular", 400, "normal"),
         ("Pixelify", "PixelifySans", "400 700", "normal"), ("RockSalt", "RockSalt-Regular", 400, "normal"), ("Syne", "Syne", "400 800", "normal"),
         ("BarlowC", "BarlowCondensed-ExtraBold", 800, "normal"), ("BarlowC", "BarlowCondensed-BlackItalic", 900, "italic"), ("MC", "MCCaption", 400, "normal"), ("Emoji", "SegoeEmoji", 400, "normal")]

TYPES = {
    "gaming": {"vo_lufs": -17, "music": "drop", "bed": -34, "swell": -30, "accent": "#6dffb0", "slot_label": "GAMEPLAY GOES HERE"},
    "phone": {"vo_lufs": -17, "music": "steady", "bed": -31, "swell": -29.5, "accent": "#06C167", "slot_label": "PHONE CLIP"},
    # split: no footage shot longer than this; a long line gets 2-3 different clips (dhgate cartier watch 2026-10-22: the
    # store page sat on screen 11 s, "too much of the watch, we need more motion")
    "review": {"vo_lufs": -14, "music": "steady", "bed": -28, "swell": -26, "accent": "#3DFF7A", "slot_label": "PRODUCT B-ROLL", "split": 2.6},   # tried 1.4 (watch spreadsheet 2026-10-24, "faster ... add more"): he preferred the 2.6 version
}
# Whisper-checked, instrumental, no producer tags (no-vocal-music; phone-tutorial-edit clean rotation)
MUSIC = {
    "phone": [r"{{MUSIC_ROOT}}/Type Beats/Drake/Drake Type Beat - Family Matters (ECHOBEATS).mp3", r"{{MUSIC_ROOT}}/Type Beats/Drake/[FREE] DRAKE TYPE BEAT   KENDALL  .mp3",
              r"{{MUSIC_ROOT}}/Type Beats/Drake/FREE Drake Type Beat - DoTheMove (Prod. 20).mp3", r"{{MUSIC_ROOT}}/Type Beats/Drake/Drake x RnB Type Beat - Close To Me (ECHOBEATS).mp3"],
    "review": [r"{{MUSIC_ROOT}}/Type Beats/Drake/[FREE] Drake x Iceman Type Beat - ''Name''.mp3", r"{{MUSIC_ROOT}}/Type Beats/Drake/(BEAT SWITCH) Drake Type Beat On Fire.mp3",
               r"{{MUSIC_ROOT}}/Type Beats/Drake/(FREE) Drake Iceman SWITCH Type Beat TRUST DIED FIRST.mp3",
               r"{{MUSIC_ROOT}}/Type Beats/Drake/(FREE) DRAKE TYPE BEAT - ALRIGHT TRAP TYPE BEAT HARD FREESTYLE RAP BEAT 2026.mp3"],
    "gaming": [r"{{KIT}}/assets/Graphics/HyperFrames/servers-intro-oct/assets/music-ultrashooters.mp3",
               r"{{KIT}}/assets/Graphics/HyperFrames/servers-intro-oct/assets/music-bloodytears.mp3"],
}
SFX = {"whip": "whip.mp3", "drop": "impact-bass-2.mp3", "click": "click.mp3", "ping": "ping.mp3", "register": "register.wav", "xpfill": "xp-fill.wav", "xpfull": "xp-full.wav",
       "glitch": "glitch-1.mp3", "error": "error.mp3", "key": "key-press.mp3", "notify": "notification.mp3",
       "swoosh": "swoosh.mp3", "shutter": "shutter.mp3"}   # shutter = Mixkit "Camera shutter click" (free license)

# ---------------------------------------------------------------- VO analysis
FIX = [(r"\bDH ?K\b|\bD\.? ?H\.? ?gate\b|\bDH Gate\b|\bdhgated\b|\bdee ?h ?gate\b", "DHgate"), (r"\bMonclairs?\b", lambda m: "Monclers" if m.group(0).endswith("s") else "Moncler"),
       (r"\bshifter(y|ie)\b", "Studio"), (r"\bShamall\b|\bsome more views\b", "{{REVIEW_CHANNEL}}"), (r"\bK ?subi\b", "Ksubi"), (r"\bNorth ?face\b", "North Face"), (r"\bSheen\b", "Shein"),
       (r"\bX ?3 ?Mila\b|\bx[- ]?remo(?:a|wa)?\b|\bRimova\b", "x Rimowa"),   # "Dior X3 Mila suitcase" (asics intro 2026-10-22)
       # "a peer will probably set you back $1,000", "I actually had a peer here" (dhgae prada glasses 2026-10-25): a pair
       (r"\b(a|the|one|this|that|each|per|another|new|first|second|my|your) (peer|pear)\b", lambda m: m.group(1) + " pair"),
       # "a lot of content traders are gatekeeping it" (Shein VO re-transcribed with the title as the Whisper hint, 2026-10-25)
       (r"\bcontent traders?\b", lambda m: "content creators" if m.group(0).endswith("s") else "content creator")]


def for_hit(f, text):
    """footage "for": one word/phrase or a list of them; True when any of them is in the line text."""
    fs = f.get("for") or []
    # spacing-blind too: Whisper writes "DH gate" (prada cups 2026-10-22: the store page never matched "over the DH gate
    # versions", so that line got another unboxing clip); only long keys, "site" would hit "is it every"
    flat = re.sub(r"\s+", "", text.lower())
    return any(k and (k.lower() in text.lower() or (len(k) >= 6 and re.sub(r"\s+", "", k.lower()) in flat)) for k in ([fs] if isinstance(fs, str) else fs))
STOP = set("a an the and or but so to of in on for at it its it's is are was be been i i'm im you your you're we we're our they this that these those with as if just like "
           "um uh yeah okay gonna going go get got do does did have has had can can't will would very really one then some when up all way out over here there what "
           "my me am not no don't didn't couldn't won't from by about into because trust me even also too more most much than then today today's let's lets what told tell have these been using again other day went made make making want wanted thing things lot know right something everything there's that's it's gonna wanna kind sort pretty actually literally basically they're we're you're i've i'll we'll they'll he's she's isn't aren't doesn't see any good ones one's even every honestly".split())
# topic words that are everywhere in a video type: never the key of a line there
GENERIC = {"gaming": {"servers", "server", "minecraft", "bedrock", "edition", "realms", "realm", "game", "video", "world", "worlds"},
           "phone": {"app", "apps", "video"}, "review": {"video", "review"}}
GAME_WORDS = ["kitpvp", "kit", "pvp", "skyblock", "prisons", "prison", "pixelmon", "cobblemon", "smp", "bedwars", "factions", "survival", "featured",
              "console", "parkour", "hardcore", "lifesteal", "oneblock", "anarchy", "minigames", "hide", "seek", "pokemon", "dragons", "mods", "addons", "shaders"]
BRANDS = ["dhgate", "moncler", "monclers", "north face", "ksubi", "chrome hearts", "louis vuitton", "lv", "rolex", "bape", "airpods", "palm angels", "neiman marcus",
          "gucci", "prada", "dior", "balenciaga", "supreme", "nike", "jordan", "yeezy", "essentials", "fear of god", "stone island", "canada goose", "arcteryx",
          "uber eats", "doordash", "shein", "instacart", "grubhub", "temu", "amazon", "cash app", "chime", "attapoll", "minecraft", "bedrock", "realms", "realm",
          "servers", "server", "cobblemon", "pixelmon", "roblox", "maya", "civic", "honda", "cartier", "omega", "kia", "bmw", "tesla", "toyota",
          "mercedes", "porsche", "ferrari", "lamborghini", "hermes", "chanel"]
DATE_RE = re.compile(r"(19|20)\d\d|january|february|march|april|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")
NEG = set("unfortunately sad scam fake expensive couldn't can't broke worst overpriced problem never hate trash bad lost empty".split())
POS = set("free best shock shocked legit insane crazy secret exactly coveted perfect amazing win huge new working".split())
ICONS = [(r"store|mall|neiman|shop|shopping|retail", "🛍️"), (r"computer|laptop|online|website|link|spreadsheet", "💻"), (r"sad|cry|unfortunately|disappoint", "😢"),
         (r"jacket|coat|puffer|hoodie|moncler|north", "🧥"), (r"jeans|pants|denim|ksubi", "👖"), (r"shoe|sneaker|jordan|yeezy", "👟"), (r"rolex|wristwatch|watches", "⌚"),
         (r"civic|honda|car", "🚗"), (r"money|price|\$|cost|expensive|paid|pay|dollars|budget|cheap", "💸"), (r"shock|crazy|insane|wild", "🤯"),
         (r"test|testing|review|check", "🔍"), (r"home|house", "🏠"), (r"box|package|shipping|order|delivered", "📦"), (r"free|code|codes|promo|coupon", "🎟️"),
         (r"friend|friends|everyone|people", "👥"), (r"phone|app|iphone", "📱"), (r"food|pizza|eat|eats|hungry", "🍕"), (r"secret|hidden|method|methods", "🤫"),
         (r"server|servers|realm|realms|world|minecraft", "⛏️"), (r"win|best|top|crown|king|reign", "👑"), (r"fire|hot|lit", "🔥"), (r"time|wait|minutes|hours", "⏰"),
         (r"empty|nothing|left", "🫥"), (r"hand|handed", "✋")]


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, errors="replace", **kw)


def trim_vo_lead(vo, out, pre=0.08, min_lead=0.15, quiet_db=-42.0):
    """Every intro VO starts right on his first word (top 5 reselling products spring 2026-10-25, 0:00: "you can hear a
    keyboard click at the start of the intro voiceover. Trim the intro VO so it starts right on my first word, and make
    that automatic for every intro"). The first VOICED run (>= 0.12 s over quiet_db: a key click is a few ms) minus `pre`;
    a lead under min_lead is left as it is. The trimmed copy lives in the build folder (his VO file is never touched);
    the word cache is dropped when the trim changes, so word times always match the audio that plays."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", vo, "-ac", "1", "-ar", "16000", "-t", "15", "-f", "s16le", "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    if len(x) < 1600:
        return vo
    H = 160   # 10 ms
    db = 20 * np.log10(np.sqrt((x[: len(x) // H * H].reshape(-1, H) ** 2).mean(1)) + 1e-9)
    loud = db > quiet_db
    start = next((i for i in range(len(loud) - 12) if loud[i:i + 12].all()), None)
    if start is None:
        return vo
    lead = max(0.0, start * 0.01 - pre)
    mark = os.path.join(out, "vo_trim.json")
    try:
        old = json.load(open(mark, encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    if lead < min_lead:
        if old.get("lead"):   # a trim used before is gone now: the cached words belong to the trimmed copy
            for f in ("vo-words.json",):
                if os.path.exists(os.path.join(out, f)):
                    os.remove(os.path.join(out, f))
            os.remove(mark)
        return vo
    dst = os.path.join(out, "vo_trimmed.wav")
    key = {"src": os.path.abspath(vo), "mtime": os.path.getmtime(vo), "lead": round(lead, 3)}
    if old != key or not os.path.exists(dst):
        os.makedirs(out, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{lead:.3f}", "-i", vo, "-af", "afade=t=in:d=0.015",
                        "-c:a", "pcm_s16le", dst], check=True)
        if os.path.exists(os.path.join(out, "vo-words.json")):
            os.remove(os.path.join(out, "vo-words.json"))   # word times were for the untrimmed VO
        json.dump(key, open(mark, "w", encoding="utf-8"))
        print(f"intro VO: {lead:.2f} s before the first word trimmed off (clicks / breath)", file=sys.stderr)
    return dst


def transcribe(vo, cache, hint=""):
    if os.path.exists(cache):
        return json.load(open(cache))
    import numpy as np
    from faster_whisper import WhisperModel
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", vo, "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    m = WhisperModel("small.en", device="cpu", compute_type="int8")
    # the video title as a hint: product names come out right ("Yeezy Slides", not "Easy Slides", 2026-10-21)
    W = [{"w": x.word.strip(), "s": round(x.start, 2), "e": round(x.end, 2)}
         for s in m.transcribe(a, word_timestamps=True, initial_prompt=hint or None)[0] for x in s.words]
    json.dump(W, open(cache, "w"))
    return W


def site_words(W):
    """Website names Whisper mishears or splits ("alley bobble" = Alibaba, reselling spreadsheet 2026-10-23) become the
    site's own name as ONE word, timed from the first to the last piece (intro_library/named_sites.json aliases)."""
    try:
        reg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "named_sites.json"), encoding="utf-8"))["sites"]
    except (OSError, ValueError, KeyError):
        return W
    al = sorted(((a.split(), s.get("name") or k.title()) for k, s in reg.items() for a in s["aliases"]), key=lambda x: -len(x[0]))
    out, i = [], 0
    while i < len(W):
        for parts, name in al:
            seg = W[i:i + len(parts)]
            if len(seg) == len(parts) and all(re.sub(r"[^a-z0-9]", "", w["w"].lower()) == p for w, p in zip(seg, parts)):
                tail = re.search(r"[.,!?]*$", seg[-1]["w"]).group(0)
                out.append(dict(seg[0], w=name + tail, e=seg[-1]["e"]))
                i += len(parts)
                break
        else:
            out.append(W[i])
            i += 1
    return out


def fix_words(W):
    W = site_words(W)
    txt = " ".join(w["w"] for w in W)
    for pat, rep in FIX:
        txt2 = re.sub(pat, rep, txt, flags=re.I)
        if txt2 != txt and len(txt2.split()) != len(txt.split()):  # a fix that merges/splits words: apply per word instead
            for w in W:
                w["w"] = re.sub(pat, rep, w["w"], flags=re.I)
            txt = " ".join(w["w"] for w in W)
        else:
            txt = txt2
    toks = txt.split()
    if len(toks) == len(W):
        for w, t in zip(W, toks):
            w["w"] = t
    # Whisper splits big amounts: "$25" ",000" (dhgate cartier watch intro 2026-10-22: the caption read "$25" then "000")
    M = []
    for w in W:
        if M and re.fullmatch(r",\d{3}[.,!?]?", w["w"]) and re.search(r"\d$", M[-1]["w"]):
            M[-1] = dict(M[-1], w=M[-1]["w"] + w["w"], e=w["e"])
        else:
            M.append(w)
    return M


def app_slip(W, title):
    """A different app named right before "promo codes / coupons" in a phone intro is a slip of the tongue: the video's own app
    goes on screen (dhgate coupons 2026-10-24: the VO said "the best working Shein promo codes" on the DHgate video, user: "I
    messed up in the audio ... just ignore that"). The video's app comes from the title."""
    try:
        sys.path.insert(0, r"{{KIT}}/tools/phone_edit")
        from events import APPS
    except Exception:
        return W
    tt = " ".join(norm(x) for x in (title or "").split())
    mine = next((k for k, a in APPS.items() if any(re.search(r"(^|\s)" + re.escape(al) + r"($|\s)", tt) for al in a["aliases"])), None)
    if not mine:
        return W
    toks = [norm(w["w"]) for w in W]
    for i, t in enumerate(toks):
        other = next((k for k, a in APPS.items() if k != mine and t in a["aliases"]), None)
        if other and any(x.startswith(("promo", "coupon", "code", "discount")) for x in toks[i + 1:i + 3]):
            tail = re.search(r"[.,!?]*$", W[i]["w"]).group(0)
            print(f"intro: '{W[i]['w']}' before promo codes on a {APPS[mine]['name']} video -> {APPS[mine]['name']} (slip)")
            W[i] = dict(W[i], w=APPS[mine]["name"] + tail)
    return W


def norm(w):
    return re.sub(r"[^a-z0-9$%']", "", w.lower())


CLAUSE_OPENERS = [("in", "today's", "video"), ("in", "todays", "video"), ("in", "this", "video"), ("today",), ("so",), ("but",),
                  ("and", "trust"), ("now",), ("let's",), ("lets",)]


def regroup_clauses(L, W, max_shift=8):
    """A line ends where its clause ends, not mid-sentence (s25 ultra 2026-10-23, 0:05: "...the Chinese factory has |
    already gotten a hold of it in today's video" - the factory shot stopped on "has" and an unrelated shot played under
    "gotten a hold of it"). When a line ends without sentence punctuation and the next line has a clause opener ("in
    today's video", "so", "but", "and trust me") within its first max_shift words, the words before that opener move
    back to the line they belong to. Beats and slots are built from the lines afterwards, so everything follows."""
    for i in range(len(L) - 1):
        a, b = L[i], L[i + 1]
        if re.search(r"[.!?]$", W[a["wi"][1]]["w"]):
            continue
        s0, s1 = b["wi"]
        toks = [norm(W[j]["w"]) for j in range(s0, s1 + 1)]
        cut = None
        for k in range(1, min(max_shift, len(toks)) + 1):
            if any(tuple(toks[k:k + len(o)]) == o for o in CLAUSE_OPENERS):
                cut = s0 + k
                break
        if cut is None or cut > s1:
            continue
        a["wi"] = [a["wi"][0], cut - 1]
        b["wi"] = [cut, s1]
        a["e"], b["s"] = W[cut - 1]["e"], W[cut]["s"]
        a["text"] = " ".join(W[j]["w"] for j in range(a["wi"][0], cut))
        b["text"] = " ".join(W[j]["w"] for j in range(cut, s1 + 1))
    return L


# things a key word can be (product nouns); names and brands are found on their own
KEY_THINGS = {"hoodie", "hoodies", "spider", "sp5der", "clothing", "clothes", "tracksuit", "shirt", "pants", "jacket", "shoes", "shoe",
              "sneakers", "jeans", "watch", "bag", "slides", "phone", "airpods", "cologne", "album", "quality", "price", "scam",
              "material", "fit", "size", "listing", "link", "links", "spreadsheet", "store", "seller"}


# what a line is ABOUT in money / shopping talk: these beat a name or the longest word (dhgate coupons 2026-10-24, 0:08 / 0:11:
# "why is the word STARTING highlighted ... the word GUYS highlighted, this makes no sense ... highlight the words that are
# actually important"). "I was starting to get a lot of fees" = FEES; "such as shipping, taxes" = SHIPPING TAXES.
KEY_CONCEPTS = {"fees", "fee", "shipping", "taxes", "tax", "cheap", "cheaper", "cheapest", "expensive", "price", "prices", "pricing",
                "checkout", "coupon", "coupons", "code", "codes", "promo", "discount", "discounts", "deal", "deals", "save", "saving",
                "savings", "money", "free", "bulk", "sale", "cost", "costs", "total", "surface", "hidden", "scam", "surprising",
                "shocking", "refund", "cashback", "bonus", "reward", "rewards", "referral", "glitch", "hack", "secret", "trick"}
# never the highlight, even as the last resort: narration and address words ("guys", "starting", "looked", "honestly")
KEY_NEVER = {"guys", "guy", "starting", "started", "start", "looked", "looking", "look", "going", "gonna", "about", "kind", "honestly",
             "actually", "really", "literally", "little", "thing", "things", "stuff", "pretty", "basically", "something", "everything",
             "anything", "name", "deeper", "soon", "seems", "seem", "want", "wanted", "know", "think", "make", "made", "show", "today",
             "video", "videos", "adding", "added", "getting", "gotten", "trying", "right", "every", "were", "been", "being", "doing"}


def analyze(W, kind, title):
    """Sentences -> lines with roles (hook/problem/turn/reveal/watch/go), key words, word classes, literal icons, beats."""
    toks = [norm(w["w"]) for w in W]
    joined = " ".join(toks)
    # word classes
    for i, w in enumerate(W):
        t = toks[i]
        two = t + " " + (toks[i + 1] if i + 1 < len(toks) else "")
        prev2 = (toks[i - 1] + " " + t) if i else t
        nxt, prv = (toks[i + 1] if i + 1 < len(toks) else ""), (toks[i - 1] if i else "")
        if DATE_RE.fullmatch(t) or (t == "may" and (re.fullmatch(r"\d+(st|nd|rd|th)?", nxt) or prv in ("of", "in"))):   # spoken dates stay in the VO, never on screen (no-dates-in-graphics)
            w["date"] = True
            continue
        if "$" in w["w"] or re.fullmatch(r"\d[\d,.]*", t) and i + 1 < len(toks) and toks[i + 1].startswith("dollar"):
            w["c"], w["k"] = "money", True
        elif t in GENERIC.get(kind, ()):
            pass
        elif t in BRANDS or two in BRANDS or prev2 in BRANDS or t.rstrip("s") in BRANDS or (kind == "gaming" and t.rstrip("s") in GAME_WORDS):
            w["c"], w["k"] = "brand", True
        elif t in NEG:
            w["c"] = "neg"
        elif t in POS:
            w["c"], w["k"] = "pos", True
    # sentences
    lines, cur = [], [0]
    for i in range(1, len(W)):
        prev = W[i - 1]
        long_ = W[i]["s"] - W[cur[0]]["s"] > 4.4 and (prev["w"][-1:] in ",;" or W[i]["s"] - prev["e"] > 0.3)
        if prev["w"][-1:] in ".!?" or W[i]["s"] - prev["e"] > 0.55 or long_:
            lines.append((cur[0], i - 1))
            cur = [i]
    lines.append((cur[0], len(W) - 1))
    # a scene per ~2-3.5 s: split long sentences at a comma, then a conjunction, then the longest pause, near the middle

    def split(a, b):
        if W[b]["e"] - W[a]["s"] <= 3.6 or b - a < 5:
            return [(a, b)]
        mid = (W[a]["s"] + W[b]["e"]) / 2
        cands = []
        for j in range(a + 2, b - 1):
            gap = W[j + 1]["s"] - W[j]["e"]
            score = abs(W[j + 1]["s"] - mid) / 2.0
            if W[j]["w"][-1:] in ",;:":
                score -= 1.5
            elif toks[j + 1] in ("but", "and", "so", "because", "which", "when", "then", "or"):
                score -= 1.0
            score -= min(gap, 0.6) * 2
            cands.append((score, j))
        j = min(cands)[1]
        return split(a, j) + split(j + 1, b)
    lines = [p for a, b in lines for p in split(a, b)]
    L = []
    for a, b in lines:
        text = " ".join(W[j]["w"] for j in range(a, b + 1))
        L.append({"s": W[a]["s"], "e": W[b]["e"], "wi": [a, b], "text": text, "role": "reveal"})
    # merge tiny fragments (< 0.9 s) into the previous line
    M = []
    for ln in L:
        if M and ln["e"] - ln["s"] < 0.9 and ln["wi"][1] - ln["wi"][0] < 2 and not re.search(r"let.?s (go|get)", ln["text"], re.I):
            M[-1]["e"], M[-1]["wi"][1], M[-1]["text"] = ln["e"], ln["wi"][1], M[-1]["text"] + " " + ln["text"]
        else:
            M.append(ln)
    L = M
    low = lambda ln: " ".join(toks[ln["wi"][0]:ln["wi"][1] + 1])
    turn_i = next((i for i, ln in enumerate(L) if re.search(r"in today'?s|today'?s video|in this video|but today|today i'?m|today we", low(ln))), None)
    if turn_i is None:
        turn_i = next((i for i, ln in enumerate(L) if i and ln["s"] > W[-1]["e"] * 0.4 and re.match(r"(but|so|now)\b", low(ln))), max(1, int(len(L) * 0.55)))
    for i, ln in enumerate(L):
        ln["role"] = "hook" if i == 0 and turn_i > 0 else "problem" if i < turn_i else "turn" if i == turn_i else "reveal"
        lw = low(ln)
        if re.search(r"watch .*end|to the (very )?end|stick around", lw):
            ln["role"] = "watch"
        if re.search(r"let'?s go|let'?s get (into|started)|let'?s jump|let'?s dive|let'?s get it", lw):
            ln["role"] = "go"
        # key phrase: brand/money words first, else the longest content word
        ws = list(range(ln["wi"][0], ln["wi"][1] + 1))
        # the highlighted word is the THING the line is about (best sp5der hoodie 2026-10-23, 0:08: "it's just highlighting
        # random words ... 'pressed' ... 'forgettable' but the product line isn't forgettable, it's just the album"): a brand /
        # price, then a name he says (capitalised, not the line's first filler word), then a product word, then the noun after
        # this/these/that ("this clothing line"), then a positive word. Only then the longest content word, marked weak
        # (templates may leave a weak key off the screen).
        keys = [j for j in ws if W[j].get("c") in ("money", "brand")]
        # a capitalised month is not a name (dhgae prada glasses 2026-10-25: "I know it's November" put NOVEMBER on a label)
        names = [j for j in ws if re.sub(r"[^\w']", "", W[j]["w"])[:1].isupper() and not W[j].get("date") and toks[j] not in STOP and toks[j] not in ("i", "i'm", "i've", "i'll", "let's")
                 and len(toks[j]) > 2 and not (j == ws[0] and toks[j] in ("but", "so", "and", "now", "then"))]
        prod = [j for j in ws if toks[j] in KEY_THINGS or toks[j].rstrip("s") in KEY_THINGS]
        if prod and prod[0] + 1 <= ws[-1] and toks[prod[0] + 1] in ("line", "brand", "collection", "hoodie", "hoodies", "tracksuit"):
            prod = [prod[0], prod[0] + 1]   # "clothing line", "spider hoodie": the word with its noun
        demo = [j + 1 for j in ws[:-1] if toks[j] in ("this", "these", "that", "those") and toks[j + 1] not in STOP and len(toks[j + 1]) > 2]
        ln["key_weak"] = False
        conc = [j for j in ws if (toks[j] in KEY_CONCEPTS or (toks[j] == "check" and j + 1 <= ws[-1] and toks[j + 1].startswith("out")))
                and not W[j].get("date")]
        conc = [x for j in conc for x in ([j, j + 1] if toks[j] == "check" else [j])]   # "check out" = checkout
        keys = keys or conc[:2] or names[:2] or prod[:2] or [j for j in demo[:1] for j in ([j, j + 1] if j + 1 <= ws[-1] and toks[j + 1] not in STOP and toks[j + 1] in KEY_THINGS | {"line", "brand", "collection", "piece"} else [j])]             or [j for j in ws if W[j].get("c") == "pos"]
        if not keys:
            cont = [j for j in ws if not W[j].get("date") and toks[j] not in STOP and toks[j] not in GENERIC.get(kind, ()) and len(toks[j]) > 2
                    and not toks[j].endswith(("ly", "'s")) and toks[j] not in KEY_NEVER]
            keys = sorted(cont, key=lambda j: -len(toks[j]))[:1]
            ln["key_weak"] = True
        keys = [j for j in keys if toks[j] not in KEY_NEVER]
        # a weak (longest-word) key is never highlighted: scenes show the line itself instead of a random word
        for j in ([] if ln["key_weak"] else keys[:3]):
            W[j]["k"] = True
        ln["key"] = re.sub(r"'s\b", "", " ".join(re.sub(r"[^\w$%'&,.-]", "", W[j]["w"]).strip(",.") for j in sorted(keys[:2]))) if keys else ""
        ln["keyT"] = W[sorted(keys)[0]]["s"] if keys else ln["s"]
        ln["icon"] = ""   # no emoji in intros (user 2026-10-21: "very, very weird"); scenes draw their own icons
        m = re.search(r"\$\s?[\d,]+(\.\d+)?", ln["text"])
        ln["money"] = m.group(0).replace(" ", "") if m else ""
    beats = {"turn": L[turn_i]["s"] if turn_i < len(L) else W[-1]["e"] * 0.6}
    go = next((ln for ln in L if ln["role"] == "go"), None)
    if go:   # the title lands on "let's" itself, not on the start of the line that contains it
        gi = next((j for j in range(go["wi"][0], go["wi"][1] + 1) if toks[j] in ("let's", "lets") and j + 1 < len(toks)), go["wi"][0])
        beats["go"] = W[gi]["s"]
    else:
        beats["go"] = None
    wi = next((i for i, t in enumerate(toks) if t == "watch" and re.search(r"end", " ".join(toks[i:i + 8]))), None)
    if wi is not None:
        endi = next((j for j in range(wi, min(len(W), wi + 8)) if toks[j].startswith("end")), wi + 3)
        beats["watch"] = {"s": W[wi]["s"], "fill": round(max(1.0, min(1.4, W[endi]["e"] - W[wi]["s"])), 2)}
    else:
        beats["watch"] = None
    beats["money"] = [{"t": w["s"], "w": w["w"]} for w in W if w.get("c") == "money"]
    return L, beats


def _amount(txt):
    m = re.search(r"\$\s?([\d,]+(?:\.\d+)?)\s*(k|thousand|million)?", txt, re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", "") or 0)
    return v * {"k": 1e3, "thousand": 1e3, "million": 1e6}.get((m.group(2) or "").lower(), 1)


def review_graphics(L, product_price=None):
    """Generated motion graphics for review intros (dhgate cartier watch 2026-10-22: "too much of the watch. We need more
    motion, more motion graphics, different things that need to be generated"):
      price   - the retail price he says ("one costing around $25,000") counts up on a price tag, RETAIL stamp
      compare - the reveal line about the cost ("a fraction of the cost", "way cheaper") when the DHgate price is known
                (the main edit's price pop-up): retail struck through, the DHgate price slams in, a -NN% badge
    Only numbers he says himself (or the edit already shows) are used; nothing is invented."""
    mg, retail = [], None
    for ln in L:
        v = _amount(ln.get("money") or "")
        # ONE price card per intro (balenciaga 2026-10-26: "$1,000" then "$120" got the same card back to back, "I don't
        # think we need two of them ... we use the same card twice"); a later price stays a plain glowing caption
        if v and v >= 50 and ln["role"] not in ("go", "watch") and len(mg) < 1:
            retail = retail or v
            # the tag swings in ON the number he says, showing only that number (no count-up: dhgate cologne spread
            # 2026-10-25, the tag read $156 while he said "$200"); the stamp says what the number is: a resale price
            # ("reselling them for as high as $200") is not a retail price
            hit = ln.get("keyT", ln["s"])
            t = max(ln["s"] + 0.1, hit - 0.25)
            nxt = next((x["s"] for x in L if x["s"] > ln["s"]), ln["e"] + 0.6)
            lab = "RESALE" if re.search(r"\bresell|\bresale|\bflip|\bsell(ing)? (them|it|these) for", ln["text"], re.I) else "RETAIL"
            mg.append({"type": "price", "t": round(t, 2), "hit": round(hit, 2), "e": round(max(hit + 1.0, min(nxt, t + 3.4)), 2), "value": v, "label": lab})
    if retail and product_price and product_price < retail:
        for i, ln in enumerate(L):
            if ln["role"] in ("reveal", "turn") and re.search(r"fraction|cheaper|less than|the cost|for only|half the|save|price", ln["text"], re.I):
                nxt = L[i + 1]["s"] if i + 1 < len(L) else ln["e"] + 0.6
                mg.append({"type": "compare", "t": round(ln["s"] + 0.1, 2), "e": round(max(ln["s"] + 2.0, nxt), 2), "from": retail, "to": float(product_price),
                           "off": max(1, min(99, int(round(100 * (1 - product_price / retail)))))})
                break
    return mg


# ---------- the editor's toolkit (channel intro study 2026-10-24, _references/channel/STUDY.md): the moves his human editor
# used that our intros lacked. Each is tied to HIS words on that line; at most one of each per intro, never on go/watch lines.
STAMP_RE = re.compile(r"\b(gate ?keep(?:er|ers|ing)?|scam(?:med|mers?)?|fake|legit|sold out|overpriced|rip(?:ped)? ?off|exposed|banned|"
                      r"trash|worth it|secret|game ?changer)\b", re.I)
CHART_RE = re.compile(r"\b(high(?:est)? profit|profit(?:able|s)?|trend(?:ing|s)?|lucrative|grow(?:ing|th)?|blow(?:ing)? up|skyrocket\w*|"
                      r"in demand|demand|popular|going up|selling out)\b", re.I)
RAIN_RE = re.compile(r"\b(a few thousand|thousands?|make (?:money|bank|a killing)|making (?:money|bank)|earn(?:ing)?|cash ?flow|"
                     r"stack(?:ing)? (?:money|cash)|bag)\b", re.I)


def _word_time(W, ln, phrase):
    """When the first word of `phrase` is said inside line ln (else the line start)."""
    first = norm(phrase.split()[0]) if phrase else ""
    hit = next((w["s"] for w in W if ln["s"] - 0.05 <= w["s"] < ln["e"] + 0.05 and norm(w["w"]).startswith(first[:6])), None)
    return hit if hit is not None else ln["s"]


def editor_graphics(L, W, taken=()):
    """Stamp / chart / money-rain graphics on the lines whose words call for them. `taken` = (t, e) spans already holding a
    graphic (the price tag), never overlapped."""
    out, used = [], set()
    busy = list(taken)
    for i, ln in enumerate(L):
        if ln["role"] in ("go", "watch"):
            continue
        nxt = L[i + 1]["s"] if i + 1 < len(L) else ln["e"] + 0.5
        for kind, rx in (("stamp", STAMP_RE), ("chart", CHART_RE), ("rain", RAIN_RE)):
            if kind in used:
                continue
            m = rx.search(ln["text"])
            if not m:
                continue
            t = _word_time(W, ln, m.group(1))
            e = min(nxt, t + (2.0 if kind == "chart" else 1.6))
            if e - t < 0.7 or any(t < b and e > a for a, b in busy):
                continue
            label = m.group(1).upper().replace("GATE KEEP", "GATEKEEP")
            if kind == "stamp" and label.startswith("GATEKEEP"):
                label = "GATEKEEPER" if not label.endswith("ING") else "GATEKEEPING"
            if kind == "chart":
                label = "HIGH PROFIT" if "PROFIT" in label else label
            out.append({"type": kind, "t": round(t, 2), "e": round(e, 2), "label": label, "line": i})
            used.add(kind)
            busy.append((t, e))
            break
    return out


def fx_plan(L, beats, dur, mg=()):
    """3-4 professional transitions (light leak / flash) on the big beats: the turn ("but in today's video"), the first stamp / chart, one cut in the
    middle of the problem part, and the hand-over at the end. Visual only (no whoosh: phone intros have none inside)."""
    # NO orange burst / fire (user 2026-10-24, coupons 0:09 + reselling 0:15: "I don't like that orange thing ... it looks kind
    # of cheap"): smoke puff and cyan swirl only
    # and NO cartoon smoke puff / swirl either (same day: "remove the cartoon smoke puff too. Keep only effects that look
    # professional"): a soft white light-leak sweep and a white flash, the kind his approved intros already use
    kinds = ["lightleak", "flash"]
    ts = []
    if beats.get("turn"):
        ts.append(beats["turn"])
    ts += [g["t"] for g in mg if g["type"] in ("stamp", "chart")][:1]
    mids = [ln["s"] for ln in L if ln["role"] == "problem" and 2.0 < ln["s"] < (beats.get("turn") or dur) - 2.0]
    if mids:
        ts.append(mids[len(mids) // 2])
    ends = [ln["s"] for ln in L if ln["role"] in ("go", "watch")]
    if ends:
        ts.append(ends[0])
    out = []
    for t in sorted(set(round(x, 2) for x in ts if 0.8 < x < dur - 0.3)):
        if all(abs(t - o["t"]) > 2.5 for o in out):
            out.append({"t": t, "kind": kinds[len(out) % len(kinds)]})
    return out[:4]


def strip_dates(s):
    s = re.sub(r"\b(19|20)\d{2}\b", "", s)
    s = re.sub(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b", "", s, flags=re.I)
    return re.sub(r"\s{2,}", " ", s).strip(" -|·")


# ---------------------------------------------------------------- audio
def lufs(path, ss=0.0, t=None, vol=1.0):
    cmd = ["ffmpeg", "-v", "info", "-ss", str(ss)] + (["-t", str(t)] if t else []) + ["-i", path, "-af", f"volume={vol},ebur128", "-f", "null", "-"]
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", run(cmd).stderr)
    return float(m[-1]) if m else -14.0


def steady_start(track, need):
    import numpy as np, scipy.signal as ss
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", track, "-t", "180", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    b, aa = ss.butter(4, 150 / 4000)
    bass = ss.lfilter(b, aa, a)
    w = 4000
    eb = np.array([20 * np.log10(np.sqrt((bass[i:i + w] ** 2).mean()) + 1e-9) for i in range(0, len(a) - w, w)])
    ok = eb > np.median(eb) - 8
    n = int(need * 2)
    for i in range(8, max(9, len(ok) - n)):
        if ok[i:i + n].mean() > 0.93:
            return i * 0.5
    return 6.0


def pick_music(kind, forced=None, avoid=(), title="", out=None):
    """The intro's track from the WHOLE {{MUSIC_ROOT}} library (_tools/music_lib.py: mood from the type, title and transcript,
    vocal-scanned, not used by the channel's last 15 videos; user 2026-10-24 "we've been using the same tracks over and
    over again"). Never one he turned down for this video (extra.json "avoid_music", from the Studio's
    settings.intro_music_skip: s25 ultra 2026-10-23, "let's try a different soundtrack" got the same Drake beat back
    because the rotation's first fresh track was that one). The old fixed rotation below is the fallback."""
    if forced:
        return forced
    try:
        sys.path.insert(0, os.path.dirname(HERE))
        import music_lib
        got = music_lib.pick_for(out or os.getcwd(), kind=kind, n=1, title=title or None, avoid=avoid, min_len=20, role="intro")
        if got:
            print(f"intro music: {os.path.basename(got[0])} (music_lib)")
            return got[0]
    except Exception as e:   # the picker never stops an intro build
        print(f"music_lib skipped: {type(e).__name__}: {str(e)[:160]}")
    bad = {os.path.normcase(os.path.normpath(a)) for a in avoid or ()}
    hist_p = os.path.join(STATE, "music.json")
    hist = json.load(open(hist_p)) if os.path.exists(hist_p) else {}
    used = hist.get(kind, [])
    pool = [m for m in MUSIC[kind] if os.path.exists(m) and os.path.normcase(os.path.normpath(m)) not in bad] or         [m for m in MUSIC[kind] if os.path.exists(m)]
    fresh = [m for m in pool if m not in used] or pool
    choice = fresh[0]
    hist[kind] = (used + [choice])[-len(pool) + 1:] if len(pool) > 1 else [choice]
    os.makedirs(STATE, exist_ok=True)
    json.dump(hist, open(hist_p, "w"), indent=1)
    return choice


CAM_CYCLE = {"gaming": ["whip", "punch", "tilt", "whip", "dolly"], "phone": ["punch", "tilt", "dolly", "punch", "whip"],
             "review": ["whip", "punch", "dolly", "punch"]}   # no tilt in reviews: it read as camera shake (s25 ultra 2026-10-23)


def plan_camera(kind, L, W, beats, dur, seed):
    """One camera move per VO line (whip / punch / tilt / dolly) + the key-word punch-in times. The turn line always punches."""
    cyc = CAM_CYCLE[kind]
    out = []
    for i, ln in enumerate(L):
        typ = cyc[(i + seed) % len(cyc)]
        if ln["role"] == "turn":
            typ = "punch"
        e = L[i + 1]["s"] if i + 1 < len(L) else dur
        keys = [W[j]["s"] for j in range(ln["wi"][0], ln["wi"][1] + 1) if W[j].get("k")]
        out.append({"t": round(max(0, ln["s"] - 0.04), 2), "e": round(e, 2), "type": typ, "keys": keys, "big": ln["role"] == "turn"})
    return out


def build_audio(kind, out, vo, beats, dur, music, cfg, tcfg, cam=None):
    A = os.path.join(out, "assets")
    tags = []
    run(["ffmpeg", "-v", "error", "-y", "-i", vo, "-af", f"loudnorm=I={cfg['vo_lufs']}:TP=-1.5", "-ar", "48000", os.path.join(A, "vo-norm.wav")])
    tags.append(f'<audio id="a-vo" src="assets/vo-norm.wav" data-start="0" data-track-index="20" data-volume="1"></audio>')
    turn = beats["turn"]
    if music:
        if cfg["music"] == "drop":
            m_main = steady_start(music, 8)
            pre_from = max(0.0, m_main - turn - 4.0)
            pre_len = max(0.1, turn - 0.26)
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{pre_from:.2f}", "-t", f"{pre_len:.2f}", "-i", music, "-af",
                 "lowpass=f=650,lowpass=f=650,afade=t=in:d=0.6", "-ar", "48000", os.path.join(A, "music-pre.wav")])
            pv = 10 ** ((cfg["bed"] + 2 - lufs(os.path.join(A, "music-pre.wav"))) / 20)
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{m_main:.2f}", "-t", f"{dur - turn:.2f}", "-i", music, "-af",
                 f"afade=t=out:st={max(0, dur - turn - 1.2):.2f}:d=1.2", "-ar", "48000", os.path.join(A, "music-main.wav")])
            mv = 10 ** ((cfg["bed"] - lufs(os.path.join(A, "music-main.wav"), 0, 8)) / 20)
            tags.append(f'<audio id="a-mpre" src="assets/music-pre.wav" data-start="0" data-duration="{pre_len:.2f}" data-track-index="21" data-volume="{pv:.3f}"></audio>')
            tags.append(f'<audio id="a-mmain" src="assets/music-main.wav" data-start="{turn:.2f}" data-duration="{dur - turn:.2f}" data-track-index="22" data-volume="{mv:.3f}"></audio>')
            json.dump({"track": music, "end": round(m_main + dur - turn, 2)}, open(os.path.join(out, "intro_music.json"), "w"))
        else:
            m0 = steady_start(music, dur + 2)
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{m0:.2f}", "-t", f"{dur:.2f}", "-i", music, "-af",
                 f"afade=t=in:d=0.4,afade=t=out:st={max(0, dur - 1.4):.2f}:d=1.4", "-ar", "48000", os.path.join(A, "music.wav")])
            mv = 10 ** ((cfg["bed"] - lufs(os.path.join(A, "music.wav"), 0, min(dur, 12))) / 20)
            tags.append(f'<audio id="a-music" src="assets/music.wav" data-start="0" data-duration="{dur:.2f}" data-track-index="21" data-volume="{mv:.3f}"></audio>')
            json.dump({"track": music, "end": round(m0 + dur, 2)}, open(os.path.join(out, "intro_music.json"), "w"))
    # sound effects: type rules + the template's own cue list
    cues = []
    if kind == "gaming":
        cues.append(("drop", turn, 0.42, 0.9))   # the ONE 808 per intro, on the drop
        # whip-ins after the drop only (nothing may build into it), at most two, quiet
        whips = [c["t"] for c in (cam or []) if c["type"] == "whip" and c["t"] > turn + 0.8][:2]
        cues += [("whip", t, 0.18, 0.6) for t in whips]
    if beats.get("watch"):
        w = beats["watch"]
        if kind == "gaming":   # the Pokémon XP fill + ding is the GAMING signature only
            cues.append(("xpfill", w["s"], 0.26, w["fill"]))
            cues.append(("xpfull", w["s"] + w["fill"], 0.28, 1.2))
        else:   # review/phone (prada cups 2026-10-22: "change this level up sound ... an asset from a gaming video"):
            # a soft notification ding at the end of the line, plus a quiet swoosh into it on reviews (phone = no whooshes)
            if kind == "review":
                cues.append(("swoosh", w["s"], 0.12, 0.7))
            cues.append(("notify", w["s"] + w["fill"], 0.2, 1.0))
    if kind in ("phone", "review") and beats.get("money"):
        for m in beats["money"][: (1 if kind == "review" else 3)]:
            cues.append(("register", m["t"], 0.3 if kind == "phone" else 0.22, 1.2))
    for c in tcfg.get("sfx", []):
        t = c.get("t")
        if isinstance(t, str):
            t = beats.get(t) if not t.startswith("end") else dur - float(t[3:] or 0.6)
        if t is None:
            continue
        cues.append((c["sfx"], float(t) + float(c.get("off", 0)), float(c.get("vol", 0.2)), float(c.get("d", 0.6))))
    os.makedirs(os.path.join(A, "sfx"), exist_ok=True)
    for k, (name, t, vol, d) in enumerate(sorted(cues, key=lambda c: c[1])):
        f = SFX.get(name, name)
        shutil.copy(os.path.join(KIT, "sfx", f), os.path.join(A, "sfx", f))
        tags.append(f'<audio id="a-sfx{k}" src="assets/sfx/{f}" data-start="{max(0, t):.2f}" data-duration="{d:.2f}" data-track-index="{30 + k}" data-volume="{vol:.2f}"></audio>')
    return tags


# ---------------------------------------------------------------- footage slots
# + a keyframe every second (remote test prada 2 2026-10-26: x264's default 250-frame GOP = 4.2 s at 60 fps; HyperFrames
# seeks the clips, captured 43 of 67 frames of one and aborted the intro render: "sparse keyframes ... seek failures")
BT709 = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-g", str(max(IFPS, 30)), "-keyint_min", str(max(IFPS, 30))]
_TRC = {}


def sdr(src):
    """Tone-map filter prefix for HDR sources (iPhone HLG B-roll). HDR-tagged clips render as a bare layer over the whole
    HyperFrames composition (asics intro, 2026-10-22: the last clip covered the captions and the title), so every clip is SDR bt709."""
    if src not in _TRC:
        _TRC[src] = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=color_transfer", "-of", "csv=p=0", src]).stdout.strip().strip(",")
    if _TRC[src] in ("arib-std-b67", "smpte2084"):
        return "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p,eq=gamma=1.12,"
    return ""


# a knock needs a WHO (other resellers / influencers / their links): "to see if it's a complete scam" is about the product and
# put another reseller's vendor page under his own DHgate line (best sp5der hoodie 2026-10-23: "never show another reseller's
# vendor link page unless I'm saying they don't have it in hand")
KNOCK_RE = re.compile(r"\b(influencers?|gurus?|youtubers?|other resellers?|other people'?s links|wrong path|vendor links|never had|"
                      r"(?:don'?t|didn'?t|never) (?:even )?ha(?:ve|d) (?:it|them|any of (?:this|it)|the \w+)(?: \w+)? in hand|"
                      r"rip(?:ping)? you off|lying|liars?)\b")
TURN_RE = re.compile(r"^\s*(but|however|so|now|that'?s why|instead|luckily|i went|i bought|i actually)\b")
CREATOR_LINE = re.compile(r"\b(influencers?|youtubers?|gurus?|creators?|tik ?tokers?|other resellers?)\b", re.I)


def plan_slots(L, beats, dur, tcfg, footage, out, label, forced=None, split=None):
    """Template asks for footage on certain line roles; every slot spans its line (until the next line starts)."""
    fc = tcfg.get("footage", {"roles": ["hook", "problem", "reveal"], "max": 6})
    roles = fc.get("roles", [])
    for f in footage or []:
        f.pop("_next_t", None)   # where a reused clip plays on from (_slot); fresh every plan
    # footage marked "must" (the product countdown) owns the first line it is meant for: no director stock, no type-only
    # there (top 5 products to resell in winter 2024: the director's "warehouse inventory shelves" replaced the countdown)
    musts = []
    for f in footage or []:
        if not f.get("must"):
            continue
        hit = next((i for i, ln in enumerate(L) if for_hit(f, ln["text"].lower())), None)
        if hit is not None:
            if forced and hit in forced and not forced[hit].get("entity"):
                forced = {k: v for k, v in forced.items() if k != hit}
            L[hit]["type_only"] = False
            L[hit]["pics"] = None
            L[hit]["prefer"] = [k for k, x in enumerate(footage) if x is f]
            musts.append(hit)
    want = [i for i, ln in enumerate(L) if ln["role"] in roles][:: fc.get("every", 1)][: fc.get("max", 6)]
    want = sorted(set(want) | set(musts))
    # the director chose kinetic type only for these lines: they get no clip of their own, but the shot before them runs on
    # under the type (lv trainer 2026-10-23: "or if they're complete trash" sat on an empty black frame, 0:17-0:19)
    type_only = {i for i in want if L[i].get("type_only")}
    want = [i for i in want if i not in type_only]
    # lines that knock other resellers / influencers, and the line right after that carries the same thought ("and the
    # crazy part is they never had | any of this stuff in hand"): marked "knock" (see _slot) until a turn ("but I went out")
    # A line that runs on from the knock (the previous line has no sentence end) or points back at THEM stays a knock
    # whatever its role (remote test prada 2026-10-26, 0:23: "influencers claiming that they | have the best link for Prada
    # sunglasses," was role "reveal", lost the knock, and his everyday-glasses clip + his own DHgate listing played under
    # "they're absolutely lying to you ... you don't want to listen to them", "doesn't make any sense").
    knock, prev = False, ""
    for ln in L:
        t = ln["text"].lower()
        runs_on = os.environ.get("RG_OFF") != "knockcont" and knock and (
            not re.search(r"[.!?]\s*$", prev) or re.search(r"\b(they|them|their|they'?re|those (people|guys))\b", t))
        # the turn can END the line before ("... you don't know about, but | in today's video,") or be the template's turn
        # line itself: the knock ends there ($30k reselling 2026-10-26: it ran on from "online influencers" (0:05) to 0:25,
        # so his $30,000 / AirPods / hoodie / cologne lines lost all his footage to other people's AirPods clips)
        turned = os.environ.get("RG_OFF") != "knockturn" and (
            ln["role"] == "turn" or re.search(r"\b(but|however)\W*$", prev)) and not re.search(r"\b(they|them|their|they'?re)\b", t)
        if KNOCK_RE.search(t):
            knock = True
        elif knock and turned:
            knock = False
        elif knock and TURN_RE.search(t) and not re.search(r"\b(they|them|their|they'?re)\b", t):
            knock = False
        elif knock and not runs_on and ln["role"] not in ("hook", "problem"):
            knock = False
        ln["knock"] = knock
        prev = t
    slots, used, uses = [], set(), []
    clips_dir = os.path.join(out, "assets", "clips")
    os.makedirs(clips_dir, exist_ok=True)
    # a line with nothing literal to show continues the shot before it when that shot is literal (asics intro 2026-10-22:
    # 10 of 14 slots were the shoe — "and honestly I had to agree" cut to the shoe in the middle of the TSA story)
    literal = lambda i: bool(forced and i in forced) or bool(L[i].get("prefer")) or any(for_hit(f, L[i]["text"].lower()) for f in (footage or []))
    groups = []
    for i in want:
        if groups and not literal(i) and L[i]["role"] not in ("turn", "go") and literal(groups[-1][0]) and i == groups[-1][-1] + 1 \
                and (L[i + 1]["s"] if i + 1 < len(L) else dur) - L[groups[-1][0]]["s"] <= fc.get("continue_max", 7.0):
            groups[-1].append(i)
        else:
            groups.append([i])
    for grp in groups:
        while grp[-1] + 1 in type_only:
            grp.append(grp[-1] + 1)
    # the intro never opens on an empty stage (remote test prada 2 2026-10-26, 0:00-0:03: the director made "Okay, so I know
    # it's November, | but I had to come on here" type only, no shot ran before them, and R13 showed its bare corkboard for
    # 2.9 s, "there's no footage at all ... just a blank background"): the first shot starts at 0. Templates with a designed
    # opener keep it (start_after: R01's smoke words; open_type: R04's front page).
    open_foot = not fc.get("start_after") and not tcfg.get("open_type") and os.environ.get("RG_OFF") != "openfoot"
    for n, grp in enumerate(groups):
        i, last = grp[0], grp[-1]
        ln = L[i]
        s = max(ln["s"] - fc.get("lead", 0.0), fc.get("start_after", 0.0))   # start_after: the opening stays on the template's own look
        if n == 0 and open_foot and 0 < s <= 6.0:
            s = 0.0
        e = L[last + 1]["s"] if last + 1 < len(L) else dur
        # maxlen never cuts a shot that runs on under type-only lines (that left an empty stage at 0:08 of the lv trainer
        # intro); the split below still keeps every piece short
        if fc.get("maxlen") and not any(j in type_only for j in grp):
            e = min(e, s + fc["maxlen"])
        # the last clip runs under the title (masked titles need live footage). Count GROUPS, not wanted lines: grouping
        # merges lines, so n never reached len(want) - 1 and "let's go" sat on the black #reveal for 0.8 s (prada cups 0:17)
        if fc.get("extend_last") and n == len(groups) - 1:
            e = dur
        # a long group on footage is cut into pieces of <= split s, each its own clip (never one 6-11 s shot)
        pieces = [(s, e)]
        # director-picked stock is split too (lv skatesta 2026-10-24: a skater clip 3.0-8.9 s and a shoe clip 8.9-13.7 s,
        # "lacking movement"); people / places he names (full) and held clips keep their one shot
        fz = forced[i] if forced and i in forced else None
        splittable = footage and (fz is None or not (fz.get("full") or fz.get("hold") or fz.get("must")))
        if split and splittable and e - s > split * 1.25:
            k = int(-(-(e - s) // split))
            cuts = [s + (e - s) * j / k for j in range(k + 1)]
            ws = [w for ln_ in L[i:last + 1] for w in [ln_["s"]]]   # line starts are the natural cut points
            cuts = [cuts[0]] + [min(ws + [c], key=lambda x: abs(x - c)) if any(abs(x - c) < 0.6 for x in ws) else c for c in cuts[1:-1]] + [cuts[-1]]
            pieces = [(a, b) for a, b in zip(cuts, cuts[1:]) if b - a >= 0.6]
        for pn, (s, e) in enumerate(pieces):   # each piece matches the line it actually sits under
            lp = max((L[j] for j in range(i, last + 1) if L[j]["s"] <= s + 0.05), key=lambda x: x["s"], default=ln)
            if fz is not None and pn > 0:
                # a later piece of a director-picked stock shot: the NEXT match for the same idea, never the same clip again;
                # no second match -> his own footage for that line
                import pics as P
                alt = P.stock_video(fz.get("tag", ""), nth=pn) if fz.get("tag") else None
                if alt and os.path.normcase(alt["file"]) != os.path.normcase(str(fz.get("src", ""))):
                    slots.append(_slot(len(slots), i, last, s, e, L, lp, label, {i: dict(fz, src=alt["file"], t=0.5)}, footage, used,
                                       uses, want, clips_dir))
                else:
                    slots.append(_slot(len(slots), i, last, s, e, L, dict(lp, prefer=None), label, None, footage, used, uses, want, clips_dir))
                continue
            # a line naming several products ("hoodies to cologne to airpod maxes") cuts to each one in the order he says
            # them (ultimate dhgate free reselling spreadsheet 2026-10-23: the line got one hoodie shot and the cologne
            # clips ended up on "sell them to your customers"); each piece matches only its own product
            ment = _product_mentions(lp["text"].lower(), footage) if footage and not (forced and i in forced) else []
            if len(ment) >= 2 and e - s >= 0.6 * len(ment):
                step = (e - s) / len(ment)
                for m, ph in enumerate(ment):
                    slots.append(_slot(len(slots), i, last, s + m * step, s + (m + 1) * step, L, dict(lp, text=ph, pics=None),
                                       label, forced, footage, used, uses, want, clips_dir))
                continue
            slots.append(_slot(len(slots), i, last, s, e, L, lp, label, forced, footage, used, uses, want, clips_dir))
    return hold_slots(slots, footage, dur)


def hold_slots(slots, footage, dur):
    """Footage with "hold": s plays at least that long, the slots after it give way (top 5 products to resell in winter 2024:
    the 2.5 s product countdown landed on the 1 s line "In today's video," and showed 2 of its 5 products). _slot already
    cut its clip at the held length; here the shots it now covers are dropped or start after it."""
    holds = {os.path.normcase(str(f["src"])) for f in footage or [] if f.get("hold")}
    if not holds:
        return slots
    out, until = [], -1.0
    for sl in slots:
        if float(sl["e"]) <= until + 0.05:
            continue                          # swallowed by the held shot
        if float(sl["s"]) < until:
            sl = dict(sl, s=round(until, 2))  # starts where the held shot ends
            if float(sl["e"]) - float(sl["s"]) < 0.6:
                continue
        if os.path.normcase(str(sl.get("from", "")).rpartition("@")[0]) in holds:
            sl = dict(sl, e=round(min(dur, float(sl["e"])), 2))
            until = float(sl["e"])
        out.append(sl)
    for n, sl in enumerate(out):
        sl["i"] = n
    return out


PHRASE_ALIAS = {"dhk": "dhgate", "dhd": "dhgate", "dhgates": "dhgate"}


def planned_shot(sl):
    """A shot placed ON PURPOSE for what the line names: the stock of a named non-product thing (the factory) or a clip of
    a named product from his other videos (the iPhone, also on the clause leading to it). The self-check never swaps
    those (s25 ultra round 6: it replaced the factory and moved the iPhone back to "too late", undoing two of his notes)."""
    tag = str(sl.get("tag", ""))
    # other creators' clips too: muted on purpose, so the eyes' "talking face with no sound" is expected (reselling
    # spreadsheet 2026-10-23: the creator clip on "these influencers" got swapped for stock "influencer filming phone")
    if tag.startswith("creator clip") or tag == "product countdown":   # the countdown is his request (top 5 products)
        return True
    return tag in {q for _, q in __import__("pics").NAMED_STOCK} | {"electronics factory"} or        (tag.startswith("product:") and sl.get("pinned") != "auto")


def _phrase_at(W, phrase, after=0.0):
    """Start time of the first run of words equal to `phrase` at or after `after` (punctuation/case ignored; Whisper's
    "DHK" = "DHgate": a pin written "dhk to see" never matched the VO's "DHgate", s25 ultra round 6)."""
    al = lambda x: PHRASE_ALIAS.get(norm(x), norm(x))
    want = [al(x) for x in phrase.split()]
    ws = [al(w["w"]) for w in W]
    for k in range(len(W) - len(want) + 1):
        if W[k]["s"] >= after - 0.01 and ws[k:k + len(want)] == want:
            return W[k]["s"]
    return None


# food / order items he names: P21 "order" graphic rows + a tap as each lands (scene.js ITEMS mirrors this list)
ITEM_RX = r"^(combo|meals?|fries|burgers?|pizzas?|drinks?|sodas?|nuggets|wings|tacos?|burritos?|sandwich(es)?|salads?|coffees?|shakes?|desserts?|sides?)$"


def knock_guard(slots, footage, L, clips_dir, label):
    """Last word on knock lines: after pins, repeat swaps and dedupe, no slot of a line knocking other resellers shows HIS
    footage (remote test prada 2026-10-26, 0:23: the repeat swap put his own product clip back on "they're absolutely lying
    to you", "doesn't make any sense"). His own pins are left alone. The swap is the least-used clip that is not his."""
    if os.environ.get("RG_OFF") == "knockguard":
        return slots
    own = lambda sl: str(sl.get("tag", "")).startswith(("product", "screen:", "store page", "listing", "his ")) \
        or any(f.get("own_page") and os.path.normcase(str(f["src"])) == os.path.normcase(str(sl.get("from", "")).rpartition("@")[0])
               for f in footage or [])
    others = [f for f in footage or [] if not f.get("own_page") and not str(f.get("tag", "")).startswith(("stock", "backdrop"))]
    count = {}
    for sl in slots:
        count[str(sl.get("tag"))] = count.get(str(sl.get("tag")), 0) + 1
    out = []
    for sl in slots:
        if L[sl["line"]].get("knock") and sl.get("pinned") != "his" and own(sl) and others:
            alt = min(others, key=lambda f: (count.get(str(f.get("tag")), 0), others.index(f)))
            j = sl["line"]
            new = _slot(sl["i"], j, j, sl["s"], sl["e"], L, dict(L[j], pics=None, prefer=None, knock=False), label, None,
                        [dict(alt)], set(), [], [j], clips_dir)
            if new.get("src"):
                print(f"intro: knock line at {sl['s']:.1f} s showed his own '{sl.get('tag')}', now '{alt.get('tag')}'", file=sys.stderr)
                count[str(alt.get("tag"))] = count.get(str(alt.get("tag")), 0) + 1
                sl = dict(new, s=sl["s"], e=sl["e"])
        out.append(sl)
    return out


def named_first_guard(slots, footage, L, clips_dir, label):
    """Last word on named products: a clip of a product he names ("for" words) never plays before the line that names it
    ($30k reselling 2026-10-26, 0:13: his AirPods under "breaking it down on how I'm able to make $30,000", 5 s before he
    says AirPods; "I didn't mention anything about AirPods yet"). The swap is the least-used clip that is not a named
    product (a page, a wall, a creator clip); his own pins stay."""
    if os.environ.get("RG_OFF") == "namedfirst" or not footage:
        return slots
    src_of = lambda x: os.path.normcase(str(x.get("from", "")).rpartition("@")[0])
    first = {}
    for f in footage:
        if str(f.get("tag", "")).startswith("product:") and f.get("for"):
            j = next((j for j, ln in enumerate(L) if for_hit(f, ln["text"].lower())), None)
            if j is not None:
                key = os.path.normcase(str(f["src"]))
                first[key] = min(first.get(key, j), j)
    others = [f for f in footage if not (str(f.get("tag", "")).startswith("product:") and f.get("for"))
              and not str(f.get("tag", "")).startswith(("stock", "backdrop"))]
    count = {}
    for sl in slots:
        count[src_of(sl)] = count.get(src_of(sl), 0) + 1
    out = []
    for sl in slots:
        j = first.get(src_of(sl))
        if j is not None and sl["line"] < j and sl.get("pinned") != "his" and others:
            ln = sl["line"]
            # the product this line DOES name, when it names one; else the least-used clip that is no named product
            own = [f for f in footage if first.get(os.path.normcase(str(f["src"]))) == ln
                   and str(f.get("tag", "")).startswith("product:") and f.get("for") and for_hit(f, L[ln]["text"].lower())]
            alt = own[0] if own else min(others, key=lambda f: (count.get(os.path.normcase(str(f["src"])), 0), others.index(f)))
            new = _slot(sl["i"], ln, ln, sl["s"], sl["e"], L, dict(L[ln], pics=None, prefer=None, knock=False), label, None,
                        [dict(alt)], set(), [], [ln], clips_dir)
            if new.get("src"):
                print(f"intro: {sl.get('tag')} at {sl['s']:.1f} s is named only on line {j}, now '{alt.get('tag')}'", file=sys.stderr)
                count[os.path.normcase(str(alt["src"]))] = count.get(os.path.normcase(str(alt["src"])), 0) + 1
                sl = dict(new, s=sl["s"], e=sl["e"])
        out.append(sl)
    return out


def line_split(slots, L, clips_dir, label):
    """A slot that runs across the next line's start is cut there, the clip playing on in the next piece, and every piece
    carries the line it plays under. Templates switch panels on line beats (R11 fades its "cold" panel out at the turn and
    mounts only slots starting after it in the reveal): remote test prada 2026-10-26, 0:20.5-0:21.9, the vendor-site slot
    started 0.5 s before the turn, faded with the cold panel, and "but they're absolutely lying to you" stood on an empty
    stage. Each line's scene in other templates shows only its own slots, same cure."""
    if os.environ.get("RG_OFF") == "linesplit":
        return slots
    line_at = lambda t: max([j for j, ln in enumerate(L) if ln["s"] <= t + 0.01] or [0])
    out = []
    for sl in slots:
        cuts = [ln["s"] for ln in L if sl["s"] + 0.2 < ln["s"] < sl["e"] - 0.2]
        src, _, t0 = str(sl.get("from", "")).rpartition("@")
        if not cuts or not src or sl.get("pinned") or not os.path.exists(src):
            out.append(dict(sl, line=line_at(sl["s"])) if not sl.get("pinned") else sl)
            continue
        edges = [sl["s"]] + cuts + [sl["e"]]
        pieces = []
        for a, b in zip(edges, edges[1:]):
            j = line_at(a)
            g = {"src": src, "t": round(float(t0 or 0) + a - sl["s"], 2), "tag": sl.get("tag"), "kind": sl.get("kind", "broll")}
            g.update(sl.get("cut") or {})
            new = _slot(sl["i"], j, j, a, b, L, dict(L[j], pics=None, prefer=None, knock=False), label, None, [g], set(), [], [j],
                        clips_dir)
            if not new.get("src"):
                pieces = None
                break
            pieces.append(dict(new, s=a, e=b))
        if pieces:
            print(f"intro: slot {sl['s']:.2f}-{sl['e']:.2f} crossed a line start, split at {', '.join(f'{c:.2f}' for c in cuts)}",
                  file=sys.stderr)
            out += pieces
        else:
            out.append(sl)
    return out


def dedupe_moments(slots, footage, L, dur, clips_dir, label, window=25.0):
    """The same B-roll never plays twice in one intro (dhgate cologne spread 2026-10-25, 0:02-0:05: "you reused the creed
    b-roll twice": his pinned Creed box @87.8, the director's box @101.0 right after it, and the self-check's fix @101.0
    again at 0:07). Two moments of one long recording (> 2 min) less than `window` s apart are the same shot (he is still
    turning the same box). The later one (never his own pin) gets the first footage moment of the same kind that is
    `window` s from every moment shown; with none left it stays and is printed."""
    src_of = lambda x: os.path.normcase(str(x.get("from", "")).rpartition("@")[0])
    t_of = lambda x: float(str(x.get("from", "")).rpartition("@")[2] or 0)
    line_end = lambda j: L[j + 1]["s"] if j + 1 < len(L) else dur
    order = sorted(slots, key=lambda x: (x.get("pinned") != "his", x["s"]))   # his pins claim their moments first
    used, out = [], []
    for sl in order:
        src, t = src_of(sl), t_of(sl)
        clash = bool(src) and _src_dur(str(sl.get("from", "")).rpartition("@")[0]) > 120 and             any(s0 == src and abs(t0 - t) < window for s0, t0 in used)
        if clash and sl.get("pinned") != "his":
            kind = str(sl.get("tag", "")).split(":")[0]
            # ...and far from every OTHER shot of the intro too, or the swap just moves the repeat later
            shown = used + [(src_of(x), t_of(x)) for x in slots if x is not sl and src_of(x)]
            free = [f for f in footage or [] if str(f.get("tag", "")).split(":")[0] == kind and not f.get("for")
                    and not (L[sl["line"]].get("knock") and f.get("own_page"))
                    and not any(s0 == os.path.normcase(str(f["src"])) and abs(t0 - float(f.get("t", 0))) < window for s0, t0 in shown)]
            if free:
                j = sl["line"]
                ln = L[j]
                new = _slot(sl["i"], j, j, sl["s"], sl["e"], L, dict(ln, pics=None, prefer=None, knock=False), label, None,
                            [dict(free[0])], set(), [], [j], clips_dir)
                if new.get("src"):
                    print(f"intro: shot at {sl['s']:.1f} s repeated {os.path.basename(src)}@{t:.1f}, now @{free[0].get('t', 0)}", file=sys.stderr)
                    new = dict(new, s=sl["s"], e=sl["e"], **({"pinned": sl["pinned"]} if sl.get("pinned") else {}))
                    sl, src, t = new, src_of(new), t_of(new)
            else:
                print(f"intro: shot at {sl['s']:.1f} s repeats {os.path.basename(src)}@{t:.1f}, no other moment left", file=sys.stderr)
        if src:
            used.append((src, t))
        out.append(sl)
    return sorted(out, key=lambda x: x["s"])


def apply_pins(slots, L, W, footage, pins, dur, clips_dir, label, no_stock=False):
    """His own intro picks win over the director (ultimate dhgate free reselling spreadsheet 2026-10-23: "at 15 s ... I want
    some type of money B-roll", "10-13 s they never had this stuff in hand ... a warehouse", "a transition between spider
    hoodie, cologne and AirPod Max ... a camera sound effect, not too loud"). A pin = {"from": phrase, "to": phrase (else the
    next pin / end of that line), one of "stock": Mixkit query | "src": file (+ "t") | "product": phrase of a product clip | "creators": true,
    "flash": white flash + quiet shutter on the cut}. Times come from the VO words, so a cut lands on the word he says.
    Returns (slots, flash times)."""
    import pics as P
    line_end = lambda j: L[j + 1]["s"] if j + 1 < len(L) else dur
    spans, after = [], 0.0
    for p in pins:
        # his pins are in speaking order (a repeated word = the next time he says it); self-check fixes search the whole VO
        a = _phrase_at(W, p.get("from", ""), (max(0.0, float(p["at"]) - 1.5) if p.get("at") is not None else 0.0)
                       if p.get("auto") else after)
        if a is None and p.get("auto") and p.get("at") is not None:
            a = _phrase_at(W, p.get("from", ""), 0.0)
        if a is None:
            print(f"pin: '{p.get('from')}' is not in the VO, skipped", file=sys.stderr)
            continue
        spans.append([max(0.0, a - 0.08), p])
        if not p.get("auto"):
            after = a + 0.01
    spans.sort(key=lambda x: x[0])
    # a self-check fix never lands inside one of his pins
    his = [x[0] for x in spans if not x[1].get("auto")]
    spans = [x for x in spans if not x[1].get("auto") or not any(abs(x[0] - h) < 0.3 for h in his)]
    # ...nor on a person / place he names (best sp5der hoodie 2026-10-23: the self-check's eyes called the Young Thug photo
    # "a talking head with no sound, not Young Thug" and swapped in concert-crowd stock): those shots are proven by Wikipedia
    named = [(sl["s"], sl["e"]) for sl in slots if sl.get("full") or planned_shot(sl)
             or str(sl.get("tag", "")).startswith(("creator clip", "screen recording: "))]   # creators / named sites stay put
    spans = [x for x in spans if not x[1].get("auto") or not any(s0 - 0.1 <= x[0] < e0 - 0.1 for s0, e0 in named)]
    # ...and generic STOCK never replaces his own footage of a product (dhgate watchb spread 2026-10-24: "online shopping
    # phone" stock replaced the AP / Patek shots and played 9 s under "watches are super expensive ... Rolexes")
    # = everything that is HIS footage or a named picture: the self-check only swaps stock for stock
    own = lambda sl: not str(sl.get("tag", "")).startswith(("stock", "backdrop"))
    prod = [(sl["s"], sl["e"]) for sl in slots if own(sl)] +            [(ln["s"], line_end(j)) for j, ln in enumerate(L) if ln.get("pics")]   # a real picture of what the line names
    spans = [x for x in spans if not (x[1].get("auto") and x[1].get("stock")) or not any(s0 - 0.1 <= x[0] < e0 - 0.1 for s0, e0 in prod)]
    out, flashes, drop = [], [], []
    for k, (a, p) in enumerate(spans):
        nxt = spans[k + 1][0] if k + 1 < len(spans) else None
        to = _phrase_at(W, p["to"], a + 0.1) if p.get("to") else None
        if to is not None:
            b = to - 0.08
        elif nxt is not None and nxt - a <= 8:   # runs until his next pick ("money ... up to 20 s, then the spider hoodie")
            b = nxt
        else:
            here = next((j for j in range(len(L)) if L[j]["s"] <= a + 0.1 < line_end(j)), len(L) - 1)
            b = line_end(here)
        if nxt is not None:
            b = min(b, nxt)
        if p.get("auto") and p.get("stock"):   # a stock fix never runs past the line it starts on
            here = next((j for j in range(len(L)) if L[j]["s"] <= a + 0.1 < line_end(j)), None)
            if here is not None:
                b = min(b, line_end(here))
        if b - a < 0.3:
            continue
        if p.get("stock") and p.get("auto") and no_stock:
            # no stock in this template (P21): the fix is one of HIS phone-app clips not on screen yet, else the shot goes and
            # the line shows its designed graphic (Uber codes october 2026-10-25: the self-check swapped his pages for "some
            # irrelevant person cooking")
            used = {str(x.get("from", "")) for x in list(slots) + out}
            own = [x for x in footage or [] if str(x.get("tag", "")).startswith("phone") and f"{x['src']}@{x['t']}" not in used]
            f = dict(own[0]) if own else None
            if not f:
                drop.append((a, b))
                continue
        elif p.get("stock"):
            hit = P.stock_video(p["stock"], allow_cash=not p.get("auto"))
            f = {"src": hit["file"], "t": float(p.get("t", 0.5)), "tag": "stock: " + p["stock"], "kind": "broll", "no_stab": True} if hit else None
            if not f and p.get("auto"):
                # the self-check said the shot is wrong: a miss must not keep it (s25 ultra 2026-10-23, 0:08-0:13: his Studio
                # link page stayed because "online shopping app" found no stock). Fall back to his own product footage,
                # a different clip per fix so two fixes in a row don't repeat
                own = [x for x in footage or [] if str(x.get("tag", "")) == "product" and not x.get("for")]
                f = dict(own[(k * 3 + 1) % len(own)]) if own else None
        elif p.get("src"):
            f = {"src": p["src"], "t": float(p.get("t", 0)), "tag": p.get("tag", "pinned clip"), "kind": "broll",
                 "no_stab": bool(p.get("no_stab")), "crop": p.get("crop", "")}   # crop "right"/"left": one half of a side-by-side recording; a still page / photo pan is never "stabilised" (it fought the pan)
            # a pinned clip shorter than its pin ends the pin (canada goose jacket 2026-10-24: a 4 s clip pinned over 5.2 s
            # left a 0.2 s slice past its end, an empty mp4, and the whole intro render failed)
            try:
                cd = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                           p["src"]], capture_output=True, text=True).stdout.strip())
                b = min(b, a + max(0.3, cd - f["t"] - 0.1))
            except (ValueError, OSError):
                pass
        elif p.get("creators"):
            # the creator clips found for this video, whatever file they are this build (reselling spreadsheet 2026-10-23:
            # "put the influencers there", right after the first scroll, not at 0:37 under "sell them to your customers")
            hits = [x for x in footage or [] if str(x.get("tag", "")).startswith("creator clip")]
            f = dict(hits[0]) if hits else None
        else:
            # only real product footage answers a product pin: a screen moment tagged by its keyword ("screen: ultra", his
            # Studio link page) matched "samsung galaxy s25 ultra" and covered three lines (s25 ultra 2026-10-23 round 6)
            prod = lambda x: str(x.get("tag", "")).startswith("product") or x.get("own")
            hits = [x for x in footage or [] if prod(x) and for_hit(x, p.get("product", "").lower())] or                    [x for x in footage or [] if str(x.get("tag", "")) == "product" and not x.get("for")]
            if p.get("auto"):
                # a self-check fix never answers with the clip it just called wrong (dhgae prada glasses 2026-10-25, 0:12: it
                # flagged his other video's talking shot under "I actually had a pair here" and its "product: prada
                # sunglasses" fix picked that same clip again, "the B-roll doesn't make any sense"); then this video's own
                # product-camera footage, at a moment no other shot of the intro plays
                bad = {os.path.normcase(str(sl.get("from", "")).rpartition("@")[0]) for sl in slots
                       if sl["s"] - 0.1 <= a < sl["e"] - 0.1 and sl.get("from")}
                hits = [x for x in hits if os.path.normcase(str(x["src"])) not in bad]
                used = [(os.path.normcase(str(sl.get("from", "")).rpartition("@")[0]), float(str(sl.get("from", "")).rpartition("@")[2] or 0))
                        for sl in list(slots) + out if sl.get("from")]
                free = [x for x in footage or [] if str(x.get("tag", "")) == "product" and not x.get("for")
                        and not any(s0 == os.path.normcase(str(x["src"])) and abs(t0 - float(x.get("t", 0))) < 3 for s0, t0 in used)]
                hits = hits or free
            f = dict(hits[0]) if hits else None
        # never the same moment twice (dhgate watchb spread 2026-10-24: three self-check fixes fell back to "the first
        # product clip" and the Cartier wrist shot @437.3 played at 3 s, 9 s and 11 s: "I used this clip twice"): a clip
        # whose moment is already on screen plays on from past it, else the next one, else the pin is skipped
        if f and p.get("auto"):   # HIS pins always play what he picked (watch spreadsheet r2: his AP pin became a grid)
            taken = [(os.path.normcase(str(x.get("from", "")).rpartition("@")[0]), float(str(x.get("from", "")).rpartition("@")[2] or 0),
                      float(x["e"]) - float(x["s"])) for x in list(slots) + out if x.get("from")]
            src_n = os.path.normcase(str(f["src"]))
            # a long recording (> 2 min) is one shot for 25 s either side (dhgate cologne spread 2026-10-25: the fix for an empty
            # desk at 0:26 picked the Creed box @101.0, 13 s from the box @87.8 that opens the intro, "reused the creed b-roll")
            near = 25.0 if _src_dur(f["src"]) > 120 else 3.0
            clash = [t0 + d0 for s0, t0, d0 in taken if s0 == src_n and t0 - near < float(f.get("t", 0)) < t0 + d0 + near]
            if clash:
                nt = max(t0 + d0 for s0, t0, d0 in taken if s0 == src_n) + 1.0
                # (playing on past the last shown moment only makes sense in a short clip; in a long recording that is any
                # random moment, a screen page or an empty desk)
                if near < 25.0 and nt + (b - a) <= _src_dur(f["src"]) - 0.2:
                    f = dict(f, t=round(nt, 2))
                else:
                    alts = [x for x in footage or [] if os.path.normcase(str(x["src"])) not in {s0 for s0, _, _ in taken}
                            and str(x.get("tag", "")).startswith(("product", "stock", "screen"))]
                    f = dict(alts[0]) if alts else None
        if not f:
            print(f"pin: nothing found for {p}, the director's shot stays", file=sys.stderr)
            continue
        # one slot per VO line it crosses (each line's scene shows only its own slots), the clip running on across them
        off = 0.0
        for j, ln in enumerate(L):
            s, e = max(a, ln["s"]), min(b, line_end(j))
            if e - s < 0.2:
                continue
            g = dict(f, t=round(f["t"] + off, 2))
            sl = _slot(len(slots) + len(out), j, j, s, e, L, dict(ln, pics=None, prefer=None, knock=False), label, None, [g],
                       set(), [], [j], clips_dir)
            if sl.get("src"):
                sl["pinned"] = "auto" if p.get("auto") else "his"
                out.append(sl)
            off += e - s
        if p.get("flash") and a > 0.3:
            flashes.append(round(a + 0.08, 2))
    # the pinned stretches replace whatever the director put there (a dropped stretch = no clip, its line's graphic shows)
    keep = []
    for sl in slots:
        s, e = sl["s"], sl["e"]
        for x in out + [{"s": a_, "e": b_} for a_, b_ in drop]:
            if x["s"] <= s + 0.05 and e <= x["e"] + 0.05:
                s = e   # fully covered
            elif s < x["s"] < e:
                e = x["s"]
            elif s < x["e"] < e:
                s = x["e"]
        if e - s >= 0.3:
            keep.append(dict(sl, s=round(s, 2), e=round(e, 2)))
    allslots = sorted(keep + out, key=lambda x: x["s"])
    # a director shot cut down to a sliver by a pin (< 0.8 s) is a flash, not a shot (watch spreadsheet r2, 0:07: the AP
    # photo for half a second under "secret", 3 s before "APs"): the shot before it plays on instead
    # ...and a shot from the SAME video right after his pinned one is that pin playing on, not a jump to another moment of
    # the same spin (watch spreadsheet 2026-10-24, 12.2 s: the pinned Patek @1.4 then the director's Patek @20.4)
    src_of = lambda x: os.path.normcase(str(x.get("from", "")).rpartition("@")[0])
    t_of = lambda x: float(str(x.get("from", "")).rpartition("@")[2] or 0)
    # ...but only the SAME moment playing on (within 6 s of where the pin's clip has got to), and never past 3.5 s of one
    # shot (dhgate cologne spread 2026-10-25, 0:08: the pinned Creed box swallowed the director's next two shots because
    # they were other moments of the same 9-min recording, raw/camera.mp4, and one box shot sat 8.4 s, "lasting way too long")
    # (a short B-roll spin is one shot whatever moment: the Patek rule above stays for clips under 2 min)
    def same_shot(pin, sl):
        if not src_of(sl) or src_of(sl) != src_of(pin):
            return False
        try:
            long_rec = _src_dur(str(pin.get("from", "")).rpartition("@")[0]) > 120
        except Exception:  # noqa
            long_rec = False
        return not long_rec or (abs(t_of(sl) - (t_of(pin) + sl["s"] - pin["s"])) < 6.0 and sl["e"] - pin["s"] <= 3.5)
    trimmed = []
    for sl in allslots:
        if not sl.get("pinned") and trimmed and ((sl["e"] - sl["s"] < 0.8) or
                                                 (trimmed[-1].get("pinned") and same_shot(trimmed[-1], sl))):
            trimmed[-1]["e"] = sl["e"]
            continue
        trimmed.append(sl)
    allslots = trimmed
    # faster pacing means more shots from the same footage: a shot that repeats an earlier one (the same video within 6 s,
    # the product grid again, the Apple Watch listing a second after its pin) gets an unused clip instead (watch
    # spreadsheet 2026-10-24: 19% repeats after the split went 2.6 -> 1.4 s)
    def _at(x):
        src_, _, t_ = str(x.get("from", "")).rpartition("@")
        try:
            return os.path.normcase(src_), float(t_ or 0)
        except ValueError:
            return os.path.normcase(src_), 0.0
    seen_, fresh = [], []
    for sl in allslots:
        src_, t_ = _at(sl)
        rep = src_ and any(src_ == a and abs(t_ - b) < 6.0 + d for a, b, d in seen_)
        if rep and not sl.get("pinned"):
            used_src = {(a, round(b)) for a, b, _ in seen_}
            alt = next((x for x in footage or [] if not any(os.path.normcase(str(x["src"])) == a and abs(float(x.get("t", 0)) - b) < 6.0
                                                            for a, b, _ in seen_)
                        and not str(x.get("tag", "")).startswith(("stock", "backdrop"))
                        and not (L[sl["line"]].get("knock") and x.get("own_page"))), None)
            if alt is not None:
                j = sl["line"]
                nsl = _slot(sl["i"], j, j, sl["s"], sl["e"], L, dict(L[j], pics=None, prefer=None, knock=False), label, None,
                            [dict(alt)], set(), [], [j], clips_dir)
                if nsl.get("src"):
                    sl = nsl
                    src_, t_ = _at(sl)
        seen_.append((src_, t_, sl["e"] - sl["s"]))
        fresh.append(sl)
    allslots = fresh
    for n, sl in enumerate(allslots):
        sl["i"] = n
    return allslots, flashes


def _product_mentions(text, footage):
    """Distinct products (footage tagged "product: ...") that this line names, in the order they are said; each returned as
    the product's own phrase so the piece only matches that product's clips."""
    hits = {}
    for f in footage:
        if not str(f.get("tag", "")).startswith("product:"):
            continue
        fs = f.get("for") or []
        fs = [fs] if isinstance(fs, str) else fs
        if not fs or fs[0] in hits:
            continue
        pos = [text.find(k.lower()) for k in fs if k and k.lower() in text]
        if pos:
            hits[fs[0]] = min(pos)
    return [ph for ph, _ in sorted(hits.items(), key=lambda x: x[1])]


def _slot(n, i, last, s, e, L, ln, label, forced, footage, used, uses, want, clips_dir):
    if True:
        sl = {"i": n, "line": i, "s": round(max(0, s), 2), "e": round(e, 2), "label": label, "src": None}
        if forced and i in forced:   # a real clip of the thing the line names
            f = forced[i]
            name = f"clipv{n}-{hashlib.md5(f'{f['src']}{f.get('t', 0)}{sl['e'] - sl['s']:.2f}k'.encode()).hexdigest()[:6]}.mp4"
            dst = os.path.join(clips_dir, name)
            if not os.path.exists(dst):   # -ss: a reused story clip shows a later part, not the same opening again
                run(["ffmpeg", "-v", "error", "-y", "-stream_loop", "3", "-ss", f"{f.get('t', 0):.2f}", "-i", f["src"], "-t", f"{sl['e'] - sl['s'] + 0.4:.2f}", "-an"] + (["-vf", sdr(f["src"]).rstrip(",")] if sdr(f["src"]) else [])
                    + ["-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p"] + BT709 + [dst])
            sl["src"], sl["tag"] = f"assets/clips/{name}", f["tag"]
            sl["from"] = f"{f['src']}@{f.get('t', 0)}"   # intro_check sees repeats of director stock too
            if f.get("full"):   # a person / place he names: templates show it full frame with its name, not as another card
                sl["full"], sl["name"] = True, f.get("label", "")
        elif footage:
            lw = ln["text"].lower()
            fits = lambda f: not f.get("roles") or ln["role"] in f["roles"]   # e.g. cam clips for problem lines, phone clips for the reveal
            # a line whose named thing has its own picture ("the same price as a brand new Kia") is about THAT thing: no
            # store page for its "price" word (dhgate cartier watch 2026-10-22: 11 s of the watch store page, "too much
            # of the watch"); the page stays for the DHgate line
            cand = [] if ln.get("pics") else [k for k, f in enumerate(footage) if k not in used and for_hit(f, lw)]
            if ln.get("pics"):
                fits_ = fits
                fits = lambda f: fits_(f) and not f.get("for")
            # a clip tagged "for" a later line stays reserved for it (asics intro 2026-10-22: the store page meant for
            # "where to get the DHgate ASICS" was used up on the suitcase line)
            later = " ".join(L[j]["text"].lower() for j in want if j > last)
            free = [k for k in range(len(footage)) if k not in used and not for_hit(footage[k], later)]
            # the director (director.py) looked at the clips and named the ones that show this line: those first, an unused
            # one before a reused one, never the clip just shown
            pref = [k for k in (ln.get("prefer") or []) if k < len(footage)]
            if pref:
                cand = [k for k in pref if k not in used] or [x for x in uses if x in pref and x != (uses[-1] if uses else None)] or pref
            cand = cand or [k for k in free if fits(footage[k])] or free
            if not cand:   # more lines than clips: reuse the clip shown longest ago (never the one just before)
                order = [x for x in uses if x != (uses[-1] if uses else None) and not for_hit(footage[x], later)] or \
                        [x for x in uses if x != (uses[-1] if uses else None)]
                cand = [order[0]] if order else [0]
            # variety: never 3 slots in a row from the same KIND of source (dhgate jordan 3 2026-10-23: four web pages in a
            # row at 0:08-0:17 after four turntable spins, "it just keeps showing over and over again ... try something
            # different"). Only when a clip of another kind is free and not reserved for a later line.
            fam = lambda x: ("web" if str(x.get("tag", "")).startswith("screen recording") else "own" if x.get("own")
                             else "store" if x.get("tag") == "store page" else "cam" if x.get("crop") else "other")
            if len(uses) >= 2 and fam(footage[uses[-1]]) == fam(footage[uses[-2]]) == fam(footage[cand[0]]) \
                    and not for_hit(footage[cand[0]], lw):   # a clip meant for this very line ("stock x") still wins
                alt = [x for x in cand + free if fam(footage[x]) != fam(footage[cand[0]]) and x not in used and fits(footage[x])
                       and not for_hit(footage[x], later)]
                if alt:
                    cand = alt
            # a line knocking OTHER resellers ("selling you poor quality links") never shows his own pages or listings
            # (ultimate dhgate free reselling spreadsheet 2026-10-23, 0:08: his spreadsheet of DHgate links sat under "poor
            # quality", "that might not be good for promotion, like saying that our links are bad"): competitor pages first
            if ln.get("knock"):
                ok = lambda x: not footage[x].get("own_page")
                cand = [x for x in cand if ok(x)] or [x for x in free if ok(x) and for_hit(footage[x], lw)] or                     [x for x in free if ok(x)] or [x for x in uses if ok(x) and x != (uses[-1] if uses else None)] or                     [x for x in range(len(footage)) if ok(x)] or cand
            k = cand[0]
            again = k in used
            used.add(k)
            uses[:] = [x for x in uses if x != k] + [k]
            f = footage[k]
            # a reused clip plays ON from where it stopped, never the same moment again (lv skatesta 2026-10-24: the spin
            # IMG_0428 @0.5 opened the intro and came back at 27.5 s, "reusing the same clip over and over again")
            nt = f.get("_next_t")
            if again and nt is not None:
                # ...past any page that goes dark while it loads (coupons 2026-10-24: the continued DHgate page hit its
                # loading darkness at 2:00 and the intro showed a near-black frame at 19 s)
                d_ = sl["e"] - sl["s"]
                ok_t = next((x for x in (nt, nt + 3, nt + 6, nt + 9) if x + d_ <= _src_dur(f["src"]) and not _goes_dark(f, x, d_)), None)
                if ok_t is not None:
                    f = dict(f, t=round(ok_t, 2))
            footage[k]["_next_t"] = float(f["t"]) + (sl["e"] - sl["s"]) + 0.5
            if f.get("hold"):   # plays at least this long (hold_slots moves the next shots back)
                sl["e"] = round(max(sl["e"], sl["s"] + float(f["hold"])), 2)
            # a screen clip never jumps mid-shot (watch spreadsheet 2026-10-24: "the clips will basically play and then
            # they'll jump": a mouse-wheel scroll step / a product photo switching inside his recording): slide the window
            # to the nearest steady stretch of the same recording
            if not str(f.get("tag", "")).startswith(("stock", "backdrop", "product grid")) and not str(f["src"]).endswith(".jpg"):
                # + 1 s: the shot may still grow (a pin's leftover sliver merges into it) and R01 starts it 0.27 s early
                st_ = _steady_t(f, float(f["t"]), sl["e"] - sl["s"] + 1.6)
                if st_ != float(f["t"]):
                    f = dict(f, t=round(st_, 2))
            sl["from"] = f"{f['src']}@{f['t']}"   # intro_check: the same source clip never twice in one intro
            # how the clip was cut, so line_split re-cuts the same picture (remote test prada 2 2026-10-26: it dropped the
            # crop and the opening showed the seam of the two-camera recording)
            sl["cut"] = {k: f[k] for k in ("crop", "vf", "box") if f.get(k)}
            # handheld clips (his phone B-roll, clips from his other videos; no crop = not the tripod recording) are
            # stabilized (s25 ultra 2026-10-23: "we probably should not be shaking the camera as much ... calm it down")
            stab = not f.get("crop") and not f.get("no_stab")
            # the source file's size + mtime are in the key: a re-made source (the blurred product reel, top 5 reselling
            # products spring 2026-10-25) must never reuse clips cut from its old version (a sharp "#3 COLOGNE" played)
            _st = os.stat(f["src"]) if os.path.exists(str(f["src"])) else None
            _ver = f"{_st.st_size}-{int(_st.st_mtime)}" if _st else ""
            # keyed WITHOUT the slot number and the exact slot length: an earlier cut of the same moment that is long
            # enough is reused (top 5 reselling products spring 2026-10-25: every revision build re-cut all ~19 clips,
            # the 30 fps creator / YouTube ones through minterpolate at ~80 s each = 11 of the intro step's 18 min, only
            # because the slots had moved by fractions of a second); new cuts are rounded up to 2 s so they get reused.
            # The real length is checked: _trim_dark_tail may have shortened a cut since
            need = sl["e"] - sl["s"] + 3.0
            h_ = hashlib.md5(f"{f['src']}{_ver}{f['t']}{f.get('crop', '')}{f.get('vf', '')}sdr{'stab' if stab else ''}m5fk{IFPS}".encode()).hexdigest()[:8]
            have = sorted((int(m.group(1)), x) for x in os.listdir(clips_dir)
                          if (m := re.fullmatch(rf"clip-{h_}-L(\d+)\.mp4", x)) and int(m.group(1)) >= need
                          and _src_dur(os.path.join(clips_dir, x)) >= sl["e"] - sl["s"] + 0.4)
            cut_len = 2 * -(-need // 2)
            name = have[0][1] if have else f"clip-{h_}-L{int(cut_len)}.mp4"
            sl["src"], sl["tag"] = f"assets/clips/{name}", f.get("tag", "")
            dst = os.path.join(clips_dir, name)
            crop = {"right": "crop=iw/2:ih:iw/2:0,", "left": "crop=iw/2:ih:0:0,"}.get(f.get("crop", ""), "")
            sl["kind"] = f.get("kind") or ("phone" if f.get("crop") == "phone" else "cam" if f.get("kind") == "cam" else "broll")
            if not os.path.exists(dst) or f.get("refresh"):
                tmp = dst + ".part.mp4"   # cut to a temp name: a killed cut must never leave a broken clip behind
                vf = (f"crop={f.get('box', '504:1080:2628:0')},scale=540:-2,fps={IFPS}" if f.get("crop") == "phone"   # the mirrored phone, portrait
                      else crop + f"scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps={IFPS}") + f.get("vf", "")
                # a 29.97 / variable-rate phone clip (his iPhone .MOV B-roll) is made a steady 30 first, so a 60 fps intro shows
                # every frame exactly twice; straight to 60 repeated them unevenly and the Rolex / Patek shots stuttered (watch
                # spreadsheet 2026-10-24, 0:07-0:12: "the watch b roll for rolex ap and patek its jumpy")
                # ...and its in-between frames are GENERATED (motion interpolation), not repeated: shown twice each, a
                # turntable spin moved every other frame under a glide that moves every frame, a "jolt" (round 6: "the AP,
                # Rolex and Patek still don't spin smoothly ... like a jolt animation")
                if IFPS >= 50 and _src_fps(f["src"]) < 50:
                    vf = ("fps=30," + vf.replace(f",fps={IFPS}", "") +
                          f",minterpolate=fps={IFPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1")
                # up to 3 tries: ffmpeg can die silently mid-cut on the 2 GB recording (dhgate jordan 3 2026-10-23: exit != 0,
                # empty stderr, half-written .part; the same command ran fine right after) and that killed the whole intro
                for attempt in range(3):
                    r = run(["ffmpeg", "-v", "error", "-y", "-ss", str(f["t"]), "-t", f"{cut_len:.2f}", "-i", f["src"], "-an", "-vf", sdr(f["src"]) + vf,
                             "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p"] + BT709 + [tmp])
                    if not r.returncode and os.path.exists(tmp):
                        break
                    time.sleep(2)
                if r.returncode or not os.path.exists(tmp):
                    raise SystemExit(f"clip cut failed for {f['src']} @ {f['t']} (exit {r.returncode}): {r.stderr[-400:]}")
                if stab:
                    stabilize(tmp)
                os.replace(tmp, dst)
        else:
            sl["tag"] = ln.get("key", "")
        if sl["src"]:
            # the clip's last frame sits behind the video: a template that keeps a card up after its clip ends shows the
            # frozen shot, never the empty #111 slot (amiri jeans 2026-10-22: the cards "go black for a second" all intro)
            clip = os.path.join(clips_dir, os.path.basename(sl["src"]))
            poster = clip[:-4] + ".jpg"
            # ...and that last frame must not be a page going dark: clips are cut 3 s past their shot, and a screen recording
            # that switches windows there left a BLACK polaroid up for 2 s (asset-mix test 2026-10-25, store listing 217 -> 34)
            if _trim_dark_tail(clip, min_keep=sl["e"] - sl["s"] + 0.4) and os.path.exists(poster):
                os.remove(poster)
            if not os.path.exists(poster):
                run(["ffmpeg", "-v", "error", "-y", "-sseof", "-0.2", "-i", clip, "-frames:v", "1", "-q:v", "3", poster])
            if os.path.exists(poster):
                sl["poster"] = sl["src"][:-4] + ".jpg"
        return sl


_DUR = {}


_FPS = {}


def _src_fps(src):
    if src not in _FPS:
        r = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=avg_frame_rate", "-of", "csv=p=0", str(src)])
        try:
            n_, d_ = (r.stdout.strip().split(",")[0] or "30/1").split("/")
            _FPS[src] = float(n_) / float(d_ or 1)
        except (ValueError, ZeroDivisionError):
            _FPS[src] = 30.0
    return _FPS[src]


_STEADY = {}


def _jumps(f, t, d):
    """Frame-to-frame jumps (big sudden changes) inside [t, t+d] of a footage item, at 15 fps on a small grey copy of
    the part the intro shows (crop = one half of a side-by-side recording)."""
    import numpy as np
    key = (str(f["src"]), round(t, 2), round(d, 2), f.get("crop"))
    if key in _STEADY:
        return _STEADY[key]
    vf = {"left": "crop=iw/2:ih:0:0,", "right": "crop=iw/2:ih:iw/2:0,"}.get(f.get("crop") or "", "")
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{max(0.0, t):.2f}", "-t", f"{d:.2f}", "-i", str(f["src"]), "-an",
                          "-vf", f"{vf}fps=15,scale=96:54,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8)
    n = len(fr) // (96 * 54)
    if n < 3:
        _STEADY[key] = 0
        return 0
    fr = fr[: n * 96 * 54].reshape(n, 54, 96).astype(float)
    dd = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
    # a smooth scroll moves ~1-3 per frame; a product photo switching spreads over 2-4 frames of 6-10 each (watch
    # spreadsheet 2026-10-24: "> 10" missed it, the intro still jumped at 6.6 s)
    base = max(0.3, float(np.median(dd)))
    _STEADY[key] = int(((dd > 4) & (dd > 8 * base)).sum())
    return _STEADY[key]


def _steady_t(f, t, d):
    """t itself when [t, t+d] has no jump, else the nearest start within 8 s that has none (t when there is none)."""
    try:
        if not _jumps(f, t, d):
            return t
        dur = _src_dur(f["src"])
        for k in range(1, 17):
            for c in (t + 0.5 * k, t - 0.5 * k):
                if 0 <= c and (not dur or c + d <= dur - 0.2) and not _jumps(f, c, d):
                    print(f"intro: steady window for {os.path.basename(str(f['src']))} @{t:.1f} -> {c:.1f} s (a jump inside the shot)")
                    return c
    except Exception as e:  # noqa: never stops a build
        print(f"intro: steady-window check failed ({e})")
    return t


def _src_dur(src):
    """Length of a source file in seconds (0 when unreadable), cached."""
    if src not in _DUR:
        r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)])
        try:
            _DUR[src] = float(r.stdout.strip())
        except (ValueError, AttributeError):
            _DUR[src] = 0.0
    return _DUR[src]


def page_groups(footage, thr=45.0):
    """A group id per footage clip: clips whose frame (1 s in, 32x18 grey) looks alike show the same page / product.
    thr 45 (coupons 2026-10-24): four scroll positions of one listing measured 18-41 apart, the homepage 71-80 from them."""
    import numpy as np
    thumbs = []
    for f in footage:
        crop = {"right": "crop=iw/2:ih:iw/2:0,", "left": "crop=iw/2:ih:0:0,"}.get(f.get("crop", ""), "")
        # a phone clip is compared on the PHONE: on the whole 3840 recording the webcam half made every phone screen
        # "the same page", and the intro dropped all but one of his app clips (Uber codes october 2026-10-25, "this intro
        # is missing b roll")
        if f.get("crop") == "phone":
            crop = f"crop={f.get('box', '504:1080:2628:0')},"
        r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{float(f.get('t', 0)) + 1:.2f}", "-i", str(f["src"]), "-frames:v", "1", "-vf",
                            crop + "scale=1920:1080" + ("" if f.get("crop") == "phone" else (f.get("vf") or "")) + ",scale=32:18,format=gray", "-f", "rawvideo", "-"], capture_output=True)
        thumbs.append(np.frombuffer(r.stdout, np.uint8).astype(float) if len(r.stdout) == 576 else None)
    gid, reps = [], []
    for th in thumbs:
        hit = next((g for g, rp in enumerate(reps) if th is not None and rp is not None and np.abs(th - rp).mean() < thr), None)
        if hit is None:
            reps.append(th)
            hit = len(reps) - 1
        gid.append(hit)
    return gid


def _trim_dark_tail(clip, min_keep=1.0):
    """Cut a clip just before its picture drops under 45% of its median brightness (a page loading dark / a window switch)
    when that happens after min_keep s. Once per clip (a .lit marker). True when the clip was trimmed."""
    mark = clip + ".lit"
    if os.path.exists(mark) or not os.path.exists(clip):
        return False
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", clip, "-vf", "fps=10,scale=32:18,format=gray", "-f", "rawvideo", "-"],
                       capture_output=True)
    b = np.frombuffer(r.stdout[:len(r.stdout) // 576 * 576], np.uint8).reshape(-1, 576).mean(axis=1)
    open(mark, "w").close()
    if len(b) < 10:
        return False
    med = float(np.median(b))
    dark = [i for i, v in enumerate(b) if med > 40 and v < 0.45 * med]
    cut = (dark[0] / 10.0 - 0.15) if dark else None
    if cut is None or cut < min_keep:
        return False
    tmp = clip[:-4] + ".trim.mp4"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", clip, "-t", f"{cut:.2f}", "-an", "-c:v", "libx264", "-preset", "fast",
                        "-crf", "18", "-pix_fmt", "yuv420p"] + BT709 + [tmp], capture_output=True)
    if r.returncode or not os.path.exists(tmp):
        return False
    os.replace(tmp, clip)
    print(f"intro: {os.path.basename(clip)} trimmed at {cut:.2f} s (its picture went dark there)")
    return True


def _goes_dark(f, t, d):
    """The clip's stretch [t, t + d] holds a frame under 45% of its median brightness (a page loading dark)."""
    crop = {"right": "crop=iw/2:ih:iw/2:0,", "left": "crop=iw/2:ih:0:0,"}.get(f.get("crop", ""), "")
    r = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-t", f"{d + 0.3:.2f}", "-i", str(f["src"]), "-vf",
                        crop + "fps=5,scale=32:18,format=gray", "-f", "rawvideo", "-"], capture_output=True)
    import numpy as np
    b = np.frombuffer(r.stdout[:len(r.stdout) // 576 * 576], np.uint8).reshape(-1, 576).mean(axis=1)
    return bool(len(b)) and np.median(b) > 40 and b.min() < 0.45 * np.median(b)


def stabilize(path, smooth=30, zoom=6):
    """Two-pass vidstab on a cut clip, in place; a failure keeps the clip as it was."""
    d, base = os.path.dirname(path), os.path.basename(path)
    trf, st = base + ".trf", base + ".stab.mp4"
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", base, "-vf", f"vidstabdetect=shakiness=6:accuracy=12:result={trf}",
                        "-f", "null", "-"], cwd=d, capture_output=True, text=True)
    if r.returncode == 0 and os.path.exists(os.path.join(d, trf)):
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", base, "-vf",
                            f"vidstabtransform=input={trf}:smoothing={smooth}:zoom={zoom}:optzoom=0:interpol=bicubic,unsharp=5:5:0.5,format=yuv420p",
                            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p"] + BT709 + [st],
                           cwd=d, capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(os.path.join(d, st)):
            os.replace(os.path.join(d, st), path)
    for x in (trf, st):
        if os.path.exists(os.path.join(d, x)):
            os.remove(os.path.join(d, x))


def brand_logos(out, title, W, brand):
    """The title lockup's pictures: the product brand's real logo + the DHgate logo (amiri jeans 2026-10-22: the ransom-note
    title was "a bit whack", "maybe like Amiri Jeans on DHgate with the DHgate logo"). Missing logo -> the name as type."""
    d = {"brand": (brand or "").strip()}
    os.makedirs(os.path.join(out, "assets", "pics"), exist_ok=True)
    if d["brand"]:
        import pics as P
        hit = P.fetch(f"{d['brand']} logo", "logo")
        if hit and hit.get("file"):
            name = "brand-logo" + os.path.splitext(hit["file"])[1]
            shutil.copy(hit["file"], os.path.join(out, "assets", "pics", name))
            d["brandLogo"] = "assets/pics/" + name
    if re.search(r"dh ?gate", (title or "") + " " + " ".join(w["w"] for w in W), re.I):
        shutil.copy(os.path.join(KIT, "logos", "dhgate.jpg"), os.path.join(out, "assets", "pics", "dhgate.jpg"))
        d["dhLogo"] = "assets/pics/dhgate.jpg"
    return d


def slot_html(slots, dur=None):
    h = []
    # no clip plays past the intro's end (remote test prada 2 2026-10-26: the last piece of a line-start split ran 0.4 s past
    # 26.68 s, HyperFrames captured 43 of its 67 frames and aborted the whole intro render, twice)
    end_all = dur if dur else max((sl["e"] for sl in slots), default=0.0) + 0.4
    # ...and every <video> id is unique: the line-start split gives its pieces the same slot number, and HyperFrames keeps
    # extracted frames per id, so two "v-slot2" clips overwrote each other's frames ("ENOENT ... v-slot2/frame_00090.jpg")
    seen_ids = {}
    for sl in slots:
        if sl["src"]:
            k = seen_ids[sl["i"]] = seen_ids.get(sl["i"], -1) + 1
            vid = f"v-slot{sl['i']}" + (f"p{k}" if k else "")
            # the video PLAYS from the moment the template starts showing it ("lead": R01 dissolves each shot in 0.27 s before
            # its word) through the template's hold after it: started at sl.s, every shot showed its last-frame poster during
            # the dissolve, then snapped back to its first frame (watch spreadsheet 2026-10-24: "jumpy one time for each, like
            # someone cut a portion out of each clip"); +0.4 covers R01's 0.32 s hold (was +0.15: a second, smaller snap)
            st0 = max(0.0, sl["s"] - float(sl.get("lead") or 0))
            # ...and its own TRACK: the pieces of a split line shared track 2+i and overlapped by the +0.4 s hold, so the
            # first piece rendered as an empty black panel (maison mahara dhgae review 2026-10-26, 0:05 and 0:10-0:11: "there's
            # black cards ... supposed to be a B-roll, but nothing showed up"; both were the first half of a split line)
            track = 2 + sl["i"] if not k else 100 + 4 * sl["i"] + k
            inner = (f'<video id="{vid}" class="clip" src="{sl["src"]}" muted playsinline data-start="{st0:.2f}" '
                     f'data-duration="{max(0.1, min(sl["e"] + 0.4, end_all) - st0):.2f}" data-track-index="{track}"></video>')
        else:
            inner = f'<div class="ph">{sl["label"]} · {sl["i"] + 1}<small>{sl.get("tag") or ""}</small></div>'
        bg = f' style="background:#111 url(\'{sl["poster"]}\') center/cover"' if sl.get("poster") else ""
        h.append(f'<div class="slot" id="slot-{sl["i"]}"{bg}>{inner}</div>')
    return "\n".join(h)


def guess_kind(W):
    """food (delivery apps) or shop (stores, marketplaces) from what the VO talks about; shop unless it is clearly food."""
    text = " ".join(norm(w["w"]) for w in W)
    return "food" if re.search(r"\b(food|restaurants?|deliver(y|ed)|pizza|burgers?|meals?|eats|groceries|dinner|lunch|takeout|hungry)\b", text) else "shop"


def detect_app(W, out, forced=None):
    """Phone videos: which app the VO is about (phone_edit apps.json aliases), with its brand colour and real App Store icon."""
    sys.path.insert(0, r"{{KIT}}/tools/phone_edit")
    try:
        from events import APPS, icon
    except Exception:
        return None
    text = " ".join(norm(w["w"]) for w in W)
    keys = [forced] if forced in APPS else [k for k, a in APPS.items() if any(al in text for al in a["aliases"]) and not a.get("no_card")]
    if not keys:
        return None
    first = lambda k: min([text.find(al) for al in APPS[k]["aliases"] if al in text] or [0])
    k = min(keys, key=first)
    a = APPS[k]

    def ic(key):
        try:
            return "assets/" + icon(key, os.path.join(out, "assets"))
        except Exception:
            return ""
    others = [{"name": APPS[o]["name"], "icon": ic(o), "accent": APPS[o]["accent"]} for o in keys if o != k][:4]
    return {"key": k, "name": a["name"], "accent": a["accent"], "icon": ic(k), "kind": a.get("kind") or guess_kind(W), "others": others,
            "items": a.get("intro_items"), "fees": a.get("intro_fees"),
            "methods": a.get("intro_methods", ["PROMO CODES", "REFERRAL $$$", "FREE TRIAL"])}


# ---------------------------------------------------------------- templates
def templates(kind=None):
    out = []
    for k in ([kind] if kind else sorted(os.listdir(TPL))):
        d = os.path.join(TPL, k)
        if not os.path.isdir(d):
            continue
        for t in sorted(os.listdir(d)):
            p = os.path.join(d, t, "template.json")
            if os.path.exists(p):
                j = json.load(open(p, encoding="utf-8"))
                j["dir"], j["type"] = os.path.join(d, t), k
                out.append(j)
    return out


def choose(kind, tid):
    ts = templates(kind)
    if tid and tid != "auto":
        m = [t for t in ts if t["id"].lower() == tid.lower() or os.path.basename(t["dir"]).lower().startswith(tid.lower())]
        if not m:
            sys.exit(f"no template {tid} for {kind}")
        return m[0]
    p = os.path.join(STATE, "rotation.json")
    rot = json.load(open(p)) if os.path.exists(p) else {}
    used = rot.get(kind, [])
    ready = [t for t in ts if t.get("status", "ready") == "ready"]
    fresh = [t for t in ready if t["id"] not in used] or sorted(ready, key=lambda t: used.index(t["id"]) if t["id"] in used else -1)
    t = fresh[0]
    rot[kind] = [x for x in used if x != t["id"]] + [t["id"]]
    os.makedirs(STATE, exist_ok=True)
    json.dump(rot, open(p, "w"), indent=1)
    return t


def apply_direction(kind, title, t, tcfg, L, W, footage, forced, out, extra):
    """Claude decides what each line shows (director.py); its decisions replace the keyword rules line by line. No answer
    (CLAUDE_BRAIN=0, offline, not signed in) = the rules above stay as they are."""
    import director
    fc = tcfg.get("footage", {"roles": ["hook", "problem", "reveal"], "max": 6})
    slot_lines = set([i for i, ln in enumerate(L) if ln["role"] in fc.get("roles", [])][:: fc.get("every", 1)][: fc.get("max", 6)])
    product = (extra or {}).get("product", "")
    # people / places he names (pics.entity_footage) stay on their line whatever the director says
    named = {i: f for i, f in (forced or {}).items() if f.get("named")}
    plan = director.direct(kind, title, product, L, footage, slot_lines, out, f"{t['id']} {t.get('name', '')}", requests=(extra or {}).get("requests", ""))
    if not plan:   # no director answer: the keyword rules stay, the named-thing stock below still applies
        plan = {}
    import pics as P
    forced = dict(forced or {})
    pj = os.path.join(out, "pics.json")
    pdata = json.load(open(pj)) if os.path.exists(pj) else {"pics": {}, "credits": []}
    for i, d in plan.items():
        ln = L[i]
        if d["show"] == "footage":
            ln["prefer"] = d["clips"]
            forced.pop(i, None)
            ln.pop("pics", None)
        elif d["show"] == "type":
            ln["type_only"] = True
            forced.pop(i, None)
            ln.pop("pics", None)
        elif d["show"] == "stock" and kind == "phone" and not tcfg.get("backdrops", True):
            # no stock in P21 (Uber codes october 2026-10-25: "some irrelevant person cooking, which doesn't make any sense"):
            # the line keeps its context graphic / his own clips instead
            ln["type_only"] = True
            forced.pop(i, None)
            ln.pop("pics", None)
        elif d["show"] == "stock" and os.environ.get("RG_OFF") != "nostockcreators" and (CREATOR_LINE.search(ln["text"]) or any(
                str(f.get("tag", "")).startswith("creator clip") and f.get("for") and for_hit(f, ln["text"].lower()) for f in footage or [])):
            # (also a line a real creator clip is MEANT for: "risen in popularity on the street" = people wearing the product,
            # never Mixkit "street style sneakers" dancers / a moped, maison mahara dhgae review 2026-10-26)
            # never stock people for the creators he talks about (remote test prada 2 2026-10-26, 0:17: "influencer filming
            # phone" stock, "we don't ever wanna use stock footage of influencers, we wanna use actual influencers"): the
            # real creator clips / YouTube search found for those words, else the shot before runs on
            ks = sorted((k for k, f in enumerate(footage or []) if f.get("for") and for_hit(f, ln["text"].lower())),
                        key=lambda k: 0 if str(footage[k].get("tag", "")).startswith("creator clip") else
                        1 if "youtube" in str(footage[k].get("tag", "")).lower() else 2)
            forced.pop(i, None)
            ln.pop("pics", None)
            if ks:
                ln["prefer"] = ks[:2]
                print(f"  L{i} creators: {footage[ks[0]].get('tag', '')} instead of stock '{d['query']}'", file=sys.stderr)
            else:
                ln["type_only"] = True
        elif d["show"] == "stock":
            hit = P.stock_video(d["query"])
            if hit:
                forced[i] = {"src": hit["file"], "t": 0.5, "tag": d["query"], "for": "", "entity": ""}
                ln.pop("pics", None)
                pdata["credits"].append(f"{hit['title']} - Mixkit ({hit['license']})")
        elif d["show"] == "picture" and kind == "review":   # only the review kit draws picture pops
            qw = d["query"].split()   # Commons wants every query word in the file title: fall back to brand + object
            hit = next((h for q in dict.fromkeys([d["query"], " ".join(qw[:1] + qw[-1:])]) if (h := P.fetch(q, d.get("kind", "photo")))), None)
            if hit:
                name = os.path.basename(hit["file"])
                os.makedirs(os.path.join(out, "assets", "pics"), exist_ok=True)
                shutil.copy(hit["file"], os.path.join(out, "assets", "pics", name))
                wt = next((W[j]["s"] for j in range(ln["wi"][0], ln["wi"][1] + 1) if d.get("word") and norm(d["word"].split()[0]) == norm(W[j]["w"])), ln["s"])
                ln["pics"] = [{"src": "assets/pics/" + name, "kind": hit["kind"], "label": d.get("word") or d["query"], "t": wt}]
                forced.pop(i, None)
                if hit.get("license"):
                    pdata["credits"].append(f"{hit['title'].replace('File:', '')} - {hit.get('artist') or 'Wikimedia Commons'} ({hit['license']}) {hit.get('page', '')}")
            else:
                # no picture of it: HIS footage of the product, never the stock of the line before running on (maison mahara
                # dhgae review 2026-10-26, 0:06: "Maison Mihara Yasuhiro sneakers" had no Commons photo, the "street style
                # sneakers" stock of line 1 carried on as a parked moped under "a pair of these will set you back")
                used = {k for x in plan.values() if x.get("show") == "footage" for k in x.get("clips", [])}
                own_k = [k for k, f in enumerate(footage or []) if f.get("own_page") and str(f.get("tag", "")).startswith("product")
                         and k not in used]
                forced.pop(i, None)
                if own_k:
                    ln["prefer"] = own_k[:2]
                    print(f"  L{i} picture '{d['query']}' not found -> his product footage [{own_k[0]}]", file=sys.stderr)
    # a clip of a product he names LATER never plays before he says it ($30k reselling 2026-10-26, 0:03-0:06: the director
    # put his AirPods under "reselling is one of the most lucrative ... business models", "I didn't mention anything about
    # AirPods yet"). Only clips tagged for a named product ("for" words); the line falls back to the free clips.
    if footage and os.environ.get("RG_OFF") != "namedfirst":
        first = {}
        for k, f in enumerate(footage):
            if str(f.get("tag", "")).startswith("product:") and f.get("for"):
                first[k] = next((j for j, ln in enumerate(L) if for_hit(f, ln["text"].lower())), None)
        for i, ln in enumerate(L):
            early = [k for k in (ln.get("prefer") or []) if k in first and first[k] is not None and first[k] > i]
            if early:
                ln["prefer"] = [k for k in ln["prefer"] if k not in early]
                print(f"  L{i} drops {early}: that product is named on a later line", file=sys.stderr)
                if not ln["prefer"]:
                    ln.pop("prefer")
    # REAL footage before designed cards (dhgate coupons 2026-10-24: with 4 of his haul clips available the director still
    # made 7 of 10 lines type / designed cards, "lacking character"). When unused clips are left, at most 4 lines stay
    # clip-free: lines a clip is meant for ("for" words) take it first, then lines with no fee / price graphic to carry them
    # templates with their own context graphics (P21 "context_gfx"): a line its graphic explains (fees -> checkout, promo
    # codes -> tickets, save -> SAVE tag, surprising -> total, "in today's video" -> app icon) keeps it; every OTHER
    # clip-free line takes an unused real clip (2026-10-24: "in the future we're going to have more footage, so we want to
    # be accommodating to that": more footage = more real clips, graphics only where they say something)
    ctx_gfx = re.compile(r"surpris|shock|crazy|believe|insane|fees?\b|shipping|tax(es)?|adding it|name it|check ?out|handling|"
                         r"\border\b|combo|meals?\b|fries|burgers?|pizza|nuggets|out of nowhere|goes (all the way )?up|\$\d|"
                         r"today'?s video|show you|going over|walk you|promo|codes?\b|coupons?|\bsav(e|ing)\b|money|cheaper|discount", re.I)
    if kind in ("phone", "review") and footage:
        TYPE_CAP = 0 if tcfg.get("context_gfx") else 4
        used_k = {k for ln in L for k in (ln.get("prefer") or [])}
        free = [k for k in range(len(footage)) if k not in used_k]
        typed = [i for i, ln in enumerate(L) if ln.get("type_only") and ln["role"] != "go" and i not in named
                 and not (tcfg.get("context_gfx") and ctx_gfx.search(ln["text"]))]
        graphic = re.compile(r"fees?\b|shipping|tax(es)?|total|\$\d|price|surpris|shock")
        def score(i):
            hit = any(for_hit(footage[k], L[i]["text"].lower()) for k in free if footage[k].get("for"))
            return (0 if hit else 1, 1 if graphic.search(L[i]["text"].lower()) else 0, i)
        for i in sorted(typed, key=score):
            if len([j for j in typed if L[j].get("type_only")]) <= TYPE_CAP or not free:
                break
            # a clip meant for this line's words, else one of the video's own pages; his haul clips only where their words
            # match (the LED lamp landed on "promo codes for the month", 2026-10-24)
            k = next((k for k in free if footage[k].get("for") and for_hit(footage[k], L[i]["text"].lower())), None)
            if k is None:
                # never another creator's clip as filler: it belongs on the line its words name (maison mahara 2026-10-26,
                # 0:12: @PrinceCarterJr's Mihara clip played under "I decided to opt for the DHgate versions")
                k = next((k for k in free if not str(footage[k].get("tag", "")).startswith(("product:", "creator clip"))), None)
            if k is None:
                continue
            free.remove(k)
            L[i].pop("type_only", None)
            L[i]["prefer"] = [k]
            print(f"  L{i} real clip  [{k}]  - {footage[k].get('tag', '')} instead of a designed card", file=sys.stderr)
    # a LIST of products in a line ("AirPods, | Spider Hoodies, and even Clone") shows each product's own clip, in the order
    # he says them, over any creator clip / page / stock the director picked ($30k reselling 2026-10-26, intro 0:20: "when
    # things are listed in the list like that, they should have pictures for them ... all I see is some supplier website")
    if kind == "review" and footage and os.environ.get("RG_OFF") != "productlist":
        used_list = set()
        for i, ln in enumerate(L):
            if ln["role"] == "go":
                continue
            low = ln["text"].lower()
            hits = []
            for k, f in enumerate(footage):
                if k in used_list or not str(f.get("tag", "")).startswith("product:") or not f.get("for"):
                    continue
                fs = f["for"] if isinstance(f["for"], list) else [f["for"]]
                pos = min((low.find(w.lower()) for w in fs if w and low.find(w.lower()) >= 0), default=-1)
                if pos >= 0 and not any(footage[h]["tag"] == f["tag"] for _, h in hits):   # one clip per product
                    hits.append((pos, k))
            if hits:
                ks = [k for _, k in sorted(hits)][:3]
                used_list.update(ks)
                ln["prefer"] = ks
                ln.pop("type_only", None)
                ln.pop("pics", None)
                forced.pop(i, None)
                print(f"  L{i} names {len(ks)} product(s) -> their clips: " + ", ".join(footage[k]['tag'] for k in ks), file=sys.stderr)
    # each PAGE once (coupons 2026-10-24: "I noticed you reuse the same clip twice"): different moments of the same listing
    # read as the same clip, so clips whose frames look alike form one group and a group shows on one line only; a later
    # line that only had that group goes to its context graphic
    if tcfg.get("page_once") and footage:
        groups = page_groups(footage)
        seen = set()
        for i, ln in enumerate(L):
            pref = ln.get("prefer") or []
            keep = [k for k in pref if k < len(footage) and groups[k] not in seen]
            if pref and not keep:
                ln.pop("prefer", None)
                ln["type_only"] = True
                print(f"  L{i} page already shown -> context graphic", file=sys.stderr)
            elif pref:
                ln["prefer"] = keep[:1]
                seen.add(groups[keep[0]])
    # P21 phone intros (Uber codes october 2026-10-25, "there should've been graphics for all this stuff on the screen"): a
    # line that names his ORDER items or the price climbing shows the order / total graphic, never a clip; a line that names
    # an app shows HIS clip of that app (intro_footage tags phone screens with the app OCR'd on them)
    if kind == "phone" and tcfg.get("context_gfx") and footage:
        story = re.compile(r"\border\b|combo|meals?\b|fries|burgers?|pizza|nuggets|out of nowhere|goes (all the way )?up|\$\d", re.I)
        taken = {k for ln in L for k in (ln.get("prefer") or [])}
        for i, ln in enumerate(L):
            if ln["role"] == "go" or i in named:
                continue
            if story.search(ln["text"]):
                if ln.get("prefer"):
                    taken -= set(ln["prefer"])
                ln.pop("prefer", None)
                forced.pop(i, None)
                ln["type_only"] = True
                print(f"  L{i} order / price line -> its graphic", file=sys.stderr)
                continue
            k = next((k for k in range(len(footage)) if k not in taken and footage[k].get("kind") == "phone"
                      and footage[k].get("for") and for_hit(footage[k], ln["text"])), None)
            if k is not None and not any(footage[j].get("kind") == "phone" and for_hit(footage[j], ln["text"]) for j in (ln.get("prefer") or [])):
                ln["prefer"] = [k]
                ln.pop("type_only", None)
                forced.pop(i, None)
                taken.add(k)
                print(f"  L{i} names the app -> his clip {footage[k].get('tag')}", file=sys.stderr)
    # the first time the VO says the product's NAME, a real photo of it pops on that word (s25 ultra 2026-10-23, 0:00: "if
    # I'm saying a product name in an intro, most likely it should appear, especially when it's the first mention ... grab
    # a phone picture online"). Commons, every query word in the file title (pics.fetch); the vision check below drops a
    # picture that isn't provably the thing.
    if kind == "review" and title:
        tw = [norm(x) for x in title.split() if norm(x) and norm(x) not in ("dhgate", "review", "reviews", "the", "best", "on", "from", "vs")]
        if tw:
            first = next((i for i, ln in enumerate(L) if all(x in [norm(y) for y in ln["text"].split()] for x in tw[:2])), None)
            if first is not None and not L[first].get("pics"):
                brand = (extra or {}).get("brand") or ""
                qs = [" ".join(tw)] + ([f"{brand} {' '.join(tw)}"] if brand and norm(brand) not in tw else [])
                hit = next((h for q in qs if (h := P.fetch(q, "photo"))), None)
                if hit:
                    name = os.path.basename(hit["file"])
                    os.makedirs(os.path.join(out, "assets", "pics"), exist_ok=True)
                    shutil.copy(hit["file"], os.path.join(out, "assets", "pics", name))
                    ln = L[first]
                    wt = next((W[j]["s"] for j in range(ln["wi"][0], ln["wi"][1] + 1) if norm(W[j]["w"]) == tw[0]), ln["s"])
                    ln["pics"] = [{"src": "assets/pics/" + name, "kind": hit["kind"], "label": " ".join(tw).upper(), "t": wt}]
                    if hit.get("license"):
                        pdata["credits"].append(f"{hit['title'].replace('File:', '')} - {hit.get('artist') or 'Wikimedia Commons'} ({hit['license']}) {hit.get('page', '')}")
    # a line that NAMES something other than the product (s25 ultra 2026-10-23: "when I said the Chinese factory's got a
    # hold of it, it was some B-roll of the Chinese factories ... too much of the phone") shows THAT thing: the director's
    # "type only" or another product shot there is overridden by stock of it
    if kind == "review":
        for i, ln in enumerate(L):
            if i in forced or ln.get("pics"):
                continue
            q = next((q for pat, q in P.NAMED_STOCK if re.search(pat, ln["text"].lower())), None)
            # the factory of THIS product: a phone is made in an electronics factory, not on a beer-bottle line
            if q == "factory production line" and re.search(r"phone|airpod|earbud|watch|tablet|laptop|console|camera|speaker|headphone|charger|ultra",
                                                           f"{product} {title}".lower()):
                q = "electronics factory"
            hit = P.stock_video(q) if q else None
            # money he or people EARN ("making upwards of $10,000", "turn a profit", "make lots of money") = money on screen,
            # a different clip per line (pics.EARN_RE; a product PRICE line keeps its product shot)
            if not hit and not q and P.EARN_RE.search(ln["text"]) and os.environ.get("INTRO_EARN_STOCK", "1") != "0":
                k = sum(1 for f in forced.values() if f.get("earn"))
                for q in P.EARN_STOCK[k % len(P.EARN_STOCK):] + P.EARN_STOCK[:k % len(P.EARN_STOCK)]:
                    hit = P.stock_video(q, allow_cash=True)
                    if hit and not any(f.get("src") == hit["file"] for f in forced.values()):
                        break
                    hit = None
                if hit:
                    forced[i] = {"src": hit["file"], "t": 0.5, "tag": "money: " + q, "for": "", "entity": "", "earn": True}
                    ln.pop("type_only", None)
                    ln.pop("prefer", None)
                    pdata["credits"].append(f"{hit['title']} - Mixkit ({hit['license']})")
                continue
            if hit:
                forced[i] = {"src": hit["file"], "t": 0.5, "tag": q, "for": "", "entity": ""}
                ln.pop("type_only", None)
                ln.pop("prefer", None)
                pdata["credits"].append(f"{hit['title']} - Mixkit ({hit['license']})")
    for i, f in named.items():
        forced[i] = f
        for k in ("type_only", "prefer", "pics"):
            L[i].pop(k, None)
    # a clip of a NAMED thing (his iPhone from another video, tag "product: iphone ...") starts where the clause that leads
    # to the word starts, not on the word: "and trust me after reviewing the | iphone I was definitely surprised" put the
    # iPhone on the second line only (s25 ultra 2026-10-23: "that clip needs to be moved earlier ... stretch that farther
    # back so it can actually show up more"). The line before gets the first of those clips, this line the next one.
    if kind == "review" and footage:
        named = lambda k: (str(footage[k].get("tag", "")).split("(")[0].split(":", 1)[1].strip()
                           if 0 <= k < len(footage) and str(footage[k].get("tag", "")).startswith("product:") else "")
        # not in a topic video that names several products (a list): each product starts ON its word ($30k reselling
        # 2026-10-26: AirPods moved back onto "how I'm able to make $30,000", 5 s before he says AirPods)
        listed = {named(k) for k in range(len(footage)) if named(k) and footage[k].get("for")}
        for i in range(1, len(L) if len(listed) < 2 or os.environ.get("RG_OFF") == "namedfirst" else 1):
            ks = [k for k in (L[i].get("prefer") or []) if named(k) and named(k) in L[i]["text"].lower()]
            prev = L[i - 1]
            if not ks or re.search(r"[.!?]$", W[prev["wi"][1]]["w"]) or prev.get("pics") or i - 1 in forced:
                continue
            if any(named(k) == named(ks[0]) for k in (prev.get("prefer") or [])):
                continue
            # never into a line that names its OWN product: in a list ("such as AirPods, | Spider Hoodies") the hoodie took
            # the AirPods line ($30k reselling 2026-10-26, 0:19)
            if os.environ.get("RG_OFF") != "namedfirst" and any(
                    named(k) and named(k) in prev["text"].lower() for k in range(len(footage))):
                continue
            prev["prefer"] = [ks[0]]
            prev.pop("type_only", None)
            L[i]["prefer"] = [k for k in L[i]["prefer"] if k != ks[0]] + [ks[0]]
    if kind == "review":
        director.check_pictures(L, out, product)
    pdata["pics"] = {str(i): ln["pics"] for i, ln in enumerate(L) if ln.get("pics")}
    pdata["credits"] = sorted(set(pdata["credits"]))
    json.dump(pdata, open(pj, "w"), indent=1)
    return forced


def plan_key(kind, tid, vo, title, footage, music, extra, pics, direct):
    """What the director's plan depends on. The self-check's auto_pins are left out: they only swap shots after planning."""
    foot = open(footage, encoding="utf-8").read() if isinstance(footage, str) and os.path.exists(footage) else json.dumps(footage)
    code = [os.path.getmtime(os.path.join(HERE, f)) for f in ("build_intro.py", "director.py", "pics.py", "director_rules.md")
            if os.path.exists(os.path.join(HERE, f))]
    ex = {k: v for k, v in (extra or {}).items() if k not in ("auto_pins", "text_fixes")}   # his text fixes never re-plan
    st = os.stat(vo)
    return hashlib.md5(json.dumps([kind, tid, os.path.abspath(vo), st.st_size, st.st_mtime, title, foot, music, ex, pics, direct, code],
                                  sort_keys=True, default=str).encode()).hexdigest()


def build(kind, tid, vo, title, out, sub="", footage=None, music=None, accent=None, seed=None, render=False, quality="looks", extra=None, pics=None,
          direct=True, reuse_plan=False):
    cfg = TYPES[kind]
    # self-check fix passes (review_intro --reuse-plan, 2026-10-23: "where most of our time is going"): the director's plan,
    # the pictures and the named-thing stock from the first pass are kept, so a fix pass only swaps the flagged shots and
    # re-renders (~1.2 min) instead of planning the whole intro again with new AI calls (~3 min, and a different plan the
    # fixes were never judged against). Any change to the VO, footage, requests, pins or the intro code = plan from scratch.
    pc = os.path.join(out, "plan_cache.pkl")
    pkey = plan_key(kind, tid, vo, title, footage, music, extra, pics, direct)
    cached = None
    if reuse_plan and os.path.exists(pc):
        try:
            c = pickle.load(open(pc, "rb"))
            cached = c if c.get("key") == pkey else None
        except Exception:   # noqa: a bad cache = plan again
            cached = None
        print("intro: reusing the first pass's plan (only the self-check's shots change)" if cached else "intro: plan cache out of date, planning again")
    req = (extra or {}).get("requests") or ""
    if cached:
        tid, title, music = cached["tid"], cached["title"], cached["music"]
    # the user's special requests (Studio, 2026-10-23): a style / title / track they ask for wins over the rotation. Phone keeps
    # its template (the pipeline picks P02 vs auto_intro from the footage); review may switch style.
    elif req and direct:
        import director
        w = director.wishes(kind, req, templates(kind), [m for m in MUSIC.get(kind, []) if os.path.exists(m)], title or "")
        if w.get("template") and kind == "review":
            tid = w["template"]
        if w.get("title"):
            title = w["title"]
        if w.get("music"):
            music = w["music"]
    t = choose(kind, tid)
    tcfg = t
    if t.get("external") == "auto_intro":   # P01: the original phone kit (phone_edit/auto_intro.py) stays the source of truth
        sys.path.insert(0, r"{{KIT}}/tools/phone_edit")
        import auto_intro
        os.makedirs(out, exist_ok=True)
        auto_intro.build(vo, strip_dates(title or ""), out, music or pick_music(kind, None, (extra or {}).get("avoid_music"), title, out) or auto_intro.DEFAULT_MUSIC)
        json.dump({"template": t["id"], "name": t.get("name"), "type": kind}, open(os.path.join(out, "intro.json"), "w"), indent=1)
        print(f"intro {t['id']} ({t.get('name')}) -> {out}  (phone_edit auto_intro)")
        return render_project(out, quality) if render else out
    os.makedirs(os.path.join(out, "assets", "fonts"), exist_ok=True)
    for fn in os.listdir(os.path.join(KIT, "fonts")):
        dst = os.path.join(out, "assets", "fonts", fn)
        if not os.path.exists(dst):
            shutil.copy(os.path.join(KIT, "fonts", fn), dst)
    vo_dst = os.path.join(out, "assets", "vo" + os.path.splitext(vo)[1])
    if not (os.path.exists(vo_dst) and os.path.samefile(vo, vo_dst)):   # a rebuild may feed the project's own VO copy back in
        shutil.copy(vo, vo_dst)
    if cached:
        W, L, beats, dur, cam, forced, footage = (cached[k] for k in ("W", "L", "beats", "dur", "cam", "forced", "footage"))
    else:
        W, L, beats, dur, cam, forced, footage = plan_lines(kind, t, tcfg, vo, title, footage, extra, pics, direct, seed, out)
        title = strip_dates(title or "")
        try:
            pickle.dump({"key": pkey, "tid": t["id"], "title": title, "music": music, "W": W, "L": L, "beats": beats, "dur": dur,
                         "cam": cam, "forced": forced, "footage": footage}, open(pc, "wb"))
        except Exception as e:   # noqa: no cache = the next pass plans again
            print(f"intro: plan cache not saved ({e})")
    title = strip_dates(title or "")
    slots = plan_slots(L, beats, dur, tcfg, footage, out, tcfg.get("slot_label", cfg["slot_label"]), forced, split=tcfg.get("split", cfg.get("split")))
    flashes = []
    # his pins first, then the self-check's fixes (intro_check.py) on the shots his pins leave alone
    pins = list((extra or {}).get("pins") or []) + list((extra or {}).get("auto_pins") or [])
    if True:   # always: with no pins it still drops slivers, merges same-video shots and swaps repeats
        slots, flashes = apply_pins(slots, L, W, footage, pins, dur, os.path.join(out, "assets", "clips"),
                                    tcfg.get("slot_label", cfg["slot_label"]), no_stock=kind == "phone" and not tcfg.get("backdrops", True))
        slots = dedupe_moments(slots, footage, L, dur, os.path.join(out, "assets", "clips"), tcfg.get("slot_label", cfg["slot_label"]))
        slots = knock_guard(slots, footage, L, os.path.join(out, "assets", "clips"), tcfg.get("slot_label", cfg["slot_label"]))
        slots = named_first_guard(slots, footage, L, os.path.join(out, "assets", "clips"), tcfg.get("slot_label", cfg["slot_label"]))
        slots = line_split(slots, L, os.path.join(out, "assets", "clips"), tcfg.get("slot_label", cfg["slot_label"]))
        # every slot its own number: the split pieces kept their slot's, K.slot(i) found the FIRST "#slot-i" for both, so
        # the second piece took the first one's video and the opening stood empty (remote test prada 2 2026-10-26, 0:00-0:01.4)
        for n, sl in enumerate(slots):
            sl["i"] = n
        # a quiet shutter on each flash cut ("make sure it's not too loud")
        tcfg = dict(tcfg, sfx=list(tcfg.get("sfx", [])) + [{"sfx": "shutter", "t": t - 0.03, "vol": 0.09, "d": 0.6} for t in flashes])
    if kind == "phone" and tcfg.get("backdrops", True):   # P21: no stock backdrops ("this girl, what is she doing", 2026-10-24)
        slots = backdrop_slots(L, slots, dur, os.path.join(out, "assets", "clips"), tcfg.get("slot_label", cfg["slot_label"]))
    return _finish(kind, cfg, t, tcfg, vo, title, out, sub, footage, music, accent, seed, render, quality, extra, W, L, beats, dur, cam, slots, flashes)


# what a phone-intro line with no clip of its own is about -> a Mixkit search for the moving picture behind its words. Never
# cash stock (pics.NO_STOCK); first match wins.
BACKDROP = [
    (r"\bsav(e|ing)\b|cheaper|discount|coupons?|promo|codes?|deals?|money|price|cost", "shopping bags"),
    (r"shipping|deliver|package|order|arriv", "delivery package"),
    (r"fees?|tax(es)?|total|check ?out|pay", "online payment"),
    (r"surpris|shock|crazy|insane|believe", "surprised woman"),
    (r"today'?s video|show you|going over|walk you|this video|let me", "typing on laptop"),
    (r"phone|app\b|apps\b|download", "using smartphone"),
    (r"search|look(ing)? for|find|google", "searching laptop"),
    (r"friends?|everyone|people|you guys", "friends shopping"),
    (r"shop|cart|store|buy|online", "online shopping"),
]


def backdrop_slots(L, slots, dur, clips_dir, label):
    """Phone intros: a line with no clip of its own gets a full-frame moving stock clip BEHIND its words (dhgate coupons
    2026-10-24: type beats on a flat light background, 30% of frames more than half empty, "lacking motion and just like
    different types of stuff going on"). The best intro (reselling spreadsheet) never puts words on an empty background.
    Each backdrop is a different clip (nth match when a search repeats); the kit plays it under the type, not as a scene."""
    import pics as P
    have = {sl["line"] for sl in slots}
    used, nth = {os.path.normcase(str(sl.get("from", "")).rpartition("@")[0]) for sl in slots}, {}
    out = list(slots)
    for i, ln in enumerate(L):
        if i in have or ln["role"] == "go":
            continue
        s, e = ln["s"], (L[i + 1]["s"] if i + 1 < len(L) else dur)
        if e - s < 0.6:
            continue
        q = next((q for pat, q in BACKDROP if re.search(pat, ln["text"].lower())), "online shopping")
        hit = None
        while nth.get(q, 0) < 4:
            hit = P.stock_video(q, nth=nth.get(q, 0))
            nth[q] = nth.get(q, 0) + 1
            if not hit or os.path.normcase(hit["file"]) not in used:
                break
            hit = None
        if not hit:
            continue
        used.add(os.path.normcase(hit["file"]))
        sl = _slot(len(out), i, i, s, e, L, ln, label, {i: {"src": hit["file"], "t": 0.5, "tag": "backdrop: " + q}}, None,
                   set(), [], [i], clips_dir)
        if sl.get("src"):
            sl["backdrop"] = True
            out.append(sl)
    out.sort(key=lambda x: x["s"])
    for n, sl in enumerate(out):
        sl["i"] = n
    return out


def plan_lines(kind, t, tcfg, vo, title, footage, extra, pics, direct, seed, out):
    """Words -> lines, beats, length, camera, and what each line shows (pictures, stock, the director). The slow, AI part."""
    cfg = TYPES[kind]
    W = fix_words(transcribe(vo, os.path.join(out, "vo-words.json"), strip_dates(title or "")))
    title = strip_dates(title or "")
    if kind == "phone":
        W = app_slip(W, title)
    L, beats = analyze(W, kind, title)
    if kind == "review":
        regroup_clauses(L, W)
        turn = next((ln for ln in L if ln["role"] == "turn"), None)
        if turn:   # the turn beat is its line's start
            beats["turn"] = turn["s"]
    end_t = W[-1]["e"]
    hold = float(tcfg.get("hold", 1.8))
    go_line = next((ln for ln in L if ln["role"] == "go"), None)
    if kind == "review" and not tcfg.get("title_card"):
        # NO title card in review intros (dhgate jordan 3 2026-10-23: "I like when I say let's go but I only want like 1 s
        # ... I want to cut the DHgate Jordan 3 review tab, that automatic generated tab, for the product reviews ... really
        # speed up the video"): the footage runs on under "let's go" and the intro ends ~1 s after "let's" (or 0.5 s after
        # the last word). beats.title past the end = every template's title never shows. (lv trainer had the title land on
        # "let's go" with 1 s after it; this drops the card itself.)
        # ...and NO extra seconds after the last word either (reselling spreadsheet 2026-10-23: "from the voiceover intro to
        # the actual video intro, like hey guys ... we shouldn't add extra seconds, we just want to jump right into the
        # video"): the intro ends 0.3 s after the last word, the slide into "hey guys" overlaps it (join.py --slide)
        dur = round(end_t + 0.3, 2)
        beats["title"] = round(dur + 1.0, 2)
    elif kind == "review" and beats["go"] is not None and go_line is L[-1]:
        # review intros (lv trainer 2026-10-23, "0:19-0:21 there's a lot of dead space ... say let's go and give it 1 s
        # after let's go, then transition into hey guys"): the title lands ON "let's go" (scenes read beats.title) and the
        # intro ends ~1 s after the last word, instead of the title waiting for the VO to end and holding ~2 s
        beats["title"] = round(beats["go"] - 0.05, 2)
        dur = round(max(beats["title"] + 1.6, end_t + 1.0), 2)
    elif kind == "phone" and not tcfg.get("hold_end"):
        # phone intros keep their app title card, but it lands ON "let's go" and the intro ends 1 s after it / 0.3 s after
        # the last word, no 1.8 s hold + tail (reselling spreadsheet 2026-10-23: "removing the 1 second was a good call
        # across all of our videos ... no spacing in between the intro for the voiceover and the other intro").
        # template "hold_end": true = the old hold.
        # (P-templates time their title from beats.go themselves; the exit wipe runs in the last 0.6 s)
        beats["title"] = None
        dur = round(max(end_t + 0.3, (beats["go"] if beats["go"] is not None else end_t) + 1.0), 2)
    else:
        beats["title"] = None
        dur = round(max((beats["go"] or end_t) + hold, end_t + 0.9) + float(tcfg.get("tail", 0.3)), 2)
    if kind == "gaming":
        beats["gap"] = 0.26
    cam = plan_camera(kind, L, W, beats, dur, seed if seed is not None else 7)
    # real pictures of the real things the VO names (review videos by default; "off" or a beats.json override list)
    pics = pics if pics is not None else ("auto" if kind == "review" else "off")
    forced = {}
    if pics != "off":
        import pics as P
        ov = json.load(open(pics)) if isinstance(pics, str) and pics.endswith(".json") else None
        own = json.load(open(footage)) if isinstance(footage, str) else (footage or [])
        forced, vcred = P.videos_for_lines(W, L, own)   # real clips of named things + free stock B-roll for generic things
        # people and places he names get THEIR photo, full frame (best sp5der hoodie 2026-10-23: Young Thug, Atlanta,
        # Dunwoody, Decatur were all missing, "the intro needs to understand context")
        ents, ecred = P.entity_footage(W, L)
        forced.update(ents)
        vcred = list(vcred) + ecred
        for li, ps in P.for_lines(W, L, out, ov, skip={f["entity"] for f in forced.values()}, product=(extra or {}).get("product", "")).items():
            L[li]["pics"] = ps
        for li, qs in P.quotes_for_lines(L).items():   # people he quotes ("TSA agents ... said ...") -> speech bubble
            L[li]["quotes"] = qs
        if vcred:
            pj = os.path.join(out, "pics.json")
            d = json.load(open(pj)) if os.path.exists(pj) else {"pics": {}, "credits": []}
            d["credits"] = sorted(set(d.get("credits", []) + vcred))
            json.dump(d, open(pj, "w"), indent=1)
    footage = json.load(open(footage)) if isinstance(footage, str) else footage
    if direct:
        forced = apply_direction(kind, title, t, tcfg, L, W, footage, forced, out, extra)
    return W, L, beats, dur, cam, forced, footage


def _finish(kind, cfg, t, tcfg, vo, title, out, sub, footage, music, accent, seed, render, quality, extra, W, L, beats, dur, cam, slots, flashes):
    """Music, audio, the page and the render: everything after the shots are chosen."""
    for sl_ in slots or []:   # template "lead": how early it starts showing each shot (the video must already play)
        sl_["lead"] = float(tcfg.get("lead", 0) or 0)
    music = pick_music(kind, music, (extra or {}).get("avoid_music"), title, out) if music != "none" else None
    # footage with marked beats ("hits": a json with offsets into the clip, review_intro's product countdown): a whoosh + click
    # on every product it shows (top 5 products to resell in winter 2024: "show the 5 and have sound effects to mark it")
    hits = []
    for f in footage or []:
        if not f.get("hits"):
            continue
        try:
            offs = json.load(open(f["hits"], encoding="utf-8")).get("hits", [])
        except (OSError, ValueError):
            continue
        for sl in slots or []:
            src, _, at = str(sl.get("from", "")).rpartition("@")
            if os.path.normcase(src) != os.path.normcase(str(f["src"])):
                continue
            s0, e0, o = float(sl["s"]), float(sl["e"]), float(at or 0)
            for h in offs:
                if o - 0.05 <= h < o + (e0 - s0) - 0.1:
                    hits += [{"sfx": "whoosh-short.mp3", "t": s0 + h - o - 0.04, "vol": 0.14, "d": 0.5},
                             {"sfx": "click", "t": s0 + h - o, "vol": 0.16, "d": 0.3}]
    if hits:
        tcfg = dict(tcfg, sfx=list(tcfg.get("sfx", [])) + hits)
    if tcfg.get("bed") is not None:   # a template may sit its music higher (P21: "we got to turn it up", 2026-10-24)
        cfg = dict(cfg, bed=float(tcfg["bed"]))
    if tcfg.get("story_sfx") and kind in ("review", "phone"):
        # each beat its own quiet sound, tied to HIS words (2026-10-24, "turn it up"; the sparse + quiet rule, no whooshes /
        # risers / bass inside intros): a key tap as each fee lands, a ping on the turn, a click as the code tickets fan in,
        # the cash register on "save" (register = money slams), a ping on the title payoff
        cues, seen = [], set()
        for w in W:
            lw = re.sub(r"[^a-z]", "", w["w"].lower())
            for lab, rx in (("shipping", r"^shipping"), ("tax", r"^tax"), ("fees", r"^fees?$")):
                if lab not in seen and re.match(rx, lw):
                    seen.add(lab)
                    cues.append({"sfx": "key-press.mp3", "t": round(w["s"] - 0.05, 2), "vol": 0.16, "d": 0.3})
            # order items land with a tap (P21 "order" graphic), and the word he punches ("boom", "bam") gets an impact
            # (Uber codes october 2026-10-25: "big mac combo meal over here, some fries, boom: maybe an explosion sound effect")
            if re.match(ITEM_RX, lw) and lw not in seen:
                seen.add(lw)
                cues.append({"sfx": "key-press.mp3", "t": round(w["s"] - 0.05, 2), "vol": 0.16, "d": 0.3})
            if re.match(r"^(boom|bam|bang|kaboom)$", lw) and "boom" not in seen:
                seen.add("boom")
                cues.append({"sfx": "impact-bass-2.mp3", "t": round(w["s"] - 0.03, 2), "vol": 0.3, "d": 1.2})
        if beats.get("turn") is not None:
            cues.append({"sfx": "ping.mp3", "t": round(beats["turn"], 2), "vol": 0.18, "d": 0.8})
        tk = next((ln for ln in L if re.search(r"promo|\bcodes?\b|coupons?", ln["text"], re.I) and ln["role"] != "go"
                   and (beats.get("turn") is None or ln["s"] > beats["turn"])), None)
        if tk:
            cues.append({"sfx": "click.mp3", "t": round(tk["s"] + 0.1, 2), "vol": 0.14, "d": 0.3})
        sv = next((w for w in W if re.match(r"^sav(e|ing)", w["w"].lower()) and (beats.get("turn") is None or w["s"] > beats["turn"])), None)
        if sv:
            cues.append({"sfx": "register.wav", "t": round(sv["s"], 2), "vol": 0.2, "d": 1.0})
        if beats.get("go") is not None:
            cues.append({"sfx": "ping.mp3", "t": round(beats["go"] + 0.05, 2), "vol": 0.16, "d": 0.8})
        tcfg = dict(tcfg, sfx=list(tcfg.get("sfx", [])) + cues)
    elif tcfg.get("editor") and kind in ("review", "phone"):
        # one quiet click as a key word lands, on at most 4 lines (2026-10-24 "there's also sound effects we could do"; the
        # sparse + quiet SFX rule; no whooshes inside intros)
        keys = [ln for ln in L if ln.get("key") and not ln.get("key_weak") and ln["role"] != "go" and ln.get("keyT")]
        step = max(1, len(keys) // 4)
        tcfg = dict(tcfg, sfx=list(tcfg.get("sfx", [])) + [{"sfx": "click", "t": round(ln["keyT"], 2), "vol": 0.12, "d": 0.3}
                                                           for ln in keys[::step][:4]])
    atags = build_audio(kind, out, vo, beats, dur, music, cfg, tcfg, cam)
    seed = seed if seed is not None else int(hashlib.md5((vo + t["id"]).encode()).hexdigest()[:6], 16)
    I = {"type": kind, "template": t["id"], "dur": dur, "title": title, "sub": strip_dates(sub or ""), "accent": accent or tcfg.get("accent") or cfg["accent"],
         "words": W, "lines": L, "beats": beats, "slots": slots, "seed": seed, "cam": cam, "flashes": flashes}
    if kind == "phone":
        forced_app = (extra or {}).get("app")
        I["app"] = None if forced_app == "none" else detect_app(W, out, forced_app)   # "none": the VO names another app by mistake
        if I["app"] and not accent:
            I["accent"] = I["app"]["accent"]
        I["kind"] = (I["app"] or {}).get("kind") or guess_kind(W)
    if kind == "review":
        I["mg"] = review_graphics(L, (extra or {}).get("product_price"))
        # the retail line has a REAL price page under it (StockX / the brand's page): the tag floats over that page instead of
        # covering it with a full-screen card (lv skatesta 2026-10-24, his own edit: "$1,000" over the LV product page)
        for g in I["mg"]:
            if g["type"] == "price" and any("screen recording" in str(sl.get("tag", "")) and sl["s"] < g["e"] and sl["e"] > g["t"]
                                            for sl in slots):
                g["over"] = True
        I.update(brand_logos(out, title, W, (extra or {}).get("brand")))
    # the editor's toolkit (templates with "editor": true): stamp / chart / money rain on his words + cartoon FX transitions
    if tcfg.get("editor") and kind in ("review", "phone"):
        I["mg"] = list(I.get("mg") or []) + editor_graphics(L, W, [(g["t"], g["e"]) for g in I.get("mg") or []])
        I["fx"] = fx_plan(L, beats, dur, I["mg"])
    if extra:
        I.update({k: v for k, v in extra.items() if k not in ("app", "text_fixes")})   # app is resolved above
    # his intro text fixes (Studio double-click, text_fixes.py): the unfixed data is kept for later fixes / undo
    import text_fixes
    open(os.path.join(out, "intro_data.json"), "w", encoding="utf-8").write(json.dumps(I))
    I, _hits = text_fixes.apply(I, (extra or {}).get("text_fixes"))
    open(os.path.join(out, "text_fixes.json"), "w", encoding="utf-8").write(json.dumps((extra or {}).get("text_fixes") or []))
    fonts ="".join(f'@font-face{{font-family:"{f}";src:url("assets/fonts/{n}.ttf") format("truetype");font-weight:{w};font-style:{s};}}\n' for f, n, w, s in FONTS)
    rd = lambda f: open(os.path.join(t["dir"], f), encoding="utf-8").read() if os.path.exists(os.path.join(t["dir"], f)) else ""
    body = rd("body.html")
    # scene banks (gaming/phone): literal, moving scenes the theme templates direct line by line
    bank = os.path.join(KIT, f"scenes_{kind}.js")
    extra_js = open(bank, encoding="utf-8").read() if os.path.exists(bank) else ""
    if (extra or {}).get("scenes"):
        I["scenes"] = extra["scenes"]
    # templates may need their own asset files (textures they ship)
    if os.path.isdir(os.path.join(t["dir"], "assets")):
        for fn in os.listdir(os.path.join(t["dir"], "assets")):
            shutil.copy(os.path.join(t["dir"], "assets", fn), os.path.join(out, "assets", fn))
    shutil.copy(os.path.join(KIT, "gsap.min.js"), os.path.join(out, "assets", "gsap.min.js"))
    shutil.copytree(os.path.join(KIT, "tex"), os.path.join(out, "assets", "tex"), dirs_exist_ok=True)
    html = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <script src="assets/gsap.min.js"></script>
    <style>
{fonts}
{open(os.path.join(KIT, "kit.css"), encoding="utf-8").read()}
:root {{ --accent: {I['accent']}; }}
{rd("style.css")}
    </style>
  </head>
  <body>
    <div id="intro" data-composition-id="intro" data-start="0" data-width="1920" data-height="1080" data-duration="{dur:.2f}" data-fps="{IFPS}">
      <div id="stage">
        <div id="cam"><div id="cam-in">
{body}
        </div></div>
      </div>
      <div id="slotbank">
{slot_html(slots, dur)}
      </div>
      {chr(10).join('      ' + a for a in atags)}
    </div>
    <script>window.INTRO = {json.dumps(I)};</script>
    <script>
{rd("scene.js")}
    </script>
    <script>
{open(os.path.join(KIT, "kit.js"), encoding="utf-8").read()}
    </script>
    <script>
{extra_js}
    </script>
  </body>
</html>
"""
    open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(html)
    open(os.path.join(out, "package.json"), "w").write(json.dumps({"name": "intro-" + t["id"].lower(), "private": True, "type": "module",
                                                                    "scripts": {"check": f"{HF} check", "render": f"{HF} render"}}, indent=2))
    shutil.copy(os.path.join(HERE, "kit", "hyperframes.json"), os.path.join(out, "hyperframes.json"))
    json.dump({"template": t["id"], "name": t.get("name"), "type": kind, "dur": dur, "music": music, "beats": beats,
               "title": title, "mg": I.get("mg") or [], "fx": I.get("fx") or [],
               "lines": [{k: ln.get(k) for k in ("s", "e", "role", "key", "key_weak", "icon", "text")} for ln in L], "slots": slots},
              open(os.path.join(out, "intro.json"), "w"), indent=1)
    print(f"intro {t['id']} ({t.get('name')}) -> {out}  dur {dur}s  turn {beats['turn']:.2f}  go {beats['go']}  watch {bool(beats['watch'])}  slots {len(slots)}")
    if render:
        return render_project(out, quality)
    return out


def render_project(out, quality="looks", name="intro.mp4"):
    os.makedirs(os.path.join(out, "renders"), exist_ok=True)
    raw = os.path.join(out, "renders", "_raw.mp4")
    r = subprocess.run(f'{HF} render --quiet --quality {quality} --fps {IFPS} -o renders/_raw.mp4', cwd=out, shell=True, capture_output=True, text=True, errors="replace")
    if not os.path.exists(raw):
        print(r.stdout[-3000:], r.stderr[-3000:])
        raise SystemExit("render failed")
    final = os.path.join(out, "renders", name)
    # deliverable contract: H.264 High yuv420p + AAC, faststart (render-h264-only)
    # up to 3 tries: ffmpeg can die silently mid-encode (best sp5der hoodie 2026-10-23: a 48-byte intro.mp4, empty stderr,
    # and the whole intro was dropped from the draft)
    for attempt in range(3):
        e = run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p", "-crf", "17", "-preset", "medium",
                 "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", final])
        ok = not e.returncode and run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", final]).stdout.strip()
        if ok:
            break
        time.sleep(3)
    if not ok:   # a truncated encode (no moov atom) once slipped through as a 256 KB "intro" (gallery P17, 2026-10-22)
        raise SystemExit(f"final encode failed, raw kept at {raw}: {e.stderr[-600:]}")
    os.remove(raw)
    print("rendered", final)
    return final


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", choices=list(TYPES))
    ap.add_argument("--template", default="auto")
    ap.add_argument("--vo")
    ap.add_argument("--title", default="")
    ap.add_argument("--sub", default="")
    ap.add_argument("--out")
    ap.add_argument("--footage", help="json list of {src,t,d,crop,for,tag}")
    ap.add_argument("--music", help="track path or 'none'")
    ap.add_argument("--accent")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--quality", default="looks")
    ap.add_argument("--pics", help="auto | off | beats.json override list (default: auto for review videos)")
    ap.add_argument("--app", help="phone: force the app key (phone_edit apps.json) or 'none'")
    ap.add_argument("--extra", help="json file merged into the build: product (noun), product_price (DHgate price, for the compare graphic)")
    ap.add_argument("--direct", default="auto", help="auto: Claude plans what each line shows (director.py; off with CLAUDE_BRAIN=0) | off")
    ap.add_argument("--reuse-plan", action="store_true", help="self-check fix pass: keep the first pass's plan (plan_cache.pkl), only re-pin + render")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for t in templates(a.type):
            print(f"{t['type']:7} {t['id']:4} {t.get('status', 'ready'):6} {t.get('name', '')}  - {t.get('blurb', '')}")
        sys.exit()
    if a.vo and a.out and os.environ.get("INTRO_VO_TRIM", "1") != "0":
        a.vo = trim_vo_lead(a.vo, a.out)
    build(a.type, a.template, a.vo, a.title, a.out, a.sub, a.footage, a.music, a.accent, a.seed, a.render, a.quality, pics=a.pics, direct=a.direct != "off", reuse_plan=a.reuse_plan,
          extra=dict(json.load(open(a.extra, encoding="utf-8")) if a.extra else {}, **({"app": a.app} if a.app else {})) or None)

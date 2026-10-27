"""Real clips for a phone video's intro, picked from THIS video's website half (the "screens" intro, approved on Shein).
Usage: python intro_footage.py <edit dir> <out footage.json> [--max 5]
Reads edit\\cut-full.mp4 (blurred cut), edit\\layout.json ("web" runs) and edit\\screen_codes.json. Writes a footage.json for
intro_library\\build_intro.py: [{src, t, crop, vf, kind: "cam", tag}], or [] when the video has no website stretches.

Pick rule (dhgate coupons 2026-10-22: the intro had no clips from the video and showed a food order on a DHgate video):
  - sample the website half once a second; score = colour (product photos, store pages) + movement (scrolling)
  - skip the moments a code is on screen (codes are never readable in an intro, retention), white document / table
    pages (spreadsheets of codes with dates in them: mostly white AND low colour) and anything near a privacy blur
    (no blurred screen recordings in intros); dark graphic pages (a link page of product lists) are kept
  - the best moments at least 8 s apart, in video order, browser tabs + taskbar cropped off
  - never his own WORKSPACE pages (Uber codes october 2026-10-25: his Notion dashboard opened the intro on "Uber Eats is
    ..." and came back on "out of nowhere"; a dark, still page passes every picture rule). The address bar + page text of
    each pick is OCR'd; a workspace site (Notion, Google Docs/Sheets/Drive, Gmail, Trello, ClickUp, ChatGPT, YouTube
    Studio ...) is skipped. The intro self-check can't fix it later: a stock fix never replaces his own footage.
"""
import json, os, re, subprocess, sys
import numpy as np

W, H = 320, 180   # analysis frame (one screen half)
WORKSPACE = re.compile(r"notion\.(so|site)|\bnotion\b|docs\.google|sheets\.google|drive\.google|mail\.google|\bgmail\b|"
                       r"calendar\.google|trello\.com|clickup|airtable|monday\.com|asana\.com|obsidian|todoist|ticktick|"
                       r"chatgpt\.com|chat\.openai|claude\.ai|studio\.youtube|youtube studio|life os", re.I)


# CPA / survey offer pages ("Complete twenty Deals to claim", "Answer question 1 of 3", LevelRewards): not his footage, never
# intro footage (Uber codes october 2026-10-25: "CPA page, this is like a survey type thing, we want to try to grab our own
# footage"). They stay in the main video, where he walks through them.
CPA = re.compile(r"deals?\W+\d*\W*to claim|answer question \d|surveysandpromo|levelrewards|level rewards|offer not sponsored|"
                 r"complete \w+ deals|rewardzone|flashrewards|\bclaim (your|now)\b", re.I)
_TEXT = {}


def workspace(src, side, t, rx=WORKSPACE):
    """True when the page at t is one of his own workspace tools (OCR of the address bar, tabs and page title)"""
    key = (src, side, round(t, 1))
    if key not in _TEXT:
        _TEXT[key] = page_text(src, side, t)
    return bool(rx.search(_TEXT[key]))


def cpa(src, side, t):
    return workspace(src, side, t, CPA)


def page_text(src, side, t):
    x = 0 if side == "left" else 1920
    # below the tab strip (y > 70): other open tabs (a "Life OS Pro" tab beside the Uber Eats survey page) don't count;
    # the address bar is read at 2x (OCR missed "surveysandpromoonline.com" at 1x)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1", "-vf",
                          f"crop=1920:230:{x}:70,scale=3840:460", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
    if len(raw) < 3840 * 460 * 3:
        return ""
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import privacy_ocr
        return " ".join(ln for ln, _ in privacy_ocr.ocr(np.frombuffer(raw, np.uint8).reshape(460, 3840, 3)))
    except Exception as err:   # no OCR: say so, the pick goes on (the self-check still looks)
        print(f"intro footage: page OCR skipped: {type(err).__name__}: {str(err)[:120]}")
        return ""


def frames(src, side, a, b):
    """One frame per second of one half between a and b (main-video time) as small RGB arrays."""
    x = 0 if side == "left" else 1920
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.2f}", "-t", f"{b - a:.2f}", "-i", src, "-vf",
                          f"fps=1,crop=1920:1080:{x}:0,scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
    n = len(raw) // (W * H * 3)
    return np.frombuffer(raw[:n * W * H * 3], np.uint8).reshape(n, H, W, 3).astype(np.float32)


def white(f):
    """Share of near-white page pixels (documents, spreadsheets)."""
    f = f[int(H * 0.1):int(H * 0.94)]
    return float((f.min(axis=2) > 225).mean())


def colourful(f):
    """Hasan-Suesstrunk colourfulness of the page area (browser bar and taskbar left out)."""
    f = f[int(H * 0.1):int(H * 0.94)]
    r, g, b = f[..., 0], f[..., 1], f[..., 2]
    rg, yb = r - g, 0.5 * (r + g) - b
    return float(np.hypot(rg.std(), yb.std()) + 0.3 * np.hypot(rg.mean(), yb.mean()))


def thumb(f):
    """32x18 grey thumbnail of the page area: two moments of the same page look alike, different pages do not."""
    g = f[int(H * 0.1):int(H * 0.94)].mean(axis=2)
    h, w = g.shape
    return g[:h - h % 18, :w - w % 32].reshape(18, (h - h % 18) // 18, 32, (w - w % 32) // 32).mean(axis=(1, 3))


def pick(edit, n_max=5):
    lay = json.load(open(os.path.join(edit, "layout.json")))
    src = os.path.join(edit, "cut-full.mp4")
    web = [(a, b, s) for a, b, s in lay.get("web", []) if b - a >= 6]
    if sum(b - a for a, b, _ in web) < 20:
        web = []
    scp = os.path.join(edit, "screen_codes.json")
    codes = json.load(open(scp, encoding="utf-8")) if os.path.exists(scp) else []
    code_on = [(c["said"] - 1, c["said"] + 9) for c in codes]
    # privacy-blurred spans (raw time in work\privacy.json) -> main time
    blur = []
    try:
        keep = json.load(open(os.path.join(edit, "..", "work", "cuts.json")))["keep"]
        for r in json.load(open(os.path.join(edit, "..", "work", "privacy.json"))):
            s_, e_ = (r.get("s"), r.get("e")) if isinstance(r, dict) else (r[0], r[1])
            acc = 0.0
            for a_, b_ in keep:
                if e_ > a_ and s_ < b_:
                    blur.append((acc + max(0, s_ - a_) - 1, acc + min(b_, e_) - a_ + 1))
                acc += b_ - a_
    except Exception:
        pass
    cand = []
    for a, b, side in web:
        fr = frames(src, side, a + 0.5, b - 0.5)
        # brightness at 4 fps (a page-load flash lasts ~0.5 s and slips between the 1 fps samples)
        x0 = 0 if side == "left" else 1920
        raw4 = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a + 0.5:.2f}", "-t", f"{b - a - 1:.2f}", "-i", src, "-vf",
                               f"fps=4,crop=1920:1080:{x0}:0,scale=32:18", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
        lum4 = np.frombuffer(raw4[:len(raw4) // 576 * 576], np.uint8).reshape(-1, 576).mean(axis=1)
        for i in range(len(fr)):
            t = a + 0.5 + i
            # the clip runs ~5 s from t: none of it may touch a code on screen or a blur (blurs get 0.5 s extra)
            if any(t - 0.5 < y and x < t + 5.5 for x, y in code_on) or any(t - 1.0 < y and x < t + 6.0 for x, y in blur):
                continue
            # a page that goes dark while it loads (dhgate coupons 2026-10-24: 0.6 s of near-black at 123.7 s showed as an
            # empty black window in the intro's first shot): skip any start whose ~4 s holds a frame under 45% of its median brightness
            lum = lum4[i * 4:i * 4 + 16]   # the ~4 s a slot can run
            if len(lum) and np.median(lum) > 80 and lum.min() < 0.45 * np.median(lum):
                continue
            col, wh = colourful(fr[i]), white(fr[i])
            # movement in the clip's first ~2 s (intro slots are 1-3 s long): a page that scrolls a second later still counts
            mov = max([float(np.abs(fr[j + 1] - fr[j]).mean()) for j in range(i, min(i + 2, len(fr) - 1))] or [0.0])
            cand.append((col + 1.5 * min(mov, 20), col, mov, t, side, wh, thumb(fr[i])))
    # store pages with product photos are colour 30+; a white spreadsheet of codes is ~18 with most of the page white
    good = sorted([c[:5] + (c[6],) for c in cand if c[1] >= 28 or c[5] < 0.35], key=lambda c: c[:4], reverse=True)
    # DIFFERENT pages first (dhgate coupons 2026-10-24, user: the intro "needs more movement, different things going on";
    # the colour score picked the same product listing 4 times, 8 s apart, and the DHgate homepage + product grid never
    # showed): a pick whose page looks like an earlier pick (small grey thumbnails, mean difference < 14) waits until every
    # distinct page has had its turn
    picks, dups, ws = [], [], []
    for sc, col, mov, t, side, th in good:
        if any(abs(t - p[3]) < 8 for p in picks):
            continue
        # a page that looks like a workspace page already rejected is the same page (no second OCR)
        if any(np.abs(th - w_).mean() < 8 for w_ in ws):
            continue
        if workspace(src, side, t) or cpa(src, side, t):
            ws.append(th)
            print(f"intro footage: {t:.0f}s is a workspace / CPA offer page (skipped)")
            continue
        (dups if any(np.abs(th - p[5]).mean() < 14 for p in picks) else picks).append((sc, col, mov, t, side, th))
        if len(picks) >= n_max:
            break
    for d in dups:
        if len(picks) >= n_max:
            break
        if all(abs(d[3] - p[3]) >= 8 for p in picks):
            picks.append(d)
    picks = [p[:5] for p in picks]
    picks.sort(key=lambda p: p[3])
    # 16:9 page area: browser tabs + address bar (top ~8%) and the taskbar (bottom ~5%) cut off
    vf = ",crop=1672:940:124:80,scale=1920:1080"
    out = [{"src": src.replace("\\", "/"), "t": round(t, 2), "crop": side, "vf": vf, "kind": "cam", "tag": f"website {t:.0f}s",
            "score": round(sc, 1), "colour": round(col, 1), "move": round(mov, 1)} for sc, col, mov, t, side in picks]
    # his own APP footage first (Uber codes october 2026-10-25: "we want to try to grab our own footage" - the intro was three
    # takes of a survey offer page while the video has minutes of him in the Uber Eats app)
    return phone_picks(edit, src, lay, blur + code_on) + out


def phone_picks(edit, src, lay, avoid, n_max=5):
    """Moments of the phone mirror (layout "app" runs) for the intro: colourful, detailed screens (food photos, the store,
    the promo screen), never a blank / loading screen, a privacy blur or a code; different screens first, >= 6 s apart.
    -> [{src, t, crop: "phone", box: "w:h:x:y", kind: "phone", tag}]"""
    pb = os.path.join(edit, "phone_box.json")
    if not lay.get("app") or not os.path.exists(pb):
        return []
    b_ = json.load(open(pb))
    x, y, w, h = b_["x"], b_["y"], b_["w"], b_["h"]
    PW, PH = 90, 192
    cand = []
    for a, b in lay["app"]:
        if b - a < 4:
            continue
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a + 0.5:.2f}", "-t", f"{b - a - 1:.2f}", "-i", src, "-vf",
                              f"fps=1,crop={w}:{h - 90}:{x}:{y + 60},scale={PW}:{PH}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True).stdout   # status bar / home bar left out
        n = len(raw) // (PW * PH * 3)
        fr = np.frombuffer(raw[:n * PW * PH * 3], np.uint8).reshape(n, PH, PW, 3).astype(np.float32)
        for i in range(n):
            t = a + 0.5 + i
            if any(t - 1.0 < q and p < t + 5.0 for p, q in avoid):
                continue
            g = fr[i].mean(axis=2)
            if g.mean() < 35 or g.std() < 25:   # dark / loading / blank screen
                continue
            # the shot stays one screen: no page change inside its first ~3 s (a tap mid-shot reads as a jump)
            if any(float(np.abs(fr[j + 1] - fr[j]).mean()) > 25 for j in range(i, min(i + 3, n - 1))):
                continue
            col = colourful(fr[i])
            th = g[:PH - PH % 12, :PW - PW % 6].reshape(12, PH // 12, 6, PW // 6).mean(axis=(1, 3))
            cand.append((col + 0.15 * g.std(), t, th))
    cand.sort(key=lambda c: -c[0])
    picks, dups = [], []
    for sc, t, th in cand:
        if any(abs(t - p[1]) < 6 for p in picks + dups):
            continue
        (dups if any(np.abs(th - p[2]).mean() < 18 for p in picks) else picks).append((sc, t, th))
        if len(picks) >= n_max:
            break
    picks = (picks + dups)[:n_max]
    picks.sort(key=lambda p: p[1])
    # which app the screen shows (OCR vs apps.json names): build_intro puts a clip on the line that names its app ("for"),
    # so "Uber Eats is one of those platforms" opens on his own Uber Eats screen
    try:
        apps = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "apps.json"), encoding="utf-8"))
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import privacy_ocr
    except Exception:
        apps, privacy_ocr = {}, None
    out = []
    for sc, t, _ in picks:
        names = []
        if privacy_ocr:
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1", "-vf", f"crop={w}:{h}:{x}:{y}",
                                  "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True).stdout
            if len(raw) >= w * h * 3:
                txt = " ".join(l for l, _ in privacy_ocr.ocr(np.frombuffer(raw[:w * h * 3], np.uint8).reshape(h, w, 3))).lower()
                names = [a["name"] for a in apps.values() if isinstance(a, dict) and any(al in txt for al in a.get("aliases", []))]
        out.append({"src": src.replace("\\", "/"), "t": round(t, 2), "crop": "phone", "box": f"{w}:{h}:{x}:{y}", "kind": "phone",
                    "tag": f"phone {t:.0f}s" + (f" ({names[0]})" if names else ""), "score": round(float(sc), 1),
                    **({"for": [n.lower() for n in names]} if names else {})})
    print(f"intro footage: {len(out)} phone-app clips", [(o["t"], o.get("for")) for o in out])
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    res = pick(a[0], int(a[a.index("--max") + 1]) if "--max" in a else 5)
    json.dump(res, open(a[1], "w"), indent=1)
    print(f"intro footage: {len(res)} clips", [(r["tag"], r["t"]) for r in res])

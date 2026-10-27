"""Main-video compositor for the Uber Eats edit (phone-tutorial-edit skill).

Input: edit/cut-full.mp4 (approved cut, 3840x1080, address already blurred), edit/layout.json, graphics/events.json.
Layouts (1920x1080):
  talk  - full webcam (left half of the capture)
  app   - blurred webcam background, webcam card left, phone big right (slides in on each app-mode start)
  side  - second camera (right half) while the user is turned left
Graphics: transparent HyperFrames MOVs from graphics/renders, placed at their event times.
Audio: voice normalised to -16 LUFS, one type beat per section at ~17 LU under the voice, quiet SFX on graphics.
Usage: python build_main.py [--draft]   (draft = NVENC cq 23, full = cq 19)
"""
import json, os, subprocess, sys
import numpy as np
import cv2

E = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(E, "cut-full.mp4")
GR = os.path.join(E, "graphics")
SFX = r"{{KIT}}/assets/Graphics/HyperFrames/servers-intro-oct/assets/sfx"
TB = r"{{MUSIC_ROOT}}/Type Beats"
lay = json.load(open(os.path.join(E, "layout.json")))
events = json.load(open(os.path.join(GR, "events.json")))
DUR = lay["dur"]

# --- geometry --------------------------------------------------------------------------------------------
CAM = (80, 110, 1020, 574)        # webcam card x, y, w, h
PH = (40, 60, 448, 960)           # phone picture-in-picture on the LEFT over the full webcam (user's normal style, v7 note)
# where the phone mirror sits in this recording (layout.py measures it: Uber codes october had it at x 2526, the old fixed
# 2628 crop cut off the phone's left edge)
_pb = json.load(open(os.path.join(E, "phone_box.json"))) if os.path.exists(os.path.join(E, "phone_box.json")) else {}
PCROP = f"crop={_pb.get('w', 504)}:{_pb.get('h', 1080)}:{_pb.get('x', 2628)}:{_pb.get('y', 0)}"


def rounded(w, h, r, path):
    m = np.zeros((h, w), np.uint8)
    cv2.rectangle(m, (r, 0), (w - r, h), 255, -1)
    cv2.rectangle(m, (0, r), (w, h - r), 255, -1)
    for cx, cy in ((r, r), (w - r, r), (r, h - r), (w - r, h - r)):
        cv2.circle(m, (cx, cy), r, 255, -1, cv2.LINE_AA)
    cv2.imwrite(path, m)


def shadows(path):
    img = np.zeros((1080, 1920, 4), np.uint8)
    a = np.zeros((1080, 1920), np.uint8)
    for x, y, w, h, r in ((PH[0], PH[1] + 14, PH[2], PH[3], 46),):
        cv2.rectangle(a, (x + r, y), (x + w - r, y + h), 200, -1)
        cv2.rectangle(a, (x, y + r), (x + w, y + h - r), 200, -1)
    a = cv2.GaussianBlur(a, (0, 0), 22)
    img[..., 3] = a
    cv2.imwrite(path, img)


# face cam card over a website: TOP LEFT (user 2026-10-21: the code cards came up bottom-right right over the cam; "move the
# face cam to the top left"). Cards stay bottom-right / right-anchored.
WC = (40, 40, 512, 288)
# the card gets a border + drop shadow (user, Shein 2026-10-21: "we need a border ... might need a drop shadow because it is
# on a white screen", rule for all videos). Border = the video's accent (code-card colour) so it reads on white AND dark
# pages; the shadow separates it from a white page.
CAM_BW = 4


def cam_frame(path):
    acc = "#ffffff"
    bp = os.path.join(GR, "batch.json")
    if os.path.exists(bp):
        acc = next((b["accent"] for b in json.load(open(bp)) if b.get("kind") == "code" and b.get("accent")), acc)
    rgb = tuple(int(acc.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    x, y, w, h = WC
    r = round(36 * w / CAM[2]) + CAM_BW
    img = np.zeros((1080, 1920, 4), np.uint8)
    sh = np.zeros((1080, 1920), np.uint8)
    def rrect(m, x0, y0, x1, y1, r, v):
        cv2.rectangle(m, (x0 + r, y0), (x1 - r, y1), v, -1)
        cv2.rectangle(m, (x0, y0 + r), (x1, y1 - r), v, -1)
        for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)):
            cv2.circle(m, (cx, cy), r, v, -1, cv2.LINE_AA)
    rrect(sh, x - CAM_BW, y - CAM_BW + 12, x + w + CAM_BW, y + h + CAM_BW + 12, r, 150)
    sh = cv2.GaussianBlur(sh, (0, 0), 16)
    img[..., 3] = sh   # black shadow
    ring = np.zeros((1080, 1920), np.uint8)
    rrect(ring, x - CAM_BW, y - CAM_BW, x + w + CAM_BW, y + h + CAM_BW, r, 255)
    on = ring > 0
    a = ring.astype(np.float32) / 255
    for c, v in zip((0, 1, 2), rgb[::-1]):  # BGR
        img[..., c] = (v * a).astype(np.uint8)
    img[..., 3] = np.maximum(img[..., 3], ring)
    cv2.imwrite(path, img)


os.makedirs(os.path.join(E, "build"), exist_ok=True)
B = os.path.join(E, "build")
rounded(CAM[2], CAM[3], 36, os.path.join(B, "mask_cam.png"))
rounded(PH[2], PH[3], 46, os.path.join(B, "mask_phone.png"))
shadows(os.path.join(B, "shadows.png"))
cam_frame(os.path.join(B, "cam_frame.png"))

between = lambda segs: "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in segs) or "0"
app, side = lay["app"], lay["side"]


def to_wipes(runs):
    """a screen run that ends within 3 s after a section wipe ends UNDER the wipe (Uber codes october 2026-10-25, 1:18:
    the method-1 survey page ran on 0.7 s past the METHOD 2 wipe, so the wipe "transitioned us into something we have
    already showed"). Starts are never pulled EARLIER to a wipe: that showed 1 s of his Notion page before the cut to the
    website (same draft, 0:45)"""
    mids = [e["t"] + e["dur"] / 2 for e in events if e.get("kind") == "wipe"]
    out = []
    for r in runs:
        a, b = r[0], r[1]
        for m in mids:
            if m < b <= m + 3 and a < m - 1:
                b = m
        out.append([round(a, 2), round(b, 2)] + list(r[2:]))
    return out


app = to_wipes(app)
lay["web"] = to_wipes(lay.get("web", []))
# phone slide-in from the right over 0.35 s at each app-mode start (eased), card fades in with it
slide = "+".join(f"if(between(t,{a:.3f},{a + 0.35:.3f}),pow(1-(t-{a:.3f})/0.35,2)*620,0)" for a, b in app) or "0"

# --- video graph -----------------------------------------------------------------------------------------
# looped stills get an END (-t): an endless mask kept the website card's graph waiting after the last frame until ffmpeg
# ran out of memory (Doordash 2026-10-21, full render hung at frame 15273 of 15273)
LOOP = ["-loop", "1", "-t", f"{DUR + 2:.2f}"]
inputs = ["-i", SRC] + LOOP + ["-i", os.path.join(B, "mask_cam.png")] + LOOP + ["-i", os.path.join(B, "mask_phone.png")] + LOOP + ["-i", os.path.join(B, "shadows.png")] + LOOP + ["-i", os.path.join(B, "cam_frame.png")]
g = []
web, camr = lay.get("web", []), lay.get("camr", [])
g.append("[0:v]split=6[v1][v6][v4][v5][v7][v8]")
# the face cam is whichever half shows it at that moment (layout "camr" = right half; Shein / Doordash website sections)
g.append("[v1]crop=1920:1080:0:0,setsar=1[camL0];[v6]crop=1920:1080:1920:0,setsar=1[camR0]")
g.append(f"[camL0][camR0]overlay=0:0:enable='{between(camr)}'[camx];[camx]split=3[cam][bg][cardsrc]")
# website runs: that half full screen + the face cam in a rounded corner card
g.append(f"[cardsrc]scale={WC[2]}:{WC[3]},format=yuva420p[card0];[1:v]format=gray,scale={WC[2]}:{WC[3]}[cm];[card0][cm]alphamerge,split=2[cardA][cardB]")
# zoom-ins on the code box while each code is on (user 2026-10-21: "add zoom ins to the coupon code section ... boost
# engagement"): screen_codes.json says where on the screen each code was typed; ease in 0.6 s after it is announced,
# hold, ease out before the next one, so every code gets its own push-in
def zoom_filter(side):
    scp = os.path.join(E, "screen_codes.json")
    sc = [c for c in (json.load(open(scp, encoding="utf-8")) if os.path.exists(scp) else []) if c.get("box") and c["box"][0] == side]
    if not sc:
        return ""
    Z, wins = 1.7, []
    for i, c in enumerate(sc):
        a = c["said"] + 0.4
        nxt = sc[i + 1]["said"] if i + 1 < len(sc) else a + 9
        b = min(nxt - 0.3, a + 12)
        if b - a < 1.6:
            continue
        _, x, y, w, h = c["box"]
        wins.append((a, b, x + w / 2, y + h / 2))
    if not wins:
        return ""
    T = "(in/30)"
    r = lambda a, b: f"clip(({T}-{a:.2f})/0.6,0,1)*clip(({b:.2f}-{T})/0.5,0,1)"
    s = lambda a, b: f"({r(a, b)})*({r(a, b)})*(3-2*({r(a, b)}))"
    z = "1+" + f"{Z - 1:.2f}*(" + "+".join(s(a, b) for a, b, _, _ in wins) + ")"
    on = "+".join(f"between({T},{a - 0.1:.2f},{b + 0.1:.2f})" for a, b, _, _ in wins)
    cx = "+".join(f"between({T},{a - 0.1:.2f},{b + 0.1:.2f})*{x:.0f}" for a, b, x, _ in wins) + f"+(1-({on}))*960"
    cy = "+".join(f"between({T},{a - 0.1:.2f},{b + 0.1:.2f})*{y:.0f}" for a, b, _, y in wins) + f"+(1-({on}))*540"
    print(f"zoom-ins ({side and 'right' or 'left'} half):", [(round(a, 1), round(b, 1)) for a, b, _, _ in wins])
    return (f",zoompan=z='{z}':x='clip(({cx})-iw/zoom/2,0,iw-iw/zoom)':y='clip(({cy})-ih/zoom/2,0,ih-ih/zoom)':d=1:s=1920x1080:fps=30")


g.append("[4:v]format=rgba,split=2[frL][frR]")
g.append(f"[v7]crop=1920:1080:0:0,setsar=1{zoom_filter(0)}[scrL];[scrL][frL]overlay=0:0:shortest=1[scrLf];[scrLf][cardA]overlay={WC[0]}:{WC[1]}[webL]")
g.append(f"[v8]crop=1920:1080:1920:0,setsar=1{zoom_filter(1)}[scrR];[scrR][frR]overlay=0:0:shortest=1[scrRf];[scrRf][cardB]overlay={WC[0]}:{WC[1]}[webR]")
g.append(f"[cam][webL]overlay=0:0:enable='{between([[a, b] for a, b, s in web if s == 'left'])}'[camw0]")
g.append(f"[camw0][webR]overlay=0:0:enable='{between([[a, b] for a, b, s in web if s == 'right'])}'[camw]")
g.append(f"[v4]{PCROP},scale={PH[2]}:{PH[3]},format=yuva420p[ph];[2:v]format=gray,scale={PH[2]}:{PH[3]}[mp];[ph][mp]alphamerge[phonec]")
g.append("[v5]crop=1920:1080:1920:0,setsar=1[side]")
g.append("[bg][3:v]overlay=0:0:shortest=1[bgs]")
g.append("[bgs]null[bgc]")
# dead phone screens (app loading / blank) while he talks: hold the last good phone frame (user note: "dead space")
holds = []
bp = os.path.join(E, "..", "work", "blank_phone.json")
cuts_keep = json.load(open(os.path.join(E, "..", "work", "cuts.json")))["keep"]
def to_out(t):
    acc = 0.0
    for a_, b_ in cuts_keep:
        if a_ <= t < b_:
            return acc + t - a_
        acc += b_ - a_
if os.path.exists(bp):
    for r in json.load(open(bp)):
        o0, o1 = to_out(r["s"]), to_out(r["e"] - 0.01)
        if o0 is not None and o1 is not None and o1 > o0:
            still = os.path.join(B, f"hold_{len(holds)}.png")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0, o0 - 0.15):.3f}", "-i", SRC, "-frames:v", "1",
                            "-vf", f"{PCROP},scale={PH[2]}:{PH[3]}", still], check=True)
            holds.append((o0 - 0.05, o1 + 0.1, still))
g.append(f"[bgc][phonec]overlay=x='{PH[0]}-({slide})':y={PH[1]}:eval=frame[appv0]")  # slides in from the left edge
prev = "appv0"
HOLD_BASE = 5  # inputs 5.. are the hold stills (added below, before the wipe input)
for k, (h0, h1, still) in enumerate(holds):
    g.append(f"[{prev}][{HOLD_BASE + k}:v]overlay={PH[0]}:{PH[1]}:enable='between(t,{h0:.3f},{h1:.3f})'[apph{k}]")
    prev = f"apph{k}"
g.append(f"[{prev}]null[appv]")
for h0, h1, still in holds:
    inputs += LOOP + ["-i", still]
print("phone holds:", [(round(a, 2), round(b, 2)) for a, b, _ in holds])
g.append(f"[camw][appv]overlay=0:0:enable='{between(app)}'[l1]")
g.append(f"[l1][side]overlay=0:0:enable='{between(side)}'[l2]")
# the intro ends on a covering green wipe: open the main video on the second half of the same wipe
inputs += ["-ss", "0.36", "-i", os.path.join(GR, "renders", "wipe1.mov")]
g.append(f"[l2][{5 + len(holds)}:v]overlay=0:0:eof_action=pass:format=auto[l3]")
cur = "l3"
n_in = 6 + len(holds)
for k, ev in enumerate(events):
    f = os.path.join(GR, "renders", ev["name"] + ".mov")
    if not os.path.exists(f):
        print("missing graphic", ev["name"]); continue
    inputs += ["-itsoffset", f"{ev['t']:.3f}", "-i", f]
    g.append(f"[{cur}][{n_in}:v]overlay=0:0:eof_action=pass:format=auto[g{k}]")
    cur = f"g{k}"
    n_in += 1
# every video ends on a fade to black (user 2026-10-21: "no fade transition on the end of the video. We need these for all videos")
g.append(f"[{cur}]fade=t=out:st={DUR - 1.2:.3f}:d=1.2,format=yuv420p[vout]")

# --- audio: voice + sectioned music + sfx ----------------------------------------------------------------
# music: one approved type beat per section; sections start at the section wipes (events.json)
PLAYLIST = [  # medium-Whisper-checked instrumentals: NO vocals and NO producer tags (BeatStars-tagged Ruiz beat removed 2026-10-20)
    f"{TB}/Drake/[FREE] DRAKE TYPE BEAT   KENDALL  .mp3",
    f"{TB}/Drake/Drake Type Beat - Family Matters (ECHOBEATS).mp3",
    f"{TB}/Drake/FREE Drake Type Beat - DoTheMove (Prod. 20).mp3",
    f"{TB}/Drake/Drake x RnB Type Beat - Close To Me (ECHOBEATS).mp3",
]
# section changes = the wipes (section wipes, the dive-in hand-over); the outro starts at its own wipe ("wipe-outro"), or
# 4.5 s before the end card on older plans. The outro bound used to need DUR - 20, so an outro in the last 20 s was lost.
cuts_ = sorted(ev["t"] + 0.35 for ev in events if ev["kind"] == "wipe" and ev["name"] != "wipe-outro")
ends_ = [ev["t"] + 0.35 for ev in events if ev["name"] == "wipe-outro"] or [ev["t"] - 4.5 for ev in events if ev["kind"] == "end"]
end_cut = ends_[0] if ends_ and DUR - ends_[0] >= 8 and ends_[0] > max([c for c in cuts_ if c > 5] or [0]) + 10 else None
bounds = [0.0] + [c for c in cuts_ if 5 < c < (end_cut or DUR) - 10] + ([end_cut] if end_cut else []) + [DUR]
SECTIONS = []
im = os.path.join(E, "intro_music.json")  # written by the intro builder: the intro's beat (the main video starts another)
intro_mus = json.load(open(im)) if os.path.exists(im) else None
body = [t for t in PLAYLIST if not (intro_mus and t == intro_mus["track"])] or PLAYLIST
# section beats from the WHOLE {{MUSIC_ROOT}} library (user 2026-10-24: "we've been using the same tracks over and over again"):
# music_lib fits clean steady beats to this video's title + transcript and skips what the channel's last 15 videos used;
# a re-render keeps its beats. PLAYLIST stays the fallback.
try:
    sys.path.insert(0, r"{{KIT}}/tools")
    import music_lib
    _lib = music_lib.pick_for(E, kind="phone", n=len(bounds) + 3, min_len=45, role="main",
                              exclude=[intro_mus["track"]] if intro_mus else ())
    if _lib:
        body = _lib
        print("music (library):", "; ".join(os.path.basename(t)[:40] for t in body))
except Exception as _e:
    print(f"music_lib skipped: {type(_e).__name__}: {str(_e)[:160]}")


def usable(track):
    """Seconds of real music in the track: the end minus its trailing quiet / fade-out tail."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", track, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    db = 20 * np.log10(np.sqrt((a[:len(a) // 4000 * 4000].reshape(-1, 4000) ** 2).mean(1)) + 1e-9)   # 0.5 s windows
    on = np.where(db > np.median(db) - 14)[0]
    return (on[-1] + 1) * 0.5 if len(on) else len(a) / 8000


seams = list(np.cumsum([b_ - a_ for a_, b_ in cuts_keep])[:-1])
plan, used_k = [], 0
for k in range(len(bounds) - 1):
    # the intro's beat fades out; the main video starts a DIFFERENT beat (user v6). The outro brings the INTRO's beat back
    # as a bookend instead of replaying a section track (user 2026-10-21: "it just plays the same songs" at the outro)
    last = k == len(bounds) - 2 and bool(end_cut)
    s0, e0 = bounds[k], bounds[k + 1]
    if last:
        plan.append((s0, e0, intro_mus["track"] if intro_mus else PLAYLIST[0], 40.0))
        continue
    # a section longer than its beat used to run the beat out and leave silence (dhgate coupons 2026-10-22: 130 s KENDALL
    # under a 260 s section, music gone from 2:16 on). Change beat before it runs out, on a cut where possible.
    while e0 - s0 > 0.5:
        track = body[used_k % len(body)]
        used_k += 1
        room = usable(track) - 2.0
        if e0 - s0 <= room:
            plan.append((s0, e0, track, 0.0))
            break
        cand = [t for t in seams if s0 + room * 0.6 < t < s0 + room]
        cut = max(cand) if cand else s0 + room
        plan.append((s0, cut, track, 0.0))
        print(f"music: {os.path.basename(track)} runs out after {room:.0f} s, next beat from {cut:.1f} s")
        s0 = cut
SECTIONS = plan
if os.environ.get("STUDIO_NO_MUSIC") == "1":   # {{STUDIO_NAME}} New Project "Music" unticked: voice + SFX only
    SECTIONS = []


def lufs(path, ss=0, t=60):
    err = subprocess.run(["ffmpeg", "-v", "info", "-ss", str(ss), "-t", str(t), "-i", path, "-af", "ebur128", "-f", "null", "-"],
                         capture_output=True, text=True, errors="replace").stderr
    import re
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", err)
    return float(m[-1]) if m else -14.0


BED = -31.0   # ~15 LU under the -16 LUFS voice (user v6: "a tad louder"; was -33)
SFX_EV = {    # graphic kind -> [(sfx file, volume, offset)]. User note v1: "too many risers" -> sound ONLY on section wipes,
              # one soft ping per code card, the subscribe click. No whooshes on stats/end card/phone slide-ins.
    # every section transition gets a swoosh on the wipe (user, dhgate coupons 2026-10-22: "every transition needs a sound
    # effect"; replaces the v4 tap + ding). Still no risers, and nothing on stats / end card / phone slide-ins.
    "wipe": [("whoosh-short.mp3", 0.32, 0.0)],
    "code": [("ping.mp3", 0.14, 1.75)],   # only a lone code card (see code_t below)
    "subscribe": [("click.mp3", 0.26, 1.12)],
}
a_inputs, a_graph, mix = [], [], []
# voice: a SLOW leveler (15 s gaussian window, max +2.5x) evens louder/softer stretches without pumping (user notes:
# dynamic loudnorm pumped at 1:50 in v1; a fixed gain alone left a 2.5 dB louder stretch at 1:42-1:52 in v8), then one
# measured gain to -16 LUFS so the music stays exactly 15 LU under the voice.
_vw = os.path.join(B, "voice_leveled.wav")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", SRC, "-vn", "-af", "dynaudnorm=f=500:g=31:m=2.5:p=0.89", "-ar", "48000", _vw], check=True)
_vl = lufs(_vw, 0, DUR)
inputs += ["-i", _vw]
VOICE_IN = n_in   # the leveled voice is the last "video-side" input; music/SFX inputs start after it
n_in += 1
base = n_in
a_graph.append(f"[{VOICE_IN}:a]aresample=48000,volume={-16.0 - _vl:.2f}dB[voice]")  # fixed gain only (compressor + join boost made the music sound boosted)
print("voice LUFS", _vl, "-> gain", round(-16.0 - _vl, 2))
mix.append("[voice]")
for k, (s, e, track, ms) in enumerate(SECTIONS):
    # measured over the stretch this section really plays (was the first 60 s after ms + 10: DoTheMove is 2.5 dB louder
    # after its first minute, so the bed sat ~12.5 LU under the voice instead of 15 from 1:30 on; dhgate coupons 2026-10-22)
    gain = BED - lufs(track, ms, max(10.0, e - s))
    a_inputs += ["-ss", f"{ms:.2f}", "-i", track]
    idx = base + len(a_inputs) // 4 - 1
    d = e - s
    # each track FADES OUT before the next one starts (user 2026-10-21: "always fade it out ... when you transition to
    # each track"; the old 1 s overlap ran two beats at once): 1.6 s fade ending on the section change, the next beat
    # comes in over 0.5 s, and the last one fades out under the end of the video
    fo = min(1.6, d / 3)
    a_graph.append(f"[{idx}:a]aresample=48000,atrim=0:{d:.3f},asetpts=PTS-STARTPTS,volume={gain:.2f}dB,"
                   + f"afade=t=in:d={0.5 if k else 1.0}," + f"afade=t=out:st={d - fo:.3f}:d={fo:.3f},adelay={int(s * 1000)}|{int(s * 1000)}[m{k}]")
    mix.append(f"[m{k}]")
sfx_n = 0
# code cards that come back to back get NO ping (user, Shein 2026-10-21: many codes close together, the ping "gets
# repetitive very quickly"): a code card only pings when no other code card is within 45 s of it
code_t = [ev["t"] for ev in events if ev["kind"] == "code"]
for ev in events:
    if ev["kind"] == "code" and any(0 < abs(t - ev["t"]) < 45 for t in code_t):
        continue
    for name, vol, off in SFX_EV.get(ev["kind"], []):
        a_inputs += ["-i", os.path.join(SFX, name)]
        idx = base + (len([x for x in a_inputs if x == "-i"])) - 1
        ms_ = int((ev["t"] + off) * 1000)
        a_graph.append(f"[{idx}:a]aresample=48000,volume={vol},adelay={ms_}|{ms_}[s{sfx_n}]")
        mix.append(f"[s{sfx_n}]")
        sfx_n += 1
a_graph.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first,alimiter=limit=0.84:level=0,afade=t=out:st={DUR - 1.2:.3f}:d=1.2,aresample=48000[aout]")
# 48 kHz forced: the mix used to come out at 24 kHz (format negotiation with the 24 kHz SFX mp3s) = everything above 12 kHz
# gone, the "muddy / muffled" voice (user, Shein draft 2026-10-21)

graph = ";".join(g + a_graph)
gp = os.path.join(B, "graph_main.txt")
open(gp, "w").write(graph)
out = os.path.join(E, "main-test.mp4" if "--test" in sys.argv else ("main-draft.mp4" if "--draft" in sys.argv else "main.mp4"))
cmd = ["ffmpeg", "-v", "error", "-stats", "-y"] + inputs + a_inputs + ["-/filter_complex", gp, "-map", "[vout]", "-map", "[aout]",
       "-t", (sys.argv[sys.argv.index("--test") + 1] if "--test" in sys.argv else f"{DUR:.3f}"), "-c:v", "h264_nvenc", "-profile:v", "high", "-pix_fmt", "yuv420p",
       "-cq", "23" if "--draft" in sys.argv else "19", "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-movflags", "+faststart", out]
print("inputs:", len([x for x in cmd if x == "-i"]), "graph chars:", len(graph))
subprocess.run(cmd, check=True)
print("wrote", out)

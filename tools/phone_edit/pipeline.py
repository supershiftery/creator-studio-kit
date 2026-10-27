"""Fully automatic phone-tutorial edit (Uber Eats style, approved 2026-10-20). Usage:
    python pipeline.py <project dir>        (the watcher creates <project>\\raw\\source.mp4 and, optionally, raw\\intro.wav)
Steps (each skipped when its output already exists, so a re-run resumes):
  1 mic track + transcript      work\\mic.wav, work\\words.json      (faster-whisper small.en, verbatim prompt)
  2 trim                        work\\cuts.json                      (take_cuts.py rules, approved on Uber Eats v16)
  3 privacy                     work\\privacy.json + blurred full-res cut edit\\cut-full.mp4
  4 layout                      edit\\layout.json                    (app mode / side camera)
  5 graphics                    edit\\graphics\\renders\\*.mov       (events.py + HyperFrames template, transparent MOV)
  6 main video                  edit\\main-draft.mp4                 (build_main.py)
  7 intro (only with raw\\intro.*) edit\\intro\\renders\\intro.mp4   (auto_intro.py)
  8 join + checks               output\\<name> - DRAFT.mp4, output\\report.md
"""
import json, os, re, shutil, subprocess, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
PY = sys.executable
HF = "npx --yes hyperframes@0.8.181"


def sh(cmd, **kw):
    print(">>", cmd if isinstance(cmd, str) else " ".join(cmd), flush=True)
    t = time.time()
    r = subprocess.run(cmd, check=True, **kw)
    # per-step seconds, so a slow revision shows which step it was (2026-10-24 speed pass)
    print(f"<< {time.time() - t:.0f} s  {os.path.basename(cmd.split()[0] if isinstance(cmd, str) else cmd[1] if len(cmd) > 1 else cmd[0])}", flush=True)
    return r


class same_content:
    """Wrap a step that rewrites files: any file that comes out byte-identical gets its old time back, so the steps
    after it (keyed on file times) are not redone for nothing (2026-10-24 speed pass: a re-cut with the same result
    re-rendered the full cut, layout, graphics, main video and privacy sweep)."""
    def __init__(self, *paths):
        self.paths = paths

    def __enter__(self):
        import hashlib
        self.before = {p: (hashlib.sha1(open(p, "rb").read()).hexdigest(), os.stat(p)) for p in self.paths if os.path.exists(p)}
        return self

    def __exit__(self, *exc):
        import hashlib
        for p, (h, st) in self.before.items():
            if os.path.exists(p) and hashlib.sha1(open(p, "rb").read()).hexdigest() == h:
                os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
        return False


def log(project, msg):
    with open(os.path.join(project, "output", "pipeline.log"), "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')}  {msg}\n")
    print(msg, flush=True)


def mic_track(src, work):
    """The speech track = the loudest audio track (OBS mixes can carry silent tracks)."""
    n = int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", src],
                           capture_output=True, text=True).stdout.count("\n"))
    best, best_db = 0, -999.0
    for i in range(max(1, n)):
        e = subprocess.run(["ffmpeg", "-v", "info", "-ss", "60", "-t", "120", "-i", src, "-map", f"0:a:{i}", "-af", "volumedetect", "-f", "null", "-"],
                           capture_output=True, text=True, errors="replace").stderr
        m = re.search(r"mean_volume: (-?[\d.]+) dB", e)
        if m and float(m.group(1)) > best_db:
            best, best_db = i, float(m.group(1))
    sh(["ffmpeg", "-v", "error", "-y", "-i", src, "-map", f"0:a:{best}", "-ac", "1", "-ar", "16000", os.path.join(work, "mic.wav")])
    return best


def _whisper():
    """small.en on the GPU when CUDA loads, else the CPU as before (_tools/whisper_gpu.py, 2026-10-22)"""
    sys.path.insert(0, os.path.dirname(HERE))
    from whisper_gpu import load
    m, where = load("small.en", cpu_threads=8)
    print(f"whisper: {where}", flush=True)
    return m


def transcribe(work):
    from faster_whisper import WhisperModel
    import wave
    w = wave.open(os.path.join(work, "mic.wav"))
    a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    m = _whisper()
    segs, _ = m.transcribe(a, word_timestamps=True, condition_on_previous_text=False,
                           initial_prompt="Um, so, so I I was, uh, the the thing is, like, like this.")
    out = [{"w": x.word.strip(), "s": round(x.start, 2), "e": round(x.end, 2), "p": round(x.probability, 2)} for s in segs for x in s.words]
    json.dump(out, open(os.path.join(work, "words.json"), "w"))
    fill_holes(work, a, m)


def write_seams(work):
    """work\\seams.md: every seam of the cut with the words either side, in draft order (main-video time), plus the
    short pieces. Read it before calling a draft done (Doordash 2026-10-21: cut-off sentences and leftover scraps
    reached the user because only the picture was checked)."""
    keep = json.load(open(os.path.join(work, "cuts.json")))["keep"]
    words = json.load(open(os.path.join(work, "words.json")))
    mid = lambda w: (w["s"] + w["e"]) / 2
    rows, acc = ["# Seams (main-video time; read every line before showing a draft)", ""], 0.0
    for i, (s, e) in enumerate(keep):
        inside = [w["w"] for w in words if s - 0.05 <= mid(w) < e]
        if i:
            prev = [w["w"] for w in words if keep[i - 1][0] - 0.05 <= mid(w) < keep[i - 1][1]][-6:]
            flag = " **SHORT PIECE**" if len(inside) <= 6 else ""
            rows.append(f"- {int(acc // 60)}:{acc % 60:04.1f}  ...{' '.join(prev)} **|** {' '.join(inside[:8])}...{flag}")
        acc += e - s
    open(os.path.join(work, "seams.md"), "w", encoding="utf-8").write("\n".join(rows) + "\n")


def fill_holes(work, a=None, m=None):
    """Whisper sometimes drops a whole stretch of clear speech (Doordash 2026-10-21: 28 s about the link + Google Voice
    came back as NO words, so the trim cut through the middle of that explanation). Any gap >= 3 s between words where
    the mic is at talking level gets transcribed again on its own and its words are put in. Marks words.json as checked."""
    import wave
    from faster_whisper import WhisperModel
    path = os.path.join(work, "words.json")
    words = json.load(open(path))
    if a is None:
        w = wave.open(os.path.join(work, "mic.wav"))
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    sr, n = 16000, 800  # 50 ms frames
    fr = a[:len(a) // n * n].reshape(-1, n)
    rms = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9)
    voice = float(np.percentile(rms, 90))  # their normal talking level
    talk = rms > voice - 15
    # gaps: before the first word, between words, after the last word
    gaps = list(zip([0.0] + [w_["e"] for w_ in words], [w_["s"] for w_ in words] + [len(a) / sr]))
    holes = []
    for gs, ge in gaps:
        if ge - gs >= 3.0 and talk[int(gs * sr / n):int(ge * sr / n)].mean() > 0.3:
            holes.append((gs, ge))
    # Whisper also HIDES speech inside one stretched word (Shein 2026-10-21: "like" stamped 2010.82-2013.86 swallowed "one
    # more time. This is the last time I got it.", so that bad take stayed in the draft). A word >= 1.5 s long with talking
    # under most of it is re-read with 3 words of context on each side, and those words are replaced by the new read.
    stretched = []
    for k, w_ in enumerate(words):
        if w_["e"] - w_["s"] >= 1.5 and talk[int(w_["s"] * sr / n):int(w_["e"] * sr / n)].mean() > 0.4:
            gs, ge = words[max(0, k - 3)]["s"], words[min(len(words) - 1, k + 3)]["e"]
            if stretched and gs <= stretched[-1][1]:
                stretched[-1] = (stretched[-1][0], ge)
            else:
                stretched.append((gs, ge))
    added = []
    for gs, ge in stretched:
        m = m or _whisper()
        s0 = max(0.0, gs - 0.3)
        segs, _ = m.transcribe(a[int(s0 * sr):int((ge + 0.3) * sr)], word_timestamps=True, condition_on_previous_text=False,
                               initial_prompt="Um, so, so I I was, uh, the the thing is, like, like this.")
        mid = lambda x: (x["s"] + x["e"]) / 2
        got = [{"w": x.word.strip(), "s": round(x.start + s0, 2), "e": round(x.end + s0, 2), "p": round(x.probability, 2)}
               for s in segs for x in s.words]
        got = [x for x in got if gs <= mid(x) <= ge]
        old = [x for x in words if gs <= mid(x) <= ge]
        if len(got) > len(old):  # only when the new read actually found hidden words
            words = [x for x in words if not gs <= mid(x) <= ge] + got
            print(f"stretched word {gs:.1f}-{ge:.1f} s: {len(old)} -> {len(got)} words", flush=True)
            added += got
    words = sorted(words, key=lambda w_: w_["s"])
    n_stretch = len(added)
    for gs, ge in holes:
        m = m or _whisper()
        s0 = max(0.0, gs - 0.3)
        segs, _ = m.transcribe(a[int(s0 * sr):int((ge + 0.3) * sr)], word_timestamps=True, condition_on_previous_text=False,
                               initial_prompt="Um, so, so I I was, uh, the the thing is, like, like this.")
        got = [{"w": x.word.strip(), "s": round(x.start + s0, 2), "e": round(x.end + s0, 2), "p": round(x.probability, 2)}
               for s in segs for x in s.words if gs - 0.05 <= x.start + s0 and x.end + s0 <= ge + 0.05]
        added += got
        print(f"transcript hole {gs:.1f}-{ge:.1f} s ({ge - gs:.0f} s of talking with no words): re-read {len(got)} words", flush=True)
    if added:  # stretched re-reads are already in words; hole words go in now
        hole_words = added[n_stretch:]
        words = sorted(words + hole_words, key=lambda w_: w_["s"])
        json.dump(words, open(path, "w"))
    open(os.path.join(work, "words.holes-checked"), "w").write(f"{len(holes)} holes, {len(stretched)} stretched, {len(added)} words added\n")


def run(project):
    raw, work, edit, out = (os.path.join(project, d) for d in ("raw", "work", "edit", "output"))
    for d in (work, edit, out):
        os.makedirs(d, exist_ok=True)
    src = os.path.join(raw, "source.mp4")
    name = os.path.basename(project.rstrip("\\/"))
    t0 = time.time()
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src],
                               capture_output=True, text=True).stdout)
    # the layout's raw-video scans need only the recording, so they CAN start now, alongside the transcript and privacy
    # scan. OFF by default: measured 2026-10-22 on dhgate coupons it made the first build slower (21.2 vs 18.5 min), the
    # CPU is already busy with the privacy scan (160 s -> 239 s). LAYOUT_WARM=1 turns it on (a machine with spare cores).
    warm = None
    if os.environ.get("LAYOUT_WARM") == "1" and not os.path.exists(os.path.join(work, "layout_yaw_3.pkl")):
        warm = subprocess.Popen([PY, os.path.join(HERE, "layout.py"), "--warm", src], stdout=open(os.path.join(work, "layout_warm.log"), "w"),
                                stderr=subprocess.STDOUT, cwd=work)
    # 1 transcript
    if not os.path.exists(os.path.join(work, "words.json")):
        log(project, f"track {mic_track(src, work)} is the mic; transcribing")
        transcribe(work)
    elif not os.path.exists(os.path.join(work, "words.holes-checked")) or "stretched" not in open(os.path.join(work, "words.holes-checked")).read():
        log(project, "checking the transcript for dropped speech")
        fill_holes(work)
    # every heavy step is skipped when its output is newer than its inputs, so a re-run (an intro dropped later, a
    # note in extra_cuts.json) only redoes what changed (user 2026-10-20: a late intro must not redo the whole edit)
    def stale(out_path, *inputs):
        if not os.path.exists(out_path):
            return True
        t = os.path.getmtime(out_path)
        return any(os.path.exists(i) and os.path.getmtime(i) > t for i in inputs)
    W = lambda f: os.path.join(work, f)
    D = lambda f: os.path.join(edit, f)
    # stage stamps (2026-10-24 speed pass): a stage whose output came out identical keeps the output's OLD time (so later
    # stages skip), and its stamp file records that the stage did run for these inputs (so it does not run again)
    st = lambda name, out: W(f"{name}.stamp") if os.path.exists(W(f"{name}.stamp")) else out
    done = lambda name: open(W(f"{name}.stamp"), "w").write(time.strftime("%Y-%m-%d %H:%M:%S"))
    # 2 trim (user notes go in work\extra_cuts.json and win)
    if stale(st("cuts", W("cuts.json")), W("words.json"), W("extra_cuts.json")):
      with same_content(W("cuts.json")):
          cut_cmd = lambda extra: [PY, os.path.join(TOOLS, "take_cuts.py"), W("words.json"), "60", work, "--duration", f"{dur:.3f}",
                                   "--extra", extra, "--audio", W("mic.wav"), "--video", src]
          if not os.path.exists(W("extra_cuts.json")):
              json.dump([], open(W("extra_cuts.json"), "w"))
          sh(cut_cmd(W("extra_cuts.json")))
          # take review (Claude reads the kept transcript for sections redone in different words, stray join words,
          # off-video lines; user 2026-10-21), then the cut again with its marks. PHONE_TAKE_REVIEW=0 turns it off.
          if os.environ.get("PHONE_TAKE_REVIEW", "1") != "0":
              intro_mp4 = os.path.join(edit, "intro", "renders", "intro.mp4")
              ilen = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", intro_mp4],
                                          capture_output=True, text=True).stdout or 0) if os.path.exists(intro_mp4) else 0.0
              try:
                  # same transcript + same notes = same review: reuse it. Studio rewrites extra_cuts.json on every run, and a
                  # fresh Claude pass can choose differently each time (dhgate coupons 2026-10-22: a re-run brought back a
                  # "for ... next code" scrap the first review had cut). Keyed on content, not file times.
                  import hashlib
                  rkey = hashlib.sha1(open(W("words.json"), "rb").read() + json.dumps(json.load(open(W("extra_cuts.json"))), sort_keys=True).encode()).hexdigest()
                  if os.path.exists(W("review_cuts.json")) and os.path.exists(W("review.key")) and open(W("review.key")).read().strip() == rkey:
                      log(project, "take review: transcript + notes unchanged, reusing work\\review_cuts.json")
                  else:
                      sh([PY, os.path.join(HERE, "take_review.py"), project, f"{ilen:.2f}"])
                      open(W("review.key"), "w").write(rkey)
                  merged = json.load(open(W("extra_cuts.json"))) + json.load(open(W("review_cuts.json")))
                  json.dump(merged, open(W("extra_all.json"), "w"), indent=1)
                  sh(cut_cmd(W("extra_all.json")))
              except Exception as e:  # no sign-in / no network: the rules-only cut stands
                  log(project, f"take review skipped: {e}")
      done("cuts")
    write_seams(work)
    # 3 privacy + full-res blurred cut
    # what each half shows per second (cam / phone / website): layout, privacy and the compositor read it
    if stale(W("halves.json"), src):
        sh([PY, os.path.join(HERE, "halves.py"), src, W("halves.json")])
    # re-scan when the private terms or the finder changed (the old Uber-only scan left DoorDash addresses unblurred)
    # {{STUDIO_NAME}} New Project "Privacy check" unticked (STUDIO_NO_PRIVACY=1, user 2026-10-22): no address scan, no blur,
    # no final sweep. An empty privacy.json makes privacy.py apply a plain copy.
    no_privacy = os.environ.get("STUDIO_NO_PRIVACY") == "1"
    if no_privacy:
        if not os.path.exists(W("privacy.json")) or json.load(open(W("privacy.json"))):
            json.dump([], open(W("privacy.json"), "w"))
        open(W("privacy.off"), "w").write("privacy.json is a placeholder: rescan when the check is turned back on\n")
        log(project, "privacy check OFF for this project (Studio setting): nothing is blurred")
    elif os.path.exists(W("privacy.off")) or stale(W("privacy.json"), src, W("halves.json"), os.path.join(TOOLS, "privacy_terms.json"), os.path.join(TOOLS, "privacy_ocr.py"), os.path.join(TOOLS, "privacy.py")):
        sh([PY, os.path.join(TOOLS, "privacy.py"), "find", src, W("words.json"), W("privacy.json")])
        if os.path.exists(W("privacy.off")):
            os.remove(W("privacy.off"))
    if stale(W("blank_phone.json"), src):
        sh([PY, os.path.join(TOOLS, "blank_phone.py"), src, W("words.json"), W("blank_phone.json")])
    if stale(D("cut-full-noblur.mp4"), W("cuts.json")):
        sh([PY, os.path.join(TOOLS, "render_draft.py"), src, W("cuts.json"), D("cut-full-noblur.mp4"), "--width", "3840", "--fps", "30", "--cq", "19"])
    if stale(D("cut-full.mp4"), D("cut-full-noblur.mp4"), W("privacy.json")):
        sh([PY, os.path.join(TOOLS, "privacy.py"), "apply", D("cut-full-noblur.mp4"), W("cuts.json"), W("privacy.json"), D("cut-full.mp4"), "--scale", "1.0"])
    # 4 layout + 5 graphics
    g = os.path.join(edit, "graphics")
    os.makedirs(os.path.join(g, "renders"), exist_ok=True)
    new_layout = stale(st("layout", D("layout.json")), W("cuts.json"), W("halves.json"), os.path.join(HERE, "layout.py"))
    if warm is not None:
        warm.wait()   # its caches are what layout.py reads next
    lay_guard = same_content(D("layout.json")).__enter__()   # layout.py + bridge.py together: same result = old time
    if new_layout:
        sh([PY, os.path.join(HERE, "layout.py"), src, W("cuts.json"), D("layout.json")])
    for f in ("index.html", "package.json", "hyperframes.json", "render_all.py"):
        # render_all.py is tooling, not project content: always take the current one (parallel renders 2026-10-21)
        if f == "render_all.py" or not os.path.exists(os.path.join(g, f)):
            shutil.copy(os.path.join(HERE, "templates", "graphics", f), os.path.join(g, f))
    # codes are read off THIS video's screen (they change, user 2026-10-21) -> one card each (events.py)
    scj = D("screen_codes.json")
    if stale(scj, D("cut-full.mp4"), os.path.join(HERE, "screen_codes.py")) or stale(scj, D("screen_codes.manual.json")):
        sh([PY, os.path.join(HERE, "events.py"), W("cuts.json"), W("words.json"), edit])   # writes out_words.json first
        sh([PY, os.path.join(HERE, "screen_codes.py"), D("cut-full.mp4"), D("out_words.json"), scj])
    ev = os.path.join(g, "events.json")
    if stale(st("events", ev), W("cuts.json"), W("words.json"), os.path.join(HERE, "codes.json"), scj, os.path.join(HERE, "events.py")):
        ev_t = os.path.getmtime(ev) if os.path.exists(ev) else 0
        with same_content(ev, D("out_words.json")):
            sh([PY, os.path.join(HERE, "events.py"), W("cuts.json"), W("words.json"), edit])
        done("events")
        if not os.path.exists(ev) or os.path.getmtime(ev) != ev_t:   # a new plan means new graphics (renders\_cache keeps
            for old in os.listdir(os.path.join(g, "renders")):         # the unchanged ones: render_all copies them back)
                if os.path.isfile(os.path.join(g, "renders", old)):
                    os.remove(os.path.join(g, "renders", old))
            new_layout = True
    if new_layout:
        sh([PY, os.path.join(HERE, "bridge.py"), D("layout.json"), D("out_words.json"), src, W("cuts.json")])  # phone stays up while read
        done("layout")
    lay_guard.__exit__(None, None, None)
    sh([PY, "render_all.py"], cwd=g)  # renders only the graphics that are missing
    # 6 intro first (the main video picks a different beat than the intro: edit\intro_music.json)
    intro = next((os.path.join(raw, f) for f in os.listdir(raw) if f.lower().startswith("intro.")), None)
    if intro:
        idir = os.path.join(edit, "intro")
        # videos with website stretches get the "screens" intro (intro library P02, the approved Shein look): the user's real
        # pages from THIS video in moving browser windows (intro_footage.py picks store / link pages, never codes, tables or
        # blurred spots). User 2026-10-22 (dhgate coupons): the designed-only intro had no clips, no movement and a food order.
        # Phone-screen videos keep auto_intro (Uber Eats / DoorDash look).
        foot = D("intro_footage.json")
        if stale(foot, D("layout.json"), D("cut-full.mp4"), os.path.join(HERE, "intro_footage.py")):
            sh([PY, os.path.join(HERE, "intro_footage.py"), edit, foot])
        # outside B-roll for store apps: his own haul footage of that store + its live site (intro_extras.py, coupons
        # 2026-10-24: "maybe we just don't have enough B-roll from the original video ... lacking character")
        try:
            apps = json.load(open(os.path.join(HERE, "apps.json"), encoding="utf-8"))
            low = name.lower()
            key = next((k for k, a in apps.items() if isinstance(a, dict) and any(re.search(r"\b" + re.escape(x) + r"\b", low) for x in a.get("aliases", [k]))), None)
            # every app now (2026-10-25 asset mix): store extras stay shop-only inside intro_extras; the outside sources
            # (thumbnail wall / viewer comments / city maps) work from the VO for any app
            try:
                chan = json.load(open(os.path.join(project, "studio.json"), encoding="utf-8-sig")).get("channel") or "{{PHONE_CHANNEL}}"
            except (OSError, ValueError):
                chan = "{{PHONE_CHANNEL}}"
            sh([PY, os.path.join(HERE, "intro_extras.py"), key or "none", foot, "--vo", intro, "--title", name, "--channel", chan])
        except Exception as err:
            print(f"intro extras skipped: {err}", flush=True)
        screens = len(json.load(open(foot))) >= 2
        ij = os.path.join(idir, "intro.json")
        built = json.load(open(ij)).get("template") if os.path.exists(ij) else None
        # STUDIO_INTRO_REBUILD=1: Studio's {"intro": "rebuild"} / a batch with intro notes re-makes it (fresh footage + music)
        if (stale(os.path.join(idir, "renders", "intro.mp4"), intro) or (built in ("P02", "P21")) != screens   # P21 = live phone style since 2026-10-24
                or os.environ.get("STUDIO_INTRO_REBUILD") == "1"):
            # no dates/years in any graphic (user rule 2026-10-20: dates make a video time-sensitive)
            title = re.sub(r"(?i)\b(19|20)\d\d\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b", "", name)
            title = re.sub(r"\s+", " ", re.sub(r"(?i)\b(raw|part \d+|v\d+|promo codes?)\b", "", title)).strip()
            if screens:
                sys.path.insert(0, HERE)
                from auto_intro import DEFAULT_MUSIC
                # his special requests from Studio's New Project (studio.json settings.requests, 2026-10-23) go to the intro director
                sj = os.path.join(project, "studio.json")
                req = (json.load(open(sj, encoding="utf-8-sig")).get("settings") or {}).get("requests", "") if os.path.exists(sj) else ""
                xj = D("intro_extra.json")
                json.dump({"requests": req} if req else {}, open(xj, "w"))
                # no forced track: build_intro picks from the whole {{MUSIC_ROOT}} library (music_lib.py, 2026-10-24: every phone
                # intro used to get DEFAULT_MUSIC "Family Matters"); a track he picked in Studio (slots.music.intro) wins
                sd = json.load(open(sj, encoding="utf-8-sig")) if os.path.exists(sj) else {}
                want = ((sd.get("slots") or {}).get("music") or {}).get("intro")
                bcmd = [PY, os.path.join(TOOLS, "intro_library", "build_intro.py"), "--type", "phone", "--template", "P21", "--vo", intro,   # P21 Editor Phone: he accepted it 2026-10-24 ("this definitely moves the video forward")
                        "--title", title, "--footage", foot, "--out", idir, "--render", "--extra", xj] + (["--music", want] if want else [])
                sh(bcmd)
                # the intro checks itself before he sees it, like review intros (2026-10-24: phone intros never ran the check;
                # dhgate coupons went out with 30% half-empty frames). Bad shots become pins, re-rendered on the same plan;
                # two fix rounds, the last look only reports (intro/intro_check.md)
                try:
                    sys.path.insert(0, os.path.join(TOOLS, "intro_library"))
                    import intro_check
                    rendered = os.path.join(idir, "renders", "intro.mp4")
                    for rnd in range(1, 4):
                        res = intro_check.check(idir, lambda m: print(m, flush=True))
                        if not res["pins"] or rnd == 3:
                            break
                        e = json.load(open(xj))
                        have = {p["from"] for p in e.get("auto_pins", [])}
                        e["auto_pins"] = e.get("auto_pins", []) + [p for p in res["pins"] if p["from"] not in have]
                        json.dump(e, open(xj, "w"))
                        good = rendered[:-4] + ".checked_prev.mp4"
                        shutil.copy2(rendered, good)
                        r = subprocess.run(bcmd + ["--reuse-plan"])
                        if r.returncode or not os.path.exists(rendered) or os.path.getsize(rendered) < 100000:
                            shutil.copy2(good, rendered)   # a failed re-render keeps the last good intro
                            break
                except Exception as err:   # the check never stops a build
                    print(f"intro self-check skipped: {type(err).__name__}: {str(err)[:160]}", flush=True)
                # the main video starts a different beat than the intro (build_main reads this; a requested track wins)
                ji = json.load(open(ij))
                json.dump({"track": ji.get("music") or DEFAULT_MUSIC, "end": ji["dur"]}, open(D("intro_music.json"), "w"))
            else:
                sh([PY, os.path.join(HERE, "auto_intro.py"), intro, title, idir])
                sh(f'{HF} render --quiet -o renders/intro.mp4', cwd=idir, shell=True)
                if os.path.exists(ij):
                    os.remove(ij)
    # 7 main video (rebuilt when the cut, layout, graphics plan or intro beat changed)
    shutil.copy(os.path.join(HERE, "build_main.py"), D("build_main.py"))
    # the compositor itself is an input too: a fix to it (music levels, SFX) must reach the next draft
    if stale(D("main-draft.mp4"), D("cut-full.mp4"), D("layout.json"), os.path.join(g, "events.json"), D("intro_music.json"),
             os.path.join(HERE, "build_main.py")):
        sh([PY, D("build_main.py"), "--draft"], cwd=edit)
    final = os.path.join(out, f"{name} - DRAFT.mp4")
    if intro:
        idir = os.path.join(edit, "intro")
        sh([PY, os.path.join(HERE, "join.py"), os.path.join(idir, "renders", "intro.mp4"), os.path.join(edit, "main-draft.mp4"), final])
    else:
        shutil.copy(os.path.join(edit, "main-draft.mp4"), final)
    # 8 checks
    rep = [f"# {name}", "", f"- source {dur / 60:.1f} min -> draft (intro: {'yes' if intro else 'no'})",
           f"- built in {(time.time() - t0) / 60:.1f} min"]
    # privacy sweep only when the PICTURE inputs changed (user 2026-10-20: re-running it after audio-only changes wasted ~9 min)
    import hashlib
    fp = hashlib.sha1()
    # phone_box.json too: a new phone crop shows a strip of the phone that was never swept (Uber codes october 2026-10-25)
    for f in (os.path.join(work, "cuts.json"), os.path.join(work, "privacy.json"), os.path.join(edit, "layout.json"),
              os.path.join(work, "blank_phone.json"), os.path.join(edit, "phone_box.json"), src):
        if not os.path.exists(f):
            continue
        fp.update(open(f, "rb").read() if f != src else str(os.path.getsize(src)).encode())
    fp = fp.hexdigest()
    cache = os.path.join(work, "privacy_pass.json")
    prev = json.load(open(cache)) if os.path.exists(cache) else {}
    if no_privacy:
        rep.append("- privacy: OFF for this project (Studio setting), nothing scanned or blurred")
    elif prev.get("fingerprint") == fp:
        rep.append(f"- privacy: picture inputs unchanged since the last passing sweep ({prev.get('when')}), skipped")
    else:
        print("== privacy sweep", flush=True)  # stage markers for {{STUDIO_NAME}}'s progress bar
        pv = subprocess.run([PY, os.path.join(TOOLS, "final_privacy_sweep.py"), final], capture_output=True, text=True)
        rep.append(f"- privacy: {pv.stdout.strip().splitlines()[0] if pv.stdout else pv.stderr[-200:]}")
        if pv.returncode == 0:
            json.dump({"fingerprint": fp, "when": time.strftime("%Y-%m-%d %H:%M")}, open(cache, "w"))
        else:
            rep.append("- PRIVACY FAILED: do not upload; see the sweep output above")
    print("== QC check", flush=True)
    qc = subprocess.run([PY, r"{{KIT}}/assets/Tools/check_video.py", "check", final, "--sheets", "none", "--no-words"],
                        capture_output=True, text=True)
    qc_lines = qc.stdout.strip().splitlines()
    rep.append(f"- QC: {next((l for l in qc_lines if ' flags ' in l), qc.stderr[-200:])}")
    broken = [l for l in qc_lines if l.startswith("!! BROKEN")]
    rep += [f"- ❌ {l[3:]}" for l in broken]
    rep.append("- cut list (bad takes removed, REVIEW items): work\\cuts.md")
    open(os.path.join(out, "report.md"), "w", encoding="utf-8").write("\n".join(rep) + "\n")
    if qc.returncode == 3:   # stretched/frozen render (Uber october draft 1): fail the build, never hand it to the AI QC
        print("\n".join(broken), flush=True)
        sys.exit(3)
    log(project, f"done: {final}")
    return final


if __name__ == "__main__":
    run(sys.argv[1])

---
name: phone-tutorial-edit
description: Edits the user's ({{PHONE_CHANNEL}}) raw app / promo-code tutorial videos (Uber Eats, DoorDash, Shein, Chime, Atapole-type apps) recorded as a 3840x1080 side-by-side OBS capture (webcam left, PC screen with a mirrored phone right). Covers the Gling XML drop in {{PROJECTS_ROOT}}, bad-take cutting, phone-screen crop, a HyperFrames intro built from the user's VO + phone footage, segmented music, half-size drafts and the 10 fps QC check. Use when the user asks to edit, cut, check or render one of these phone/app videos. Not for DHgate product reviews (product-review-edit) or Minecraft videos (minecraft-video).
---

> **Before showing ANY draft and on every note: run the `editor-gate` skill** (one-take mode, per-type pre-show checks, note -> check, laptop sync).

**EDIT RULES FIRST (2026-10-25):** before building or showing ANY draft, read `{{KIT}}/tools\EDIT_RULES.md` (every past revision note turned into rules) and run its section I, the editor's pass. A note that says "again" / "never" means a rule exists but nothing checks it: build the check and update that file.


## Start here (2026-10-22)
Read the memory `video-editing-playbook` first: it is the single current rulebook (newer than older notes below where they disagree).
Targets measured from the approved Shein FINAL (best phone edit):
- **Intros: read `{{KIT}}/tools\intro_library\INTRO_RULES.md` first** (approved/rejected rulebook, asset mix 4+ source kinds with product <= 50%, pre-send check) and pick a style from `STYLES.md` (80 editorial styles, 20 per type; his Keep/Tweak/Drop votes at https://claude.ai/artifact/MZm9akvvCr7k8NvhW7inU9, db collection verdicts).
- Cold-open intro ~17 s: curiosity hook (codes "GATEKEPT"/blurred, price drop proof, counter "1 → 9 promo codes, $188 saved"), new visual every ~2 s, ends on the title.
- Full-cam talking ~20 s, first code card by ~0:40.
- Keep ~24% of the raw at ~214 wpm; median kept piece ~14 s.
- Mix -16 LUFS integrated, LRA ~4.5, peak -1.3 dBTP.
- Every Studio build writes `<video> targets.md` (tools/targets_check.py vs these numbers): read it before showing a draft and fix each ⚠️ or say why not. The AI take review is frozen after draft 1 (settings.take_review = "fresh" re-asks).

# Phone tutorial edit (training started 2026-10-20 on "uber eats promo codes may 2025")

STATUS: in training. The cut + check stages work. Layout, intro and music get decided with the user (see "Open
decisions"). Record every note the user gives here by REWRITING the rule it changes, never by stacking a new one.

## Inputs
- Raw videos live in `{{RECORDINGS}}`. Named files = full videos, date-named files = not set up yet.
- Normal flow (user, 2026-10-20): the user cuts the talking in **Gling** and drops the **XML into `{{PROJECTS_ROOT}}`**.
  Use the XML's kept ranges as the cut (saves credits). Parse it with
  `{{KIT}}/review_pipeline\scripts\xml_cuts.py` (gives the original media path + kept
  ranges) and build from the ORIGINAL file, which has every audio track. CAUTION: the product-review watcher in `{{KIT}}/watcher`
  also picks up XML drops and will treat it as a product review. Check with the user before relying on it.
- No XML? Fall back to `{{KIT}}/tools\take_cuts.py` (below).
- Intro VO: a separate WAV the user records (e.g. `Downloads\uber eats codes.wav`). Copy it to `<project>\intro\intro-vo.wav`.
- The finished video = **intro first, then the edited main video**, with music added. Always in that order.

## Source layout (3840x1080 OBS capture, measured on the Uber Eats test)
- Left half x 0-1920 = webcam (Camo Studio). Right half x 1920-3840 = PC screen.
- Phone mirror sits inside the right half with black bars: **x 2628-3132, full height (504x1080)**. Re-measure per video:
  sample 1 frame / 10 s and take the most common bbox of pixels > 12 in the right half (code in "Lessons").
- The first ~45 s can have a SECOND camera (side angle) in the right half instead of the phone, so it's a dual-cam intro.
- Watch for junk frames: a "Configure Camo Studio" error card (~0:45 on the Uber test), dark frames before the phone appears.
- Audio: track 0 = mic, track 1 = silent on the Uber test. Identify tracks by MEASURING levels, never by order (product-review lesson).

## Cut (fallback when there is no Gling XML)
```
python "{{KIT}}/tools\take_cuts.py" work\words.json 60 work --duration <sec> --extra work\extra_cuts.json --audio work\mic.wav
```
- Transcript: faster-whisper `small.en`, `word_timestamps=True`, `condition_on_previous_text=False`, and the verbatim
  initial_prompt "Um, so, so I I was, uh, the the thing is, like, like this." Pass audio as a numpy array (PyAV decode
  is broken on this machine). GPU fails (missing cublas64_12.dll), so use CPU int8 (~4 min for 17 min of audio).
  Whisper can silently DROP a whole 30 s window of clear speech (Doordash: 2 of them). `pipeline.fill_holes` re-reads
  every >= 3 s word gap where the mic is at talking level; `work\words.holes-checked` marks it done.
- Rules: keep the LAST clean take of every line. Intro = the last "hey guys" take in the first 90 s. Restarts are matched on
  the opening words (stutter within 6 s and ≤ 6 words, 3 words exact; same line again = 8 opening words exact, or 7 of 8 / 4 of 5
  ONLY if the earlier try was abandoned, meaning a pause within 14 words, or a ≤ 25-word sentence followed by a pause). Both takes slide back
  over identical words, and the kept take snaps back to a SENTENCE start (a comma is not a start: "hey guys, | shift reviews" was clipped).
  One-word stutters get cut ("very very" etc. are allowed). Asides to themself ("cut that", "hold on", "nope", "whoops") are cut and listed as REVIEW.
  So are spoken notes to the editor ("blur the address", "cut it at this", "run that whole thing back", "leaking my address", "my bad") -
  in a long unpunctuated line only the cue's sentence goes. Off-camera asides: a line 4-9 dB under their voice while the webcam shows them
  looking down at the phone / turned away (pitch >= +7 or yaw >= 18 vs their pose on normal lines; `--video src`), plus a short quiet line
  between two cut asides ("Well Zach left"). Mutter = >= 9 dB under (8 caught real lines). Scraps: a <= 4-word piece repeated in the next
  piece's opening words, or a <= 6-word piece opening with the same 2 words as the next ("Next up is going to be | Next up we're...") go.
  Words count by their MIDDLE (one starting on a cut edge belongs to the cut).
  Silences come from the AUDIO (silencedetect -42 dB 0.8 s), not word gaps: Whisper stretches words over pauses. They shrink to 0.2 s.
- Output: `work\cuts.json` (keep ranges, frame-snapped) + `work\cuts.md` (a review list with every cut and its words).

## Privacy blur (ALWAYS, user rule 2026-10-20; text-based since 2026-10-21)
- `_tools\privacy_terms.json` (LOCAL ONLY, never copy into notes/chats/memory) holds the user's addresses + real name. `privacy_ocr.py`
  reads the phone with Windows OCR in ANY app (the Uber-only templates missed every DoorDash address). An address box also covers the
  line above/below (a half-scrolled "...to Hidden" leaked). The final sweep OCRs the finished frame at 2 fps too, in STRICT mode:
  an exact street word fails at once, but a one-letter-off fuzzy word needs a 2nd address piece (number/ZIP/town) on that or a
  neighbouring line. The blur FINDER stays loose (fuzzy alone = blur). Reason: the half-hidden Eureka survey name "Unimrkt Response
  IncIndia" (under the "New Daily Poll" pill, ~8 px) OCR'd as noise one letter off the street name and failed a clean DoorDash draft
  (2026-10-21). If the sweep fails, look at the flagged frame before re-cutting: a real leak shows an address LINE, noise shows app text.
- `privacy.py apply` re-encodes only the keyframe pieces holding boxes (copy when none); the find pass searches windows in parallel.
The user's home address and phone number show on the phone (Carts "Deliver to ...", Checkout Delivery tab). Every render:
```
python "{{KIT}}/tools\privacy.py" find <source> work\words.json work\privacy.json   # spoken cues + every on-screen hit
python "{{KIT}}/tools\privacy.py" apply <cut.mp4> work\cuts.json work\privacy.json <out.mp4>
python "{{KIT}}/tools\privacy.py" check <out.mp4> work\cuts.json work\privacy.json     # must say 0 problems
```
- Templates in `_tools\privacy_templates` (street name, address line, phone number) are reused across videos. Add any new
  private field (card, email) the same way.
- find = 4 fps pass, then a 30 fps pass around each hit (boxes lagged behind fast scrolls), and EVERY match per frame
  (several cart rows show the address at once, and the house number varies, so match on the street name).
- check = frame-exact box sharpness (Laplacian var > 400 = readable) PLUS a sweep of the whole phone for any template.
  The sweep is what caught the rows the finder had missed. Never trust a box list alone.

## Learned from the user's finished edit (youtube dnacX9U83Hk, 8:55 with a 24.7 s intro (ends on "Let's go", then "Hey guys"), compared with compare_to_final.py)
- `python "{{KIT}}/tools\compare_to_final.py" work\words.json <finished words.json> work\cuts.json`: aligns the user's upload
  to the raw recording and lists OVER-KEPT / OVER-CUT. Run it whenever the user sends a finished video, then turn every real diff into a rule.
- The user cuts: muttering while navigating (≥ 9 dB under their voice: "what was I called", "how do you put in the code"),
  first reads of on-screen survey text and thinking aloud ("monkey, wait, dog, oh, desk"), fuzzy restarts
  ("once you are signed up" → "once you GUYS are signed up"), stuck lines (3+ times), and dead-end sentences
  ("next up is going to be... sit back and wait"). Their main part = 8:30 (510 s). Talking time was the same as mine (490 s); the gap was PAUSES (their 20 s vs my 36 s), so pauses > 0.4 s now shrink to 0.24 s. My cut: 8:40. The remaining ~10 s is the first Eureka take + the "once you have your order" dead-end sentence.
- Leftover diffs under 2 s are mostly Whisper wording or the same words taken from a different take. Ignore them.

## Draft + check loop (read `{{KIT}}/tools\CHECKING.md`)
1. `python "{{KIT}}/tools\render_draft.py" <source> work\cuts.json <project>\draft-cut-vN-halfsize.mp4`
   One select/aselect pass at 1920x540, NVENC, about 1 min for a 17 min source. Picture and sound can't drift.
2. `check_video.py check <draft> --raw`, then `feedback_cuts.py <draft_check\report.json> work\cuts.json work\extra_cuts.json`, then re-cut.
3. Read the draft transcript at every seam (intro, restart chains, outro) before showing the user.
4. Full-quality render only after the user approves the cut. H.264 High yuv420p + AAC, never HEVC.

## Intro style P21 "Editor Phone" (LIVE since 2026-10-24, he accepted it: "this definitely moves the video forward")
pipeline.py builds `--template P21` for every phone video with website footage (was P02). Built over one long day of his
notes on the DHgate coupons intro; test render `{{PROJECTS_ROOT}}\_tests\intro_editor_p21\intro\renders\intro.mp4` (not put in
the project: he said no rebuild). Every rule below is a note he gave; don't undo any of them.
- **Real footage first, always.** `intro_footage.py` (the video's own website moments) + `intro_extras.py` (store apps: his own
  HAUL footage of that store from `{{DRIVE_RAW}}` via product_library, and the store's live site when it isn't walled).
  "In the future we're going to have more footage, so we want to be accommodating": every clip-free line that has no graphic
  of its own takes an unused real clip (build_intro type cap, `context_gfx`). Each PAGE once (`page_once`: all scroll
  positions of one listing are one page, thumb distance < 45). Haul clips only on store / product lines, never filler.
- **Clips full frame** (`window.CLIP_FULL`), never small cards on an empty page. Captions have a black outline so they read on
  white pages.
- **Lines with no real clip get a number-free motion graphic of what he says** (P21 scene.js, glowing, dark base): fees /
  shipping / taxes -> CHECKOUT panel whose rows land on the words and carry over the lines; surprising -> TOTAL bar + red
  arrow; "in today's video" -> the app icon with rings; promo codes -> tickets with HIDDEN codes; save money -> PRICE tag
  struck + green SAVE stamp. NEVER a number he doesn't say (the old cards invented totals and coupon amounts: "numbers keep
  changing so I'm confused"). No stock people / random B-roll (`backdrops: false`): "this girl, what is she doing".
- **Simple + glowing:** one caption track (K.punch: 2-3 word uppercase phrases, key words glow in the app colour), captions
  low, no scene text, no browser bar, no "?" graphic. "We had glowing text, I thought that was a cool thing."
- **Alive, not sleepy:** a moving world behind everything (perspective grid floor + rising light particles); a graphic that
  spans several lines is ONE graphic with one continuous push (no re-pop, no freeze); the camera punches in on each checkout
  row as he says it; a zoom pulse on every glowing key word (zoom, never shake); a new view every ~1-2 s like the reselling
  spreadsheet intro (6.4 changes / 10 s).
- **Arc:** a turn moment on "In today's video" (rings burst + zoom punch) and a title payoff ON "let's go" (icon slam, light
  rays, app title + pill). Music stays one steady beat (no drop), bed -28 LUFS (template `bed`).
- **Sound (story_sfx):** a key tap as each fee lands, ping on the turn, click as the tickets fan in, cash register on "save",
  ping on the title. Quiet, no whooshes / risers / bass. SFX names need the file extension.
- **Transitions:** a smooth PUSH (new scene glides in from the right, old one out left, both fading) and ONLY when the
  picture changes. NO white flashes, NO light leaks, NO orange swipe, NO orange closing wipe ("random flashes were too
  much"; "don't like the transition if you're not transitioning to anything"; "agree with the transition to the logo").
  NO cartoon FX at all (burst / fire / smoke puff / swirl: "corny ... makes the quality go down").
- **Check before showing:** intro_check runs on phone intros now (2 fix rounds): long holds, repeats, page runs, names with
  no shot, empty frames (warning). Motion check: no still frames inside a graphic run, no sudden brightness jumps.
- Files: `intro_library/templates/phone/P21-editor-phone/` (scene.js, template.json flags `editor context_gfx page_once
  story_sfx`, `backdrops: false`, `bed: -28`), kit.js (K.punch, K.director cut "push" + CUT_ON_CHANGE), memory
  intro-quality-gate.md + no-corny-effects.md.

## Intro (older method, before P21; kept for history)
- AUTO (`auto_intro.py`, rebuilt 2026-10-21 after "the whole intro is missing motion graphics": it used to show stripped key words
  as captions): the Uber kit placed on VO words. Deals (if >= 1.6 s before the money line) -> cart + receipt adding up -> total slam ->
  blackout on "in today's" -> TOP SECRET folder + method cards (on "methods"/"secret") -> price struck to $0.00 + 100% FREE (on "free")
  -> group chat (on "friends") + $0.00 orders (on "over/again") -> FREE <APP> title on "let's go". Accent + icon from apps.json
  (`intro_methods` per app optional). Always look at 10 rendered frames before using it.
- Transcribe the VO, then make one scene per line that turns the sentence into a literal visual. Use the user's own phone footage
  from the raw video (the cart, the price climbing to $25, the promo code screen) before anything generated.
- Arc: problem half → dip on the turn line ("In today's video") → music DROP → reveal → slam on "Let's go".
- Build it in HyperFrames, using the template idea from `{{KIT}}/assets\Graphics\HyperFrames\servers-intro-oct`.
  No Higgsfield credits without the user's go ([[wait-for-assets-before-generating]]).
- No captions. Instrumental music only. Bed about 17 LU under the voice (VO about -17 LUFS, bed about -34 LUFS), measured with ebur128.

## Decisions (user, 2026-10-20, via buttons)
- Layout SWITCHES PER BEAT: full-screen webcam while only talking; phone big in the center with the face cam beside it while
  showing the app (cut on the phone action, not on the spoken cue).
- Silent phone-demo waits (tapping through the app) are SPED UP 2-4x so every tap stays visible. Talking silences still shrink to 0.2 s.
- Content calls: cut rants that contradict the method ("Eureka screwed me") but keep the method and code itself.
- Music: type beats from {{MUSIC_ROOT}} (instrumental, Whisper-scanned), like the product reviews, one track per section.
- Ask any further open question with AskUserQuestion buttons. The user prefers clicking.

## Lessons
- Phone bbox: `cols = where((gray_right_half > 12).mean(axis=0) > 0.3)`. Take the most common (min, max) over 1/10 s samples.
- The checker's repeat/brief fire on phone scrolls and app loading screens in raw drafts, so use `--raw` and re-check the final layout.
- Whisper hides doubled words (it drops one and stretches the neighbour). The checker flags long words and the spliced-audio echo for that reason.

## Training log: user notes on the Uber Eats drafts (2026-10-20), and the rule each one changed
| note (draft time) | what was wrong | rule now |
|---|---|---|
| v7 0:27-0:33, 0:47 | abandoned openers / "once you have... once" leftovers | false-start before a retake chain goes too; orphan fragment (< 9 words, stutters inside) dropped |
| v7 1:40, v10 6:40 | asides/muttering inside long unpunctuated lines | mutter rule (>= 9 dB under the voice); user notes win over auto rules |
| v7 2:09, 3:39 | a phrase said 3+ times | stuck-line rule: keep the last time |
| v10 0:40 | stray "for" from the previous take | no slide-back step; the kept take snaps to a SENTENCE start (looks back 10 words, not 6) |
| v10 1:22, 2:03, 3:01, 3:23, 7:41 | clipped words, "too snappy" | NO trims inside sentences (pauses > 0.4 s only between sentences; mid-sentence only measured stalls >= 1 s, trimmed to 0.4 s). Every cut edge sits on REAL audio quiet (>= 80 ms runs for pauses); cut starts look for quiet BEFORE the first removed word; a one-shot in-word repair (never cascading); the user's own note edges are never moved |
| v10 1:40-1:46 | "take it uh uh / this is actually going to be" mess | user note: keep "easily take advantage of" + the final clean take (the user's own edit did the same) |
| v10 2:18 | gray app-loading screen = dead space | `blank_phone.py`: detail < 2 = dead screen; no words -> cut, words -> hold the last phone frame in the final layout |
| v10 3:23 | "go to to make" lost a "to" | legit doubles allowed: very, really, to, that, had, is... |
| v10 7:18 | "go out and cash out" heard as "go out out", and the 1st "out" was cut | 1-word stutters only when both words <= 0.45 s; checker fixes must be confirmed in the RAW transcript |
| v10 8:17 | outro started 7 words late | sentence-start snap looks back 10 words |
| privacy | 2 cart rows (a different house number) and fast scrolls not blurred | all matches per frame, street-name template, 30 fps pass, half-frame slack, whole-phone sweep check |
| v14 0:41 | "for, uh" tail of a broken take (Whisper puts "when" ~1 s early) | user-note cut; edges from the audio, not Whisper times |
| v14 1:21, 1:41 | "promotion|s", "take advantage|of" clipped | user-note edges are EXACT: no quiet-snapping, no repair; set them on measured silence |
| v14 4:27 | "do this. This is why" lost "this" | a double across a sentence break is never a stutter |
| v15 2:55 | "beneficial" clipped: I set the note edge from Whisper's word end (373.6), the word runs to 373.95 | set every note edge on MEASURED silence, never on Whisper times |
| v15 2:57 | "card holder, [I] I actually": a 1-letter stutter cut mid-sentence | never stutter-cut 1-letter words (I, a); seam check now 0 edges on sound |
| v14 0:41 side effect | blanket "notes win" rule brought back half a broken take | notes PROTECT explicit word ranges ("protect": [s, e]) instead |
| user's finished edit | 16 s longer than theirs | it was pauses, not words: same talking time (490 s) |
| Doordash 1:06, 2:30 | sentences cut off mid-explanation | Whisper dropped 2 x 30 s of speech: fill_holes re-reads talking gaps |
| Doordash 1:12, 1:16-1:40, 1:50-1:58 | scraps + off-camera asides kept (power mirror, "Zilla", "blur the address") | off-camera aside + editor-note cues + scrap rules (see Cut) |
| Doordash intro | no motion graphics | auto_intro rebuilt as designed scenes (see Intro) |
| Doordash privacy | DoorDash address never blurred | OCR of the user's terms in any app |
| Doordash 7:59 sweep FAIL | false alarm: half-hidden survey name OCR'd one letter off the street | final sweep = strict OCR (fuzzy needs a 2nd address piece) |
| Doordash 5:25 | section intro said twice in different words | ALWAYS cut the first announcement (user: "obviously"): `find_reopened` (next up / next method / another way ... within 25 s) |
| Doordash review of seams | "what the heck" cue cut a real line; stuck-line rule cut the Attapoll code steps | sentence-level aside cuts only for editor notes (EDITOR_CUES); stuck line needs <= 12 words between repeats and keeps the last time from its sentence start |
| Doordash v2 3:02-3:24, 6:11-6:43, 9:14-9:32 | a SECTION abandoned and redone in different words stayed (DashPass, cart attempt, "only downside") | no automatic rule yet: word overlap found 2/5 with 6 false hits (meaning-level). Until a take-review step exists, read seams.md for "same idea twice" and cut from the first try to the redo |
| Doordash v2 1:35, 2:20, 8:29 | clipped "problem", stray "to", a retake spliced from two takes | user notes in extra_cuts.json, edges on measured audio quiet; whisper word times were off by up to 0.6 s at each one |
| Doordash v2 music | two beats overlapped at section changes; outro replayed a section song | each beat fades out over 1.6 s ENDING on the change, next fades in 0.5 s; outro = the intro's beat (bookend) |
| Doordash v2 2:15, 8:14 | a fading tail of a cut word / an untranscribed "wait, whoa, hold on" at the start of a piece | AUDIO rule in take_cuts: a piece opening on a burst < 0.9 s then >= 0.35 s quiet (<= 2 words / fillers) starts at the real speech (walks back to the soft onset); never start inside a fading tail. Whisper may drop such words entirely |
| Doordash v2 end | final "Bye" cut (never transcribed) | the last piece runs through the first sound burst after it (+0.35 s) |
| Doordash v2 1:04, end | (liked) cut to the PC screen; the end transition | keep: halves-based layout, current outro |
| Doordash, all | draft handed over without reading seams | `work\seams.md` every build: read every seam + SHORT PIECE before showing a draft |
| dhgate coupons 2:36 | 1.4 s of breath after "...buying in bulk." held a join open ("blank space") | join air: past a piece's last word only sound within 8 dB of that word counts as speech |
| dhgate coupons 3:38 | small.en heard "shipping shipping", the stutter cut garbled "because shipping is very expensive" | one-word stutters are confirmed by medium.en (+-0.6 s, cached in work\stutter_check.json) before cutting |

Seam check (take_cuts.py prints it): every kept edge is measured at +-10 ms; "CLIPPED?" = the edge sits on sound. Fix or listen to each one before rendering.

## What Gling does (studied 2026-10-20 on the alo clothing XML: {{KIT}}/tools\gling_study)
- Gling's site and reviews only claim it removes "bad takes, silences, filler words". There is no public method. Learned from its output instead:
  - FEW, LARGE cuts: 17 pieces from 17 min (about 22 s each). It removes whole failed takes and sections (88 s, 99 s, 171 s) and
    never micro-trims inside a good take (only 4 pauses > 0.6 s were left, all <= 0.8 s).
  - Edges: about 0.15 s of air before the first word of a piece, and about 0.1-0.2 s after the last word.
  - Retakes: it keeps the LAST take and cuts from the first attempt to the start of the final one (same rule as take_cuts).
  - It also drops an earlier attempt at a whole SECTION said in different words ("so in order to get aloe clothing, simply go
    over to solo.to" -> later "if you are wondering where to purchase aloe from... solo.to slash shift three").
    Word-overlap detection of this over-cut both test videos, so `find_resaid` is OFF (`--resaid`). It needs meaning-level
    matching (sentence embeddings) before it can be trusted.
- Benchmark: run take_cuts.py on the alo raw and compare with Gling's keep (script in the gling_study notes). Current result:
  we agree on 1143 words, Gling kept 85 that I cut, and I kept ~225 that Gling cut, mostly that re-said section.
- Scraps: a kept piece < 1.2 s with < 3 words is dropped (a lone "So" at v13 0:27 was heard as "okay").

## Full edit pipeline (first done: Uber Eats, 2026-10-20; project folder <project>\edit)
1. Full-res cut: `render_draft.py <src> work\cuts.json edit\cut-full-noblur.mp4 --width 3840 --fps 30 --cq 19`, then
   `privacy.py apply ... --scale 1.0` -> edit\cut-full.mp4 (the address is blurred BEFORE any layout work).
2. Layout map (edit\layout.json):
   - app mode = phone visible (black bars beside it) and the phone changes within -1.5/+2.5 s. Merge gaps < 4 s, drop runs < 3 s.
   - side camera = the right half is the 2nd camera (no black bars) and head yaw <= -18 deg or no face for >= 1.2 s
     (mediapipe face_landmarker from the product-review skill). On the Uber test: 0:19.6-0:27.2 and the outro.
3. Graphics = ONE HyperFrames template with variables (edit\graphics\index.html), rendered per event as transparent MOV
   (`--format mov --variables-file`, about 25 s each, run in the background). Kinds: wipe (section transition), method (title),
   app (real App Store icon via itunes.apple.com/search artworkUrl512), code (types out, with copy button + "link in
   description"), stat, subscribe, end. Events are timed from out_words.json (cut-timeline words).
   Codes come from the user's own video description (search "{{PHONE_CHANNEL}} <app> promo code"). Uber Eats = EXAMPLECODE (new account, 2026-10-20), Attapoll = EXAMPLECODE, Eureka = EXAMPLECODE.
4. `edit\build_main.py --draft`: talk = full webcam. app = blurred webcam background + rounded webcam card (80,110,1020x574) +
   phone (1373,40,467x1000) sliding in. side = right half. Graphics overlaid with -itsoffset.
   Audio: voice -16 LUFS (slow leveler + one measured gain, no compressor), one type beat per section (bed -31 LUFS, v6), quiet SFX per graphic kind. About 2x realtime on NVENC.
5. Intro (edit\intro, HyperFrames, built from the VO, one literal scene per line). Real phone clips come from the BLURRED cut.
   Videos must not sit inside timed wrappers (lint error), so drive scene visibility with tl.set.
   Music (v4+): ONE steady section of a clean beat the whole intro, no break->drop, no build, NO 808 (none anywhere since 2026-10-22).
   The intro beat fades out under the closing wipe, and the main video opens on the second half of the same wipe on a different beat.
6. `edit\join.py intro.mp4 main-draft.mp4 out.mp4`: intro ALWAYS first.
Transitions (current, 2026-10-22): bright brand-color slide wipe (never a dark panel) + ONE swoosh (whoosh-short.mp3) at each section
change (opening talk -> walkthrough, METHOD wipes, into the outro), each section with its own beat. Silent phone slide-ins; hard cut to the side camera.

## Drop-folder automation (added 2026-10-20)
- `{{PROJECTS_ROOT}}\Phone Videos`: drop `<name>.mp4` [+ `<name> intro.wav|mp3`]. The watcher's scan_phone lane makes `<inbox>\<name>\raw\source.mp4`
  (+ raw\intro.*) and runs `{{KIT}}/tools\phone_edit\pipeline.py <project>`. The draft lands in `<name>\output\<name> - DRAFT.mp4` + report.md.
- Shared code: `_tools\phone_edit\` (pipeline, layout, events, auto_intro, build_main, join, templates\, apps.json, codes.json).
  Keep codes.json current with the user's referral codes. Add new apps (aliases = Whisper spellings) to apps.json.
- User notes on a draft: edit work\extra_cuts.json (cuts) / edit\graphics\batch.json (graphics), then re-run pipeline.py, which resumes.

## v1 review notes (2026-10-20), now defaults
- SFX only on section wipes (soft) + one ping per code card + the subscribe click. No whooshes on stats/end card/phone slide-ins ("too many risers").
- (superseded: no 808 at all now) A cash register on money slams.
- Intro: designed UI (cart cards, receipt) instead of screen recordings with blurred addresses.
- The "all codes in the description" card only at the end.
- Voice: slow leveler (dynaudnorm ~15 s window) + a fixed measured gain to -16 LUFS, NO compressor (v5/v9; dynamic loudnorm pumped ~3 dB).
- Phone loading screens while talking: hold the last good phone frame (blank_phone.json -> build_main holds).
- (v2 5:54) Keep the phone on screen while they read/refer to it even when it barely changes: `phone_edit\bridge.py` bridges app gaps
  (phone visible the whole gap, <= 12 s or a screen cue like "as you can see/the following/select" and <= 25 s, never across a section wipe).
- No dates/years/months in ANY graphic (user rule, all videos, 2026-10-20). Evergreen wording: "100% FREE · PROMO CODES".
- (v3) NO risers in phone/app videos, and since 2026-10-22 none in gaming either. Section wipes = one swoosh (was click + soft ping).
- (v3) Beats: reject producer tags too ("BeatStars.com" every 30 s in the Ruiz beat, now recycled). Scan with medium.en, vad_filter=False,
  highpass 200 Hz. small.en+VAD missed it. Current clean rotation: KENDALL, Family Matters, DoTheMove, Close To Me (+ intro: Aggressive Fire Flow).
- (v4) Intro music: ONE steady beat section, no break->drop "half and half", no build, no 808 (not used in any video type now). Turn line = quarter-second blackout + music gap only.
- (v5) Music never pauses; the intro beat continues into the main video (edit\intro_music.json); clean beat (Family Matters). Voice = fixed gain only, NO compressor (it made the music sound boosted).
- (v6) Music: the intro beat FADES OUT under the closing wipe, and the main video starts a different beat. Bed -31 LUFS (~15 LU under the voice, "a tad louder"). One beat per section, crossfading at the wipes.
- Privacy sweep runs only when the picture inputs change (cut/privacy/layout/blank_phone/source). Audio-only and intro-only re-renders skip it (user 2026-10-20).
- (v7) Layout: ALWAYS the full webcam. App moments = phone picture-in-picture on the LEFT (40,60,448x960) over the full cam. No shrunk cam card or blurred background. Graphics right-anchored (ax=right).

## Reference edits (approved)
- **Dhgate coupon codes** (2026-10-24, test video, no Drive/TickTick). Folder {{PROJECTS_ROOT}}\Dhgate coupon codes; the approved file is output\Dhgate coupon codes - DRAFT.mp4 (3:51.7, 24.6 s P02 intro, 17 min raw -> 20% kept).
  Reference for website / coupon-sheet videos (sheet on the LEFT half, cam right) and for the P02 intro.
  One round of 3 notes taught:
  - Breath after a clip's last word is not talk: join air counts only sound within 8 dB of that word.
  - Whisper small.en invents doubles: confirm stutters with medium.en.
  - Intro needs varied pages + designed motion scenes (fee ticker, shock slam, kinetic type, swipe cuts, three clip layouts), skipping page-load black flashes.
  - Highlight only meaning words; a wrong app named in the VO is a slip and shows the video's app.
  - Year fragments ("202N") are never codes.
  Memory: dhgate-coupon-codes-reference-edit.

## Reference result
Uber Eats promo codes, FINAL v8 (2026-10-20, "this was a good test"): {{PROJECTS_ROOT}}\uber eats promo codes may 2025\Uber Eats Promo Codes - DRAFT v8.mp4.
Every default above was learned on it. Next videos are tests of the same rules and of the unattended drop lane.
Doordash Test video, v2 draft (2026-10-21, "very good job"): {{PROJECTS_ROOT}}\Doordash Test video\output\Doordash Test video - DRAFT.mp4.
Shein Promo Codes, FINAL (2026-10-21, "perfect, no more changes"): {{PROJECTS_ROOT}}\Shein Promo Codes\output\Shein Promo Codes - FINAL.mp4.
The reference for website-heavy code videos (see "Shein revision rules"). Final render = `edit\build_main.py` (no --draft, cq 19)
then `join.py edit\intro\renders\intro.mp4 edit\main.mp4 "output\<name> - FINAL.mp4" --cq 17` (without --cq the join re-encodes
at the draft's cq 21 and the final comes out at draft bitrate). Time every render. Shein (8:36): main 3 min 20 s (2.6x realtime) + join 37 s + QC 37 s.
- (v8) Voice: dynaudnorm f=500 g=31 m=2.5 (slow ~15 s leveling) -> measured gain to -16 LUFS. A fixed gain alone kept natural 2.5 dB louder stretches. Wipes never use a dark panel (it read as a black screen).

## Shein revision rules (user, 2026-10-21) - now defaults
- CODES come from THIS video's screen (`phone_edit\screen_codes.py`, Windows OCR 1 fps on both halves, a code counts only
  when it is spelled/said within 25 s; I/L/1 confusions repaired from the speech). One code card per code
  (events.py `scode-N`), never an old list: codes change. Tiny text OCR misses -> `edit\screen_codes.manual.json`
  [{"code","after": words said just before}]. Shein: 13 codes, EXAMPLECODE added by hand (search-bar text).
  A year with one OCR'd letter ("202N", "202B" from "2024-10-01" on a code sheet) is never a code (dhgate coupons 2026-10-24).
- No METHOD wipe/title inside a run of codes ("next code" is not a new section); "secret method" is a section cue.
- Website half: shown the WHOLE time it is on screen (not only while it changes), face cam card TOP-LEFT (40,40,512x288),
  code cards bottom-right; each code gets a 1.7x push-in onto its own box (screen_codes box) ~0.4 s after it is announced.
- Phone: on for the whole phone section, off at the outro ("anyways guys"). Website also leaves at the outro.
- Side camera: layout.py face detection ran on a squashed 640x180 frame and missed most faces -> 640x360 now; the
  talking opening where they face the 2nd camera (yaw -25..-35) uses that camera.
- Every video ends on a 1.2 s fade to black (picture + sound).
- Intro needs VARIATION per video (the Shein one looked like the DoorDash one). Variation B "screens" = the user's own
  pages in 3D browser windows + search typing -> gatekept/redacted codes + padlock -> research on the real checkout,
  price struck down -> the video's real codes stacking + savings count -> "<APP> / PROMO CODES" title
  ({{PROJECTS_ROOT}}\Shein Promo Codes\edit\intro2). The end title says what the video is ("SHEIN PROMO CODES"), not "FREE <APP>".
- Intro MOTION (dhgate coupons 2026-10-24: "not a big fan of this style ... more motion, different things going on"; the P02
  intro showed one DHgate listing page 5 times and black words on a plain grey background): intro_footage.py picks DIFFERENT
  pages first (homepage, product grid, listing), P02 cuts with an accent swipe and drifts its background, page clips rotate
  three layouts (window left / full-bleed push-in + lower third / window right in 3D), fee/shipping/tax lines get the fee
  ticker (S.fees), surprise lines the shock slam (S.shock), lines with nothing to show their own words as kinetic type.
- Intro HIGHLIGHTS = what the line is about: money, the app, then shopping concepts (fees, shipping, codes, save, free,
  check out); never narration words (guys, starting, looked). A weak longest-word key is never shown. A different app said
  before "promo codes" is a VO slip and shows the video's app (build_intro.app_slip).
- Cut edges: the cutter's seam check flags "CLIPPED?" edges; check every one (Shein 549.82 was the user's "1:29 start of
  my sentence cut off": a take-review cut ended inside "it's").
- Studio app: notes are "revisions" read by Claude (Opus via the Claude Code CLI) on "Apply revisions + rebuild"; exact
  cuts live as cut notes with raw times (extra_cuts.json is rewritten from the notes, applied ones included).
## Draft checks (2026-10-25)
- Phone drafts end with draft_audit.py (work/cuts.json + edit/main-draft.mp4 + work/mic.wav): a dangling or doubled word at a cut is a problem and goes to the revision AI; a loud mic alone is "listen" (he talks with no pause between sentences). Repeat/stranded checks are "listen" on phone videos.
- pipeline.py stops (exit 3) when check_video finds a BROKEN render (picture/sound length mismatch, 30 s+ freeze): never let the AI QC excuse it (Uber october draft 1).

- 2026-10-25: phone drafts also get bookend_checks (greeting/sign-off twice, > 2 s after 'bye') and the stub rule; phone intros get the intro_check subject rule (Uber: Notion dashboard / survey page = wrong subject).

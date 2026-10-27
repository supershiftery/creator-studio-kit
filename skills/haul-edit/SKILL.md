---
name: haul-edit
description: Edits {{REVIEW_CHANNEL}}'s HAUL videos (one long iPhone/phone recording showing many products back to back, no intro VO, no OBS side-by-side) through {{STUDIO_NAME}}'s "haul" type. Covers detection, the 1080p60 SDR normalise of mixed 4K/1080, 30/60 fps, HDR, VFR phone clips, the trim, intro/outro detection, type-beat music (intro / body play-through / outro), Gling "Doug" captions on the intro + outro, and checking the draft. Use when asked to edit, build, fix or revise a haul (e.g. "30kg haul", "mulebuy haul" filmed on the phone). Older side-by-side OBS hauls use product-review-edit instead.
---

> **Before showing ANY draft and on every note: run the `editor-gate` skill** (one-take mode, per-type pre-show checks, note -> check, laptop sync).

**EDIT RULES FIRST (2026-10-25):** before building or showing ANY draft, read `{{KIT}}/tools\EDIT_RULES.md` (every past revision note turned into rules) and run its section I, the editor's pass. A note that says "again" / "never" means a rule exists but nothing checks it: build the check and update that file.


# Haul edit ({{STUDIO_NAME}} type `haul`, built 2026-10-23)

A haul = he films ONE long phone recording (often split into a few iPhone clips, IMG_6814.MOV, IMG_6815.MOV ...) showing a
pile of products one after another. No separate intro VO, no OBS side-by-side, few mess-ups. Different format from the
product reviews, so it has its own pipeline. First one: "30KG haul DHgate" ({{REVIEW_CHANNEL}}), raw on Drive at
`{{DRIVE_RAW}}\{{REVIEW_CHANNEL}}\30kg haul Dhgate\`.

Older hauls (#8-#21, the mulebuy / 15kg / 12kg ones) were OBS side-by-side recordings (3840x1080 / 5120x1440). Those are
NOT this type; detect.py scores side-by-side "hauls" -8 so they stay review-pipeline videos.

## Files
- `{{KIT}}/Studio\app\recipes\haul.py`: steps, paths, notes mapping, outputs.
- `{{KIT}}/Studio\app\tools\haul_normalise.py`: clips -> raw\source.mp4.
- `{{KIT}}/Studio\app\tools\haul_render.py`: the edit render (draft `--draft`).
- `{{KIT}}/Studio\app\tools\captions.py`: preset `doug`.
- `{{KIT}}/Studio\app\detect.py`: the haul signals.
- Reused: gaming `prep.py` / `transcribe.py` / `cuts.py` (haul = take review kind "haul", no game-panel scan),
  `{{KIT}}/tools\take_cuts.py`, `phone_edit\take_review.py` KINDS["haul"], review `edit_review.midstart_guard`.
- Project layout: `raw\clips\NN <name>` (copies) -> `raw\clips\norm\` (normalised clips, clips.json) -> `raw\source.mp4`;
  `Edit\studio\` (source.json, words.json, cuts\, haul_structure.json, timeline-haul.json, haul_intro.ass);
  `<title> - DRAFT.mp4` / `<title> - FINAL.mp4` in the project root.

## Format rules (user 2026-10-23)
- **Always 1920x1080 at 60 fps**, even when the phone recorded 4K ("they need to be downscaled to 1080p (60fps)").
  30 fps clips get each frame twice. Portrait clips sit on a blurred fill of themselves.
- **HDR -> SDR**: iPhone 17 Pro Max records HEVC 10-bit HLG + Dolby Vision 8.4. Tone-map with libplacebo on the GPU
  (`-init_hw_device vulkan`, `libplacebo=...:colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv:format=yuv420p:tonemapping=bt.2390`,
  ~3.4x real time); zscale + hable is the CPU fallback (looks duller). Never deliver HEVC: H.264 High yuv420p + AAC 48 kHz.
- **Audio**: the first AAC track (iPhones add an `apple_apac` spatial track: skip it), resampled with async, padded/cut to
  the picture length.
- **Spatial Audio clips** (30kg haul 2026-10-23, clip 1 "sounds like it's going around me"): an iPhone clip filmed with
  Spatial Audio on carries an `apple_apac` track and its AAC track is a WIDE stereo render (L/R phase correlation 0.43, side
  only 6 dB under mid, voice +5 dB at 2.5-6 kHz) while normal clips are dual-mono (L = R). haul_normalise measures every
  clip (mid/side + 3 voice bands, 60 s mid-clip) and folds Spatial / wide (side > -15 dB of mid) clips to mono + a match EQ
  towards the plain clips (+-6 dB), logged as `-> mono + match EQ (...)`. `settings.haul_keep_stereo` turns it off.
  NOTE: Studio's step freshness is mtime-only, so a normalise CODE change on an old project needs `raw\source.mp4` moved
  aside (cached clips re-use by key; only changed clips re-encode).
- **Stream durations, never the format duration** (VFR phone/OBS files). A source clip with picture vs sound > 0.5 s apart
  is REFUSED; every normalised clip must come out picture = sound (+-1 frame), the join and the render are re-checked too.
- **Clip order** = camera creation_time, then the IMG_#### number (iPhone numbers count up; 30kg: 6814 18:12 -> 6815 18:31
  -> 6816 18:34). `settings.haul_keep_order` keeps the added order.
- Clips are joined only AFTER normalising (New Project never stream-copy joins a haul).

## Edit rules
- Trim: the shared take_cuts rules + take review (kind "haul": never cut the greeting, the haul total, a product's first
  mention, the outro/sign-off), then midstart_guard. User notes = cut/protect notes as usual.
- Start = the greeting ("hey guys ... Agent {{REVIEW_CHANNEL}} here"), regex in haul_render.py; anything kept before it is dropped.
- End = the sign-off: the outro starts at "anyways guys / that's pretty much it / that's gonna be it / hope you enjoyed"
  (last 30% of the video), ends at the line with "peace / see you / next one / bye / later" + 0.6 s. A user protect wins.
- Intro end + product list: Claude reads the kept transcript (claude_brain task `haul_structure`, cached in
  haul_structure.json). Fallback: first product start, else 30 s. Sane range 4-120 s.
- **Music (user 2026-10-23)**: "the intro gets its own music. Throughout the whole video you're going to change the track;
  once one ends, the next one's going to go, and then the outro is going to get its own music." So: intro beat ->
  body beats played through to their end (never looped; switch on a pause, 1.5 s crossfade) -> its own outro beat.
  Type beats from `{{MUSIC_ROOT}}\Type Beats` (no Lo-Fi), shuffled per project, beats from the last 5 videos in
  `~\.claude\skills\product-review-edit\work\music_history.json` go last (variety rule), a re-render keeps its beats.
  Every beat is vocal/producer-tag scanned (medium.en, no VAD, highpass 200, cache `{{MUSIC_ROOT}}\_vocal_scan.json`).
  A beat with more than 8 confident words is rejected (30kg: "Drake - Feds Emotional Piano" scanned 19 words, too close
  to the old 20-word vocal line; "Lil Uzi Vert - Blindsided" 10).
  Each beat sits 15 LU under the voice of ITS stretch (volume follows voice). Mix -> -16 LUFS, then alimiter 0.75
  (loudnorm alone came out at -0.8 dBTP after the AAC encode; target <= -1).
- **Captions over the intro AND the outro** (user 2026-10-23, 30kg haul at 14:02: "it didn't even go to the outro captions"),
  Gling "Doug" style; NONE in the body. The outro stretch starts at the detected outro, or at
  `settings.haul_outro_captions_from` (RAW time; 30kg = 1088.4, the wrap-up "As you can see over here..." before "anyways guys").
  Written to Edit\studio\haul_captions.ass. `settings.haul_captions = false` turns them off, or a preset name swaps the style.

## Gling "Doug" (copied from Gling's source, `C:\Program Files\Gling\resources\app.asar`)
`fontSize: 110 * 1.5` (165 px on a 1080p canvas), `fontFamily: Anton`, white `#ffffff`, `fontWeight: bold`,
`mainColor #FF0000, secondaryColor #FFFF00, tertiaryColor #00FF00`, `fontOutlineStrokeWidth: 32` black (canvas stroke:
16 px shows outside the glyph -> ASS Outline 16), shadow black offset 2/2, no caps, no word-by-word reveal: the whole group
shows, the spoken word coloured. Colour index = `currGroupIndex % 3`, so the highlight colour changes per caption GROUP
(red, then yellow, then green ...), not per word. Our chunks: max 3 words / 20 chars, break after a sentence end or a
0.6 s pause, bottom-centre 10% up; a lone sentence-ending word ("it.") joins the group before it (`no_orphan`).

## Studio UI
A new type needs its entry in `ui/app.js` SLOT_DEFS (and app3.js side0), or the project page throws and the draft
"doesn't load inside the studio" (user, 30kg haul 2026-10-23). UI edits need a reload (Ctrl+R), backend edits a restart. Fonts in `{{KIT}}/Studio\app\fonts` (Anton-Regular.ttf is there).

## Detection (detect.py, VERSION 4)
Signals: phone camera metadata (QuickTime/Android make+model, or a .MOV in HLG / rotated) on a non-side-by-side file +4;
"haul" in the file or folder name +4; speech: "haul" +4, "<n> kg" +2, agent/shipping +1, "next item / moving on" +1;
side-by-side -8. On a close haul-vs-review call on a phone file the director (claude_brain `detect_haul`, Claude eyes +
Claude) looks at a 6-frame sheet + the transcript sample (+3 to its answer). Phone hauls are never flagged "screen".

## Build + check
- Studio: `POST http://127.0.0.1:8765/api/project/run?id=<pid>` `{"action": "draft"}` (one GPU build at a time; the
  queue handles it). Steps: normalise -> prep -> transcribe -> cuts -> render (half-size 960x540 30 fps cq 23) -> QC
  (check_video.py 10 fps) -> AI QC -> targets (targets.json "haul", no approved haul final yet).
- Before showing: read the render log (greeting / outro / intro end / products / music lines), `<video> targets.md`,
  the QC flags, a frame sheet of the intro + outro captions (colours cycle, nothing in the body) and the music switch points,
  and listen to the seams (Whisper the draft at joins). Log findings as Studio revision notes ([[studio-status-always]]).
- Final: `{"action": "final"}` -> `<title> - FINAL.mp4` 1080p60 cq 17. Test videos: no Drive / TickTick.

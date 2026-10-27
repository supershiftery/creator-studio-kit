---
name: product-review-edit
description: Edits the reviewer's product review videos (any product, often from DHgate) fully unattended. Use when asked to edit, cut, assemble or render a product review from a project folder of raw dual-camera footage and screen recordings. Tightens pacing, switches camera angles on head turns, adds a circular face cam, centred and cursor zooms, B-roll, a green price callout with a payment chime, subscribe animations and per-section type beat music, then renders. No captions. Asks one question only: which B-roll clips to add.
---

# Product Review Edit

Run start to finish without asking me anything, except the B-roll question (Step 0). Where something is unclear, make the safest choice, keep going, and write it in the report at the end.

## Fast path

- If `scripts/edit_review.py` exists in this skill folder, just run it: `python scripts/edit_review.py <project folder>`. Do not re-plan or re-read the footage yourself.
- If it doesn't exist yet (first run only), build it from the steps below, test it on the project, and save it there so later runs are cheap.
- All numbers live in `scripts/config.json` (pause length, circle size, border, music levels). Change settings there, never in the code.
- A project can override any setting in `raw/config.json` (e.g. `{ "pacing": { "enabled": false } }` when the footage is already trimmed).
- Python on this PC: `%LOCALAPPDATA%\Programs\Python\Python312\python.exe` (not on PATH). Face model: `models/face_landmarker.task`.
- Add `--fresh` to the command when I say "fresh run".

## Step 0: Ask me for B-roll (the one question)

This is important. Before the final render, always do this:

1. Run `python scripts/edit_review.py <project folder> --broll-plan`. It splits the product review into the pairs/products I talk about and finds, for each pair, the moments that call for B-roll, then writes `output/broll_requests.md` (see "How B-roll moments are picked" below).
2. Show me that shot list in chat (slot, time, which pair, kind of shot, what I'm saying, length) and ask what B-roll I want to add. Tell me to drop clips in `raw/broll/` named by slot number (`2.mov`) or described (`red feet.mov`, `white spin.mov`, `black sole.mov`, `box.mov`), or to just send them. Then wait for my answer.
3. If I send clips with camera names (`IMG_5908.mov`), **look at each clip** (a strip of 6 frames per clip) and match it to the right moment yourself: same pair/colour as what I'm talking about, and the right kind of shot (on-feet clips on on-feet moments, turntable spins on "look at this" moments, sole shots on "the bottom", box shots on box talk). You can't tell colours from pixel values under my purple lighting, so judge by eye. If the best moments aren't in the plan, rewrite `work/broll_plan.json` with them (5-10 s each, inside that pair's part of the review). Then write `raw/broll.json` (`[{"slot": 1, "file": "IMG_5908.mov", "start": 0}]`, `start` = seconds into the clip to begin, e.g. to land on the soles) instead of renaming my files.
4. If I say no B-roll / skip, render without it.
5. Then run the normal command.

B-roll rules (the script does all of this):
- Clips are always silent. Their audio is never used. My voice keeps playing underneath.
- B-roll only goes over the product review, while I'm talking about the product.
- Each clip is on screen 5-10 seconds, long enough to drive the point home. It is fitted to its moment: sped up (up to 2x, using the middle of a long clip) or slowed (down to 0.5x for very short clips).

How B-roll moments are picked (`broll` in config):
- I often review several pairs (different colours) in one video, in any order. The review is split into pairs where I say things like "first shoe", "next up", "the last one". Each pair is labelled with the first colour I say for it ("Pair 1 (red)"); colour words that describe a part ("black backing", "red bottom") don't count.
- For each pair, one moment per kind, in this order: **on feet** ("here's what it looks like on feet", "showing them off", "wearing them", "such a comfortable shoe"...), **close-up / turntable** ("so shiny", "here's the shoe", "reminds you of", "the spikes"...), **the sole** ("look at the bottom"), **the box** ("double box", "packaging"). At most 3 per pair.
- Each moment starts on the phrase and runs to the end of the sentence(s), 5-10 seconds, never into the next pair.
- Clips match a moment by slot number in the file name, then by kind and colour words in the file name, then in order (flagged in the report).
- To look better: light grade (contrast and saturation), slight sharpening, slow 1.06x push-in, 0.3 s fade in and out. Vertical phone clips sit on a blurred copy of themselves instead of black bars.
- B-roll is full screen with no face cam: the face circle is hidden while a clip is on screen.
- Settings live in `broll` in `scripts/config.json` (pair transitions, colours, kinds with their trigger phrases and file-name words, slot length, speed limits, grade).

## Drop-folder automation (`{{PROJECTS_ROOT}}`)

My normal process: I cut the video in Gling.ai and drop the export into `{{PROJECTS_ROOT}}`. A watcher does the rest without Claude:

- `scripts/watcher.py` runs in the background (pythonw, started at sign-in by the Startup shortcut `AI Editing Watcher.lnk`; install/remove with `scripts/install_watcher.ps1` / `-Uninstall`).
- New video in the top of the folder: waits until it stops growing, makes `{{PROJECTS_ROOT}}\<video name>\` (raw/camera.mp4 moved in, `raw/config.json` with pacing cuts off because Gling already cut it), runs `--broll-plan` and the full edit, then shows a Windows notification. Clicking it opens the B-roll shot list.
- B-roll: I drop clips into that project's `raw\broll` named by slot number (`3.mov`, `5 - Copy.mov` works too) or described (`red feet.mov`). Camera-named clips (`IMG_...`) are placed in order; for the best match ask Claude to look at them. When they finish copying, the watcher re-renders and notifies me. The notification replaces the Step 0 chat question for automatic runs.
- Videos that aren't the side-by-side two-camera layout (width/height under 3) get a project folder and a report but are not edited.
- Log and state: `{{KIT}}/watcher\watcher.log`, `state.json`. One render at a time. If I ask why something didn't edit, read the log first.

## Notes from real footage

- Camera halves can be 1920x1080 (camera.mp4 = 3840x1080, 60 fps). The script detects the half size and only crops when a half is taller than 16:9.
- The right half is not always the side angle. It switches between side camera (intro/outro), product camera (review) and the screen recording (showcase). The script classifies it per frame, uses it for the full-frame/circle layout, and uses it as the section fallback when the markers are missing.
- Camera B (side angle) is only used when the right half actually shows the side camera; in review/showcase the circle is always Camera A.
- Voice and beats are loudness-matched before mixing, so the music dB values are relative to the voice.

## Project folder (always the same names)

- `raw/camera.mp4`: 3840x1920, two 1920x1920 angles side by side.
  - Camera A (main, front) = left half: `crop=1920:1920:0:0`
  - Camera B (side angle) = right half: `crop=1920:1920:1920:0`
- `raw/screen.mp4`: the spreadsheet and DHgate listing screen recording, if there is one.
- Optional `raw/music.txt`: four beat file names (intro, review, showcase, outro) to override the automatic pick.
- Subscribe animation: `assets/subscribe.mov` in this skill folder (has transparency).
- Music: type beats in `~/Downloads` (mp3, wav or m4a with "type beat" in the name).

If `raw/camera.mp4` is missing, stop and write that in the report. Anything else missing: skip that feature and note it.

## Output

- `output/final.mp4`: 1920x1080, 30 fps, H.264, AAC 192k. No captions or subtitles ever.
- Volume: my mic is never raised more than 4 dB. The mix aims for -14 LUFS but the gain is capped at +4 dB and never turned down (`output.max_boost_db`). The music is turned down to sit under the voice instead of the voice being boosted.
- Fades: 0.5 second fade in from black and fade out to black (picture and sound) at the very start and end of the video (`output.fade_seconds`).
- `output/preview_540p.mp4`: quick low-res copy for checking.
- `output/report.md`: what was done (see Report).

## Step 1: Transcribe once and cache

- Whisper with word-level timestamps on the camera audio, saved to `work/transcript.json`. Reuse it if it exists. It is only for finding cuts, markers and "subscribe". Nothing from it goes on screen.

## Step 2: Find the sections from my spoken markers

- While recording I say "next section" at each change. There are three markers, which give four sections in order:
  1. Intro
  2. Product review
  3. Showcase (spreadsheet and DHgate listing)
  4. Outro
- Cut the marker phrase itself out of the video, along with 0.5 seconds either side.
- If the transcript doesn't have exactly 3 markers, fall back to the transcript topic and the screen recording timing. Then flag it in the report.
- Save to `work/sections.json`.

## Step 3: Tighten the pacing (general cuts)

- Cut silences longer than 0.6 seconds down to 0.2 seconds.
- Cut retakes: when I repeat a sentence, keep the last take.
- Trim setup and fumbling at the very start and end.
- Save the kept ranges to `work/cuts.json`.

## Step 4: Camera switching on head turns

- MediaPipe face mesh on Camera A at 5 fps.
- Head turned left more than about 25 degrees = Camera B. Facing forward = Camera A.
- Ignore turns under 1.5 seconds. Hold every shot at least 2 seconds.
- Save to `work/angles.json`.

## Step 5: Layout per section

- Intro and outro: the active camera fills the frame (1920x1920 scaled and cropped to 1920x1080, face centred).
- Product review and showcase: the product shot, spreadsheet or DHgate listing fills the frame. My face cam is a 360 px circle in the top-left, 40 px from the edges, with an 8 px white border and a soft drop shadow. The circle follows the Step 4 angle switching.

## Step 5b: Strategic zooms (on by default, `zooms.enabled` in config)

- Intro and outro: smooth punch-ins (1.18x) straight into the centre of the frame (not toward the face, which sits off-centre on the side angle), when the whole face is on screen, on emphasis words ("honestly", "definitely", "highly recommend", "10 out of 10"...) and at sentence starts so the shot never sits still more than about 9 seconds. Works on both camera angles.
- Showcase (spreadsheet / DHgate listing): 1.6x zoom to where the mouse settles when I say "right here", "over here", "click on", "on the side", "looking like this"... Only when the mouse actually moved there (pointing at something), and at most one every 14 seconds. The mouse is tracked from small frame-to-frame changes in the screen recording; the taskbar, browser tab/address bar and scrollbar are ignored.
- No zooms in the product review section. The face circle is never zoomed.
- Saved to `work/zooms.json` (cursor track in `work/cursor.json`). Set `"zooms": {"enabled": false}` to take them out.

## Step 6: Subscribe animation

- Every time I say "subscribe": overlay `assets/subscribe.mov` 0.2 seconds before the word, lower third, plays once.
- Skip any within 10 seconds of the previous one.

## Step 6b: Price callout (`price` in config)

- The first time I say a dollar amount ("$140", "140 dollars", "140 is a reasonable price", or "it's going to cost 55": a bare number with price words just before or after it), the price pops up on screen: bold green text (Segoe UI Black, `#3DFF7A`) with a dark green outline and soft shadow, lower middle of the frame.
- Animation: quick pop with a small overshoot, held about 2.6 seconds, 0.3 second fade out.
- Plays a soft payment chime with it (Apple Pay style, two quick rising notes; synthesised, not Apple's sound), kept quiet under the voice at -14 dB (`price.cash_db`). `price.sound` can be `"chime"` (default) or `"register"` (cha-ching). Dropping my own `assets/cash.wav` overrides both.
- **Only one per video.** If I say the price again later, it is not shown again (`price.max_per_video: 1`).
- Sizes, sizing words ("size 44", "US 12") and ratings ("10 out of 10") are never treated as prices.

## Step 7: Music

- Use `raw/music.txt` if it exists. Otherwise pick four different type beats from `~/Downloads`, newest first, and never use the same beat as the last video (keep a log in `work/music_history.json` in this skill folder).
- Copy the chosen beats into the project's `work/music` folder.
- Fade in 1 second and fade out 3 seconds at every section change, so each beat ends cleanly before the next one starts (`music.fade_out_seconds`).
- Duck to about -20 dB under my voice with sidechain compression. Intro and outro can be -12 dB when I'm not talking.

## Step 8: Render

- One FFmpeg filter graph pass for the final. No intermediate full-quality files.
- Hardware encoder if available: `h264_videotoolbox` on a Mac, `h264_nvenc` on NVIDIA, otherwise `libx264 -preset fast -crf 20`.
- Then make `preview_540p.mp4` from the final.

## Report (output/report.md)

- Section timestamps, minutes cut, number of camera switches, zooms, B-roll placed, subscribe moments, price callout, beats used, volume change.
- A "Check these" list of anything flagged: wrong marker count, missing files, fallbacks used.

## Rules

- Never ask questions mid-run, except the Step 0 B-roll question before rendering. Never add captions.
- Never redo steps whose work files exist unless I say "fresh run".
- Keep chat output to one line when done: where the video is and how many items are in "Check these".

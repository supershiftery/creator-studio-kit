# {{STUDIO_NAME}}

> **Kit edition: editing software only.** The menu is just **Projects**, **Queue** and **Settings**. The parts of this README about the
> Dashboard, Tracker, To-do, Thumbnails board, Deliverables (Drive / description / website), TickTick, Telegram and the
> overnight lab describe the original creator's studio: they are switched off or removed here. Everything about projects,
> building drafts/finals, the editor, review notes, revisions, Shorts, the targets check and speed applies.
>
> - **AI director** (project setting, on by default): at a few judgment points the pipelines ask Claude through the same sign-in
>   (`tools/claude_brain.py`, lean one-turn calls of ~1-5k tokens, cached): what each intro line should show, whether a downloaded
>   picture is really the thing, what each B-roll clip shows, and whether each QC flag is a real mistake (suggestions only).
>   Teach it with `tools/teach.py` + `tools/teach/playbook.md`. Off, or Claude not signed in = the rule-based result is used.
>   `tools/brain.json` picks the model per role (swap `opus` for `sonnet` on a small plan).

One desktop app for the three kinds of videos you make, built on the tools that already work (the cutter, the phone
pipeline, the product-review pipeline, the Realms edit), plus a tracker and a hub for everything around them.

## Start it
Double-click **`{{STUDIO_NAME}}.cmd`** (desktop window), or **`{{STUDIO_NAME}} (browser).cmd`** (opens in your browser).
There is also a shortcut on the Desktop. The window runs on `http://127.0.0.1:8765`. Closing it while a build runs asks first: **Yes** hides the window and keeps
building (you still get the toast + Telegram; Studio quits itself ~30 s after the last build ends), **No** stops the builds
and quits, **Cancel** stays. Opening Studio again (shortcut or `.cmd`) brings the hidden window back instead of a second one.

## What is where
| | |
|---|---|
| **Dashboard** | To-do (TickTick two-way), weekly targets per channel, overdue / due soon / drafts to review / finals not on Drive / needs thumbnail, recent projects, and the hub: recordings not yet in a project, competitor outliers, Minecraft library, live realms, watchers, Drive, intro templates, VO takes, music. |
| **Projects** | Every video as a card with its thumbnail, stage and checklist progress. Click to pick it back up. |
| **Tracker** | Kanban by stage + a three-week calendar driven by due dates. TickTick boards read-only. |
| **To-do** | The TickTick list: overdue / today / next 7 days / no date. Add → created in TickTick (Apple widget + Telegram bot see it). Tick → completed in TickTick. "→ tmrw" pushes a task. If TickTick is offline, adds are queued in `data\todo-queue.json`. |
| **Settings** | Folder roots, Drive root, channels and weekly targets (import from TickTick). |

## A project page
- **Header**: thumbnail (click = grab a frame), title, channel, due date, stage (auto from the checklist, or override), the 11-point checklist.
- **Slots** (drop zones): recording, intro (MP4 or VO), B-roll, cards (gaming), thumbnail, description, articles. Drop a file anywhere on the page and pick where it goes.
- **Build**: the pipeline steps with their status, **Build DRAFT** / **Render FINAL** / QC check, live log. Steps whose outputs are newer than their inputs are skipped.
- **Review + notes**: watch the draft in-app, "note at this time", then notes like `cut 1:22-1:30`, `protect 2:03-2:10`, `broll 3:20 6s castle`, `section #5 Dragonforge 11:09-15:30`. Times come from the draft you watched and are mapped back to the recording; the cutter applies them on the next build.
- **Sections + music** (gaming): the section table (auto-detected from "coming in at number N", "honorable mention", the opener and the sign-off), transcript to set times from, music per section, matched cards.
- **Deliverables**: YouTube description with chapters filled in, Google Drive hand-off (finals only), TickTick card, articles/listings and website drafts (gaming), renders.
- **Brief for Claude**: copies a ready-to-paste brief (paths, slots, open notes) for hand-made intros, articles or fixes.

## More
- **Revisions** tab: chat with Claude (Opus 5.5 through the Claude Code sign-in) about this project; it can edit, add notes and rebuild.
- **Editor**: Gling-style. Space play/pause, ←/→ 5 s, J/L 10 s, C cut selection, P protect, S skip cuts, F full screen, Esc leaves it. "Make Short" renders the selection as a 9:16 Short into `<project>\Shorts`.
- **Review + notes**: the QC report (10 fps checker) with every flag; click a time to jump the player there, "sheet" shows the contact sheet.
- **Sections + music** (gaming): Code column + "Render code cards" builds the typed-code lower thirds for the next build. Music picker: "scan" runs the Whisper vocal check (🚫 vocal, ⚠ producer tag, ★ clean).
- **Search transcripts** (sidebar, Ctrl+K): finds what you said across every project and opens the editor at that spot.
- Progress bar + build history on every project; builds start on their own when footage is added; toast + Telegram when a draft or final is ready.

## Feature batch 3 (2026-10-21)
- **Shorts tab (Shorts Factory)**: "Find moments" transcribes the best render once (final before draft) and ranks 18-58 s windows by voice energy, hype words, a strong opener and a finished last sentence. "Title + score with Opus" names and scores each one. Tick, pick the crop, "Render selected Shorts" (1080x1920, -14 LUFS, a .txt with title + upload notes beside each). Gaming projects also get "Gaming package": one polished Short per ranked section (app\gaming\shorts.py).
- **Editor**: fillers (um, uh…) underlined, pauses over 1.2 s marked, "Cut N fillers" adds cut notes for the safe ones.
- **Deliverables**: "Write with Opus" drafts the YouTube description from the transcript, chapters and codes; "Title ideas" gives 10 titles (click one to set the YouTube title); "Copy for VA" copies title, description, files, Drive folder and Shorts.
- **Thumbnail frames**: the frame picker suggests the most expressive face frames (MediaPipe: mouth open, brows up, eyes wide, smile) and the sharpest screen frames.
- **New recording alert**: a toast + Telegram when a new MP4 finishes writing in {{RECORDINGS}}, and a "Create project" banner on the dashboard.
- **Build tab**: edit stats (raw vs kept, % cut, pieces, words per minute, why things were cut) and Disk space (regenerable intermediates to the Recycle Bin).
- **Music picker**: ▶ preview.
- **Dashboard**: output over the last 6 weeks (shipped per week, streak, build speed).
- **Phone projects, Revisions tab**: "Revise draft" (notes with draft times → revise.py turns them into exact cuts with Opus → resumed rebuild), draft history, revision history, seams.md.

## Video types
| type | pipeline | project home | output |
|---|---|---|---|
| Gaming / Minecraft | `app\gaming\*.py` (prep → transcript → sections → cutter + UI panels → body → assemble → chapters → QC). A generalized port of the Top 5 Realms edit: corner cam top-left with reactions, B-roll reel under the talking intro, inventory zooms, pixel wipes, auto-matched code/IP cards, soft game-OST bed per section, Pokémon music on Pokémon sections, chapters into the description. | `{{GAMING_ROOT}}\<title>\` (work in `Edit\studio\`) | `Edit\<title> draft.mp4` (960x540) / `final.mp4` (1080p60) |
| Phone / app tutorial | `{{KIT}}/tools\phone_edit\pipeline.py` (unchanged) + full-quality build_main + join for the final | `{{PROJECTS_ROOT}}\<name>\` | `output\<name> - DRAFT.mp4` / `- FINAL.mp4` |
| Product review | `review_pipeline\scripts\edit_review.py` (unchanged) | `{{PROJECTS_ROOT}}\<name>\` | `output\final.mp4`, `preview_540p.mp4` |

Gaming projects reference the OBS recording in place (60+ minute files). Phone/review projects copy it into `raw\` because those pipelines expect it there.

## Files
- `app\` Python backend (`main.py` window/launcher, `server.py` API, `store.py` projects, `jobs.py` runner, `recipes\` per type, `gaming\` the new pipeline, `tracker.py`, `hub.py`, `todo.py`).
- `ui\` the page (vanilla HTML/JS/CSS).
- `data\` settings, project index, thumbnails cache, to-do queue. Each project keeps its own `studio.json` in its folder.
- `DESIGN.md` design notes.

## Rules baked in
H.264 High yuv420p + AAC for every deliverable. Instrumental music only (gaming pool is the vetted list in `app\gaming\music_pool.json`). No dates in graphics. Finals only to Drive. Drafts at half size; QC check (10 fps) after every build.

## Batch 4 (2026-10-22): Director B-roll + edit options
- **Pink B-roll (gaming)**: the B-roll step uses `{{KIT}}/tools/minecraft/modpipe\brollmap.py`. It finds each Director reel between its pink flashes, splits it at the fades to black, and trims every shot at full frame rate, so no black or pink frame is left in. Each shot is saved as its own clip in `<project>\B-roll\`, named after what it shows when the reel is known (`… - Pokemon (CobbleDrock) 01 Charizard (attack).mp4`), with `B-roll map.csv` beside it. The clips go into the project's B-roll slot by themselves. A dropped raw Director recording is replaced in the pool by its clean shots.
- **Reel codes**: after the pink, the Director flashes 3 colour digits that say which reel it is (`reels.js` "code", kept permanent in `modpipe\reel_codes.json`). A white flash marks a skipped shot. Recordings made before this have no code and only map by shot count (CobbleDrock = 20 shots).
- **Where the clips go**: the reels inside the main recording are cut out of the gameplay (`cuts.py`; `settings.broll_keep_reels` keeps them in). `body.py` then places the clips full-frame under the corner cam, 4 s each:
  1. where you name the subject ("Charizard");
  2. otherwise spread through the section they were filmed in, starting at least 6 s in.

  Never in the intro or outro, never over inventory zooms or your manual `broll` notes, at least 20 s apart, each clip used once. The intro reel cycles subjects. Settings: `broll_auto`, `broll_auto_len`, `broll_auto_gap`, `broll_per_section`. Placements are logged in the build log and in `body-<mode>.json` "auto_broll".
- **Edit options** (New Project + right-click → Project settings):
  - **Trim only**: any type. Runs the transcript and the cutter, then `app\tools\trim_render.py` writes `<project>\<title> - TRIMMED.mp4` with nothing added. **Speed**: 1× / 1.1× / 1.25× / 1.5×.
  - **Music**: on by default. When off, the step env gets `STUDIO_NO_MUSIC=1`; gaming assemble, phone build_main and review pick_music then add no bed.
  - **Privacy check**: on by default, phone only. When off, the env gets `STUDIO_NO_PRIVACY=1`: no address scan, no blur, no final sweep. Turning it back on rescans.
  - Routing lives in `app\recipes\__init__.py` (`trim.py` for trim-only projects).
  - **Captions**: OFF by default (standing rule: no captions unless asked). Tick it per project and pick a style; the
    dropdown shows a preview (`ui\captions\<style>.png`). Styles = what most creators use: Bold pop / Hormozi (the default:
    Montserrat Black, caps, spoken word yellow, 22 % up so it clears lower thirds), Clean subtitles (Montserrat Bold), MrBeast (Komika Axis, 2 words, green), The Bold Font
    (tall caps, red), YouTube CC box (Roboto on black). `app\tools\captions.py` transcribes the finished render (GPU whisper
    medium.en, project `vocabulary` as hotwords), skips the intro, burns the captions in place (NVENC H.264 High yuv420p,
    cq 17 finals / 21 drafts, audio copied) and keeps the clean render in `<project>\_captions\`, so a style change re-burns
    and unticking restores it. `recipes\__init__.py` `with_captions()` adds the step before QC on draft / final / revise /
    intro-only builds of every type. Fonts live in `app\fonts\`; a missing one falls back (Montserrat -> Poppins,
    Komika Axis -> Bangers -> Anton, The Bold Font -> Anton): drop the real .ttf in and run `captions.py --previews`.
    Phone builds pause the captions while a promo-code card is up (`edit\graphics\events.json`). Screen / trim-only edits
    are NOT re-burned: `tools	rim_render.py` burns them inside its single render (its own medium.en words of the edit,
    the same presets via `captions.build_ass`, the filter last on [v] so captions sit above zooms / graphics / overlays).

## Motion graphics (2026-10-22)
- **Edit options → Motion graphics** (screen-recording edits for now) + a type dropdown. Type 1 = **Article highlight (3D)**, the MacBook one-off's
  news card: a real article page tilted in 3D, the camera pushes to each claim and a yellow marker sweeps over it, "Source: <outlet>" pill.
- Optional **Article link** and **Highlight** (phrases split with `|`). Left empty, Claude (CLI, web search, ~1-2 min) reads the kept
  transcript, finds an article backing the main claim, copies 1-3 exact phrases from it and picks the spoken line the card starts on.
- Step `graphics` (app/tools/motion_graphics.py) between the cutter and the render: Playwright capture → crop to the article column →
  HyperFrames render (kit from intro_library) → Edit\studio\graphics\graphics.json `{items: [{type, file, raw, dur, url, highlight}]}`.
  trim_render.py lays each item over the edit at its raw time (mapped through the kept ranges), 0.35 s alpha fade in/out, voice keeps running.
  Only the cut list makes it stale; the step's **re-run** button makes it again (new search). Add a type = a maker in MAKERS + GFX_TYPES (ui/app2.js).
- Screen renders also nudge the PICTURE (not the voice) where a video playing on screen hard-cuts within 0.36 s of a join (0.2 s "flash");
  the next piece's picture starts earlier and keeps its end, so no frames are lost. Tested on the MacBook video: 8 joins nudged, 0 flashes,
  picture = sound length (also fixed a 1-frame-per-piece loss from 4-dp rounding in the select times).

## Batch 5 (2026-10-22): faster builds + the targets check
**Targets check** (`app\tools\targets_check.py`, numbers in `app\tools\targets.json`): the last step of every gaming / phone / review build.
It measures the new draft/final against the approved finals (intro length, time to first entry/code, section lengths, big visual
changes per minute, loudness, % of the recording kept, talk speed) and writes `<video> targets.md` next to it with a fix for each miss.
It never fails a build. Change the numbers in targets.json when a new reference video is approved.

**Speed** (Top 10 Servers revision: 5-7.5 min -> 2.3 min; phone revision ~15 min -> ~6-7 min expected):
- Gaming piece cache (`body.py`, `segs-*\cache`): a piece whose ffmpeg command + input files are unchanged is reused (settings.seg_cache = false turns it off).
- Gaming frame-scan cache (`cuts.py`, `cuts\frame_scan.json`): UI panels / frozen / loading flags per raw piece, decoded once.
- AI take review frozen after draft 1 (`_tools\phone_edit\take_review.py`): later builds reuse its cuts (raw times); settings.take_review = "fresh" re-asks.
- Phone: layout analyses cached per recording (`work\layout_*.pkl`, 211 s -> 0 s), code OCR cached by raw time (`work\ocr_cache.json`, 133 s -> 21 s),
  HyperFrames graphics cached by their variables (`edit\graphics\renders\_cache`, unchanged cards aren't re-rendered).
- Whisper on the RTX 4070 (`_tools\whisper_gpu.py`; pip nvidia-cublas-cu12 + nvidia-cudnn-cu12): ~3.8x faster than CPU, CPU fallback automatic
  (WHISPER_DEVICE=cpu forces it). Batched whisper was ~5x faster again but uses VAD chunks (drops ums, 88.7 % word agreement), so it is not the default.
- Parallel steps (`jobs.py`): a step with "background": True runs alongside the next steps; "wait_for": [ids] waits for it. Gaming runs the CPU
  B-roll scan while the GPU transcribes.
- Not faster: NVDEC GPU decoding was slower than the CPU for these scans (14.9 s vs 6.5 s per 2 min), so scans stay on the CPU.
- Phone privacy address scan (`_tools\privacy.py find`, 2026-10-22): templates + phone OCR now share ONE decode with two worker threads, and the
  website-half OCR runs alongside (OCR engine per thread in privacy_ocr.py). dhgate coupons (16 min): 259 s -> 172 s, blur items identical
  (24/24). PRIVACY_FAST=0 runs the old three passes.
- Phone first build: running the layout scans alongside the privacy scan (`layout.py --warm`, LAYOUT_WARM=1) was tested and made the first
  build SLOWER (21.2 vs 18.5 min: both need the CPU), so it is off by default. First build on the scratch copy: 18.5 min (was ~23).
- Measured on a scratch copy of dhgate coupons (16 min): phone REVISION 7.7 min (was ~15-16; take review, OCR, layout and all 14 graphics
  reused). Remaining revision work: full-res re-cut ~1.6, blur ~1.2, compose ~1.8, final privacy sweep + QC ~1.7 min.

## Batch 5 (2026-10-22): Claude at the judgment points
The pipelines stay rule-based and free; Claude is called only where rules guess wrong, through one lean helper
(`{{KIT}}/tools\claude_brain.py`: no memory/skills/hooks/MCP loaded, so ~1-5k tokens a call instead of ~146k;
answers cached, so a rebuild never asks twice; every call logged in `_tools\_state\claude_ledger.jsonl`).
- **Intro director** (`intro_library\director.py`, every intro type): one Opus call sees each VO line plus a contact sheet
  of the actual clips and decides what each line shows: your clip #n, a real picture (exact search), stock B-roll, or type
  only. Rules for it live in `intro_library\director_rules.md`; add a line there when you give intro feedback.
- **Picture check**: one Sonnet call looks at every picture before it is used; a wrong one is replaced or dropped
  (Cartier test: caught a solid-dial Santos photo on the "Cartier Skeleton" line).
- **QC flag review** (`app\tools\claude_review.py`, step "Claude reviews the QC flags" after every QC check): no flags =
  no call; otherwise one Sonnet call marks each flag fine / REAL with a suggested note. Shown in Review + notes (the flag
  text starts with ✔ Claude / ⚠ Claude) and in `<video>_check\claude_review.md`. Nothing is cut automatically.
- **Cost**: about $0.06 per intro (director + picture check) and $0-0.03 per QC review. `python claude_brain.py ledger 7`
  prints the last week. The Shorts titles, descriptions, note interpreter and phone take review use the same lean flags now.
- **Switch**: New Project / Project settings → **Claude director** (on by default; off = `CLAUDE_BRAIN=0`, pure rules).

### Teaching the AI director
- `tools/teach.py`: every prompt carries the playbook (`tools/teach/playbook.md`) and the newest worked examples
  (`tools/teach/examples/<task>/`). When a video is approved or you correct a decision:
  `python teach.py add intro_director --answer <director.json> --title ... --lesson "why"`.

## Batch 2026-10-24: Gling-style transcript cutter + redesign
- Editor tab = `ui/app4.js` (replaces renderEditor/wireEditor). Modelled on Gling 1.66's TextEditor (studied from its shipped
  source maps in `C:\Program Files\Gling\resources\app.asar`): sentence rows with a ✂ gutter button, selection snaps to whole
  words + bubble (Cut / Keep / B-roll / Short), Backspace/Delete/D cut-uncut, Shift+Backspace = sentence at playhead,
  ←/→ word, Shift+←/→ sentence, Space, Ctrl+Z / Ctrl+Shift+Z, H hide cuts, F full screen. Playback hops over pending cuts.
- Every cut/keep is a studio note (`from: "editor"`, raw times); adjacent cuts merge into one note; uncut/undo removes or
  trims notes (POST project/notes remove + notes). They show in Revisions as "Next batch"; "Apply + rebuild" = rebuild-notes.
- recipes/review.py apply_notes: extra_cuts.json is no longer merged forever. Ranges Studio wrote are tracked in
  raw/studio_extra.json and replaced from the notes each time; protect notes -> raw/extra_keeps.json. LIVE AFTER A RESTART.
- Redesign: `ui/redesign.css` (tokens, sidebar with SVG icons, compact project header with Details drawer + ⋯ menu, tabs
  Editor / Revisions / Build ..., dashboard "Needs you" with empty lists hidden, idle channels hidden, hub folded).
  Backup of the old UI: `_backups/2026-10-24-before-redesign`.

## Batch 2026-10-24 (afternoon): revision speed for review + phone
Measured first (770 job logs): one review build ~10 min, phone ~18 min, but revision batches took 20-155 min.
47 of the last 60 review builds re-made the intro from scratch (AI plan + 3 renders, ~8-10 min) with no note on it,
mostly because the shared intro code had changed that day; the revision AI ran up to 5 full builds per batch.
- **Intro lock** (review). `tools/review_intro.py`: with `STUDIO_INTRO_LOCK=1` (set by recipes/review.py on the intro
  step) a built intro is kept as it is; only a new VO or a style / music / pin change in settings re-makes it. Code /
  sections / B-roll changes re-make it only when `STUDIO_INTRO_REBUILD=1`: a fresh build (force), `doc["intro_rebuild"]`
  (set by api_rebuild_notes when any note of the batch is about the intro, `server.note_in_intro`) or
  `{"action":"draft","intro":"rebuild"}` on /api/project/run. start_build pops the flag for that one build; a failed
  build puts it back. Intro-only builds (action "intro") keep the old rules. Test (yeezy scratch copy, intro code newer
  than the render): intro step 21 s instead of ~8-10 min.
- **One build per batch** (all types). The revision message tells the AI to make every fix, check without rendering,
  build ONCE and verify with frames at each note's time; a 2nd build only for a note still wrong or a failed build.
  /api/project/run replies with `warning` from build 2 of a running batch on. chat.py system prompt + resume text agree.
- **Phone stage stamps** (`{{KIT}}/tools\phone_edit\pipeline.py`, backup `pipeline.py.bak-speedcache`): `same_content`
  gives a byte-identical output its old file time back, and `work\<stage>.stamp` (cuts, layout, events) records that the
  stage ran, so an unchanged result no longer re-renders the full cut, layout, graphics, main video and privacy sweep.
  `sh()` now prints `<< N s <script>` after every step (find slow steps in the job log).
- **bridge.py raw scan cached** (`workridge_bars.npz`, keyed on the recording's path/size/time): 46 s -> 1 s, layout
  byte-identical. Scratch test {{PROJECTS_ROOT}}\_speedtest\coupons (17 min source, one added cut, a Studio render running
  alongside): revision 6.9 -> 5.8 min, same QC flags + clean privacy sweep as the real draft. The rest of a cut
  revision is real work (full-res cut 60 s, blur 50 s, compose 75 s, sweep + QC ~1.5 min).
- Backend changes are LIVE ONLY AFTER A STUDIO RESTART (review_intro.py / pipeline.py are read per build, but the lock
  only switches on with the new recipe's env). Backups: `_backups/2026-10-24-before-speedups`.
- **Two render slots** (`jobs.py` `slots()`, settings `"render_slots"`, default 2; 1 = one at a time). The second slot is the
  existing SHARE pass: a build that gets its turn moves into it when free, so the next in line starts; when the SHARE build
  ends, the build rendering now moves over. Never more than 2. Why: this morning each review build waited ~16 min in line
  while the PC ran ~40% CPU / ~35% GPU with one build. Fake-job test (4 builds): 42.9 s -> 26.0 s, peak 2. Not yet measured
  on real builds: each build may run somewhat slower side by side (CPU), but nothing waits 16 min. Backup jobs.py in
  `_backups/2026-10-24-before-speedups`.
- **Targets check is light** (`recipes/common.py`): as the last step after the AI QC review it kept the render slot up to
  5 min; now the slot passes on once only the AI review + targets are left.
- **QC check passes in parallel** (`{{KIT}}/assets\Tools\check_video.py`, backup `.bak-parallel`): the
  black/frozen/silence pass and the loudness pass run alongside the frame scan instead of after it; identical report
  (canada goose final: same 20 flags, cuts, loudness). GPU decode was tried and was slower: opt-in `CHECK_HWDEC=1`.
- Looked at and NOT done: half-size review drafts (the approved draft IS the final, so it would add a full render at
  approval); QC only on the changed parts (saves seconds on most videos, risks missed flags).
- **Whisper GPU-hang watchdog** (`{{KIT}}/tools\whisper_gpu.py`, backup `.bak-watchdog`): every GPU transcribe runs
  in a worker thread; past max(90 s, audio/4) it is redone on a CPU model (kept for the rest of that process). Why: canada
  goose, dhgate haul #11, lv skatesta and top 5 products each sat 25-33 min at 0 CPU in a CUDA transcribe until the stall
  kill retried them. Tested: normal 0.2 s on GPU; forced timeout -> CPU redo in 1.9 s. `WHISPER_GPU_TIMEOUT` overrides.
- **Stall kill 25 -> 12 min** (jobs.py STALL_KILL_MIN, 0.4 min per footage minute instead of 0.75).
- **Regression replays in parallel** (`{{KIT}}/tools\regress\regress.py`, backup `.bak-parallel`): 6 at a time
  (`RG_JOBS`), each run in its own `_regress\run-<pid>` folder (deleted after; two AIs replaying at once used to delete each
  other's shadow copies). Why: the canada goose batch spent 30 of its first 42 min on 5 sequential replays.
- **Revision AI: build first, replay while it builds** (chat.py rules): no "before" replay (baseline.json is the before),
  bisect drifts from the report first. Live since the Studio start after the PC reboot (2026-10-24 14:19).
- Tried and dropped: `-filter_complex_threads 16` on the phone compose (28.6 vs 29.9 s, no gain), GPU decode for the compose
  (hung) and for the QC scan (slower).
- Studio restarted 2026-10-24 13:54 with: intro lock, one build per batch, two render slots, light targets, stall 12 min.
- **Phone full-res cut render seeks to the kept pieces** (`{{KIT}}/tools\render_draft.py`, backup `.bak-seek`): each
  kept piece is its own input, seeked to its first frame and trimmed to the exact frame count / audio packets the old
  select pass keeps; every 2nd frame of the joined 60 fps run (what fps=30 picked). Only the kept minutes are decoded.
  dhgate coupons (17 min source, 14 pieces): 65 s -> 27.5 s, same 6210 frames, avg PSNR 51-56 dB vs the old render; 4 frames
  differ by 1/60 s where the old fps filter rounded onto the next source frame. Falls back to the old single pass (bit
  identical) for non-integer frame-rate ratios, > 60 pieces, or `RD_SELECT=1`. End-to-end phone run OK (privacy sweep
  clean). Quiet-machine check (only Steam running, 20-piece 297 s cut): old 64.5 / 69.2 s, new 37.5 / 39.7 s, same 8904 frames.
- Found while testing (NOT mine, flagged to the session): take_cuts.py 14:53 "retake kept ... muttered off-mic" rule changes
  the approved dhgate coupons cut (first trim 4:13 -> 5:43); regress.py only covers review projects.
- **First real build on the new code** (watchb draft 14:57, 24.1 min: edit 10.2, intro 12.5): the intro was re-made
  correctly (5 intro notes + style switched to R01). Two follow-ups, LIVE since the Studio restart ~15:40:
  - /api/project/run also unlocks the intro when the running revision run has an open note about it (a Claude Code chat
    calls the API directly and never went through api_rebuild_notes, so intro fixes could have been locked out).
  - An intro re-made because of his notes (STUDIO_INTRO_REBUILD=1) gets 1 self-check fix round, like intro-only builds
    (~3-4 min less than the 3 renders + 2 AI looks watchb's took). First drafts keep 2.
- **Review edit profile** (cProfile, shadow copy of watchb, caches warm): 106 s total, 88 s = the final render (~5x
  realtime NVENC); every Python stage together < 3 s. Watchb's 10.2 min edit in Studio was first-time work for that
  batch's new cuts (AI take review, vision checks on newly kept ranges), cached afterwards. Nothing big left on a
  repeat review build; the remaining wins are fewer builds per batch (prompt rule) and measuring real batches.
- **Speed report**: `python app\tools\speed_report.py [--since "YYYY-MM-DD HH:MM"] [--md data\speed-report.md]` lists every
  revision batch since a time: builds in the batch, minutes in the render line, each build's step minutes, minutes from
  "notes sent" to the last build. First real batch on the new code (watchb, 13 notes): 1 build so far, 0 min in line,
  24.1 min built (edit 10.2, intro 12.5 = intro notes + style change); its 79 min sent->build includes the 14:19 reboot.

## Ideas board + Competitors tab (2026-10-25)
Backend `app/ideas.py` (routes registered at the end of server.ROUTES), UI `ui/app7.js` + `ui/ideas.css`. Live after a Studio restart.
- **Ideas** (sidebar): cards with title, format (Add-on showcase / Top 5 / Top 10), why (reference videos + views), thumbnails,
  candidate download pages. **Approve** = Studio project + folder under {{GAMING_ROOT}}, `Showcase guide.html`,
  `Download links.txt`, `00 START HERE.txt`, `idea.json`, `mc.py video new`, TickTick card on the channel board. Nothing is
  downloaded. **Dismiss** stores the key in `data/ideas.json` "dismissed" and the idea never comes back.
- Sourcing ({{GAMING_CHANNEL}}): 18 YouTube searches, this week + this month sorted by views, long-form only, English, Bedrock only
  (CurseForge `/minecraft/`, Modrinth and Fabric/Forge videos are skipped). Each description is read for download links:
  free download / Marketplace only / no link found. Hidden by default: Marketplace-only, no-link, and already covered
  ({{GAMING_ROOT}} folders, library.json videos and featured add-on pages). A Top 5/10 card is made per category with 5+ free add-ons. `minecraft-topic-report.json` in TickTick Bot (from the research
  session) is imported as "research report" cards.
- Refresh: the button, or by itself every 12 h. When settings.workers has the laptop, the scrape runs there over SSH
  (`python ideas.py source --out ...`), the result is copied back and merged here; laptop off = runs here. Network only.
  Descriptions are cached for 7 days in data/ideas-cache.json.
- **Competitors** (sidebar): tracker.py outliers (long-form, last 7/14/30 days) as a thumbnail grid: channel, views,
  × subscribers, × usual views, +24 h, upload date. Filter by niche/channel, sort, search. Uses the newer of the desktop and
  laptop `tracker_data.json` (the laptop copy is pulled by scp at most every 30 min). **→ Idea** reads the video's description
  and adds an Ideas card on top of the board.
- More channels: add a source function to `ideas.SOURCES[<channel>]`, returning idea dicts (see source_minecraft).
- Test without touching the live app: `STUDIO_TEST=1`, `IDEAS_DRY=<folder>` (approve writes only to that folder: no project, library or TickTick).

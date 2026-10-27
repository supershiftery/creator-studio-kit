# Intro Library

Turns one intro VO + one template into a moving HyperFrames intro (and the rendered MP4).
60 templates: review R01-R20 (R03 cut), phone P01-P20, gaming G01-G20.

## Build one intro

```
python build_intro.py --type review|phone|gaming --template R01|auto --vo <intro.wav> --title "<evergreen title>" \
       --footage <footage.json> --out <dir> [--music <track>] [--render]
python build_intro.py --list [--type phone]
```

- `--template auto` = least-recently-used template of that type (`_state/rotation.json`).
- Music rotates per type (`_state/music.json`); pass `--music` to keep the same track on a rebuild.
- Whisper words are cached in `<out>/vo-words.json`; delete it to re-transcribe. The title is the Whisper hint.
- Output: `<out>/renders/intro.mp4`, always H.264 High yuv420p + AAC.

### footage.json

A list of clips from the user's own recordings, one per VO line at most:

```json
{"src": "main.mp4", "t": 115.0, "crop": "right", "tag": "slide in hand", "for": "hands"}
```

- `crop`: `left` / `right` (half of a side-by-side OBS recording), `phone` (+ `box` = `w:h:x:y` of the mirrored phone, portrait), or none (full frame).
- `vf`: extra ffmpeg filters after the crop + scale to 1920x1080, e.g. `",crop=1600:900:200:96,scale=1920:1080"` to cut away browser tabs and the taskbar. The coordinates are in 1920x1080 space (after the scale).
- `for`: a word in the VO line this clip belongs to, or a list of words (first clip with a hit wins); otherwise clips fill lines in order.
  Review intros (review_intro.py) tag his own screen recording of the store page `for` store/link/"where to get" lines, face-free, browser bar + taskbar cropped off.
- Travel lines (airport, traveling, TSA, flight, suitcase) always get stock B-roll (`CONCEPT_VIDEO` in pics.py, max 3 stock clips per intro).
- `kind` (phone videos): `cam` = landscape window scene (cam clips and desktop screen recordings), `phone` = inside a phone frame.
- `roles`: which line roles may use the clip (hook/problem/turn/reveal/watch).
- Never pick shots with a private address, an account name, or dates (codes like `DH2025MAY...`, expiry columns, product titles with years).

## House rules (enforced in code where possible)

- No emojis, no dates/years/months on screen (spoken dates are dropped from captions and keys automatically).
- Footage always in colour; smoke/plain backgrounds only for text-only beats.
- Gaming: one 808 on the drop, XP fill + ding on "watch to the very end", no risers.
- Phone: one steady beat, no 808/risers/whooshes, cash register on money words.
- Every intro must move: `python _work/motion.py <mp4>` near-still frames under ~25%.
- QC before showing: `{{KIT}}/assets\Tools\check_video.py check <mp4> --no-words`.

## Files

- `director.py` + `director_rules.md` - Claude plans what each line shows (one Opus call, looks at a contact sheet of the clips) and checks every picture (one Sonnet call); `--direct off` or `CLAUDE_BRAIN=0` = keyword rules only. Output: `<out>/director.json`.
- `build_intro.py` - VO analysis (lines, roles, keys), camera plan, footage slots, audio, HTML assembly, render.
- `kit/kit.js` - runtime: camera rig, captions (`K.kinetic`, option `until` clears captions before the title), pictures, icons, XP bar.
- `kit/scenes_gaming.js`, `kit/scenes_phone.js` - one literal scene per VO line, picked by `RULES` regexes.
  Gaming has `ytscroll` (a drawn video-results page that scrolls fast, slows, gold frame + click) for lines about YouTube/videos/views/search.
- `templates/<type>/<ID>/` - template.json (footage roles, hold, sfx), body.html, style.css, scene.js.
- `pics.py` - real clips/photos of named things (Wikimedia Commons, then Mixkit stock); credits in `<out>/pics.json`.
- `check_all.py [IDs]` - builds each template on its demo VO and runs `hyperframes check`.
- `make_gallery.py [IDs]` - renders demo previews into `gallery/`; `art_gallery.py <dir> [IDs]` writes the claude.ai gallery page
  (https://claude.ai/artifact/F4xxgBXSkN21VVMYEhhcL7, Keep/Tweak/Drop in db collection "verdicts").
- `_work/gen_phone.py`, `_work/gen_gaming.py` - generate the P02-P20 / G02-G20 themes over the scene banks.

## Quality gate + editor toolkit (2026-10-24)
- `intro_score.py <mp4>`: scorecard (shots/10 s, longest hold, repeats, half-empty frames, stills); `--calibrate` = his judged set.
- `intro_check.py` measured rules: shot > 3.5 s, same source moment twice, 4+ web-page/stock shots in a row, names he says
  with no shot of them, half-empty frames (warning only). `regress_intros.py` replays them on his judged intros: run it
  before/after any intro change.
- Editor toolkit (templates with `"editor": true`; R21 Editor Cut, P21 Editor Phone, both status "test" until approved):
  stamp / chart / money-rain graphics on his words (`editor_graphics`), 3-4 cartoon FX cuts (`fx_plan`, `K.fxCut`),
  phrase captions + hero ending (`K.punch`). Study: `_references/channel/STUDY.md`.

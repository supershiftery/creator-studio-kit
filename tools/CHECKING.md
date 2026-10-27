# How to check a video (run before the user sees ANY cut)

Source: Duncan Rogoff, "I Finally Solved AI Video Editing" (youtube VVWiJm0sA7Y, job 5 "checking the work"),
adapted to the user's videos on 2026-10-20. Rule: check the way a viewer watches, not the fastest way.
Sampling 1 frame/s misses mistakes, so look at 10 frames/s, and look at every flagged moment yourself.

Tool: `python "{{KIT}}/assets\Tools\check_video.py" check <video> [--raw] [--no-words] [--protect x,y,w,h] [--sheets flags|all]`
Output: `<video>_check\report.md` + `report.json` + `sheets\*.jpg` (a 10 fps contact sheet for each flag).

## The checks
| check | what it catches | how |
|---|---|---|
| repeat | an animation/shot that plays twice | 1 s+ moving stretch matching an earlier one within 15 s |
| flash | a graphic/frame on screen for a split second | A-B-A at FULL frame rate (2-frame flashes fall between 10 fps samples), shots < 0.3 s between hard cuts |
| brief | text/graphic gone in under 1 s (too fast to read) | grid cell that pops, HOLDS still, and reverts within 0.2-1 s (moving speed lines don't count) |
| cover | a graphic covering the face cam | sudden change inside the `--protect` box that isn't a cut |
| words | a word/phrase said twice | Whisper word timestamps, verbatim prompt; plus "word lasts too long" (Whisper hides doubles by stretching a word) |
| sync | lips drifting from the voice | `check_video.py sync <camera.mp4> <mic.wav>`: offset every 60 s; fixed offset = shift once, drift = re-sync per section |
| format | not H.264 High yuv420p + AAC 1080p (yuvj420p counts as wrong), true peak over -1 dBTP | ffprobe / loudnorm |
| black / frozen / dead-air | unintended black, a stuck render, silence over 1.5 s | blackdetect / freezedetect / silencedetect |

## Which flags to use
- Intros / voiceover-only pieces (MP3/WAV VO): `--no-words`. VOs have no retakes (user, 2026-10-20).
- Cut-only drafts of raw side-by-side recordings: `--raw`. Phone scrolls and app loading screens trip repeat/brief; run those on the final layout render instead.
- Final renders with a face cam: pass `--protect` with the face cam box.

## The loop (Duncan's "loop engineering")
1. Render a HALF-SIZE draft (fast). Full quality only after the user approves the cut.
2. Run the checker and open the flagged sheets. Decide for each one: real mistake or intended.
3. Turn real ones into fixes: `{{KIT}}/tools\feedback_cuts.py` maps "said twice" flags from draft time back to source time (`extra_cuts.json`).
4. Re-render and re-check until clean. ALSO read the draft's own transcript at the seams (intro, restarts, outro). That is how the clipped "Hey guys" and the lost "all you need is a mobile phone" were caught on the first test. The automatic checks cannot see a missing sentence.
5. Known noise: "very very" is how the user talks. Whisper hears slightly different words each pass, so a new 1-word double can appear after a re-cut. Listen before chasing it.

## When a note comes in
Find the rule in the skill that would have prevented it and REWRITE that rule (don't stack a second one on top). That keeps the skills from drifting and bloating.

## Privacy (address / phone number) - added 2026-10-20
`privacy.py check` must report 0 problems whenever the PICTURE changed (cut, blur boxes, layout, source). Audio-only or intro-only re-renders reuse the last passing sweep (pipeline.py fingerprints the inputs). User asked 2026-10-20 why it kept re-running. It tests each blur box frame by frame AND sweeps
the whole phone for any readable template. The sweep caught 2 cart rows (a different house number) that the box list missed.

## Learning from the user's own finished edit
`compare_to_final.py` aligns the user's upload with the raw transcript. OVER-KEPT = what my checker/cutter let through.
First run (Uber Eats): the misses were muttering, fuzzy restarts, stuck lines and dead-end sentences, all now rules in take_cuts.py.

---
name: short-edit
description: Edits raw VERTICAL recordings (1080x1920 phone / talking-head Shorts, TikToks, Reels) through {{STUDIO_NAME}}'s "short" type - normalise to 1080x1920 60 fps, tight trim, type beat, Doug captions over the whole Short, hook headline, punch-in zooms. Use when asked to edit, build, fix or revise a Short / vertical video recorded on its own (e.g. "What Is a Lift Kit"). NOT for Shorts cut OUT of a long video (Studio Shorts tab / extras.make_short / gaming shorts.py).
---

> **Before showing ANY draft and on every note: run the `editor-gate` skill** (one-take mode, per-type pre-show checks, note -> check, laptop sync).

**EDIT RULES FIRST (2026-10-25):** before building or showing ANY draft, read `{{KIT}}/tools\EDIT_RULES.md` (every past revision note turned into rules) and run its section I, the editor's pass. A note that says "again" / "never" means a rule exists but nothing checks it: build the check and update that file.


# Short edit (Studio type `short`, built 2026-10-23)

User 2026-10-23: "Build a Studio type for raw vertical Short recordings: keep it 1080x1920, trim, music, captions." Then: "I want
to create viral shorts ... talking head short style is what I am gonna try first". First test: "What Is a Lift Kit" (98 s
1080x1920 30 fps talking head, script given; project {{PROJECTS_ROOT}}\What Is a Lift Kit, script.txt in the project).

## How it is built (the haul pipeline in vertical)
- `{{KIT}}/Studio\app\recipes\short.py` (copy of haul.py: paths, ingest, steps, outputs; timeline-short.json).
- Normalise: `tools\haul_normalise.py`, canvas 1080x1920 when doc type = short (60 fps CFR, HDR -> SDR, Spatial Audio clips
  folded to mono + EQ/loudness matched). A clip of the other shape (sideways) sits on a blurred fill of itself (`needs_fill`).
- prep / transcribe / cuts: gaming steps (`gaming\cuts.py` treats short like haul: take review kind = doc type),
  take review KIND "short" in `{{KIT}}/tools\phone_edit\take_review.py`: cut harder (false starts, a point said twice,
  "so um basically" openers) but never the HOOK (first real sentence), the payoff, a number/name the point needs, the CTA.
- Render: `tools\haul_render.py` SHORT mode (`SHORT = doc type == "short"`): midstart guard; no greeting/outro/product
  structure (no Claude structure call); beats played through from 0:00 (no intro/outro beat), 15 LU under the voice;
  -16 LUFS, alimiter; draft 540x960 30 fps cq 23, final 1080x1920 60 fps cq 17; H.264 High yuv420p + AAC.
- Captions: Doug over the WHOLE Short in preset `doug_v` (`tools\captions.py`: 120 px Anton on 1920 tall, 12 px outline, max 3
  words / 16 chars, 30 % up so the Shorts UI doesn't cover it). The 1080p "doug" sizes are fractions of the height: 293 px
  letters on a Short, never use it there.
- Hook headline (study): 3-6 words over the first ~3.2 s, top of frame, keyword yellow, written by claude_brain task
  `short_hook` (cached Edit\studio\short_hook.json). `settings.short_hook = "text with *keyword*"` overrides, false = off.
- Punch-ins (study): framing alternates full / 1.15x push-in on the upper third at sentence starts, >= 1.5 s each, split
  at a word gap past 4 s. `settings.short_zoom` = false off / number = push-in.
- Detect (`detect.py` VERSION 5): an upright picture as shown (rotation-aware `_vertical`) = short +12, <= 180 s +2.
- Registered in recipes/__init__, store.TYPES/roots, server (multi-clip ingest, SKILL_DIRS, chat hint), chat.py, extras2,
  targets_check (timeline-short.json; no "short" targets yet -> gaming defaults), ui/app.js SLOT_DEFS + app3.js side0.
  Backend edits need a Studio restart.

## Viral Short study (2026-10-23, the user's 3 references)
1. Submagic ad (youtube.com/shorts/aJS-qY9VymI, 15 s, 42K views): RAW vs EDITED MrBeast podcast clip. Edited = hook title card
   in the first 3 s, ONE-word uppercase captions at chest height with the keyword yellow, a literal visual every 1-1.5 s
   (Facebook / Instagram / TikTok / YouTube logos popping on those words, a stock photo on "history", a phone screen),
   punch-in zooms.
2. Softgirlnocode "How I use AI to edit all my Short-form Videos (Hyperframes Setup & Prompts)" (z6zkeILNHL8, 98K views):
   HyperFrames + Codex + ElevenLabs captions; animated screenshots / interfaces, a live-typing chat window, text behind
   the person (Canva Magic Layers). We have HyperFrames skills installed - the route for animated cards.
3. Joseph | Video Editing "How to Edit a Viral Talking-Head Using ONLY AI (2026 Style)" (WcMOCtas1pg, 228K views): close-up
   podcast talking head, SMALL thin sentence-case captions, and every few seconds a full-screen WHITE minimal explainer
   card: dark headline with ONE blue keyword ("the average american adult", "they want to see you fail."), black-and-white
   cut-out photos with torn-paper edges, tiny labels ("obese", "divorced", "less than $1K"), hands pointing in.
Common rules: hook in the first 1-3 s (on-screen headline), the picture changes every 1.5-4 s, captions short and synced,
literal visuals for nouns/numbers, music low under the voice.

## Explainer cards (built 2026-10-23, `tools\short_cards.py`, Studio step "cards" between cuts and render)
- Plan: claude_brain `short_cards` (Claude) on the kept lines + script.txt -> cards (line, dur 1.6-3.0 s, headline,
  keyword, 1-3 pictures {query, alt[2], must, label}), `subject` (fallback photo search), `punch` (3-4 key words).
  Never a card before 3.5 s (hook stays on the face), never two lines in a row, ~30-40 % of the Short. Cached plan.json (v5).
- Pictures: Wikimedia Commons then Openverse (open licences, credits in cards.json), drawings / mostly-white rejected,
  then the eyes model checks ALL candidates on one labelled sheet (`short_pics_check`); a reject tries the next candidate /
  search (3 rounds). Cards still bare get a different subject photo (dedup by an 8x8 grey fingerprint: the same Ram came
  back from two URLs). Searches must name the subject + the part ("pickup truck leaf springs"): bare part names found a
  freight-car bogie, a Sherman tank, a LEGO truck, an RC buggy (all correctly rejected).
- Look: off-white card, Inter 800 92 px headline top-left, one keyword #2b6fea, grey torn-paper circles (PIL), white
  labels; layouts keep everything above y 1536 (bottom 20 %) and off the right edge. Motion: words rise one by one, then
  pictures ease in one after another (power2.out, no bounce), slow 1.03 push. Hard cuts in/out, cards cover the captions.
- Render: one HyperFrames composition (npx hyperframes@0.8.180, 1080x1920 60 fps) cut into card_NN.mp4; reused when the
  HTML hash is unchanged. haul_render SHORT overlays them (raw -> edit time).
- Punch-ins only on the planned key words (1.15x upper third, 1.2-2.5 s). Hook headline placed above the head top
  measured with the MediaPipe face landmarker (mesh top - 30 % of mesh height); no room -> on the chest.

## Grow with Alex rules ("Learn 90% of Claude Video Editing in under 20 Minutes", 03BNd8ygnq8)
Basics: dead air (cut inside pauses, never mid-word); first 2 s make sense with the sound off; good text (nothing in the
bottom 20 % or right edge); pace (a change every 2-3 s); grade (match the look, not the room). Hard rules: clean image (no
grain/glow/filters); natural face (never tint skin); one thing moves at a time (eased, no bounce, never stacked); captions
one style one position; no dead space above the head; steady framing, punch in on 3-4 words; measure the head top before
framing anything over it; big words readable by the time they're said. "Every fix becomes part of the prompt."
Workflow: beat table + contact sheet checked before rendering; several hook variations.

## Lift Kit test (2026-10-23)
98 s -> 53.3 s; hook kept (take_cuts fix), hook headline above the head, 6 cards / 15.9 s, 4 punch-ins, 0 QC flags.
Draft build ~1.5 min when cached, ~4-8 min with a fresh card plan + picture hunt. 3 of 6 cards text-only: the free photo
pools had no truck shocks / springs / spacer photos that passed the eyes check.

## Not built yet
- Better pictures for parts: the user has NO Higgsfield (2026-10-23). Own photos go in <project>\pictures\ named
  "<card number> <label>.jpg" (short_cards.py: they replace that card's pictures; the folder is a step input, so a rebuild
  picks them up). A stock photo API key would also help.
- Short targets in tools	argets.json (targets_check uses the gaming defaults: its "intro" / "section" misses are noise).
- Hook variations (Alex), white card variety (person cut-outs with rembg, number cards).

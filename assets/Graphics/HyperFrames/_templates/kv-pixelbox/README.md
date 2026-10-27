# KV Pixel Box intro — APPROVED template (2026-10-24)

The user's best old editor, KV Digital (2020 {{GAMING_CHANNEL}}), rebuilt as a HyperFrames intro. First used and approved on the
Top 10 Minecraft Servers intro (`reference-approved-v7.mp4` here = the final, user: "v7 is final"; sound design "matches perfectly").
Full study + every rule's evidence: `{{KIT}}/assets\Reference\editor-study-2026-10\STUDY.md` (v4-v7 sections).

## To make a new one
1. Copy this folder next to it (e.g. `HyperFrames\<video>-intro-kv`). Add `assets/vo-norm.wav`, the music, and `assets/gameplay/*.mp4` cut from the video's raw recording (game half: `crop=1920:1080:1920:0`).
2. Transcribe the VO (word times). One beat per line/idea, every key word on screen as a pixel box at its word time.
3. Rewrite the scenes in `index.html` (S1-S13 are the pattern library below), keep the CSS, the `kvbox` filter and the `slam()` helper.
4. `npx hyperframes@0.8.180 check` → `render --output renders/<name>-raw.mp4`, then the mix pass (below), then QC frames at every beat.

## The look (measured from his frames — do not drift)
- Font **Minecraftia** (proportional). One box PER WORD: `<div class="kv"><span>Word</span><span class="g">Keyword</span></div>`.
- Box = SVG filter `kvbox` (stepped pixel outline: fill #2A2530, red #F81010, orange #F8B000, slab shadow). Span padding 0 22px.
- Text white #F8F8F8 + ONE lime keyword (#88A800) per line. No other text colours.
- Sizes: 130 px main, 170 px hero (`xl`), 100 px (`m`), 84 px (`s`), 70 px (`xs`, card labels). Centred.
- Entry: `slam()` = big + tilted → lands with overshoot, keeps a small tilt. Camera shake on hero words only.
- Backgrounds: `dirt2.png` (KV dirt, mean 47/34/29, low contrast) + faint grey mascot ghost + vignette; lists on tan #A88038.
  Blurred gameplay under text stays BRIGHT (blur 12 px, no darkening).
- Mascot poses `pose1-5.png` (1 smug/hand up, 2 arms-up excited, 3 facepalm sad, 4 thinking, 5 shy) slide/pop in on matching lines.
- Logos: GIANT white, one at a time on dirt (xbox icon + "XBOX ONE" wordmark, PlayStation, Switch).
- NO Studio logo sting (user left that brand behind). End on a hero "Let's Go!" style slam, ~1.3 s, then the normal join.

## Pattern library (in index.html)
S1 word stack + mascot · key-art card slam · sad mascot · S4 tilted sticker collage + "lights out" darken · S5 hard-cut montage of
real pictures with push-ins · S6 photo → giant logos · S7 menu + vector red X + meme reaction (angry kid) · S8 drop: fire burst
(first 0.55 s only) → excited mascot · S9 blurred gameplay + word stack + thinking mascot · S10 list = cards IN A ROW, each playing
that item's real footage, label under each, building up · S11 big question · S12 VS split (underrated LOBBY vs a REAL featured
server lobby) · S13 Let's Go.

## Sound (approved v6/v7)
- ONE soft pitchless swoosh per key beat or listed item (`k_pop1/2`, ~1 per 0.8-1.5 s), never two stacked.
- KV's own whip swish (`k_whip`) only on scene entries; `k_passby` on big logos/cards; `k_shutter` per sticker; `k_buzzer` on a red X;
  `k_newpoint` (his cartoon blip) ONLY on a meme cutaway; `t_whoosh` under the fire burst.
- Levels: pops 0.07, whip 0.11, passby 0.09, shutter 0.6, buzzer/newpoint 0.1.
- BANNED: cartoon swing (the "shrill" whistle), cymbal, zap, crowd aww, hissy whooshes, pops/dings, 808s, risers.
- Mix pass after render (KV is very even, no spikes):
  `ffmpeg -i raw.mp4 -c:v copy -af "acompressor=threshold=-24dB:ratio=3:attack=8:release=150:makeup=2,loudnorm=I=-17:TP=-1.5:LRA=5" -ar 48000 -c:a aac -b:a 256k -movflags +faststart final.mp4`
  Target: -17 LUFS, momentary p95 within ~2-3 dB of the median, 0 spikes.

## Footage rules
- Every listed thing gets context (its real clip), every named site/server gets its real picture.
- Comparison beats: recognisable lobbies, real featured servers. Gaming recordings usually open in a featured lobby + the Bedrock
  Servers tab before entry #1 — mine those first. Label generically if a server's identity isn't certain.
- No dates/years in graphics, no emojis, game music (never Minecraft's OST), H.264 High yuv420p + AAC.

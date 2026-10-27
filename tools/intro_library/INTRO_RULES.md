# Intro rulebook (all video types) — what gets approved, what gets rejected

Built 2026-10-25 from every intro note in memory, `regress/study_log.jsonl` (139 intro notes), `director_rules.md`,
the channel study (`_references/channel/STUDY.md`) and the KV editor study
(`{{KIT}}/assets\Reference\editor-study-2026-10\STUDY.md`). Style catalog: `STYLES.md` (80 styles,
20 per type) + the gallery artifact (link in STYLES.md). Run this list BEFORE any intro is shown to him.

## The core idea (why intros fail)
He judges an intro on three questions, in this order:
1. **Does every shot make sense with the words under it?** (44% of all intro notes = wrong / irrelevant picture.)
2. **Is it moving?** A new real source every ~1.5-2 s, smooth, no long holds, no repeats. ("Boring" = held shot,
   repeated clip, empty frame, template page — never "not enough effects".)
3. **Does it look like an editor thought about THIS video?** One idea that only this video could have (the radar
   finding "#10 ???", the server LOBBY vs a featured lobby, Alibaba's own page, his own Sp5der hoodie on its word).
   A theme skin dropped over any VO = "someone had a template and plugged it in" (Realms KV v1).

So a STYLE is an editorial DEVICE (how the story is told: payoff first, a journey, a comparison, a dive), not a
skin (slot machine, newspaper, grid paper). The approved text layer of each type stays the same; the device varies.

## Approved text layer per type (keep; vary the motion/device around it)
| Type | Text layer | Music | Ending |
|---|---|---|---|
| Minecraft | KV Pixel Box (Minecraftia, per-word stepped box, white + ONE lime keyword, KV dirt) — calm kvgen baseline: ~0.85 phrase pops/s, one pop per PHRASE, shakes only on ~5 big words | other games' OST / game beats (never Minecraft's own), drop on the turn line | "Let's Go!" / title slam, XP bar on "watch to the very end", ends 0.3 s after last word |
| Phone / app | P21 glowing 2-4 word phrase captions, low, black outline; one caption track | one steady clean type beat, no drop trick, bed -28 | app title on "let's go", no gap |
| Reselling | R01 Smoke Words look (he asked twice: reselling = R01) | type beat by mood (music_lib) | no title card, slide straight into "hey guys" |
| Product review | full-frame footage + bold white word captions; brand lockup only as accent | type beat by brand vibe | no title card, footage under "let's go" |

## Asset mix: the main reason approved intros still "fall short" (2026-10-25)
His words: "some of them just don't have enough movement ... we need different assets, different things that are being
brought in, TikToks, articles, YouTube videos ... stock images, stock videos, GIFs". Measured on his judged intros
(source kinds per intro, his own product share): reselling spreadsheet ("perfect") 4 kinds / 22% product, sp5der 4 / 36%;
the "decent" ones 2 kinds / 70-100% (cartier 83%, s25 100% = "too much of the product").
- Target for every non-gaming intro: **4+ kinds of source, his product footage <= 50% of shots**, ~1 outside asset
  every 2 lines. intro_check now warns ("mix") when an intro has < 3 kinds or > 60% product.
- For each line ask "what OUTSIDE thing proves this line?" before using the product again.
- The asset menu (kit per style in styles.json "assets"): his own footage · creator TikToks · a fresh YouTube search ·
  YouTube thumbnail wall · the named site's page · retail / StockX page · ONE real headline · real photos of named
  people / places / brands · official logos · stock video that acts out the line · real viewer comments · Google Trends ·
  a real Reddit / X post · a map of a named city · real-footage GIF loops. (Gaming: gameplay, Director B-roll, real game UI.)
- BUILT 2026-10-25 (`assets_plus.py`, wired into Studio `review_intro.plus_footage`): YouTube thumbnail wall on
  "everyone / a lot of people / trending / booming" lines (year-titled videos dropped, titles never drawn), his viewers'
  real comments on "you guys asked / in the comments" lines (his own channel, positive or request comments only, names
  blurred), OpenStreetMap push-in for cities he names (nearby-town bias: Decatur next to Atlanta). All CPU-rendered.
- Not built: Google Trends (may be walled), GIFs, Pexels/Pixabay (GIPHY/Tenor/Pexels/Pixabay need free API keys only HE
  can sign up for; GIFs = real footage loops only). Reddit is BLOCKED for scripts here: not a source, never worked around.
- Phone (P21): intro_extras.py calls plus_footage for EVERY app with creators=True, so "content creators are
  gatekeeping" lines (Shein) get the wall of real promo-code videos (phone has no TikTok creator clips). Own channels are
  matched by substring ("{{PHONE_CHANNEL}}" contains "studio").
- Minecraft (hand-built HyperFrames): `assets_plus.thumb_wall([...], light='auto')` on "other YouTubers / everyone /
  so many servers" lines, or as the KV sticker collage source (minecraft-video skill has the one-liner).
- Movement floor: every shot moves (glide, scroll, push, the clip's own motion); no still frame held > 1.5 s unless it
  is a pan; the gaming intros he loves measure motion in every second.

## ALWAYS (approved patterns)
- Literal shot per line: the named product, brand, site, person, place, action. Real things beat drawn things.
- His OWN footage first (this recording, then his Drive videos via product_library), then real web pages, then
  real photos (Wikimedia), then stock that acts out the word. Product = the subject of every line (cologne != the city).
- Footage FULL FRAME. Cards / paper / panels are accents, max 2 template pages per intro, never back to back.
- Named site = that site's page scroll on its line (live, or recreated when walled). Named creator talk = muted
  creator clips (triptych) or a fresh YouTube search — a NEW query every video, never a reused screen recording.
- Named list ("Rolex, AP, Patek") = each item its own shot, ON the word (dissolve starts early, complete as he says it).
- Smooth: 0.3 s early dissolve or push/glide, calm 24 px glide 1.05-1.13 linear, sub-pixel zooms, 60 fps when the
  video is 60, steady windows of screen recordings, 30 fps clips interpolated. ("Looks smooth finally".)
- Arc: problem -> turn ("but in today's video") -> payoff. Gaming: the drop + big moment on the turn, title slam at end.
- Earnings lines show money (cash, payout, sold listing). Price lines show the product / its real retail page.
- Top-N teases: products and names blurred (boxblur 22), numbers sharp, 1..N in order shown.
- Story SFX tied to words, quiet and varied: key tap per fee, ping on the turn, register on "save", soft pitchless
  swoosh per KV beat, shutter on his-footage pops. SFX density follows the music tempo (~1 per beat max).
- Text-on-black only as a ~1 s breather for connective words; big centred text beats are fine when they alternate
  with clips (his 2023 Amazon intro).
- Ends 0.3 s after the last word, slides straight into the talking intro. Intro VO starts on his first word.

## Product-review STYLE POOL (user 2026-10-26: multiple styles yes, but one spine)
Every style keeps the same beats, footage FULL FRAME, the same caption look and the same handoff; a style only changes the
backdrop of the text beats and the transitions. Pool (review_intro.STYLE_POOL / pick_style): R21 smoke cloud (default,
story / news / hype lines), R02 grid notebook (comparisons, real vs fake, lists, rankings), R22 crumpled paper (deals,
codes, apps). Checkerboard (the house formula from the channel study) joins once built (needs his avatar PNG). Picked by
the voiceover / title, never the style this channel's last video got (_state/style_history.json), kept on rebuilds and
revisions (prior_template). Reselling keeps R01. Panel / card templates (R05 R06 R10 R13 ...) are NOT in the pool.
A new style joins only after he approves it on a real video.

## NEVER (each one was a rejection)
- A product's clip before he names it; another product's reviewers / ads (AirPods Pro noise graph, Apple ad) on a reselling intro; him holding an item to the talking camera in a multi-product intro ($30k reselling 2026-10-26).
- The SAME price graphic in every intro (user 2026-10-26: "that tag for the price ... the green background ... looks the same across all"). kit.reviewMG price has three looks from his editors' intros, one per video by its seed (I.priceStyle pins one): glow = huge glowing yellow price over his footage, burst = glowing price on a purple sunburst, tag = the swinging tag.
- Footage shrunk into panels / cards / a map / a box frame as the main look of a {{REVIEW_CHANNEL}} / {{REVIEW_CHANNEL}} 2 review intro (balenciaga
  track led review 2026-10-26, R10 Shipping Route: "everything's super small ... not up to our standards"; maison mahara,
  R06 Floating Panels). His published {{REVIEW_CHANNEL}} 2 intros (ref: youtube.com/watch?v=ONcmv2WAnSM, first 30 s) are FULL FRAME
  every shot: his product footage / on-feet, the store page full screen with the face circle, a few HUGE glowing keyword
  pops ($1000, HONESTLY, SURPRISED, $120), flash cuts, a cutout product hook. R21 Editor Cut is that look (pinned on maison
  mahara, balenciaga, lanvins 2026-10-26 as the test; panel templates only as a <= 2 s accent until he says otherwise).
- Generic Mixkit stock on a line about the PRODUCT ("X has risen in popularity in the street"): people dancing / a moped.
  Those lines get real YouTube clips of people with THAT product (review_intro.hype_footage; the name is checked against
  YouTube titles + how it sounds, a guess said "Margiela" for "Mason Mahara" = Maison Mihara Yasuhiro).
- A reselling-income YouTube scroll on a product's retail price ("set you back $500"): money bank only when the VO is about
  reselling / making money.
- Two pieces of one split line on the same HyperFrames track: the first rendered as a BLACK card (slot_html gives each its own).
- HIS OWN videos / channels on screen in a filmed search, thumbnail wall or creator clip (dhgae prada glasses 2026-10-26,
  0:18: our own video ranked #1 in the "best prada sunglasses dhgate" YouTube scroll right after "influencers are lying to
  you"). screenrec.hide_own removes every result card of his channels (creator_sources.json `own` + `own_contains`
  "{{REVIEW_CHANNEL}}"/"studio"; Shorts owners via YouTube oEmbed) before the first frame and as results load; a search left with
  < 3 results is not filmed (next query). creator_clips skips the same channels. New channel = add it to `own`.
- Cartoon FX of any kind: burst, fire, smoke puff, swirl, starburst ("corny ... quality goes down"). Emojis. Memes.
- Flashes / light leaks in phone intros, orange full-frame swipe, any full-frame colour panel wipe, dark/black wipe panel.
- Risers, swells, 808 / bass impacts. Cymbal, zap, whistle (cartoon swing), dings in KV. Gaming SFX in non-gaming
  (Pokémon XP / level-up sound in a review). Jingle/mission-start. Minecraft's own soundtrack.
- Black or empty screens / cards, dip to black mid-intro, a white page for a second, half-empty frames for long.
- Narrow / vertical intro with bars ("we make 16:9 videos"). Footage in small cards on a dark wall. Split-screen that
  reveals the recording is a side-by-side capture.
- One shot > 3.5 s; the same clip (or the same recording moment) twice; same kind of source 3 lines in a row;
  4+ web pages / articles; turntable on more than 3 lines; "too much of the product".
- Muted talking camera (reads as lip-sync). His desk / room / camera tests on "in today's video".
- Wrong-context pictures: brand that is also a place (Cartier valley), same-kind other product (his normal glasses,
  Eau Sauvage), workspace pages (Notion, Docs, CPA survey), random stock people (lady with a credit card, person cooking).
- His solo.to / Studio link page (3 times!). Linktree only when he SAYS it.
- Numbers he didn't say (invented totals, fees, coupon values); a price on screen that differs from what he says.
- Readable promo codes / IPs in an intro (retention). Blurred addresses. Dates, years, months in any graphic.
- Highlighting filler words ("guys", "starting"); weird text effects (the "mainstream" text effect), multi-coloured
  comic text, ransom-note titles, game-mode keyword callouts.
- Busy: too many pops (60 pops in 27 s = "seizure"), random zooms, elements gone before they can be read, shaky
  camera every 3 s, jitter / jumps inside clips.
- Retired templates (status off): R03 Spotlight & Cash, R07 Receipt Tape, R08 Swinging Price Tag, R09 Product
  Listing, R12 Magazine Cover, R15 Luxury Minimal, R17 Group Chat, R18 Giant Type Mask, R20 Score Card, R16 as a
  full intro (dark wall). Newspaper (R04) only as a 1-2 page accent. New styles must not look like these.

## Picking a style (so every video is different but deliberate)
1. Read the VO and tag its shape: comparison? journey? list/top-N? story with people/places? a problem with a
   villain (influencers, fees, featured servers)? an update/changelog? a before/after?
2. Shortlist the catalog styles whose `fits` match the tags (STYLES.md), drop any used on that channel in the last
   5 videos, prefer approved ("safe") > fresh > bold. Bold styles only as a test render, never straight to a delivery.
3. Write the ONE signature moment for this video (the thing only this topic has) before building anything.
4. Build, then the pre-send check below. Log the style id in the project (studio.json settings.intro_style).

## Pre-send check (every intro, every type)
- [ ] 1 fps contact sheet: every frame makes sense with its line; no link page, no workspace page, no wrong product,
      none of HIS OWN videos / channel names ({{REVIEW_CHANNEL}} ..., {{REVIEW_CHANNEL}} 2, Studio ...) in a search scroll or wall.
- [ ] intro_check / intro_score: no shot > 3.5 s, 0 repeats, shots/10 s near the type's target (review ~5.5-6.5,
      median >= 1.8 s; gaming 0.5-1.5 s per visual; phone readable, one idea per line).
- [ ] No black / empty / white frames (4 fps scan), no bars, footage full frame. No dark CARD either: a clip whose
      tail goes dark (a screen recording switching windows) is trimmed by build_intro._trim_dark_tail, and intro_check
      flags a dark last-frame poster (kind "black").
- [ ] Outside assets on topic: the thumbnail wall searches the whole topic phrase ("uber eats promo codes", never just
      "uber eats" = driver vlogs); comments only praise/requests; maps only real cities.
- [ ] Optical-flow spike scan: no jumps inside clips; brightness-jump count 0 for phone.
- [ ] Every number on screen = a number he says. No dates. No readable codes.
- [ ] Audio: no riser / 808 / banned SFX in the <audio> list; SFX/s within the music's beat; bed level per type.
- [ ] Ends 0.3 s after the last word; VO starts on the first word.

- **Own phone B-roll = only the steady part (2026-10-26, dhgate lanvins 0:20).** Never the head/tail where his hand grabs the phone (blurry floor/rug as it is picked up). review_intro.handled_span measures it per clip; a clip with < 2 s steady is skipped and a product picture from online fills the line instead.

- **One price card per intro; a price on a card is never also a caption (balenciaga 2026-10-26, 0:08 "$1,000" card + green "$1,000" caption, then the same card again for "$120").** build_intro.review_graphics keeps only the first price; kit.chunks drops money words inside a price/compare card window.
- Burst price card colour rotates per video: navy, red, emerald, purple (user picked 2026-10-26 from samples; charcoal + bronze rejected; purple alone every time was the problem); I.priceBurst pins one. Samples: TickTick Bot/price_card_colors.png.
- A LIST of products in the VO ("AirPods, Spider Hoodies, and even cologne") = one picture/clip per item on its word: product_phrases splits at commas; "clone" in a product list = cologne (Whisper); $30k reselling 2026-10-26 0:20.

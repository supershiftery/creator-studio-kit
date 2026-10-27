# Editing Playbook

These are the rules behind every video this studio makes. Each one came from a real note on a real draft: something
looked or sounded wrong, and the fix became a rule. The **why** matters more than the rule. Once you can feel the
why, you have the eye.

Rules marked **[house]** are craft. Keep them unless you have a strong reason. Rules marked **[taste]** were one
creator's preference. Your setup asks about them, and you can flip them.

---

## 1. The cut (all talking videos)

The goal is a video that feels like **one perfect take**. Nobody should notice a cut.

- **[house] Keep the LAST clean take of every line.** People restart until it sounds right, so the last try is usually the keeper.
- **[house] Cut:** retakes and false starts. Lines said 3+ times (keep the last). Fuzzy restarts ("once you are signed up" → "once you GUYS are signed up").
  Half-sentences that go nowhere. Muttering while navigating (about 9 dB quieter than your normal voice). Notes to the editor ("cut that",
  "hold on", "blur that"). Scraps under ~1.2 s. Dead air with no talking and no action.
- **[house] If a whole section was said twice in different words, cut the first one.** "Next up is…" followed 20 s later by
  "OK so the next method…" means the first try goes.
- **[house] Never cut inside a sentence.** Trimming pauses inside a sentence makes it "too snappy" and clips words.
  Only shrink pauses BETWEEN sentences, down to about 0.2–0.25 s.
- **[house] Never start or end a cut mid-word.** Every cut edge sits on MEASURED silence in the audio, never on the
  transcript's word times. Whisper ends words early and stretches them over pauses. Almost every clipped word in 16 drafts came from trusting it.
- **[house] Few, large cuts.** About 0.15 s of air before the first word of a piece and 0.1–0.2 s after the last one.
- **[house] Never cut the greeting or the sign-off.** "Hello YouTube" / "Hey guys" plays in full, and so does the final "Bye!".
  The sign-off is part of the show.
- **[house] Don't cut story moments you set up on purpose**, even when they look like a tangent.
- **[taste] Filler words:** *light* = um/uh only. *heavy* = also "and yeah / so yeah" bridges and lone "ya / alright".
  Never cut a "yeah" that carries meaning.
- **[house] Your notes are exact.** When you say "cut 1:22–1:30", the edges go exactly there, set on silence. A note can also
  *protect* a range so the auto-cutter never touches it.

**Train it:** watch only the joins. Listen for the breath and the first consonant of each piece. If you hear a jump in
room tone or a half-letter, that cut is wrong.

## 2. Sound

Bad audio makes people leave faster than bad picture.

- **[house] Voice level never drifts.** Run a slow leveller first (about a 15 s window) so loud and quiet stretches even out,
  then apply one measured gain to about **-16 LUFS**. Avoid heavy compressors: they pump the music up between words.
- **[house] Music sits UNDER the voice. Measure it, don't guess.** Voice about -16/-17 LUFS. Music bed about -31 to -36 LUFS
  (15–18 LU quieter). "Too loud" is the most common note of all. If the voice drops, the music drops with it.
- **[house] Instrumentals only.** Vocals and rap distract and hurt retention. Scan every track with Whisper (`medium.en`,
  no VAD). More than ~20 words means it has vocals, so reject it. Also reject producer tags ("BeatStars", "prod. by").
- **[house] Music never just stops.** Fade one track out over ~1.6 s ending on the section change, and fade the next in over
  ~0.5 s. Never let a track run out mid-section. Change tracks on a cut before that happens.
- **[house] One track per section.** The intro, the talking opener and each section/ranking entry each get their own track.
  The outro can repeat the intro's track as a bookend.
- **[taste] Music by genre:** phone/app and product videos = clean type beats (trap/R&B instrumentals). Gaming = upbeat game OSTs
  (Nintendo, Zelda, Sonic, menu / character-select music), never the game's own soundtrack, and themed when the content is themed
  (Pokémon server → Pokémon music for the whole entry). Screen recordings = a lo-fi bed.
- **[house] Sound effects: sparse and quiet** (about 0.16–0.5 volume). One sound per graphic *kind*, not one per graphic.
- **[taste] No risers, swells or 808/bass hits** in intros or before drops. They read as cheap. A section transition = a wipe + a soft swoosh.
  A money number slamming in = a cash register.
- **[house] Comedy beats work:** drop the music to silence for a second, or duck it under a suspense track during a fight and
  bring it back "like nothing happened".
- **[house] Old or muddy recordings:** EQ the voice clear before anything else.
- **[house] Every video ends on a ~1.2 s fade to black, picture and sound together.**

## 3. Picture and layout

- **[house] Show what you're talking about, the moment you talk about it.** When the screen changes, the edit switches to the screen.
  Don't wait for a head turn. When you read something out (a chat message, a price, a size chart), zoom into it.
- **[house] Keep the screen up while you're still referring to it**, even when it barely changes (reading survey questions, scrolling options).
- **[house] Loading screens and blank app screens are dead space.** Cut them when nothing is said. Hold the last good frame when you're talking.
- **[house] Silent demo stretches (tapping through an app) get sped up 2–4×**, slow enough that every tap stays visible.
- **[taste] Talking-head + phone videos:** always the full webcam. The phone sits as a tall picture-in-picture on the LEFT and slides in.
  Cards and titles go on the RIGHT.
- **[taste] Gaming:** never a full-screen face cam ("people are here for the game"). The corner cam goes top-left with a white border and
  is always gently moving. A big snap zoom only on genuinely urgent lines ("wait, what is going on?"). Re-centre the face if you sat off-centre.
- **[house] Inventory / menus / chests open on screen get a quick 0.3 s eased zoom** while you talk about them.
- **[house] No captions burned along the bottom** unless the format needs them (Shorts). Keyword titles and graphics do that job better.
- **[house] No dates, years or months in any graphic.** It makes the video look old in three months. Use evergreen words.
- **[house] No emojis in intros.** Draw icons, or use real pictures.
- **[house] Privacy, always:** your home address, real name and phone number get blurred in every frame, and a final sweep must find
  zero readable hits before a render ships. The address hides in carts, checkout pages and delivery tabs.

## 4. Intros (the first 15–35 seconds)

The intro decides whether people stay.

- **[house] Record the voiceover first, then build ONE literal scene per line.** If you say "TSA agents were commenting on my shoes",
  show an airport and a speech bubble with what they actually said. Never invent dialogue. If you name a real thing (a store,
  a car, a brand), show the REAL thing: your own clip first, then a free-licence photo or video, and only then a designed graphic.
- **[house] It must MOVE.** Every line gets a camera move (whip, punch-in, tilt, drift) and key words pop on their exact timestamp.
  QC: fewer than ~25% of frames should be near-still.
- **[house] Arc:** the problem (moodier) → the turn line ("But in today's video…") → the reveal (energetic) → a title slam on the last line.
- **[house] Rotate styles.** The same intro every video becomes formulaic. The intro library has 60 templates. Track which ones get kept.
- **[house] Colour footage only.** No black-and-white "problem" B-roll.
- **[taste] Gaming intros:** a fresh visual theme per video, pixel fonts, and "watch to the very end" = an XP bar filling plus a ding (signature).
- **[house] Intros can be built before filming**, as templates with labelled "GAMEPLAY GOES HERE" slots that get filled later.

## 5. Graphics

- **[house] One template, many renders.** A HyperFrames template with variables, rendered per use as a transparent MOV and overlaid.
- **[house] Codes/IPs typed out on cards** at the moment they're said, plus a "link in description" line. The "all codes in the
  description" card goes ONLY at the end.
- **[house] Codes come from THIS video's screen** (read with OCR), never from an old list. Codes change.
- **[house] Wipes use bright panels** (brand colour + white/gold). A dark panel reads as a black screen.
- **[taste] Lists and rankings:** each numbered entry gets a card (name + IP/code) and a section wipe. The section start times drive
  the card, the wipe, the music change AND the YouTube chapters, so get them exact.

## 6. The draft → final loop

- **[house] Drafts are half size** (960×540 or 1920×540) and fast. Finals only after the draft is approved.
- **[house] QC every render before anyone sees it:** the 10 fps checker (flashes, repeated frames, brief pieces, covered faces,
  doubled words, sync, format), the seam check (no edge on sound), the privacy check, and a read of every seam in the transcript.
- **[house] Deliver H.264 High, yuv420p, AAC MP4.** Never HEVC: some phones and editors can't play it.
- **[house] Time every render** and write it down. You can't speed up what you don't measure.
- **[house] When someone gives a timestamp, check which file they watched.** With an intro joined, main-edit time + intro length = output time.
- **[house] Every note becomes a rule.** Don't just fix the one spot: ask why it happened, then change the tool or the rule so it
  can't happen again. Rewrite the old rule; don't stack a new one on top.
- **[house] When a video is approved, it becomes a reference.** Save what made it work, so the next video gets compared against it.

## 7. Per video type (what the studio does for you)

| Type | Source | What the edit does |
|---|---|---|
| **Phone / app tutorial** (promo codes, money apps) | OBS side-by-side: webcam left, PC screen with a mirrored phone right (3840×1080) | auto-cut → privacy blur → layout map (talk / app / side camera) → phone PiP + code cards + section wipes → VO intro → beats per section → QC |
| **Product review** | 1–2 cameras (+ optional second mic), or a Gling XML | two-mic swap, camera switching on head turns AND screen content, circular face cam, zooms on details and price, price callout, subscribe overlay, rotating intro, beats |
| **Gaming list** (Top 5/10 servers, realms, add-ons) | long OBS recording (game + webcam) | sections from "coming in at number N", corner cam, B-roll under the talking intro, UI zooms, wipes, name/IP cards, game OST per section, chapters, Shorts from each entry |
| **Screen recording / walkthrough** (no cam) | plain 16:9 capture | trim (heavy fillers) + full-screen picture + lo-fi bed + optional article-highlight motion graphic backing the main claim |
| **Trim only** | anything | transcript + cutter, nothing added; optional 1.1–1.5× speed |
| **Shorts** | any finished video | ranks 18–58 s moments by energy + hook + clean ending, 1080×1920, -14 LUFS, title + upload notes |

## 8. Habits that compound

- Research topics from YouTube first: this week's / this month's uploads, sorted by views. Read the descriptions.
- Track competitors by **outliers** (videos far above that channel's normal views and subscriber count), long-form only.
- One recording session should become several uploads: a flagship, cut-downs per entry, and Shorts.
- Every finished video gets a description with chapters, a Drive hand-off, and a checked-off task.

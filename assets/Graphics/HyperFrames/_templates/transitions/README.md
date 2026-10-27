# Custom per-video section transitions (user request 2026-10-24)

User: "I would like custom transition motion graphics [for each video], because I thought that really brought the video to
the next level." The two approved ones get reused as-is; every NEW video theme gets its own.

## Approved (reuse)
| Video kind | Project | What it does |
|---|---|---|
| Server lists | `HyperFrames\server-transition` | Bedrock "server list" rows slide in from alternating sides with pixel-stepped edges, lock into a full-frame list at 0.34-0.44 s while a signal-bars glyph pops, slide out. |
| Realm lists | `HyperFrames\realm-transition` | "Case file" pixel blocks sweep in diagonally, cover the frame at 0.40 s, sweep out. Realms ONLY. |

## How the pipeline picks one ({{STUDIO_NAME}} `app/gaming/glib.py` `wipe_for`)
1. `settings.wipe` in the project's studio.json (a full path), else
2. **the project's own transition: any transparent `*transition*.mov` in `<project>\Graphics\`** (folders starting `_replaced` /
   `_test` are ignored), else
3. the Realms wipe for Realms titles, the server transition for everything else.
It plays over every rank cut with the audible swish (`settings.wipe_sfx`, default swish-fast.wav at 0.9).

## Making a new themed one (per video, before the edit)
1. Copy `server-transition` (or `realm-transition`) to `HyperFrames\<theme>-transition`.
2. Keep the CONTRACT (why the approved ones work):
   - transparent background, exactly **0.8 s**, rendered **60 fps** (`npx hyperframes render --fps 60 --format mov`);
   - motion builds in from one side/pattern, **covers 100 % of the frame from ~0.34 to 0.44 s** (the cut sits at 0.40 s,
     placed 0.4 s before the section start), then clears out the other way; never a frozen full-frame card;
   - Minecraft-native shapes (pixel-stepped edges, block textures, Bedrock UI pieces), one clear icon pop at the cover moment;
   - no audio in the MOV (the pipeline adds the swish), no 808/riser, no dates, no text that names a specific entry.
3. Theme it from the video's subject — literal, like the intros:
   - **Dragon add-ons:** a dragon wing / silhouette sweeps across, ember particles, scales texture cover; icon = dragon egg.
   - **Pokémon add-ons (Cobblemon, PocketMobs...):** Poké Ball rolls across splitting red/white, covers on the button flash; icon = Poké Ball.
   - **Shaders:** god-ray light sweep with a sunrise cover; icon = sun/moon.
   - **Texture packs:** block faces flipping tile by tile (old → new texture).
   - **Clients / mods UI:** menu panels sliding in like a settings screen.
   - **Add-ons in general:** item-frame / inventory slots filling across the screen.
4. Render to `<project>\Graphics\<theme> transition.mov` — the build picks it up automatically (step 2 above).
5. QC: frames at 0.34/0.40/0.44 s must be fully covered (no gameplay showing), and play one wipe in context with its swish
   before the full build.

Approve-once rule: the first render of a new theme is shown to the user as a short clip before the full video build.

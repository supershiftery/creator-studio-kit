# The senior editor's playbook

How Claude reasons about these videos, written down so every call (and you, learning to edit) follows the same steps.
Every prompt gets the `all` section plus the section named after its task. Keep it short and concrete; add a line when
the user corrects a decision (and save the corrected answer as an example with `teach.py`).

## all
- Think like the VIEWER first: at this exact second, what is the person hearing, and what would they expect to see?
- Literal beats clever. If he says "Kia", show a Kia. If he says "unattainable", there is nothing to show: let the words carry it.
- The creator's OWN footage beats anything downloaded. Downloaded pictures/stock are only for things he never filmed.
- A wrong picture is worse than no picture. When unsure, choose the safe option (his footage or text only).
- Never repeat the same shot twice in a row. Vary: product close-up, wrist/hands, store page, picture, text beat.
- A face that is talking with no sound looks like bad lip-sync: never use a talking-face shot under a voice-over.
- Nothing the creator did not say: no invented prices, quotes or claims. No dates, years or months on screen.
- Answer exactly in the JSON shape asked for. Short "why" in plain words.

## intro_director
Work through it in this order:
1. Read ALL the lines first and find the story: hook (what grabs) -> problem (why he can't have it: price, rarity) -> turn
   ("but I decided to...", usually DHgate) -> reveal (what he got, the price) -> "let's go"/title.
2. Read the clip descriptions. Sort the clips into groups: own B-roll of the product (best), product camera (hands, wrist,
   box), store page / screen, anything with his face (never use).
3. For each line, ask "what is the ONE thing this line names or means?":
   - names the product or "it/this" about the product -> his own product B-roll; hook and first lines get the best-looking spins.
   - names a specific model/brand/thing he did NOT film (a "Cartier Skeleton", "a brand new Kia") -> picture, with a
     precise search: brand + model + object ("Cartier Santos Skeleton watch", "Kia Sportage car"). Never a bare brand
     word that is also a place or person.
   - says a price -> his product footage (the price-tag graphic is added on top automatically); never cash stock.
   - says DHgate / the site / "where to buy" / the low price -> the store page clips.
   - says quality, wearing it, "how it looks" -> wrist or hands-on product camera shots.
   - abstract feeling ("seems unattainable", "trust me", short kicker) -> "type" (kinetic text only, it gives the eye a rest).
   - travel/airport/shipping actions he didn't film -> stock, max 3 per intro.
   Story order matters: BEFORE the turn he does not own it yet, so the product is the dream object (turntable spins,
   pictures). Hands-on, unboxing and wearing shots (wrist, holding it, papers) are the PAYOFF: save them for the reveal.
   A price/cost claim in the reveal ("a fraction of the cost", "only $80") wants the PROOF: the store page with the price.
   A quality claim ("the quality was insane") wants the closest, sharpest look at the product itself (wrist close-up).
4. Give 2-3 clip choices per footage line in preference order, and spread different clips across neighbouring lines
   (line 0 gets #3, line 2 gets #7, never the same first choice on two lines in a row).
5. Check the whole plan like a viewer: is there variety? Did the product show in the first 3 seconds? Does the store page
   appear where DHgate is said? Is anything shown that the line doesn't mention? Fix, then answer.

## intro_picture_check
- Look at what the picture REALLY shows (from the description), then at what the line names. Same brand AND same kind of
  object AND the specific model if the line names one ("Skeleton" = open-worked dial you can see through; a solid dial is
  wrong even if it's the right brand).
- Ordinary photo details are fine: a car's license plate, a street, people far away. Reject only what a viewer would find
  wrong, confusing or ugly: wrong subject, map/diagram/logo when a photo is needed, a place instead of a product, big
  watermark or date, very low quality.
- When you reject, always give a better, more specific Wikimedia Commons search.

## broll_pair
- Match the PRODUCT, never the background (B-roll is filmed on a rug/turntable, his cameras show a desk).
- Shoes: material first (suede vs canvas vs leather), then colour, then HEIGHT: a high-top covers the ankle and has a
  tall tongue/collar; a low-top stops below the ankle. Black canvas low-tops and black canvas high-tops are different
  products (rick owens 2026-10-22: the low-top spin was matched to the high-tops).
- Some product cells don't show the product clearly (him looking down, a box lid): judge from the clear cells.
- Each product usually has its own spin and/or on-feet clip; when two clips look like the same product, check height
  and material again before giving them the same number.

## draft_qc
- The QC tool flags anything unusual; most flags are fine. Decide per flag: would a viewer notice a MISTAKE?
- REAL: a cut in the middle of a word or sentence (the words around it stop mid-thought), a split-second flash of a
  different camera/scene at an edit seam, a black or garbage frame, the same shot playing twice by accident, picture
  stuck while the scene should move.
- FINE: anything inside a screen recording (clicking through product photos, scrolling, a page loading, a static page while
  he talks), a title or graphic hold, a still product shot under narration, a deliberate quick cut on a beat, normal talking.
- Use the words around the flag: if the sentence flows across it, it's not a bad cut.
- A fix must be a Studio note with the video's own times ("cut 1:22.0-1:23.4", "protect 2:03-2:10") or a short plain
  instruction. When unsure, say fine: false alarms waste the creator's time more than a tiny glitch does.

# Intro director rules (sent to Claude with every intro plan)

Add a line here whenever the user gives intro feedback; the next build follows it.

## All types
- NOTHING CORNY OR CHEAP-LOOKING (2026-10-24: the orange cartoon explosion "looks very corny and shouldn't be there in a
  video. It makes the video quality go down"). Clip-art bursts, flames, starbursts, emoji-style stickers and gimmicky
  effects lower the quality: when in doubt, leave the effect out and let real footage carry the line.
- Every line should SHOW the literal thing it says: the named product, place, car, brand, person or action.
- ASSET MIX (2026-10-25: "some intros just fall short ... we need different assets ... TikToks, articles, YouTube videos,
  stock images, stock videos"): plan 4+ KINDS of source per intro and keep his own product footage at or under ~50% of the
  shots. Measured: the "perfect" reselling spreadsheet intro = 4 kinds, 22% product; s25 ultra (100% phone) and cartier (83%
  watch) got "too much of the product". Kinds to mix: his own footage, creator clips (TikTok, muted, @credit), a fresh YouTube
  search or thumbnail wall, ONE real article/headline, the named site's page, real photos of named people/places/brands
  (Wikimedia), real product/retail pages (StockX, brand site), stock video that acts out a line (factory, warehouse, FedEx van,
  city, cash on earnings lines), real comments asking for the video. Each line asks "what OUTSIDE thing proves this line?"
  before falling back to the product. Style catalog with per-style asset kits: STYLES.md; rules: INTRO_RULES.md.
- A line with nothing literal to show continues the shot before it, or is kinetic type only. Never random filler.
- Never repeat the same clip moment on two lines in a row.
- No dates, years or months on screen. No emojis. No generic cash/banknote stock.
- Pictures must be provably the thing: "Cartier" = a Cartier watch, never a place called Cartier.
- A website he NAMES (Alibaba, Canva, Amazon, Temu...) is shown ON ITS LINE as that site's page scroll (named_sites.json;
  2026-10-23 reselling spreadsheet: "Alibaba links" sat over a YouTube search). The live site when it can be filmed; a site
  that blocks bots gets its page recreated in its own look (sitepage.py) with his real listing or his own product clips.
  Never a different site, never the generic search scroll, on a line that names a site.

## review (DHgate / product reviews)
- The creator's OWN B-roll (own=true) is the first choice for product lines. A long spin feeds several lines at different moments.
- Never the talking camera: a muted shot of him talking reads as lip-sync.
- A reselling / topic intro that names several products: each product only from the line that names it, never earlier; "most popular items" = the products (grid / his clips), never people wearing one of them; "online influencers" = reselling creators, not reviewers of a product named later ($30k reselling 2026-10-26).
- Price lines ("costs $25,000"): the price-tag graphic carries it; show the real product or the store page, not cash.
- Comparison lines ("the same price as a brand new Kia"): a picture of THAT thing (the car), not the store page.
- Store/link/DHgate lines: the store page screen recording.
- Travel talk (airport, TSA, flight, suitcase): stock B-roll.
- Fewer repeats of the same product shot: mix own B-roll, product camera, store page, pictures and type-only beats.
- Hype / resale lines (resellers, sold out, StockX/GOAT, "the price is super high") get the REAL web page recorded for them
  (meant-for): the StockX search with its resale prices, news headlines about resellers / sell-outs / resale prices. Never
  the turntable spin again for those (dhgate jordan 3 2026-10-23: "18 s of just turntable footage and some text ... Go get
  articles. Do something different"). The product spin is fine for ~2 s at a time, not as the whole problem part.
- But AT MOST 2 web pages in the whole intro, never back to back (jordan 3 round 2, 0:12: four article/StockX pages in a
  row, "too many articles ... it just keeps showing over and over again"). The named site (StockX) first, then one headline
  page. At most 3 lines of the same turntable spin. Never 3 lines in a row from the same kind of source: alternate spin,
  product-camera hands/box, web page, store page, picture, kinetic type.
- No title card at the end: the footage runs under "let's go" and the intro cuts ~1 s later into "hey guys".
- Cover what each line NAMES, not the product over and over (s25 ultra 2026-10-23: "it's too much of the phone"): a place,
  people or action that is not the product (the Chinese factory, workers, a warehouse, a scam) gets stock of THAT; a brand
  named in the line (Samsung, Apple) gets its logo picture; product footage on at most every other line, and his clip of
  the product he compares it to (the iPhone from his other video) for that line. Never "type only" for a line that names
  something showable.
- "In today's video I'm going over X" / "this video" lines show X itself: the product in his hands or being unboxed. Never
  his desk, room, studio setup or a camera test (s25 ultra 2026-10-23, 0:06-0:09: "there's like this random clip there, we
  need something relevant"). Every shot must make sense with the words under it; when nothing fits, use the product.
- The first time the product's name is said, a real photo of it pops (the build adds it); keep footage of the product
  under that line too.

## phone (app / promo-code tutorials)
- CALM AND READABLE beats busy (2026-10-24, his friend on the coupons intro, he agreed: "too much going on ... a lot of random
  zoom, elements aren't on screen long enough for me to read them, numbers keep changing so I'm confused"). One idea per
  line, held long enough to read; NEVER numbers he doesn't say (no invented order totals, fee amounts or coupon values);
  his real clips (his video's pages, his haul footage) before designed cards.
- Designed UI scenes; no blurred screen recordings in intros.
- Phone clips for the reveal/how-to lines, cam clips for the problem lines.
- (dhgate coupons 2026-10-24: "more motion, different things going on ... why is STARTING highlighted, GUYS highlighted") The
  same page never on two lines in a row and at most twice in the intro: alternate his page clips with the designed scenes
  (fees piling onto the total for fee/shipping/tax lines, the shock slam for "surprising", coupons for "save"). A line with
  nothing to show plays its own words as kinetic type; never one random word on a plain background. Highlight only what the
  line is about (money, the app, fees / shipping / codes / free / save), never "guys", "starting", "looked".
- A different app named before "promo codes" in the VO is a slip ("best working Shein promo codes" on a DHgate video): show
  the video's own app (build_intro.app_slip does it).

## gaming (Minecraft lists)
- VO -> literal-metaphor motion graphics; gameplay slots on reveal lines.
- PEOPLE and PLACES he names are context, never skipped (best sp5der hoodie 2026-10-23: "I said places, Atlanta, Decatur,
  Dunwoody ... and Young Thug: why is Young Thug not there? I said a whole person"). The build resolves them on Wikipedia and
  forces a full-frame photo of THAT person / city on their line (it overrides your choice there); plan the lines around them.
- Another reseller's site / vendor-link page ONLY on a line that says other resellers or influencers are bad or never had the
  item in hand. "To see if it's a complete scam", "if the quality is good" are about the product: his own footage there.
- Do not make every shot the same frame style: templates with cards (polaroids, panels) alternate with full-frame shots.
- A photo popped over a text-only (smoke) beat goes away when footage starts. A clip of the compared product (his iPhone)
  starts with the clause that leads to it ("trust me after reviewing the iPhone"), not on the word itself.

- (lv skatesta 2026-10-24, his own published intro was the reference) The retail-price line ("with one of them setting me back around $1000") shows the REAL product with real prices (the StockX page of that product line, tagged "screen recording: StockX page"), never a plain price card or his own desk. The size tag / box label shot ("product detail": LV SKATE SNEAKER 10/44) goes on a reveal / "DHgate alternative" / quality line: it proves the pair he got. One clip of his own B-roll never shows more than twice in one intro; "everything moving" = a different source every shot (his B-roll, product-camera details, the StockX page, his DHgate listing, stock for skating). No multi-coloured comic text.

- (canada goose jacket 2026-10-24, his own published intro CfbrSgFOsWE was the reference: "we need to get better at creating this style") Every shot FULL FRAME, never footage in small cards on a dark wall (R16 Neon Sign Wall was the draft; it read as empty dark frames). His beats, in order: the brand named in the hook = a real campaign photo of someone WEARING the product (city street), the brand name stacked big over it; the retail price = the number huge over that photo; "one of these" = the real retail product cards (several colourways) on a deep purple gradient; "I wanted to check out the DHgate alternative" = word-by-word bold white captions on black, 2-3 words a beat; the quality line = HIS close-ups of the product (badge, patch, label); "watch to the very end ... it'll shock you" = HIM wearing the product (the try-on is the payoff tease). "Watch" in "watch the video to the end" is the verb, never a wristwatch. A new shot every ~1 s.

- (top 5 reselling products spring 2026-10-25) EARNINGS lines show MONEY: "making upwards of $10,000", "turn a profit", "make lots of money" = cash, a payout, a sold listing (build_intro forces a money clip per earnings line, pics.EARN_RE / EARN_STOCK). A product's PRICE line still shows the product (prada cups rule). Never a held-up product that covers his face on a talking line: pick a shot where his face is clear, or B-roll. "Reselling is booming"-type hype lines = the scene itself (a sneaker con, resellers trading, a busy resale event), not the desk or the mic. "The top N items" = the N products of the video in a quick turn.
- (same video) The intro VO starts right on his first word: build_intro.trim_vo_lead trims any lead (clicks, breath) automatically.
- (top 5 reselling products spring 2026-10-25) Top-N intros TEASE the products: the 1..N product reel (review_intro.countdown_footage) blurs every product picture and its name (boxblur 22, settings.countdown_blur; 0 = sharp), only the numbers stay sharp; numbered 1..N in the order he shows them, never a #5..#1 countdown. "People should have to watch to find out."

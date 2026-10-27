window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e;
  const papers = document.getElementById("papers"), full = document.getElementById("full");
  const r = K.rng(I.seed);
  const MAST = ["THE DAILY DROP", "THE RESELL TIMES", "FASHION WEEKLY", "THE HAUL HERALD"];
  // clips that START under a line (a clip spanning several lines belongs to the line it starts on)
  const clipsOf = (ln) => K.slotsIn(ln.s - 0.1, K.end(ln)).filter((s) => s.s >= ln.s - 0.1);
  const showIn = (sl, frame, t0) => {
    const w = K.into(tl, sl, frame);
    if (!w) return;
    w.style.opacity = 0;
    tl.to(w, { opacity: 1, duration: 0.12 }, Math.max(t0 || 0, sl.s));
    tl.set(w, { opacity: 0 }, Math.max(sl.s + 0.1, sl.e + 0.05));
  };
  // spoken dates never print (no dates in graphics): headlines are built from the line's words minus date words
  const lineText = (ln) => I.words.filter((w) => w.s >= ln.s - 0.01 && w.s < ln.e + 0.01 && !w.date).map((w) => w.w).join(" ") || ln.text;
  // The newspaper is an ACCENT, not the whole intro (dhgae prada glasses 2026-10-25: "we use the newspaper too much ...
  // incorporate some full screen B-roll to break this up ... it's just a bit boring"; 0:20 "a lot of this B-roll should've
  // been full screen"). At most two front pages (rick owens: "too many flips"), each <= 2 lines and <= PAGE_MAX s: the
  // opening hook, and one more after >= 2 full-frame lines. Every other line plays its clip FULL FRAME with captions.
  const PAGE_MAX = 4.6;
  // the product in news form, from the title ("dhgae prada glasses" -> "PRADA GLASSES: THE HONEST REVIEW"); no dates
  const prodName = String(I.title || "").split(/\s+/).filter((w) => w && !/^(dh.?g\w*|dhg\w*|review|honest|on|the|best|20\d\d)$/i.test(w)).join(" ");
  const newsHead = prodName ? `${prodName}: THE HONEST REVIEW` : "THE HONEST REVIEW";
  const pre = I.lines.filter((l) => l.s < turn - 0.05 && l.role !== "go");
  const takePage = (from) => {
    const g = [];
    for (let i = from; i < pre.length && g.length < 2; i++) {
      if (K.end(pre[i]) - pre[from].s > PAGE_MAX && g.length) break;
      g.push(pre[i]);
    }
    return g;
  };
  const pages = [];
  if (pre.length) pages.push(takePage(0));
  const afterA = pages.length ? pre.indexOf(pages[0][pages[0].length - 1]) + 1 : 0;
  // the second page: the first line >= 2 lines later that has its own clip (an empty photo box is a black screen)
  for (let i = afterA + 2; i < pre.length - 1; i++) {
    if (clipsOf(pre[i]).length) { pages.push(takePage(i)); break; }
  }
  const onPaper = new Set(pages.flat());
  pages.forEach((grp, k) => {
    const np = K.div("np", papers);
    np.innerHTML = `<div class="mast">${MAST[(k + I.seed) % MAST.length]}</div><div class="strap"><span>SPECIAL EDITION</span><span>No. ${100 + k * 7}</span><span>EXTRA!</span></div>` +
      `<div class="head"></div><div class="body"><div class="pic"><div class="pcol"></div></div><div class="col"></div><div class="col"></div></div>`;
    np.querySelectorAll(".col, .pcol").forEach((c) => { for (let i = 0; i < 26; i++) K.div("ln", c, `width:${70 + r() * 30}%`); });
    const headBox = np.querySelector(".head"), pic = np.querySelector(".pic");
    // the page stays up until the next full-frame clip is in (<= 0.6 s), never a flash of bare smoke between them
    const lineEnd = K.end(grp[grp.length - 1]);
    const nextClip = I.slots.filter((s) => s.s >= lineEnd - 0.05).map((s) => s.s).sort((a, b) => a - b)[0];
    const t = grp[0].s - 0.05, end = nextClip != null && nextClip - lineEnd <= 0.6 ? Math.max(lineEnd, nextClip + 0.06) : lineEnd;
    tl.set(np, { opacity: 1 }, t);
    tl.set(full, { opacity: 0 }, t);   // the page sits on the dark desk, not over the last full-frame shot
    tl.fromTo(np, { scale: 0.05, rotation: -720 + k * 30 }, { scale: 1, rotation: (k % 2 ? 3 : -3), duration: 0.55, ease: "power2.out" }, t);
    tl.to(np, { scale: 1.07, duration: Math.max(0.2, end - t - 0.6), ease: "none" }, t + 0.55);
    tl.set(np, { opacity: 0 }, end);
    tl.set(full, { opacity: 1 }, end);
    // A filler line with no clip ("Okay, so I know it's November, but I had to come on here") is NOT a front page by itself
    // (prada glasses 2026-10-25, 0:01: "this newspaper doesn't make any sense because there's no graphics on it ... it's
    // just a blank newspaper"): such lines share ONE real front page = a news headline of the product, a printed photo
    // (the still of the clip coming next, slow push-in) and an EXCLUSIVE stamp slammed on.
    // Filler = by its WORDS, clip or not (round 2: the director gave "Okay, so I know it's November" a clip and the page still
    // read "OKAY, SO I KNOW IT'S" for 2 s): only on the opening page, only the lines before the first one with a real key
    const firstKey = grp.findIndex((x) => x.key && !x.key_weak);
    const filler = (ln) => k === 0 && (!ln.key || ln.key_weak) && (firstKey < 0 || grp.indexOf(ln) < firstKey);
    let fillHd = null;
    grp.forEach((ln, j) => {
      const ls = j ? ln.s - 0.05 : t, le = K.end(ln);
      if (filler(ln) && fillHd) {   // the front page made by the line before stays up (its end covers this line)
      } else {
        const hd = K.div("hdl", headBox, "opacity:0", K.esc((filler(ln) ? newsHead : K.short(lineText(ln), 6)).toUpperCase()));
        K.fit(hd, 1300, 92, 52);   // a long headline shrinks instead of running off the page ("...BE CHECKING (")
        tl.set(hd, { opacity: 1 }, j ? ls : t + 0.4);
        tl.fromTo(hd, { clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)", duration: 0.28, ease: "power2.out" }, j ? ls : t + 0.4);
        let he = le;   // a run of filler lines keeps one headline
        for (let q = j + 1; filler(ln) && q < grp.length && filler(grp[q]); q++) he = K.end(grp[q]);
        tl.set(hd, { opacity: 0 }, he);
        fillHd = filler(ln) ? hd : null;
      }
      clipsOf(ln).forEach((sl) => showIn(sl, pic, ls));
      if (!clipsOf(ln).length) {
        // never an empty photo box: the still of the next clip, printed, with a slow push-in
        const nx = I.slots.filter((s) => s.s >= ln.s - 0.1 && s.poster).sort((a, b) => a.s - b.s)[0];
        if (nx) {
          const im = K.el("img", { attrs: { src: nx.poster }, style: "position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:0;filter:sepia(.15) contrast(1.12)" }, pic);
          tl.set(im, { opacity: 1 }, ls);
          tl.fromTo(im, { scale: 1.0 }, { scale: 1.12, duration: Math.max(0.3, le - ls), ease: "none" }, ls);
          tl.set(im, { opacity: 0 }, le);
        }
      }
      if (filler(ln) && j === 0) {   // the opening front page always gets its stamp
        const st = K.div("stamp", np, "opacity:0", "EXCLUSIVE");
        tl.fromTo(st, { opacity: 0, scale: 2.6, rotation: -24 }, { opacity: 1, scale: 1, rotation: -12, duration: 0.2, ease: "power4.in" }, t + 0.75);
        tl.fromTo(np, { x: 0 }, { x: 8, duration: 0.05, yoyo: true, repeat: 1 }, t + 0.95);   // the stamp hits the page
      }
      if (ln.key && !ln.key_weak) {
        const hl = K.div("hl", papers, "opacity:0", K.esc(ln.key.toUpperCase()));
        gsap.set(hl, { rotation: -4 });
        hl.style.left = "560px"; hl.style.top = "620px";
        tl.fromTo(hl, { opacity: 0, scaleX: 0, transformOrigin: "0% 50%" }, { opacity: 1, scaleX: 1, duration: 0.22, ease: "power3.out" }, Math.max(ls + 0.35, ln.keyT));
        tl.set(hl, { opacity: 0 }, le);
      }
      if (j) tl.fromTo(np, { y: 0 }, { y: -12, duration: 0.12, yoyo: true, repeat: 1, ease: "power1.inOut" }, ls);
    });
  });
  // the product page (rick owens: "maybe some motion graphics of product page"): only on a line after the turn that names
  // the store, a link or a price, and never on a line knocking other resellers / influencers (prada glasses 0:20: the
  // turn-line fallback put HIS listing card under "they're absolutely lying to you ... complete rubbish", with an empty
  // photo for 1.6 s). Only his own numbers: no price shown when none is known.
  const KNOCK = /influencer|lying|\blie\b|scam|rubbish|trash|wrong path|never had|don'?t want to listen|youtuber|guru|other resellers/i;
  const ppLine = I.lines.find((l) => l.s >= turn - 0.1 && l.role !== "go" && !KNOCK.test(l.text) && /dhgate|store|site|link|price|dollar|\$|cheap|cost/i.test(l.text));
  // every clip live during the card's line (a clip that started on the line before fills the photo from the first frame)
  const ppSlots = ppLine ? K.slotsIn(ppLine.s - 0.05, Math.min(K.end(ppLine), ppLine.s + 4.2)) : [];
  if (ppLine && ppSlots.length) {
    const t = ppLine.s - 0.05, end = Math.min(K.end(ppLine), t + 4.2);
    const pp = K.div("pp", stage, "opacity:0");
    const price = I.product_price ? `US $${Math.round(I.product_price)}` : "";
    pp.innerHTML = `<div class="bar"><i></i><i></i><i></i><span>dhgate.com</span></div><div class="pbody"><div class="shot"></div><div class="info">` +
      `<div class="pt">${K.esc((I.title || "").toUpperCase())}</div><div class="stars">★★★★★<b>4.8</b></div>` +
      (price ? `<div class="pr">${K.esc(price)}</div>` : "") + `<div class="sold">IN STOCK · SHIPS WORLDWIDE</div><div class="btn">ADD TO CART</div></div></div>` +
      `<svg class="cur" viewBox="0 0 24 24"><path d="M3 2l7 19 2.6-7.6L20 11z" fill="#fff" stroke="#111" stroke-width="1.6"/></svg>`;
    const shot = pp.querySelector(".shot"), btn = pp.querySelector(".btn"), cur = pp.querySelector(".cur");
    ppSlots.forEach((sl) => showIn(sl, shot, t));
    tl.set(pp, { opacity: 1 }, t);
    tl.fromTo(pp, { x: 900, rotation: 4, scale: 0.92 }, { x: 0, rotation: 0, scale: 1, duration: 0.45, ease: "back.out(1.4)" }, t);
    tl.to(pp, { scale: 1.04, duration: Math.max(0.3, end - t - 0.5), ease: "none" }, t + 0.45);
    if (price) tl.fromTo(pp.querySelector(".pr"), { scale: 0.4, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.3, ease: "back.out(2)" }, t + 0.55);
    const click = Math.max(t + 0.9, Math.min(end - 0.6, t + 1.6));
    tl.fromTo(cur, { x: 520, y: 420, opacity: 0 }, { x: 0, y: 0, opacity: 1, duration: 0.7, ease: "power2.inOut" }, click - 0.7);
    tl.to(btn, { scale: 0.92, duration: 0.08, yoyo: true, repeat: 1 }, click);
    tl.to(btn, { backgroundColor: "#1fb455", duration: 0.1 }, click + 0.08);
    tl.to(pp, { x: -900, opacity: 0, duration: 0.3, ease: "power2.in" }, end - 0.3);
  }
  // full frame: every clip not printed on a page or in the card, from the first word on (smoke where a line has no clip)
  const paperSlot = (sl) => [...onPaper].some((ln) => clipsOf(ln).includes(sl));
  K.smoke(tl, full, { alpha: 0.4, seed: I.seed, t0: 0 });
  I.slots.filter((s) => !paperSlot(s) && !ppSlots.includes(s)).forEach((sl, n) => {
    const w = K.mount(tl, sl, full, { fade: 0.06 });
    // calm alternating push-in / pull-out (never the same move twice in a row)
    if (w) tl.fromTo(w, { scale: n % 2 ? 1.0 : 1.12 }, { scale: n % 2 ? 1.1 : 1.0, duration: Math.max(0.2, sl.e - sl.s), ease: "none" }, sl.s);
  });
  // captions over the full-frame lines only: no caption on a page (it has its headline) or on top of the card
  const inPaper = (w) => [...onPaper].some((ln) => w.s >= ln.s - 0.05 && w.s < K.end(ln));
  const inCard = (w) => ppLine && ppSlots.length && w.s >= ppLine.s - 1.2 && w.s < K.end(ppLine);
  K.kinetic(tl, I.words.filter((w) => !inPaper(w) && !inCard(w)), { cls: "kin cap", upper: true, chunk: { max: 2, chars: 14 }, enter: "rise",
    pos: (c, i) => ({ left: i % 2 ? 1180 : 760, top: i % 2 ? 640 : 520, align: "center" }) });
  K.flash(tl, turn, "#fff", stage, 0.25);
  K.grain(tl, stage, 0.18, I.seed);
  K.vignette(stage, 0.6);
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE END" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  t1.textContent = I.title || "REVIEW";
  K.fit(t1, 1700, 150, 70);
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));
  tl.fromTo(T, { opacity: 0 }, { opacity: 1, duration: 0.3 }, t0);
  tl.fromTo([T.querySelector(".t0"), t1], { opacity: 0, filter: "brightness(3) blur(10px)" }, { opacity: 1, filter: "brightness(1) blur(0px)", duration: 0.6, stagger: 0.15, ease: "power2.out" }, t0);
};

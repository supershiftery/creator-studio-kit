window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e;
  const pins = document.getElementById("pins"), r = K.rng(I.seed);
  const svg = K.svg(pins, "z-index:5");
  // round 2 (best sp5der hoodie 2026-10-23, b34a9e: "I like the background ... but there's nothing going on, too plain, a lot
  // of space ... not enough full screen clips or product listing ... you can add portions of it", 0:24 / 0:32 "too small in
  // the corner ... we can't have blank spaces"): FULL frame is the default; the corkboard shows only as a big polaroid pair
  // every third shot (each pin ~half the frame, the one before it still pinned beside it), never a lone small card. Named
  // people / places and store pages are always full. The hand-written callout carries the name / the line's THING (a weak
  // key word, "pressed", is left off).
  const spots = [[70, 70], [930, 110]];
  let prev = null, nPin = 0, pinsLeft = [];
  const cap = (sl, ln) => (sl.name || (ln.key_weak ? "" : ln.key) || "").toLowerCase();
  I.slots.forEach((sl, k) => {
    const ln = I.lines[sl.line];
    const tag = String(sl.tag || "");
    const pinIt = !sl.full && !/store|listing/.test(tag) && (k % 5 === 2 || k % 5 === 3) && sl.e - sl.s >= 1.0;
    if (!pinIt) {
      const f = K.div("full", stage, "z-index:40");
      const inn = K.div("in", f);
      K.into(tl, sl, inn);
      const word = cap(sl, ln);
      const c = word ? K.div("fcap", f, "", K.esc(word)) : null;
      const rot = (r() - 0.5) * 14;
      tl.set(f, { opacity: 1 }, sl.s - 0.05);
      tl.fromTo(f, { scale: 0.3, rotation: rot, padding: "60px 60px 200px" }, { scale: 1, rotation: 0, padding: "0px 0px 0px", duration: 0.38, ease: "power3.inOut" }, sl.s - 0.05);
      tl.fromTo(inn, { scale: 1.0 }, { scale: 1.07, duration: Math.max(0.5, sl.e - sl.s), ease: "none" }, sl.s);   // slow push-in, never a still frame
      if (c) tl.fromTo(c, { opacity: 0, x: -60, rotation: -6 }, { opacity: 1, x: 0, rotation: -3, duration: 0.3, ease: "back.out(1.6)" }, sl.s + 0.25);
      tl.to(f, { opacity: 0, scale: 1.06, duration: 0.16, ease: "power2.in" }, sl.e - 0.08);
      pinsLeft = [];
      return;
    }
    const s = spots[nPin++ % spots.length];
    // the first pin of a pair never sits alone on the board: the shot before it is pinned beside it as a still
    if (!pinsLeft.length && k > 0 && I.slots[k - 1].poster) {
      const o = spots[nPin % spots.length];
      const q = K.div("pol big old", pins, `left:${o[0]}px;top:${o[1]}px;z-index:${9 + nPin}`);
      K.el("img", { attrs: { src: I.slots[k - 1].poster }, style: "width:100%;height:100%;object-fit:cover;display:block" }, K.div("in", q));
      K.div("pin", q);
      const pw = cap(I.slots[k - 1], I.lines[I.slots[k - 1].line]);
      if (pw) K.div("cap", q, "", K.esc(pw));
      tl.set(q, { opacity: 1 }, sl.s - 0.05);
      tl.fromTo(q, { scale: 1.2, rotation: 8, y: -60 }, { scale: 1, rotation: 4, y: 0, duration: 0.3, ease: "power3.out" }, sl.s - 0.05);
      pinsLeft = [q];
    }
    const p = K.div("pol big" + (sl.s < turn - 0.1 ? " old" : ""), pins, `left:${s[0]}px;top:${s[1]}px;z-index:${10 + nPin}`);
    const inn = K.div("in", p);
    K.into(tl, sl, inn);
    K.div("pin", p);
    const word = cap(sl, ln);
    if (word) K.div("cap", p, "", K.esc(word));
    const rot = (r() - 0.5) * 10;
    tl.set(p, { opacity: 1 }, sl.s - 0.05);
    tl.fromTo(p, { scale: 1.4, rotation: rot * 3, y: -120 }, { scale: 1, rotation: rot, y: 0, duration: 0.32, ease: "power3.out" }, sl.s - 0.05);
    tl.to(p, { y: 14, rotation: rot * 0.6, duration: Math.max(0.4, sl.e - sl.s), ease: "sine.inOut" }, sl.s + 0.3);
    // the earlier pin of the pair stays beside it while this one plays, then both leave
    pinsLeft.forEach((q) => tl.to(q, { opacity: 0, duration: 0.2 }, sl.e));
    pinsLeft = [p];
    tl.to(p, { opacity: 0, duration: 0.2 }, Math.min(I.dur, sl.e + 2.5));
    if (prev) {
      const pth = K.path(svg, `M ${prev[0] + 480} ${prev[1] + 4} Q ${(prev[0] + s[0]) / 2 + 480} ${Math.max(prev[1], s[1]) + 160} ${s[0] + 480} ${s[1] + 4}`, { color: "#b01515", width: 6 });
      K.draw(tl, pth, sl.s + 0.1, 0.35);
      tl.to(pth, { opacity: 0, duration: 0.2 }, Math.min(I.dur, sl.e + 2.5));
    }
    prev = s;
  });
  K.flash(tl, turn, "#fff", stage, 0.35);
  K.vignette(stage, 0.35);
  K.xp(tl, stage, { top: 40, label: "watch to the very end" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  t1.textContent = I.title || "Review";
  T.querySelector(".t2").textContent = I.sub || "honest review";
  K.fit(t1, 1140, 170, 70);
  const pin = K.div("pin", T.querySelector(".card"), "top:-30px;width:50px;height:50px;margin-left:-25px");
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(T.querySelector(".card"), { scale: 1.4, rotation: -10, y: -200 }, { scale: 1, rotation: -2, y: 0, duration: 0.35, ease: "power3.out" }, t0);
  tl.fromTo(t1, { clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)", duration: 0.7, ease: "none" }, t0 + 0.2);
};

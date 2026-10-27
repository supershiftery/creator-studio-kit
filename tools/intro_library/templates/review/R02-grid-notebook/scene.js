window.PICS_HANDLED = true;
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), page = document.getElementById("page"), desk = document.getElementById("desk"), reveal = document.getElementById("reveal");
  const turn = I.beats.turn, last = I.words[I.words.length - 1].e;
  K.tex("grid.jpg", document.getElementById("paper"));
  K.dust(tl, page, { n: 40, color: "rgba(30,30,30,.35)", seed: I.seed });
  const pen = K.svg(desk);
  // hook: the search bar types the hook's key thing ("LOOKING FOR JACKET")
  const hook = I.lines[0];
  const sb = K.div("search", desk, "", '<div class="mag"></div><div class="q"></div>');
  // the product from the title ("dhgate jordan 3" -> "jordan 3"); else a WHOLE-word noun from the VO (jordan 3 2026-10-23:
  // without word boundaries "ring" matched inside "compaRING" and the bar typed "LOOKING FOR RING")
  const NOUN = /\b(jacket|coat|jeans|shoes|sneakers|watch|hoodie|bag|glasses|sunglasses|chain|ring|tee|shirt)\b/i;
  const prod = String(I.title || "").replace(/\b(dh ?gate|review|reviews|honest|the|best)\b/gi, " ").replace(/\s+/g, " ").trim();
  const noun = (I.lines.find((l) => NOUN.test(l.text)) || hook).text.match(NOUN);
  const q = "looking for " + (prod && prod.length <= 22 ? prod : noun ? noun[0] : (hook.key || "the best one")).toLowerCase();
  K.pop(tl, sb, 0.05, { from: 0.8 });
  K.type(tl, sb.querySelector(".q"), q.toUpperCase(), 0.25, Math.min(1.4, q.length * 0.07), "|");
  K.markerCircle(tl, pen, { x: 960, y: 135, w: 1330, h: 210, t: 1.7, d: 0.5, seed: I.seed });
  // problem lines: printed B&W photos land around the page, a red arrow from the search bar to each
  const spots = [[110, 310, -5], [1010, 330, 4], [560, 290, -2]];
  const probs = I.slots.filter((s) => s.s < turn - 0.05);
  probs.forEach((sl, k) => {
    const p = spots[k % spots.length];
    const ph = K.photo(desk, { x: p[0], y: p[1], w: 800, h: 460, rot: p[2] });
    K.into(tl, sl, ph.inner);
    tl.fromTo(ph.frame, { opacity: 0, scale: 1.25, y: 40 }, { opacity: 1, scale: 1, y: 0, duration: 0.24, ease: "power3.out" }, sl.s);
    tl.to(ph.frame, { opacity: 0, scale: 0.92, duration: 0.15 }, Math.min(turn - 0.05, sl.e - 0.1));
    const hide = Math.min(turn - 0.05, sl.e - 0.1);
    const arr = K.markerArrow(tl, pen, { x1: 960 + (p[0] < 700 ? -260 : p[0] > 900 ? 260 : 0), y1: 225, x2: p[0] + 400, y2: p[1] - 10, t: sl.s + 0.2, d: 0.28, bend: p[0] < 700 ? -70 : 70 });
    tl.to(arr, { opacity: 0, duration: 0.12 }, hide);
    const ln = I.lines[sl.line];
    if (!window.__goog && /\bsad\b|empty/i.test(ln.text) && (window.__goog = 1)) K.googly(tl, desk, { x: p[0] + 300, y: p[1] + 150, size: 100, t0: sl.s + 0.3, t1: hide, seed: k + 3 });
  });
  // the real things the VO names: a printed photo taped to the page, circled in red pen with a handwritten label;
  // logos are stamped on the paper in ink
  I.lines.filter((l) => l.s < turn - 0.05).forEach((ln, k) => {
    (ln.pics || []).slice(0, 1).forEach((p) => {
      const t = Math.max(ln.s, p.t - 0.15), end = Math.min(turn - 0.05, K.end(ln) - 0.05);
      const right = (I.slots.filter((s) => s.s < turn - 0.05).findIndex((s) => s.line === I.lines.indexOf(ln)) % 2) !== 1;
      const x = right ? 1160 : 160, y = 560;
      if (p.kind === "logo") {
        const e = K.el("img", { attrs: { src: p.src }, style: `position:absolute;left:${x}px;top:${y}px;width:560px;height:260px;object-fit:contain;mix-blend-mode:multiply;opacity:0` }, desk);
        tl.fromTo(e, { opacity: 0, scale: 1.8, rotation: -8 }, { opacity: 0.9, scale: 1, rotation: -4, duration: 0.18, ease: "power4.out" }, t);
        tl.to(e, { opacity: 0, duration: 0.12 }, end);
        return;
      }
      const ph = K.photo(desk, { x, y, w: 600, h: 380, rot: right ? 5 : -5 });
      K.el("img", { attrs: { src: p.src }, style: "width:100%;height:100%;object-fit:cover" }, ph.inner);
      tl.fromTo(ph.frame, { opacity: 0, scale: 1.4, rotation: right ? 14 : -14 }, { opacity: 1, scale: 1, rotation: right ? 5 : -5, duration: 0.26, ease: "back.out(1.5)" }, t);
      tl.to(ph.frame, { opacity: 0, duration: 0.12 }, end);
      const c = K.markerCircle(tl, pen, { x: x + 300, y: y + 190, w: 720, h: 520, t: t + 0.25, d: 0.4, seed: k + 9 });
      tl.to(c, { opacity: 0, duration: 0.1 }, end);
      const lab = K.div("", desk, `position:absolute;left:${x + 40}px;top:${y - 90}px;font:700 76px Caveat, cursive;color:#e0201b;opacity:0;white-space:nowrap`, K.esc(p.label));
      tl.fromTo(lab, { opacity: 0, clipPath: "inset(0 100% 0 0)" }, { opacity: 1, clipPath: "inset(0 0% 0 0)", duration: 0.35, ease: "none" }, t + 0.45);
      tl.to(lab, { opacity: 0, duration: 0.1 }, end);
    });
  });
  // after the turn: logos land as white stamps over the colour B-roll
  I.lines.filter((l) => l.s >= turn - 0.05).forEach((ln, k) => (ln.pics || []).filter((p) => p.kind === "logo").slice(0, 1).forEach((p) => {
    const e = K.el("img", { attrs: { src: p.src }, style: `position:absolute;left:${k % 2 ? 1120 : 140}px;top:120px;width:660px;height:260px;object-fit:contain;filter:grayscale(1) invert(1) contrast(1.6);mix-blend-mode:screen;opacity:0;z-index:30` }, stage);
    tl.fromTo(e, { opacity: 0, scale: 1.6 }, { opacity: 0.95, scale: 1, duration: 0.2, ease: "power3.out" }, Math.max(ln.s, p.t - 0.1));
    tl.to(e, { opacity: 0, duration: 0.15 }, K.end(ln) - 0.1);
  }));
  tl.to(pen, { opacity: 0, duration: 0.15 }, turn - 0.2);
  tl.to(sb, { opacity: 0, duration: 0.15 }, turn - 0.2);
  // captions: ink on paper before the turn, white on footage after
  K.kinetic(tl, I.words.filter((w) => w.s < turn - 0.02), { cls: "kin ink", lower: true, chunk: { max: 2, chars: 14 },
    pos: (c, i) => ({ left: 110, top: 950, align: "left" }) });
  // the turn: the page flips up and away, full-colour B-roll underneath
  tl.to(page, { y: -1180, rotation: -4, duration: 0.42, ease: "power3.in" }, turn - 0.28);
  I.slots.filter((s) => s.s >= turn - 0.05).forEach((sl) => {
    const w = K.mount(tl, sl, reveal, { fade: 0.06 });
    if (w) tl.fromTo(w, { scale: 1.02 }, { scale: 1.1, duration: Math.max(0.2, sl.e - sl.s), ease: "none" }, sl.s);
  });
  K.kinetic(tl, I.words.filter((w) => w.s >= turn - 0.02), { cls: "kin lite", lower: true, chunk: { max: 2, chars: 12 }, until: (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05)) + 0.2, enter: (c) => (c.key ? "slam" : "pop"),
    pos: () => ({ left: 960, top: 860, align: "center" }) });
  K.grain(tl, stage, 0.12, I.seed);
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE VERY END" });
  // title back on fresh grid paper, last word circled in red
  const T = document.getElementById("title");
  K.tex("grid.jpg", document.getElementById("paper2"));
  const t1 = T.querySelector(".t1"), t2 = T.querySelector(".t2");
  t1.textContent = I.title || "THE REVIEW";
  t2.textContent = I.sub || "honest review";
  K.fit(t1, 1640, 140, 70);
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));
  tl.fromTo(T, { opacity: 1, y: 1080 }, { y: 0, duration: 0.4, ease: "power3.out", immediateRender: false }, t0);
  tl.set(T, { opacity: 0 }, 0);
  tl.set(T, { opacity: 1 }, t0);
  const pen2 = K.svg(T);
  const tw = Math.min(1640, t1.scrollWidth);
  K.markerCircle(tl, pen2, { x: 960, y: 500, w: tw + 120, h: 230, t: t0 + 0.45, d: 0.5, seed: I.seed + 2 });
  K.scribble(tl, pen2, { x: 960 - tw / 2, y: 640, w: tw * 0.55, t: t0 + 0.9, n: 2 });
  tl.fromTo(t2, { opacity: 0 }, { opacity: 1, duration: 0.3 }, t0 + 0.7);
};

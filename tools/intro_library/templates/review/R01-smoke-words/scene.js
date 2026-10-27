window.PICS_HANDLED = true;
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), foot = document.getElementById("foot"), fx = document.getElementById("fx");
  const turn = I.beats.turn;
  K.smoke(tl, document.getElementById("bg"), { alpha: 0.55, seed: I.seed });
  // footage: full-frame, slow push-in; problem lines play desaturated, the reveal in colour
  // more motion (s25 ultra 2026-10-23: "lacking a little bit of movement and just motion"): every shot PUNCHES in (fast
  // scale-down from 1.22 with a short motion blur), then drifts slowly, alternating left/right pans and push-in/pull-out,
  // so no two shots in a row move the same way. Smooth eases only: no shake ("we should not be shaking the camera as much")
  // calmer again (reselling spreadsheet 2026-10-23: "shaking the screen every 3 seconds ... B-roll to B-roll just looks too
  // jarring"): no punch-in, no sideways jump, no blur. Each shot dissolves in over the last one (0.3 s) and glides for its
  // whole length, alternating push-in / pull-out and left / right so the motion still never repeats. The flash pins stay.
  // ON TIME and SMOOTH (watch spreadsheet 2026-10-24): round 1 "popping up too late" (a 0.3 s dissolve that STARTED on the
  // word); round 2 a 0.1 s cut-in fixed the timing but "everything is just kind of spawning in ... popping out at you ...
  // a little bit shaky": so the soft 0.3 s dissolve is back, started 0.27 s early so it is complete as he says the word,
  // and the calm glide (24 px, 1.05-1.13, linear) is back. Shot lengths are unchanged.
  I.slots.forEach((sl, k) => {
    const s0 = Math.max(0, sl.s - (sl.lead != null ? sl.lead : 0.27));   // = template.json lead (the video starts then too)
    const w = K.mount(tl, Object.assign({}, sl, { s: s0 }), foot, { fade: sl.s < 0.3 ? 0.06 : 0.3, hold: 0.32 });
    if (!w) return;
    const ln = I.lines[sl.line];
    w.style.filter = "saturate(1.12) contrast(1.05)";   // colour only (user: no black-and-white footage)
    const dur = Math.max(0.3, sl.e - s0 + 0.3), dir = k % 2 ? -1 : 1, pull = k % 2 === 1;
    tl.fromTo(w, { scale: pull ? 1.13 : 1.05, x: 24 * dir }, { scale: pull ? 1.05 : 1.13, x: -24 * dir, duration: dur, ease: "none" }, s0);
  });
  // the literal things: real photos as tilted print cutouts, logos as white stamps, otherwise an emoji sticker
  const pics = document.getElementById("pics");
  const side = {};
  I.lines.forEach((ln, i) => {
    const end = K.end(ln), lineEnd = end;
    const left = i % 2 === 1;
    (ln.pics || []).forEach((p, j) => {
      const t = Math.max(ln.s, p.t - 0.12);
      // a photo that pops over the smoke (no footage under it) leaves WITH the smoke, when the first footage comes in: it
      // never rides over the B-roll (s25 ultra 2026-10-23, 0:01: "it should have cut at once with the smoke ... we don't
      // want to carry that graphic over to the B-roll")
      const onSmoke = !I.slots.some((sl) => sl.s <= t + 0.05 && sl.e > t + 0.05);
      const nextSlot = I.slots.filter((sl) => sl.s > t).sort((a, b) => a.s - b.s)[0];
      const end = onSmoke && nextSlot && nextSlot.s < lineEnd ? nextSlot.s - 0.02 : lineEnd;   // exit done as the footage cuts in
      // never a photo card OVER footage (watch spreadsheet 2026-10-24, "tens of thousands": a Rolex photo card over a DHgate
      // watch listing, "why would you put a picture of a watch over a listing of a watch? Does that make any sense?"): the
      // footage already shows it. Cards only on the smoke beats.
      if (!onSmoke && p.kind !== "logo") return;
      if (p.kind === "logo") {
        const e = K.el("img", { cls: "logo", attrs: { src: p.src } }, pics);
        e.style.left = (left ? 140 : 1080) + "px"; e.style.top = 300 + j * 40 + "px";
        tl.fromTo(e, { opacity: 0, scale: 1.6 }, { opacity: 0.95, scale: 1, duration: 0.22, ease: "power3.out" }, t);
        tl.to(e, { opacity: 0, duration: 0.15 }, end - 0.1);
      } else {
        const c = K.div("cut", pics, `left:${left ? 120 : 1020}px;top:${150 + j * 70}px`);
        K.el("img", { attrs: { src: p.src } }, c);
        K.div("lab", c, "", K.esc(p.label));
        tl.set(c, { opacity: 1 }, t);
        tl.fromTo(c, { rotation: left ? -16 : 16, scale: 1.5, y: 80 }, { rotation: left ? -4 : 4, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.6)" }, t);
        tl.to(c, { rotation: left ? -2 : 2, y: -14, duration: Math.max(0.3, end - t - 0.4), ease: "sine.inOut" }, t + 0.3);
        tl.to(c, { opacity: 0, x: left ? -260 : 260, duration: 0.2, ease: "power2.in" }, end - 0.18);
      }
      side[i] = left ? "right" : "left";
    });
    if (!(ln.pics || []).length && ln.icon && ln.role !== "go") {
      const e = K.sticker(pics, `<div class="emo-in">${ln.icon}</div>`, `left:${i % 2 ? 260 : 1460}px;top:${240 + (i % 3) * 30}px;opacity:0`);
      const t = Math.max(ln.s, ln.keyT - 0.1);
      tl.fromTo(e, { opacity: 0, scale: 0.2, rotation: -30 }, { opacity: 1, scale: 1, rotation: i % 2 ? -8 : 8, duration: 0.3, ease: "back.out(2.4)" }, t);
      tl.to(e, { y: -20, duration: Math.max(0.3, end - t - 0.4), ease: "sine.inOut" }, t + 0.3);
      tl.to(e, { opacity: 0, scale: 0.6, duration: 0.15 }, end - 0.15);
    }
  });
  K.grain(tl, stage, 0.2, I.seed);
  K.vignette(stage, 0.7);
  // word-by-word captions; on footage they sit low-centre, on smoke they wander between thirds (never on a picture's side)
  const spots = [[560, 430, "center"], [1340, 520, "center"], [960, 600, "center"], [300, 380, "left"], [1620, 640, "right"], [960, 420, "center"]];
  const last = I.words[I.words.length - 1].e;
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));   // title time: every caption clears before it
  K.kinetic(tl, I.words, {
    cls: "kin", chunk: { max: 2, chars: 12 }, lower: true, until: t0,
    enter: (c) => (c.key ? "slam" : "pop"),
    pos: (c, i) => {
      const li = I.lines.indexOf(K.lineAt(c.s));
      if (side[li] === "right") return { left: 1420, top: 760 - (i % 2) * 120, align: "center" };
      if (side[li] === "left") return { left: 500, top: 760 - (i % 2) * 120, align: "center" };
      const on = K.slotsIn(c.s, c.s + 0.05).length > 0;
      if (on) return { left: 960, top: 840, align: "center" };
      const p = spots[(i * 7 + (I.seed % 5)) % spots.length];
      return { left: p[0], top: p[1], align: p[2] };
    },
  });
  // turn line: white flash through the smoke
  K.flash(tl, turn, "#fff", fx, 0.28);
  K.xp(tl, stage, { top: 930, label: "WATCH TO THE END" });
  // title: "DHGATE MONCLER" with the brand word in green, tracked in from wide
  const T = document.getElementById("title"), t1 = T.querySelector(".t1"), bar = T.querySelector(".bar"), t2 = T.querySelector(".t2");
  const words = K.titleWords();
  t1.innerHTML = words.map((w, i) => (i === words.length - 1 ? "<b>" + K.esc(w) + "</b>" : K.esc(w))).join(" ");
  t2.textContent = I.sub || "REVIEW";
  K.fit(t1, 1700, 150, 70);
  tl.fromTo(T, { opacity: 0 }, { opacity: 1, duration: 0.25 }, t0);
  tl.fromTo(t1, { letterSpacing: "60px", opacity: 0, filter: "blur(16px)" }, { letterSpacing: "22px", opacity: 1, filter: "blur(0px)", duration: 0.7, ease: "power3.out" }, t0);
  tl.to(bar, { width: 520, duration: 0.45, ease: "power3.out" }, t0 + 0.35);
  tl.fromTo(t2, { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.35 }, t0 + 0.5);
  tl.to(T, { opacity: 0, duration: 0.3 }, I.dur - 0.3);
};

window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e;
  const foot = document.getElementById("foot"), vhs = document.getElementById("vhs"), hud = document.getElementById("hud");
  I.slots.forEach((sl) => {
    const w = K.mount(tl, sl, foot, { fade: 0.04 });
    if (!w) return;
    if (sl.s < turn - 0.1) w.classList.add("bw");
    // handheld wobble
    tl.fromTo(w, { x: 0, y: 0, rotation: 0 }, { x: 10, y: -6, rotation: 0.4, duration: Math.max(0.2, sl.e - sl.s), ease: "sine.inOut" }, sl.s);
  });
  // tracking bands rolling down, a few at a time
  const r = K.rng(I.seed);
  for (let i = 0; i < 6; i++) {
    const b = K.div("band", vhs);
    const t = r() * (I.dur - 2);
    tl.fromTo(b, { y: -80, opacity: 0.9 }, { y: 1100, duration: 1.4 + r(), ease: "none", immediateRender: false }, t);
    tl.set(b, { opacity: 0 }, 0);
  }
  // REC blink + tape counter (no dates, only running time)
  const dot = hud.querySelector(".rec i");
  tl.to(dot, { opacity: 0, duration: 0.01, yoyo: true, repeat: Math.floor(I.dur / 0.5) * 2 - 1, repeatDelay: 0.49 }, 0);
  const ctr = hud.querySelector(".ctr"), c = { v: 0 };
  const fmt = () => {
    const t = tl.time(), f = t < turn - 0.5 ? 0 : t > turn ? 1 : Math.pow((t - turn + 0.5) / 0.5, 2);
    const s = Math.floor(12 + t + f * 600); ctr.textContent = `0:${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`; };
  tl.to(c, { v: I.dur, duration: I.dur, ease: "none", onUpdate: fmt }, 0);
  // fast-forward into the turn
  const ff = hud.querySelector(".ff");
  tl.set(ff, { opacity: 1 }, turn - 0.5);
  tl.set(ff, { opacity: 0 }, turn);
  tl.fromTo(foot, { skewX: 0 }, { skewX: 12, duration: 0.25, yoyo: true, repeat: 1, ease: "power2.inOut" }, turn - 0.5);
  K.flash(tl, turn, "#fff", stage, 0.15);
  K.kinetic(tl, I.words, { cls: "kin vcr", upper: true, chunk: { max: 2, chars: 14 }, pos: (c, i) => ({ left: 960, top: 760, align: "center" }) });
  K.xp(tl, stage, { top: 900, label: "WATCH TO THE END" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  t1.textContent = I.title || "REVIEW";
  T.querySelector(".t2").textContent = "TAPE 01 · " + (I.sub || "REVIEW").toUpperCase();
  K.fit(t1, 1280, 130, 50);
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(T.querySelector(".label"), { y: 700, rotation: 6 }, { y: 0, rotation: -2, duration: 0.4, ease: "power3.out" }, t0);
};

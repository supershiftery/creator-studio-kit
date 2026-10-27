window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e;
  const board = document.getElementById("board"), signs = document.getElementById("signs");
  const r = K.rng(I.seed);
  // neon flicker-on: a few seeded off/on blinks, then steady with a faint hum wobble
  const flick = (el, t, on) => {
    const seq = [0.05, 0.04, 0.07, 0.03, 0.09];
    let tt = t;
    seq.forEach((d, i) => { tl.set(el, { opacity: i % 2 ? 0.15 : on }, tt); tt += d + r() * 0.03; });
    tl.set(el, { opacity: on }, tt);
    return tt;
  };
  tl.fromTo(board, { opacity: 0 }, { opacity: 1, duration: 0.3 }, 0.1);
  I.slots.forEach((sl) => K.mount(tl, sl, board.querySelector(".in"), { fade: 0.08 }));
  I.lines.filter((l) => l.role !== "go").forEach((ln, k) => {
    const txt = ln.key || K.short(ln.text, 2);
    const e = K.div("neon" + (txt.length > 10 ? " sm" : ""), signs, "", K.esc(txt));
    e.style.setProperty("--nc", ln.s < turn ? (ln.money || /neg/.test((K.lineWords(ln).find((w) => w.k) || {}).c || "") ? "#ff2e63" : "#ff2e63") : I.accent);
    K.fit(e, 1800, txt.length > 10 ? 110 : 150, 50);
    const t = Math.max(ln.s, ln.keyT - 0.15);
    flick(e, t, 1);
    tl.set(e, { opacity: 0 }, K.end(ln) - 0.02);
  });
  // the turn: the board shorts out with a sputter
  [0, 0.05, 0.1, 0.18].forEach((d, i) => tl.set(board, { opacity: i % 2 ? 1 : 0.1 }, turn - 0.25 + d));
  tl.set(board, { opacity: 1 }, turn);
  K.flash(tl, turn, "#ff9ec0", stage, 0.25);
  K.grain(tl, stage, 0.12, I.seed);
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE END" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  t1.textContent = I.title || "REVIEW";
  T.querySelector(".t2").textContent = I.sub || "review";
  K.fit(t1, 1760, 160, 60);
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));
  tl.to(board, { opacity: 0, duration: 0.2 }, t0 - 0.1);
  tl.set(T, { opacity: 1 }, t0);
  tl.set([T.querySelector(".t0"), t1, T.querySelector(".t2")], { opacity: 0 }, t0);
  flick(T.querySelector(".t0"), t0, 1);
  flick(t1, t0 + 0.2, 1);
  flick(T.querySelector(".t2"), t0 + 0.6, 1);
};

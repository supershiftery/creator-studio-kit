// THEME over the phone scene bank: night-mode brand world with drifting bokeh; a persistent app icon top-right whose red
window.CAMERA = { intensity: 1.3 };
// notification badge climbs on every problem line and flips to a green check after the turn; title with the real icon.
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e, app = K.app();
  const r = K.rng(I.seed);
  for (let i = 0; i < 12; i++) {
    const s = 120 + r() * 300, b = K.div("bk", document.getElementById("bokeh"), `left:${r() * 1920}px;top:${r() * 1080}px;width:${s}px;height:${s}px`);
    tl.fromTo(b, { y: 0, opacity: 0.3 + r() * 0.5 }, { y: -120 - r() * 200, duration: I.dur, ease: "none" }, 0);
  }
  const d = K.director(tl, { cut: "none" });
  // frame device: the app icon + notification badge
  const fr = document.getElementById("badge");
  K.appIcon(fr, 120, "box-shadow:0 12px 30px rgba(0,0,0,.45)");
  const bd = K.div("bd", fr, "", "0");
  tl.fromTo(fr, { scale: 0, rotation: -30 }, { scale: 1, rotation: 0, duration: 0.35, ease: "back.out(2.4)" }, 0.2);
  const pre = I.lines.filter((l) => l.s < turn - 0.05);
  pre.forEach((ln, k) => {
    K.text(tl, bd, Math.max(ln.s, ln.keyT), String((k + 1) * 3));
    tl.fromTo(bd, { scale: 1.7 }, { scale: 1, duration: 0.2, ease: "back.out(3)" }, Math.max(ln.s, ln.keyT));
    tl.fromTo(fr, { rotation: -10 }, { rotation: 0, duration: 0.3, ease: "elastic.out(1.2,0.4)" }, Math.max(ln.s, ln.keyT));
  });
  K.text(tl, bd, turn + 0.1, "✓");
  tl.to(bd, { backgroundColor: "#1fbf5f", duration: 0.1 }, turn + 0.1);
  K.xp(tl, stage, { top: 980, label: "WATCH TO THE END" });
  // title
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  K.appIcon(document.getElementById("ticon"), 200, "box-shadow:0 20px 50px rgba(0,0,0,.45)");
  t1.textContent = (I.title || app.name).toUpperCase();
  K.fit(t1, 1400, 190, 90);
  const t0 = Math.max(last + 0.05, (I.beats.go || last) - 0.1);
  tl.to(fr, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  tl.fromTo(T, { opacity: 0, scale: 1.3 }, { opacity: 1, scale: 1, duration: 0.3, ease: "power4.out" }, t0);
  tl.fromTo(T.querySelector(".pill"), { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.3, ease: "back.out(2)" }, t0 + 0.3);
  K.wipe(tl, I.dur - 0.6);
};

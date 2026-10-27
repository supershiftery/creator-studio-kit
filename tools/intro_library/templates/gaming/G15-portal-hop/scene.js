// THEME over the gaming scene bank: Portal Hop. Every scene is seen through a nether portal.
window.CAMERA = { intensity: 1.2 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");
  tl.fromTo(bg, { rotation: 0 }, { rotation: 90, duration: I.dur, ease: "none" }, 0);
  K.embers(tl, bg, { n: 40, color: "#c56cff", seed: I.seed });
  const d = K.director(tl, { cut: "flash" });
  K.div("ob", frame);
  lines.forEach((ln) => { const s = K.div("sw", frame); tl.set(s, { opacity: 0.9 }, Math.max(0, ln.s - 0.12)); tl.fromTo(s, { rotation: 0, scale: 0.6 }, { rotation: 140, scale: 1.2, duration: 0.3, ease: "power2.out" }, Math.max(0, ln.s - 0.12)); tl.set(s, { opacity: 0 }, ln.s + 0.2); });
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));

  const big = [K.pix3d(words, ps, ["#f3d1ff", "#c56cff", "#7a22c2"], "#2a0a4a", Math.round(ps * 1.4), T)];
  if (I.sub) big.push(K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#eeeeee", "#cfcfcf"], "#222222", Math.round(ps * 0.6), T));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(big, { opacity: 0, scale: 0.2, y: 80 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0 + 0.0);

  K.shake(tl, stage, t0 + 0.0 + 0.05, 18, 0.3);
  K.vignette(stage, 0.6);
};

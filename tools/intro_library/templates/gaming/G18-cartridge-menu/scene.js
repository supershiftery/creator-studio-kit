// THEME over the gaming scene bank: Retro Cartridge. An 8-bit console select screen.
window.CAMERA = { intensity: 1.0 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");
  const r = K.rng(I.seed); for (let i = 0; i < 5; i++) { const c = K.div("cl", bg, `left:${r() * 1700}px;top:${80 + r() * 600}px`); tl.fromTo(c, { x: 0 }, { x: -300 - r() * 300, duration: I.dur, ease: "none" }, 0); }
  const d = K.director(tl, { cut: "pixel" });
  const mn = K.div("mn", frame); const items = lines.slice(0, 7).map((ln) => { const e = K.div("", mn, "position:relative"); K.pixo((ln.key || "???").toUpperCase().slice(0, 14), 4, "#ffffff", { outline: 0, shadow: 0 }, e); return e; });
  const cur = K.div("", mn, "position:absolute;left:18px;top:20px"); K.pixo(">", 5, "#ffe14a", { outline: 0, shadow: 0 }, cur);
  lines.slice(0, 7).forEach((ln, k) => tl.to(cur, { y: k * (28 + 18), duration: 0.08, ease: "steps(1)" }, ln.s));
  tl.to(cur, { opacity: 0, duration: 0.01, yoyo: true, repeat: Math.floor(I.dur / 0.5), repeatDelay: 0.24 }, 0);
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));
  const ps2 = K.pixo("PRESS START", 8, ["#ffffff", "#dddddd"], {}, T);
  const big = [K.pix3d(words, ps, ["#fff7a8", "#ffe14a", "#ff7b00"], "#7a1f00", Math.round(ps * 1.4), T)];
  if (I.sub) big.push(K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#eeeeee", "#cfcfcf"], "#222222", Math.round(ps * 0.6), T));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(big, { opacity: 0, scale: 0.2, y: 80 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0 + 0.0);
  tl.fromTo(ps2, { opacity: 0 }, { opacity: 1, duration: 0.01, yoyo: true, repeat: 9, repeatDelay: 0.18 }, t0 + 0.5);
  K.shake(tl, stage, t0 + 0.0 + 0.05, 18, 0.3);
  K.vignette(stage, 0.35);
};

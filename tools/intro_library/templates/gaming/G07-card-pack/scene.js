// THEME over the gaming scene bank: Trading Card Pack. The whole frame is a holographic trading card.
window.CAMERA = { intensity: 1.15 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");
  tl.fromTo(bg, { backgroundPosition: "0% 50%" }, { backgroundPosition: "100% 50%", duration: I.dur, ease: "none" }, 0);
  const d = K.director(tl, { cut: "flash" });
  K.div("bd", frame);
  [[40, 40], [1824, 40], [40, 984], [1824, 984]].forEach((p) => K.div("gem", frame, `left:${p[0] - 28}px;top:${p[1] - 28}px`));
  const ct = K.div("ct", frame);
  lines.forEach((ln, k) => { const e = K.div("", ct, "position:absolute;opacity:0"); K.pixo("CARD " + (k + 1) + "/" + lines.length, 4, "#fff2b0", { outline: 0, shadow: 4, shadowColor: "#5a4000" }, e); tl.set(e, { opacity: 1 }, ln.s); tl.set(e, { opacity: 0 }, K.end(ln)); const f = K.div("foil", frame); tl.fromTo(f, { opacity: 1, xPercent: -100 }, { xPercent: 100, duration: 0.5, ease: "power2.inOut", immediateRender: false }, ln.s); tl.set(f, { opacity: 0 }, 0); });
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));
  const r = K.pixo("ULTRA RARE", 7, ["#ffffff", "#ffe9a6"], {}, T);
  const big = [K.pix3d(words, ps, ["#fffbe0", "#ffd700", "#d49a00"], "#5a3a00", Math.round(ps * 1.4), T)];
  if (I.sub) big.push(K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#eeeeee", "#cfcfcf"], "#222222", Math.round(ps * 0.6), T));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(big, { opacity: 0, scale: 0.2, y: 80 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0 + 0.2);
  tl.fromTo(r, { opacity: 0, y: -40 }, { opacity: 1, y: 0, duration: 0.3 }, t0);
  K.shake(tl, stage, t0 + 0.2 + 0.05, 18, 0.3);
  K.vignette(stage, 0.5);
};

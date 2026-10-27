// THEME over the gaming scene bank: Breaking News. A pixel news broadcast.
window.CAMERA = { intensity: 1.05 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");

  const d = K.director(tl, { cut: "flash" });
  const lt = K.div("lt", frame); const bk = K.div("bk", lt); K.pixo("BREAKING", 6, "#fff", { outline: 0, shadow: 0 }, bk); const hl = K.div("hl", lt);
  lines.forEach((ln) => { const e = K.div("", hl, "position:absolute;left:30px;top:30px;opacity:0"); K.pixo((ln.key || K.short(ln.text, 3)).toUpperCase().slice(0, 26), 8, "#0a1a4a", { outline: 0, shadow: 0 }, e); tl.set(e, { opacity: 1 }, ln.s); tl.fromTo(e, { y: 60 }, { y: 0, duration: 0.2, ease: "power3.out" }, ln.s); tl.set(e, { opacity: 0 }, K.end(ln)); });
  const tk = K.div("tk", frame); const tt = K.div("", tk, "", (I.lines.map((l) => (l.key || "").toUpperCase()).filter(Boolean).join("   +++   ") + "   +++   ").repeat(3)); tl.fromTo(tt, { x: 1920 }, { x: -3000, duration: I.dur, ease: "none" }, 0);
  const lg = K.div("logo", frame); K.pixo("SMC NEWS", 5, "#fff", { outline: 0, shadow: 0 }, lg);
  K.xp(tl, stage, { top: 880, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));

  const big = [K.pix3d(words, ps, ["#ffffff", "#ffe9a6", "#ffc23a"], "#0a1a4a", Math.round(ps * 1.4), T)];
  if (I.sub) big.push(K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#eeeeee", "#cfcfcf"], "#222222", Math.round(ps * 0.6), T));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(big, { opacity: 0, scale: 0.2, y: 80 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0 + 0.0);

  K.shake(tl, stage, t0 + 0.0 + 0.05, 18, 0.3);
  K.vignette(stage, 0.4);
};

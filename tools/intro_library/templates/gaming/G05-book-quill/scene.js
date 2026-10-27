// THEME over the gaming scene bank: Book & Quill. An open book on a wooden desk frames every scene.
window.CAMERA = { intensity: 1.0 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");

  const d = K.director(tl, { cut: "flash" });
  K.div("pg", frame, "left:40px;top:40px;width:1840px;height:1000px;border-radius:16px");
  K.div("spine", frame);
  const pn = K.div("", frame, "position:absolute;left:0;right:0;bottom:56px;display:flex;justify-content:center");
  lines.forEach((ln, k) => { const e = K.div("", pn, "position:absolute;opacity:0"); K.pixo("- " + (k + 1) * 2 + " -", 4, "#7a5a2a", { outline: 0, shadow: 0 }, e); tl.set(e, { opacity: 1 }, ln.s); tl.set(e, { opacity: 0 }, K.end(ln)); });
  lines.forEach((ln) => { const c = K.div("", frame, "position:absolute;right:40px;top:40px;width:0;height:0;border-style:solid;border-width:0 0 0 0;border-color:transparent transparent #d8c79c transparent"); tl.fromTo(c, { borderWidth: "0 0 0 0" }, { borderWidth: "0 0 220px 220px", duration: 0.12, yoyo: true, repeat: 1, ease: "power2.in" }, Math.max(0.1, ln.s - 0.16)); });
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));

  const big = [K.pix3d(words, ps, ["#ffe9b0", "#e3b04b", "#a8701c"], "#3a2200", Math.round(ps * 1.4), T)];
  if (I.sub) big.push(K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#eeeeee", "#cfcfcf"], "#222222", Math.round(ps * 0.6), T));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(big, { opacity: 0, scale: 0.2, y: 80 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0 + 0.0);

  K.shake(tl, stage, t0 + 0.0 + 0.05, 18, 0.3);
  K.vignette(stage, 0.55);
};

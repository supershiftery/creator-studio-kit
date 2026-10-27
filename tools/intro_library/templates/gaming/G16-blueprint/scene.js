// THEME over the gaming scene bank: Blueprint. An architect's blueprint.
window.CAMERA = { intensity: 1.0 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");

  const d = K.director(tl, { cut: "pixel" });
  const tb = K.div("tb", frame); const nm = K.div("", tb, "position:relative;height:40px"); const sh = K.div("", tb, "position:relative;height:28px");
  const svg = K.svg(frame);
  lines.forEach((ln, k) => { const a = K.div("", nm, "position:absolute;opacity:0"); K.pixo((ln.key || "PLAN").toUpperCase().slice(0, 16), 5, "#fff", { outline: 0, shadow: 0 }, a); const b = K.div("", sh, "position:absolute;opacity:0"); K.pixo("SHEET " + (k + 1) + " OF " + lines.length, 3, "#bfe6ff", { outline: 0, shadow: 0 }, b); tl.set([a, b], { opacity: 1 }, ln.s); tl.set([a, b], { opacity: 0 }, K.end(ln)); const y = 120 + (k % 3) * 60; const p = K.path(svg, `M 80 ${y} L 80 ${y + 40} M 80 ${y + 20} L 700 ${y + 20} M 700 ${y} L 700 ${y + 40}`, { color: "#ffffff", width: 4 }); K.draw(tl, p, ln.s + 0.1, 0.4); tl.to(p, { opacity: 0, duration: 0.1 }, K.end(ln)); });
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));

  const big = [K.pix3d(words, ps, ["#ffffff", "#e6f4ff", "#bfe6ff"], "#0a2a5a", Math.round(ps * 1.4), T)];
  if (I.sub) big.push(K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#eeeeee", "#cfcfcf"], "#222222", Math.round(ps * 0.6), T));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(big, { opacity: 0, scale: 0.2, y: 80 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0 + 0.0);

  K.shake(tl, stage, t0 + 0.0 + 0.05, 18, 0.3);
  K.vignette(stage, 0.45);
};

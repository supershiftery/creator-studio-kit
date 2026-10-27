// THEME over the gaming scene bank: The Vote. An election-night mob-vote world.
window.CAMERA = { intensity: 1.1 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");

  const d = K.director(tl, { cut: "whip" });
  const vb = K.div("vb", frame), a = K.div("a", vb, "width:50%"); K.div("b", vb);
  const l1 = K.div("lb", frame, "left:180px"), l2 = K.div("lb", frame, "right:180px"); K.pixo("FEATURED", 5, ["#ffe56b", "#ffb300"], {}, l1); K.pixo("UNDERRATED", 5, ["#9df5ff", "#3fd0ff"], {}, l2);
  lines.forEach((ln, k) => tl.to(a, { width: (ln.s < turn ? 55 + k * 7 : Math.max(18, 75 - (k + 1) * 9)) + "%", duration: 0.45, ease: "power3.out" }, ln.s + 0.1));
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));

  const big = [K.pix3d(words, ps, ["#e6fbff", "#9df5ff", "#3fd0ff"], "#0d3a55", Math.round(ps * 1.4), T)];
  if (I.sub) big.push(K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#eeeeee", "#cfcfcf"], "#222222", Math.round(ps * 0.6), T));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(big, { opacity: 0, scale: 0.2, y: 80 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0 + 0.0);

  K.shake(tl, stage, t0 + 0.0 + 0.05, 18, 0.3);
  K.vignette(stage, 0.5);
};

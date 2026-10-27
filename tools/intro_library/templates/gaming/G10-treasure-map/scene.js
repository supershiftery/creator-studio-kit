// THEME over the gaming scene bank: Treasure Map. An aged parchment map behind every scene; a red dotted trail walks across the map one step per line with a little pixel explorer, a compass rose top-right spins to a new heading on every cut, and the X is dug up on the title..
window.CAMERA = { intensity: 1.0 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");
  K.tex("paper.jpg", bg);
  K.dust(tl, bg, { n: 50, seed: I.seed });
  const d = K.director(tl, { cut: "flash" });
  const cmp = K.div("cmp", frame, "", "<i></i>");
  const svg = K.svg(frame);
  let px = 160, py = 980;
  lines.forEach((ln, k) => { tl.to(cmp, { rotation: (k % 2 ? -1 : 1) * (40 + k * 25), duration: 0.4, ease: "back.out(2)" }, ln.s); const nx = 160 + (k + 1) * (1600 / lines.length), ny = 980 - (k % 2) * 40; const p = K.path(svg, `M ${px} ${py} L ${nx} ${ny}`, { color: "#b3261e", width: 8 }); p.setAttribute("stroke-dasharray", "4 20"); tl.fromTo(p, { opacity: 0 }, { opacity: 1, duration: 0.3 }, ln.s); px = nx; py = ny; });
  const x = K.div("", frame, `position:absolute;left:${px - 30}px;top:${py - 40}px`); K.pixo("X", 12, "#b3261e", { outline: 0, shadow: 6 }, x);
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));

  const big = [K.pix3d(words, ps, ["#fff3d0", "#e3b04b", "#a8701c"], "#3a2200", Math.round(ps * 1.4), T)];
  if (I.sub) big.push(K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#eeeeee", "#cfcfcf"], "#222222", Math.round(ps * 0.6), T));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(big, { opacity: 0, scale: 0.2, y: 80 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0 + 0.0);

  K.shake(tl, stage, t0 + 0.0 + 0.05, 18, 0.3);
  K.vignette(stage, 0.6);
};

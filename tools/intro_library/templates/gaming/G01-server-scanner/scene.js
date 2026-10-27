// THEME over the gaming scene bank: the approved Top 10 Servers look - dark tech grid, scanlines, cyan HUD corner brackets
// around every scene and a running SCANNING readout that counts results found; whip cuts (camera); 3D pixel title.
window.CAMERA = { intensity: 1.1 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn;
  tl.fromTo("#grid", { x: 0, y: 0 }, { x: -120, y: -60, duration: I.dur, ease: "none" }, 0);
  const d = K.director(tl, { cut: "whip" });
  // HUD frame: corner brackets + a status readout
  const hud = document.getElementById("hud");
  ["tl", "tr", "bl", "br"].forEach((c) => K.div("c " + c, hud));
  const st = K.div("st", hud);
  const lab = K.div("", st), num = K.div("num", st, "", "0");
  K.pixo("SCANNING", 4, "#6dffb0", { outline: 0, shadow: 0 }, lab);
  tl.fromTo(hud, { opacity: 0, scale: 1.08 }, { opacity: 1, scale: 1, duration: 0.3 }, 0.05);
  I.lines.forEach((ln, k) => K.text(tl, num, ln.s, String((k + 1) * (ln.s < turn ? 37 : 113))));
  tl.to(st, { color: "#ffd23a", duration: 0.1 }, turn);
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(hud, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));
  const a = K.pix3d(words, ps, ["#fff3a6", "#ffd23a", "#ff9d00"], "#7a3b00", Math.round(ps * 1.4), T);
  const b = I.sub ? K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#e8f7ff", "#9edfff"], "#0d3a55", Math.round(ps * 0.6), T) : null;
  const go = K.pixo("LET'S GO!", 12, ["#ff6a5e", "#e01e12"], {}, T);
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(a, { opacity: 0, scale: 3.2 }, { opacity: 1, scale: 1, duration: 0.3, ease: "power4.out" }, t0);
  if (b) tl.fromTo(b, { opacity: 0, y: 60 }, { opacity: 1, y: 0, duration: 0.3, ease: "back.out(2)" }, t0 + 0.25);
  tl.fromTo(go, { opacity: 0, scale: 0.3 }, { opacity: 1, scale: 1, duration: 0.25, ease: "back.out(2.4)" }, t0 + 0.5);
  K.shake(tl, stage, t0 + 0.04, 22, 0.34);
  K.scan(stage, 0.8);
  K.vignette(stage, 0.6);
};

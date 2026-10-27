// THEME over the gaming scene bank: Corrupted Save. A corrupted save file.
window.CAMERA = { intensity: 1.15 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");
  K.grain(tl, bg, 0.55, I.seed);
  const d = K.director(tl, { cut: "glitch" });
  const pre = lines.filter((l) => l.s < turn);
  const errs = pre.map((ln, k) => { const e = K.div("err", frame, `left:${160 + (k % 4) * 330}px;top:${120 + (k % 3) * 200}px`); const tb = K.div("tb", e); K.pixo("ERROR", 4, "#fff", { outline: 0, shadow: 0 }, tb); const bd = K.div("bd", e); K.pixo((ln.key || "???").toUpperCase().slice(0, 14) + " NOT FOUND", 4, "#000", { outline: 0, shadow: 0 }, bd); tl.fromTo(e, { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: 0.15, ease: "back.out(2)" }, Math.max(ln.s, ln.keyT)); return e; });
  const rp = K.div("rp", frame); K.pixo("REPAIRING SAVE...", 5, "#000", { outline: 0, shadow: 0 }, rp); const bar = K.div("bar", rp); const fl = K.div("fl", bar);
  gsap.set(fl, { scaleX: 0 }); tl.set(rp, { opacity: 1 }, turn + 0.05); tl.to(fl, { scaleX: 1, duration: 0.9, ease: "steps(12)" }, turn + 0.1); tl.to(errs, { opacity: 0, scale: 0.6, duration: 0.12, stagger: 0.05 }, turn + 0.3); tl.set(rp, { opacity: 0 }, turn + 1.15);
  tl.to(bg, { backgroundColor: "#0a1a12", duration: 0.2 }, turn + 1.1);
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));

  const big = [K.pix3d(words, ps, ["#e0fff0", "#6dffb0", "#1fbf6f"], "#04301c", Math.round(ps * 1.4), T)];
  if (I.sub) big.push(K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#eeeeee", "#cfcfcf"], "#222222", Math.round(ps * 0.6), T));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(big, { opacity: 0, scale: 0.2, y: 80 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0 + 0.0);

  K.shake(tl, stage, t0 + 0.0 + 0.05, 18, 0.3);
  K.vignette(stage, 0.5);
};

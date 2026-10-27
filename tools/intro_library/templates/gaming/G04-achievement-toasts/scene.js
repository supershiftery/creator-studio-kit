// THEME over the gaming scene bank: Achievement Get!. Survival-world dirt and grass behind every scene; every line pops an 'Advancement Made!' toast top-right with a pixel icon and the line's key word, and the toasts stack; pixel-wipe cuts; title as the final 'Challenge Complete!' toast in purple, then the 3D pixel title..
window.CAMERA = { intensity: 1.1 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");
  K.blocks(bg, { base: [118, 86, 58], seed: I.seed });
  const d = K.director(tl, { cut: "pixel" });
  lines.forEach((ln, k) => {
    const t = K.div("toast", frame, `top:${40 + (k % 3) * 130}px`);
    K.icon(K.gicon(ln), 6, t);
    const tx = K.div("", t, "display:flex;flex-direction:column;gap:8px");
    K.pixo(ln.s < turn ? "ADVANCEMENT MADE!" : "GOAL REACHED!", 4, ln.s < turn ? "#ffff55" : "#55ff55", { outline: 0, shadow: 4, shadowColor: "#3f3f00" }, tx);
    K.pixo((ln.key || "???").toUpperCase().slice(0, 18), 4, "#ffffff", { outline: 0, shadow: 4, shadowColor: "#3f3f3f" }, tx);
    const tt = Math.max(ln.s, ln.keyT - 0.1);
    tl.fromTo(t, { opacity: 1, x: 700 }, { x: 0, duration: 0.25, ease: "power3.out", immediateRender: false }, tt);
    tl.set(t, { opacity: 0 }, 0);
    tl.set(t, { opacity: 1 }, tt);
    tl.to(t, { x: 700, duration: 0.2, ease: "power3.in" }, Math.min(tt + 2.4, K.end(ln) + 1.2));
  });
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));

  const big = [K.pix3d(words, ps, ["#f3d1ff", "#c56cff", "#8a2be2"], "#3a0a5a", Math.round(ps * 1.4), T)];
  if (I.sub) big.push(K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#eeeeee", "#cfcfcf"], "#222222", Math.round(ps * 0.6), T));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(big, { opacity: 0, scale: 0.2, y: 80 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0 + 0.0);

  K.shake(tl, stage, t0 + 0.0 + 0.05, 18, 0.3);
  K.vignette(stage, 0.5);
};

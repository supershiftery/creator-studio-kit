// THEME over the gaming scene bank: Loot Cave. A dark cave of stone and ore with flickering torchlight behind every scene; a rarity banner along the bottom climbs COMMON -> UNCOMMON -> RARE -> EPIC -> LEGENDARY as the lines go on (colour shifting each step); pixel-wipe cuts; title shines as LEGENDARY loot..
window.CAMERA = { intensity: 1.1 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");
  K.blocks(bg, { base: [58, 58, 62], seed: I.seed, vary: 30 });
  const torch = K.div("torch", bg);
  tl.to(torch, { opacity: 0.7, duration: 0.12, yoyo: true, repeat: Math.floor(I.dur / 0.24), ease: "none" }, 0);
  const d = K.director(tl, { cut: "pixel" });
  const rb = K.div("rb", frame);
  const R = [["COMMON", "#bbbbbb"], ["UNCOMMON", "#55ff55"], ["RARE", "#5599ff"], ["EPIC", "#c56cff"], ["LEGENDARY", "#ffb400"]];
  lines.forEach((ln, k) => { const r = R[Math.min(4, Math.floor(k * 5 / lines.length))]; const e = K.div("", rb, "position:absolute;opacity:0"); K.pixo(r[0], 7, r[1], {}, e); tl.set(e, { opacity: 1 }, ln.s); tl.fromTo(e, { scale: 1.5 }, { scale: 1, duration: 0.2, ease: "power3.out" }, ln.s); tl.set(e, { opacity: 0 }, K.end(ln)); });
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));

  const big = [K.pix3d(words, ps, ["#fff3a6", "#ffb400", "#ff6a00"], "#5a2400", Math.round(ps * 1.4), T)];
  if (I.sub) big.push(K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#eeeeee", "#cfcfcf"], "#222222", Math.round(ps * 0.6), T));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(big, { opacity: 0, scale: 0.2, y: 80 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0 + 0.0);

  K.shake(tl, stage, t0 + 0.0 + 0.05, 18, 0.3);
  K.vignette(stage, 0.75);
};

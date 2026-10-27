// THEME over the gaming scene bank: survival-inventory world. Stone wall behind every scene, a hotbar along the bottom that
// fills one item per line (the intro "collects" each point), pixel-wipe cuts, crafting-grid title.
window.CAMERA = { intensity: 1.15 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root();
  K.blocks(document.getElementById("wall"), { base: [96, 96, 98], seed: I.seed });
  tl.fromTo("#wall", { scale: 1.1 }, { scale: 1.0, duration: I.dur, ease: "none" }, 0);
  const d = K.director(tl, { cut: "pixel" });
  // hotbar frame device: 9 slots, an item drops in on every line, the selector follows
  const hb = document.getElementById("hotbar");
  const cells = [];
  for (let i = 0; i < 9; i++) cells.push(K.div("mslot", hb));
  const sel = K.div("hsel", hb);
  tl.fromTo(hb, { y: 200 }, { y: 0, duration: 0.35, ease: "back.out(1.6)" }, 0.1);
  I.lines.filter((l) => l.role !== "go").slice(0, 9).forEach((ln, k) => {
    const ic = K.icon(K.gicon(ln), 6, cells[k]);
    tl.fromTo(ic, { opacity: 0, scale: 2.5, y: -160 }, { opacity: 1, scale: 1, y: 0, duration: 0.25, ease: "back.out(1.6)" }, Math.max(ln.s, ln.keyT - 0.05));
    tl.to(sel, { x: k * 114, duration: 0.15, ease: "power2.out" }, Math.max(ln.s, ln.keyT - 0.05));
  });
  K.xp(tl, stage, { top: 820, label: "WATCH TO THE VERY END" });
  // title: the crafting result
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));
  const grid = K.div("cgrid", T);
  for (let i = 0; i < 9; i++) { const c = K.div("mslot", grid); K.icon(["gem", "pick", "gem", "sword", "chest", "sword", "gem", "crown", "gem"][i], 6, c); }
  const big = [K.pix3d(words, ps, ["#fff3a6", "#ffd23a", "#ff9d00"], "#7a3b00", Math.round(ps * 1.4), T)];
  if (I.sub) big.push(K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#e8f7ff", "#9edfff"], "#0d3a55", Math.round(ps * 0.6), T));
  const t0 = d.t0title;
  tl.to(hb, { y: 220, duration: 0.25 }, t0 - 0.1);
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(grid, { scale: 1.4, opacity: 0 }, { scale: 0.7, opacity: 1, duration: 0.25, ease: "power3.out" }, t0);
  tl.to(grid, { scale: 0, opacity: 0, rotation: 90, duration: 0.25, ease: "power3.in" }, t0 + 0.35);
  tl.fromTo(big, { opacity: 0, scale: 0.2, y: 120 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0 + 0.5);
  K.shake(tl, stage, t0 + 0.55, 18, 0.3);
  K.vignette(stage, 0.55);
};

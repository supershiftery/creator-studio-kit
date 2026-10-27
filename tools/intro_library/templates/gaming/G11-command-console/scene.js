// THEME over the gaming scene bank: Command Console. A black terminal world.
window.CAMERA = { intensity: 1.0 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");

  const d = K.director(tl, { cut: "glitch" });
  const log = K.div("log", frame);
  lines.forEach((ln, k) => {
    const cmd = "/" + ["find", "locate", "scan", "tp", "give", "check"][k % 6] + " " + (ln.key || "???").toLowerCase().replace(/\s+/g, "_");
    const out = ln.s < turn ? "Error: nothing worth playing" : "Found it ✓";
    const row = K.div("", log, "white-space:nowrap"), o = K.div("", log, "white-space:nowrap;color:" + (ln.s < turn ? "#ff6b6b" : "#6dff8a"));
    log.insertBefore(o, log.firstChild); log.insertBefore(row, log.firstChild);
    row.style.display = "none"; o.style.display = "none";
    tl.set(row, { display: "block" }, ln.s); K.type(tl, row, "> " + cmd, ln.s, Math.min(0.6, cmd.length * 0.03), "_");
    tl.set(o, { display: "block" }, ln.s + 0.7); K.text(tl, o, ln.s + 0.7, out);
  });
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));

  const big = [K.pix3d(words, ps, ["#d9ffe0", "#6dff8a", "#1fbf3f"], "#04300c", Math.round(ps * 1.4), T)];
  if (I.sub) big.push(K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#eeeeee", "#cfcfcf"], "#222222", Math.round(ps * 0.6), T));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(big, { opacity: 0, scale: 0.2, y: 80 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0 + 0.0);

  K.shake(tl, stage, t0 + 0.0 + 0.05, 18, 0.3);
  K.vignette(stage, 0.5);
};

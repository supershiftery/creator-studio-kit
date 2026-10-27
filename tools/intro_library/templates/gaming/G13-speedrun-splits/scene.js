// THEME over the gaming scene bank: Speedrun Splits. A speedrun overlay.
window.CAMERA = { intensity: 1.05 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");

  const d = K.director(tl, { cut: "whip" });
  const ls = K.div("ls", frame);
  const rows = lines.slice(0, 8).map((ln, k) => K.div("sp", ls, "", `<span>${K.esc((ln.key || "split " + (k + 1)).slice(0, 14))}</span><b>—</b>`));
  const tm = K.div("tm", ls, "", "0:00.00");
  const c = { v: 0 }; tl.to(c, { v: 1, duration: I.dur, ease: "none", onUpdate: () => { const s = tl.time(); tm.textContent = Math.floor(s / 60) + ":" + (s % 60).toFixed(2).padStart(5, "0"); tm.style.color = s < turn ? "#ff5a5a" : "#ffd23a"; } }, 0);
  lines.slice(0, 8).forEach((ln, k) => { tl.set(rows[k], { opacity: 1 }, ln.s); const b = rows[k].querySelector("b"); K.text(tl, b, ln.s + 0.2, (ln.s < turn ? "+" : "-") + (0.4 + k * 0.7).toFixed(1)); tl.set(b, { color: ln.s < turn ? "#ff5a5a" : "#ffd23a" }, ln.s + 0.2); });
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));
  const pb = K.pixo("NEW PERSONAL BEST", 7, ["#ffe56b", "#ffb300"], {}, T);
  const big = [K.pix3d(words, ps, ["#fff3a6", "#ffd23a", "#ff9d00"], "#7a3b00", Math.round(ps * 1.4), T)];
  if (I.sub) big.push(K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#eeeeee", "#cfcfcf"], "#222222", Math.round(ps * 0.6), T));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(big, { opacity: 0, scale: 0.2, y: 80 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0 + 0.25);
  tl.fromTo(pb, { opacity: 0, y: -30 }, { opacity: 1, y: 0, duration: 0.3 }, t0);
  K.shake(tl, stage, t0 + 0.25 + 0.05, 18, 0.3);
  K.vignette(stage, 0.5);
};

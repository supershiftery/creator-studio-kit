// THEME over the gaming scene bank: Comic Panels. A comic-book page.
window.CAMERA = { intensity: 1.15 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");
  const cols = ["#ff4f4f", "#4fa3ff", "#ffcf3f", "#7dff6a", "#c56cff"]; lines.forEach((ln, k) => tl.set(bg, { backgroundColor: cols[k % 5] }, ln.s));
  const d = K.director(tl, { cut: "flash" });
  K.div("pb", frame); const cap = K.div("cap", frame);
  lines.forEach((ln) => { const e = K.div("", cap, "position:absolute;left:26px;top:16px;opacity:0;white-space:nowrap"); K.pixo((ln.key || K.short(ln.text, 3)).toUpperCase().slice(0, 22) + "...", 5, "#000", { outline: 0, shadow: 0 }, e); tl.set(e, { opacity: 1 }, ln.s); tl.set(e, { opacity: 0 }, K.end(ln)); });
  cap.style.width = "720px"; cap.style.height = "80px";
  const pow = K.div("pow", frame); K.pixo("POW!", 10, "#ff3b00", { outline: 4, outlineColor: "#000", shadow: 0 }, pow); tl.fromTo(pow, { opacity: 0, scale: 0.2, rotation: -20 }, { opacity: 1, scale: 1, rotation: 6, duration: 0.2, ease: "back.out(3)" }, turn); tl.to(pow, { opacity: 0, duration: 0.2 }, turn + 1.0);
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));

  const big = [K.pix3d(words, ps, ["#fff8a0", "#ffe500", "#ff9d00"], "#000000", Math.round(ps * 1.4), T)];
  if (I.sub) big.push(K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#eeeeee", "#cfcfcf"], "#222222", Math.round(ps * 0.6), T));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(big, { opacity: 0, scale: 0.2, y: 80 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0 + 0.0);

  K.shake(tl, stage, t0 + 0.0 + 0.05, 18, 0.3);
  K.vignette(stage, 0.3);
};

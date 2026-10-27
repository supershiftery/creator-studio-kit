// THEME over the gaming scene bank: Case File. Detective case-file world (the approved Realms look).
window.CAMERA = { intensity: 1.1 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");
  const beam = K.div("beam", bg);
  tl.fromTo(beam, { x: 0, y: 0 }, { x: 1100, y: 300, duration: I.dur, ease: "sine.inOut" }, 0);
  K.grain(tl, stage, 0.16, I.seed);
  const d = K.director(tl, { cut: "flash" });
  const ev = K.div("ev", frame);
  lines.forEach((ln, k) => { const e = K.div("", ev, "position:absolute;left:22px;top:10px;opacity:0"); K.pixo("EVIDENCE " + String(k + 1).padStart(2, "0"), 4, "#3a2a10", { outline: 0, shadow: 0 }, e); tl.set(e, { opacity: 1 }, ln.s); tl.set(e, { opacity: 0 }, K.end(ln)); });
  ev.style.width = "330px"; ev.style.height = "58px";
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));
  const stamp = K.div("", T, "position:absolute;top:170px;padding:10px 30px;border:10px solid #ff3b3b;transform:rotate(-8deg)");
  K.pixo("CASE OPEN", 10, "#ff3b3b", { outline: 0, shadow: 0 }, stamp);
  const big = [K.pix3d(words, ps, ["#ffe0d6", "#ff7a6a", "#d62828"], "#4a0a06", Math.round(ps * 1.4), T)];
  if (I.sub) big.push(K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#eeeeee", "#cfcfcf"], "#222222", Math.round(ps * 0.6), T));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(big, { opacity: 0, scale: 0.2, y: 80 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0 + 0.35);
  tl.fromTo(stamp, { opacity: 0, scale: 2.4 }, { opacity: 1, scale: 1, duration: 0.2, ease: "power4.out" }, t0);
  K.shake(tl, stage, t0 + 0.35 + 0.05, 18, 0.3);
  K.vignette(stage, 0.7);
};

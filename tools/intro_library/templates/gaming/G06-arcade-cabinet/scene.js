// THEME over the gaming scene bank: Arcade Cabinet. Every scene plays on a curved CRT arcade screen inside a cabinet bezel with glare and scanlines; a 1UP / HI-SCORE counter climbs on every line, problem lines flash GAME OVER lives lost, glitch cuts between scenes; INSERT COIN blinks, then the title as the game's logo..
window.CAMERA = { intensity: 1.0 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");
  K.scan(stage, 1);
  const d = K.director(tl, { cut: "glitch" });
  K.div("glare", frame); K.div("bez", frame);
  const sc = K.div("sc", frame);
  const a = K.div("", sc), b = K.div("", sc);
  K.pixo("1UP", 5, "#ff2f2f", { outline: 0, shadow: 0 }, a); const s1 = K.div("", a, "font:400 58px VT323, monospace;color:#fff", "000000");
  K.pixo("HI-SCORE", 5, "#ff2f2f", { outline: 0, shadow: 0 }, b); K.div("", b, "font:400 58px VT323, monospace;color:#fff", "999990");
  lines.forEach((ln, k) => K.text(tl, s1, ln.s, String((k + 1) * 4250).padStart(6, "0")));
  K.xp(tl, stage, { top: 900, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));
  const ic = K.pixo("INSERT COIN", 9, ["#ffe14a", "#ff7b00"], {}, T);
  const big = [K.pix3d(words, ps, ["#fff7a8", "#ffe14a", "#ff7b00"], "#7a1f00", Math.round(ps * 1.4), T)];
  if (I.sub) big.push(K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#eeeeee", "#cfcfcf"], "#222222", Math.round(ps * 0.6), T));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(big, { opacity: 0, scale: 0.2, y: 80 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0 + 0.0);
  tl.fromTo(ic, { opacity: 0 }, { opacity: 1, duration: 0.01, yoyo: true, repeat: 7, repeatDelay: 0.2 }, t0 + 0.5);
  K.shake(tl, stage, t0 + 0.0 + 0.05, 18, 0.3);
  K.vignette(stage, 0.4);
};

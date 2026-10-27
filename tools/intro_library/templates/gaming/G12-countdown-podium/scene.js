// THEME over the gaming scene bank: Countdown Podium. A dark stage with sweeping spotlights; every scene plays above a three-step podium whose ??? silhouettes light up one by one through the reveal, and a rank ticker counts down #10 -> #1 along the bottom; whip cuts; the title lands on the top step..
window.CAMERA = { intensity: 1.1 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");
  [300, 1300].forEach((x, i) => { const s = K.div("sp", bg, `left:${x}px`); tl.fromTo(s, { rotation: i ? 20 : -20 }, { rotation: i ? -20 : 20, duration: 2.2, yoyo: true, repeat: Math.floor(I.dur / 2.2), ease: "sine.inOut" }, 0); });
  const d = K.director(tl, { cut: "whip" });
  const pods = [[760, 400, 140, "1"], [360, 400, 90, "2"], [1160, 400, 60, "3"]].map((p) => { const e = K.div("pod", frame, `left:${p[0]}px;width:${p[1]}px;height:${p[2]}px`); K.pixo(p[3], 5, "#ffd23a", { outline: 0, shadow: 0 }, e); return e; });
  const tk = K.div("", frame, "position:absolute;right:60px;top:60px");
  lines.forEach((ln, k) => { const e = K.div("", tk, "position:absolute;right:0;opacity:0"); K.pixo("#" + Math.max(1, 10 - k), 9, ["#ffe56b", "#ffb300"], {}, e); tl.set(e, { opacity: 1 }, ln.s); tl.fromTo(e, { scale: 1.8 }, { scale: 1, duration: 0.2, ease: "power4.out" }, ln.s); tl.set(e, { opacity: 0 }, K.end(ln)); });
  pods.forEach((p, k) => tl.fromTo(p, { y: 200 }, { y: 0, duration: 0.4, ease: "back.out(1.6)" }, turn + k * 0.2));
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  const T = document.getElementById("title");
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));

  const big = [K.pix3d(words, ps, ["#fff3a6", "#ffd23a", "#ff9d00"], "#7a3b00", Math.round(ps * 1.4), T)];
  if (I.sub) big.push(K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#eeeeee", "#cfcfcf"], "#222222", Math.round(ps * 0.6), T));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(big, { opacity: 0, scale: 0.2, y: 80 }, { opacity: 1, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0 + 0.0);

  K.shake(tl, stage, t0 + 0.0 + 0.05, 18, 0.3);
  K.vignette(stage, 0.55);
};

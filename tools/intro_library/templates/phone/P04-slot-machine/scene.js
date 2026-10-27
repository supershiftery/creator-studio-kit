// THEME over the phone scene bank: Jackpot Lights. Every VO line is its own literal scene (cart, receipt, gatekept codes, secret folder,
// $0.00 strike, group chat, orders at $0, plus the user's own face-cam / phone-screen clips); the frame device below ties them together.
window.CAMERA = { intensity: 1.25 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e, app = K.app();
  const frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");

  const d = K.director(tl, { cut: "flash" });
  const B = []; for (let i = 0; i < 30; i++) { const top = i < 15; B.push(K.div("bulb", frame, `left:${60 + (i % 15) * 128}px;top:${top ? 20 : 1036}px`)); }
  B.forEach((b, i) => tl.fromTo(b, { opacity: 0.25 }, { opacity: 1, duration: 0.2, yoyo: true, repeat: Math.floor(I.dur / 0.4), ease: "none" }, (i % 3) * 0.13));
  const jm = K.div("jm", frame), fill = K.div("", jm); fill.outerHTML; const bar = jm.appendChild(document.createElement("b")); gsap.set(bar, { scaleX: 0 });
  lines.forEach((ln, k) => tl.to(bar, { scaleX: Math.min(1, (k + 1) / lines.length), duration: 0.35, ease: "power3.out" }, ln.s));
  K.xp(tl, stage, { top: 940, label: "WATCH TO THE END" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  K.appIcon(document.getElementById("ticon"), 200, "box-shadow:0 20px 50px rgba(0,0,0,.35)");
  t1.textContent = (I.title || app.name).toUpperCase();
  K.fit(t1, 1400, 190, 90);
  const t0 = Math.max(last + 0.05, (I.beats.go || last) - 0.1);
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(T.querySelector(".row"), { opacity: 0, scale: 1.4 }, { opacity: 1, scale: 1, duration: 0.3, ease: "power4.out" }, t0);
  tl.fromTo(T.querySelector(".pill"), { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.3, ease: "back.out(2)" }, t0 + 0.3);
  K.wipe(tl, I.dur - 0.6, "#ffd34d", "#fff");
};

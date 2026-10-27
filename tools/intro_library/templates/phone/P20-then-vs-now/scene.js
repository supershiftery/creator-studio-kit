// THEME over the phone scene bank: Before / After. Every VO line is its own literal scene (cart, receipt, gatekept codes, secret folder,
// $0.00 strike, group chat, orders at $0, plus the user's own face-cam / phone-screen clips); the frame device below ties them together.
window.CAMERA = { intensity: 1.15 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e, app = K.app();
  const frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");
  const bf = K.div("bf", bg); const rain = K.div("rain", bf); tl.fromTo(rain, { y: 0 }, { y: 200, duration: I.dur, ease: "none" }, 0);
  const pos = { x: 1920 }; const apply = () => { bf.style.clipPath = `inset(0 ${1920 - pos.x}px 0 0)`; }; apply(); tl.to(pos, { x: 0, duration: 0.55, ease: "power3.inOut", onUpdate: apply }, turn - 0.1);
  const d = K.director(tl, { cut: "none" });
  const lb = K.div("lb", frame, "", "BEFORE"); K.text(tl, lb, turn + 0.3, "AFTER");
  const dv = K.div("dv", frame); tl.fromTo(dv, { left: 1920 }, { left: -20, duration: 0.55, ease: "power3.inOut", immediateRender: false }, turn - 0.1);
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE END" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  K.appIcon(document.getElementById("ticon"), 200, "box-shadow:0 20px 50px rgba(0,0,0,.35)");
  t1.textContent = (I.title || app.name).toUpperCase();
  K.fit(t1, 1400, 190, 90);
  const t0 = Math.max(last + 0.05, (I.beats.go || last) - 0.1);
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(T, { clipPath: "circle(0% at 50% 50%)" }, { clipPath: "circle(80% at 50% 50%)", duration: 0.45, ease: "power3.out" }, t0);
  tl.fromTo(T.querySelector(".pill"), { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.3, ease: "back.out(2)" }, t0 + 0.3);
  K.wipe(tl, I.dur - 0.6, "#fff");
};

// THEME over the phone scene bank: Price Odometer. Every VO line is its own literal scene (cart, receipt, gatekept codes, secret folder,
// $0.00 strike, group chat, orders at $0, plus the user's own face-cam / phone-screen clips); the frame device below ties them together.
window.CAMERA = { intensity: 1.15 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e, app = K.app();
  const frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");

  const d = K.director(tl, { cut: "none" });
  const od = K.div("od", frame, "", "$0.00"); let v = 0;
  lines.filter((l) => l.s < turn).forEach((ln, k) => { const f = [20.48, 3.99, 3.2, 3.51][k % 4]; K.count(tl, od, v, v + f, ln.s, 0.5, K.money); v += f; });
  K.count(tl, od, v, 0, turn + 0.15, 1.3, K.money, "power3.inOut"); tl.set(od, { color: app.accent }, turn + 0.15);
  const st = K.div("st", frame, "", "100% FREE"); tl.fromTo(st, { opacity: 0, scale: 2.4 }, { opacity: 1, scale: 1, duration: 0.2, ease: "power4.out" }, turn + 1.5);
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE END" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  K.appIcon(document.getElementById("ticon"), 200, "box-shadow:0 20px 50px rgba(0,0,0,.35)");
  t1.textContent = (I.title || app.name).toUpperCase();
  K.fit(t1, 1400, 190, 90);
  const t0 = Math.max(last + 0.05, (I.beats.go || last) - 0.1);
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(T.querySelector(".row"), { opacity: 0, scale: 1.4 }, { opacity: 1, scale: 1, duration: 0.3, ease: "power4.out" }, t0);
  tl.fromTo(T.querySelector(".pill"), { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.3, ease: "back.out(2)" }, t0 + 0.3);
  K.wipe(tl, I.dur - 0.6, "#fff");
};

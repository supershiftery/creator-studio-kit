// THEME over the phone scene bank: Money Meter. Every VO line is its own literal scene (cart, receipt, gatekept codes, secret folder,
// $0.00 strike, group chat, orders at $0, plus the user's own face-cam / phone-screen clips); the frame device below ties them together.
window.CAMERA = { intensity: 1.15 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e, app = K.app();
  const frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");

  const d = K.director(tl, { cut: "none" });
  const mt = K.div("mt", frame), b = mt.appendChild(document.createElement("b")); const ml = K.div("ml", frame, "", "SPENT"); gsap.set(b, { scaleY: 0 });
  const pre = lines.filter((l) => l.s < turn), post = lines.filter((l) => l.s >= turn);
  pre.forEach((ln, k) => tl.to(b, { scaleY: (k + 1) / pre.length, duration: 0.4, ease: "power2.out" }, ln.s));
  tl.to(b, { scaleY: 0, duration: 0.4, ease: "power2.in" }, turn); tl.set(b, { backgroundColor: app.accent }, turn + 0.4); K.text(tl, ml, turn + 0.4, "SAVED");
  post.forEach((ln, k) => tl.to(b, { scaleY: (k + 1) / post.length, duration: 0.4, ease: "back.out(1.6)" }, ln.s));
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE END" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  K.appIcon(document.getElementById("ticon"), 200, "box-shadow:0 20px 50px rgba(0,0,0,.35)");
  t1.textContent = (I.title || app.name).toUpperCase();
  K.fit(t1, 1400, 190, 90);
  const t0 = Math.max(last + 0.05, (I.beats.go || last) - 0.1);
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(T.querySelector(".row"), { opacity: 0, y: -300 }, { opacity: 1, y: 0, duration: 0.4, ease: "bounce.out" }, t0);
  tl.fromTo(T.querySelector(".pill"), { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.3, ease: "back.out(2)" }, t0 + 0.3);
  K.wipe(tl, I.dur - 0.6);
};

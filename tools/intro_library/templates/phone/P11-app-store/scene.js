// THEME over the phone scene bank: Store Listing. Every VO line is its own literal scene (cart, receipt, gatekept codes, secret folder,
// $0.00 strike, group chat, orders at $0, plus the user's own face-cam / phone-screen clips); the frame device below ties them together.
window.CAMERA = { intensity: 1.15 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e, app = K.app();
  const frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");

  const d = K.director(tl, { cut: "none" });
  const hd = K.div("hd", frame); K.appIcon(hd, 90); K.div("nm", hd, "", K.esc(app.name)); const rt = K.div("rt", hd, "", "★ 4.8"); const get = K.div("get", hd, "", "GET");
  let v = 4.8; lines.forEach((ln, k) => { const to = ln.s < turn ? Math.max(1.2, v - 0.8) : Math.min(5, v + 1.2); K.count(tl, rt, v, to, ln.s, 0.4, (x) => "★ " + x.toFixed(1)); v = to; });
  tl.fromTo(get, { scale: 1 }, { scale: 1.25, duration: 0.12, yoyo: true, repeat: 3 }, turn);
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
  K.wipe(tl, I.dur - 0.6, app.accent, "#fff");
};

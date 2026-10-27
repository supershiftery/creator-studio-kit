// THEME over the phone scene bank: Search Results. Every VO line is its own literal scene (cart, receipt, gatekept codes, secret folder,
// $0.00 strike, group chat, orders at $0, plus the user's own face-cam / phone-screen clips); the frame device below ties them together.
window.CAMERA = { intensity: 1.15 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e, app = K.app();
  const frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");

  const d = K.director(tl, { cut: "none" });
  const sb = K.div("sb", frame); K.glyph("search", 40, "#5f6368", sb); const q = K.div("", sb); const bd = K.div("badge", frame, "", "SEARCHING");
  const Q = ["free " + app.name + " code", app.name + " promo code reddit", app.name + " code that works", "secret " + app.name + " methods"];
  lines.forEach((ln, k) => { K.type(tl, q, Q[k % Q.length].toLowerCase(), ln.s, 0.5); K.text(tl, bd, ln.s + 0.3, ln.s < turn ? ["EXPIRED", "FAKE", "NOT WORKING"][k % 3] : "VERIFIED ✓"); tl.set(bd, { backgroundColor: ln.s < turn ? "#d93025" : "#188038" }, ln.s + 0.3); });
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE END" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  K.appIcon(document.getElementById("ticon"), 200, "box-shadow:0 20px 50px rgba(0,0,0,.35)");
  t1.textContent = (I.title || app.name).toUpperCase();
  K.fit(t1, 1400, 190, 90);
  const t0 = Math.max(last + 0.05, (I.beats.go || last) - 0.1);
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(T, { clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)", duration: 0.35, ease: "power4.out" }, t0);
  tl.fromTo(T.querySelector(".pill"), { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.3, ease: "back.out(2)" }, t0 + 0.3);
  K.wipe(tl, I.dur - 0.6);
};

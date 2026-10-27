// THEME over the phone scene bank: Balance Drain. Every VO line is its own literal scene (cart, receipt, gatekept codes, secret folder,
// $0.00 strike, group chat, orders at $0, plus the user's own face-cam / phone-screen clips); the frame device below ties them together.
window.CAMERA = { intensity: 1.15 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e, app = K.app();
  const frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");

  const d = K.director(tl, { cut: "none" });
  const bal = K.div("bal", frame, "", "<small>Available balance</small><b>$312.40</b><i></i>"); const b = bal.querySelector("b"), ch = bal.querySelector("i");
  let v = 312.4; lines.forEach((ln, k) => { const amt = ln.s < turn ? -[27.67, 9.12, 31.4, 5.99][k % 4] : [18, 25.5, 33][k % 3]; K.count(tl, b, v, v + amt, ln.s + 0.05, 0.4, K.money); K.text(tl, ch, ln.s + 0.05, (amt < 0 ? "- " : "+ ") + K.money(Math.abs(amt)) + "  " + app.name); tl.set(ch, { color: amt < 0 ? "#ff6b6b" : "#3dff7a" }, ln.s + 0.05); v += amt; });
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

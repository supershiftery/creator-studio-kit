// THEME over the phone scene bank: Vault Keypad. Every VO line is its own literal scene (cart, receipt, gatekept codes, secret folder,
// $0.00 strike, group chat, orders at $0, plus the user's own face-cam / phone-screen clips); the frame device below ties them together.
window.CAMERA = { intensity: 1.15 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e, app = K.app();
  const frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");
  const gold = K.div("gold", bg); tl.to(gold, { opacity: 1, duration: 0.6 }, turn + 0.3);
  const d = K.director(tl, { cut: "flash" });
  const kp = K.div("kp", frame, "", '<div class="s">LOCKED</div><div class="c">_ _ _ _</div>'); const s = kp.querySelector(".s"), c = kp.querySelector(".c");
  lines.filter((l) => l.s < turn).forEach((ln, k) => { K.text(tl, s, ln.s + 0.05, k % 2 ? "DENIED" : "LOCKED"); tl.fromTo(kp, { x: 0 }, { x: 10, duration: 0.05, yoyo: true, repeat: 5 }, ln.s + 0.05); });
  ["7", "3", "1", "9"].forEach((dg, k) => K.text(tl, c, turn + 0.2 + k * 0.25, ["7", "3", "1", "9"].slice(0, k + 1).join(" ") + " _".repeat(3 - k)));
  K.text(tl, s, turn + 1.2, "OPEN"); tl.set(s, { color: "#8cff9e" }, turn + 1.2);
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
  K.wipe(tl, I.dur - 0.6);
};

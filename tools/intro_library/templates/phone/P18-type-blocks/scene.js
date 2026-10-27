// THEME over the phone scene bank: Swiss Blocks. Every VO line is its own literal scene (cart, receipt, gatekept codes, secret folder,
// $0.00 strike, group chat, orders at $0, plus the user's own face-cam / phone-screen clips); the frame device below ties them together.
window.CAMERA = { intensity: 1.25 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e, app = K.app();
  const frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");
  const A = K.div("bl", bg, "background:#e63329"), B = K.div("bl", bg, "background:#f4f1ea");
  const L = [[[0, 0, 640, 1080], [1500, 700, 420, 380]], [[0, 700, 1920, 380], [1500, 0, 420, 700]], [[1280, 0, 640, 1080], [0, 0, 420, 400]], [[0, 0, 1920, 300], [0, 780, 700, 300]]];
  I.lines.forEach((ln, k) => { const l = L[k % 4]; tl.to(A, { left: l[0][0], top: l[0][1], width: l[0][2], height: l[0][3], duration: 0.35, ease: "power4.inOut" }, ln.s - 0.1); tl.to(B, { left: l[1][0], top: l[1][1], width: l[1][2], height: l[1][3], duration: 0.35, ease: "power4.inOut" }, ln.s - 0.1); });
  tl.to(A, { backgroundColor: K.app().accent, duration: 0.05 }, turn);
  const d = K.director(tl, { cut: "none" });
  const n = K.div("n", frame); lines.forEach((ln, k) => K.text(tl, n, ln.s, String(k + 1).padStart(2, "0")));
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
  K.wipe(tl, I.dur - 0.6, "#fff", "#111");
};

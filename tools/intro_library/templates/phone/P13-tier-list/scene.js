// THEME over the phone scene bank: Tier Ranking. Every VO line is its own literal scene (cart, receipt, gatekept codes, secret folder,
// $0.00 strike, group chat, orders at $0, plus the user's own face-cam / phone-screen clips); the frame device below ties them together.
window.CAMERA = { intensity: 1.2 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e, app = K.app();
  const frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");

  const d = K.director(tl, { cut: "flash" });
  const ts = K.div("tiers", frame); [["S", "#ff7f7f"], ["A", "#ffbf7f"], ["B", "#ffdf7f"], ["C", "#bfff7f"], ["F", "#7fbfff"]].forEach((t) => K.div("", ts, `background:${t[1]}`, t[0]));
  const mk = K.div("mk", frame); gsap.set(mk, { y: 864 }); const post = lines.filter((l) => l.s >= turn);
  post.forEach((ln, k) => tl.to(mk, { y: Math.max(0, 864 - (k + 1) * Math.ceil(864 / Math.max(1, post.length))), duration: 0.3, ease: "back.out(2)" }, ln.s));
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
  K.wipe(tl, I.dur - 0.6);
};

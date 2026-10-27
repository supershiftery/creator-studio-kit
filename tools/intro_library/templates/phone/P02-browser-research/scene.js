// THEME over the phone scene bank: Browser Research. Every VO line is its own literal scene (cart, receipt, gatekept codes, secret folder,
// $0.00 strike, group chat, orders at $0, plus the user's own face-cam / phone-screen clips); the frame device below ties them together.
window.CAMERA = { intensity: 1.2 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e, app = K.app();
  const frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");

  // the background never sits still: two soft accent blobs drift across it the whole intro (dhgate coupons 2026-10-24)
  [[200, 120, 900], [1300, 600, 1100]].forEach(([x, y, r], i) => {
    const b = K.div("", bg, `position:absolute;left:${x}px;top:${y}px;width:${r}px;height:${r}px;border-radius:50%;background:radial-gradient(circle,${app.accent}33,transparent 70%)`);
    tl.fromTo(b, { x: 0, y: 0 }, { x: i ? -500 : 600, y: i ? -300 : 250, duration: I.dur, ease: "sine.inOut" }, 0);
  });
  const d = K.director(tl, { cut: "swipe" });
  const ch = K.div("chrome", frame, "", "<i></i><i></i><i></i>"); const url = K.div("url", ch); K.glyph("search", 28, "#9aa0aa", url); const q = K.div("", url);
  K.type(tl, q, (app.name + " promo codes that actually work").toLowerCase(), 0.2, 1.4, "|");
  tl.fromTo(ch, { y: -100 }, { y: 0, duration: 0.3, ease: "power3.out" }, 0);
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

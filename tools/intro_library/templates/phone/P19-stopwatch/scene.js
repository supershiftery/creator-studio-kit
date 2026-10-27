// THEME over the phone scene bank: Stopwatch Race. Every VO line is its own literal scene (cart, receipt, gatekept codes, secret folder,
// $0.00 strike, group chat, orders at $0, plus the user's own face-cam / phone-screen clips); the frame device below ties them together.
window.CAMERA = { intensity: 1.15 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e, app = K.app();
  const frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");

  const d = K.director(tl, { cut: "none" });
  const sw = K.div("sw", frame, "", "<small>MONEY LOST</small><b>00:00.00</b>"); const sm = sw.querySelector("small"), b = sw.querySelector("b");
  const c = { v: 0 }; tl.to(c, { v: 1, duration: I.dur, ease: "none", onUpdate: () => { const t = tl.time(), s = t < turn ? t * 3.1 : Math.max(0, t - turn) * 0.9; b.textContent = String(Math.floor(s / 60)).padStart(2, "0") + ":" + (s % 60).toFixed(2).padStart(5, "0"); b.style.color = t < turn ? "#ff5a5a" : "#3dff7a"; } }, 0);
  K.text(tl, sm, turn, "FREE IN"); tl.set(sm, { color: "#3dff7a" }, turn);
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
  K.wipe(tl, I.dur - 0.6, "#3dff7a", "#fff");
};

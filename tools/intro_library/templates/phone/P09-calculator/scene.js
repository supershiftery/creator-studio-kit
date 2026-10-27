// THEME over the phone scene bank: Running Total. Every VO line is its own literal scene (cart, receipt, gatekept codes, secret folder,
// $0.00 strike, group chat, orders at $0, plus the user's own face-cam / phone-screen clips); the frame device below ties them together.
window.CAMERA = { intensity: 1.15 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e, app = K.app();
  const frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");

  const d = K.director(tl, { cut: "none" });
  const ds = K.div("disp", frame, "", '<span class="tp"></span><b>0.00</b>'); const tp = ds.querySelector(".tp"), b = ds.querySelector("b");
  let v = 0; lines.forEach((ln, k) => { if (ln.s < turn) { const f = [20.48, 3.99, 3.2, 3.51][k % 4]; K.text(tl, tp, ln.s, "+ " + f.toFixed(2) + " " + ["food", "delivery", "service", "taxes"][k % 4]); K.count(tl, b, v, v + f, ln.s, 0.35, (x) => x.toFixed(2)); v += f; } });
  tl.set(b, { color: "#ff6b5a" }, turn - 0.4); app.methods.slice(0, 3).forEach((m, k) => K.text(tl, tp, turn + 0.2 + k * 0.4, "− " + m));
  K.count(tl, b, v, 0, turn + 1.4, 0.6, (x) => x.toFixed(2)); tl.set(b, { color: "#3dff7a" }, turn + 1.4);
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

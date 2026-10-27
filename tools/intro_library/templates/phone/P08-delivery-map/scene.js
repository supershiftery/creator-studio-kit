// THEME over the phone scene bank: Live Tracking. Every VO line is its own literal scene (cart, receipt, gatekept codes, secret folder,
// $0.00 strike, group chat, orders at $0, plus the user's own face-cam / phone-screen clips); the frame device below ties them together.
window.CAMERA = { intensity: 1.15 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e, app = K.app();
  const frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");
  const r = K.rng(I.seed); for (let y = 0; y < 8; y++) for (let x = 0; x < 13; x++) if (r() > 0.12) K.div("blk", bg, `left:${x * 150 + 20}px;top:${y * 140 + 20}px;width:112px;height:100px`);
  const d = K.director(tl, { cut: "none" });
  const svg = K.svg(frame); const R = [[120, 1000], [120, 760], [460, 760], [460, 500], [900, 500], [900, 240], [1300, 240]];
  const route = K.path(svg, "M " + R.map((p) => p.join(" ")).join(" L "), { color: app.accent, width: 14 }); K.draw(tl, route, 0.1, Math.max(1, last - 0.5), "none");
  const pin = K.div("pin", frame, "", K.glyphHTML("scooter", 46, app.accent)); const L = route.getTotalLength(), pr = { p: 0 };
  const place = () => { const pt = route.getPointAtLength(pr.p * L); pin.style.left = pt.x + "px"; pin.style.top = pt.y + "px"; }; place();
  tl.to(pr, { p: 1, duration: Math.max(1, last - 0.5), ease: "none", onUpdate: place }, 0.1);
  const eta = K.div("eta", frame, "", "Order total<b>$20.48</b>"); const tot = eta.querySelector("b"); let v = 20.48;
  lines.filter((l) => l.s < turn).forEach((ln, k) => { const f = [3.99, 3.2, 3.51, 2][k % 4]; K.count(tl, tot, v, v + f, ln.s, 0.35, K.money); v += f; });
  K.count(tl, tot, v, 0, turn + 0.1, 0.8, K.money); tl.set(tot, { color: "#0a9a44" }, turn + 0.1);
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
  K.wipe(tl, I.dur - 0.6, "#fff");
};

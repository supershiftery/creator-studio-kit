window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e;
  const page = document.getElementById("page"), cur = document.getElementById("cursor");
  page.querySelector(".cart").insertAdjacentHTML("afterbegin", K.glyphHTML("cart", 54, "#111"));
  I.slots.forEach((sl) => {
    const w = K.mount(tl, sl, page.querySelector(".photo"), { fade: 0.08 });
    if (w) tl.fromTo(w, { scale: 1.08 }, { scale: 1, duration: Math.max(0.2, sl.e - sl.s), ease: "none" }, sl.s);
  });
  tl.fromTo(page, { opacity: 0, y: 60 }, { opacity: 1, y: 0, duration: 0.35, ease: "power3.out" }, 0);
  // product name types from the title; price + rating roll in
  const name = page.querySelector(".name");
  K.type(tl, name, (I.title || "Product") + " - Premium Quality, Fast Shipping", 0.3, 1.4);
  const num = page.querySelector(".num"), sold = page.querySelector(".sold");
  K.count(tl, num, 0, 4.8, 0.6, 1.2, (v) => v.toFixed(1));
  K.count(tl, sold, 0, 12480, 0.6, 1.6, (v) => Math.round(v).toLocaleString("en-US") + " sold");
  const money = (I.lines.find((l) => l.money) || {}).money;
  page.querySelector(".was").textContent = money || "$1,500.00";
  // one thumbnail + one option chip per line; the cursor clicks each chip on the key word
  const thumbs = page.querySelector(".thumbs"), opts = page.querySelector(".opts");
  const lines = I.lines.filter((l) => l.role !== "go").slice(0, 6);
  let cx = 1500, cy = 900;
  tl.set(cur, { opacity: 1, x: cx, y: cy }, 0.5);
  lines.forEach((ln, k) => {
    const th = K.div("th", thumbs, "", K.glyphHTML(["tag", "box", "card", "cart", "gift", "check"][k % 6], 60, "#888"));
    tl.set(th, { opacity: 1 }, ln.s);
    tl.fromTo(th, { scale: 0.4 }, { scale: 1, duration: 0.25, ease: "back.out(2)" }, ln.s);
    const o = K.div("opt", opts, "", K.esc((ln.key || K.short(ln.text, 2)).slice(0, 18)));
    tl.set(o, { opacity: 1 }, ln.s + 0.05);
    const tx = 1060 + (k % 3) * 250, ty = 690 + Math.floor(k / 3) * 70;
    tl.to(cur, { x: tx, y: ty, duration: 0.35, ease: "power2.inOut" }, Math.max(ln.s, ln.keyT - 0.35));
    tl.to(o, { borderColor: "#ff6a00", color: "#ff6a00", duration: 0.05 }, ln.keyT);
    tl.fromTo(cur, { scale: 1 }, { scale: 0.8, duration: 0.08, yoyo: true, repeat: 1 }, ln.keyT);
  });
  // the turn: ADD TO CART click, badge pops, page zooms into the photo for the reveal
  const atc = page.querySelector(".atc"), badge = page.querySelector(".cart b");
  tl.to(cur, { x: 1200, y: 880, duration: 0.3, ease: "power2.inOut" }, turn - 0.45);
  tl.fromTo(atc, { scale: 1 }, { scale: 0.92, duration: 0.08, yoyo: true, repeat: 1 }, turn - 0.1);
  K.text(tl, badge, turn, "1");
  tl.fromTo(badge, { scale: 1 }, { scale: 1.8, duration: 0.12, yoyo: true, repeat: 1 }, turn);
  tl.to(page.querySelector(".now"), { color: "#0a9a44", duration: 0.2 }, turn + 0.3);
  tl.to(page, { scale: 2.05, x: 300, y: 130, duration: 0.6, ease: "power3.inOut" }, turn + 0.4);
  tl.to(cur, { opacity: 0, duration: 0.1 }, turn + 0.4);
  K.kinetic(tl, I.words.filter((w) => w.s >= turn + 0.5), { cls: "kin ui", lower: true, chunk: { max: 2, chars: 13 }, pos: () => ({ left: 960, top: 930, align: "center" }) });
  K.xp(tl, stage, { top: 40, label: "WATCH TO THE END" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  t1.textContent = I.title || "REVIEW";
  T.querySelector(".t2").textContent = I.sub || "review";
  K.fit(t1, 1500, 130, 50);
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(T.querySelector(".btn"), { scale: 0.3 }, { scale: 1, duration: 0.35, ease: "back.out(1.8)" }, t0);
  tl.fromTo(T.querySelector(".t2"), { opacity: 0 }, { opacity: 1, duration: 0.25 }, t0 + 0.4);
};

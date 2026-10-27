window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e;
  const hang = document.getElementById("hang"), tag = document.getElementById("tag");
  // blurred B-roll behind everything
  I.slots.forEach((sl) => K.mount(tl, sl, document.getElementById("back"), { fade: 0.2 }));
  // the tag swings like a pendulum the whole time (damped swings, re-kicked on the turn)
  const swing = (t0, t1, amp) => {
    let t = t0, a = amp, k = 0;
    while (t < t1) { tl.to(hang, { rotation: (k % 2 ? -1 : 1) * a, duration: 0.9, ease: "sine.inOut" }, t); t += 0.9; a *= 0.82; k++; }
  };
  tl.fromTo(hang, { y: -900 }, { y: 0, duration: 0.6, ease: "bounce.out" }, 0);
  swing(0.4, turn - 0.2, 9);
  const brand = (I.words.find((w) => w.c === "brand") || { w: I.title || "LUXURY" }).w;
  tag.querySelector(".front .brand").textContent = K.clean(brand);
  const money = (I.lines.find((l) => l.money) || {}).money || "$1,500";
  const price = tag.querySelector(".front .price");
  price.textContent = money;
  K.fit(price, 470, 140, 60);
  const slash = K.div("slash", price);
  tl.to(slash, { width: price.offsetWidth + 60, duration: 0.25, ease: "power2.out" }, turn - 0.6);
  // turn: flip to the dhgate side
  tl.to(tag, { rotationY: 180, duration: 0.5, ease: "back.out(1.4)" }, turn - 0.05);
  K.flash(tl, turn, "#fff", stage, 0.2);
  swing(turn + 0.3, last, 7);
  // key words hang off as small tags left and right
  const minis = document.getElementById("minis");
  I.lines.filter((l) => l.role !== "go").forEach((ln, k) => {
    const kw = K.lineWords(ln).find((w) => w.k) || null;
    if (!kw) return;
    const e = K.div("mini " + (kw.c || ""), minis, `left:${k % 2 ? 1290 : 230}px;top:${330 + (k % 3) * 170}px`, K.esc(ln.key || K.clean(kw.w)));
    gsap.set(e, { rotation: k % 2 ? 6 : -6, transformOrigin: "50% 0%" });
    tl.fromTo(e, { opacity: 0, y: -260 }, { opacity: 1, y: 0, duration: 0.35, ease: "back.out(1.8)" }, Math.max(ln.s, kw.s - 0.1));
    tl.to(e, { rotation: k % 2 ? -3 : 3, duration: 0.6, ease: "sine.inOut" }, Math.max(ln.s, kw.s - 0.1) + 0.35);
    tl.to(e, { opacity: 0, y: 40, duration: 0.15 }, K.end(ln) - 0.05);
  });
  K.vignette(stage, 0.5);
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE END" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  t1.textContent = I.title || "REVIEW";
  T.querySelector(".t2").textContent = I.sub || "review";
  K.fit(t1, 1700, 150, 60);
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));
  tl.to(hang, { y: -1200, duration: 0.4, ease: "power3.in" }, t0 - 0.2);
  tl.fromTo(T, { opacity: 0, y: 60 }, { opacity: 1, y: 0, duration: 0.45, ease: "power3.out" }, t0);
};

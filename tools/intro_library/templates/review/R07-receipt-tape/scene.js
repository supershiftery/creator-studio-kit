window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e;
  const r = K.rng(I.seed);
  // B-roll frame on the right
  const fr = document.getElementById("frame");
  tl.fromTo(fr, { opacity: 0, x: 200 }, { opacity: 1, x: 0, duration: 0.4, ease: "power3.out" }, 0.05);
  I.slots.forEach((sl) => {
    const w = K.mount(tl, sl, fr.querySelector(".in"), { fade: 0.06 });
    if (w) tl.fromTo(w, { scale: 1.12 }, { scale: 1, duration: Math.max(0.2, sl.e - sl.s), ease: "none" }, sl.s);
  });
  // a receipt prints: each line item grows the paper
  const brand = (I.words.find((w) => w.c === "brand") || { w: "STORE" }).w;
  const receipt = (el, head, lines, money, t0, cheap) => {
    el.querySelector(".hd").innerHTML = K.esc(head) + "<br>* * * * * *";
    const items = el.querySelector(".items");
    let total = 0, h = 150;
    tl.set(el, { height: 150 }, t0);
    tl.fromTo(el, { height: 0 }, { height: 150, duration: 0.3, ease: "none" }, t0);
    lines.forEach((ln, k) => {
      const v = cheap ? 18 + r() * 40 : 180 + r() * 520;
      total += v;
      const it = K.div("it", items, "", `<span>${K.esc(K.short((ln.key || K.clean(K.lineWords(ln)[0].w)).toUpperCase(), 3))}</span><span>${K.money(v)}</span>`);
      h += 58;
      tl.to(el, { height: h, duration: 0.25, ease: "none" }, ln.s);
      tl.set(it, { opacity: 1 }, ln.s + 0.12);
    });
    const tot = el.querySelector(".tot");
    tot.innerHTML = `<span>TOTAL</span><b>${K.esc(money || K.money(total))}</b>`;
    return { tot, h };
  };
  const pre = I.lines.filter((l) => l.s < turn - 0.05);
  const post = I.lines.filter((l) => l.s >= turn - 0.05 && l.role !== "go");
  const a = receipt(document.getElementById("r1"), brand.toUpperCase() + " RETAIL", pre, (pre.find((l) => l.money) || {}).money, 0.1, false);
  const tA = pre.length ? K.end(pre[pre.length - 1]) - 0.7 : turn - 0.7;
  tl.to(document.getElementById("r1"), { height: a.h + 110, duration: 0.2 }, tA);
  tl.set(a.tot, { opacity: 1 }, tA + 0.1);
  tl.fromTo(a.tot, { scale: 1.6 }, { scale: 1, duration: 0.25, ease: "power4.out" }, tA + 0.1);
  K.shake(tl, document.getElementById("r1"), tA + 0.15, 10, 0.25);
  // the turn: tear it off, print the DHgate order
  tl.to(document.getElementById("r1"), { y: 1300, rotation: -14, duration: 0.4, ease: "power3.in" }, turn - 0.2);
  const b = receipt(document.getElementById("r2"), "DHGATE ORDER", post, "", turn + 0.05, true);
  const tB = post.length ? post[post.length - 1].s + 0.6 : turn + 2;
  tl.to(document.getElementById("r2"), { height: b.h + 110, duration: 0.2 }, tB);
  tl.set(b.tot, { opacity: 1 }, tB + 0.1);
  K.pop(tl, document.getElementById("stamp"), tB + 0.4, { from: 2.2, rot: -10, rot2: -10, d: 0.2, ease: "power4.out" });
  // captions over the frame
  K.kinetic(tl, I.words, { cls: "kin mono", lower: true, chunk: { max: 2, chars: 13 }, pos: () => ({ left: 1290, top: 960, align: "center" }) });
  K.xp(tl, stage, { top: 40, label: "WATCH TO THE END" });
  K.grain(tl, stage, 0.1, I.seed);
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  t1.textContent = I.title || "REVIEW";
  T.querySelector(".t2").textContent = I.sub || "scam or steal?";
  K.fit(t1, 1700, 150, 60);
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(T, { clipPath: "inset(0 0 100% 0)" }, { clipPath: "inset(0 0 0% 0)", duration: 0.45, ease: "none" }, t0);
  tl.fromTo(T.querySelector(".t2"), { scale: 0 }, { scale: 1, duration: 0.25, ease: "back.out(2)" }, t0 + 0.5);
};

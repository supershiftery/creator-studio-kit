window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), space = document.getElementById("space"), turn = I.beats.turn, last = I.words[I.words.length - 1].e;
  const r = K.rng(I.seed);
  const pans = I.slots.map((sl, k) => {
    const p = K.div("pan", space);
    K.into(tl, sl, p);
    return { p, sl, side: k % 2 ? 1 : -1 };
  });
  // each new panel arrives at the front; earlier ones fall back, sideways and blurred (parallax depth)
  pans.forEach((o, k) => {
    const t = o.sl.s - 0.1;
    tl.set(o.p, { opacity: 1 }, t);
    tl.fromTo(o.p, { z: 700, x: o.side * 900, rotationY: -o.side * 40, filter: "blur(0px)" },
      { z: 0, x: o.side * 60, rotationY: -o.side * 12, rotationX: 4, duration: 0.45, ease: "power3.out" }, t);
    tl.to(o.p, { x: o.side * -30, rotationY: o.side * 6, duration: Math.max(0.2, o.sl.e - t - 0.45), ease: "none" }, t + 0.45);
    // when the next panel lands, this one recedes
    const nx = pans[k + 1];
    if (nx) {
      tl.to(o.p, { z: -900 - (k % 3) * 300, x: o.side * (600 + r() * 300), y: (r() - 0.5) * 500, rotationY: o.side * 25, filter: "blur(6px)", opacity: 0.55, duration: 0.5, ease: "power2.inOut" }, nx.sl.s - 0.1);
      tl.to(o.p, { opacity: 0, duration: 0.3 }, nx.sl.s + 1.6);
    }
  });
  // the turn: the camera rushes through the stack
  tl.fromTo(space, { z: 0 }, { z: 1200, duration: 0.35, ease: "power3.in", immediateRender: false }, turn - 0.35);
  tl.set(space, { z: 0 }, turn);
  K.flash(tl, turn, "#d9b8ff", stage, 0.3);
  K.kinetic(tl, I.words, { cls: "kin neo", lower: true, chunk: { max: 2, chars: 12 }, enter: (c) => (c.key ? "slam" : "blur"),
    pos: (c, i) => ({ left: 960 + (i % 3 - 1) * 280, top: 880, align: "center" }) });
  K.grain(tl, stage, 0.1, I.seed);
  K.xp(tl, stage, { top: 70, label: "WATCH TO THE END" });
  // title: panels line up as a wall behind it
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  t1.textContent = I.title || "REVIEW";
  T.querySelector(".t2").textContent = I.sub || "review";
  K.fit(t1, 1700, 160, 60);
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));
  pans.slice(-4).forEach((o, k) => {
    tl.to(o.p, { opacity: 0.35, z: -1400, x: (k - 1.5) * 1250, y: 0, rotationY: 0, rotationX: 0, filter: "blur(3px)", duration: 0.5, ease: "power3.out" }, t0 - 0.2);
  });
  tl.fromTo(T, { opacity: 0, scale: 0.7 }, { opacity: 1, scale: 1, duration: 0.4, ease: "back.out(1.6)" }, t0);
};

window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e;
  const cover = document.getElementById("cover"), lines = cover.querySelector(".lines");
  const brand = (I.words.find((w) => w.c === "brand") || {}).w;
  cover.querySelector(".mast").textContent = (brand ? K.clean(brand) : "REVIEW").toUpperCase().slice(0, 8);
  K.fit(cover.querySelector(".mast"), 780, 220, 90);
  tl.fromTo(cover, { opacity: 0, rotationY: -30, x: 300 }, { opacity: 1, rotationY: -8, x: 0, duration: 0.6, ease: "power3.out" }, 0);
  tl.to(cover, { rotationY: 6, duration: Math.max(0.4, turn - 0.6), ease: "sine.inOut" }, 0.6);
  I.slots.forEach((sl) => {
    const w = K.mount(tl, sl, cover.querySelector(".photo"), { fade: 0.08 });
    if (w) tl.fromTo(w, { scale: 1.15 }, { scale: 1.02, duration: Math.max(0.2, sl.e - sl.s), ease: "none" }, sl.s);
  });
  // cover lines: corners in turn, the key word big italic
  const corners = [[36, 300], [430, 560], [36, 700], [430, 300], [36, 500], [430, 760]];
  let n = 0;
  const addLines = (ls, t0) => ls.forEach((ln) => {
    const c = corners[n++ % corners.length];
    const e = K.div("cl", lines, `left:${c[0]}px;top:${c[1]}px`, `<em>${K.esc(ln.key || "")}</em>${K.esc(K.short(ln.text, 5))}`);
    tl.fromTo(e, { opacity: 0, x: c[0] < 200 ? -40 : 40 }, { opacity: 1, x: 0, duration: 0.25, ease: "power3.out" }, Math.max(ln.s, ln.keyT - 0.1));
    tl.to(e, { opacity: 0, duration: 0.12 }, Math.min(K.end(ln) + 2.2, t0 || I.dur));
  });
  const pre = I.lines.filter((l) => l.s < turn - 0.05), post = I.lines.filter((l) => l.s >= turn - 0.05 && l.role !== "go");
  addLines(pre, turn - 0.3);
  // the turn: page turn to the next issue
  tl.to(cover, { rotationY: -100, duration: 0.3, ease: "power2.in" }, turn - 0.3);
  tl.set(cover, { rotationY: 80 }, turn);
  tl.to(cover, { rotationY: -6, duration: 0.45, ease: "power3.out" }, turn);
  K.pop(tl, cover.querySelector(".badge"), turn + 0.6, { from: 2, rot: 14, rot2: 14, d: 0.25, ease: "power4.out" });
  addLines(post, null);
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE END" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  t1.textContent = I.title || "Review";
  T.querySelector(".t2").textContent = I.sub || "the honest review";
  K.fit(t1, 1720, 170, 70);
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(T, { clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)", duration: 0.45, ease: "power3.inOut" }, t0);
  tl.fromTo(t1, { letterSpacing: "20px" }, { letterSpacing: "-4px", duration: 0.8, ease: "power3.out" }, t0);
};

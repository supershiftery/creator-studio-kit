window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e;
  const box = document.getElementById("box"), lid = box.querySelector(".lid"), cold = document.getElementById("cold"), rise = document.getElementById("rise");
  // box breathes under the light, jolts on each problem line
  // the box is a small emblem under the big footage panel (it used to fill the lower half, the footage squeezed above it)
  tl.set(box, { transformOrigin: "50% 100%", scale: 0.5 }, 0);
  tl.fromTo(box, { y: 400, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, ease: "power3.out" }, 0);
  const pre = I.lines.filter((l) => l.s < turn - 0.05);
  pre.forEach((ln) => { tl.to(lid, { y: -24, rotation: -3, duration: 0.1, yoyo: true, repeat: 1, ease: "power2.out" }, Math.max(ln.s, ln.keyT)); });
  tl.to(box, { scale: 0.54, duration: Math.max(0.3, turn - 0.5), ease: "sine.inOut" }, 0.5);
  // cold B-roll above the box in the problem half
  const preSlots = I.slots.filter((s) => s.s < turn - 0.1);
  if (preSlots.length) tl.fromTo(cold, { opacity: 0 }, { opacity: 0.9, duration: 0.3 }, preSlots[0].s);
  preSlots.forEach((sl) => K.mount(tl, sl, cold.querySelector(".in"), { fade: 0.1 }));
  tl.to(cold, { opacity: 0, duration: 0.2 }, turn - 0.25);
  // the turn: lid off, rays, the reveal rises out of the box
  tl.to(lid, { y: -900, x: 300, rotation: 50, duration: 0.5, ease: "power2.out" }, turn);
  K.flash(tl, turn, "#ffe9b0", stage, 0.35);
  const rays = document.getElementById("rays");
  K.div("", rays);
  tl.set(rays, { opacity: 1 }, turn);
  tl.fromTo(rays, { scale: 0.3, rotation: 0 }, { scale: 1, rotation: 40, duration: I.dur - turn, ease: "none" }, turn);
  K.dust(tl, stage, { n: 50, color: "rgba(255,220,150,.8)", seed: I.seed });
  tl.to(box.querySelector(".front"), { color: "#fff", duration: 0.2 }, turn);
  tl.set(rise, { opacity: 1 }, turn + 0.15);
  tl.fromTo(rise, { y: 560, scale: 0.35 }, { y: 0, scale: 1, duration: 0.55, ease: "back.out(1.3)" }, turn + 0.15);
  tl.to(box, { y: 300, opacity: 0.6, duration: 0.5 }, turn + 0.4);
  I.slots.filter((s) => s.s >= turn - 0.1).forEach((sl) => K.mount(tl, sl, rise.querySelector(".in"), { fade: 0.06 }));
  K.kinetic(tl, I.words, { cls: "kin glow", lower: true, chunk: { max: 2, chars: 13 }, enter: (c) => (c.key ? "scale" : "pop"),
    pos: (c) => (c.s < turn ? { left: 960, top: 720, align: "center" } : { left: 960, top: 930, align: "center" }) });
  K.grain(tl, stage, 0.14, I.seed);
  K.xp(tl, stage, { top: 40, label: "WATCH TO THE END" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  t1.textContent = I.title || "REVIEW";
  T.querySelector(".t2").textContent = I.sub || "unboxing";
  K.fit(t1, 1700, 150, 60);
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));
  tl.to(rise, { opacity: 0, scale: 0.9, duration: 0.25 }, t0 - 0.1);
  tl.fromTo(T, { opacity: 0, scale: 0.85 }, { opacity: 1, scale: 1, duration: 0.5, ease: "power3.out" }, t0);
};

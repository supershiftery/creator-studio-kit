window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e;
  const view = document.getElementById("view"), read = view.querySelector(".read"), list = document.querySelector("#panel .list");
  const needle = document.querySelector(".meter .needle");
  tl.fromTo([view, document.getElementById("panel")], { opacity: 0, scale: 1.05 }, { opacity: 1, scale: 1, duration: 0.35, stagger: 0.1, ease: "power3.out" }, 0);
  I.slots.forEach((sl) => {
    const w = K.mount(tl, sl, view.querySelector(".in"), { fade: 0.06 });
    if (w) tl.fromTo(w, { scale: 1.18 }, { scale: 1.04, duration: Math.max(0.2, sl.e - sl.s), ease: "power1.out" }, sl.s);
  });
  // the scan line sweeps up and down the whole time
  const n = Math.floor(I.dur / 1.6);
  tl.fromTo(view.querySelector(".scanl"), { y: 0 }, { y: 860, duration: 0.8, ease: "sine.inOut", yoyo: true, repeat: Math.max(0, n * 2 - 1) }, 0);
  // checklist: one item per line; problem items get "?" or a cross, reveal items a green tick
  const lines = I.lines.filter((l) => l.role !== "go").slice(0, 9);
  lines.forEach((ln, k) => {
    const bad = ln.s < turn - 0.05;
    const it = K.div("chk", list, "", `<b>${bad ? "?" : "✓"}</b><span>${K.esc((ln.key || K.short(ln.text, 2)).slice(0, 16))}</span>`);
    tl.fromTo(it, { opacity: 0, x: 40 }, { opacity: 1, x: 0, duration: 0.2 }, Math.max(ln.s, ln.keyT - 0.1));
    if (!bad) tl.fromTo(it.querySelector("b"), { backgroundColor: "rgba(0,0,0,0)" }, { backgroundColor: "#36ff8f", color: "#04110a", borderColor: "#36ff8f", duration: 0.15 }, Math.max(ln.s, ln.keyT));
    if (k >= 6) tl.to(list.children[k - 6], { opacity: 0, height: 0, duration: 0.2 }, Math.max(ln.s, ln.keyT - 0.1));
  });
  // needle wobbles undecided, then swings to REAL after the turn
  let t = 0.6, a = 1;
  while (t < turn - 0.3) { tl.to(needle, { rotation: (a % 2 ? 1 : -1) * (12 + (a * 7) % 18), duration: 0.5, ease: "sine.inOut" }, t); t += 0.5; a++; }
  tl.to(needle, { rotation: 62, duration: 0.6, ease: "back.out(2)" }, turn + 0.3);
  tl.to(".meter .q", { opacity: 0, duration: 0.2 }, turn + 0.3);
  K.text(tl, read, turn, "MATCH FOUND ✓");
  tl.to(read, { color: "#36ff8f", duration: 0.1 }, turn);
  tl.to(document.documentElement, { "--hud": "#36ff8f", duration: 0.3 }, turn);
  K.flash(tl, turn, "#36ff8f", stage, 0.25);
  K.kinetic(tl, I.words, { cls: "kin hud", lower: true, chunk: { max: 2, chars: 12 }, pos: () => ({ left: 650, top: 860, align: "center" }) });
  K.scan(stage, 0.4);
  K.xp(tl, stage, { top: 20, label: "WATCH TO THE END" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  t1.textContent = I.title || "REVIEW";
  T.querySelector(".t2").textContent = I.sub || "legit or not?";
  K.fit(t1, 1720, 150, 60);
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));
  tl.set(T, { opacity: 1 }, t0);
  K.type(tl, t1, (I.title || "REVIEW").toUpperCase(), t0 + 0.1, 0.5, "_");
  tl.fromTo(T.querySelector(".t2"), { opacity: 0, scale: 0.6 }, { opacity: 1, scale: 1, duration: 0.25, ease: "back.out(2)" }, t0 + 0.7);
};

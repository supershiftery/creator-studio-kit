window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e;
  const arch = document.getElementById("arch"), words = document.getElementById("words");
  tl.fromTo(arch, { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 1.0, ease: "power2.out" }, 0.1);
  tl.to(arch, { scale: 1.02, duration: I.dur, ease: "sine.inOut" }, 0);
  I.slots.forEach((sl) => {
    const w = K.mount(tl, sl, arch.querySelector(".in"), { fade: 0.35 });
    if (w) tl.fromTo(w, { scale: 1.1 }, { scale: 1.0, duration: Math.max(0.3, sl.e - sl.s), ease: "none" }, sl.s);
  });
  tl.to("#rule1", { width: 820, duration: 0.9, ease: "power2.inOut" }, 0.2);
  tl.to("#rule2", { width: 820, duration: 0.9, ease: "power2.inOut" }, 0.35);
  // one phrase per line: small spaced caps of the line + the key word in italic serif, slow crossfades
  I.lines.filter((l) => l.role !== "go").forEach((ln) => {
    const p = K.div("ph", words);
    const key = ln.key || K.clean(K.lineWords(ln).slice(-1)[0].w);
    const rest = ln.text.split(key).join(" ").replace(/\s+/g, " ");
    p.innerHTML = '<div class="small">' + K.esc(K.short(rest, 7)) + '</div><div class="big">' + K.esc(key) + "</div>";
    K.fit(p.querySelector(".big"), 820, 118, 60);
    tl.fromTo(p, { opacity: 0, y: 16 }, { opacity: 1, y: 0, duration: 0.45, ease: "power2.out" }, ln.s);
    tl.to(p, { opacity: 0, duration: 0.3 }, K.end(ln) - 0.3);
  });
  // the turn: a gold line sweeps across the whole frame
  const sweep = K.div("rule", stage, "left:0;top:540px;z-index:30");
  tl.fromTo(sweep, { width: 0, opacity: 1 }, { width: 1920, duration: 0.6, ease: "power3.inOut" }, turn - 0.3);
  tl.to(sweep, { opacity: 0, duration: 0.4 }, turn + 0.4);
  K.xp(tl, stage, { top: 820, label: "watch to the end" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  t1.textContent = I.title || "REVIEW";
  T.querySelector(".t2").textContent = I.sub || "the review";
  T.querySelector(".mono").textContent = (I.title || "R").trim()[0];
  K.fit(t1, 1700, 130, 50);
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));
  tl.fromTo(T, { opacity: 0 }, { opacity: 1, duration: 0.6, ease: "power2.out" }, t0);
  tl.fromTo(t1, { letterSpacing: "40px", opacity: 0 }, { letterSpacing: "18px", opacity: 1, duration: 1.1, ease: "power2.out" }, t0 + 0.1);
  tl.to(T.querySelector(".rule3"), { width: 600, duration: 0.8, ease: "power2.inOut" }, t0 + 0.4);
};

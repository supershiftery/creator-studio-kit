window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e;
  const foot = document.getElementById("foot"), masks = document.getElementById("masks");
  I.slots.forEach((sl) => {
    const w = K.mount(tl, sl, foot, { fade: 0.04 });
    if (w) tl.fromTo(w, { scale: 1.15 }, { scale: 1.0, duration: Math.max(0.2, sl.e - sl.s), ease: "power1.out" }, sl.s);
  });
  I.lines.filter((l) => l.role !== "go").forEach((ln) => {
    const word = (ln.key || K.short(ln.text, 1)).split(" ").slice(0, 2).join(" ");
    const t = Math.max(ln.s, ln.keyT - 0.05), end = K.end(ln);
    if (ln.s < turn - 0.05) {
      // the footage only inside the letters, then the word punches out to full frame
      const m = K.div("mask", masks, "", "<span>" + K.esc(word) + "</span>");
      K.fit(m.querySelector("span"), 1840, 520, 160);
      tl.set(m, { opacity: 1 }, ln.s - 0.02);
      tl.fromTo(m.querySelector("span"), { scale: 0.85 }, { scale: 1.0, duration: Math.max(0.3, t - ln.s + 0.6), ease: "power2.out" }, ln.s - 0.02);
      tl.to(m.querySelector("span"), { scale: 9, duration: 0.35, ease: "power3.in" }, Math.min(end - 0.4, t + 0.9));
      tl.set(m, { opacity: 0 }, Math.min(end - 0.05, t + 1.25));
    } else {
      const o = K.div("over" + (ln.key ? " key" : ""), masks, "", "<span>" + K.esc(word) + "</span>");
      K.fit(o.querySelector("span"), 1800, 360, 120);
      tl.fromTo(o, { opacity: 0, scale: 1.4 }, { opacity: 1, scale: 1, duration: 0.16, ease: "power4.out" }, t);
      tl.to(o, { opacity: 0, duration: 0.12 }, Math.min(end - 0.05, t + 1.2));
    }
  });
  K.flash(tl, turn, "#fff", stage, 0.2);
  K.shake(tl, stage, turn, 14, 0.3);
  K.kinetic(tl, I.words, { cls: "kin low", lower: true, chunk: { max: 3, chars: 18 }, pos: () => ({ left: 960, top: 1000, align: "center" }) });
  K.xp(tl, stage, { top: 40, label: "WATCH TO THE END" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  t1.textContent = I.title || "REVIEW";
  T.querySelector(".t2").textContent = I.sub || "review";
  K.fit(t1, 1820, 300, 90);
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(t1, { scale: 3 }, { scale: 1, duration: 0.35, ease: "power4.out" }, t0);
  tl.fromTo(T.querySelector(".t2"), { opacity: 0 }, { opacity: 1, duration: 0.3 }, t0 + 0.4);
};

window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e;
  const tv = document.getElementById("tv"), card = document.getElementById("card"), rows = card.querySelector(".rows");
  tl.fromTo(tv, { opacity: 0, x: -200 }, { opacity: 1, x: 0, duration: 0.4, ease: "power3.out" }, 0.05);
  tl.fromTo(card, { opacity: 0, x: 200 }, { opacity: 1, x: 0, duration: 0.4, ease: "power3.out" }, 0.15);
  I.slots.forEach((sl) => {
    const w = K.mount(tl, sl, tv.querySelector(".in"), { fade: 0.05 });
    if (w) tl.fromTo(w, { scale: 1.1 }, { scale: 1, duration: Math.max(0.2, sl.e - sl.s), ease: "none" }, sl.s);
  });
  // categories: fixed review axes, each revealed on a line; scores spin and stop on "?" until the turn
  const CATS = ["QUALITY", "PRICE", "LOOKS", "FIT", "MATERIAL", "SHIPPING"];
  const lines = I.lines.filter((l) => l.role !== "go");
  const n = Math.min(5, lines.length);
  const rs = [];
  for (let k = 0; k < n; k++) {
    const ln = lines[k];
    const row = K.div("row", rows, "", `<div class="nm"><span>${CATS[k]}</span><b>?</b></div><div class="bar"><i></i></div>`);
    tl.fromTo(row, { opacity: 0, x: 60 }, { opacity: 1, x: 0, duration: 0.25, ease: "power3.out" }, ln.s);
    const b = row.querySelector(".nm b"), bar = row.querySelector(".bar i");
    gsap.set(bar, { scaleX: 0 });
    // slot-reel digits then "?"
    for (let j = 0; j < 6; j++) K.text(tl, b, ln.s + 0.05 + j * 0.07, String((j * 7 + k * 3) % 10));
    K.text(tl, b, ln.s + 0.5, "?");
    tl.to(bar, { scaleX: 0.3 + ((k * 37) % 50) / 100, duration: 0.35, ease: "power2.out" }, ln.s + 0.1);
    tl.to(bar, { scaleX: 0.15, duration: 0.3, ease: "power2.inOut" }, ln.s + 0.55);
    rs.push({ b, bar });
  }
  // the turn: the card flips gold, bars fill (still no numbers: the verdict is in the video)
  tl.to(card.querySelector(".hd"), { backgroundColor: "#ffb400", color: "#0b1d3a", duration: 0.2 }, turn);
  rs.forEach((o, k) => tl.to(o.bar, { scaleX: 0.75 + (k % 3) * 0.08, backgroundColor: "#ffb400", duration: 0.6, ease: "power2.out" }, turn + 0.1 + k * 0.08));
  K.flash(tl, turn, "#ffcc33", stage, 0.25);
  // ticker of key words crawling along the bottom
  const tk = document.querySelector("#ticker .tk");
  tk.innerHTML = I.lines.map((l) => l.key).filter(Boolean).map((k) => "★ " + K.esc(k)).join("&nbsp;&nbsp;&nbsp;").repeat(2);
  tl.fromTo("#ticker", { opacity: 0, y: 90 }, { opacity: 1, y: 0, duration: 0.3 }, 0.6);
  tl.fromTo(tk, { x: 1920 }, { x: -tk.scrollWidth / 2, duration: I.dur, ease: "none" }, 0.6);
  K.xp(tl, stage, { top: 20, label: "WATCH TO THE END" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  t1.textContent = I.title || "REVIEW";
  T.querySelector(".t2").textContent = I.sub || "the verdict";
  K.fit(t1, 1700, 130, 50);
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(T.querySelector(".big"), { scale: 0.2, rotation: -10 }, { scale: 1, rotation: 0, duration: 0.35, ease: "back.out(1.8)" }, t0);
  tl.fromTo([t1, T.querySelector(".t2")], { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.3, stagger: 0.12 }, t0 + 0.3);
};

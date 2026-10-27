window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e;
  // a phone on the left, the key word big on the right
  const ph = K.phone(document.getElementById("dev"), { x: 160, y: 40, w: 620, h: 1260, color: "#1b1b1d", wall: "#fff" });
  gsap.set(ph.frame, { rotation: -3 });
  tl.fromTo(ph.frame, { y: 1100 }, { y: 0, duration: 0.5, ease: "power3.out" }, 0);
  // the phone keeps swaying in the hand between bubbles (the thread alone left over a quarter of the frames still)
  const sway = 1.6, n = Math.max(1, Math.floor((I.dur - 0.6) / sway));
  tl.to(ph.frame, { y: -36, rotation: -1, duration: sway, ease: "sine.inOut", yoyo: true, repeat: n - 1 }, 0.5);
  const hdr = K.div("hdr", ph.screen, "", '<div class="av">' + K.glyphHTML("person", 44, "#fff") + '</div><div>Bro</div>');
  const th = K.div("thread", ph.screen), feed = K.div("feed", th);
  // the feed grows from the bottom; each new bubble pushes the stack up by its height (measured once, seek-safe)
  const add = (el, t) => {
    el.style.display = "none";
    tl.set(el, { display: el.classList.contains("dots") ? "flex" : "block", opacity: 1 }, t);
    tl.fromTo(el, { scale: 0.6, y: 30 }, { scale: 1, y: 0, duration: 0.22, ease: "back.out(2)" }, t);
  };
  const q = K.div("b them", feed, "", "yo where'd you get that??");
  add(q, 0.15);
  const bubbles = [];
  I.lines.filter((l) => l.role !== "go").forEach((ln, k) => {
    if (ln.role === "turn") {
      const d = K.div("dots", feed, "", "<i></i><i></i><i></i>");
      add(d, ln.s - 0.6);
      tl.set(d, { display: "none" }, ln.s - 0.05);
      add(K.div("b them", feed, "", "WAIT WHAT"), ln.s - 0.05);
    }
    const html = K.lineWords(ln).map((w) => (w.k ? "<b>" + K.esc(w.w) + "</b>" : K.esc(w.w))).join(" ");
    const b = K.div("b me", feed, "", html);
    add(b, ln.s + 0.05);
    const sl = K.slotFor(ln);
    if (sl) {
      const pic = K.div("b me pic", feed, "", '<div class="in"></div>');
      K.into(tl, sl, pic.querySelector(".in"));
      add(pic, sl.s + 0.4);
    }
  });
  K.kinetic(tl, I.words.filter((w) => w.k), { cls: "kin chat", lower: true, chunk: { max: 2, chars: 14 }, enter: "scale", pos: (c, i) => ({ left: 1370, top: 420 + (i % 3) * 140, align: "center" }) });
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE END" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  t1.textContent = I.title || "REVIEW";
  T.querySelector(".t2").textContent = I.sub || "review";
  K.fit(t1, 1700, 160, 60);
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(T, { yPercent: -100 }, { yPercent: 0, duration: 0.4, ease: "power3.out" }, t0);
  tl.fromTo(T.querySelector(".t2"), { scale: 0 }, { scale: 1, duration: 0.25, ease: "back.out(2)" }, t0 + 0.4);
};

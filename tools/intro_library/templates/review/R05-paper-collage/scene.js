window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e;
  const board = document.getElementById("board"), strips = document.getElementById("strips"), sheet2 = document.getElementById("sheet2");
  K.tex("paper.jpg", document.getElementById("paper"));
  K.dust(tl, stage, { n: 70, seed: I.seed });
  const r = K.rng(I.seed + 5);
  const print = (parent, sl, x, y, w, h, rot, bw) => {
    const p = K.div("print" + (bw ? " bw" : ""), parent, `left:${x}px;top:${y}px;width:${w}px;height:${h}px`);
    const inn = K.div("in", p);
    if (sl) K.into(tl, sl, inn);
    K.div("tape", p, `left:${w / 2 - 75}px;top:-22px;transform:rotate(${(r() - 0.5) * 10}deg)`);
    gsap.set(p, { rotation: rot });
    return { p, inn };
  };
  // the whole desk drifts the entire time (amiri jeans 2026-10-22: "more motion graphics, more movement in general")
  tl.fromTo(board, { scale: 1, x: 0 }, { scale: 1.07, x: -40, y: -20, duration: Math.max(1, turn), ease: "none" }, 0);
  // problem half: one taped print PER CLIP (not per line: a line with two clips kept its first print up after that clip
  // ended, a black card, amiri jeans 0:02), big, alternating sides, the shot pushing in while it plays
  const preSl = I.slots.filter((s) => s.s < turn - 0.05);
  preSl.forEach((sl, k) => {
    const left = k % 2 === 0, nx = preSl[k + 1];
    const { p, inn } = print(board, sl, left ? 110 : 700, 150 + (k % 3) * 24, 1080, 608, left ? -4 : 3, true);
    const out = nx ? nx.s + 0.2 : sl.e + 0.15;   // the next print lands on top, then this one leaves
    tl.set(p, { opacity: 1 }, sl.s - 0.05);
    tl.fromTo(p, { scale: 1.35, y: -70, rotation: left ? -12 : 10 }, { scale: 1, y: 0, rotation: left ? -4 : 3, duration: 0.28, ease: "power3.out" }, sl.s - 0.05);
    tl.fromTo(inn, { scale: 1 }, { scale: 1.1, duration: Math.max(0.3, out - sl.s), ease: "none" }, sl.s);
    tl.to(p, { x: left ? -260 : 260, opacity: 0, duration: 0.2, ease: "power2.in" }, out);
    if (k) K.shake(tl, board, sl.s, 5, 0.15);
  });
  const pre = I.lines.filter((l) => l.s < turn - 0.05);
  pre.forEach((ln, k) => {
    const end = K.end(ln), left = k % 2 === 0;
    const st = K.div("strip", strips, `left:${left ? 760 : 160}px;top:${740 + (k % 2) * 60}px`);
    const ws = K.lineWords(ln).filter((w) => w.k || w.c === "neg").slice(0, 3);
    st.innerHTML = (ws.length ? ws : K.lineWords(ln).slice(-2)).map((w) => `<span class="${w.k ? "k" : w.c || ""}">${K.esc(K.clean(w.w).toLowerCase())}</span>`).join(" ");
    gsap.set(st, { rotation: left ? 2 : -3 });
    tl.fromTo(st, { opacity: 0, x: left ? 200 : -200 }, { opacity: 1, x: 0, duration: 0.2, ease: "power3.out" }, Math.max(ln.s + 0.1, ln.keyT - 0.1));
    tl.set(st, { opacity: 0 }, end - 0.02);
  });
  // the turn: a fresh sheet slides over and drifts; never an empty page (amiri jeans 0:11, "it just goes completely white")
  K.tex("paper.jpg", sheet2, "filter:hue-rotate(-8deg) brightness(1.03)");
  tl.set(sheet2, { opacity: 1 }, turn - 0.3);
  tl.fromTo(sheet2, { x: 1920 }, { x: 0, duration: 0.3, ease: "power3.out" }, turn - 0.3);
  tl.fromTo(sheet2, { scale: 1 }, { scale: 1.06, duration: Math.max(1, I.dur - turn), ease: "none" }, turn);
  const post = I.slots.filter((s) => s.s >= turn - 0.1);
  const firstPost = post.length ? post[0].s : last;
  // turn card: the brand vs DHgate, stamped down until the first reveal shot lands
  if (firstPost - turn > 0.5) {
    const vs = K.div("", sheet2, "position:absolute;inset:0;z-index:15");
    const card = (x, rot, html) => {
      const c = K.div("print", vs, `left:${x}px;top:250px;width:640px;height:420px;display:flex;align-items:center;justify-content:center;opacity:1`, html);
      gsap.set(c, { rotation: rot });
      K.div("tape", c, `left:245px;top:-22px`);
      return c;
    };
    const a = card(170, -5, I.brandLogo ? `<img src="${I.brandLogo}" style="max-width:520px;max-height:200px;object-fit:contain">`
      : `<div style="font:400 120px Anton;color:#111">${K.esc((I.brand || "RETAIL").toUpperCase())}</div>`);
    const b = card(1110, 4, I.dhLogo ? `<div style="display:flex;align-items:center;gap:22px"><img src="${I.dhLogo}" style="width:150px;height:150px;border-radius:32px">` +
      `<div style="font:900 104px Poppins;color:#111">DH<span style="color:#f5a300">gate</span></div></div>` : `<div style="font:400 120px Anton;color:#111">DUPE</div>`);
    const v = K.div("", vs, "position:absolute;left:860px;top:380px;width:200px;height:160px;display:flex;align-items:center;justify-content:center;" +
      "font:400 130px Anton;color:#fff;background:#c4161c;box-shadow:0 12px 26px rgba(0,0,0,.35)", "VS");
    gsap.set([a, b, v], { opacity: 0 });
    tl.fromTo(a, { opacity: 0, x: -700, rotation: -20 }, { opacity: 1, x: 0, rotation: -5, duration: 0.28, ease: "power3.out" }, turn - 0.05);
    tl.fromTo(b, { opacity: 0, x: 700, rotation: 20 }, { opacity: 1, x: 0, rotation: 4, duration: 0.28, ease: "power3.out" }, turn + 0.2);
    tl.fromTo(v, { opacity: 0, scale: 3, rotation: -25 }, { opacity: 1, scale: 1, rotation: -6, duration: 0.2, ease: "power4.out" }, turn + 0.45);
    K.shake(tl, sheet2, turn + 0.5, 10, 0.2);
    tl.to(vs, { y: -1100, duration: 0.3, ease: "power2.in" }, firstPost - 0.1);
  }
  // reveal shots stack into a three-photo collage, big; a held print shows its clip's last frame (build_intro poster)
  const spots = [[60, 60, 960, 560, -5], [900, 120, 960, 560, 4], [400, 430, 1060, 600, -1]];
  post.forEach((sl, k) => {
    const sp = spots[k % 3];
    const { p, inn } = print(sheet2, sl, sp[0], sp[1], sp[2], sp[3], sp[4], false);
    const off = (post[k + 3] || {}).s || I.dur;
    tl.set(p, { opacity: 1 }, sl.s);
    tl.fromTo(p, { scale: 1.6, rotation: sp[4] * 4 }, { scale: 1, rotation: sp[4], duration: 0.28, ease: "power3.out" }, sl.s);
    tl.fromTo(inn, { scale: 1 }, { scale: 1.12, duration: Math.max(0.3, off - sl.s), ease: "none" }, sl.s);
    tl.set(p, { opacity: 0 }, off);
    if (k % 3 === 2 || k === post.length - 1) K.shake(tl, sheet2, sl.s + 0.05, 8, 0.2);
  });
  // reveal words: strips again, bottom-left, red key words
  I.lines.filter((l) => l.s >= turn - 0.05 && l.role !== "go").forEach((ln, k) => {
    const st = K.div("strip", sheet2, `left:${90 + (k % 2) * 40}px;top:${880 - (k % 2) * 30}px;z-index:20`);
    const ws = K.lineWords(ln).filter((w) => w.k).slice(0, 3);
    st.innerHTML = (ws.length ? ws : K.lineWords(ln).slice(-2)).map((w) => `<span class="${w.k ? "k" : ""}">${K.esc(K.clean(w.w).toLowerCase())}</span>`).join(" ");
    gsap.set(st, { rotation: k % 2 ? 2 : -2 });
    tl.fromTo(st, { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.18 }, Math.max(ln.s, ln.keyT - 0.1));
    tl.set(st, { opacity: 0 }, Math.min(K.end(ln), last + 0.1) - 0.02);   // gone before the title, never peeking under it
  });
  K.xp(tl, stage, { top: 40, label: "WATCH TO THE END" });
  K.vignette(stage, 0.35);
  // title: a clean brand lockup on a torn sheet ("Amiri Jeans on DHgate" + the DHgate logo), not ransom letters
  const T = document.getElementById("title");
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));
  tl.set(T, { opacity: 1 }, t0);
  tl.to(sheet2, { opacity: 0.25, duration: 0.2 }, t0);
  const pad = K.div("", T, "position:absolute;left:310px;top:150px;width:1300px;height:780px;background:#fffdf7;box-shadow:0 24px 60px rgba(60,40,10,.35);" +
    "clip-path:polygon(0 3%, 6% 0, 20% 2%, 38% 0, 55% 3%, 72% 0, 90% 2%, 100% 0, 99% 97%, 85% 100%, 66% 98%, 47% 100%, 28% 97%, 10% 100%, 0 98%)");
  tl.fromTo(pad, { opacity: 0, y: 1080, rotation: 6 }, { opacity: 1, y: 0, rotation: -1.5, duration: 0.25, ease: "power3.out" }, t0);
  K.lockup(tl, T, t0 + 0.12, { z: 46 });
};

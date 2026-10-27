// THEME over the gaming scene bank: nether boss arena. Rising embers behind every scene; a boss bar across the top (named after
// the problem) charges up through the problem half and is hit down chunk by chunk on every reveal line; flash cuts; BOSS DEFEATED title.
window.CAMERA = { intensity: 1.2 };
window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn;
  K.embers(tl, document.getElementById("embers"), { n: 46, seed: I.seed });
  const d = K.director(tl, { cut: "flash" });
  const boss = document.getElementById("boss"), hp = boss.querySelector(".hp"), ghost = boss.querySelector(".ghost");
  const pre = I.lines.filter((l) => l.s < turn - 0.1), post = I.lines.filter((l) => l.s >= turn - 0.1 && l.role !== "go");
  const bossName = (pre.map((l) => l.key).filter((k) => k && !/unfortunately|sadly/i.test(k)).sort((a, b) => b.length - a.length)[0] || "THE PROBLEM").toUpperCase().slice(0, 20);
  K.pixo(bossName, 6, ["#fff", "#f0d6ff"], {}, boss.querySelector(".name"));
  tl.fromTo(boss, { opacity: 0, y: -80 }, { opacity: 1, y: 0, duration: 0.3, ease: "power3.out" }, 0.1);
  gsap.set([hp, ghost], { scaleX: 0 });
  pre.forEach((ln, k) => tl.to([hp, ghost], { scaleX: Math.min(1, 0.3 + ((k + 1) / pre.length) * 0.7), duration: 0.35, ease: "power2.out" }, ln.s + 0.1));
  let now = 1;
  post.forEach((ln, k) => {
    const t = Math.max(ln.s, ln.keyT - 0.05), to = Math.max(0.06, 1 - (k + 1) / (post.length + 1));
    tl.to(hp, { scaleX: to, duration: 0.12, ease: "power4.out" }, t);
    tl.to(ghost, { scaleX: to, duration: 0.5, ease: "power2.inOut" }, t + 0.25);
    const dm = K.div("", boss, `position:absolute;right:${-40 - (k % 2) * 60}px;top:${50 + (k % 3) * 24}px;opacity:0`);
    K.pixo("-" + Math.round((now - to) * 100) + "%", 6, ["#ffe25a", "#ff9d00"], {}, dm);
    tl.fromTo(dm, { opacity: 0, y: 20, scale: 1.6 }, { opacity: 1, y: -10, scale: 1, duration: 0.22 }, t);
    tl.to(dm, { opacity: 0, y: -50, duration: 0.35 }, t + 0.6);
    if (k < 2) K.shake(tl, boss, t, 10, 0.22);
    now = to;
  });
  K.xp(tl, stage, { top: 980, label: "WATCH TO THE VERY END" });
  const t0 = d.t0title;
  tl.to(hp, { scaleX: 0, duration: 0.1 }, t0 - 0.3);
  tl.to(ghost, { scaleX: 0, duration: 0.3 }, t0 - 0.25);
  const T = document.getElementById("title");
  K.pixo("BOSS DEFEATED", 9, ["#80ff20", "#3cc43c"], {}, T);
  const words = (I.title || "LET'S GO").toUpperCase(), ps = Math.max(10, Math.min(26, Math.floor(1700 / (words.length * 6))));
  K.pix3d(words, ps, ["#ffe0f7", "#ff7ad9", "#c2189b"], "#4a0638", Math.round(ps * 1.4), T);
  if (I.sub) K.pix3d(I.sub.toUpperCase(), Math.max(6, Math.floor(ps * 0.45)), ["#ffffff", "#ffe9a6", "#ffc23a"], "#5a3300", Math.round(ps * 0.6), T);
  tl.to(boss, { opacity: 0, duration: 0.2 }, t0);
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(T.children, { opacity: 0, scale: 0.2 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(1.7)", stagger: 0.12 }, t0);
  K.shake(tl, stage, t0 + 0.1, 16, 0.3);
  K.vignette(stage, 0.55);
};

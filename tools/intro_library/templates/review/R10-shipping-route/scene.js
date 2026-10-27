window.TEMPLATE = function (tl, I, K) {
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e;
  const map = document.getElementById("map");
  // stylised continents + dot grid
  [[1180, 40, 760, 560], [1520, 520, 300, 260], [-120, 60, 760, 520], [120, 560, 380, 420], [820, 120, 260, 300]].forEach((l) =>
    K.div("land", map, `left:${l[0]}px;top:${l[1]}px;width:${l[2]}px;height:${l[3]}px`));
  K.div("dotgrid", map);
  const svg = K.svg(map);
  const A = [1500, 260], B = [330, 330];
  const path = K.path(svg, `M ${A[0]} ${A[1]} Q 930 -120 ${B[0]} ${B[1]}`, { color: "#7fb0ff", width: 7 });
  path.setAttribute("stroke-dasharray", "4 18");
  K.div("pin", map, `left:${A[0] - 13}px;top:${A[1] - 13}px`);
  K.div("pin", map, `left:${B[0] - 13}px;top:${B[1] - 13}px`);
  const parcel = K.div("parcel", map, "", K.glyphHTML("box", 64, "#ffd36b"));
  const L = path.getTotalLength();
  const prog = { p: 0 };
  const place = () => { const pt = path.getPointAtLength(prog.p * L); parcel.style.transform = `translate(${pt.x - 32}px, ${pt.y - 40}px)`; };
  place();
  tl.to(prog, { p: 1, duration: Math.max(1, turn - 0.4), ease: "power1.inOut", onUpdate: place }, 0.2);
  tl.fromTo(map, { scale: 1.15 }, { scale: 1, duration: turn, ease: "power2.out" }, 0);
  // tracking statuses: one per problem line, key word as the detail
  const ST = ["ORDER PLACED", "PROCESSING", "SHIPPED", "IN TRANSIT", "IN CUSTOMS", "OUT FOR DELIVERY"];
  const pre = I.lines.filter((l) => l.s < turn - 0.05);
  const stat = document.getElementById("status");
  pre.slice(-4).forEach((ln, k) => {
    const s = K.div("st", stat, "", `<i></i><b>${ST[k % ST.length]}</b><span>${K.esc(ln.key || K.short(ln.text, 3))}</span>`);
    tl.fromTo(s, { opacity: 0, x: -80 }, { opacity: 1, x: 0, duration: 0.25, ease: "power3.out" }, ln.s);
  });
  tl.to(stat, { opacity: 0, duration: 0.2 }, turn - 0.2);
  // B-roll window during the problem half
  const win = document.getElementById("win");
  const preSlots = I.slots.filter((s) => s.s < turn - 0.1);
  if (preSlots.length) tl.fromTo(win, { opacity: 0, y: 60 }, { opacity: 1, y: 0, duration: 0.3 }, preSlots[0].s);
  preSlots.forEach((sl) => K.mount(tl, sl, win.querySelector(".in"), { fade: 0.06 }));
  tl.to(win, { opacity: 0, duration: 0.15 }, turn - 0.2);
  // the turn: the box drops in and opens, the reveal plays from inside it
  const box = document.getElementById("box"), bin = box.querySelector(".in");
  tl.set(box, { opacity: 1 }, turn - 0.15);
  tl.fromTo(box, { y: -1100 }, { y: 0, duration: 0.35, ease: "bounce.out" }, turn - 0.15);
  tl.to(map, { filter: "blur(8px) brightness(.5)", duration: 0.3 }, turn);
  tl.to(box.querySelector(".flap.l"), { rotationX: 0, rotation: -120, duration: 0.35, ease: "back.out(1.5)" }, turn + 0.25);
  tl.to(box.querySelector(".flap.r"), { rotation: 120, duration: 0.35, ease: "back.out(1.5)" }, turn + 0.25);
  tl.set(bin, { opacity: 1 }, turn + 0.4);
  tl.fromTo(bin, { y: 420, scale: 0.6 }, { y: 0, scale: 1, duration: 0.45, ease: "back.out(1.4)" }, turn + 0.4);
  I.slots.filter((s) => s.s >= turn - 0.1).forEach((sl) => K.mount(tl, sl, bin, { fade: 0.06 }));
  K.kinetic(tl, I.words.filter((w) => w.s >= turn + 0.3), { cls: "kin map", lower: true, chunk: { max: 2, chars: 13 }, pos: () => ({ left: 960, top: 1000, align: "center" }) });
  K.kinetic(tl, I.words.filter((w) => w.s < turn - 0.05), { cls: "kin map", lower: true, chunk: { max: 2, chars: 13 }, pos: () => ({ left: 1420, top: 360, align: "center" }) });
  K.xp(tl, stage, { top: 40, label: "WATCH TO THE END" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  t1.textContent = I.title || "REVIEW";
  T.querySelector(".t2").textContent = (I.sub || "tracking no. 0001") + "  ·  priority";
  K.fit(t1, 1360, 150, 60);
  const t0 = (I.beats.title != null ? I.beats.title : Math.max(last + 0.1, (I.beats.go || last) + 0.05));
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(T.querySelector(".label"), { scale: 1.6, rotation: -8, opacity: 0 }, { scale: 1, rotation: -2, opacity: 1, duration: 0.3, ease: "power4.out" }, t0);
  K.shake(tl, T, t0 + 0.25, 10, 0.25);
};

/* Intro Library kit: shared, seek-safe helpers for every intro template (gaming / phone / review).
   A template is one function: window.TEMPLATE = function (tl, I, K) { ... } that adds tweens to the paused
   timeline `tl` from the INTRO data `I` (words, lines, beats, slots, title). Everything here is deterministic:
   no clocks, no Math.random (K.rng is seeded), text changes go through tween onUpdate so seeking any frame works. */
(function () {
  "use strict";
  const I = window.INTRO;
  const K = {};
  window.K = K;
  K.I = I;
  K.W = 1920;
  K.H = 1080;
  // content lives inside the camera rig (#cam > #cam-in) so the whole scene moves like a filmed shot;
  // overlays (flash, blackout, XP bar, grain, vignette, wipes) sit on #stage above it and stay locked to the frame
  K.root = () => document.getElementById("cam-in") || document.getElementById("stage");
  K.over = () => document.getElementById("stage");
  const OV = (p) => (!p || p === K.root() ? K.over() : p);

  // ---------- basics ----------
  K.rng = function (seed) {
    let a = (seed >>> 0) || 1;
    return function () {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  };
  K.r = K.rng(I.seed || 7);
  K.pick = (arr, r) => arr[Math.floor((r || K.r)() * arr.length) % arr.length];
  K.el = function (tag, o, parent) {
    o = o || {};
    const e = document.createElement(tag);
    if (o.cls) e.className = o.cls;
    if (o.id) e.id = o.id;
    if (o.html != null) e.innerHTML = o.html;
    if (o.text != null) e.textContent = o.text;
    if (o.style) e.setAttribute("style", o.style);
    if (o.attrs) for (const k in o.attrs) e.setAttribute(k, o.attrs[k]);
    (parent || K.root()).appendChild(e);
    return e;
  };
  K.div = (cls, parent, style, html) => K.el("div", { cls, style, html }, parent);
  K.layer = (cls, parent) => K.div("layer " + (cls || ""), parent || K.root());
  K.esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  K.clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  // ---------- VO data ----------
  K.words = (s, e) => I.words.filter((w) => w.s >= s - 0.001 && w.s < e);
  K.lineWords = (ln) => I.words.slice(ln.wi[0], ln.wi[1] + 1);
  K.lineAt = (t) => I.lines.find((l) => t >= l.s && t < l.e) || I.lines[I.lines.length - 1];
  K.before = (t) => I.lines.filter((l) => l.s < t);
  K.after = (t) => I.lines.filter((l) => l.s >= t);
  K.role = (r) => I.lines.filter((l) => l.role === r);
  K.end = (ln) => {
    const i = I.lines.indexOf(ln);
    return i >= 0 && i < I.lines.length - 1 ? I.lines[i + 1].s : I.dur;
  };
  K.clean = (w) => String(w).replace(/^[^\w$#%']+|[^\w$%']+$/g, "");

  // group spoken words into 1-2 word caption chunks (the reference look: "so / i was", "the store", "gate moncler's")
  K.chunks = function (words, o) {
    o = Object.assign({ max: 2, chars: 13, gap: 0.22 }, o || {});
    const out = [];
    let cur = null;
    words.forEach((w, idx) => {
      const txt = K.clean(w.w);
      if (!txt || w.date) return;   // spoken dates never become captions
      // a price the price card already shows is never ALSO a caption (balenciaga 2026-10-26, 0:08: the "$1,000" card with a
      // green "$1,000" caption under it, "the text in green isn't supposed to be there"; again at "$120")
      const I0 = window.INTRO || {};
      if (w.c === "money" && (I0.mg || []).some((g) => (g.type === "price" || g.type === "compare") && w.s >= g.t - 0.5 && w.s <= g.e)) return;
      const brk = !cur || cur.words.length >= o.max || (cur.text + " " + txt).length > o.chars ||
        w.s - cur.e > o.gap || w.k || cur.key || /[.!?,]$/.test(cur.raw);
      if (brk) {
        if (cur) out.push(cur);
        cur = { s: w.s, e: w.e, text: txt, raw: w.w, words: [w], key: !!w.k, cls: w.c || "" };
      } else {
        cur.text += " " + txt; cur.e = w.e; cur.raw = w.w; cur.words.push(w);
      }
    });
    if (cur) out.push(cur);
    // a chunk on screen for under 0.2 s can't be read: fold it into the next one
    for (let i = out.length - 2; i >= 0; i--) {
      // a zero-length chunk ("the" at 2.42-2.42 before the brand word "Cartier") folds even into a key chunk: on its own its
      // hide time came before its show time and it stuck on screen to the end (dhgate cartier watch intro 2026-10-22)
      if (out[i + 1].s - out[i].s < 0.2 && (out[i].text + " " + out[i + 1].text).length <= o.chars + 6 && (!out[i + 1].key || out[i + 1].s - out[i].s < 0.06)) {
        if (out[i + 1].key) { out[i].key = true; out[i].cls = out[i + 1].cls; }
        out[i].text += " " + out[i + 1].text; out[i].e = out[i + 1].e; out[i].words = out[i].words.concat(out[i + 1].words); out.splice(i + 1, 1);
      }
    }
    out.forEach((c, i) => (c.next = i < out.length - 1 ? out[i + 1].s : c.e + 0.6));
    return out;
  };

  // ---------- motion primitives ----------
  K.set = (tl, el, vars, t) => tl.set(el, vars, t);
  K.pop = function (tl, el, t, o) {
    o = Object.assign({ d: 0.32, from: 0.6, ease: "back.out(2.2)", y: 0, rot: 0 }, o || {});
    tl.fromTo(el, { opacity: 0, scale: o.from, y: o.y, rotation: o.rot }, { opacity: 1, scale: 1, y: 0, rotation: o.rot2 || 0, duration: o.d, ease: o.ease }, t);
  };
  K.fadeIn = (tl, el, t, d, vars) => tl.fromTo(el, Object.assign({ opacity: 0 }, (vars && vars.from) || {}), Object.assign({ opacity: 1, duration: d || 0.3, ease: "power2.out" }, (vars && vars.to) || {}), t);
  K.out = (tl, el, t, d, vars) => tl.to(el, Object.assign({ opacity: 0, duration: d || 0.2, ease: "power2.in" }, vars || {}), t);
  K.whip = function (tl, el, t, dir, d) {
    const m = { l: { x: -1920 }, r: { x: 1920 }, u: { y: -1080 }, d: { y: 1080 } }[dir || "r"];
    tl.fromTo(el, Object.assign({ opacity: 1 }, m), { x: 0, y: 0, opacity: 1, duration: d || 0.26, ease: "power3.out" }, t);
  };
  K.whipOut = function (tl, el, t, dir, d) {
    const m = { l: { x: -1920 }, r: { x: 1920 }, u: { y: -1080 }, d: { y: 1080 } }[dir || "l"];
    tl.to(el, Object.assign({ duration: d || 0.22, ease: "power3.in" }, m), t);
  };
  K.shake = function (tl, el, t, amp, d) {
    amp = amp || 16; d = d || 0.36;
    const r = K.rng(Math.round(t * 1000) + 3);
    const n = 7, step = d / n;
    for (let i = 0; i < n; i++) {
      const f = 1 - i / n;
      tl.to(el, { x: (r() - 0.5) * 2 * amp * f, y: (r() - 0.5) * 2 * amp * f, duration: step, ease: "none" }, t + i * step);
    }
    tl.to(el, { x: 0, y: 0, duration: step, ease: "none" }, t + d);
  };
  K.flash = function (tl, t, color, parent, d) {
    const f = K.div("flash", OV(parent), "background:" + (color || "#fff"));
    tl.set(f, { opacity: 0.95 }, t);   // set + to (not fromTo): rewinding past t restores the hidden state
    tl.to(f, { opacity: 0, duration: d || 0.32, ease: "power2.out" }, t + 0.001);
    return f;
  };
  K.blackout = function (tl, t, d, parent) {
    const f = K.div("flash", OV(parent), "background:#000;z-index:80");
    tl.set(f, { opacity: 1 }, t);
    tl.set(f, { opacity: 0 }, t + (d || 0.26));
    return f;
  };
  K.text = function (tl, el, t, txt) {   // seek-safe text swap: every swap on an element resolves from one ordered list
    if (!el._seq) el._seq = [{ t: -1, txt: el.textContent }];
    el._seq.push({ t, txt });
    el._seq.sort((a, b) => a.t - b.t);
    const o = { v: 0 };
    tl.to(o, { v: 1, duration: 0.02, onUpdate: () => {
      const now = tl.time();
      let cur = el._seq[0].txt;
      for (const s of el._seq) if (now >= s.t) cur = s.txt;
      el.textContent = cur;
    } }, t);
  };
  K.type = function (tl, el, txt, t, d, caret) {
    const o = { n: 0 };
    el.textContent = "";
    tl.to(o, { n: txt.length, duration: d, ease: "none", onUpdate: () => (el.textContent = txt.slice(0, Math.round(o.n)) + (caret && o.n < txt.length ? caret : "")) }, t);
  };
  K.count = function (tl, el, from, to, t, d, fmt, ease) {
    const o = { v: from };
    fmt = fmt || ((v) => Math.round(v).toLocaleString("en-US"));
    el.textContent = fmt(from);
    tl.to(o, { v: to, duration: d, ease: ease || "power2.out", onUpdate: () => (el.textContent = fmt(o.v)) }, t);
  };
  K.money = (v) => "$" + v.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  K.draw = function (tl, path, t, d, ease) {   // SVG stroke draw-on
    const L = path.getTotalLength ? path.getTotalLength() : 1000;
    path.style.strokeDasharray = L;
    tl.fromTo(path, { strokeDashoffset: L }, { strokeDashoffset: 0, duration: d || 0.5, ease: ease || "power2.inOut" }, t);
  };
  K.float = function (tl, el, t0, t1, amp, seed) {   // gentle idle drift over a window
    const r = K.rng(seed || 11);
    tl.fromTo(el, { x: 0, y: 0, rotation: 0 }, { x: (r() - 0.5) * amp, y: (r() - 0.5) * amp, rotation: (r() - 0.5) * amp * 0.06, duration: Math.max(0.1, t1 - t0), ease: "sine.inOut" }, t0);
  };

  // ---------- word-by-word kinetic captions (the review reference look) ----------
  // opts: parent, cls, chunk {max,chars,gap}, pos(chunk,i)->{left,top,align}, enter 'pop'|'rise'|'blur'|'slam'|'type'|'scale', hold extra, until (hide time)
  K.kinetic = function (tl, words, o) {
    o = Object.assign({ parent: K.root(), cls: "kin", enter: "pop", chunk: {}, hold: 0 }, o || {});
    const box = K.div("kin-layer", o.parent);
    const cs = K.chunks(words, o.chunk);
    const r = K.rng((I.seed || 7) + 99);
    cs.forEach((c, i) => {
      const p = o.pos ? o.pos(c, i, r) : { left: 960, top: 540, align: "center" };
      const e = K.div(o.cls + (c.key ? " key" : "") + (c.cls ? " " + c.cls : ""), box);
      e.innerHTML = c.words.map((w) => '<span class="w' + (w.k ? " k" : "") + (w.c ? " " + w.c : "") + '">' + K.esc(o.lower ? K.clean(w.w).toLowerCase() : o.upper ? K.clean(w.w).toUpperCase() : K.clean(w.w)) + "</span>").join(" ");
      e.style.left = p.left + "px"; e.style.top = p.top + "px";
      e.style.transformOrigin = "50% 50%";
      gsap.set(e, { xPercent: p.align === "left" ? 0 : p.align === "right" ? -100 : -50, yPercent: -50, rotation: p.rot || 0 });
      const s = c.s, end = Math.max(c.s + 0.05, Math.min(o.until || 1e9, c.next < c.e + 0.9 + o.hold ? c.next - 0.01 : c.e + 0.9 + o.hold));   // until: clear before the title lands; never before it shows
      const ent = typeof o.enter === "function" ? o.enter(c, i) : o.enter;
      const D = (d) => Math.max(0.03, Math.min(d, (end - s) * 0.6));   // an entry never outlives its chunk (else the hide is overwritten)
      if (ent === "rise") tl.fromTo(e, { opacity: 0, y: 34 }, { opacity: 1, y: 0, duration: D(0.18), ease: "power3.out" }, s);
      else if (ent === "blur") tl.fromTo(e, { opacity: 0, scale: 1.25, filter: "blur(14px)" }, { opacity: 1, scale: 1, filter: "blur(0px)", duration: D(0.2), ease: "power2.out" }, s);
      else if (ent === "slam") tl.fromTo(e, { opacity: 0, scale: 2.2 }, { opacity: 1, scale: 1, duration: D(0.14), ease: "power4.out" }, s);
      else if (ent === "type") { tl.set(e, { opacity: 1 }, s); const sp = e.querySelectorAll(".w"); sp.forEach((x, j) => tl.fromTo(x, { opacity: 0 }, { opacity: 1, duration: 0.01 }, c.words[j].s)); }
      else if (ent === "scale") tl.fromTo(e, { opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1, duration: D(0.22), ease: "back.out(2)" }, s);
      else tl.fromTo(e, { opacity: 0, scale: 1.18 }, { opacity: 1, scale: 1, duration: D(0.14), ease: "power2.out" }, s);
      if (o.drift) tl.to(e, { x: o.drift, duration: Math.max(0.1, end - s), ease: "none" }, s);
      tl.set(e, { opacity: 0 }, end);
    });
    return { box, chunks: cs };
  };

  // ---------- textures ----------
  // real fog: pre-rendered fractal-noise smoke textures (kit/tex/smoke0-2.png) drifting in layers
  K.smoke = function (tl, parent, o) {
    o = Object.assign({ layers: 3, alpha: 0.5, seed: 5, t0: 0, t1: I.dur, tint: "", blend: "screen", side: "" }, o || {});
    const r = K.rng(o.seed);
    const box = K.div("smoke", parent, `opacity:${o.alpha};mix-blend-mode:${o.blend}`);
    for (let i = 0; i < o.layers; i++) {
      const img = K.el("img", { attrs: { src: "assets/tex/smoke" + ((i + o.seed) % 3) + ".png" },
        style: `position:absolute;left:${-200 + r() * 120}px;top:${-80 + r() * 80}px;width:2300px;height:1250px;${o.tint ? "filter:" + o.tint : ""}` }, box);
      const dx = (r() - 0.35) * 360, dy = (r() - 0.5) * 120;
      tl.fromTo(img, { x: 0, y: 0, scale: 1, rotation: 0, opacity: 0.55 + r() * 0.45 },
        { x: dx, y: dy, scale: 1.12 + r() * 0.2, rotation: (r() - 0.5) * 8, duration: Math.max(0.1, o.t1 - o.t0), ease: "none" }, o.t0);
    }
    if (o.side) box.style.webkitMaskImage = box.style.maskImage = o.side === "right" ? "linear-gradient(90deg, transparent 25%, #000 75%)" : "linear-gradient(270deg, transparent 25%, #000 75%)";
    return box;
  };
  K.tex = (name, parent, style) => K.el("img", { attrs: { src: "assets/tex/" + name }, style: "position:absolute;left:0;top:0;width:1920px;height:1080px;" + (style || "") }, parent);
  K.grain = function (tl, parent, op, seed) {   // stepped film grain (SVG turbulence)
    const svg = "<svg xmlns='http://www.w3.org/2000/svg' width='300' height='300'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 .5  0 0 0 0 .5  0 0 0 0 .5  0 0 0 1.2 0'/></filter><rect width='300' height='300' filter='url(%23n)'/></svg>";
    const g = K.div("grain", OV(parent), `opacity:${op == null ? 0.16 : op};background-image:url("data:image/svg+xml;utf8,${svg}")`);
    const n = Math.floor(I.dur * 12);
    tl.fromTo(g, { backgroundPosition: "0px 0px" }, { backgroundPosition: `${n * 137}px ${n * 91}px`, duration: I.dur, ease: `steps(${n})` }, 0);
    return g;
  };
  K.dust = function (tl, parent, o) {   // specks drifting on paper / film
    o = Object.assign({ n: 60, color: "rgba(40,30,20,.55)", seed: 9 }, o || {});
    const r = K.rng(o.seed);
    const box = K.div("dust", parent);
    for (let i = 0; i < o.n; i++) {
      const s = 2 + r() * 7;
      const d = K.div("speck", box, `left:${r() * 1920}px;top:${r() * 1080}px;width:${s}px;height:${s * (0.5 + r())}px;background:${o.color};border-radius:${r() * 50}%`);
      tl.fromTo(d, { x: 0, y: 0 }, { x: (r() - 0.5) * 160, y: (r() - 0.5) * 90, duration: I.dur, ease: "none" }, 0);
    }
    return box;
  };
  K.vignette = (parent, a) => K.div("vig", OV(parent), `background:radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,${a == null ? 0.6 : a}) 100%)`);
  K.scan = (parent, a) => K.div("scan", OV(parent), `opacity:${a == null ? 1 : a}`);

  // ---------- hand-drawn marker (red pen circles, arrows, scribble underlines) ----------
  const NS = "http://www.w3.org/2000/svg";
  K.svg = function (parent, style) {
    const s = document.createElementNS(NS, "svg");
    s.setAttribute("width", 1920); s.setAttribute("height", 1080); s.setAttribute("viewBox", "0 0 1920 1080");
    s.setAttribute("style", "position:absolute;left:0;top:0;overflow:visible;pointer-events:none;" + (style || ""));
    (parent || K.root()).appendChild(s);
    return s;
  };
  K.path = function (svg, d, o) {
    o = Object.assign({ color: "#e0201b", width: 9, fill: "none" }, o || {});
    const p = document.createElementNS(NS, "path");
    p.setAttribute("d", d); p.setAttribute("fill", o.fill); p.setAttribute("stroke", o.color); p.setAttribute("stroke-width", o.width);
    p.setAttribute("stroke-linecap", "round"); p.setAttribute("stroke-linejoin", "round");
    svg.appendChild(p);
    return p;
  };
  K.markerCircle = function (tl, svg, o) {   // a loose double loop like a real pen circle
    const r = K.rng(o.seed || 21), cx = o.x, cy = o.y, rx = o.w / 2, ry = o.h / 2;
    let d = "";
    const n = 44, turns = 1.18;
    for (let i = 0; i <= n; i++) {
      const a = -2.4 + (i / n) * Math.PI * 2 * turns, j = 1 + (r() - 0.5) * 0.06 + (i / n) * 0.07;
      d += (i ? " L " : "M ") + (cx + Math.cos(a) * rx * j).toFixed(1) + " " + (cy + Math.sin(a) * ry * j).toFixed(1);
    }
    const p = K.path(svg, d, o);
    K.draw(tl, p, o.t, o.d || 0.45, "power1.inOut");
    return p;
  };
  K.markerArrow = function (tl, svg, o) {
    const mx = (o.x1 + o.x2) / 2 + (o.bend || 80), my = (o.y1 + o.y2) / 2 - (o.bend || 80) * 0.6;
    const p = K.path(svg, `M ${o.x1} ${o.y1} Q ${mx} ${my} ${o.x2} ${o.y2}`, o);
    const ang = Math.atan2(o.y2 - my, o.x2 - mx), L = 38;
    const h = K.path(svg, `M ${o.x2 - L * Math.cos(ang - 0.5)} ${o.y2 - L * Math.sin(ang - 0.5)} L ${o.x2} ${o.y2} L ${o.x2 - L * Math.cos(ang + 0.5)} ${o.y2 - L * Math.sin(ang + 0.5)}`, o);
    K.draw(tl, p, o.t, o.d || 0.35);
    K.draw(tl, h, o.t + (o.d || 0.35), 0.12);
    return [p, h];
  };
  K.scribble = function (tl, svg, o) {   // zig-zag underline
    let d = `M ${o.x} ${o.y}`;
    const n = o.n || 3;
    for (let i = 0; i < n; i++) d += ` L ${o.x + o.w} ${o.y + i * 10 + 4} L ${o.x + 18} ${o.y + i * 10 + 12}`;
    const p = K.path(svg, d, o);
    K.draw(tl, p, o.t, o.d || 0.4);
    return p;
  };
  K.googly = function (tl, parent, o) {   // two googly eyes; pupils roll on a seeded path
    const box = K.div("googly", parent, `position:absolute;left:${o.x}px;top:${o.y}px;width:${o.size * 2.2}px;height:${o.size}px;opacity:0`);
    const r = K.rng(o.seed || 4);
    for (let i = 0; i < 2; i++) {
      const e = K.div("", box, `position:absolute;left:${i * o.size * 1.15}px;top:0;width:${o.size}px;height:${o.size}px;border-radius:50%;background:#fff;border:${Math.max(3, o.size / 18)}px solid #111;box-shadow:0 6px 14px rgba(0,0,0,.35)`);
      const p = K.div("", e, `position:absolute;left:${o.size * 0.28}px;top:${o.size * 0.28}px;width:${o.size * 0.42}px;height:${o.size * 0.42}px;border-radius:50%;background:#111`);
      const n = Math.max(2, Math.floor((o.t1 - o.t0) / 0.35));
      for (let k = 0; k < n; k++) tl.to(p, { x: (r() - 0.5) * o.size * 0.4, y: (r() - 0.5) * o.size * 0.4, duration: 0.18, ease: "back.out(3)" }, o.t0 + k * 0.35);
    }
    K.pop(tl, box, o.t0, { from: 0.2 });
    tl.to(box, { opacity: 0, duration: 0.15 }, o.t1);
    return box;
  };
  // a printed-photo / polaroid frame that a footage slot can be mounted into
  K.photo = function (parent, o) {
    o = Object.assign({ w: 720, h: 405, rot: 0, border: 14, bg: "#fff", shadow: "0 22px 50px rgba(0,0,0,.35)" }, o);
    const f = K.div("photo", parent, `position:absolute;left:${o.x}px;top:${o.y}px;width:${o.w}px;height:${o.h}px;padding:${o.border}px;background:${o.bg};box-shadow:${o.shadow};opacity:0`);
    const inner = K.div("photo-in", f, "position:relative;width:100%;height:100%;overflow:hidden;background:#222");
    gsap.set(f, { rotation: o.rot });
    return { frame: f, inner };
  };
  // mount a slot into a frame's inner box (the slot fills it)
  K.into = function (tl, sl, inner) {
    const w = K.slot(sl.i);
    if (!w) return null;
    inner.appendChild(w);
    w.style.opacity = 1;
    return w;
  };
  // review title lockup: the brand's real logo, the product word, "on" + the DHgate logo (amiri jeans 2026-10-22: the
  // ransom-note title was "a bit whack ... maybe like Amiri Jeans on DHgate with the DHgate logo"). o.ink = text colour.
  K.lockup = function (tl, parent, t0, o) {
    o = Object.assign({ ink: "#111", font: "Anton", z: 45 }, o || {});
    const brand = (I.brand || "").toLowerCase();
    const prod = (I.title || "").toLowerCase().split(/\s+/).filter((w) => w && !/^(dh ?gate|review|honest|on)$/.test(w) && !brand.split(" ").includes(w)).join(" ");
    const box = K.div("lockup", parent, `position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:26px;z-index:${o.z};opacity:0`);
    const top = I.brandLogo ? K.el("img", { attrs: { src: I.brandLogo }, style: "height:220px;max-width:1150px;object-fit:contain;display:block" }, box)
      : K.div("", box, `font:400 170px ${o.font};color:${o.ink};letter-spacing:6px;line-height:1`, K.esc((I.brand || I.title || "").toUpperCase()));
    const mid = prod && I.brandLogo ? K.div("", box, `font:400 140px ${o.font};color:${o.ink};letter-spacing:22px;line-height:1`, K.esc(prod.toUpperCase())) : null;
    const row = I.dhLogo ? K.div("", box, "display:flex;align-items:center;gap:26px") : null;
    let on, dh, word;
    if (row) {
      on = K.div("", row, `font:400 64px "Typewriter", monospace;color:${o.ink}`, "on");
      dh = K.el("img", { attrs: { src: I.dhLogo }, style: "width:150px;height:150px;border-radius:32px;display:block;box-shadow:0 10px 24px rgba(0,0,0,.3)" }, row);
      word = K.div("", row, `font:900 124px Poppins, sans-serif;color:${o.ink};letter-spacing:-1px`, 'DH<span style="color:#f5a300">gate</span>');
    }
    tl.set(box, { opacity: 1 }, t0);
    tl.fromTo(top, { opacity: 0, scale: 1.8, y: -30 }, { opacity: 1, scale: 1, y: 0, duration: 0.24, ease: "power3.out" }, t0);
    if (mid) tl.fromTo(mid, { opacity: 0, letterSpacing: "70px" }, { opacity: 1, letterSpacing: "22px", duration: 0.35, ease: "power3.out" }, t0 + 0.14);
    if (row) {
      tl.fromTo(on, { opacity: 0, x: -60 }, { opacity: 1, x: 0, duration: 0.2 }, t0 + 0.3);
      tl.fromTo(dh, { opacity: 0, scale: 0.2, rotation: -200 }, { opacity: 1, scale: 1, rotation: 0, duration: 0.4, ease: "back.out(1.7)" }, t0 + 0.34);
      tl.fromTo(word, { opacity: 0, x: 80 }, { opacity: 1, x: 0, duration: 0.25, ease: "power3.out" }, t0 + 0.44);
    }
    tl.fromTo(box, { scale: 1 }, { scale: 1.05, duration: Math.max(0.5, I.dur - t0), ease: "none" }, t0);   // never a still title
    return box;
  };

  // ---------- phone / app UI (phone tutorial intros) ----------
  K.app = () => I.app || { name: (I.title || "APP").split(" ")[0], accent: I.accent, icon: "", methods: ["PROMO CODES", "REFERRAL $$$", "FREE TRIAL"], others: [] };
  K.appIcon = function (parent, size, style) {
    const a = K.app();
    if (a.icon) return K.el("img", { attrs: { src: a.icon }, style: `width:${size}px;height:${size}px;border-radius:${size * 0.23}px;display:block;${style || ""}` }, parent);
    return K.div("", parent, `width:${size}px;height:${size}px;border-radius:${size * 0.23}px;background:${a.accent};display:flex;align-items:center;justify-content:center;font:900 ${size * 0.5}px Poppins;color:#fff;${style || ""}`, K.esc(a.name[0]));
  };
  K.phone = function (parent, o) {   // a modern phone body; returns {frame, screen}
    o = Object.assign({ x: 680, y: 40, w: 560, h: 1140, r: 78, color: "#111", wall: "" }, o || {});
    const f = K.div("phone", parent, `position:absolute;left:${o.x}px;top:${o.y}px;width:${o.w}px;height:${o.h}px;border-radius:${o.r}px;background:${o.color};padding:18px;box-shadow:0 0 0 4px #2a2a2e, 0 50px 120px rgba(0,0,0,.55)`);
    const s = K.div("screen", f, `position:relative;width:100%;height:100%;border-radius:${o.r - 16}px;overflow:hidden;background:${o.wall || "linear-gradient(160deg, " + K.app().accent + ", #0b0b10 75%)"}`);
    K.div("", s, "position:absolute;left:50%;top:18px;width:150px;height:40px;margin-left:-75px;border-radius:22px;background:#000;z-index:5");
    return { frame: f, screen: s };
  };
  K.notif = function (parent, o) {   // iOS-style notification card
    const n = K.div("notif", parent, `position:absolute;left:${o.x || 22}px;top:${o.y || 120}px;width:${o.w || 480}px;padding:20px 22px;border-radius:30px;` +
      `background:${o.bg || "rgba(245,245,248,.92)"};box-shadow:0 12px 30px rgba(0,0,0,.25);display:flex;gap:16px;align-items:flex-start;opacity:0`);
    const ic = K.div("", n, "flex:none");
    if (o.emoji) K.div("", ic, "width:74px;height:74px;border-radius:17px;background:#fff;display:flex;align-items:center;justify-content:center;font:46px Emoji", o.emoji);
    else K.appIcon(ic, 74);
    K.div("", n, "flex:1;min-width:0", `<div style="display:flex;justify-content:space-between;font:700 25px Inter;color:#333;letter-spacing:.3px"><span>${K.esc((o.app || K.app().name).toUpperCase())}</span><span style="font-weight:500;color:#888">now</span></div>` +
      `<div style="font:700 34px Inter;color:${o.color || "#111"};margin-top:6px;line-height:1.2">${o.html || K.esc(o.text || "")}</div>`);
    return n;
  };
  // bright two-panel slide wipe into the main video (phone rule: brand colour + white, never a dark panel)
  K.wipe = function (tl, t, c1, c2) {
    const a = K.div("", K.over(), `position:absolute;inset:0;background:${c1 || K.app().accent};z-index:90`);
    const b = K.div("", K.over(), `position:absolute;inset:0;background:${c2 || "#fff"};z-index:91`);
    tl.fromTo(a, { xPercent: -101 }, { xPercent: 0, duration: 0.3, ease: "power3.inOut" }, t);
    tl.fromTo(b, { xPercent: -101 }, { xPercent: 0, duration: 0.3, ease: "power3.inOut" }, t + 0.08);
  };
  K.short = function (text, n) {   // first n words of a line, for UI copy
    const w = String(text).replace(/[,.!?]+$/, "").split(/\s+/);
    return w.slice(0, n || 7).join(" ") + (w.length > (n || 7) ? "…" : "");
  };

  // ---------- drawn line icons (no emoji anywhere in an intro - user rule 2026-10-21) ----------
  const GL = {
    lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    unlock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 7.6-1.8"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="M16.5 16.5L21 21"/>',
    house: '<path d="M3 11l9-8 9 8v10H3z"/><path d="M10 21v-6h4v6"/>',
    scooter: '<circle cx="6" cy="18" r="3"/><circle cx="18" cy="18" r="3"/><path d="M6 18h7l3-8h3"/><path d="M13 18l-2-7H7"/>',
    box: '<path d="M3 7l9-4 9 4v10l-9 4-9-4z"/><path d="M3 7l9 4 9-4"/><path d="M12 11v10"/>',
    cart: '<circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/><path d="M2 3h3l3 12h11l2-8H6"/>',
    card: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>',
    receipt: '<path d="M5 3h14v18l-3-2-2 2-2-2-2 2-2-2-3 2z"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    gift: '<rect x="3" y="8" width="18" height="4"/><rect x="5" y="12" width="14" height="9"/><path d="M12 8v13"/><path d="M12 8C10 4 6 4 6 7c0 2 6 1 6 1zM12 8c2-4 6-4 6-1 0 2-6 1-6 1z"/>',
    pin: '<circle cx="12" cy="9" r="4"/><path d="M12 13v9"/>',
    person: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-7 8-7s8 3 8 7"/>',
    fire: '<path d="M12 2c2 4 6 6 6 11a6 6 0 0 1-12 0c0-3 2-5 3-7 1 2 2 3 3 3 0-3-1-5 0-7z"/>',
    tag: '<path d="M3 12V3h9l9 9-9 9z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
    check: '<path d="M4 12l5 5L20 6"/>',
  };
  K.glyph = function (name, size, color, parent, style) {
    const s = K.el("span", { cls: "glyph", style: `display:inline-flex;width:${size}px;height:${size}px;${style || ""}` }, parent);
    s.innerHTML = `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="${color || "currentColor"}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${GL[name] || GL.tag}</svg>`;
    return s;
  };
  K.glyphHTML = (name, size, color) => `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="${color || "currentColor"}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${GL[name] || GL.tag}</svg>`;

  // ---------- icons / stickers ----------
  K.emoji = (ch, size, parent, style) => K.div("emo", parent, `font-size:${size || 160}px;${style || ""}`, ch);
  K.pixEmoji = function (ch, px, scale, parent, style) {   // emoji drawn tiny then upscaled = instant pixel art
    const c = K.el("canvas", { cls: "pixemo", style: `width:${px * scale}px;height:${px * scale}px;${style || ""}` }, parent);
    c.width = px; c.height = px;
    const x = c.getContext("2d");
    x.textAlign = "center"; x.textBaseline = "middle";
    x.font = `${Math.round(px * 0.86)}px "Emoji"`;
    x.fillText(ch, px / 2, px / 2 + px * 0.06);
    return c;
  };
  K.sticker = function (parent, html, style) {   // white die-cut outline sticker
    return K.div("sticker", parent, style || "", html);
  };
  // the line's literal icon (analysis picks it from a keyword dictionary), with a type-appropriate fallback
  K.iconOf = (ln, fb) => "";   // emoji icons are off (user rule); templates use K.glyph

  // ---------- footage slots (the wrappers are written by build_intro.py; <video> inside is timed by the framework) ----------
  K.slots = () => I.slots || [];
  K.slot = (i) => document.getElementById("slot-" + i);
  K.slotFor = (ln) => (I.slots || []).find((s) => s.line === I.lines.indexOf(ln));
  K.slotsIn = (t0, t1) => (I.slots || []).filter((s) => s.s < t1 && s.e > t0);
  // move a slot wrapper into a frame element and show it while its window is live
  K.mount = function (tl, sl, frame, o) {
    o = Object.assign({ fade: 0.12 }, o || {});
    const w = K.slot(sl.i);
    if (!w) return null;
    frame.appendChild(w);
    w.style.opacity = 0;
    tl.to(w, { opacity: 1, duration: o.fade }, sl.s);
    tl.to(w, { opacity: 0, duration: 0.08 }, Math.max(sl.s + 0.1, sl.e + (o.hold != null ? o.hold : 0.05)));   // fade after the next clip is already up (hold = the next clip's dissolve)
    return w;
  };

  // ---------- "watch to the very end" XP bar (signature: Pokemon EXP fill + ding, sfx placed by the builder) ----------
  K.xp = function (tl, parent, o) {
    const w = I.beats.watch;
    if (!w) return null;
    o = Object.assign({ cls: "xp", label: "WATCH TO THE END", top: 900 }, o || {});
    const box = K.div(o.cls, OV(parent), `top:${o.top}px`);
    box.innerHTML = `<div class="xp-lab">${o.label}</div><div class="xp-bar"><div class="xp-fill"></div></div>`;
    const f = box.querySelector(".xp-fill");
    tl.fromTo(box, { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.2, ease: "power2.out" }, w.s - 0.15);
    tl.fromTo(f, { scaleX: 0 }, { scaleX: 1, duration: w.fill, ease: "none" }, w.s);
    tl.fromTo(box, { scale: 1 }, { scale: 1.08, duration: 0.09, yoyo: true, repeat: 1 }, w.s + w.fill);
    tl.to(box, { opacity: 0, duration: 0.25 }, Math.min(I.dur - 0.3, w.s + w.fill + 1.1));
    return box;
  };

  // ---------- title helpers ----------
  K.titleWords = () => String(I.title || "").split(/\s+/).filter(Boolean);
  K.fit = function (el, maxW, maxPx, minPx) {   // shrink a single-line display text until its TEXT (not its box) fits maxW
    let px = maxPx;
    el.style.fontSize = px + "px";
    el.style.whiteSpace = "nowrap";
    // measure a hidden inline clone: a full-width block's scrollWidth is its box, never smaller than the frame
    const m = el.cloneNode(true);
    m.removeAttribute("id");
    m.style.cssText += ";position:absolute;visibility:hidden;display:inline-block;width:auto;left:0;right:auto;transform:none;max-width:none";
    (el.parentNode || document.body).appendChild(m);
    const w = () => m.getBoundingClientRect().width;
    while (px > (minPx || 30) && w() > maxW) { px -= 4; m.style.fontSize = px + "px"; }
    const over = w() > maxW;
    m.remove();
    el.style.fontSize = px + "px";
    // still too wide at the smallest size: two lines, broken at the space nearest the middle (ultimate dhgate free reselling
    // spreadsheet 2026-10-23: "ULTIMATE DHGATE FREE RESELLING SPREADSHEET" ran off both edges of the R01 title card)
    if (over && !el.dataset.split) {
      const html = el.innerHTML, text = html.replace(/<[^>]+>/g, "");
      let depth = 0, seen = 0, best = -1, bestD = 1e9;
      for (let i = 0; i < html.length; i++) {
        const c = html[i];
        if (c === "<") depth++;
        else if (c === ">") depth--;
        else if (depth === 0) {   // text, inside or outside <b>…</b> (depth only counts the tag markup itself)
          if (c === " " && Math.abs(seen - text.length / 2) < bestD) { best = i; bestD = Math.abs(seen - text.length / 2); }
          seen++;
        }
      }
      if (best > 0) {
        el.innerHTML = html.slice(0, best) + "<br>" + html.slice(best + 1);
        el.dataset.split = "1";
        el.style.lineHeight = "1.08";
        return K.fit(el, maxW, maxPx, minPx);
      }
    }
    return px;
  };

  // ---------- pixel font (gaming): 5x7 glyphs drawn on canvas ----------
  const G = {
    A: "01110100011000111111100011000110001", B: "11110100011000111110100011000111110", C: "01110100011000010000100001000101110",
    D: "11110100011000110001100011000111110", E: "11111100001000011110100001000011111", F: "11111100001000011110100001000010000",
    G: "01110100011000010111100011000101111", H: "10001100011000111111100011000110001", I: "01110001000010000100001000010001110",
    J: "00111000100001000010000101001001100", K: "10001100101010011000101001001010001", L: "10000100001000010000100001000011111",
    M: "10001110111010110101100011000110001", N: "10001110011010110011100011000110001", O: "01110100011000110001100011000101110",
    P: "11110100011000111110100001000010000", Q: "01110100011000110001101011001001101", R: "11110100011000111110101001001010001",
    S: "01111100001000001110000010000111110", T: "11111001000010000100001000010000100", U: "10001100011000110001100011000101110",
    V: "10001100011000110001100010101000100", W: "10001100011000110101101011010101010", X: "10001100010101000100010101000110001",
    Y: "10001100010101000100001000010000100", Z: "11111000010001000100010001000011111",
    "0": "01110100011001110101110011000101110", "1": "00100011000010000100001000010001110", "2": "01110100010000100010001000100011111",
    "3": "11111000100010000010000011000101110", "4": "00010001100101010010111110001000010", "5": "11111100001111000001000011000101110",
    "6": "00110010001000011110100011000101110", "7": "11111000010001000100010000100001000", "8": "01110100011000101110100011000101110",
    "9": "01110100011000101111000010001001100", "!": "00100001000010000100001000000000100", "?": "01110100010000100010001000000000100",
    ".": "00000000000000000000000000110001100", "#": "01010010101111101010111110101001010", "$": "00100011111010001110001011111000100",
    "%": "11000110010001000100010001001100011", "'": "00100001000100000000000000000000000", "-": "00000000000000011111000000000000000",
    ":": "00000011000110000000011000110000000", "/": "00001000010001000100010001000010000", "+": "00000001000010011111001000010000000",
    "&": "01100100101010001000101011001001101", ",": "00000000000000000000001100010001000", " ": "00000000000000000000000000000000000",
  };
  K.pix = function (txt, cell, color, shadow, parent, style) {
    txt = String(txt).toUpperCase();
    const cw = 6, w = txt.length * cw - 1, h = 7;
    const c = K.el("canvas", { cls: "pix", style: style || "" }, parent);
    const sh = shadow ? 1 : 0;
    c.width = (w + sh) * cell; c.height = (h + sh) * cell;
    c.style.width = c.width + "px"; c.style.height = c.height + "px";
    const x = c.getContext("2d");
    const paint = (dx, dy, col) => {
      x.fillStyle = col;
      [...txt].forEach((ch, k) => {
        const g = G[ch] || G["?"];
        for (let j = 0; j < 35; j++) if (g[j] === "1") x.fillRect((k * cw + (j % 5) + dx) * cell, (Math.floor(j / 5) + dy) * cell, cell, cell);
      });
    };
    if (shadow) paint(1, 1, shadow);
    paint(0, 0, color || "#fff");
    return c;
  };
  K.pixFit = (txt, maxW, maxCell) => Math.max(3, Math.min(maxCell || 18, Math.floor(maxW / (String(txt).length * 6))));
  // from the approved servers-intro-oct: outlined pixel text, 3D extruded pixel title, hand-drawn pixel icons
  function cellsOf(text) {
    const chars = String(text).toUpperCase().split(""), widths = chars.map((c) => (c === " " ? 3 : 5));
    const cols = widths.reduce((s, w) => s + w + 1, -1), cells = [];
    let cx = 0;
    chars.forEach((c, i) => {
      const g = G[c];
      if (g && c !== " ") for (let r = 0; r < 7; r++) for (let k = 0; k < 5; k++) if (g[r * 5 + k] === "1") cells.push([cx + k, r]);
      cx += widths[i] + 1;
    });
    return { cells, cols: Math.max(1, cols) };
  }
  K.pixo = function (text, ps, fill, o, parent, style) {
    o = o || {};
    const out = o.outline != null ? o.outline : Math.round(ps * 0.45), sh = o.shadow != null ? o.shadow : ps, shc = o.shadowColor || "rgba(0,0,0,.45)";
    const { cells, cols } = cellsOf(text);
    const cv = K.el("canvas", { cls: "pix", style: style || "" }, parent);
    cv.width = cols * ps + out * 2 + sh; cv.height = 7 * ps + out * 2 + sh;
    cv.style.width = cv.width + "px"; cv.style.height = cv.height + "px";
    const ctx = cv.getContext("2d"), at = (x, y) => [out + x * ps, out + y * ps];
    ctx.fillStyle = shc; cells.forEach(([x, y]) => { const [px, py] = at(x, y); ctx.fillRect(px + sh - out, py + sh - out, ps + out * 2, ps + out * 2); });
    ctx.fillStyle = o.outlineColor || "#000"; if (out) cells.forEach(([x, y]) => { const [px, py] = at(x, y); ctx.fillRect(px - out, py - out, ps + out * 2, ps + out * 2); });
    cells.forEach(([x, y]) => { const [px, py] = at(x, y); ctx.fillStyle = Array.isArray(fill) ? (y < 4 ? fill[0] : fill[1]) : fill; ctx.fillRect(px, py, ps, ps); });
    return cv;
  };
  K.pix3d = function (text, ps, front, side, depth, parent, style) {
    const out = Math.round(ps * 0.35), { cells, cols } = cellsOf(text);
    const cv = K.el("canvas", { cls: "pix", style: style || "" }, parent);
    cv.width = cols * ps + out * 2 + depth + 6; cv.height = 7 * ps + out * 2 + depth + 6;
    cv.style.width = cv.width + "px"; cv.style.height = cv.height + "px";
    const ctx = cv.getContext("2d");
    for (let d = depth; d >= 1; d--) { ctx.fillStyle = d === depth ? "#000" : side; cells.forEach(([x, y]) => ctx.fillRect(x * ps + d, y * ps + d, ps + out * 2, ps + out * 2)); }
    ctx.fillStyle = "#000"; cells.forEach(([x, y]) => ctx.fillRect(x * ps, y * ps, ps + out * 2, ps + out * 2));
    cells.forEach(([x, y]) => { ctx.fillStyle = y < 3 ? front[0] : y < 5 ? front[1] : front[2]; ctx.fillRect(out + x * ps, out + y * ps, ps, ps); });
    ctx.fillStyle = "rgba(255,255,255,.35)"; cells.forEach(([x, y]) => { if (y === 0) ctx.fillRect(out + x * ps, out + y * ps, ps, Math.round(ps * 0.3)); });
    return cv;
  };
  K.pixW = (text, ps) => cellsOf(text).cols * ps;
  const PAL = { K: "#111", R: "#e2231a", W: "#fff", D: "#4ee6e0", H: "#8a5a2b", h: "#5e3b1a", G: "#3cc43c", Y: "#ffd400", y: "#e09a00",
    B: "#3a3a3a", b: "#5b5b5b", S: "#a8a8a8", N: "#5d9e2f", n: "#3f7a1d", M: "#866043", m: "#5f4128", L: "#c8c8c8", P: "#b84dff", p: "#7a22c2", O: "#ff8a1f" };
  K.ICON = {
    sword: ["..........DD", ".........DDD", "........DDD.", ".......DDD..", "......DDD...", ".....DDD....", "H...DDD.....", ".H.DDD......", "..HHD.......", "..HH........", ".H..H.......", "H..........."],
    ball: ["....KKKK....", "..KKRRRRKK..", ".KRRRRRRRRK.", ".KRRRRRRRRK.", "KRRRRKKRRRRK", "KKKKKWWKKKKK", "KWWWWKKWWWWK", ".KWWWWWWWWK.", ".KWWWWWWWWK.", "..KKWWWWKK..", "....KKKK....", "............"],
    island: ["............", "....N.......", "...NNNN..N..", "..NNNNNNNNN.", ".NNNNNNNNNNN", "nnnnnnnnnnnn", ".MMMMMMMMMM.", "..MMMmMMMM..", "...mMMMMm...", "....MMMM....", ".....mm.....", "......M....."],
    crown: ["Y....Y....Y.", "YY..YYY..YY.", "YYY.YYY.YYY.", "YYYYYYYYYYY.", "YYRYYYYYRYY.", "YYYYYYYYYYY.", "yyyyyyyyyyy.", "............"],
    lock: ["...KKKKK....", "..KLLLLLK...", "..KL...LK...", "..KL...LK...", "KKKKKKKKKKK.", "KYYYYYYYYYK.", "KYYYKKYYYYK.", "KYYYKKYYYYK.", "KYyyyyyyyYK.", "KKKKKKKKKKK."],
    chest: ["KKKKKKKKKKKK", "KMMMMMMMMMMK", "KMmmmmmmmmMK", "KMMMMMMMMMMK", "KKKKKYYKKKKK", "KMMMMYYMMMMK", "KMmmmmmmmmMK", "KMMMMMMMMMMK", "KMMMMMMMMMMK", "KKKKKKKKKKKK"],
    heart: [".KK...KK.", "KRRK.KRRK", "KRWRKRRRK", "KRRRRRRRK", ".KRRRRRK.", "..KRRRK..", "...KRK...", "....K...."],
    gem: ["...KKKK...", "..KDDWDK..", ".KDDDDDDK.", "KDDWDDDDDK", ".KDDDDDDK.", "..KDDDDK..", "...KDDK...", "....KK...."],
    skull: [".KKKKKK.", "KWWWWWWK", "KWKWWKWK", "KWKWWKWK", "KWWWWWWK", ".KWKKWK.", ".KWWWWK.", "..KKKK.."],
    cursor: ["K.......", "KK......", "KWK.....", "KWWK....", "KWWWK...", "KWWWWK..", "KWWKKK..", "KK.WK...", "....K..."],
    pick: ["..KKKKKKK...", ".KSSSSSSSK..", "KSK..H..KSK.", "KK...H...KK.", ".....H......", ".....H......", ".....H......", ".....H......", ".....h......", ".....h......"],
  };
  K.icon = function (name, ps, parent, style) {
    const m = K.ICON[name] || K.ICON.gem;
    const cv = K.el("canvas", { cls: "pix", style: style || "" }, parent);
    cv.width = m[0].length * ps; cv.height = m.length * ps;
    cv.style.width = cv.width + "px"; cv.style.height = cv.height + "px";
    const ctx = cv.getContext("2d");
    m.forEach((row, y) => row.split("").forEach((ch, x) => { if (ch !== ".") { ctx.fillStyle = PAL[ch]; ctx.fillRect(x * ps, y * ps, ps, ps); } }));
    return cv;
  };
  // gaming literal-icon pick from a line's words
  K.gicon = (ln) => {
    const t = (ln && ln.text || "").toLowerCase();
    return /pvp|fight|kill|sword|battle/.test(t) ? "sword" : /pokemon|pixelmon|cobblemon|catch/.test(t) ? "ball" : /sky|island/.test(t) ? "island" :
      /best|top|king|reign|featured|win/.test(t) ? "crown" : /can't|cannot|lock|console|block/.test(t) ? "lock" : /loot|chest|reward|free/.test(t) ? "chest" :
      /love|favorite|heart/.test(t) ? "heart" : /dead|die|bad|worst|boring/.test(t) ? "skull" : /mine|build|craft/.test(t) ? "pick" : "gem";
  };
  // stone/dirt pixel-block background canvas
  K.blocks = function (parent, o) {
    o = Object.assign({ px: 8, cell: 16, base: [110, 110, 110], vary: 26, seed: 3 }, o || {});
    const r = K.rng(o.seed), cv = K.el("canvas", { cls: "pix", style: "position:absolute;left:0;top:0;width:1920px;height:1080px" }, parent);
    const W = Math.ceil(1920 / o.px), H = Math.ceil(1080 / o.px);
    cv.width = W; cv.height = H;
    const x = cv.getContext("2d");
    for (let j = 0; j < H; j++) for (let i = 0; i < W; i++) {
      const v = (r() - 0.5) * o.vary, edge = i % (o.cell / o.px * 2) === 0 || j % (o.cell / o.px * 2) === 0 ? -14 : 0;
      x.fillStyle = `rgb(${o.base[0] + v + edge},${o.base[1] + v + edge},${o.base[2] + v + edge})`;
      x.fillRect(i, j, 1, 1);
    }
    return cv;
  };
  K.embers = function (tl, parent, o) {
    o = Object.assign({ n: 40, color: "#ff8a1f", seed: 6 }, o || {});
    const r = K.rng(o.seed);
    for (let i = 0; i < o.n; i++) {
      const s = 6 + Math.floor(r() * 3) * 6, e = K.div("", parent, `position:absolute;left:${r() * 1920}px;top:${300 + r() * 900}px;width:${s}px;height:${s}px;background:${o.color};box-shadow:0 0 12px ${o.color}`);
      tl.fromTo(e, { y: 0, opacity: 0.2 + r() * 0.8 }, { y: -500 - r() * 600, opacity: 0, duration: I.dur * (0.6 + r() * 0.4), ease: "none" }, r() * 2);
    }
  };
  // the gaming drop: 0.26 s blackout before the turn line, white flash + shake on it (the ONE 808 is placed by the builder)
  K.drop = function (tl, shakeEl) {
    const t = I.beats.turn;
    K.blackout(tl, t - (I.beats.gap || 0.26), I.beats.gap || 0.26);
    K.flash(tl, t, "#fff", K.over(), 0.35);
    K.shake(tl, shakeEl || K.root(), t, 22, 0.4);
  };

  // ---------- camera rig: the scene is never still (the approved intros' camera language) ----------
  // I.cam (planned by build_intro.py, so whip SFX line up) = [{t, e, type, keys:[t...], big}] one entry per VO line.
  // Between lines: whip / punch / tilt / dolly; during a line: slow push + drift; on key words: small punch-ins.
  K.camera = function (tl, o) {
    const cam = document.getElementById("cam");
    if (!cam || !I.cam || !I.cam.length) return;
    // review intros: a calm rig (s25 ultra 2026-10-23: "we probably should not be shaking the camera as much ... calm it
    // down"): no rotation, no key-word wobble, half the drift; the shots' own punch-in + pan carry the motion
    const calm = I.type === "review" ? { drift: 12, rot: 0, punch: 0, intensity: 0.6 } : {};
    o = Object.assign({ base: 1.07, push: 0.045, drift: 26, rot: 0.5, punch: 0.035, intensity: 1 }, calm, window.CAMERA || {}, o || {});
    const k = o.intensity, B = o.base;
    // every camera move renders lazily: an immediate-render whip on a later line used to paint its blur(10px) start state from
    // t=0 until it played (the first 2 s of every intro were blurred, 2026-10-22)
    gsap.set(cam, { scale: B, transformOrigin: "50% 50%", filter: "blur(0px)" });
    const r = K.rng((I.seed || 7) + 404);
    // review intros glide (ultimate dhgate free reselling spreadsheet 2026-10-23: "shaking the screen every 3 seconds ...
    // B-roll to B-roll just looks too jarring"): no whip / punch / settle between lines and no snap back to centre, one
    // continuous slow drift that hands each line's end position to the next line
    if (I.type === "review" && !(window.CAMERA || {}).moves) {
      let px = 0, py = 0, ps = B;
      I.cam.forEach((c, i) => {
        const nx = (r() - 0.5) * 2 * o.drift * k, ny = (r() - 0.5) * 2 * o.drift * 0.6 * k;
        const ns = B + o.push * k * ((i % 2) ? 0.3 : 1);
        tl.fromTo(cam, { x: px, y: py, scale: ps }, { x: nx, y: ny, scale: ns, duration: Math.max(0.2, c.e - c.t), ease: "none", immediateRender: false }, c.t);
        px = nx; py = ny; ps = ns;
      });
      return;
    }
    I.cam.forEach((c, i) => {
      const d = Math.max(0.3, c.e - c.t);
      const sx = (r() - 0.5) * 2 * o.drift * k, sy = (r() - 0.5) * 2 * o.drift * 0.6 * k, rz = (r() - 0.5) * 2 * o.rot * k;
      const dir = i % 2 ? 1 : -1;
      if (c.type === "whip") {
        tl.fromTo(cam, { x: dir * 150 * k, scale: B + 0.18, filter: "blur(10px)" }, { x: 0, scale: B, filter: "blur(0px)", duration: 0.24, ease: "power3.out", immediateRender: false }, c.t);
      } else if (c.type === "punch") {
        tl.fromTo(cam, { scale: B + 0.12 * k }, { scale: B, duration: 0.32, ease: "power3.out", immediateRender: false }, c.t);
      } else if (c.type === "tilt") {
        tl.fromTo(cam, { rotation: dir * 2.2 * k, y: 50 * k }, { rotation: 0, y: 0, duration: 0.34, ease: "power3.out", immediateRender: false }, c.t);
      } else {
        tl.fromTo(cam, { scale: B - 0.03 }, { scale: B, duration: 0.4, ease: "power2.out", immediateRender: false }, c.t);
      }
      // the shot keeps moving for the rest of the line
      const t0 = c.t + 0.34;
      tl.fromTo(cam, { x: 0, y: 0, rotation: 0, scale: B }, { x: sx, y: sy, rotation: rz, scale: B + o.push * k, duration: Math.max(0.2, c.e - t0), ease: "sine.inOut", immediateRender: false }, t0);
      // punch-ins on the line's key words (at most 2 per line)
      (c.keys || []).slice(0, 2).forEach((kt) => {
        if (kt > t0 + 0.1 && kt < c.e - 0.15) tl.to(cam, { scale: "+=" + o.punch * k, duration: 0.09, ease: "power2.out", yoyo: true, repeat: 1 }, kt);
      });
    });
  };

  // ---------- hero inserts: a full-frame cut-away on each problem line's key word (one new scene per line) ----------
  // gaming: pixel icon + 3D pixel word on a speed-line burst; phone: giant word + emoji on the app colour.
  K.inserts = function (tl, o) {
    o = Object.assign({ roles: ["hook", "problem"], dur: 0.85, max: 6 }, window.INSERTS || {}, o || {});
    const lines = I.lines.filter((l) => o.roles.includes(l.role) && (l.key || l.money)).slice(0, o.max);
    const box = K.div("ins-layer", K.root(), "position:absolute;inset:0;z-index:55;pointer-events:none");
    const acc = I.type === "phone" ? K.app().accent : I.accent;
    lines.forEach((ln, i) => {
      const t = Math.max(ln.s + 0.15, ln.keyT - 0.05), d = Math.min(o.dur, Math.max(0.45, (K.end(ln) - t) * 0.55));
      const ins = K.div("ins ins-" + I.type, box, "position:absolute;inset:0;opacity:0;overflow:hidden;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:34px");
      const bg = K.div("", ins, `position:absolute;left:-600px;top:-600px;width:3120px;height:2280px;background:${I.type === "gaming"
        ? `repeating-conic-gradient(from ${i * 17}deg at 50% 50%, rgba(255,255,255,.10) 0 4deg, transparent 4deg 12deg), radial-gradient(circle at 50% 50%, ${ln.money ? "#7a0d0d" : "#1b2b4a"}, #05060a 60%)`
        : `repeating-linear-gradient(${i % 2 ? 110 : 70}deg, rgba(255,255,255,.12) 0 30px, transparent 30px 90px), ${ln.money ? "#d62828" : acc}`}`);
      let hero;
      if (I.type === "gaming") {
        K.icon(K.gicon(ln), 16, ins, "position:relative");
        const w = (ln.money || ln.key).toUpperCase();
        hero = K.pix3d(w, Math.max(10, Math.min(24, Math.floor(1600 / (w.length * 6)))), ["#ffffff", "#ffe9a6", "#ffc23a"], "#5a3300", 18, ins, "position:relative");
      } else {
        if (ln.icon) K.div("", ins, "position:relative;font:220px Emoji;line-height:1", ln.icon);
        hero = K.div("", ins, "position:relative;font:400 230px Anton, sans-serif;color:#fff;text-transform:uppercase;white-space:nowrap;text-shadow:0 14px 0 rgba(0,0,0,.18);line-height:.9", K.esc(ln.money || ln.key));
        K.fit(hero, 1760, 230, 90);
      }
      tl.set(ins, { opacity: 1 }, t);
      tl.fromTo(ins, { clipPath: i % 2 ? "inset(0 0 0 100%)" : "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0%)", duration: 0.12, ease: "power3.out" }, t);
      tl.fromTo(hero, { scale: 2.2, rotation: i % 2 ? 6 : -6 }, { scale: 1, rotation: 0, duration: 0.22, ease: "power4.out" }, t);
      tl.fromTo(bg, { rotation: 0, scale: 1 }, { rotation: i % 2 ? 12 : -12, scale: 1.15, duration: d, ease: "none" }, t);
      tl.to(ins, { clipPath: i % 2 ? "inset(0 100% 0 0)" : "inset(0 0 0 100%)", duration: 0.12, ease: "power3.in" }, t + d - 0.12);
      tl.set(ins, { opacity: 0 }, t + d);
    });
  };

  // ---------- real pictures (review videos): the real places/things the VO names, as tilted print cutouts; logos as stamps ----------
  // templates that place pictures themselves set window.PICS_HANDLED = true; otherwise this runs after the template.
  K.pictures = function (tl, o) {
    o = Object.assign({ tint: "saturate(1.08)", frame: "#f4f2ec", ink: "#111", logo: "white" }, window.PICS || {}, o || {});
    const box = K.div("pic-layer", K.root(), "position:absolute;inset:0;z-index:58;pointer-events:none");
    I.lines.forEach((ln, i) => (ln.pics || []).slice(0, 1).forEach((p) => {
      const t = Math.max(ln.s, p.t - 0.12), end = K.end(ln);
      const left = i % 2 === 1;
      if (p.kind === "logo") {
        const e = K.el("img", { attrs: { src: p.src }, style: `position:absolute;left:${left ? 120 : 1100}px;top:110px;width:680px;height:260px;object-fit:contain;opacity:0;` +
          (o.logo === "white" ? "filter:grayscale(1) invert(1) contrast(1.6);mix-blend-mode:screen" : "filter:grayscale(1) contrast(2);mix-blend-mode:multiply") }, box);
        tl.fromTo(e, { opacity: 0, scale: 1.7 }, { opacity: 0.95, scale: 1, duration: 0.2, ease: "power3.out" }, t);
        tl.to(e, { opacity: 0, duration: 0.14 }, end - 0.1);
        return;
      }
      const c = K.div("", box, `position:absolute;left:${left ? 110 : 1060}px;top:130px;width:740px;padding:14px 14px 64px;background:${o.frame};box-shadow:0 24px 60px rgba(0,0,0,.55);opacity:0`);
      K.el("img", { attrs: { src: p.src }, style: `display:block;width:712px;height:440px;object-fit:cover;filter:${o.tint}` }, c);
      K.div("", c, `position:absolute;left:0;right:0;bottom:12px;text-align:center;font:800 38px Poppins, sans-serif;color:${o.ink};text-transform:lowercase`, K.esc(p.label));
      tl.set(c, { opacity: 1 }, t);
      tl.fromTo(c, { rotation: left ? -16 : 16, scale: 1.5, y: 80 }, { rotation: left ? -4 : 4, scale: 1, y: 0, duration: 0.3, ease: "back.out(1.6)" }, t);
      tl.to(c, { rotation: left ? -2 : 2, y: -14, duration: Math.max(0.3, end - t - 0.4), ease: "sine.inOut" }, t + 0.3);
      tl.to(c, { opacity: 0, x: left ? -260 : 260, duration: 0.2, ease: "power2.in" }, end - 0.18);
    }));
  };

  // ---------- generated motion graphics (review intros, build_intro.review_graphics; dhgate cartier watch 2026-10-22:
  // "too much of the watch ... more motion graphics, different things that need to be generated"). Full-frame cards over the
  // footage, under the captions (z 35 < kin 40): price = a swinging price tag counting up to the retail price he says, with a
  // RETAIL stamp on the word; compare = retail struck through, the DHgate price slams in, -NN% badge. His own numbers only.
  K.reviewMG = function (tl) {
    const box = K.div("mg-layer", K.root(), "position:absolute;inset:0;z-index:35;pointer-events:none");
    const fmt = (v) => "$" + Math.round(v).toLocaleString("en-US");
    const acc = I.accent || "#3DFF7A";
    (I.mg || []).filter((g) => g.type === "price" || g.type === "compare").forEach((g, i) => {   // stamp/chart/rain: K.editorMG
      const t = g.t, e = Math.max(g.t + 0.8, g.e);
      const card = K.div("mg mg-" + g.type, box, "position:absolute;inset:0;overflow:hidden;opacity:0");
      // g.over: a real price page plays under this line (lv skatesta 2026-10-24): no full-screen card, the tag floats over it
      const bg = g.over ? K.div("", card, "position:absolute;inset:0;background:linear-gradient(90deg, transparent 40%, rgba(0,0,0,.35))") :
        K.div("", card, `position:absolute;left:-700px;top:-700px;width:3320px;height:2480px;` +
        `background:repeating-conic-gradient(from ${i * 23}deg at 50% 50%, rgba(255,255,255,.06) 0 6deg, transparent 6deg 18deg), radial-gradient(circle at 50% 45%, #1d3b2a, #050807 62%)`);
      tl.set(card, { opacity: 1 }, t);
      if (g.over) tl.fromTo(card, { opacity: 0 }, { opacity: 1, duration: 0.2 }, t);
      else {
        tl.fromTo(card, { clipPath: "circle(0% at 50% 45%)" }, { clipPath: "circle(80% at 50% 45%)", duration: 0.28, ease: "power3.out" }, t);
        tl.fromTo(bg, { rotation: 0, scale: 1 }, { rotation: i % 2 ? -14 : 14, scale: 1.12, duration: e - t, ease: "none" }, t);
      }
      // three looks for the price, one per video (user 2026-10-26: "we've been using that tag for the price a lot ... the green
      // background with the price ... it just looks the same across all"); his editors' intros use all three: "glow" = a huge
      // glowing price over his footage (Balenciaga "$1000" on feet), "burst" = the glowing price on a purple sunburst (Moncler
      // "$2500"), "tag" = the swinging tag. I.priceStyle pins one; else the video's seed picks it.
      const ps = I.priceStyle || ["glow", "burst", "tag"][Math.abs(I.seed || 0) % 3];
      if (g.type === "price" && ps !== "tag") {
        if (ps === "glow") { card.style.background = "transparent"; bg.style.display = "none"; }
        else {
          // the sunburst's colour varies per video (user 2026-10-26: the purple one "could slide once, but I'm not sure if I'm
          // a big fan of it going forward ... look into that for different colors"): one of four per video.
          // I.priceBurst pins one by name.
          // kept by the user from the samples (2026-10-26: "blue red and green and purple are good"; charcoal + bronze out)
          const BURST = { navy: ["#123f8c", "#030a1c"], red: ["#8c1010", "#1c0303"], emerald: ["#0f6b43", "#02160d"],
                          purple: ["#5b1fa8", "#170530"] };
          const names = Object.keys(BURST);
          const [c1, c2] = BURST[I.priceBurst] || BURST[names[Math.floor(Math.abs(I.seed || 0) / 3) % names.length]];
          bg.style.background = `repeating-conic-gradient(from ${i * 23}deg at 50% 50%, rgba(255,255,255,.07) 0 7deg, transparent 7deg 20deg), radial-gradient(circle at 50% 50%, ${c1}, ${c2} 64%)`;
        }
        const big = K.div("", card, "position:absolute;left:0;right:0;top:" + (ps === "glow" ? 520 : 330) + "px;text-align:center;" +
          "font:400 260px Anton, sans-serif;color:#ffe14d;letter-spacing:4px;-webkit-text-stroke:6px #3a2a00;" +
          "text-shadow:0 0 30px rgba(255,225,77,.85),0 0 70px rgba(255,200,0,.55),0 14px 0 rgba(0,0,0,.35);opacity:0");
        big.textContent = fmt(g.value);
        const hit = Math.max(t + 0.1, Math.min(e - 0.5, g.hit || t + 0.2));
        tl.fromTo(big, { opacity: 0, scale: 2.2 }, { opacity: 1, scale: 1, duration: 0.2, ease: "power4.in" }, hit - 0.2);
        tl.to(big, { scale: 1.06, duration: Math.max(0.3, e - hit), ease: "sine.inOut" }, hit);
        const lab = K.div("", card, "position:absolute;left:0;right:0;top:" + (ps === "glow" ? 450 : 260) + "px;text-align:center;" +
          "font:900 54px Poppins, sans-serif;letter-spacing:14px;color:#fff;text-shadow:0 4px 0 rgba(0,0,0,.6),0 0 20px rgba(0,0,0,.7);opacity:0",
          K.esc(g.label || "RETAIL"));
        tl.fromTo(lab, { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.2 }, hit);
        K.shake(tl, big, hit, 10, 0.2);
      } else if (g.type === "price") {
        const tag = K.div("", card, (g.over ? "position:absolute;left:1040px;top:120px;" : "position:absolute;left:560px;top:150px;") +
          "width:800px;height:420px;border-radius:28px 140px 140px 28px;background:#f6f3ea;" +
          "box-shadow:0 30px 80px rgba(0,0,0,.6);transform-origin:8% 50%");
        K.div("", tag, "position:absolute;right:70px;top:180px;width:60px;height:60px;border-radius:50%;background:#050807");
        const num = K.div("", tag, "position:absolute;left:50px;top:95px;width:620px;text-align:center;font:400 190px Anton, sans-serif;color:#111;line-height:1.1");
        num.textContent = fmt(g.value);
        K.fit(num, 620, 190, 90);
        // the number he SAYS, never a count-up (dhgate cologne spread 2026-10-25, 0:08: the tag read $156 on its way to $200
        // while he said "200 dollars", "the number on screen must match what I say")
        const hit = Math.max(t + 0.2, Math.min(e - 0.5, g.hit || t + 0.3));
        const sc = g.over ? 0.72 : 1;   // over a page: smaller, upper right (the word captions sit low), the page stays readable
        tl.fromTo(tag, { rotation: -24, y: -500, scale: sc }, { rotation: 0, y: 0, scale: sc, duration: 0.5, ease: "back.out(1.5)" }, t);
        tl.to(tag, { rotation: 3, duration: Math.max(0.3, e - t - 0.6), ease: "sine.inOut" }, t + 0.5);
        const st = K.div("", card, (g.over ? "position:absolute;left:1430px;top:40px;" : "position:absolute;left:1180px;top:110px;") +
          "padding:10px 34px;border:10px solid #ff3b3b;border-radius:16px;" +
          "font:400 96px Anton, sans-serif;letter-spacing:6px;color:#ff3b3b;opacity:0", K.esc(g.label || "RETAIL"));
        tl.fromTo(st, { opacity: 0, scale: 2.6, rotation: -4 }, { opacity: 1, scale: 1, rotation: 12, duration: 0.18, ease: "power4.in" }, hit);
        K.shake(tl, tag, hit + 0.18, 14, 0.25);
      } else if (g.type === "compare") {
        const old = K.div("", card, "position:absolute;left:0;right:0;top:120px;text-align:center;font:400 170px Anton, sans-serif;color:#9aa39d;opacity:0", fmt(g.from));
        const lab = K.div("", card, "position:absolute;left:0;right:0;top:72px;text-align:center;font:900 44px Poppins, sans-serif;letter-spacing:10px;color:#9aa39d;opacity:0", "RETAIL");
        const svg = K.svg(card, "position:absolute;left:0;top:0;width:1920px;height:1080px");
        const strike = K.path(svg, "M 640 230 L 1280 196", { color: "#ff3b3b", width: 18 });
        const now = K.div("", card, `position:absolute;left:0;right:0;top:360px;text-align:center;font:400 300px Anton, sans-serif;color:${acc};opacity:0;` +
          "text-shadow:0 16px 0 rgba(0,0,0,.35)", fmt(g.to));
        const dh = K.div("", card, "position:absolute;left:0;right:0;top:700px;text-align:center;font:900 52px Poppins, sans-serif;letter-spacing:12px;color:#fff;opacity:0", "ON DHGATE");
        const badge = K.div("", card, "position:absolute;left:1360px;top:330px;width:250px;height:250px;border-radius:50%;background:#ff3b3b;display:flex;align-items:center;" +
          "justify-content:center;font:400 96px Anton, sans-serif;color:#fff;opacity:0;box-shadow:0 20px 50px rgba(0,0,0,.5)", "-" + g.off + "%");
        tl.fromTo([old, lab], { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.25, ease: "power3.out" }, t + 0.05);
        K.draw(tl, strike, t + 0.35, 0.22, "power2.in");
        tl.to([old, lab], { opacity: 0.55, duration: 0.2 }, t + 0.6);
        tl.fromTo(now, { opacity: 0, scale: 2.4 }, { opacity: 1, scale: 1, duration: 0.22, ease: "power4.in" }, t + 0.65);
        K.shake(tl, card, t + 0.87, 18, 0.25);
        tl.fromTo(dh, { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.25 }, t + 0.95);
        tl.fromTo(badge, { opacity: 0, scale: 0, rotation: -90 }, { opacity: 1, scale: 1, rotation: 14, duration: 0.35, ease: "back.out(2.2)" }, t + 1.1);
      }
      tl.to(card, { clipPath: "circle(0% at 50% 45%)", duration: 0.2, ease: "power3.in" }, e - 0.2);
      tl.set(card, { opacity: 0 }, e);
    });
  };

  // ---------- the editor's toolkit (channel intro study 2026-10-24, _references/channel/STUDY.md) ----------
  // stamp = a red rubber stamp slammed over the footage on his verdict word ("GATEKEEPER" over the masked man); chart = a
  // full-frame bar chart rising with a glowing trend line ("HIGH PROFIT"); rain = bills falling over the footage on money
  // lines ("a few thousand $$"). Drawn, never cash stock. Placed by build_intro.editor_graphics on his own words.
  K.editorMG = function (tl) {
    const box = K.div("emg-layer", K.root(), "position:absolute;inset:0;z-index:36;pointer-events:none");
    const acc = I.accent || "#3DFF7A";
    (I.mg || []).filter((g) => ["stamp", "chart", "rain"].includes(g.type)).forEach((g, i) => {
      const t = g.t, e = Math.max(t + 0.7, g.e);
      const r = K.rng((I.seed || 3) + i * 17);
      if (g.type === "stamp") {
        const st = K.div("", box, "position:absolute;left:50%;top:46%;padding:14px 46px;border:14px solid #e8262b;border-radius:22px;" +
          "font:400 150px Anton, sans-serif;letter-spacing:8px;color:#e8262b;background:rgba(255,255,255,.88);white-space:nowrap;" +
          "box-shadow:0 18px 50px rgba(0,0,0,.45);opacity:0;-webkit-mask-image:radial-gradient(circle at 30% 40%, #000 62%, rgba(0,0,0,.82) 63%)", K.esc(g.label));
        K.fit(st, 1500, 150, 70);
        gsap.set(st, { xPercent: -50, yPercent: -50 });
        tl.fromTo(st, { opacity: 0, scale: 3.2, rotation: -14 }, { opacity: 1, scale: 1, rotation: -6, duration: 0.16, ease: "power4.in" }, t);
        K.shake(tl, K.root(), t + 0.16, 16, 0.22);
        tl.to(st, { scale: 1.04, duration: Math.max(0.2, e - t - 0.4), ease: "none" }, t + 0.2);
        tl.to(st, { opacity: 0, scale: 0.9, duration: 0.15 }, e - 0.15);
      } else if (g.type === "chart") {
        const card = K.div("", box, "position:absolute;inset:0;overflow:hidden;opacity:0;background:radial-gradient(circle at 50% 60%, #12301f, #040806 70%)");
        const n = 16, base = 860, left = 360, bw = 62, gap = 18;
        const hs = Array.from({ length: n }, (_, k) => 90 + Math.pow(k / (n - 1), 1.6) * 520 + r() * 60);
        hs.forEach((h, k) => {
          const b = K.div("", card, `position:absolute;left:${left + k * (bw + gap)}px;top:${base - h}px;width:${bw}px;height:${h}px;` +
            "background:linear-gradient(#ffffff, #b9f5cf);border-radius:6px 6px 0 0;transform-origin:50% 100%;box-shadow:0 0 18px rgba(255,255,255,.35)");
          tl.fromTo(b, { scaleY: 0 }, { scaleY: 1, duration: 0.5, ease: "power3.out" }, t + 0.1 + k * 0.04);
        });
        const svg = K.svg(card, "position:absolute;left:0;top:0;width:1920px;height:1080px");
        const pts = hs.map((h, k) => `${left + k * (bw + gap) + bw / 2} ${base - h - 40}`).join(" L ");
        const line = K.path(svg, "M " + pts, { color: acc, width: 12 });
        line.style.filter = `drop-shadow(0 0 14px ${acc})`;
        K.draw(tl, line, t + 0.3, 0.8, "power2.out");
        const lab = K.div("", card, `position:absolute;left:0;right:0;top:110px;text-align:center;font:400 150px Anton, sans-serif;color:${acc};` +
          `text-shadow:0 0 30px ${acc}, 0 8px 0 rgba(0,0,0,.4);letter-spacing:3px;opacity:0`, K.esc(g.label));
        tl.fromTo(card, { opacity: 0 }, { opacity: 1, duration: 0.15 }, t);
        tl.fromTo(lab, { opacity: 0, scale: 1.6 }, { opacity: 1, scale: 1, duration: 0.2, ease: "power4.out" }, t + 0.15);
        tl.fromTo(card, { scale: 1 }, { scale: 1.06, duration: e - t, ease: "none" }, t);
        tl.to(card, { opacity: 0, duration: 0.15 }, e - 0.15);
      } else if (g.type === "rain") {
        const layer = K.div("", box, "position:absolute;inset:0;overflow:hidden");
        for (let k = 0; k < 26; k++) {
          const x = r() * 1900 - 60, d = 0.9 + r() * 0.9, t0 = t + r() * 0.5, rot = (r() - 0.5) * 120;
          const bill = K.div("", layer, "position:absolute;top:-220px;left:" + x + "px;width:230px;height:104px;border-radius:8px;" +
            "background:linear-gradient(135deg,#d9ead3,#8fbf86);border:5px solid #5e8f56;box-shadow:0 10px 24px rgba(0,0,0,.35);" +
            "display:flex;align-items:center;justify-content:center;font:900 54px Poppins, sans-serif;color:#3d6b37;opacity:0", "$");
          tl.set(bill, { opacity: 1 }, t0);
          tl.fromTo(bill, { y: 0, rotation: rot, x: 0 }, { y: 1400, rotation: rot + (r() - 0.5) * 360, x: (r() - 0.5) * 300, duration: d * 1.6, ease: "power1.in" }, t0);
          tl.set(bill, { opacity: 0 }, Math.min(e, t0 + d * 1.6));
        }
      }
    });
  };

  // cartoon FX transitions over a cut (build_intro.fx_plan, 3-4 per intro): burst = an orange/yellow flame star exploding out
  // from the centre; smoke = a white cartoon puff that covers the frame and clears; swirl = cyan slashes spinning across;
  // fire = flames licking up from the bottom edge. Each covers the cut for ~0.2 s so the next shot lands under it.
  K.fxCut = function (tl, t, kind, i) {
    // the orange cartoon burst / fire are BANNED (user 2026-10-24: "looks very corny ... makes the video quality go down")
    // ...and the cartoon smoke puff / swirl too ("keep only effects that look professional"): every cartoon kind becomes a
    // light leak. Only "lightleak" and "flash" are drawn.
    if (kind !== "flash") kind = "lightleak";
    if (kind === "flash") { K.flash(tl, t, "#fff", K.over(), 0.18); return; }
    {
      const box = K.div("fx-cut", K.root(), "position:absolute;inset:0;z-index:72;pointer-events:none;overflow:hidden;mix-blend-mode:screen");
      const dir = i % 2 ? -1 : 1;
      const leak = K.div("", box, "position:absolute;top:-200px;left:-900px;width:1500px;height:1480px;opacity:0;" +
        "background:radial-gradient(ellipse at 50% 50%, rgba(255,255,255,.95) 0%, rgba(255,246,230,.75) 22%, rgba(255,236,210,.25) 48%, transparent 70%);" +
        "filter:blur(30px)");
      const x0 = dir > 0 ? -1200 : 1900, x1 = dir > 0 ? 1900 : -1200;
      tl.fromTo(leak, { x: x0, opacity: 0 }, { x: (x0 + x1) / 2, opacity: 1, duration: 0.24, ease: "power2.in" }, t - 0.24);
      tl.to(leak, { x: x1, opacity: 0, duration: 0.3, ease: "power2.out" }, t);
      tl.set(box, { opacity: 0 }, t + 0.35);
      return;
    }
    const box = K.div("fx-cut", K.root(), "position:absolute;inset:0;z-index:72;pointer-events:none;overflow:hidden");
    const r = K.rng((I.seed || 5) + i * 31);
    const svg = K.svg(box, "position:absolute;left:0;top:0;width:1920px;height:1080px");
    const star = (cx, cy, R, rin, n, rot) => Array.from({ length: n * 2 }, (_, k) => {
      const a = rot + (k * Math.PI) / n, rr = k % 2 ? rin : R * (0.75 + r() * 0.5);
      return `${(cx + Math.cos(a) * rr).toFixed(0)},${(cy + Math.sin(a) * rr).toFixed(0)}`;
    }).join(" ");
    const poly = (pts, fill) => {
      const p = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
      p.setAttribute("points", pts); p.setAttribute("fill", fill); p.setAttribute("stroke", "#1a0d00"); p.setAttribute("stroke-width", "10");
      svg.appendChild(p); return p;
    };
    const t0 = Math.max(0, t - 0.22);
    if (kind === "burst" || kind === "fire") {
      const layers = kind === "burst"
        ? [[1500, 520, 14, "#ff3d00"], [1150, 380, 12, "#ff9100"], [760, 250, 10, "#ffd600"], [380, 130, 9, "#fff6c2"]]
        : [[1400, 420, 18, "#ff3d00"], [1050, 300, 15, "#ff9100"], [700, 200, 12, "#ffd600"]];
      const cy = kind === "burst" ? 540 : 1180;
      layers.forEach(([R, rin, n, col], k) => {
        const p = poly(star(960, cy, R, rin, n, r() * 6), col);
        p.style.transformOrigin = `960px ${cy}px`;
        tl.fromTo(p, { scale: 0, rotation: -20 }, { scale: 1, rotation: 10, duration: 0.24, ease: "power3.out" }, t0 + k * 0.03);
        tl.to(p, { scale: 1.6, opacity: 0, duration: 0.22, ease: "power2.in" }, t + 0.06 + k * 0.03);
      });
    } else if (kind === "smoke") {
      for (let k = 0; k < 18; k++) {
        const x = 960 + (r() - 0.5) * 1700, y = 540 + (r() - 0.5) * 900, rad = 220 + r() * 260;
        const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        c.setAttribute("cx", x.toFixed(0)); c.setAttribute("cy", y.toFixed(0)); c.setAttribute("r", rad.toFixed(0));
        c.setAttribute("fill", k % 3 ? "#ffffff" : "#d9dde3"); c.setAttribute("stroke", "#222"); c.setAttribute("stroke-width", "8");
        svg.appendChild(c);
        c.style.transformOrigin = `${x}px ${y}px`;
        tl.fromTo(c, { scale: 0 }, { scale: 1, duration: 0.2, ease: "back.out(1.6)" }, t0 + r() * 0.08);
        tl.to(c, { scale: 0.2, opacity: 0, x: (r() - 0.5) * 500, y: (r() - 0.5) * 300, duration: 0.28, ease: "power2.in" }, t + 0.05 + r() * 0.1);
      }
    } else {   // swirl
      for (let k = 0; k < 5; k++) {
        const s = K.div("", box, "position:absolute;left:-400px;top:" + (60 + k * 200) + "px;width:2700px;height:" + (60 + r() * 60) + "px;border-radius:60px;" +
          "background:linear-gradient(90deg, transparent, #7ff6ff 30%, #ffffff 50%, #39d0ff 70%, transparent);box-shadow:0 0 30px #39d0ff");
        tl.fromTo(s, { x: k % 2 ? 2400 : -2400, rotation: -18 + k * 4 }, { x: 0, duration: 0.2, ease: "power3.out" }, t0 + k * 0.025);
        tl.to(s, { x: k % 2 ? -2400 : 2400, duration: 0.2, ease: "power3.in" }, t + 0.04 + k * 0.025);
      }
    }
    tl.set(box, { opacity: 0 }, t + 0.6);
  };

  // phrase captions (his editor's look): 2-4 word phrases in a heavy display face, uppercase, glowing; key phrases slam with
  // faded echo copies above and below ("THE BUSINESS" x3). The last line is the hero: huge yellow outlined words, one at a
  // time ("IN HAND" / "REAL REVIEW"). Colours: white, his accent on key words, yellow for the hero.
  K.punch = function (tl, o) {
    o = Object.assign({ until: 1e9, accent: I.accent || "#3DFF7A", hero: null }, o || {});
    const box = K.div("punch-layer", K.root(), "position:absolute;inset:0;z-index:40;pointer-events:none");
    const words = (I.words || []).filter((w) => !w.date);
    const heroT = o.hero != null ? o.hero : 1e9;
    const body = words.filter((w) => w.s < heroT);
    const cs = K.chunks(body, { max: 3, chars: 16 });
    const spots = [[960, 820], [960, 300], [960, 560], [960, 840], [960, 260]];
    cs.forEach((c, i) => {
      const end = Math.min(o.until, c.next < c.e + 0.7 ? c.next - 0.01 : c.e + 0.7);
      if (end <= c.s + 0.05) return;
      const txt = c.words.map((w) => K.clean(w.w).toUpperCase()).join(" ");
      const key = c.key || c.words.some((w) => w.k);
      const col = key ? o.accent : "#ffffff";
      const [x, y] = window.CAP_LOW ? [960, 900] : K.slotsIn(c.s, c.s + 0.05).length ? spots[(i % 2) ? 3 : 0] : spots[i % spots.length];
      const mk = (op, dy) => {
        const e = K.div("", box, `position:absolute;left:${x}px;top:${y + dy}px;font:400 ${key ? 150 : 118}px Anton, sans-serif;letter-spacing:2px;` +
          `color:${col};white-space:nowrap;opacity:0;-webkit-text-stroke:7px #000;paint-order:stroke fill;` +
          `text-shadow:0 0 26px ${col}aa, 0 8px 18px rgba(0,0,0,.85), 0 0 6px #000`, K.esc(txt));   // readable on white pages too
        K.fit(e, 1700, key ? 150 : 118, 60);
        gsap.set(e, { xPercent: -50, yPercent: -50 });
        tl.fromTo(e, { opacity: 0, scale: key ? 1.9 : 1.25 }, { opacity: op, scale: 1, duration: key ? 0.13 : 0.12, ease: "power4.out" }, c.s + (dy ? 0.05 : 0));
        tl.set(e, { opacity: 0 }, end);
      };
      mk(1, 0);
      if (key && end - c.s > 0.5) { mk(0.22, -150); mk(0.22, 150); }
    });
    // hero ending: his last line, word by word, huge yellow with a black outline
    const hw = words.filter((w) => w.s >= heroT && w.s < o.until);
    hw.forEach((w, k) => {
      const e = K.div("", box, "position:absolute;left:960px;top:" + (k % 2 ? 700 : 380) + "px;font:400 230px Anton, sans-serif;color:#ffe600;" +
        "-webkit-text-stroke:10px #111;paint-order:stroke fill;white-space:nowrap;opacity:0;text-shadow:0 14px 0 rgba(0,0,0,.45)", K.esc(K.clean(w.w).toUpperCase()));
      K.fit(e, 1700, 230, 100);
      gsap.set(e, { xPercent: -50, yPercent: -50 });
      tl.fromTo(e, { opacity: 0, scale: 2.4 }, { opacity: 1, scale: 1, duration: 0.12, ease: "power4.in" }, w.s);
      const nx = hw[k + 2];
      tl.set(e, { opacity: 0 }, Math.min(o.until, nx ? nx.s : w.e + 1.2));
    });
    return box;
  };

  // ---------- speech bubbles: people the VO quotes (asics intro 2026-10-22: "the TSA agents were making comments about my
  // ASICS" needed a graphic). A bubble with typing dots pops on the comment line; the reported words fill it when he says
  // them ("they said they were very comfortable shoes"). Text is only ever his own words, never invented dialogue.
  K.quotes = function (tl) {
    const box = K.div("quote-layer", K.root(), "position:absolute;inset:0;z-index:60;pointer-events:none");
    I.lines.forEach((ln, i) => (ln.quotes || []).forEach((q, j) => {
      const t = Math.max(ln.s, q.t - 0.1), end = q.until || K.end(ln);
      const right = (i + j) % 2 === 0;
      const b = K.div("", box, `position:absolute;${right ? "right" : "left"}:140px;top:${170 + j * 210}px;max-width:900px;padding:30px 44px 34px;` +
        "background:#fff;border-radius:46px;box-shadow:0 22px 60px rgba(0,0,0,.5);opacity:0");
      K.div("", b, `position:absolute;bottom:-26px;${right ? "right" : "left"}:90px;width:0;height:0;border-left:26px solid transparent;` +
        "border-right:26px solid transparent;border-top:30px solid #fff");
      if (q.who) K.div("", b, "position:absolute;top:-30px;left:34px;padding:8px 22px;border-radius:30px;background:#ffcc00;" +
        "font:900 30px Poppins, sans-serif;letter-spacing:2px;color:#111", K.esc(q.who));
      const dots = K.div("", b, "font:900 64px Poppins, sans-serif;color:#9aa0a6;line-height:1;letter-spacing:8px", "•••");
      const txt = K.div("", b, "font:900 60px Poppins, sans-serif;color:#111;line-height:1.08;display:none", K.esc(q.text || ""));
      tl.set(b, { opacity: 1 }, t);
      tl.fromTo(b, { scale: 0.2, rotation: right ? 8 : -8, transformOrigin: right ? "90% 110%" : "10% 110%" },
        { scale: 1, rotation: right ? 2 : -2, duration: 0.32, ease: "back.out(2)" }, t);
      tl.fromTo(dots, { opacity: 0.35 }, { opacity: 1, duration: 0.25, repeat: 5, yoyo: true, ease: "sine.inOut" }, t + 0.1);
      if (q.text && q.fill != null) {
        tl.set(dots, { display: "none" }, q.fill);
        tl.set(txt, { display: "block" }, q.fill);
        tl.fromTo(b, { scale: 0.92 }, { scale: 1, duration: 0.22, ease: "back.out(2.4)" }, q.fill);
      } else if (q.text) {
        tl.set(dots, { display: "none" }, t + 0.45);
        tl.set(txt, { display: "block" }, t + 0.45);
      }
      tl.to(b, { opacity: 0, scale: 0.85, duration: 0.16, ease: "power2.in" }, end - 0.16);
    }));
  };

  // ---------- scene director (scene banks: kit/scenes_<type>.js register K.SCENES + K.sceneFor) ----------
  // the director: every line its own scene, cut with the theme's transition; the theme draws frame + title
  // full-frame moving clip under a line's scene (dhgate coupons 2026-10-24: type beats on flat light backgrounds, "lacking
  // motion"). Never blurred; a wash in the template's own tone keeps its ink readable; it glides the whole line.
  K.backdrop = function (tl, box, sl, t0, t1, i) {
    const w = K.slot(sl.i);
    if (!w) return;
    box.appendChild(w);
    w.style.cssText += ";position:absolute;inset:0;width:100%;height:100%;object-fit:cover;opacity:1";
    const v = w.tagName === "VIDEO" ? w : w.querySelector("video");
    if (v) v.style.cssText += ";width:100%;height:100%;object-fit:cover";
    // the template's ink as the browser resolves it (#111, rgb(), names...): dark ink gets a light wash, light ink a dark one
    // (first coupons test 2026-10-24: "#111"-style ink missed a 6-digit match -> dark wash -> dark words on dark footage)
    const probe = K.div("", box, "position:absolute;width:0;height:0;color:var(--p-ink, #ffffff)");
    const rgb = (getComputedStyle(probe).color.match(/\d+(\.\d+)?/g) || [255, 255, 255]).map(Number);
    probe.remove();
    const darkInk = rgb[0] * 0.3 + rgb[1] * 0.59 + rgb[2] * 0.11 < 128;
    // a lighter wash + richer footage (coupons 2026-10-24: "something just doesn't feel crispy"; .55 washed the clips out)
    w.style.filter = "saturate(1.2) contrast(1.06)";
    K.div("", box, `position:absolute;inset:0;background:${darkInk ? "rgba(255,255,255,.38)" : "rgba(0,0,0,.38)"}`);
    const dir = i % 2 ? -1 : 1;
    // gentle: one slow push, no sideways drift ("a lot of random zoom", 2026-10-24)
    tl.fromTo(w, { scale: 1.03 }, { scale: 1.08, duration: Math.max(0.3, t1 - t0), ease: "none" }, t0);
  };
  K.director = function (tl, o) {
    o = Object.assign({ cut: "whip", bg: null, frame: null, title: null, used: {} }, o || {});
    window.INSERTS = false;   // the scene bank already gives every line its own scene
    const lines = I.lines;
    const turn = I.beats.turn, last = I.words[I.words.length - 1].e;
    const t0title = I.beats.title != null ? I.beats.title : Math.max(last + 0.05, (I.beats.go || last) - 0.05);
    const host = K.div("dir", K.root(), "position:absolute;inset:0");
    const prevUsed = [];
    let prevBox = null;
    lines.forEach((ln, i) => {
      if (ln.role === "go" && i === lines.length - 1) return;   // the title owns the "let's go" line
      const t0 = Math.max(0, ln.s - 0.05), t1 = Math.min(t0title, i + 1 < lines.length ? lines[i + 1].s - 0.05 : t0title);
      if (t1 - t0 < 0.25) return;
      // a backdrop (build_intro.backdrop_slots, phone) is no scene of its own: it plays full frame UNDER this line's scene
      ln._slots = I.slots.filter((s) => s.line === i && !s.backdrop);
      ln._backdrop = I.slots.find((s) => s.line === i && s.backdrop) || null;
      const cands = (K.scenesFor ? K.scenesFor(ln, i) : [K.sceneFor(ln, i)]).concat(["word", "question"]);
      const count = (s) => prevUsed.filter((x) => x === s).length;
      const CLIP = ["facecam", "phoneclip", "gameplay"];   // the user's own clips: every line that has one shows it (2026-10-22)
      let sc = (ln._slots.length && CLIP.includes(cands[0]) ? cands[0] : null) || (window.SCENE_EXACT ? cands[0] : null) ||
        cands.find((s) => s !== prevUsed[prevUsed.length - 1] && (count(s) < 1 || ["gameplay", "word", "question", "carousel"].includes(s) && count(s) < 3 || s === "fees" && count(s) < 2)) || cands[0];   // vary: no repeat in a row, max 2 of a kind
      // window.CUT_ON_CHANGE (P21): a transition only when the PICTURE changes (2026-10-24: "I don't like the transition
      // effect if you're not transitioning to anything, this is just transitioning between text ... I do agree with the
      // transition to the logo"): same graphic continuing, or words to words, cut straight
      const prevSc = prevUsed[prevUsed.length - 1];
      const noCut = window.CUT_ON_CHANGE && (sc === prevSc && !CLIP.includes(sc) || sc === "word" && prevSc === "word");
      prevUsed.push(sc);
      const box = K.div("scene sc-" + sc, host, "position:absolute;inset:0;overflow:hidden;opacity:0");
      if (ln._backdrop) K.backdrop(tl, box, ln._backdrop, t0, t1, i);
      try { (K.SCENES[sc] || K.SCENES.word)(tl, box, ln, t0, t1, { slots: ln._slots, cont: sc === prevSc }); } catch (e) { console.error("scene " + sc, e); }
      // "push" (P21, 2026-10-24: "replace the orange swipe with a smoother, non-flashy transition"): the new scene glides
      // in from the right while the last one glides out left, both fading; no colour panel. The outgoing box stays up
      // through the push, so every box's hide is decided when the next line arrives.
      const push = o.cut === "push" && !noCut && prevBox;
      if (prevBox) {
        if (push) {
          tl.to(prevBox.box, { x: -260, opacity: 0, duration: 0.32, ease: "power2.in" }, t0);
          tl.set(prevBox.box, { opacity: 0 }, t0 + 0.34);
        } else tl.set(prevBox.box, { opacity: 0 }, Math.min(prevBox.t1 + 0.04, t0 + 0.02));
      }
      if (push) tl.fromTo(box, { x: 260, opacity: 0 }, { x: 0, opacity: 1, duration: 0.38, ease: "power3.out", immediateRender: false }, t0);
      else tl.set(box, { opacity: 1 }, t0);
      prevBox = { box, t1 };
      if (noCut || o.cut === "push") return;
      if (o.cut === "pixel") K.pixelWipe(tl, t0, i);
      else if (o.cut === "flash") K.flash(tl, t0, "#fff", K.over(), 0.12);
      else if (o.cut === "glitch") K.glitchCut(tl, t0, i);
      else if (o.cut === "swipe") K.swipeCut(tl, t0, i);
    });
    if (prevBox) tl.set(prevBox.box, { opacity: 0 }, prevBox.t1 + 0.04);   // the last scene leaves as before
    if (I.beats.gap) K.drop(tl, K.root());
    return { t0title };
  };
  // RGB-split glitch across a cut (a few seeded bands jump sideways for 3 frames)
  K.glitchCut = function (tl, t, seed) {
    if (t < 0.2) return;
    const r = K.rng(seed + 55), box = K.div("", K.over(), "position:absolute;inset:0;z-index:74;pointer-events:none");
    for (let i = 0; i < 7; i++) {
      const h = 20 + r() * 90, y = r() * 1000;
      const b = K.div("", box, `position:absolute;left:0;right:0;top:${y}px;height:${h}px;background:${i % 2 ? "rgba(255,0,80,.55)" : "rgba(0,220,255,.55)"};mix-blend-mode:screen;opacity:0`);
      tl.set(b, { opacity: 1, x: (r() - 0.5) * 300 }, t - 0.05);
      tl.set(b, { x: (r() - 0.5) * 200 }, t);
      tl.set(b, { opacity: 0 }, t + 0.07);
    }
  };
  // an accent-colour panel swiping across the cut (phone intros, dhgate coupons 2026-10-24: "more motion"; the brand-colour
  // wipe of the main video, never a dark panel). Direction alternates per line.
  K.swipeCut = function (tl, t, seed) {
    if (t < 0.2) return;
    const acc = (I.app && I.app.accent) || I.accent || "#3ec6ff", dir = seed % 2 ? 1 : -1;
    const p = K.div("", K.over(), `position:absolute;top:-300px;left:-400px;width:1100px;height:1680px;z-index:75;pointer-events:none;background:${acc};transform:rotate(14deg);opacity:0`);
    tl.set(p, { opacity: 1, x: dir > 0 ? -1200 : 2700 }, t - 0.16);
    tl.to(p, { x: dir > 0 ? 2700 : -1200, duration: 0.34, ease: "power2.inOut" }, t - 0.16);
    tl.set(p, { opacity: 0 }, t + 0.19);
  };
  // a blocky pixel wipe across the cut
  K.pixelWipe = function (tl, t, seed) {
    if (t < 0.2) return;
    const box = K.div("", K.over(), "position:absolute;inset:0;z-index:75;pointer-events:none");
    const r = K.rng(seed + 77), cols = 16, rows = 9;
    for (let j = 0; j < rows; j++) for (let i = 0; i < cols; i++) {
      const c = K.div("", box, `position:absolute;left:${i * 120}px;top:${j * 120}px;width:121px;height:121px;background:${(getComputedStyle(document.documentElement).getPropertyValue("--g-wipe").trim() || "#111")};opacity:0`);
      const d = (i / cols) * 0.12 + r() * 0.04;
      tl.set(c, { opacity: 1 }, t - 0.16 + d);
      tl.set(c, { opacity: 0 }, t + 0.02 + d);
    }
  };

  // ---------- bootstrap ----------
  K.start = function () {
    const tl = gsap.timeline({ paused: true });
    try { window.TEMPLATE(tl, I, K); } catch (err) { console.error("template error", err); }
    try { if (!(window.CAMERA && window.CAMERA.off)) K.camera(tl); } catch (err) { console.error("camera error", err); }
    try { if ((I.type === "gaming" || I.type === "phone") && window.INSERTS !== false) K.inserts(tl); } catch (err) { console.error("inserts error", err); }
    try { if (I.type === "review" && !window.PICS_HANDLED && I.lines.some((l) => (l.pics || []).length)) K.pictures(tl); } catch (err) { console.error("pictures error", err); }
    try { if (I.lines.some((l) => (l.quotes || []).length)) K.quotes(tl); } catch (err) { console.error("quotes error", err); }
    try { if (I.type === "review" && (I.mg || []).length && !window.MG_HANDLED) K.reviewMG(tl); } catch (err) { console.error("mg error", err); }
    // the editor's toolkit (templates with "editor": true): stamp / chart / money rain + cartoon FX transitions
    try { if ((I.mg || []).some((g) => ["stamp", "chart", "rain"].includes(g.type))) K.editorMG(tl); } catch (err) { console.error("editor mg error", err); }
    try { (I.fx || []).forEach((f, i) => K.fxCut(tl, f.t, f.kind, i)); } catch (err) { console.error("fx error", err); }
    // his pinned cuts with "flash": a short white camera flash on the cut (the builder puts a quiet shutter under it)
    try { (I.flashes || []).forEach((t) => K.flash(tl, t, "#fff", K.over(), 0.16)); } catch (err) { console.error("flash error", err); }
    // closing wipe slot: builder tells us when the intro hands over to the main video
    window.__timelines["intro"] = tl;
    if (window.__hfForceTimelineRebind) window.__hfForceTimelineRebind();
  };
  document.fonts.ready.then(K.start);
})();

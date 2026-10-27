/* Gaming scene bank: one literal, always-moving scene per VO line (the approved servers/realms/cobblemon method).
   A gaming template is a THEME (colours, textures, frame device, cut style, title) over these scenes.
   K.director(tl, opts) picks a scene for every line from what the line says (or I.scenes[i] from a beats.json),
   builds it inside the camera rig and plays it for exactly that line. Each scene animates the whole time it is up. */
(function () {
  const K = window.K, I = window.INTRO;
  const S = {};
  const R = (n) => K.rng((I.seed || 7) + n * 31);
  const css = (n, d) => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || d;
  const C = () => ({ a: css("--g-acc", "#ffd23a"), a2: css("--g-acc2", "#ff9d00"), ink: css("--g-ink", "#ffffff"), bad: css("--g-bad", "#ff5a4e"), good: css("--g-good", "#6dffb0"),
    panel: css("--g-panel", "rgba(5,8,14,.85)"), edge: css("--g-edge", "rgba(110,220,255,.6)") });
  const word = (ln) => (ln.role === "turn" && /today/i.test(ln.text) ? "IN TODAY'S VIDEO" : (ln.money || ln.key || K.short(ln.text, 3).replace(/…$/, ""))).toUpperCase();
  const pixWord = (txt, parent, maxW, maxCell, fill) => K.pixo(txt, K.pixFit(txt, maxW, maxCell), fill || ["#ffffff", "#d6d6d6"], {}, parent);
  const tag = (parent, style) => K.div("g-tag", parent, "position:absolute;padding:18px 26px;background:" + C().panel + ";border:4px solid " + C().edge + ";display:flex;align-items:center;gap:22px;" + (style || ""));
  const srvIcon = (seed, size, hue, parent) => {
    const r = K.rng(seed), cv = K.el("canvas", { cls: "pix", style: `width:${size}px;height:${size}px;flex:none;border:3px solid #111` }, parent);
    cv.width = 8; cv.height = 8;
    const x = cv.getContext("2d");
    x.fillStyle = `hsl(${hue},45%,18%)`; x.fillRect(0, 0, 8, 8);
    for (let y = 0; y < 8; y++) for (let c = 0; c < 4; c++) if (r() < 0.55) { x.fillStyle = `hsl(${hue + (r() * 40 - 20)},${60 + r() * 30}%,${42 + r() * 25}%)`; x.fillRect(c, y, 1, 1); x.fillRect(7 - c, y, 1, 1); }
    return cv;
  };
  const blockTex = (type, w, h, ps, seed, parent, style) => {
    const cv = K.el("canvas", { cls: "pix", style: `position:absolute;width:${w}px;height:${h}px;${style || ""}` }, parent);
    cv.width = Math.ceil(w / ps); cv.height = Math.ceil(h / ps);
    const x = cv.getContext("2d"), r = K.rng(seed), per = 12;
    for (let j = 0; j < cv.height; j++) for (let i = 0; i < cv.width; i++) {
      const n = r(), bx = i % per, by = j % per;
      let c;
      if (type === "gold") { let d = n * 40 - 20; if (bx === 0 || by === 0) d += 30; if (bx === per - 1 || by === per - 1) d -= 60; c = [250 + d, 205 + d, 60 + d * 0.6]; }
      else if (type === "stone") { const d = n * 36 - 18; c = [125 + d, 125 + d, 125 + d]; }
      else if (type === "sky") { const d = n * 12; c = [80 + d, 130 + d, 215 + d]; }
      else if (type === "nether") { let d = n * 24 - 12; if (by % 4 === 3) d -= 30; c = [90 + d, 30 + d, 34 + d]; }
      else { const top = by < 3, d = n * 30 - 15; c = top ? [93 + d, 155 + d, 47 + d] : [134 + d, 96 + d, 67 + d]; }
      x.fillStyle = `rgb(${c[0] | 0},${c[1] | 0},${c[2] | 0})`; x.fillRect(i, j, 1, 1);
    }
    return cv;
  };
  const NAMES = ["THE HIVE", "CUBECRAFT", "LIFEBOAT", "MELLOWCRAFT", "BLOCKHAVEN", "PIXELPEAK", "APPLEMC", "STONEWORKS", "CRAFTLAND", "NOVA REALMS", "OPLEGENDS", "EMBERSMP", "CLOUDPEAK", "IRONVALE", "FROSTBYTE", "OTTERSMP"];

  // 1. a tilted 3D server list scrolling fast ("many servers", "list", "different")
  S.list = (tl, box, ln, t0, t1) => {
    const persp = K.div("", box, "position:absolute;inset:0;perspective:1500px;perspective-origin:50% 40%");
    const plane = K.div("", persp, "position:absolute;left:50%;top:0;width:1180px;margin-left:-590px;transform-style:preserve-3d;transform-origin:50% 30%");
    NAMES.concat(NAMES).forEach((nm, i) => {
      const row = K.div("", plane, `height:128px;margin-bottom:14px;background:${i < 3 ? "#3d3418" : "#313233"};border:4px solid #1e1e1f;display:flex;align-items:center;padding:0 26px;gap:26px`);
      srvIcon(100 + i * 7, 88, (i * 47) % 360, row);
      K.pixo(nm, 6, i < 3 ? ["#ffe56b", "#ffb300"] : ["#ffffff", "#cfcfcf"], { outline: 0, shadow: 5 }, row);
    });
    tl.fromTo(plane, { rotationX: 30, rotationY: -16, z: -200, y: 120 }, { rotationX: 22, rotationY: -6, z: -60, y: -1500, duration: t1 - t0, ease: "power1.in" }, t0);
    const t = tag(box, "left:50%;top:430px;transform:translateX(-50%);z-index:3");
    K.icon(K.gicon(ln), 6, t);
    pixWord(word(ln), t, 1100, 12);
    tl.fromTo(t, { opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1, duration: 0.25, ease: "back.out(2)" }, Math.max(t0 + 0.15, ln.keyT - 0.05));
  };
  // 2. the list goes grey while a pixel sun sets behind a grass horizon ("don't get the light of day", "ignored", "nobody")
  S.sunset = (tl, box, ln, t0, t1) => {
    const sky = K.div("", box, "position:absolute;inset:0;background:linear-gradient(180deg,#26355e,#e0814a 70%,#f7c26b)");
    const sun = K.div("", box, "position:absolute;left:1380px;top:160px;width:170px;height:170px;background:#ffe36b;box-shadow:0 0 0 14px #ffb21f,0 0 100px 40px rgba(255,190,60,.55)");
    blockTex("grass", 1920, 260, 10, 9, box, "left:0;top:820px");
    const dark = K.div("", box, "position:absolute;inset:0;background:linear-gradient(180deg,rgba(3,4,10,.2),rgba(3,4,10,.92));opacity:0");
    tl.fromTo(sun, { y: 0 }, { y: 760, duration: t1 - t0, ease: "power1.in" }, t0);
    tl.fromTo(sky, { filter: "saturate(1) brightness(1)" }, { filter: "saturate(.3) brightness(.45)", duration: t1 - t0, ease: "none" }, t0);
    tl.to(dark, { opacity: 1, duration: t1 - t0, ease: "power1.in" }, t0);
    const t = tag(box, "left:50%;top:330px;transform:translateX(-50%)");
    pixWord(word(ln), t, 1200, 12, ["#e6e6e6", "#a8a8a8"]);
    tl.fromTo(t, { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.3, ease: "power3.out" }, Math.max(t0 + 0.1, ln.keyT - 0.1));
  };
  // 3. gold FEATURED cards rise, a crown drops on the key word, small cards get pushed off ("featured", "top", "best", "reign")
  S.featured = (tl, box, ln, t0, t1) => {
    K.div("", box, "position:absolute;left:50%;top:46%;width:2600px;height:2600px;margin:-1300px 0 0 -1300px;border-radius:50%;background:repeating-conic-gradient(rgba(255,206,70,.14) 0 8deg,transparent 8deg 20deg)").id = "";
    const rays = box.lastChild;
    tl.fromTo(rays, { rotation: 0 }, { rotation: 40, duration: t1 - t0, ease: "none" }, t0);
    const cards = [];
    for (let i = 0; i < 5; i++) {
      const c = K.div("", box, `position:absolute;top:430px;left:${960 + (i - 2) * 340 - 150}px;width:300px;height:380px;background:linear-gradient(180deg,#4a3d17,#2a220c);border:6px solid #ffcf3a;box-shadow:0 18px 50px rgba(0,0,0,.6),0 0 40px rgba(255,200,60,.35);display:flex;flex-direction:column;align-items:center;padding-top:34px;gap:22px`);
      srvIcon(900 + i * 13, 170, 30 + i * 60, c);
      K.pixo(NAMES[i], 4, "#fff", { outline: 0, shadow: 3 }, c);
      tl.fromTo(c, { y: 700, opacity: 0 }, { y: 0, opacity: 1, duration: 0.4, ease: "back.out(1.4)" }, t0 + 0.05 + i * 0.07);
      cards.push(c);
    }
    tl.to(cards, { y: -20, duration: t1 - t0 - 0.5, ease: "sine.inOut", stagger: 0.1 }, t0 + 0.5);
    const kw = K.div("", box, "position:absolute;left:0;right:0;top:120px;display:flex;justify-content:center");
    pixWord(word(ln), kw, 1500, 18, ["#ffe56b", "#ffb300"]);
    tl.fromTo(kw, { opacity: 0, scale: 2 }, { opacity: 1, scale: 1, duration: 0.22, ease: "power4.out" }, Math.max(t0 + 0.2, ln.keyT - 0.05));
    const crown = K.icon("crown", 15, box, "position:absolute;left:870px;top:250px");
    tl.fromTo(crown, { y: -500, opacity: 0 }, { y: 0, opacity: 1, duration: 0.35, ease: "bounce.out" }, Math.max(t0 + 0.4, ln.keyT + 0.2));
  };
  // 4. a controller, the cursor clicks ADD SERVER, it turns red, locks and shakes ("can't", "console", "locked", "blocked")
  S.locked = (tl, box, ln, t0, t1) => {
    const ctl = K.div("", box, "position:absolute;left:220px;top:330px");
    K.icon("pick", 22, ctl);
    const btn = K.div("", box, "position:absolute;left:900px;top:470px;width:720px;height:140px;background:#6f7071;border:5px solid #1e1e1f;box-shadow:inset 0 -10px 0 #4a4b4c,inset 0 6px 0 #9a9b9c;display:flex;align-items:center;justify-content:center");
    K.pixo("ADD SERVER", 8, "#e8e8e8", { outline: 0, shadow: 6 }, btn);
    const red = K.div("", btn, "position:absolute;inset:-5px;background:#b3261e;border:5px solid #3b0906;display:flex;align-items:center;justify-content:center;opacity:0");
    K.pixo(word(ln).slice(0, 14), 8, "#fff", { outline: 0, shadow: 6 }, red);
    const lock = K.icon("lock", 12, box, "position:absolute;left:1190px;top:180px;opacity:0");
    const cur = K.icon("cursor", 9, box, "position:absolute;left:0;top:0");
    tl.fromTo(btn, { opacity: 0, x: 300 }, { opacity: 1, x: 0, duration: 0.3, ease: "power3.out" }, t0 + 0.05);
    tl.fromTo(cur, { x: 1700, y: 900 }, { x: 1250, y: 540, duration: 0.5, ease: "power2.inOut" }, t0 + 0.2);
    const tc = Math.max(t0 + 0.75, ln.keyT);
    tl.fromTo(cur, { scale: 1 }, { scale: 0.8, duration: 0.07, yoyo: true, repeat: 1 }, tc);
    tl.set(red, { opacity: 1 }, tc + 0.1);
    K.shake(tl, btn, tc + 0.12, 16, 0.35);
    tl.fromTo(lock, { opacity: 0, y: -200 }, { opacity: 1, y: 0, duration: 0.3, ease: "bounce.out" }, tc + 0.15);
    tl.fromTo(ctl, { rotation: -8 }, { rotation: 8, duration: (t1 - t0) / 2, yoyo: true, repeat: 1, ease: "sine.inOut" }, t0);
  };
  // 5. radar sweep finding blips "#N ???" ("reveal", "find", "lesser known", "hidden", "discover")
  S.radar = (tl, box, ln, t0, t1) => {
    const rd = K.div("", box, "position:absolute;left:560px;top:140px;width:800px;height:800px");
    [400, 300, 200, 100].forEach((r) => K.div("", rd, `position:absolute;left:${400 - r}px;top:${400 - r}px;width:${r * 2}px;height:${r * 2}px;border:3px solid rgba(70,255,160,.35);border-radius:50%`));
    const sw = K.div("", rd, "position:absolute;inset:0;border-radius:50%;background:conic-gradient(from 0deg,rgba(70,255,160,0) 0 300deg,rgba(70,255,160,.45) 358deg,rgba(190,255,220,.9) 360deg)");
    tl.fromTo(sw, { rotation: 0 }, { rotation: 360 * Math.max(1, Math.round((t1 - t0) / 1.3)), duration: t1 - t0, ease: "none" }, t0);
    const r = R(5);
    for (let i = 0; i < 6; i++) {
      const a = r() * Math.PI * 2, d = 110 + r() * 260;
      const b = K.div("", rd, `position:absolute;left:${400 + Math.cos(a) * d - 13}px;top:${400 + Math.sin(a) * d - 13}px;width:26px;height:26px;background:#6dffb0;box-shadow:0 0 22px 8px rgba(80,255,170,.75);opacity:0`);
      K.pixo("#" + (10 - i) + " ???", 3, "#c8ffe3", { outline: 0, shadow: 3, shadowColor: "#05301a" }, K.div("", b, "position:absolute;left:36px;top:-6px"));
      tl.fromTo(b, { opacity: 0, scale: 3 }, { opacity: 1, scale: 1, duration: 0.18 }, t0 + 0.25 + i * Math.min(0.35, (t1 - t0 - 0.4) / 6));
    }
    const t = tag(box, "left:50%;top:40px;transform:translateX(-50%)");
    pixWord(word(ln), t, 1300, 10, ["#9df5ff", "#3fd0ff"]);
    tl.fromTo(t, { opacity: 0, y: -40 }, { opacity: 1, y: 0, duration: 0.25 }, Math.max(t0 + 0.1, ln.keyT - 0.05));
  };
  // 6. a tilted card carousel, each card snapping into focus on its word (game modes / list of things)
  S.carousel = (tl, box, ln, t0, t1, ctx) => {
    const items = K.lineWords(ln).filter((w) => w.k || /^[A-Z]/.test(w.w)).slice(0, 4);
    const list = items.length >= 2 ? items : [{ w: word(ln), s: ln.keyT }];
    const persp = K.div("", box, "position:absolute;inset:0;perspective:1600px");
    const track = K.div("", persp, "position:absolute;left:960px;top:540px;transform-style:preserve-3d");
    const BG = ["nether", "sky", "stone", "grass"];
    list.forEach((w, i) => {
      const c = K.div("", track, `position:absolute;left:${i * 640 - 280}px;top:-330px;width:560px;height:660px;border:8px solid #111;overflow:hidden;box-shadow:0 30px 80px rgba(0,0,0,.6)`);
      blockTex(BG[i % 4], 560, 660, 20, 300 + i, c, "left:0;top:0;filter:brightness(.55)");
      const sl = (ctx.slots || [])[i];
      if (sl) { const inn = K.div("", c, "position:absolute;inset:0"); K.into(tl, sl, inn); }
      else K.div("", c, "position:absolute;left:20px;top:20px;padding:6px 12px;background:rgba(0,0,0,.6);font:400 22px MC, monospace;color:#fff", "GAMEPLAY GOES HERE · " + K.esc(K.clean(w.w).toUpperCase()));
      const art = K.div("", c, "position:absolute;left:0;right:0;top:150px;display:flex;justify-content:center");
      K.icon(K.gicon({ text: w.w }), 22, art);
      const lb = K.div("", c, "position:absolute;left:0;right:0;bottom:60px;display:flex;justify-content:center");
      K.pixo(K.clean(w.w).toUpperCase().slice(0, 12), 9, ["#ffffff", "#d6d6d6"], {}, lb);
      tl.to(track, { x: -i * 640, duration: 0.3, ease: "power3.out" }, Math.max(t0 + 0.05, w.s - 0.1));
      tl.fromTo(c, { scale: 0.85 }, { scale: 1.04, duration: 0.25, ease: "back.out(2)" }, Math.max(t0 + 0.05, w.s - 0.1));
    });
    tl.fromTo(track, { rotationY: -14, rotationX: 6 }, { rotationY: -4, rotationX: 2, duration: t1 - t0, ease: "none" }, t0);
  };
  // 7. two block towers, one stacks up to match the other ("stack up", "compare", "versus", "better than")
  S.versus = (tl, box, ln, t0, t1) => {
    K.div("", box, "position:absolute;left:0;top:0;width:960px;height:1080px;background:linear-gradient(180deg,rgba(40,180,255,.16),rgba(40,180,255,.02))");
    K.div("", box, "position:absolute;left:960px;top:0;width:960px;height:1080px;background:linear-gradient(180deg,rgba(255,190,40,.18),rgba(255,190,40,.02))");
    blockTex("grass", 1920, 120, 12, 21, box, "left:0;top:960px");
    const n = 7, step = Math.min(0.22, (t1 - t0 - 0.6) / n);
    for (let i = 0; i < n; i++) {
      const g = blockTex("gold", 96, 96, 8, 500 + i, box, `left:${1920 - 196}px;top:${960 - 96 * (i + 1)}px`);
      tl.fromTo(g, { opacity: 0, y: -300 }, { opacity: 1, y: 0, duration: 0.2, ease: "bounce.out" }, t0 + 0.05 + i * 0.04);
      const l = blockTex("grass", 96, 96, 8, 600 + i, box, `left:100px;top:${960 - 96 * (i + 1)}px`);
      tl.fromTo(l, { opacity: 0, y: -400 }, { opacity: 1, y: 0, duration: 0.22, ease: "bounce.out" }, t0 + 0.35 + i * step);
    }
    const vs = K.div("", box, "position:absolute;left:0;right:0;top:380px;display:flex;justify-content:center");
    K.pixo("VS", 26, ["#ff5a4e", "#d1170d"], { shadow: 18 }, vs);
    tl.fromTo(vs, { opacity: 0, scale: 3 }, { opacity: 1, scale: 1, duration: 0.2, ease: "power4.out" }, Math.max(t0 + 0.2, ln.keyT - 0.05));
    const kw = K.div("", box, "position:absolute;left:0;right:0;top:120px;display:flex;justify-content:center");
    pixWord(word(ln), kw, 1400, 12);
    tl.fromTo(kw, { opacity: 0, y: -40 }, { opacity: 1, y: 0, duration: 0.25 }, t0 + 0.1);
  };
  // 8. gameplay full-frame with a pixel label (reveal lines with a clip)
  S.gameplay = (tl, box, ln, t0, t1, ctx) => {
    const sl = (ctx.slots || [])[0];
    const fr = K.div("", box, "position:absolute;left:150px;top:110px;width:1620px;height:860px;background:#000;border:8px solid #000;box-shadow:0 0 0 6px " + C().a + ",0 30px 80px rgba(0,0,0,.6)");
    const inn = K.div("", fr, "position:absolute;inset:0;overflow:hidden");
    if (sl) K.into(tl, sl, inn);
    else K.div("", inn, "position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:repeating-linear-gradient(45deg,#1c1c22 0 26px,#23232b 26px 52px);font:400 40px MC, monospace;color:#ccc", "GAMEPLAY GOES HERE · " + K.esc(word(ln)));
    tl.fromTo(fr, { scale: 0.7, rotation: -3, opacity: 0 }, { scale: 1, rotation: 0, opacity: 1, duration: 0.3, ease: "back.out(1.5)" }, t0);
    tl.fromTo(inn.firstChild || inn, { scale: 1.15 }, { scale: 1, duration: t1 - t0, ease: "none" }, t0);
    const lb = tag(box, "left:110px;top:840px;z-index:3");
    K.icon(K.gicon(ln), 5, lb);
    pixWord(word(ln), lb, 1100, 9, [C().a, C().a2]);
    tl.fromTo(lb, { opacity: 0, x: -200 }, { opacity: 1, x: 0, duration: 0.25, ease: "power3.out" }, Math.max(t0 + 0.15, ln.keyT - 0.05));
  };
  // 9. a big counting number ("10", "100", "900+") or a question ("any good?")
  S.count = (tl, box, ln, t0, t1) => {
    const n = parseInt((ln.text.match(/\d+/) || ["10"])[0], 10);
    const big = K.div("", box, "position:absolute;left:0;right:0;top:250px;display:flex;justify-content:center");
    const holder = K.div("", big);
    const parts = [];
    for (let v = 0; v <= 6; v++) parts.push(Math.round((n * v) / 6));
    parts.forEach((v, i) => {
      const c = K.pix3d(String(v), 30, ["#fff3a6", "#ffd23a", "#ff9d00"], "#7a3b00", 30, holder, "position:absolute;left:50%;transform:translateX(-50%);opacity:0");
      tl.set(c, { opacity: 1 }, t0 + i * 0.08);
      if (i < parts.length - 1) tl.set(c, { opacity: 0 }, t0 + (i + 1) * 0.08);
    });
    const kw = K.div("", box, "position:absolute;left:0;right:0;top:720px;display:flex;justify-content:center");
    pixWord(word(ln), kw, 1500, 12);
    tl.fromTo(kw, { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.25 }, t0 + 0.4);
    tl.fromTo(big, { scale: 0.6 }, { scale: 1.08, duration: t1 - t0, ease: "power2.out" }, t0);
  };
  S.question = (tl, box, ln, t0, t1) => {
    const q = K.div("", box, "position:absolute;left:0;right:0;top:200px;display:flex;justify-content:center");
    K.pixo("?", 40, ["#ffffff", "#d0d0d0"], { shadow: 26 }, q);
    tl.fromTo(q, { opacity: 0, scale: 0.2, rotation: -30 }, { opacity: 1, scale: 1, rotation: 0, duration: 0.35, ease: "back.out(2)" }, t0 + 0.05);
    tl.to(q, { rotation: 8, duration: 0.4, yoyo: true, repeat: Math.max(1, Math.floor((t1 - t0) / 0.4) - 1), ease: "sine.inOut" }, t0 + 0.4);
    const icons = ["sword", "gem", "chest", "heart", "crown", "pick"];
    icons.forEach((nm, i) => {
      const e = K.icon(nm, 8, box, `position:absolute;left:${940 + Math.cos(i) * 520}px;top:${420 + Math.sin(i) * 300}px`);
      tl.fromTo(e, { opacity: 0, scale: 0 }, { opacity: 1, scale: 1, duration: 0.2, ease: "back.out(3)" }, t0 + 0.2 + i * 0.06);
      tl.to(e, { y: -40, duration: 0.6, yoyo: true, repeat: Math.max(1, Math.floor((t1 - t0) / 0.6)), ease: "sine.inOut" }, t0 + 0.3 + i * 0.06);
    });
    const kw = K.div("", box, "position:absolute;left:0;right:0;top:820px;display:flex;justify-content:center");
    pixWord(word(ln), kw, 1400, 12, [C().a, C().a2]);
    tl.fromTo(kw, { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.25 }, Math.max(t0 + 0.2, ln.keyT - 0.05));
  };
  // 10. loot: a chest bursts open, items fly out ("free", "rewards", "loot", "win", "best")
  S.loot = (tl, box, ln, t0, t1) => {
    const ch = K.div("", box, "position:absolute;left:810px;top:500px");
    K.icon("chest", 25, ch);
    tl.fromTo(ch, { y: 600 }, { y: 0, duration: 0.35, ease: "back.out(1.6)" }, t0);
    tl.to(ch, { rotation: 4, duration: 0.06, yoyo: true, repeat: 5 }, t0 + 0.35);
    const beam = K.div("", box, "position:absolute;left:860px;top:-200px;width:200px;height:900px;background:linear-gradient(180deg,transparent," + C().a + ");opacity:0;filter:blur(6px)");
    const to = t0 + 0.75;
    tl.to(beam, { opacity: 0.7, duration: 0.2 }, to);
    const r = R(10);
    ["gem", "sword", "heart", "crown", "gem", "pick", "ball"].forEach((nm, i) => {
      const e = K.icon(nm, 9, box, "position:absolute;left:900px;top:540px;opacity:0");
      const a = -Math.PI / 2 + (r() - 0.5) * 2.4, v = 300 + r() * 300;
      tl.set(e, { opacity: 1 }, to);
      tl.fromTo(e, { x: 0, y: 0, rotation: 0 }, { x: Math.cos(a) * v, y: Math.sin(a) * v, rotation: (r() - 0.5) * 360, duration: 0.7, ease: "power2.out" }, to);
    });
    const kw = K.div("", box, "position:absolute;left:0;right:0;top:120px;display:flex;justify-content:center");
    pixWord(word(ln), kw, 1500, 16, [C().a, C().a2]);
    tl.fromTo(kw, { opacity: 0, scale: 2 }, { opacity: 1, scale: 1, duration: 0.22, ease: "power4.out" }, to);
  };
  // 11. two swords clash ("pvp", "fight", "battle", "kill")
  S.clash = (tl, box, ln, t0, t1) => {
    const a = K.icon("sword", 26, box, "position:absolute;left:520px;top:300px");
    const b = K.icon("sword", 26, box, "position:absolute;left:1080px;top:300px;transform:scaleX(-1)");
    const tc = Math.max(t0 + 0.35, ln.keyT);
    tl.fromTo(a, { x: -800, rotation: -60 }, { x: 120, rotation: 10, duration: 0.3, ease: "power3.in" }, tc - 0.3);
    tl.fromTo(b, { x: 800, rotation: 60 }, { x: -120, rotation: -10, duration: 0.3, ease: "power3.in" }, tc - 0.3);
    K.flash(tl, tc, "#fff", box, 0.15);
    const kw = K.div("", box, "position:absolute;left:0;right:0;top:780px;display:flex;justify-content:center");
    pixWord(word(ln), kw, 1500, 14, [C().bad, "#a10f08"]);
    tl.fromTo(kw, { opacity: 0, scale: 2.5 }, { opacity: 1, scale: 1, duration: 0.18, ease: "power4.out" }, tc);
    tl.to([a, b], { y: -30, duration: Math.max(0.2, t1 - tc - 0.2), ease: "sine.inOut" }, tc + 0.05);
  };
  // 12. generic: a big pixel word + icon on a burst, icons orbit (fallback)
  S.word = (tl, box, ln, t0, t1) => {
    const bg = K.div("", box, `position:absolute;left:-600px;top:-600px;width:3120px;height:2280px;background:repeating-conic-gradient(from 0deg at 50% 50%,rgba(255,255,255,.07) 0 4deg,transparent 4deg 12deg)`);
    tl.fromTo(bg, { rotation: 0 }, { rotation: 25, duration: t1 - t0, ease: "none" }, t0);
    const c = K.div("", box, "position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:40px");
    const ic = K.icon(K.gicon(ln), 16, c);
    pixWord(word(ln), c, 1600, 20, ln.s < I.beats.turn ? ["#ffffff", "#cfcfcf"] : [C().a, C().a2]);
    tl.fromTo(c, { scale: 0.6, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.25, ease: "back.out(2)" }, t0 + 0.04);
    tl.to(ic, { y: -24, duration: 0.45, yoyo: true, repeat: Math.max(1, Math.floor((t1 - t0) / 0.45)), ease: "sine.inOut" }, t0 + 0.3);
    tl.to(c, { scale: 1.08, duration: t1 - t0, ease: "none" }, t0 + 0.3);
  };

  // 13. a video-site results page: the query types, results scroll fast then ease to a stop, a gold frame + cursor click
  //     on one result ("youtube", "videos", "youtubers", "views", "searched"). Generic, drawn in code: no real logos.
  S.ytscroll = (tl, box, ln, t0, t1) => {
    const page = K.div("", box, "position:absolute;left:210px;top:60px;width:1500px;height:960px;background:#0f0f10;border-radius:22px;overflow:hidden;box-shadow:0 40px 120px rgba(0,0,0,.7),0 0 0 4px rgba(255,255,255,.08)");
    const head = K.div("", page, "position:absolute;left:0;top:0;right:0;height:110px;background:#121214;border-bottom:2px solid #262628;display:flex;align-items:center;gap:30px;padding:0 40px;z-index:3");
    const play = K.div("", head, "width:62px;height:62px;border-radius:50%;border:5px solid #e9e9ea;position:relative;flex:none");   // a generic play circle, never a brand mark
    K.div("", play, "position:absolute;left:21px;top:14px;border-left:22px solid #e9e9ea;border-top:12px solid transparent;border-bottom:12px solid transparent");
    const bar = K.div("", head, "flex:1;height:62px;border-radius:31px;background:#1e1e21;border:2px solid #3a3a3e;display:flex;align-items:center;padding:0 30px;font:500 34px Inter, sans-serif;color:#eee;overflow:hidden;white-space:nowrap");
    const q = (K.lineWords(ln).filter((w) => w.k).map((w) => K.clean(w.w)).join(" ") || word(ln)).toLowerCase().slice(0, 34);
    const qs = K.el("span", {}, bar);
    const cur0 = K.div("", bar, "width:3px;height:38px;background:#fff;margin-left:4px");
    const nType = Math.min(q.length, 34), tType = Math.min(0.55, (t1 - t0) * 0.2);
    for (let i = 1; i <= nType; i++) K.text(tl, qs, t0 + 0.08 + (tType * i) / nType, q.slice(0, i));
    tl.to(cur0, { opacity: 0, duration: 0.01, repeat: Math.max(1, Math.floor((t1 - t0) / 0.25)), yoyo: true }, t0);
    // results: drawn thumbnails (sky / grass / stone / nether scenes with a block sun), title bars, view-count bars
    const list = K.div("", page, "position:absolute;left:60px;top:150px;right:60px");
    const ROWH = 250, N = 18, target = 13, r = R(13), tex = ["sky", "grass", "stone", "nether", "gold"];
    let hit = null;
    for (let i = 0; i < N; i++) {
      const row = K.div("", list, `position:relative;height:${ROWH - 30}px;margin-bottom:30px;display:flex;gap:36px`);
      const th = K.div("", row, "position:relative;width:392px;height:220px;border-radius:14px;overflow:hidden;flex:none;background:#222");
      blockTex(tex[(i + 2) % tex.length], 392, 220, 14, 700 + i * 3, th, "left:0;top:0");
      blockTex("grass", 392, 70, 14, 800 + i, th, "left:0;top:150px");
      K.div("", th, `position:absolute;left:${40 + r() * 250}px;top:${24 + r() * 40}px;width:56px;height:56px;background:#ffe36b;box-shadow:0 0 0 6px #ffb21f`);
      K.div("", th, "position:absolute;right:10px;bottom:10px;padding:2px 10px;border-radius:6px;background:rgba(0,0,0,.8);font:600 22px Inter, sans-serif;color:#fff", `${1 + ((r() * 20) | 0)}:${String((r() * 60) | 0).padStart(2, "0")}`);
      const tx = K.div("", row, "flex:1;padding-top:10px;display:flex;flex-direction:column;gap:18px");
      K.div("", tx, `height:30px;width:${70 + r() * 25}%;border-radius:8px;background:#e9e9ea`);
      K.div("", tx, `height:30px;width:${35 + r() * 30}%;border-radius:8px;background:#e9e9ea`);
      const ch = K.div("", tx, "display:flex;align-items:center;gap:16px;margin-top:8px");
      K.div("", ch, `width:46px;height:46px;border-radius:50%;background:hsl(${(i * 67) % 360},60%,55%)`);
      K.div("", ch, `height:22px;width:${160 + r() * 140}px;border-radius:6px;background:#8c8c90`);
      K.div("", tx, `height:20px;width:${120 + r() * 120}px;border-radius:6px;background:#5d5d62`);
      if (i === target) hit = row;
    }
    // scroll: fast, then an ease-out crawl that parks the target row in the middle of the page
    const endY = -(target * ROWH) + 300, ts = t0 + 0.12 + tType;
    const tc = Math.min(t1 - 0.35, Math.max(ts + 1.0, ln.keyT + 0.3));
    tl.fromTo(list, { y: 0 }, { y: endY, duration: Math.max(0.6, tc - ts - 0.15), ease: "expo.out" }, ts);
    tl.fromTo(list, { filter: "blur(6px)" }, { filter: "blur(0px)", duration: Math.max(0.3, (tc - ts) * 0.5), ease: "power2.out" }, ts);
    const gold = K.div("", hit, "position:absolute;inset:-14px -20px;border:8px solid " + C().a + ";border-radius:20px;box-shadow:0 0 40px " + C().a + ";opacity:0");
    tl.fromTo(gold, { opacity: 0, scale: 1.15 }, { opacity: 1, scale: 1, duration: 0.2, ease: "back.out(2)" }, tc - 0.25);
    const cur = K.icon("cursor", 8, box, "position:absolute;left:0;top:0;z-index:5");
    tl.fromTo(cur, { x: 1750, y: 1000 }, { x: 760, y: 520, duration: 0.55, ease: "power2.inOut" }, Math.max(t0, tc - 0.65));
    tl.fromTo(cur, { scale: 1 }, { scale: 0.78, duration: 0.07, yoyo: true, repeat: 1 }, tc);
    tl.to(hit, { scale: 0.97, duration: 0.07, yoyo: true, repeat: 1 }, tc);
    tl.fromTo(page, { rotationX: 10, y: 60, opacity: 0 }, { rotationX: 0, y: 0, opacity: 1, duration: 0.3, ease: "power3.out" }, t0);
    tl.to(page, { scale: 1.06, duration: t1 - t0, ease: "none" }, t0 + 0.3);
  };

  // concept matching: which scene says this line literally
  const RULES = [
    [/stack up|compare|versus|\bvs\b|better than|against|actually (are|stack)/i, "versus"],
    [/youtube|youtubers?|\bvideos\b|thumbnails?|\bviews\b|search(ed|ing) (on|for|up)|scroll(ed|ing)?/i, "ytscroll"],
    [/light of day|ignored|nobody|no one|forgotten|underrated|overlooked|dead|empty/i, "sunset"],
    [/featured|reign|supreme|popular|biggest|top servers|the best/i, "featured"],
    [/can't|cannot|console|locked|blocked|not allowed|can not/i, "locked"],
    [/reveal|lesser|hidden|discover|find|search|investigat|uncover/i, "radar"],
    [/kit ?p|skyblock|prison|pixelmon|cobblemon|bedwars|smp|factions|lifesteal|oneblock|game ?modes?/i, "carousel"],
    [/pvp|fight|battle|kill|war|duel/i, "clash"],
    [/free|reward|loot|win|prize|giveaway|op items/i, "loot"],
    [/any good|worth it|\?$|what happens|is it|are they/i, "question"],
    [/\b\d{2,}\b/, "count"],
    [/many|servers|list|different|so many|tons of|hundreds/i, "list"],
  ];
  K.sceneFor = (ln, i) => (I.scenes && I.scenes[i]) || (ln.role === "reveal" && (ln._slots || []).length && !/kit ?p|skyblock|prison|pixelmon/i.test(ln.text) ? "gameplay" : null) ||
    (RULES.find(([re]) => re.test(ln.text)) || [null, ln.role === "reveal" ? "gameplay" : "word"])[1];
  K.scenesFor = (ln, i) => (I.scenes && I.scenes[i] ? [I.scenes[i]] : []).concat(ln.role === "reveal" && (ln._slots || []).length && !/kit ?p|skyblock|prison|pixelmon/i.test(ln.text) && i % 2 ? ["gameplay"] : [], RULES.filter(([re]) => re.test(ln.text.replace(/no secret/ig, ""))).map((r) => r[1]), [ln.role === "reveal" ? "gameplay" : "word"]);
  K.SCENES = S;

})();

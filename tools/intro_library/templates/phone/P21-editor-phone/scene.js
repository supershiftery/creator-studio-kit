window.CLIP_FULL = true;   // P21: real clips full frame (see scenes_phone.js S.facecam)
// THEME over the phone scene bank: Browser Research. Every VO line is its own literal scene (cart, receipt, gatekept codes, secret folder,
// $0.00 strike, group chat, orders at $0, plus the user's own face-cam / phone-screen clips); the frame device below ties them together.
// CALM (friend's + his note 2026-10-24 on the coupons intro: "too much going on ... a lot of random zoom, elements aren't on
// screen long enough for me to read them, numbers keep changing so I'm confused"): no camera rig, no number cards (the order
// totals / fee tags / coupon amounts were invented, he never says them): only his real clips and his own words as type
window.CAMERA = { off: true };
// SIMPLE (2026-10-24, he: "too much going on, too many numbers ... a more simplistic way to get the point across and also make
// it look nice ... we had glowing text, I thought that was a cool thing"): one clip per line full frame on a dark base, ONE
// caption track = his words as glowing phrases (K.punch), no scene text, no browser bar
window.NO_SCENE_TEXT = true;
window.SCENE_EXACT = true;   // the scene P21 picks per line is the one shown (checkout may run over several fee lines)
window.CAP_LOW = true;       // captions sit low, the graphic owns the middle
window.CUT_ON_CHANGE = true;  // a transition only when the picture changes (not between lines of one graphic / text)
window.TEMPLATE = function (tl, I, K) {
  K.SCENES.question = K.SCENES.word;   // the kit's last-resort fallback is the big "?": his words instead
  // CONTEXT (2026-10-24, he on the simple version: "a lot of the graphics don't make any sense now ... the jellyfish product
  // ... this girl, what is she doing in the video? someone on the keyboard ... it needs more better motion graphics"): a line
  // with no real clip of its own gets a clean motion graphic of WHAT HE SAYS, in the same glow, never random stock and never
  // a number he doesn't say. His real clips stay on the lines they show (homepage on "DHgate", the listing on "check out").
  const acc = I.accent || "#ffa000", GLOW = `0 0 22px ${acc}aa, 0 0 2px ${acc}`;
  const said = (ln, re) => (I.words || []).filter((w) => w.s >= ln.s - 0.05 && w.s < (ln.e || ln.s + 3) + 0.05 && re.test(w.w)).map((w) => w.s);
  const panel = (box, w, h, top) => K.div("", box, `position:absolute;left:${960 - w / 2}px;top:${top}px;width:${w}px;height:${h}px;border-radius:34px;` +
    "background:linear-gradient(160deg,rgba(255,255,255,.10),rgba(255,255,255,.03));border:2px solid rgba(255,255,255,.18);" +
    `box-shadow:0 30px 90px rgba(0,0,0,.6), inset 0 0 60px ${acc}14`);
  // SMOOTH (2026-10-24, he: "the animation just pauses ... it feels like it's almost lagging ... making the text more fluent
  // during the checkout process, because it feels like it stops"): a graphic that spans several lines is ONE graphic. Only
  // its first line animates it in; it then keeps one slow continuous push across the whole run (no restart, no jump at the
  // line changes), and only what he newly says animates on the later lines.
  const clipOf = (i) => (I.slots || []).find((sl) => sl.line === i && !sl.backdrop);
  const sceneOf = (i) => clipOf(i) ? (clipOf(i).kind === "phone" ? "phonefull" : "facecam") : ((GFX.find(([re]) => re.test(I.lines[i].text)) || [0, "word"])[1]);
  const runOf = (i) => {
    let a = i, b = i;
    while (a > 0 && sceneOf(a - 1) === sceneOf(i)) a--;
    while (b + 1 < I.lines.length && I.lines[b + 1].role !== "go" && sceneOf(b + 1) === sceneOf(i)) b++;
    return { s: I.lines[a].s - 0.05, e: b + 1 < I.lines.length ? I.lines[b + 1].s : I.dur, first: a === i };
  };
  const hold = (tl, box, ln, t0, t1) => {
    const r = runOf(I.lines.indexOf(ln)), w = K.div("", box, "position:absolute;inset:0");
    const f = (t) => 1 + 0.07 * Math.min(1, Math.max(0, (t - r.s) / Math.max(0.5, r.e - r.s)));
    tl.fromTo(w, { scale: f(t0) }, { scale: f(t1 + 0.05), duration: Math.max(0.05, t1 + 0.05 - t0), ease: "none" }, t0);
    return { w, first: r.first };
  };
  const enter = (tl, e, t, first, from, d) => first ? tl.fromTo(e, Object.assign({ opacity: 0 }, from), { opacity: 1, x: 0, y: 0, scale: 1, duration: d || 0.35, ease: "power3.out" }, t) : null;
  // 1. checkout: his fee words become rows that land when he says them; rows carry over across the fee lines
  const rowsShown = [];
  K.SCENES.checkout = (tl, box, ln, t0, t1) => {
    const { w, first } = hold(tl, box, ln, t0, t1);
    // AWAKE (2026-10-24, he: "these phone videos seem very tired and sleepy"): the camera punches in on each row as it lands
    const zw = K.div("", w, "position:absolute;inset:0");
    const card = panel(zw, 1100, 640, 100);
    K.div("", card, "position:absolute;left:60px;top:40px;font:400 84px Anton, sans-serif;color:#fff;letter-spacing:4px", "CHECKOUT");
    K.appIcon(card, 96, "position:absolute;right:56px;top:36px");
    const add = (label, t, k, isNew) => {
      const r = K.div("", card, `position:absolute;left:56px;right:56px;top:${170 + k * 92}px;height:80px;display:flex;align-items:center;` +
        `border-bottom:2px solid rgba(255,255,255,.12);font:400 70px Anton, sans-serif;letter-spacing:3px;color:${k ? acc : "#fff"};` +
        `text-shadow:${k ? GLOW : "none"};opacity:${isNew ? 0 : 1}`, (k ? "+ " : "") + K.esc(label));
      if (isNew) {
        tl.fromTo(r, { opacity: 0, x: 120 }, { opacity: 1, x: 0, duration: 0.35, ease: "power3.out" }, t);
        tl.fromTo(r, { textShadow: `0 0 60px ${acc}, 0 0 4px ${acc}` }, { textShadow: GLOW, duration: 0.6, ease: "power2.out" }, t + 0.3);
        tl.to(meter, { width: 120 + k * 200, duration: 0.4, ease: "power3.out" }, t + 0.1);
        const ry = 100 + 170 + k * 92 + 40;
        tl.to(zw, { scale: 1.32, x: 0, y: (540 - ry) * 0.32, transformOrigin: `960px ${ry}px`, duration: 0.32, ease: "power3.out" }, t - 0.06);
        tl.to(zw, { scale: 1, y: 0, duration: 0.55, ease: "power2.inOut" }, t + 0.85);
      }
    };
    const meter = K.div("", card, `position:absolute;left:56px;bottom:46px;height:22px;width:${120 + Math.max(0, rowsShown.length - 1) * 200}px;border-radius:11px;` +
      `background:linear-gradient(90deg,${acc},#ff3b3b);box-shadow:0 0 24px ${acc}aa`);
    const sheen = K.div("", card, "position:absolute;top:-20%;bottom:-20%;width:260px;left:-320px;transform:skewX(-18deg);" +
      "background:linear-gradient(90deg,transparent,rgba(255,255,255,.16),transparent)");
    card.style.overflow = "hidden";
    for (let x = t0 + 0.4; x < t1 - 0.6; x += 1.8) tl.fromTo(sheen, { left: -320 }, { left: 1240, duration: 0.9, ease: "power1.inOut" }, x);
    enter(tl, card, t0 + 0.02, first, { y: 60, scale: 0.94 });
    if (!rowsShown.length) rowsShown.push(["ITEMS", t0]);
    rowsShown.forEach(([lab], k) => add(lab, t0, k, false));
    [["SHIPPING", /^shipping/i], ["TAXES", /^tax/i], ["FEES", /^fees?\b/i], ["HANDLING", /^handling/i], ["SERVICE FEE", /^service/i]].forEach(([lab, re]) => {
      if (rowsShown.some((r) => r[0] === lab) || rowsShown.length >= 5) return;
      const ts = said(ln, re);
      if (!ts.length) return;
      rowsShown.push([lab, ts[0]]);
      add(lab, ts[0] - 0.08, rowsShown.length - 1, true);
    });
  };
  // 2. the total climbing: a TOTAL row whose bar keeps growing, a red arrow pulsing up (no amount)
  K.SCENES.totalup = (tl, box, ln, t0, t1) => {
    const { w, first } = hold(tl, box, ln, t0, t1);
    const card = panel(w, 1100, 380, 180);
    K.div("", card, "position:absolute;left:56px;top:46px;font:400 72px Anton, sans-serif;color:#fff;letter-spacing:3px", "TOTAL");
    const bar = K.div("", card, `position:absolute;left:56px;top:170px;height:70px;width:120px;border-radius:14px;background:linear-gradient(90deg,${acc},#ff3b3b);box-shadow:0 0 30px #ff3b3b88`);
    const arr = K.div("", card, "position:absolute;right:70px;top:40px;font:400 170px Anton, sans-serif;color:#ff3b3b;text-shadow:0 0 30px #ff3b3baa;line-height:1", "&#9650;");
    enter(tl, card, t0 + 0.02, first, { y: 60, scale: 0.94 });
    tl.to(bar, { width: 600, duration: Math.max(0.6, t1 - t0 - 0.3), ease: "power2.in" }, t0 + 0.2);
    // the amount HE says ("all the way up to $25") slams in on the word; never a number he doesn't say
    const amt = (I.words || []).find((w) => w.s >= ln.s - 0.05 && w.s < (ln.e || ln.s + 3) + 0.05 && /^\$\d/.test(w.w));
    if (amt) {
      const a = K.div("", card, `position:absolute;left:700px;top:150px;font:400 120px Anton, sans-serif;color:#fff;text-shadow:0 0 30px #ff3b3b, 0 0 4px #fff;opacity:0`,
        K.esc(amt.w.replace(/[^$\d.,]/g, "")));
      tl.fromTo(a, { opacity: 0, scale: 2.4 }, { opacity: 1, scale: 1, duration: 0.18, ease: "power4.in" }, amt.s - 0.04);
      tl.to(w, { scale: 1.16, duration: 0.22, ease: "power3.out" }, amt.s - 0.04);
    }
    const hit = said(ln, /^surpris|^shock|^crazy|^insane/i)[0];
    if (hit) {   // the word itself: the card punches in and the arrow flares
      tl.to(w, { scale: 1.18, duration: 0.25, ease: "power3.out" }, hit - 0.05);
      tl.fromTo(arr, { textShadow: "0 0 30px #ff3b3baa" }, { textShadow: "0 0 90px #ff3b3b, 0 0 20px #fff", duration: 0.3, yoyo: true, repeat: 1 }, hit);
    }
    tl.fromTo(arr, { y: 0 }, { y: -12, repeat: Math.max(1, Math.floor((t1 - t0) / 0.5)), yoyo: true, duration: 0.25, ease: "sine.inOut" }, t0 + 0.3);
  };
  // 3. the video's subject: the app's icon with glowing rings ("in today's video", "show you")
  K.SCENES.title = (tl, box, ln, t0, t1) => {
    const { w, first } = hold(tl, box, ln, t0, t1);
    [0, 1, 2].forEach((k) => {
      const d = 320 + k * 120;
      const r = K.div("", w, `position:absolute;left:${960 - d / 2}px;top:${400 - d / 2}px;width:${d}px;height:${d}px;border-radius:50%;border:3px solid ${acc};box-shadow:0 0 30px ${acc}88;opacity:${first ? 0 : 0.7 - k * 0.2}`);
      if (first) tl.fromTo(r, { opacity: 0, scale: 0.6 }, { opacity: 0.7 - k * 0.2, scale: 1, duration: 0.5, ease: "power3.out" }, t0 + 0.1 + k * 0.12);
    });
    const c = K.div("", w, "position:absolute;left:810px;top:250px;width:300px;height:300px");
    K.appIcon(c, 300, `box-shadow:0 0 60px ${acc}aa`);
    enter(tl, c, t0 + 0.05, first, { scale: 0.5 }, 0.4);
  };
  // 4. promo codes: three tickets fan in, codes hidden (never readable in an intro: retention)
  K.SCENES.tickets = (tl, box, ln, t0, t1) => {
    const { w, first } = hold(tl, box, ln, t0, t1);
    [-1, 0, 1].forEach((k, j) => {
      const tk = K.div("", w, `position:absolute;left:${960 - 330 + k * 250}px;top:${230 + Math.abs(k) * 40}px;width:660px;height:300px;border-radius:26px;` +
        `background:linear-gradient(135deg,${acc},#ffcf5a);box-shadow:0 30px 70px rgba(0,0,0,.55);transform-origin:50% 120%;transform:rotate(${k * 8}deg)`);
      K.div("", tk, "position:absolute;left:40px;top:34px;font:400 64px Anton, sans-serif;color:#111;letter-spacing:3px", "PROMO CODE");
      K.div("", tk, "position:absolute;left:40px;top:140px;width:580px;height:96px;border-radius:16px;background:rgba(0,0,0,.82);display:flex;align-items:center;" +
        "justify-content:center;font:900 54px Poppins, sans-serif;letter-spacing:22px;color:#fff", "&#9679;&#9679;&#9679;&#9679;&#9679;&#9679;");
      if (first) tl.fromTo(tk, { opacity: 0, y: 300, rotation: 0 }, { opacity: 1, y: 0, rotation: k * 8, duration: 0.45, ease: "back.out(1.4)" }, t0 + 0.05 + j * 0.15);
    });
  };
  // 5. saving: a price tag swings in, a strike line, a green SAVE stamp on the word
  K.SCENES.save = (tl, box, ln, t0, t1) => {
    const { w, first } = hold(tl, box, ln, t0, t1);
    const tag = K.div("", w, "position:absolute;left:560px;top:190px;width:800px;height:380px;border-radius:28px 150px 150px 28px;background:#f6f3ea;" +
      "box-shadow:0 30px 80px rgba(0,0,0,.6);transform-origin:8% 50%");
    K.div("", tag, "position:absolute;right:76px;top:160px;width:60px;height:60px;border-radius:50%;background:#0b0c0e");
    K.div("", tag, "position:absolute;left:70px;top:90px;font:400 170px Anton, sans-serif;color:#111;letter-spacing:4px", "PRICE");
    const strike = K.div("", tag, "position:absolute;left:50px;top:175px;height:18px;width:0;border-radius:9px;background:#ff3b3b");
    const st = K.div("", w, "position:absolute;left:1120px;top:120px;padding:10px 36px;border:12px solid #2fe37a;border-radius:18px;font:400 120px Anton, sans-serif;" +
      "letter-spacing:6px;color:#2fe37a;text-shadow:0 0 24px #2fe37a88;opacity:0", "SAVE");
    if (first) tl.fromTo(tag, { rotation: -24, y: -500 }, { rotation: 0, y: 0, duration: 0.5, ease: "back.out(1.5)" }, t0);
    const hit = Math.max(t0 + 0.6, said(ln, /^sav/i)[0] || t0 + 0.6);
    tl.to(strike, { width: 560, duration: 0.25, ease: "power2.in" }, hit - 0.2);
    tl.fromTo(st, { opacity: 0, scale: 2.6, rotation: -4 }, { opacity: 1, scale: 1, rotation: 10, duration: 0.16, ease: "power4.in" }, hit);
  };
  // 6. his ORDER (Uber codes october 2026-10-25: "big mac combo meal over here, some fries, boom ... there should've been
  //    graphics for all this stuff on the screen"): a YOUR ORDER card, each item he names lands as a row ON the word
  //    (his words, no prices he doesn't say); "boom" = the whole card punches in with a red glow (build_intro adds the impact)
  const ITEM = /^(combo|meals?|fries|burgers?|pizzas?|drinks?|sodas?|nuggets|wings|tacos?|burritos?|sandwich(es)?|salads?|coffees?|shakes?|desserts?|sides?)$/i;
  const STOPW = /^(a|an|the|some|then|and|you|get|got|over|here|of|with|your|my|me|i|to|it|this|that|plus|large|small|medium)$/i;
  const itemsShown = [];
  K.SCENES.order = (tl, box, ln, t0, t1) => {
    const { w, first } = hold(tl, box, ln, t0, t1);
    const zw = K.div("", w, "position:absolute;inset:0");
    const card = panel(zw, 1000, 700, 90);
    card.style.overflow = "hidden";
    K.div("", card, "position:absolute;left:60px;top:40px;font:400 84px Anton, sans-serif;color:#fff;letter-spacing:4px", "YOUR ORDER");
    K.appIcon(card, 96, "position:absolute;right:56px;top:36px");
    const row = (label, k, t, isNew) => {
      const r = K.div("", card, `position:absolute;left:56px;right:56px;top:${180 + k * 104}px;height:88px;display:flex;align-items:center;gap:26px;` +
        `border-bottom:2px solid rgba(255,255,255,.12);font:400 72px Anton, sans-serif;letter-spacing:3px;color:#fff;opacity:${isNew ? 0 : 1}`,
        `<span style="color:${acc};text-shadow:${GLOW}">+</span>` + K.esc(label));
      if (!isNew) return;
      tl.fromTo(r, { opacity: 0, x: 140 }, { opacity: 1, x: 0, duration: 0.3, ease: "power3.out" }, t - 0.06);
      const ry = 90 + 180 + k * 104 + 44;
      tl.to(zw, { scale: 1.22, y: (540 - ry) * 0.22, transformOrigin: `960px ${ry}px`, duration: 0.3, ease: "power3.out" }, t - 0.08);
      tl.to(zw, { scale: 1, y: 0, duration: 0.5, ease: "power2.inOut" }, t + 0.6);
    };
    itemsShown.forEach(([lab], k) => row(lab, k, t0, false));
    const ws = (I.words || []).filter((x) => x.s >= ln.s - 0.05 && x.s < (ln.e || ln.s + 3) + 0.05);
    ws.forEach((x, j) => {
      const lw = x.w.toLowerCase().replace(/[^a-z]/g, "");
      if (!ITEM.test(lw) || itemsShown.length >= 4) return;
      // "big mac combo meal": the item is the word with the words he says before it (up to 2, no filler), one row
      const prev = itemsShown[itemsShown.length - 1];
      if (prev && x.s - prev[1] < 0.9) return;
      const lead = [];
      for (let q = j - 1; q >= 0 && lead.length < 2; q--) {
        const pw = ws[q].w.replace(/[^A-Za-z']/g, "");
        if (!pw || STOPW.test(pw) || /[.,!?]$/.test(ws[q].w)) break;
        lead.unshift(pw);
      }
      const label = (lead.concat([x.w.replace(/[^A-Za-z]/g, "")])).join(" ").toUpperCase();
      itemsShown.push([label, x.s]);
      row(label, itemsShown.length - 1, x.s, true);
    });
    const boom = ws.find((x) => /^(boom|bam|bang|kaboom)\b/i.test(x.w));
    if (boom) {
      tl.fromTo(zw, { scale: 1.28 }, { scale: 1, duration: 0.45, ease: "power3.out", immediateRender: false }, boom.s - 0.03);
      tl.fromTo(card, { boxShadow: "0 0 140px #ff3b3b, 0 30px 90px rgba(0,0,0,.6)" }, { boxShadow: "0 30px 90px rgba(0,0,0,.6)", duration: 0.7, ease: "power2.out", immediateRender: false }, boom.s - 0.03);
    }
    enter(tl, card, t0 + 0.02, first, { y: 60, scale: 0.94 });
  };
  // 7. his real phone screen in a phone body, centred, a slow rise + push (his own app footage; P21 kept it full frame and
  //    the portrait clip came out as a blurry crop)
  K.SCENES.phonefull = (tl, box, ln, t0, t1, ctx) => {
    const sl = (ctx && ctx.slots || [])[0];
    const glow = K.div("", box, `position:absolute;left:560px;top:0;width:800px;height:1080px;background:radial-gradient(circle at 50% 50%,${acc}44,transparent 65%)`);
    const ph = K.phone(box, { x: 700, y: 50, w: 520, h: 1060 });
    if (sl) K.into(tl, sl, ph.screen);
    tl.fromTo(ph.frame, { y: 700, rotation: 6, opacity: 0 }, { y: 0, rotation: 2, opacity: 1, duration: 0.45, ease: "power3.out" }, t0);
    tl.to(ph.frame, { rotation: -1, y: -20, scale: 1.05, duration: Math.max(0.3, t1 - t0 - 0.45), ease: "sine.inOut" }, t0 + 0.45);
    tl.fromTo(glow, { opacity: 0 }, { opacity: 1, duration: 0.5 }, t0);
  };
  const GFX = [[/surpris|shock|crazy|can'?t believe|insane|out of nowhere|goes (all the way )?up|\$\d/i, "totalup"], [/fees?\b|shipping|tax(es)?|adding it|name it|check ?out|handling/i, "checkout"],
               [/\border\b|combo|meals?\b|fries|burgers?|pizza|nuggets|boom/i, "order"],
               [/today'?s video|show you|going over|walk you/i, "title"], [/promo|codes?\b|coupons?/i, "tickets"], [/\bsav(e|ing)\b|money|cheaper|discount/i, "save"]];
  K.scenesFor = (ln, i) => {
    if ((ln._slots || []).length) return [ln._slots[0].kind === "phone" ? "phonefull" : "facecam"];   // his real clip of this line
    const g = GFX.find(([re]) => re.test(ln.text));
    return [g ? g[1] : "word"];
  };
  // light leaks / flashes (build_intro.fx_plan) only where the PICTURE changes: one inside the checkout run at 9.2 s was a
  // "transition to nothing" (2026-10-24); the hand-over on "let's go" stays
  I.fx = [];   // no light leaks / flashes in P21 ("the random flashes were too much", 2026-10-24)
  I.fx = (I.fx || []).filter((f) => {
    const i = I.lines.findIndex((l) => Math.abs(l.s - f.t) < 0.3);
    if (i < 0) return false;
    return I.lines[i].role === "go" || (i > 0 && sceneOf(i) !== sceneOf(i - 1));
  });
  const stage = K.root(), turn = I.beats.turn, last = I.words[I.words.length - 1].e, app = K.app();
  const frame = document.getElementById("frame"), bg = document.getElementById("bg");
  const lines = I.lines.filter((l) => l.role !== "go");

  // NEXT LEVEL (2026-10-24, he: "it's almost there ... our Minecraft videos ... they just have it"). Measured: the Minecraft
  // intros live in ONE world that is always moving (motion 2-8 every second) and have an ARC (a big moment on the turn, a
  // title slam at the end); P21 sat at one level (checkout 0.6-1.6 motion, no big moment). So: a moving world behind
  // everything, a turn moment, a title payoff. Steady music, no shake, nothing corny (his phone + effects rules).
  const floor = K.div("", bg, "position:absolute;left:-600px;right:-600px;top:560px;height:900px;transform:perspective(700px) rotateX(64deg);transform-origin:50% 0;" +
    `background-image:linear-gradient(${app.accent}55 2px, transparent 2px),linear-gradient(90deg, ${app.accent}40 2px, transparent 2px);background-size:120px 120px;` +
    "-webkit-mask-image:linear-gradient(transparent, #000 35%, #000);opacity:.55");
  tl.fromTo(floor, { backgroundPosition: "0px 0px" }, { backgroundPosition: `0px ${Math.round(I.dur * 90)}px`, duration: I.dur, ease: "none" }, 0);
  const pr = K.rng(77);
  for (let k = 0; k < 26; k++) {
    const sz = 4 + pr() * 9, x = pr() * 1920, y0 = 200 + pr() * 1000;
    const dot = K.div("", bg, `position:absolute;left:${x}px;top:${y0}px;width:${sz}px;height:${sz}px;border-radius:50%;` +
      `background:${k % 3 ? app.accent : "#fff"};box-shadow:0 0 ${sz * 3}px ${k % 3 ? app.accent : "#fff"};opacity:${0.25 + pr() * 0.4}`);
    tl.fromTo(dot, { y: 0, x: 0 }, { y: -(260 + pr() * 520), x: (pr() - 0.5) * 160, duration: I.dur, ease: "none" }, 0);
  }
  // the background never sits still: two soft accent blobs drift across it the whole intro (dhgate coupons 2026-10-24)
  [[200, 120, 900], [1300, 600, 1100]].forEach(([x, y, r], i) => {
    const b = K.div("", bg, `position:absolute;left:${x}px;top:${y}px;width:${r}px;height:${r}px;border-radius:50%;background:radial-gradient(circle,${app.accent}33,transparent 70%)`);
    tl.fromTo(b, { x: 0, y: 0 }, { x: i ? -500 : 600, y: i ? -300 : 250, duration: I.dur, ease: "sine.inOut" }, 0);
  });
  const d = K.director(tl, { cut: "push" });   // a smooth push, not the orange swipe ("non-flashy", 2026-10-24)
  K.xp(tl, stage, { top: 960, label: "WATCH TO THE END" });
  const T = document.getElementById("title"), t1 = T.querySelector(".t1");
  K.appIcon(document.getElementById("ticon"), 200, "box-shadow:0 20px 50px rgba(0,0,0,.35)");
  t1.textContent = (I.title || app.name).toUpperCase();
  K.fit(t1, 1400, 190, 90);
  // the payoff lands ON "let's go" (it sat after the last word, behind the closing wipe, and never showed: 2026-10-24)
  const t0 = I.beats.go != null ? I.beats.go - 0.05 : Math.max(last + 0.05, last - 0.1);
  K.punch(tl, { until: t0 - 0.05, hero: null });   // his words, glowing; clears before the title card
  // TURN IT UP (2026-10-24): every glowing key word lands with a quick zoom pulse of the whole frame (zoom, never shake);
  // not inside the turn moment, not twice within 0.9 s
  let lastPulse = -9;
  (I.words || []).filter((w) => w.k && w.s < t0 - 0.3 && (turn == null || Math.abs(w.s - turn) > 0.8)).forEach((w) => {
    if (w.s - lastPulse < 0.9) return;
    lastPulse = w.s;
    tl.fromTo(stage, { scale: 1.045 }, { scale: 1, duration: 0.3, ease: "power3.out", immediateRender: false }, w.s);
  });
  tl.to(frame, { opacity: 0, duration: 0.15 }, t0 - 0.1);
  tl.set(T, { opacity: 1 }, t0);
  tl.fromTo(T, { clipPath: "circle(0% at 50% 50%)" }, { clipPath: "circle(80% at 50% 50%)", duration: 0.45, ease: "power3.out" }, t0);
  tl.fromTo(T.querySelector(".pill"), { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.3, ease: "back.out(2)" }, t0 + 0.3);
  // the TURN ("In today's video ..."): white flash, rings burst out from the centre, a quick zoom punch (no shake)
  if (turn != null) {
    // no white flash ("the random flashes were too much", his friend, 2026-10-24): the rings + zoom carry the turn
    [0, 1, 2].forEach((k) => {
      const r = K.div("", K.over(), `position:absolute;left:660px;top:100px;width:600px;height:600px;border-radius:50%;border:${10 - k * 3}px solid ${app.accent};` +
        `box-shadow:0 0 40px ${app.accent};opacity:0;z-index:71`);
      tl.fromTo(r, { scale: 0.3, opacity: 0.9 }, { scale: 2.6 + k * 0.5, opacity: 0, duration: 0.7 + k * 0.1, ease: "power2.out", immediateRender: false }, turn + 0.02 + k * 0.07);
    });
    tl.fromTo(stage, { scale: 1.07 }, { scale: 1, duration: 0.4, ease: "power3.out" }, turn);
  }
  // the PAYOFF: light rays turn behind the title, the icon and title slam in (on "let's go")
  const rays = K.div("", T, "position:absolute;left:-460px;top:-1000px;width:2840px;height:2840px;z-index:-1;" +
    `background:repeating-conic-gradient(from 0deg at 50% 50%, ${app.accent}26 0 7deg, transparent 7deg 18deg);opacity:0`);
  tl.fromTo(rays, { opacity: 0, rotation: 0 }, { opacity: 1, rotation: 24, duration: Math.max(0.6, I.dur - t0), ease: "none" }, t0);
  tl.fromTo(document.getElementById("ticon"), { scale: 2.4, rotation: -14 }, { scale: 1, rotation: 0, duration: 0.3, ease: "power4.out" }, t0 + 0.05);
  tl.fromTo(t1, { scale: 1.8, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.25, ease: "power4.out" }, t0 + 0.15);
  // no orange closing wipe: join.py slides into the talking part (2026-10-24, non-flashy)
};

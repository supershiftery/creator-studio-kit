/* Phone / promo-code scene bank: one literal, designed-UI scene per VO line (the approved Uber Eats kit + the Shein
   "screens" intro). Rules baked in: no blurred screen recordings (designed UI only), money slams in red with the register
   (placed by the builder), the app's real icon and brand colour everywhere. A phone template is a THEME over these. */
(function () {
  const K = window.K, I = window.INTRO;
  const S = {};
  const app = () => K.app();
  const css = (n, d) => getComputedStyle(document.documentElement).getPropertyValue(n).trim() || d;
  const ink = () => css("--p-ink", "#ffffff"), card = () => css("--p-card", "#ffffff");
  // the big word is the line's REAL key (money, brand, concept like FEES / SHIPPING); a weak longest-word key is never shown
  // (dhgate coupons 2026-10-24: "why is the word STARTING highlighted ... GUYS ... this makes no sense"): no key = no big word
  const strong = (ln) => (ln.key && !ln.key_weak ? ln.key : "");
  const word = (ln) => (ln.role === "turn" && /today/i.test(ln.text) ? "IN TODAY'S VIDEO" : (ln.money || strong(ln))).toUpperCase();
  const big = (parent, txt, style) => {
    const e = K.div("p-big", parent, "position:absolute;left:0;right:0;text-align:center;font:400 170px Anton, sans-serif;color:" + ink() + ";text-transform:uppercase;white-space:nowrap;line-height:.95;text-shadow:0 10px 30px rgba(0,0,0,.35);" + (style || ""), K.esc(txt));
    K.fit(e, 1700, 170, 70);
    return e;
  };
  // what the cart / receipt hold matches the video's subject: the app's own items (apps.json intro_items), else its kind,
  // else the kind the builder guessed from the VO (a DHgate intro showed a pizza order, 2026-10-22)
  const kit = () => {
    const a = app(), kind = a.kind || I.kind || "shop";
    const k = kind === "shop"
      ? { items: [["Satin Midi Dress", 24.99], ["Wide-Leg Jeans", 21.49], ["Chunky Sneakers", 32.0]], fees: [["Shipping", 7.99], ["Taxes", 6.27]] }
      : { items: [["Large Pepperoni Pizza", 14.99], ["Garlic Knots", 5.49], ["Wings (10 pc)", 12.99]], fees: [["Service fee", 3.2], ["Delivery fee", 3.99], ["Taxes & fees", 3.51]] };
    return { items: a.items || k.items, fees: a.fees || k.fees };
  };

  // 1. a phone-sized cart: item cards drop in, the badge counts ("order", "food", "cart", "delivery", "convenient")
  S.cart = (tl, box, ln, t0, t1) => {
    const ph = K.phone(box, { x: 690, y: 60, w: 540, h: 1100, wall: "#f4f4f6" });
    const hd = K.div("", ph.screen, "position:absolute;left:0;right:0;top:70px;display:flex;align-items:center;gap:18px;padding:0 30px;font:800 40px Inter, sans-serif;color:#111");
    K.appIcon(hd, 70); K.div("", hd, "", "Your cart");
    tl.fromTo(ph.frame, { y: 900, rotation: 6 }, { y: 0, rotation: -2, duration: 0.45, ease: "power3.out" }, t0);
    kit().items.forEach((it, i) => {
      const c = K.div("", ph.screen, `position:absolute;left:24px;right:24px;top:${190 + i * 150}px;height:130px;background:#fff;border-radius:22px;box-shadow:0 8px 20px rgba(0,0,0,.08);display:flex;align-items:center;gap:20px;padding:0 22px;opacity:0`,
        `<div style="width:84px;height:84px;border-radius:16px;background:${app().accent};opacity:.85"></div><div style="flex:1"><div style="font:700 30px Inter;color:#111">${K.esc(it[0])}</div><div style="font:600 26px Inter;color:#888">${K.money(it[1])}</div></div>`);
      tl.fromTo(c, { opacity: 0, x: 300 }, { opacity: 1, x: 0, duration: 0.25, ease: "back.out(1.6)" }, t0 + 0.3 + i * Math.min(0.35, (t1 - t0 - 0.6) / 3));
    });
    tl.to(ph.frame, { rotation: 2, y: -20, duration: t1 - t0 - 0.5, ease: "sine.inOut" }, t0 + 0.5);
    const w = big(box, word(ln), "top:880px");
    tl.fromTo(w, { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.25 }, Math.max(t0 + 0.2, ln.keyT - 0.05));
  };
  // 2. a receipt printing line by line, adding up to a red total that slams ("paying", "fees", "more than", "expensive")
  S.receipt = (tl, box, ln, t0, t1) => {
    const rc = K.div("", box, "position:absolute;left:560px;top:40px;width:800px;height:0;overflow:hidden;background:#fbfbf7;box-shadow:0 30px 70px rgba(0,0,0,.45);padding:0 50px;font:400 40px SpaceMono, monospace;color:#1a1a1a");
    K.div("", rc, "text-align:center;padding:50px 0 24px;border-bottom:4px dashed #aaa;font-size:38px;letter-spacing:4px", K.esc(app().name.toUpperCase()) + " ORDER");
    const k = kit(), lines = k.items.slice(0, 2).concat(k.fees);
    let tot = 0, h = 170;
    tl.to(rc, { height: h, duration: 0.25, ease: "none" }, t0);
    const step = Math.min(0.32, (t1 - t0 - 1.0) / lines.length);
    lines.forEach((l, i) => {
      tot += l[1];
      const r = K.div("", rc, "display:flex;justify-content:space-between;padding:14px 0;opacity:0;color:" + (i >= 2 ? "#c62828" : "#1a1a1a"), `<span>${K.esc(l[0])}</span><span>${K.money(l[1])}</span>`);
      h += 70;
      tl.to(rc, { height: h, duration: 0.2, ease: "none" }, t0 + 0.25 + i * step);
      tl.set(r, { opacity: 1 }, t0 + 0.3 + i * step);
    });
    const tt = K.div("", rc, "display:flex;justify-content:space-between;border-top:4px dashed #aaa;padding:24px 0;font-size:66px;font-weight:700;opacity:0", `<span>TOTAL</span><b style="color:#d62828">${K.money(tot)}</b>`);
    const ts = Math.max(t0 + 0.4 + lines.length * step, ln.keyT);
    tl.to(rc, { height: h + 150, duration: 0.2 }, ts - 0.1);
    tl.set(tt, { opacity: 1 }, ts);
    tl.fromTo(tt, { scale: 1.6 }, { scale: 1, duration: 0.25, ease: "power4.out" }, ts);
    K.shake(tl, rc, ts + 0.05, 14, 0.3);
    const w = big(box, ln.money || "$" + Math.round(tot), "top:780px;color:#ff4d4d;font-size:220px");
    tl.fromTo(w, { opacity: 0, scale: 2 }, { opacity: 1, scale: 1, duration: 0.22, ease: "power4.out" }, ts + 0.1);
  };
  // 3. browser windows fanned in 3D + a search bar typing ("looking", "search", "find", "best codes")
  S.search = (tl, box, ln, t0, t1) => {
    const wall = K.div("", box, "position:absolute;inset:0;perspective:1600px");
    [[-1, 0], [0, 1], [1, 0]].forEach(([s, front], i) => {
      const w = K.div("", wall, `position:absolute;left:${460 + s * 520}px;top:${300 - front * 30}px;width:1000px;height:560px;border-radius:22px;overflow:hidden;background:#fff;box-shadow:0 40px 90px rgba(0,0,0,.6)`,
        `<div style="height:46px;background:#1d1f24;display:flex;align-items:center;gap:10px;padding:0 18px"><i style="width:14px;height:14px;border-radius:50%;background:#ff5f57"></i><i style="width:14px;height:14px;border-radius:50%;background:#febc2e"></i><i style="width:14px;height:14px;border-radius:50%;background:#28c840"></i><b style="margin-left:14px;flex:1;height:26px;border-radius:13px;background:#2c2f36;color:#9aa0aa;font:600 15px Inter;display:flex;align-items:center;padding-left:16px">${["coupons", app().name.toLowerCase().replace(/\s/g, ""), "deals"][i]}.com</b></div>` +
        `<div style="padding:30px 40px;display:flex;flex-direction:column;gap:18px"><div style="font:800 40px Inter;color:#1a0dab">${K.esc(app().name)} promo codes</div>` + "<div style='height:14px;border-radius:7px;background:#e3e6ec'></div>".repeat(6) + "</div>");
      gsap.set(w, { rotationY: s * -24, transformOrigin: s < 0 ? "100% 50%" : "0% 50%" });
      tl.fromTo(w, { x: s * 600, y: front ? 400 : 0, opacity: 0 }, { x: 0, y: 0, opacity: 1, duration: 0.5, ease: "power3.out" }, t0 + i * 0.08);
      tl.to(w, { y: -50, duration: t1 - t0 - 0.5, ease: "sine.inOut" }, t0 + 0.5);
    });
    const sb = K.div("", box, "position:absolute;left:460px;top:80px;width:1000px;height:110px;border-radius:55px;background:#fff;box-shadow:0 24px 60px rgba(0,0,0,.5);display:flex;align-items:center;gap:24px;padding:0 40px;font:600 52px Inter, sans-serif;color:#222", K.glyphHTML("search", 54, "#222") + '<span class="q"></span>');
    tl.fromTo(sb, { y: -80, opacity: 0 }, { y: 0, opacity: 1, duration: 0.3, ease: "back.out(2)" }, t0 + 0.1);
    K.type(tl, sb.querySelector(".q"), (app().name + " promo codes").toLowerCase(), t0 + 0.35, Math.min(1.3, t1 - t0 - 0.6), "|");
  };
  // 4. gatekept: code tickets blacked out, a padlock slams, GATEKEPT stamp ("gatekeep", "creators", "won't share", "hiding")
  S.gate = (tl, box, ln, t0, t1) => {
    const codes = ["SAVE25", "FREEDEL", "NEW50", "WELCOME"];
    codes.forEach((c, i) => {
      const t = K.div("", box, `position:absolute;left:${300 + (i % 2) * 720}px;top:${250 + Math.floor(i / 2) * 260}px;width:620px;height:190px;border:6px dashed #fff;border-radius:22px;display:flex;align-items:center;justify-content:center;font:700 70px SpaceMono, monospace;color:#fff;background:rgba(255,255,255,.08)`,
        `${c}<s style="position:absolute;left:30px;top:50px;height:90px;width:0;background:#000;border-radius:8px"></s>`);
      tl.fromTo(t, { y: 200, opacity: 0, rotation: i % 2 ? 8 : -8 }, { y: 0, opacity: 1, rotation: i % 2 ? 3 : -3, duration: 0.35, ease: "back.out(1.8)" }, t0 + 0.05 + i * 0.12);
      tl.to(t.querySelector("s"), { width: 560, duration: 0.25, ease: "power3.out" }, t0 + 0.6 + i * 0.1);
    });
    const lk = K.div("", box, "position:absolute;left:830px;top:250px;opacity:0;filter:drop-shadow(0 20px 30px rgba(0,0,0,.5))", K.glyphHTML("lock", 260, "#ffd34d"));
    const tc = Math.max(t0 + 1.0, ln.keyT);
    tl.fromTo(lk, { y: -700, opacity: 0 }, { y: 0, opacity: 1, duration: 0.4, ease: "bounce.out" }, tc - 0.4);
    const st = K.div("", box, "position:absolute;left:560px;top:760px;font:400 140px Anton, sans-serif;color:#ff3b3b;border:12px solid #ff3b3b;padding:0 40px;border-radius:16px;opacity:0", K.esc(ln.key ? ln.key.toUpperCase() : "GATEKEPT"));
    tl.fromTo(st, { opacity: 0, scale: 2.6, rotation: -14 }, { opacity: 1, scale: 1, rotation: -6, duration: 0.2, ease: "power4.out" }, tc);
    K.shake(tl, box, tc + 0.03, 16, 0.3);
  };
  // 5. a TOP SECRET folder opens, method cards slide out ("secret", "methods", "hidden", "ways")
  S.secret = (tl, box, ln, t0, t1) => {
    const f = K.div("", box, "position:absolute;left:560px;top:260px;width:800px;height:560px");
    const back = K.div("", f, "position:absolute;inset:0;background:#c99a4c;border-radius:10px 30px 10px 10px;box-shadow:0 30px 70px rgba(0,0,0,.5)");
    const ms = app().methods.slice(0, 3).map((m, i) => K.div("", f, `position:absolute;left:60px;right:60px;top:${60 + i * 20}px;height:200px;background:#fff;border-radius:14px;box-shadow:0 10px 24px rgba(0,0,0,.25);display:flex;align-items:center;gap:24px;padding:0 34px;font:800 56px Poppins, sans-serif;color:#111;opacity:0`,
      `<span style="width:64px;height:64px;border-radius:50%;background:${app().accent};color:#fff;display:flex;align-items:center;justify-content:center;font:800 36px Inter">${i + 1}</span>${K.esc(m)}`));
    const front = K.div("", f, "position:absolute;inset:0;top:60px;background:#dcae5c;border-radius:10px;display:flex;align-items:center;justify-content:center;transform-origin:50% 100%", '<div style="font:400 110px Anton, sans-serif;color:#b3261e;border:10px solid #b3261e;padding:0 34px;transform:rotate(-8deg)">TOP SECRET</div>');
    tl.fromTo(f, { y: 900, rotation: -6 }, { y: 0, rotation: 0, duration: 0.45, ease: "power3.out" }, t0);
    const to = Math.max(t0 + 0.6, ln.keyT);
    tl.to(front, { rotationX: 70, y: 260, opacity: 0.4, duration: 0.35, ease: "power2.in" }, to);
    ms.forEach((m, i) => tl.fromTo(m, { opacity: 0, y: 0 }, { opacity: 1, y: -300 + i * 230, duration: 0.35, ease: "back.out(1.5)" }, to + 0.2 + i * 0.18));
    tl.to(f, { scale: 1.06, duration: t1 - to, ease: "none" }, to);
  };
  // 6. a price tag: the old price struck, $0.00 slams, 100% FREE stamp ("free", "100%", "save", "nothing")
  S.free = (tl, box, ln, t0, t1) => {
    const old = K.div("", box, "position:absolute;left:0;right:0;top:220px;text-align:center;font:400 220px Anton, sans-serif;color:" + ink() + ";opacity:.9", "$34.18");
    const strike = K.div("", box, "position:absolute;left:640px;top:350px;height:22px;width:0;background:#ff3b3b;border-radius:11px;transform:rotate(-8deg)");
    const nw = K.div("", box, "position:absolute;left:0;right:0;top:470px;text-align:center;font:400 300px Anton, sans-serif;color:#3dff7a;opacity:0;text-shadow:0 14px 40px rgba(0,0,0,.35)", "$0.00");
    const st = K.div("", box, "position:absolute;left:1220px;top:160px;font:400 110px Anton, sans-serif;color:#fff;background:#ff3b3b;padding:6px 34px;border-radius:14px;opacity:0", "100% FREE");
    tl.fromTo(old, { opacity: 0, scale: 0.7 }, { opacity: 0.9, scale: 1, duration: 0.25 }, t0);
    const ts = Math.max(t0 + 0.35, ln.keyT - 0.25);
    tl.to(strike, { width: 640, duration: 0.25, ease: "power3.out" }, ts);
    tl.to(old, { opacity: 0.35, scale: 0.8, duration: 0.25 }, ts + 0.1);
    tl.fromTo(nw, { opacity: 0, scale: 2.4 }, { opacity: 1, scale: 1, duration: 0.25, ease: "power4.out" }, ts + 0.25);
    K.shake(tl, box, ts + 0.3, 14, 0.3);
    tl.fromTo(st, { opacity: 0, scale: 2.4, rotation: -16 }, { opacity: 1, scale: 1, rotation: 8, duration: 0.2, ease: "power4.out" }, ts + 0.55);
    tl.to(nw, { scale: 1.06, duration: Math.max(0.3, t1 - ts - 0.6), ease: "sine.inOut" }, ts + 0.6);
  };
  // 7. a group chat: friends reacting ("friends", "everyone", "people", "family")
  S.friends = (tl, box, ln, t0, t1) => {
    const ph = K.phone(box, { x: 690, y: 40, w: 540, h: 1100, wall: "#fff" });
    tl.fromTo(ph.frame, { y: 900 }, { y: 0, duration: 0.4, ease: "power3.out" }, t0);
    const msgs = [["them", "bro how is your order $0??"], ["me", "secret method"], ["them", "SEND IT"], ["them", "wait it actually worked"], ["me", "told you"]];
    const n = Math.min(msgs.length, Math.max(2, Math.floor((t1 - t0 - 0.4) / 0.35)));
    msgs.slice(0, n).forEach((m, i) => {
      const b = K.div("", ph.screen, `position:absolute;${m[0] === "me" ? "right:24px;background:#0a84ff;color:#fff" : "left:24px;background:#e5e5ea;color:#111"};top:${140 + i * 120}px;max-width:400px;padding:18px 26px;border-radius:32px;font:500 32px Inter, sans-serif;opacity:0`, K.esc(m[1]));
      tl.fromTo(b, { opacity: 0, scale: 0.5, y: 30 }, { opacity: 1, scale: 1, y: 0, duration: 0.22, ease: "back.out(2)" }, t0 + 0.35 + i * 0.35);
    });
    ["$0", "FREE", "100%"].forEach((e, i) => {
      const x = K.div("", box, `position:absolute;left:${[260, 1380, 1460][i]}px;top:${[300, 220, 640][i]}px;font:400 120px Anton, sans-serif;color:#fff;background:${app().accent};padding:6px 26px;border-radius:18px;opacity:0`, e);
      tl.fromTo(x, { opacity: 0, scale: 0 }, { opacity: 1, scale: 1, duration: 0.3, ease: "back.out(3)" }, t0 + 0.5 + i * 0.3);
      tl.to(x, { y: -40, rotation: i % 2 ? 10 : -10, duration: 0.6, yoyo: true, repeat: 1, ease: "sine.inOut" }, t0 + 0.8 + i * 0.3);
    });
  };
  // 8. order after order at $0.00 ("over and over", "again", "every time")
  S.again = (tl, box, ln, t0, t1) => {
    const n = 6, step = Math.min(0.28, (t1 - t0 - 0.4) / n);
    for (let i = 0; i < n; i++) {
      const c = K.div("", box, `position:absolute;left:560px;top:280px;width:800px;height:200px;background:${card()};border-radius:28px;box-shadow:0 20px 50px rgba(0,0,0,.35);display:flex;align-items:center;gap:30px;padding:0 40px;opacity:0`);
      K.appIcon(c, 110);
      K.div("", c, "flex:1;font:800 48px Inter, sans-serif;color:#111", "Order #" + (1041 + i * 7) + "<div style='font:600 30px Inter;color:#0a9a44'>Delivered · promo applied</div>");
      K.div("", c, "font:800 64px Inter, sans-serif;color:#0a9a44", "$0.00");
      const t = t0 + 0.1 + i * step;
      tl.set(c, { opacity: 1 }, t);
      tl.fromTo(c, { y: 900, rotation: 6 }, { y: i * -26, rotation: (i % 2 ? 1 : -1) * 2, scale: 1 - (n - 1 - i) * 0.0, duration: 0.3, ease: "power3.out" }, t);
    }
    const w = big(box, ln.key ? ln.key : "AGAIN & AGAIN", "top:760px");
    tl.fromTo(w, { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.25 }, t0 + 0.3);
  };
  // 9. lock-screen notifications pouring in (fallback for problem lines about the order / delivery)
  S.notify = (tl, box, ln, t0, t1) => {
    const ph = K.phone(box, { x: 120, y: 60, w: 600, h: 1200 });
    tl.fromTo(ph.frame, { x: -800, rotation: -8 }, { x: 0, rotation: -3, duration: 0.45, ease: "power3.out" }, t0);
    // the order lines come from the subject's own kit (a DHgate intro said "Delivery fee / Service fee added", 2026-10-22)
    const k = kit(), tot = k.items.concat(k.fees).reduce((a, x) => a + x[1], 0);
    const msgs = ln.s < I.beats.turn ? ["Your order total: " + K.money(tot)].concat(k.fees.slice(0, 3).map((f, i) => f[0] + (i === 1 ? " added" : ": " + K.money(f[1]))))
      : ["Promo code applied ✓", "Your order is $0.00", "You saved " + K.money(tot)];
    msgs.forEach((m, i) => {
      const n = K.notif(ph.screen, { y: 140 + i * 175, html: K.esc(m), bg: ln.s < I.beats.turn ? "rgba(245,245,248,.95)" : "rgba(236,255,242,.95)" });
      tl.fromTo(n, { opacity: 0, y: -120, scale: 0.9 }, { opacity: 1, y: 0, scale: 1, duration: 0.25, ease: "back.out(1.6)" }, t0 + 0.25 + i * Math.min(0.4, (t1 - t0 - 0.5) / msgs.length));
    });
    const w = big(box, word(ln), "left:760px;right:60px;top:430px;text-align:left;font-size:180px");
    K.fit(w, 1100, 180, 70);
    tl.fromTo(w, { opacity: 0, x: 120 }, { opacity: 1, x: 0, duration: 0.25, ease: "power3.out" }, Math.max(t0 + 0.2, ln.keyT - 0.05));
  };
  // 10. a big question / "what if" beat: a giant ? and the phone shrugging
  S.question = (tl, box, ln, t0, t1) => {
    const q = K.div("", box, "position:absolute;left:0;right:0;top:120px;text-align:center;font:400 520px Anton, sans-serif;color:" + ink() + ";line-height:1;opacity:0", "?");
    tl.fromTo(q, { opacity: 0, scale: 0.3, rotation: -25 }, { opacity: 1, scale: 1, rotation: 0, duration: 0.35, ease: "back.out(2)" }, t0 + 0.05);
    tl.to(q, { rotation: 10, duration: 0.45, yoyo: true, repeat: Math.max(1, Math.floor((t1 - t0) / 0.45) - 1), ease: "sine.inOut" }, t0 + 0.4);
    const w = big(box, word(ln), "top:800px");
    tl.fromTo(w, { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.25 }, Math.max(t0 + 0.2, ln.keyT - 0.05));
  };
  // 11. fallback: giant word + emoji sticker on a moving stripe field
  S.word = (tl, box, ln, t0, t1) => {
    const st = K.div("", box, "position:absolute;left:-400px;top:-400px;width:2720px;height:1880px;background:repeating-linear-gradient(70deg,rgba(255,255,255,.07) 0 40px,transparent 40px 120px)");
    tl.fromTo(st, { x: 0 }, { x: -240, duration: t1 - t0, ease: "none" }, t0);
    if (ln.icon) {
      const e = K.div("", box, "position:absolute;left:0;right:0;top:170px;text-align:center;font:260px Emoji;line-height:1;opacity:0", ln.icon);
      tl.fromTo(e, { opacity: 0, scale: 0.2, rotation: -20 }, { opacity: 1, scale: 1, rotation: 0, duration: 0.3, ease: "back.out(2.4)" }, t0 + 0.05);
      tl.to(e, { y: -20, duration: 0.5, yoyo: true, repeat: Math.max(1, Math.floor((t1 - t0) / 0.5)), ease: "sine.inOut" }, t0 + 0.35);
    }
    const w = big(box, word(ln), "top:" + (ln.icon ? 560 : 400) + "px;font-size:230px");
    tl.fromTo(w, { opacity: 0, scale: 1.8 }, { opacity: 1, scale: 1, duration: 0.22, ease: "power4.out" }, t0 + 0.08);
    tl.to(w, { scale: 1.07, duration: t1 - t0, ease: "none" }, t0 + 0.3);
    // the fallback must still move on light themes too (the white stripes vanish there): the word sways and drifts up
    tl.to(w, { y: -40, rotation: -2, duration: Math.max(0.3, (t1 - t0) / 2), ease: "sine.inOut", yoyo: true, repeat: 1 }, t0 + 0.3);
  };
  // 12. the user's own clip (face cam / website page) in a moving window. Three layouts take turns so five clip lines never
  //     look like one repeated shot (dhgate coupons 2026-10-24: the same tilted page card + word five times, "more motion,
  //     different things going on"): A window left + word right, B full-bleed push-in + accent lower third, C window right
  //     swinging in from 3D + word left. No strong key = a bigger window and no word.
  let fcN = 0;
  S.facecam = (tl, box, ln, t0, t1, ctx) => {
    // window.CLIP_FULL (P21): every real clip FULL FRAME with a slow push, like the reselling intro he loves (coupons 2026-10-24:
    // his clips as small tilted cards on an empty light page, "doesn't feel crispy")
    const sl = (ctx.slots || [])[0], v = window.CLIP_FULL ? (fcN++, 1) : fcN++ % 3, wtxt = window.NO_SCENE_TEXT ? "" : word(ln), acc = app().accent;
    const geo = !wtxt && v !== 1 ? { l: 210, t: 130, w: 1500, h: 845 } : v === 0 ? { l: 110, t: 150, w: 1100, h: 620 } : { l: 760, t: 170, w: 1060, h: 600 };
    const win = v === 1 ? K.div("", box, "position:absolute;inset:0;overflow:hidden;background:#111")
      : K.div("", box, `position:absolute;left:${geo.l}px;top:${geo.t}px;width:${geo.w}px;height:${geo.h}px;border-radius:36px;overflow:hidden;background:#111;box-shadow:0 0 0 10px #fff,0 40px 90px rgba(0,0,0,.45)`);
    const inn = K.div("", win, "position:absolute;inset:0");
    if (sl) K.into(tl, sl, inn);
    const d = t1 - t0;
    if (v === 1) {
      // full frame: a push-in that drifts across the page, an accent lower third with the key word
      tl.fromTo(inn, { scale: 1.02, x: 40, y: 20 }, { scale: 1.22, x: -70, y: -30, duration: d, ease: "sine.inOut" }, t0);
      tl.fromTo(win, { clipPath: "inset(0 0 0 100%)" }, { clipPath: "inset(0 0 0 0%)", duration: 0.35, ease: "power3.out" }, t0);
      if (wtxt) {
        const bar = K.div("", box, `position:absolute;left:0;top:800px;height:170px;width:0;background:${acc};box-shadow:0 20px 50px rgba(0,0,0,.35)`);
        const tx = K.div("p-big", box, "position:absolute;left:90px;top:806px;font:400 150px Anton, sans-serif;color:#fff;text-transform:uppercase;white-space:nowrap;opacity:0", K.esc(wtxt));
        K.fit(tx, 1600, 150, 70);
        const tw = Math.max(t0 + 0.25, ln.keyT - 0.1);
        tl.to(bar, { width: 1920, duration: 0.3, ease: "power3.out" }, tw);
        tl.fromTo(tx, { opacity: 0, x: -200 }, { opacity: 1, x: 0, duration: 0.3, ease: "power3.out" }, tw + 0.08);
      }
      return;
    }
    const wrap = K.div("", box, "position:absolute;inset:0;perspective:1800px");
    wrap.appendChild(win);
    if (v === 0) {
      tl.fromTo(win, { x: -1300, rotationY: 28, rotation: -6 }, { x: 0, rotationY: 6, rotation: -2, duration: 0.45, ease: "power3.out" }, t0);
      tl.to(win, { rotationY: -4, y: -20, duration: Math.max(0.3, d - 0.45), ease: "sine.inOut" }, t0 + 0.45);
    } else {
      tl.fromTo(win, { x: 1300, rotationY: -40, rotation: 6 }, { x: 0, rotationY: -8, rotation: 2, duration: 0.45, ease: "power3.out" }, t0);
      tl.to(win, { rotationY: 4, y: 24, duration: Math.max(0.3, d - 0.45), ease: "sine.inOut" }, t0 + 0.45);
    }
    // the page inside keeps moving too: a slow pan + push
    tl.fromTo(inn, { scale: 1.18, x: v === 0 ? 50 : -50 }, { scale: 1.04, x: v === 0 ? -50 : 50, duration: d, ease: "none" }, t0);
    if (!wtxt) return;
    const w = K.div("p-big", box, `position:absolute;${v === 0 ? "left:1260px;right:60px" : "left:80px;width:640px"};top:320px;font:400 190px Anton, sans-serif;color:` + ink() + ";text-transform:uppercase;line-height:.92;text-shadow:0 10px 30px rgba(0,0,0,.25)", K.esc(wtxt));
    K.fit(w, 620, 190, 70); w.style.whiteSpace = "normal";
    const ul = K.div("", box, `position:absolute;${v === 0 ? "left:1260px" : "left:80px"};top:640px;height:16px;width:0;border-radius:8px;background:${acc}`);
    const tw = Math.max(t0 + 0.15, ln.keyT - 0.05);
    tl.fromTo(w, { opacity: 0, x: v === 0 ? 120 : -120, scale: 1.4 }, { opacity: 1, x: 0, scale: 1, duration: 0.22, ease: "power4.out" }, tw);
    tl.to(ul, { width: 420, duration: 0.3, ease: "power3.out" }, tw + 0.15);
    tl.to(w, { y: -14, duration: Math.max(0.3, t1 - tw - 0.3), ease: "sine.inOut" }, tw + 0.3);
    if (ln.money) K.shake(tl, box, Math.max(t0 + 0.2, ln.keyT), 12, 0.3);
  };
  // 13. the user's real phone screen inside a big tilted phone, key word + app icon beside it (reveal lines with a phone clip)
  S.phoneclip = (tl, box, ln, t0, t1, ctx) => {
    const sl = (ctx.slots || [])[0];
    const ph = K.phone(box, { x: 1080, y: 40, w: 520, h: 1100 });
    if (sl) K.into(tl, sl, ph.screen);
    gsap.set(ph.frame, { rotation: 5 });
    tl.fromTo(ph.frame, { y: 1000, rotation: 14 }, { y: 0, rotation: 5, duration: 0.45, ease: "power3.out" }, t0);
    tl.to(ph.frame, { rotation: 2, y: -24, duration: t1 - t0 - 0.45, ease: "sine.inOut" }, t0 + 0.45);
    const ic = K.div("", box, "position:absolute;left:160px;top:200px");
    K.appIcon(ic, 150, "box-shadow:0 16px 40px rgba(0,0,0,.4)");
    tl.fromTo(ic, { scale: 0, rotation: -30 }, { scale: 1, rotation: 0, duration: 0.3, ease: "back.out(2.4)" }, t0 + 0.15);
    const w = K.div("p-big", box, "position:absolute;left:160px;width:860px;top:420px;font:400 180px Anton, sans-serif;color:" + ink() + ";text-transform:uppercase;line-height:.92;text-shadow:0 10px 30px rgba(0,0,0,.35)", K.esc(word(ln)));
    K.fit(w, 860, 180, 70); w.style.whiteSpace = "normal";
    tl.fromTo(w, { opacity: 0, y: 60 }, { opacity: 1, y: 0, duration: 0.25, ease: "power3.out" }, Math.max(t0 + 0.2, ln.keyT - 0.05));
  };
  // 14. coupons: tickets with notched edges slide in one by one, then the order total counts down in the app colour
  //     ("coupons", "promo codes", "discount", "cheaper", "save", "saving")
  S.coupon = (tl, box, ln, t0, t1) => {
    const vals = ["$4 OFF", "$10 OFF", "$30 OFF", "$40 OFF"], acc = app().accent;
    const n = (t1 - t0) > 2.4 ? 4 : 3, step = Math.max(0.12, Math.min(0.32, (t1 - t0 - 1.2) / n));
    for (let i = 0; i < n; i++) {
      const c = K.div("", box, `position:absolute;left:${150 + (i % 2) * 90}px;top:${185 + i * 185}px;width:760px;height:160px;border-radius:24px;background:${acc};box-shadow:0 18px 40px rgba(0,0,0,.25);display:flex;align-items:center;overflow:hidden;opacity:0`);
      K.div("", c, "width:250px;height:100%;display:flex;align-items:center;justify-content:center;border-right:6px dashed rgba(255,255,255,.7);font:400 64px Anton, sans-serif;color:#fff", K.esc(vals[i]));
      K.div("", c, "flex:1;padding-left:34px;font:800 34px Inter, sans-serif;color:#fff;letter-spacing:2px", "COUPON<br><span style='font-weight:600;font-size:26px;opacity:.85'>tap to apply</span>");
      const t = t0 + 0.12 + i * step;
      tl.fromTo(c, { opacity: 0, x: -900, rotation: -8 }, { opacity: 1, x: 0, rotation: (i % 2 ? 2 : -2), duration: 0.3, ease: "back.out(1.4)" }, t);
      tl.to(c, { y: -18, duration: Math.max(0.3, t1 - t - 0.3), ease: "sine.inOut" }, t + 0.3);
    }
    // the order total ticks down as each coupon lands
    const tot = K.div("", box, `position:absolute;left:1080px;top:330px;width:700px;padding:40px 46px;border-radius:30px;background:${card()};box-shadow:0 24px 60px rgba(0,0,0,.25);opacity:0`);
    K.div("", tot, "font:700 34px Inter, sans-serif;color:#777;letter-spacing:2px", "ORDER TOTAL");
    const num = K.div("", tot, "font:400 150px Anton, sans-serif;color:#d1170d;line-height:1.1", "$86.40");
    tl.fromTo(tot, { opacity: 0, x: 400 }, { opacity: 1, x: 0, duration: 0.3, ease: "power3.out" }, t0 + 0.05);
    const totals = ["$82.40", "$72.40", "$42.40", "$2.40"], tEnd = t0 + 0.42 + (n - 1) * step;
    for (let i = 0; i < n; i++) K.text(tl, num, t0 + 0.42 + i * step, totals[i]);
    tl.to(num, { color: acc, duration: 0.15 }, tEnd);
    tl.fromTo(tot, { scale: 1 }, { scale: 1.08, duration: 0.1, yoyo: true, repeat: 1 }, tEnd);
    tl.to(tot, { y: -24, rotation: -1.5, duration: Math.max(0.3, t1 - tEnd - 0.2), ease: "sine.inOut" }, tEnd + 0.2);
  };
  // 15. fees piling on: the order total ticks UP while fee tags fly in from both sides and land in it
  //     ("fees", "shipping", "taxes", "adding it on", "name it")
  let feeTot = 0;
  S.fees = (tl, box, ln, t0, t1) => {
    const k = kit();
    const st = K.div("", box, "position:absolute;left:-400px;top:-400px;width:2720px;height:1880px;background:repeating-linear-gradient(115deg,rgba(214,40,40,.07) 0 50px,transparent 50px 150px)");
    tl.fromTo(st, { x: 0 }, { x: -300, duration: t1 - t0, ease: "none" }, t0);
    const crd = K.div("", box, `position:absolute;left:560px;top:250px;width:800px;padding:46px 56px;border-radius:34px;background:${card()};box-shadow:0 30px 80px rgba(0,0,0,.3);opacity:0`);
    K.div("", crd, "font:700 36px Inter, sans-serif;color:#777;letter-spacing:3px", K.esc(app().name.toUpperCase()) + " · ORDER TOTAL");
    // a second fee line ("you guys name it") keeps counting from where the last one ended, never back down
    let tot = feeTot || k.items.slice(0, 2).reduce((a, x) => a + x[1], 0);
    const num = K.div("", crd, "font:400 210px Anton, sans-serif;color:#111;line-height:1.05", K.money(tot));
    tl.fromTo(crd, { opacity: 0, y: 300, rotation: -4 }, { opacity: 1, y: 0, rotation: -1, duration: 0.4, ease: "power3.out" }, t0);
    const fees = k.fees.concat([["Service fee", 3.2], ["Handling", 2.49]]).slice(0, 4);
    const step = Math.max(0.22, Math.min(0.45, (t1 - t0 - 0.9) / fees.length));
    fees.forEach((f, i) => {
      const left = i % 2 === 0, y = 180 + i * 190;
      const tag = K.div("", box, `position:absolute;${left ? "left:60px" : "right:60px"};top:${y}px;padding:20px 34px;border-radius:20px;background:#d62828;color:#fff;font:800 50px Inter, sans-serif;box-shadow:0 16px 40px rgba(0,0,0,.3);opacity:0;white-space:nowrap`, "+ " + K.money(f[1]) + " <span style='font-weight:600;font-size:34px;opacity:.9'>" + K.esc(f[0].toUpperCase()) + "</span>");
      const t = t0 + 0.35 + i * step, land = t + Math.min(0.5, step * 0.9);
      tl.fromTo(tag, { opacity: 0, x: left ? -500 : 500, rotation: left ? -10 : 10 }, { opacity: 1, x: 0, rotation: left ? -3 : 3, duration: 0.25, ease: "back.out(1.8)" }, t);
      tl.to(tag, { x: left ? 520 : -520, y: 420 - y, scale: 0.3, opacity: 0, duration: 0.22, ease: "power2.in" }, land);
      tot += f[1];
      K.text(tl, num, land + 0.2, K.money(tot));
      tl.fromTo(crd, { scale: 1 }, { scale: 1.06, duration: 0.08, yoyo: true, repeat: 1 }, land + 0.2);
    });
    feeTot = tot;
    const tEnd = Math.min(t0 + 0.35 + fees.length * step + 0.2, t1 - 0.3);
    tl.to(num, { color: "#d62828", duration: 0.15 }, tEnd);
    K.shake(tl, crd, tEnd, 12, 0.3);
    const wt = word(ln);
    if (wt) {
      const w = big(box, wt, "top:860px;font-size:150px;color:#d62828");
      tl.fromTo(w, { opacity: 0, y: 50 }, { opacity: 1, y: 0, duration: 0.25, ease: "power3.out" }, Math.max(t0 + 0.2, ln.keyT - 0.05));
    }
  };
  // 16. the surprise: the total slams in huge over a spinning red burst, a "?!" sticker and the fees floating round it
  //     ("surprising", "shocking", "crazy", "insane", "can't believe")
  S.shock = (tl, box, ln, t0, t1) => {
    const k = kit(), tot = Math.max(feeTot, k.items.slice(0, 2).concat(k.fees).reduce((a, x) => a + x[1], 0) + 5.69);   // the total the fee ticker reached
    const burst = K.div("", box, "position:absolute;left:-40px;top:-460px;width:2000px;height:2000px;border-radius:50%;background:repeating-conic-gradient(rgba(214,40,40,.16) 0 9deg,transparent 9deg 18deg);opacity:0");
    tl.fromTo(burst, { opacity: 0 }, { opacity: 1, duration: 0.2 }, t0);   // on screen at once: no near-empty first frames
    tl.fromTo(burst, { rotation: 0, scale: 0.8 }, { rotation: 40, scale: 1.1, duration: t1 - t0, ease: "none" }, t0);
    const n = K.div("", box, "position:absolute;left:0;right:0;top:300px;text-align:center;font:400 330px Anton, sans-serif;color:#d62828;text-shadow:0 18px 50px rgba(0,0,0,.3);opacity:0", K.money(tot));
    const tk = Math.max(t0 + 0.15, Math.min(ln.keyT - 0.15, t1 - 0.7));
    tl.fromTo(n, { opacity: 0, scale: 3 }, { opacity: 1, scale: 1, duration: 0.22, ease: "power4.out" }, tk);
    K.shake(tl, box, tk + 0.05, 22, 0.4);
    tl.to(n, { scale: 1.12, duration: Math.max(0.3, t1 - tk - 0.25), ease: "none" }, tk + 0.25);
    const q = K.div("", box, "position:absolute;left:1430px;top:170px;font:400 200px Anton, sans-serif;color:#fff;background:#111;padding:0 40px;border-radius:30px;opacity:0", "?!");
    tl.fromTo(q, { opacity: 0, scale: 0, rotation: -40 }, { opacity: 1, scale: 1, rotation: 12, duration: 0.3, ease: "back.out(3)" }, tk + 0.2);
    k.fees.concat([["Service fee", 3.2]]).slice(0, 3).forEach((f, i) => {
      const c = K.div("", box, `position:absolute;left:${[250, 1250, 330][i]}px;top:${[200, 720, 760][i]}px;padding:14px 26px;border-radius:16px;background:#fff;color:#d62828;font:800 40px Inter, sans-serif;box-shadow:0 12px 30px rgba(0,0,0,.2);opacity:0`, "+" + K.money(f[1]) + " " + K.esc(f[0]));
      tl.fromTo(c, { opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1, duration: 0.25, ease: "back.out(2)" }, t0 + 0.05 + i * 0.15);
      tl.to(c, { y: i % 2 ? 30 : -30, rotation: i % 2 ? 6 : -6, duration: Math.max(0.4, t1 - t0 - 0.4), ease: "sine.inOut" }, t0 + 0.3 + i * 0.15);
    });
    const wt = word(ln);
    if (wt) {
      const w = big(box, wt, "top:760px;font-size:150px");
      tl.fromTo(w, { opacity: 0, y: 50 }, { opacity: 1, y: 0, duration: 0.25 }, tk + 0.3);
    }
  };
  // 11b. type beat: the line's OWN words land one by one on the VO, the key words in the app colour with a swipe under them,
  //      over a moving accent band + dot grid (replaces one random word on a plain background, dhgate coupons 2026-10-24)
  const plainWord = S.word;
  S.word = (tl, box, ln, t0, t1) => {
    if (window.NO_SCENE_TEXT) return;   // P21: the backdrop clip only, the words come from K.punch (one caption track)
    const acc = app().accent;
    const ws = (I.words || []).filter((w) => w.s >= ln.s - 0.02 && w.s < ln.e + 0.02 && !w.date);
    if (!ws.length || ln.role === "turn") return plainWord(tl, box, ln, t0, t1);
    const band = K.div("", box, `position:absolute;left:-300px;top:330px;width:2520px;height:420px;background:${acc};opacity:.14;transform:rotate(-6deg)`);
    tl.fromTo(band, { x: -600 }, { x: 200, duration: t1 - t0, ease: "none" }, t0);
    const dots = K.div("", box, "position:absolute;left:-200px;top:-200px;width:2320px;height:1480px;background-image:radial-gradient(rgba(0,0,0,.09) 3px,transparent 3px);background-size:46px 46px");
    tl.fromTo(dots, { x: 0, y: 0 }, { x: -138, y: -92, duration: t1 - t0, ease: "none" }, t0);
    const keyset = new Set(strong(ln).toLowerCase().split(/\s+/));
    const fs = ws.length > 8 ? 120 : ws.length > 5 ? 150 : 190;
    const wrap = K.div("", box, `position:absolute;left:140px;right:140px;top:${540 - fs}px;display:flex;flex-wrap:wrap;justify-content:center;gap:0 34px;font:400 ${fs}px Anton, sans-serif;line-height:1.05;text-transform:uppercase`);
    ws.forEach((w) => {
      const clean = w.w.replace(/[^\w$%'&.-]/g, "").replace(/[.,]$/, "");
      const hot = !ln.key_weak && (w.k || keyset.has(clean.toLowerCase()));
      const e = K.div("", wrap, `position:relative;color:${hot ? acc : ink()};opacity:0`, K.esc(clean));
      tl.fromTo(e, { opacity: 0, y: 60, scale: hot ? 1.6 : 1 }, { opacity: 1, y: 0, scale: 1, duration: hot ? 0.2 : 0.16, ease: hot ? "power4.out" : "power3.out" }, Math.max(t0, w.s - 0.04));
      if (hot) {
        const u = K.div("", e, `position:absolute;left:0;bottom:4px;height:14px;width:0;border-radius:7px;background:${acc}`);
        tl.to(u, { width: "100%", duration: 0.2, ease: "power3.out" }, Math.max(t0, w.s) + 0.12);
      }
    });
    tl.fromTo(wrap, { scale: 1 }, { scale: 1.05, duration: t1 - t0, ease: "none" }, t0);
  };
  S.gameplay = S.word;
  S.carousel = S.word;

  const RULES = [
    [/gatekeep|gate keep|won't share|creators|hiding|keep it to themselves/i, "gate"],
    [/secret|methods?|hidden|ways? to|every (single )?way|tricks?|hacks?/i, "secret"],
    [/coupons?|promo ?codes?|\bcodes\b|discount|cheaper|\bsav(e|ing)\b/i, "coupon"],
    [/free|100 ?%|\$0|zero|nothing|no money/i, "free"],
    [/friends?|everyone|people|family|my boys/i, "friends"],
    [/over and over|again|every (time|day|week)|repeat/i, "again"],
    [/surpris|shock|crazy|insane|can'?t believe|unbelievable/i, "shock"],
    [/fees?\b|shipping|tax(es)?|adding it|name it|add(ed|ing)? (it )?on/i, "fees"],
    [/paying|fees?|more than|expensive|cost|price|\$\d|total|shipping|tax(es)?|check ?out/i, "receipt"],
    [/search|looking for|find|best codes|google/i, "search"],
    [/order|food|cart|delivery|convenient|deals?|apps?/i, "cart"],
    [/what if|did you know|\?$/i, "question"],
  ];
  K.sceneFor = (ln, i) => (I.scenes && I.scenes[i]) || (RULES.find(([re]) => re.test(ln.text)) || [null, ln.s < I.beats.turn ? "notify" : "word"])[1];
  K.scenesFor = (ln, i) => (I.scenes && I.scenes[i] ? [I.scenes[i]] : []).concat((ln._slots || []).length ? [ln._slots[0].kind === "phone" ? "phoneclip" : "facecam", ln._slots[0].kind === "phone" ? "facecam" : "phoneclip"] : [], RULES.filter(([re]) => re.test(ln.text.replace(/no secret/ig, ""))).map((r) => r[1]), [ln.s < I.beats.turn ? "notify" : "word"]);
  K.SCENES = S;
})();

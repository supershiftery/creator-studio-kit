"""One-off: derives src/template.html.tpl (Join Realm card) from the server IP card's rendered index.html."""
from pathlib import Path

HERE = Path(__file__).parent
src = (HERE.parent / "server-ip-card" / "index.html").read_text(encoding="utf-8")
head, rest = src.split("<body>", 1)
script = rest.split("<script>", 1)[1].split("</script>", 1)[0]
helpers = script.split("// ---------- build ----------")[0]
helpers = "\n".join(l for l in helpers.splitlines() if not l.strip().startswith("const CFG ="))
css = head.split("<style>")[1].split("</style>")[0]
css = css.replace('/* Bedrock "Add Server" screen */', '/* Bedrock "Join Realm" screen */')
css = css.replace("#panel { position: absolute; left: 420px; top: 170px; width: 1080px; height: 720px;",
                  "#panel { position: absolute; left: 420px; top: 250px; width: 1080px; height: 580px;")
css = css.replace(".btn { position: absolute; top: 600px;", ".btn { position: absolute; top: 452px;")
css = css.replace("#b-save {", "#b-cancel {").replace("#b-play {", "#b-join {")
css += """
      #p-realm { position: absolute; left: 60px; top: 126px; display: flex; align-items: center; gap: 18px; }
      #p-ric { width: 64px; height: 64px; border: 4px solid #111; flex: none; }
      .box.code { height: 120px; }
      #lt-chip { background: #3c8527; border: 4px solid #1d4d13; padding: 6px 10px; }
      #rank { top: 120px; }
"""

BODY = r"""
    <div id="root" data-composition-id="main" data-start="0" data-duration="__DUR__" data-width="1920" data-height="1080">
      <div id="ph" class="clip layer" data-start="0" data-duration="__DUR__" data-track-index="0"><div class="chip">GAMEPLAY GOES HERE · __NAME_UP__</div></div>
      <div id="dim" class="clip layer" data-start="0" data-duration="__DUR__" data-track-index="1"><div id="dim-el"></div></div>

      <div id="typing" class="clip layer" data-start="0" data-duration="__T_FLYEND__" data-track-index="2">
        <div id="rank"></div>
        <div id="panel">
          <div id="p-head"><div id="p-x"></div></div>
          <div id="p-realm"><div id="p-ric-wrap"></div><div id="p-rname"></div></div>
          <div class="lab" id="l-code" style="top:226px"></div>
          <div class="box code" id="f-code" style="top:266px"><div class="txt" id="t-code"></div><div class="caret" id="c-code"></div></div>
          <div class="btn" id="b-cancel"></div>
          <div class="btn" id="b-join"><div id="b-flash"></div></div>
        </div>
        <div id="cursor"></div>
      </div>

      <div id="lower" class="clip layer" data-start="__T_LT__" data-duration="__LT_DUR__" data-track-index="3">
        <div id="lt"><div id="lt-bar"></div><div id="lt-ic-wrap"></div>
          <div id="lt-lines"><div id="lt-row1"></div><div id="lt-row2"><div id="lt-code"></div><div id="lt-chip"></div></div></div>
          <canvas id="lt-ping"></canvas><div id="lt-shine"></div></div>
      </div>

      __AUDIO__
    </div>
"""

BUILD = r"""
      // ---------- build ----------
      if (CFG.transparent) $("ph").style.display = "none";
      put("p-head", ptext("Join Realm", 6, "#ffffff"));
      put("p-x", ptext("x", 4, "#e8e8e8", { shadow: 0 }));
      { const ic = srvIcon(CFG.seed, 64, CFG.hue); ic.id = "p-ric"; put("p-ric-wrap", ic); }
      put("p-rname", ptext(CFG.name, Math.min(6, Math.floor(860 / (CFG.name.length * 6))), ["#fff3a6", "#ffcf3a"]));
      put("l-code", ptext("Invite Link or Code", 4, "#d0d0d0", { shadow: 0, outline: 0 }));
      put("b-cancel", ptext("Cancel", 6, "#ffffff"));
      put("b-join", ptext("Join", 6, "#ffffff"));
      put("rank", ptext("#" + CFG.rank, 16, ["#fff3a6", "#ffb300"], { shadow: 14, outlineColor: "#2b1c00" }));
      put("cursor", cursorIcon(9));
      // codes are 11 or 15 characters: as big as fits in the 960px box
      put("t-code", ptext(CFG.code, Math.min(11, Math.floor(910 / (CFG.code.length * 6))), "#ffffff", { shadow: 5 }));
      // lower third
      const ic = srvIcon(CFG.seed, 120, CFG.hue); ic.id = "lt-ic"; put("lt-ic-wrap", ic);
      { const r1 = document.createElement("div"); r1.style.cssText = "display:flex;gap:18px;align-items:center";
        r1.appendChild(ptext("#" + CFG.rank, 7, ["#ffe56b", "#ffb300"]));
        r1.appendChild(ptext(CFG.name, Math.min(7, Math.floor(1100 / (CFG.name.length * 6))), "#ffffff")); put("lt-row1", r1); }
      put("lt-code", ptext(CFG.code, 6, ["#bff6ff", "#6dd8ff"]));
      put("lt-chip", ptext("Realm Code", 4, "#ffffff", { shadow: 0 }));
      { const cv = $("lt-ping"); cv.width = 70; cv.height = 56; const ctx = cv.getContext("2d");
        for (let i = 0; i < 5; i++) { ctx.fillStyle = "#4cff6a"; ctx.fillRect(i * 14, 56 - (i + 1) * 11, 10, (i + 1) * 11); } }

      // ---------- timeline ----------
      const T = CFG.t;
      const tl = gsap.timeline({ paused: true });
      tl.fromTo("#dim-el", { opacity: 0 }, { opacity: 1, duration: 0.3 }, 0);
      tl.to("#dim-el", { opacity: 0, duration: 0.4 }, T.fly + 0.1);
      tl.fromTo("#panel", { scale: 0.82, y: 60, opacity: 0 }, { scale: 1, y: 0, opacity: 1, duration: 0.35, ease: "back.out(1.7)" }, 0.05);
      tl.fromTo("#rank", { scale: 2.2, rotation: -14, opacity: 0 }, { scale: 1, rotation: -6, opacity: 1, duration: 0.32, ease: "back.out(2.2)" }, 0.25);
      tl.fromTo("#p-realm", { x: -40, opacity: 0 }, { x: 0, opacity: 1, duration: 0.3, ease: "power2.out" }, 0.35);
      // typing the code: one char cell at a time, caret follows
      { const cv = $("t-code").firstChild, cell = +cv.dataset.cell, pad = +cv.dataset.pad, txt = $("t-code"), caret = $("c-code"), s = CFG.code, t0 = T.code;
        const end = t0 + s.length * T.per;
        tl.set("#f-code", { borderColor: "#ffffff", boxShadow: "0 0 0 4px rgba(110,220,255,.55)" }, t0 - 0.15);
        tl.set(txt, { width: 0 }, 0);
        tl.set(caret, { opacity: 1, x: 22 + pad }, t0 - 0.15);
        for (let i = 1; i <= s.length; i++) { const t = t0 + (i - 1) * T.per; tl.set(txt, { width: pad + i * cell + 4 }, t); tl.set(caret, { x: 22 + pad + i * cell + 4 }, t); }
        tl.set(txt, { width: cv.width }, end);
        for (let b = end + 0.2; b < T.click; b += 0.4) { tl.set(caret, { opacity: 0 }, b); tl.set(caret, { opacity: 1 }, b + 0.2); }
        tl.set(caret, { opacity: 0 }, T.click);
        tl.set("#f-code", { borderColor: "#8b8b8b", boxShadow: "0 0 0 0px rgba(110,220,255,0)" }, T.click); }
      // the code is the point: punch it
      tl.to("#f-code", { scale: 1.05, duration: 0.12, yoyo: true, repeat: 1, ease: "power2.out" }, T.punch);
      // cursor clicks Join, panel flies into the lower third
      tl.fromTo("#cursor", { opacity: 0, x: 0, y: 0 }, { opacity: 1, x: -490, y: -268, duration: 0.38, ease: "power2.out" }, T.cursor);
      tl.to("#cursor", { scale: 0.85, duration: 0.06, yoyo: true, repeat: 1 }, T.click);
      tl.to("#b-join", { y: 6, duration: 0.06, yoyo: true, repeat: 1 }, T.click);
      tl.fromTo("#b-flash", { opacity: 0.9 }, { opacity: 0, duration: 0.3, immediateRender: false }, T.click + 0.02);
      tl.to(["#panel", "#rank", "#cursor"], { x: -560, y: 400, scale: 0.18, opacity: 0, duration: T.flyEnd - T.fly, ease: "power3.in" }, T.fly);
      // lower third (clip starts at T.lt)
      tl.fromTo("#lt", { x: -1300 }, { x: 0, duration: 0.35, ease: "power3.out" }, T.lt);
      tl.fromTo("#lt-shine", { x: 0 }, { x: 1600, duration: 0.7, ease: "power1.inOut" }, T.lt + 0.45);
      tl.fromTo("#lt-ping", { opacity: 0 }, { opacity: 1, duration: 0.2 }, T.lt + 0.35);
      tl.to("#lt", { x: -1300, duration: 0.35, ease: "power3.in" }, T.ltOut);

      window.__timelines = window.__timelines || {};
      window.__timelines["main"] = tl;
"""

tpl = (head.split("<style>")[0] + "<style>" + css + "    </style>\n  </head>\n  <body>" + BODY
       + "\n    <script>\n      const CFG = __CFG__;\n" + helpers + BUILD + "    </script>\n  </body>\n</html>\n")
(HERE / "src" / "template.html.tpl").write_text(tpl, encoding="utf-8")
print("template written", len(tpl))

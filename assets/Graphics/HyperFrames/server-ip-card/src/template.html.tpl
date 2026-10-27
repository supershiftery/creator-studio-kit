<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
    <style>
      @font-face { font-family: "CapFont"; src: url("assets/caption.ttf") format("truetype"); font-weight: 900; }
      /* --kv: the rank badge in KV Digital's pixel box (Minecraftia, stepped charcoal/red/orange box), see _templates/kv-pixelbox */
      @font-face { font-family: "MCF"; src: url("assets/Minecraftia-Regular.ttf") format("truetype"); }
      #rank.kvmode { left: 250px; top: 78px; }
      .kvr { display: flex; font-family: "MCF"; font-size: 130px; line-height: 1; white-space: nowrap; }
      .kvr span { display: inline-block; color: #f8f8f8; filter: url(#kvbox); padding: 0 22px; }
      * { margin: 0; padding: 0; box-sizing: border-box; }
      html, body { margin: 0; width: 1920px; height: 1080px; overflow: hidden; background: transparent; }
      #root { position: relative; width: 100%; height: 100%; overflow: hidden; }
      .layer { position: absolute; inset: 0; overflow: hidden; }
      .abs { position: absolute; }
      canvas { image-rendering: pixelated; display: block; }

      /* footage placeholder (hidden when rendering as a transparent overlay) */
      #ph { background: repeating-linear-gradient(45deg, #1a2230 0 28px, #151c28 28px 56px); }
      #ph .chip { position: absolute; left: 50%; top: 46%; transform: translate(-50%, -50%); font-family: "CapFont"; font-size: 30px; letter-spacing: 2px;
        color: #dff3ff; background: rgba(0,0,0,.7); padding: 10px 22px; border: 3px dashed rgba(140,200,255,.6); white-space: nowrap; }
      #dim-el { position: absolute; inset: 0; background: rgba(4,6,12,.62); opacity: 0; }

      /* Bedrock "Add Server" screen */
      #panel { position: absolute; left: 420px; top: 170px; width: 1080px; height: 720px; background: #313233; border: 6px solid #1e1e1f;
        box-shadow: inset 0 6px 0 #4a4b4c, 0 30px 90px rgba(0,0,0,.7); opacity: 0; }
      #p-head { position: absolute; left: 0; right: 0; top: 0; height: 96px; background: #48494a; border-bottom: 6px solid #1e1e1f;
        box-shadow: inset 0 6px 0 #6a6b6c; display: flex; align-items: center; justify-content: center; }
      #p-x { position: absolute; right: 22px; top: 18px; width: 54px; height: 54px; background: #6f7071; border: 4px solid #1e1e1f;
        box-shadow: inset 0 -5px 0 #4a4b4c; display: flex; align-items: center; justify-content: center; }
      .lab { position: absolute; left: 60px; }
      .box { position: absolute; left: 60px; width: 960px; height: 88px; background: #1e1e1f; border: 4px solid #8b8b8b; }
      .box.on { border-color: #ffffff; box-shadow: 0 0 0 4px rgba(110,220,255,.55); }
      .txt { position: absolute; left: 22px; top: 50%; transform: translateY(-50%); overflow: hidden; width: 0; }
      .txt canvas { display: block; }
      .caret { position: absolute; top: 50%; width: 6px; height: 52px; margin-top: -26px; background: #fff; opacity: 0; }
      .btn { position: absolute; top: 600px; width: 465px; height: 84px; border: 5px solid #1e1e1f; display: flex; align-items: center; justify-content: center; }
      #b-save { left: 60px; background: #6f7071; box-shadow: inset 0 -8px 0 #4a4b4c, inset 0 5px 0 #9a9b9c; }
      #b-play { left: 555px; background: #3c8527; box-shadow: inset 0 -8px 0 #1d4d13, inset 0 5px 0 #6cc349; }
      #b-flash { position: absolute; inset: 0; background: #b9ff9a; opacity: 0; }
      #rank { position: absolute; left: 300px; top: 40px; opacity: 0; z-index: 3; }
      #cursor { position: absolute; left: 1700px; top: 1000px; opacity: 0; }

      /* lower third */
      #lt { position: absolute; left: 56px; top: 846px; height: 176px; display: flex; align-items: center; gap: 26px; padding: 0 34px 0 26px;
        background: rgba(49,50,51,.94); border: 6px solid #1e1e1f; box-shadow: inset 0 6px 0 #4a4b4c, 0 16px 40px rgba(0,0,0,.55); overflow: hidden; }
      #lt-ic { width: 120px; height: 120px; border: 4px solid #111; flex: none; }
      #lt-lines { display: flex; flex-direction: column; gap: 14px; }
      #lt-row2 { display: flex; align-items: center; gap: 18px; }
      #lt-port { background: #3c8527; border: 4px solid #1d4d13; padding: 6px 10px; }
      #lt-ping { width: 70px; height: 56px; flex: none; margin-left: 10px; }
      #lt-shine { position: absolute; top: -20px; bottom: -20px; width: 120px; left: -200px; transform: skewX(-20deg);
        background: linear-gradient(90deg, transparent, rgba(255,255,255,.22), transparent); }
      #lt-bar { position: absolute; left: 0; top: 0; bottom: 0; width: 10px; background: #ffd23a; }
    </style>
  </head>
  <body>
    <svg width="0" height="0" style="position:absolute"><filter id="kvbox" x="-30%" y="-60%" width="160%" height="230%" color-interpolation-filters="sRGB"><feMorphology in="SourceAlpha" operator="dilate" radius="42" result="big" /><feMorphology in="big" operator="erode" radius="29" result="d1" /><feMorphology in="big" operator="erode" radius="23" result="d2" /><feMorphology in="big" operator="erode" radius="16" result="d3" /><feOffset in="d3" dx="3" dy="16" result="sh" /><feFlood flood-color="#232327" /><feComposite in2="sh" operator="in" result="shc" /><feFlood flood-color="#f8b000" /><feComposite in2="d3" operator="in" result="o" /><feFlood flood-color="#f81010" /><feComposite in2="d2" operator="in" result="r" /><feFlood flood-color="#2a2530" /><feComposite in2="d1" operator="in" result="f" /><feMerge><feMergeNode in="shc" /><feMergeNode in="o" /><feMergeNode in="r" /><feMergeNode in="f" /><feMergeNode in="SourceGraphic" /></feMerge></filter></svg>
    <div id="root" data-composition-id="main" data-fps="60" data-start="0" data-duration="__DUR__" data-width="1920" data-height="1080">
      <div id="ph" class="clip layer" data-start="0" data-duration="__DUR__" data-track-index="0"><div class="chip">GAMEPLAY GOES HERE · __NAME_UP__</div></div>
      <div id="dim" class="clip layer" data-start="0" data-duration="__DUR__" data-track-index="1"><div id="dim-el"></div></div>

      <div id="typing" class="clip layer" data-start="0" data-duration="__T_FLYEND__" data-track-index="2">
        <div id="rank"></div>
        <div id="panel">
          <div id="p-head"><div id="p-x"></div></div>
          <div class="lab" id="l-name" style="top:126px"></div>
          <div class="box" id="f-name" style="top:166px"><div class="txt" id="t-name"></div><div class="caret" id="c-name"></div></div>
          <div class="lab" id="l-addr" style="top:280px"></div>
          <div class="box" id="f-addr" style="top:320px"><div class="txt" id="t-addr"></div><div class="caret" id="c-addr"></div></div>
          <div class="lab" id="l-port" style="top:434px"></div>
          <div class="box" id="f-port" style="top:474px;width:330px"><div class="txt" id="t-port"></div><div class="caret" id="c-port"></div></div>
          <div class="btn" id="b-save"></div>
          <div class="btn" id="b-play"><div id="b-flash"></div></div>
        </div>
        <div id="cursor"></div>
      </div>

      <div id="lower" class="clip layer" data-start="__T_LT__" data-duration="__LT_DUR__" data-track-index="3">
        <div id="lt"><div id="lt-bar"></div><div id="lt-ic-wrap"></div>
          <div id="lt-lines"><div id="lt-row1"></div><div id="lt-row2"><div id="lt-addr"></div><div id="lt-port"></div></div></div>
          <canvas id="lt-ping"></canvas><div id="lt-shine"></div></div>
      </div>

      __AUDIO__
    </div>

    <script>
      const CFG = __CFG__;

      function rng(seed) {
        let a = seed >>> 0;
        return function () {
          a |= 0; a = (a + 0x6d2b79f5) | 0;
          let t = Math.imul(a ^ (a >>> 15), 1 | a);
          t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
          return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
        };
      }
      // Minecraft-style pixel font: 5 wide, 8 rows (row 7 = descender). Upper case + digits from the 5x7 set, lower case drawn here.
      const G = {
        A:"01110100011000111111100011000110001",B:"11110100011000111110100011000111110",C:"01110100011000010000100001000101110",
        D:"11110100011000110001100011000111110",E:"11111100001000011110100001000011111",F:"11111100001000011110100001000010000",
        G:"01111100001000010011100011000101111",H:"10001100011000111111100011000110001",I:"11111001000010000100001000010011111",
        J:"00111000010000100001100011000101110",K:"10001100101010011000101001001010001",L:"10000100001000010000100001000011111",
        M:"10001110111010110101100011000110001",N:"10001110011010110011100011000110001",O:"01110100011000110001100011000101110",
        P:"11110100011000111110100001000010000",Q:"01110100011000110001101011001001101",R:"11110100011000111110101001001010001",
        S:"01111100001000001110000010000111110",T:"11111001000010000100001000010000100",U:"10001100011000110001100011000101110",
        V:"10001100011000110001100010101000100",W:"10001100011000110101101011101110001",X:"10001100010101000100010101000110001",
        Y:"10001100010101000100001000010000100",Z:"11111000010001000100010001000011111",
        "0":"01110100011000110001100011000101110","1":"00100011000010000100001000010011111","2":"01110100010000100110010001000011111",
        "3":"01110100010000100110000011000101110","4":"00010001100101010010111110001000010","5":"11111100001111000001000011000101110",
        "6":"00110010001000011110100011000101110","7":"11111000010001000100010000100001000","8":"01110100011000101110100011000101110",
        "9":"01110100011000101111000010001001100","!":"00100001000010000100001000000000100","?":"01110100010000100110001000000000100",
        "'":"00100001000100000000000000000000000",".":"00000000000000000000000000000000100","-":"00000000000000011111000000000000000",
        ":":"00000001000010000000000000010000100","/":"00001000100001000100010000100010000","#":"01010111110101001010111110101000000",
        "_":"00000000000000000000000000000011111"
      };
      const LOW = {
        a:[".....",".....",".###.","....#",".####","#...#",".####","....."], b:["#....","#....","#.##.","##..#","#...#","#...#","####.","....."],
        c:[".....",".....",".###.","#...#","#....","#...#",".###.","....."], d:["....#","....#",".##.#","#..##","#...#","#...#",".####","....."],
        e:[".....",".....",".###.","#...#","#####","#....",".####","....."], f:["..##.",".#...","####.",".#...",".#...",".#...",".#...","....."],
        g:[".....",".....",".####","#...#","#...#",".####","....#","####."], h:["#....","#....","#.##.","##..#","#...#","#...#","#...#","....."],
        i:["..#..",".....","..#..","..#..","..#..","..#..","..#..","....."], j:["....#",".....","....#","....#","....#","....#","#...#",".###."],
        k:["#....","#....","#..#.","#.#..","##...","#.#..","#..#.","....."], l:["..#..","..#..","..#..","..#..","..#..","..#..","...#.","....."],
        m:[".....",".....","##.#.","#.#.#","#.#.#","#...#","#...#","....."], n:[".....",".....","####.","#...#","#...#","#...#","#...#","....."],
        o:[".....",".....",".###.","#...#","#...#","#...#",".###.","....."], p:[".....",".....","#.##.","##..#","#...#","####.","#....","#...."],
        q:[".....",".....",".##.#","#..##","#...#",".####","....#","....#"], r:[".....",".....","#.##.","##..#","#....","#....","#....","....."],
        s:[".....",".....",".####","#....",".###.","....#","####.","....."], t:["..#..","..#..","#####","..#..","..#..","..#..","...##","....."],
        u:[".....",".....","#...#","#...#","#...#","#...#",".####","....."], v:[".....",".....","#...#","#...#","#...#",".#.#.","..#..","....."],
        w:[".....",".....","#...#","#...#","#.#.#","#.#.#",".#.#.","....."], x:[".....",".....","#...#",".#.#.","..#..",".#.#.","#...#","....."],
        y:[".....",".....","#...#","#...#","#...#",".####","....#","####."], z:[".....",".....","#####","...#.","..#..",".#...","#####","....."],
        "é":["...#.","..#..",".###.","#...#","#####","#....",".####","....."], "É":["...#.","..#..","#####","#....","####.","#....","#####","....."],
      };
      function rows(c) {
        if (LOW[c]) return LOW[c];
        const g = G[c.toUpperCase()];
        if (!g) return null;
        const r = []; for (let y = 0; y < 7; y++) r.push(g.slice(y * 5, y * 5 + 5).replace(/1/g, "#").replace(/0/g, ".")); r.push(".....");
        return r;
      }
      // pixel text (mixed case); every char cell is 6*ps wide, so typing can reveal it one cell at a time
      function ptext(text, ps, fill, o = {}) {
        const out = o.outline ?? Math.round(ps * 0.4), sh = o.shadow ?? Math.round(ps * 0.8);
        const cells = [];
        [...text].forEach((ch, i) => { const r = rows(ch); if (r) r.forEach((row, y) => [...row].forEach((v, x) => { if (v === "#") cells.push([i * 6 + x, y]); })); });
        const cv = document.createElement("canvas");
        cv.width = text.length * 6 * ps + out * 2 + sh; cv.height = 8 * ps + out * 2 + sh;
        const ctx = cv.getContext("2d"), at = (x, y) => [out + x * ps, out + y * ps];
        ctx.fillStyle = o.shadowColor || "rgba(0,0,0,.5)"; cells.forEach(([x, y]) => { const [px, py] = at(x, y); ctx.fillRect(px + sh - out, py + sh - out, ps + out * 2, ps + out * 2); });
        if (out) { ctx.fillStyle = o.outlineColor || "#000"; cells.forEach(([x, y]) => { const [px, py] = at(x, y); ctx.fillRect(px - out, py - out, ps + out * 2, ps + out * 2); }); }
        cells.forEach(([x, y]) => { const [px, py] = at(x, y); ctx.fillStyle = Array.isArray(fill) ? (y < 4 ? fill[0] : fill[1]) : fill; ctx.fillRect(px, py, ps, ps); });
        cv.dataset.cell = 6 * ps; cv.dataset.pad = out;
        return cv;
      }
      function srvIcon(seed, size, hue) {
        const r = rng(seed), cv = document.createElement("canvas"); cv.width = size; cv.height = size;
        const ctx = cv.getContext("2d"), p = size / 8;
        ctx.fillStyle = `hsl(${hue},45%,18%)`; ctx.fillRect(0, 0, size, size);
        for (let y = 0; y < 8; y++) for (let x = 0; x < 4; x++) if (r() < 0.55) {
          ctx.fillStyle = `hsl(${hue + (r() * 40 - 20)},${60 + r() * 30}%,${42 + r() * 25}%)`;
          ctx.fillRect(x * p, y * p, p, p); ctx.fillRect((7 - x) * p, y * p, p, p);
        }
        return cv;
      }
      const CURSOR = ["K.......","KK......","KWK.....","KWWK....","KWWWK...","KWWWWK..","KWWKKK..","KK.WK...","....K..."];
      function cursorIcon(ps) {
        const cv = document.createElement("canvas"); cv.width = 8 * ps; cv.height = 9 * ps; const ctx = cv.getContext("2d");
        CURSOR.forEach((row, y) => [...row].forEach((ch, x) => { if (ch !== ".") { ctx.fillStyle = ch === "K" ? "#111" : "#fff"; ctx.fillRect(x * ps, y * ps, ps, ps); } }));
        return cv;
      }
      const $ = (id) => document.getElementById(id);
      const put = (id, el) => { $(id).appendChild(el); return el; };

      // ---------- build ----------
      if (CFG.transparent) $("ph").style.display = "none";
      put("p-head", ptext("Add Server", 6, "#ffffff"));
      put("p-x", ptext("x", 4, "#e8e8e8", { shadow: 0 }));
      put("l-name", ptext("Server Name", 4, "#d0d0d0", { shadow: 0, outline: 0 }));
      put("l-addr", ptext("Server Address", 4, "#d0d0d0", { shadow: 0, outline: 0 }));
      put("l-port", ptext("Port", 4, "#d0d0d0", { shadow: 0, outline: 0 }));
      put("b-save", ptext("Save", 6, "#ffffff"));
      put("b-play", ptext("Play", 6, "#ffffff"));
      if (CFG.kv) $("rank").classList.add("kvmode"), $("rank").innerHTML = '<div class="kvr"><span>#' + CFG.rank + "</span></div>";
      else put("rank", ptext("#" + CFG.rank, 16, ["#fff3a6", "#ffb300"], { shadow: 14, outlineColor: "#2b1c00" }));
      put("cursor", cursorIcon(9));
      const FIELDS = [["name", CFG.name, CFG.t.name], ["addr", CFG.ip, CFG.t.addr], ["port", String(CFG.port), CFG.t.port]];
      // long addresses step the font down so they stay inside the 960px box
      FIELDS.forEach(([k, s]) => put("t-" + k, ptext(s, Math.min(7, Math.floor(910 / (s.length * 6))), "#ffffff", { shadow: 5 })));
      // lower third
      const ic = srvIcon(CFG.seed, 120, CFG.hue); ic.id = "lt-ic"; put("lt-ic-wrap", ic);
      { const r1 = document.createElement("div"); r1.style.cssText = "display:flex;gap:18px;align-items:center";
        r1.appendChild(ptext("#" + CFG.rank, 7, ["#ffe56b", "#ffb300"])); r1.appendChild(ptext(CFG.name, 7, "#ffffff")); put("lt-row1", r1); }
      put("lt-addr", ptext(CFG.ip, 6, ["#bff6ff", "#6dd8ff"]));
      put("lt-port", ptext("Port " + CFG.port, 4, "#ffffff", { shadow: 0 }));
      { const cv = $("lt-ping"); cv.width = 70; cv.height = 56; const ctx = cv.getContext("2d");
        for (let i = 0; i < 5; i++) { ctx.fillStyle = "#4cff6a"; ctx.fillRect(i * 14, 56 - (i + 1) * 11, 10, (i + 1) * 11); } }

      // ---------- timeline ----------
      const T = CFG.t;
      const tl = gsap.timeline({ paused: true });
      tl.fromTo("#dim-el", { opacity: 0 }, { opacity: 1, duration: 0.3 }, 0);
      tl.to("#dim-el", { opacity: 0, duration: 0.4 }, T.fly + 0.1);
      tl.fromTo("#panel", { scale: 0.82, y: 60, opacity: 0 }, { scale: 1, y: 0, opacity: 1, duration: 0.35, ease: "back.out(1.7)" }, 0.05);
      tl.fromTo("#rank", { scale: 2.2, rotation: -14, opacity: 0 }, { scale: 1, rotation: -6, opacity: 1, duration: 0.32, ease: "back.out(2.2)" }, 0.25);
      // typing: reveal one char cell at a time, caret follows; the active field gets a white border
      FIELDS.forEach(([k, s, t0], fi) => {
        const cv = $("t-" + k).firstChild, cell = +cv.dataset.cell, pad = +cv.dataset.pad, txt = $("t-" + k), caret = $("c-" + k);
        const end = t0 + s.length * T.per[fi];
        tl.set("#f-" + k, { borderColor: "#ffffff", boxShadow: "0 0 0 4px rgba(110,220,255,.55)" }, t0 - 0.12);
        tl.set(txt, { width: 0 }, 0);
        tl.set(caret, { opacity: 1, x: 22 + pad }, t0 - 0.12);
        for (let i = 1; i <= s.length; i++) {
          const t = t0 + (i - 1) * T.per[fi];
          tl.set(txt, { width: pad + i * cell + 4 }, t);
          tl.set(caret, { x: 22 + pad + i * cell + 4 }, t);
        }
        tl.set(txt, { width: cv.width }, end);
        const next = fi < 2 ? FIELDS[fi + 1][2] - 0.12 : T.click;
        for (let b = end + 0.2; b < next; b += 0.4) { tl.set(caret, { opacity: 0 }, b); tl.set(caret, { opacity: 1 }, b + 0.2); }
        tl.set(caret, { opacity: 0 }, next);
        tl.set("#f-" + k, { borderColor: "#8b8b8b", boxShadow: "0 0 0 0px rgba(110,220,255,0)" }, next);
      });
      // the address is the point: punch it
      tl.to("#f-addr", { scale: 1.05, duration: 0.12, yoyo: true, repeat: 1, ease: "power2.out" }, T.punch);
      // cursor clicks Play, panel flies into the lower third
      tl.fromTo("#cursor", { opacity: 0, x: 0, y: 0 }, { opacity: 1, x: -490, y: -190, duration: 0.38, ease: "power2.out" }, T.cursor);
      tl.to("#cursor", { scale: 0.85, duration: 0.06, yoyo: true, repeat: 1 }, T.click);
      tl.to("#b-play", { y: 6, duration: 0.06, yoyo: true, repeat: 1 }, T.click);
      tl.fromTo("#b-flash", { opacity: 0.9 }, { opacity: 0, duration: 0.3, immediateRender: false }, T.click + 0.02);
      tl.to(["#panel", "#rank", "#cursor"], { x: -560, y: 400, scale: 0.18, opacity: 0, duration: T.flyEnd - T.fly, ease: "power3.in" }, T.fly);
      // lower third (clip starts at T.lt)
      tl.fromTo("#lt", { x: -900 }, { x: 0, duration: 0.35, ease: "power3.out" }, T.lt);
      tl.fromTo("#lt-shine", { x: 0 }, { x: 1400, duration: 0.7, ease: "power1.inOut" }, T.lt + 0.45);
      tl.fromTo("#lt-ping", { opacity: 0 }, { opacity: 1, duration: 0.2 }, T.lt + 0.35);
      tl.to("#lt", { x: -900, duration: 0.35, ease: "power3.in" }, T.ltOut);

      window.__timelines = window.__timelines || {};
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>

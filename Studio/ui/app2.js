/* {{STUDIO_NAME}} UI, part 2: New Project screen, the Gling-style editor, the Thumbnails board.
   Loaded after app.js; function declarations here replace the earlier ones of the same name. */

// ---------------------------------------------------------------- edit options (New Project + Project settings; user 2026-10-22)
// Trim only = the recording with the bad takes / silences cut, nothing added (any type; optional speed-up).
// Music and Privacy check are on by default; privacy only exists in the phone pipeline.
// motion graphic types (tools/motion_graphics.py MAKERS); article = the MacBook one-off's 3D news card with a yellow marker
const GFX_TYPES = [["article", "Article highlight (3D)"]];
// burned-in captions (user 2026-10-23): OFF by default, per project; presets = the styles most creators use (app/tools/captions.py
// PRESETS, previews rendered by `captions.py --previews` into ui/captions/). A font not in app/fonts uses a look-alike.
const CAP_STYLES = [["bold", "Bold pop (Hormozi) · Montserrat Black"], ["clean", "Clean subtitles · Montserrat Bold"], ["beast", "MrBeast style · Komika Axis"],
  ["boldfont", "The Bold Font · tall caps"], ["youtube", "YouTube CC box · Roboto"]];
// 2026-10-29: picked from a grid of the preview PNGs (presets.json order); "low" styles sit at the bottom of the frame, so on
// gaming projects they're greyed out (no bottom captions on Minecraft videos). CAP_STYLES = fallback when presets.json won't load.
let CAP_META = null;
const CAP_READY = fetch("captions/presets.json").then(r => r.json()).then(j => { CAP_META = Object.fromEntries(j.filter(x => x.pick !== false).map(x => [x.key, x])); }).catch(() => {});
// 2026-10-29 (testers: "there's a lot going on" on this screen): up front only what most videos need: where the captions go,
// when it builds and on which device. Everything else sits behind "More options" (closed by default).
const CAP_WHERE = [["all", "Whole video"], ["bookends", "Intro and ending only"], ["off", "No captions"]];   // same words as the editor's Captions tab
// round 2 (user video 2026-10-29 13:43): plain words, "This computer", another computer = an advanced link, requests up top
const machineName = n => n === (S.state?.machine || "Desktop") ? "This computer" : n;
function modeOptsHtml(st = {}, type = "gaming", extraMore = "", extraTop = "") {
  const sp = st.trim_speed || 1, gx = st.graphics || {};
  const cap = st.captions, capOn = cap === true || (cap && cap.on), where = capOn ? ((cap && cap.where) || "all") : "off";
  const build = (() => {   // first build: now / at a time / not yet, on which device (2026-10-25: laptop first, schedule builds)
    const ms = [...new Set([S.state?.machine || "Desktop", ...((S.state?.remote?.workers || []).map(w => w.name))])];
    const cur = st.machine || S.state?.default_machine || "Laptop";
    const ba = st.build_at && st.build_at !== "hold" ? st.build_at.replace(" ", "T") : "";
    return `<div class="mo-row"><span class="mo-lbl">Build</span>
      <select id="mo-when" aria-label="When to build"><option value="now" ${!st.build_at ? "selected" : ""}>Now</option><option value="at" ${ba ? "selected" : ""}>At a time…</option><option value="hold" ${st.build_at === "hold" ? "selected" : ""}>Not yet</option></select>
      <input type="datetime-local" id="mo-at" value="${ba}" style="${ba ? "" : "display:none"}" aria-label="Build at">
      <span class="mo-lbl2">on</span><span class="mo-here" ${ms.length > 1 ? 'style="display:none"' : ""}>this computer</span><select id="mo-mach" aria-label="Device that builds it" title="the other device takes over if this one is off" ${ms.length < 2 ? 'style="display:none"' : ""}>${[...ms, ...(ms.length > 1 ? ["Both"] : [])].map(n => `<option value="${esc(n)}" ${n.toLowerCase() === String(cur).toLowerCase() ? "selected" : ""}>${n === "Both" ? "Both (first free)" : esc(machineName(n))}</option>`).join("")}</select>
      <a class="mo-adv" id="mo-adddev" role="button" tabindex="0">Build on another computer (advanced)</a></div>`;
  })();
  return `<div class="mo-main" id="mo-main">
    <div class="mo-row"><span class="mo-lbl">Captions</span>
      <div class="seg" role="radiogroup" aria-label="Where captions go">${CAP_WHERE.map(([k, l]) => `<button type="button" role="radio" aria-checked="${where === k}" class="${where === k ? "on" : ""}" data-capwhere="${k}">${l}</button>`).join("")}</div>
      <span class="mo-capnow" id="mo-capnow"></span><button type="button" class="sm" id="mo-caplook">Change look</button>
      <input type="hidden" id="mo-cap-where" value="${where}"><input type="hidden" id="mo-cap-style" value="${esc((cap || {}).style || "bold")}"></div>
    <div class="mo-capgrid" id="mo-capgrid" style="display:none"><div id="mo-cap-grid" class="cap-grid"></div><small id="mo-cap-font" class="muted tiny"></small></div>
    ${extraTop}
    <div class="mo-row mo-reqrow"><label class="mo-lbl" for="mo-req">Anything special?</label><textarea id="mo-req" rows="2" placeholder="optional, one per line, e.g. “title says ULTIMATE DHGATE SHEET” or “Mario music under #1”">${esc(st.requests || "")}</textarea></div>
    ${build}
  </div>
  <details class="mo-more" id="mo-more"><summary>More options <span class="muted tiny">music, cutting, channel, due date…</span></summary>
  ${extraMore}
  <div class="np-opts" id="mo">
    <label class="mo-opt" id="mo-music-l"><input type="checkbox" id="mo-music" ${st.music !== false ? "checked" : ""}><span><b>Background music</b><small>beats under your voice (game music on gaming videos)</small></span><select id="mo-mstyle" title="no-camera videos: one lo-fi loop, or beats that change by section">${[["", "Lo-fi loop"], ["beats", "Upbeat beats"], ["chill", "Chill, changes by section"]].map(([v, t]) => `<option value="${v}" ${(st.music_style || "") === v ? "selected" : ""}>${t}</option>`).join("")}</select></label>
    <label class="mo-opt"><input type="checkbox" id="mo-screen" ${st.screen ? "checked" : ""}><span><b>No camera</b><small>just your screen, shown full size (ticked by itself when there's no camera)</small></span></label>
    <label class="mo-opt"><input type="checkbox" id="mo-trim" ${st.trim_only ? "checked" : ""}><span><b>Only cut mistakes</b><small>removes bad takes and pauses, adds nothing else</small></span></label>
    <label class="mo-opt mo-stack" id="mo-speed-l"><span><b>Speed up</b><small>for "Only cut mistakes" and no-camera videos</small></span><select id="mo-speed">${[1, 1.1, 1.25, 1.5].map(v => `<option value="${v}" ${v === sp ? "selected" : ""}>${v === 1 ? "Normal speed" : v + "×"}</option>`).join("")}</select></label>
    <label class="mo-opt" id="mo-priv-l"><input type="checkbox" id="mo-priv" ${st.privacy !== false ? "checked" : ""}><span><b>Hide private info</b><small id="mo-priv-s">blurs addresses and phone numbers</small></span></label>
    <label class="mo-opt" id="mo-claude-l"><input type="checkbox" id="mo-claude" ${st.claude !== false ? "checked" : ""}><span><b>AI helper</b><small>AI picks the intro shots and checks the pictures (about 1¢ a video)</small></span></label>
    <label class="mo-opt mo-stack"><span><b>Remove “um” and “uh”</b><small>filler words</small></span><select id="mo-fill">${[["", "Usual for this channel"], ["auto", "Automatic"], ["light", "Only um / uh"], ["heavy", "Also “and yeah”, “alright”"], ["off", "Keep them"]].map(([v, t]) => `<option value="${v}" ${(st.fillers || "") === v ? "selected" : ""}>${t}</option>`).join("")}</select></label>
    <label class="mo-opt mo-wide" id="mo-gfx-l"><input type="checkbox" id="mo-gfx" ${gx.on ? "checked" : ""}><span><b>Article graphic</b><small id="mo-gfx-s">AI finds a news article and shows it as a 3D card where it fits</small><select id="mo-gfx-type">${GFX_TYPES.map(([v, t]) => `<option value="${v}" ${(gx.type || "article") === v ? "selected" : ""}>${t}</option>`).join("")}</select></span></label>
    <label class="mo-opt mo-wide" id="mo-gfx-url-l"><span><b>Article link</b><small>optional · empty = the AI searches the web</small><input id="mo-gfx-url" placeholder="https://…" value="${esc(gx.url || "")}"></span></label>
    <label class="mo-opt mo-wide" id="mo-gfx-hl-l"><span><b>Words to highlight</b><small>optional · split with |</small><input id="mo-gfx-hl" placeholder="touchscreen MacBook Pro | OLED displays" value="${esc((gx.highlight || []).join(" | "))}"></span></label>
  </div></details>`;
}
function wireModeOpts(m, getType) {
  const sync = () => {
    const trim = $("#mo-trim", m).checked, screen = $("#mo-screen", m).checked, phone = getType() === "phone";
    $("#mo-speed-l", m).classList.toggle("off", !trim && !screen); $("#mo-speed", m).disabled = !trim && !screen;
    // a screen recording keeps its music bed; trim only has none
    $("#mo-music-l", m).classList.toggle("off", trim && !screen); $("#mo-music", m).disabled = trim && !screen;
    $("#mo-mstyle", m).style.display = screen ? "" : "none";   // the music style only exists in the screen-recording edit
    // privacy: phone edits blur the user's own details; screen recordings scan the kept parts for anyone's (2026-10-23)
    const privOk = screen || (phone && !trim);
    $("#mo-priv-l", m).classList.toggle("off", !privOk); $("#mo-priv", m).disabled = !privOk;
    $("#mo-priv-s", m).textContent = screen ? "blurs emails, phone, address, bank and card numbers" : phone ? "blurs addresses and phone numbers" : "for app and no-camera videos";
    // motion graphics: screen-recording edits for now (the renderer that lays them over is tools/trim_render.py)
    const gOk = screen, gOn = gOk && $("#mo-gfx", m).checked, art = $("#mo-gfx-type", m).value === "article";
    $("#mo-gfx-l", m).classList.toggle("off", !gOk); $("#mo-gfx", m).disabled = !gOk; $("#mo-gfx-type", m).disabled = !gOn;
    $("#mo-gfx-s", m).textContent = gOk ? "AI finds a news article and shows it as a 3D card where it fits" : "for no-camera videos";
    for (const id of ["#mo-gfx-url-l", "#mo-gfx-hl-l"]) $(id, m).style.display = gOn && art ? "" : "none";
    capSync();   // the type decides which caption styles are greyed out
  };
  let lookOpen = false;
  const capSync = () => {   // captions: where they go (3 buttons); the look shows as one name + "Change look" opens the grid
    const where = $("#mo-cap-where", m).value, on = where !== "off", k = $("#mo-cap-style", m).value, meta = CAP_META && CAP_META[k], gaming = getType() === "gaming";
    m.querySelectorAll("[data-capwhere]").forEach(b => { const sel = b.dataset.capwhere === where; b.classList.toggle("on", sel); b.setAttribute("aria-checked", sel); });
    $("#mo-capnow", m).textContent = on ? "Look: " + String((meta && meta.label) || k).split(" · ")[0] : "";
    $("#mo-caplook", m).style.display = on ? "" : "none";
    $("#mo-capgrid", m).style.display = on && lookOpen ? "" : "none";
    $("#mo-caplook", m).textContent = lookOpen ? "Done" : "Change look";
    m.querySelectorAll("#mo-cap-grid .cap-tile").forEach(b => { b.classList.toggle("on", b.dataset.k === k); b.classList.toggle("low", gaming && b.dataset.low === "1"); });
    $("#mo-cap-font", m).textContent = (meta ? (meta.font === meta.wanted ? "font: " + meta.font : `shown in ${meta.font} until ${meta.wanted} is in app/fonts`) : "")
      + (gaming && meta && meta.low ? " · sits at the bottom: gaming videos skip bottom captions" : "");
  };
  const capGrid = () => {   // one tile per preview PNG
    const list = CAP_META ? Object.values(CAP_META) : CAP_STYLES.map(([key, label]) => ({ key, label }));
    $("#mo-cap-grid", m).innerHTML = list.map(x => `<button type="button" class="cap-tile" data-k="${esc(x.key)}" data-low="${x.low ? 1 : 0}" title="${esc(x.label)}"><img src="captions/${esc(x.key)}.png" alt=""><span>${esc(x.label.split(" · ")[0])}</span></button>`).join("");
    m.querySelectorAll("#mo-cap-grid .cap-tile").forEach(b => b.onclick = e => { e.preventDefault(); $("#mo-cap-style", m).value = b.dataset.k; capSync(); });
    capSync();
  };
  m.querySelectorAll("[data-capwhere]").forEach(b => b.onclick = () => { $("#mo-cap-where", m).value = b.dataset.capwhere; capSync(); });
  $("#mo-caplook", m).onclick = () => { lookOpen = !lookOpen; capSync(); };
  capGrid(); CAP_READY.then(capGrid);
  if ($("#mo-when", m)) $("#mo-when", m).onchange = () => {
    const at = $("#mo-when", m).value === "at", inp = $("#mo-at", m);
    inp.style.display = at ? "" : "none";
    if (at && !inp.value) { const d = new Date(Date.now() + 3600e3), p = n => String(n).padStart(2, "0"); inp.value = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:00`; }
  };
  $("#mo-adddev", m).onkeydown = e => { if (e.key === "Enter") e.target.click(); };
  $("#mo-adddev", m).onclick = () => addDeviceWizard(name => {   // the new device shows up in the "on" list right away
    const sel = $("#mo-mach", m); if (!sel || [...sel.options].some(o => o.value === name)) return;
    sel.style.display = ""; const here = $(".mo-here", m); if (here) here.style.display = "none";   // one PC had no picker (kit): now there are two
    sel.insertBefore(new Option(machineName(name), name), [...sel.options].find(o => o.value === "Both") || null);
    if (![...sel.options].some(o => o.value === "Both")) sel.add(new Option("Both (first free)", "Both"));
    sel.value = name;
  });
  $("#mo-trim", m).onchange = sync; $("#mo-screen", m).onchange = sync; $("#mo-gfx", m).onchange = sync; $("#mo-gfx-type", m).onchange = sync; sync();
  return sync;
}
function readModeOpts(m) {
  const where = $("#mo-cap-where", m).value, style = $("#mo-cap-style", m).value;
  return { screen: $("#mo-screen", m).checked, trim_only: $("#mo-trim", m).checked, trim_speed: +$("#mo-speed", m).value, music: $("#mo-music", m).checked, privacy: $("#mo-priv", m).checked, claude: $("#mo-claude", m).checked, fillers: $("#mo-fill", m).value || null,
    captions: where === "off" ? { on: false, style } : { on: true, style, where },
    requests: $("#mo-req", m).value.trim(), music_style: $("#mo-mstyle", m).value || null,
    graphics: { on: $("#mo-gfx", m).checked && $("#mo-screen", m).checked, type: $("#mo-gfx-type", m).value, url: $("#mo-gfx-url", m).value.trim() || null,
      highlight: $("#mo-gfx-hl", m).value.split("|").map(x => x.trim()).filter(Boolean) },
    ...(($("#mo-when", m)) ? { machine: $("#mo-mach", m).value,
      build_at: $("#mo-when", m).value === "hold" ? "hold" : $("#mo-when", m).value === "at" && $("#mo-at", m).value ? $("#mo-at", m).value.replace("T", " ") : null } : {}) };
}

// ---------------------------------------------------------------- Add a device (user 2026-10-29: "an add device button for
// rendering ... it would have to walk them through it"). Its own layer over whatever is open (New Project is a modal itself).
// Steps: what it is -> Studio on the other PC -> Tailscale on both -> one admin command on the other PC -> name + test.
function addDeviceWizard(onAdded) {
  const el = document.createElement("div"); el.className = "devwiz"; el.setAttribute("role", "dialog"); el.setAttribute("aria-label", "Add a device");
  document.body.appendChild(el);
  let step = 0, info = null, kind = "Laptop";
  const close = () => el.remove();
  const cmd = () => info ? `Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0; Set-Service sshd -StartupType Automatic; Start-Service sshd; Add-Content -Force -Path "$env:ProgramData\\ssh\\administrators_authorized_keys" -Value '${info.pub}'; icacls "$env:ProgramData\\ssh\\administrators_authorized_keys" /inheritance:r /grant "Administrators:F" /grant "SYSTEM:F"` : "loading…";
  const STEPS = [
    () => `<h3>Add a device</h3><p>Another computer with Studio on it can build your videos while you keep working on this one. If it is off, this computer builds them instead.</p>
      <p><b>What is the other computer?</b></p><div class="seg">${["Laptop", "Desktop", "Other PC"].map(k => `<button type="button" class="${k === kind ? "on" : ""}" data-kind="${k}">${k}</button>`).join("")}</div>
      <p class="muted small">You need: the other computer (Windows), turned on and on the internet, and 10 minutes.</p>`,
    () => `<h3>1 · Put Studio on the ${esc(kind.toLowerCase())}</h3><p>Install Studio on the ${esc(kind.toLowerCase())} the same way you did here, <b>in the same folder</b>:</p>
      <div class="copyrow"><code>${esc(info ? info.studio : "…")}</code></div><p class="muted small">Open it once there so it can finish setting up, then come back here.</p>`,
    () => `<h3>2 · Connect both computers with Tailscale</h3><p>Tailscale is a free app that lets your computers find each other safely, from anywhere.</p>
      <ol><li>Install it on <b>this computer</b> and on the <b>${esc(kind.toLowerCase())}</b>: <a href="https://tailscale.com/download/windows" target="_blank" rel="noopener">tailscale.com/download</a></li>
      <li>Sign in on both with the <b>same</b> account.</li><li>On the ${esc(kind.toLowerCase())}, click the Tailscale icon by the clock and note its <b>name</b> (for example <code>msi</code>) or its address (<code>100.x.x.x</code>).</li></ol>`,
    () => `<h3>3 · Let this computer send it work</h3><p>On the <b>${esc(kind.toLowerCase())}</b>: open the Start menu, type <b>PowerShell</b>, right-click it and pick <b>Run as administrator</b>. Paste this and press Enter:</p>
      <div class="copyrow"><textarea readonly rows="4" id="dw-cmd">${esc(cmd())}</textarea><button type="button" class="primary" id="dw-copy">Copy</button></div>
      <p class="muted small">It turns on Windows' built-in remote login (OpenSSH) and lets only this computer in, with its own key. It takes about a minute.</p>`,
    () => `<h3>4 · Name it and test</h3>
      <div class="field"><label for="dw-name">Name it</label><input id="dw-name" value="${esc(kind === "Other PC" ? "" : kind)}" placeholder="Laptop"></div>
      <div class="field"><label for="dw-host">Its Tailscale name or address (step 2)</label><input id="dw-host" placeholder="msi  or  100.x.y.z"></div>
      <div class="field"><label for="dw-user">Its Windows user name</label><input id="dw-user" placeholder="the name you sign in to Windows with on it"></div>
      <div id="dw-msg" class="small" role="status"></div>`,
  ];
  const draw = () => {
    el.innerHTML = `<div class="devwiz-box"><div class="devwiz-steps">${STEPS.map((_, i) => `<i class="${i === step ? "on" : i < step ? "done" : ""}"></i>`).join("")}</div>
      <div class="devwiz-body">${STEPS[step]()}</div>
      <div class="row devwiz-foot"><button type="button" id="dw-x">Cancel</button><span class="grow"></span>${step ? `<button type="button" id="dw-back">Back</button>` : ""}
      <button type="button" class="primary" id="dw-next">${step === STEPS.length - 1 ? "Test and add" : step ? "Done, next" : "Start"}</button></div></div>`;
    $("#dw-x", el).onclick = close;
    if ($("#dw-back", el)) $("#dw-back", el).onclick = () => { step--; draw(); };
    el.querySelectorAll("[data-kind]").forEach(b => b.onclick = () => { kind = b.dataset.kind; draw(); });
    if ($("#dw-copy", el)) $("#dw-copy", el).onclick = async () => { try { await navigator.clipboard.writeText(cmd()); } catch (e) { await api("clipboard", { text: cmd() }).catch(() => {}); } toast("Copied: paste it on the " + kind.toLowerCase(), "ok"); };
    $("#dw-next", el).onclick = async () => {
      if (step < STEPS.length - 1) { step++; draw(); return; }
      const b = $("#dw-next", el), msg = $("#dw-msg", el); b.disabled = true; b.textContent = "Testing…"; msg.className = "small"; msg.textContent = "Connecting to it (up to 30 s)…";
      try {
        const r = await api("devices/add", { name: $("#dw-name", el).value, host: $("#dw-host", el).value, user: $("#dw-user", el).value });
        toast(`${r.device.name} added: it can build your videos now`, "ok"); close(); refresh(true); if (onAdded) onAdded(r.device.name);
      } catch (e) { msg.className = "small bad"; msg.textContent = e.message; b.disabled = false; b.textContent = "Test and add"; }
    };
    const first = el.querySelector(".devwiz-body input, .devwiz-body button, #dw-next"); if (first) first.focus();
  };
  el.onkeydown = e => { if (e.key === "Escape") { e.stopPropagation(); close(); } };
  draw();
  api("devices/key").then(r => { info = r; draw(); }).catch(e => toast(e.message, "bad"));
}

// ---------------------------------------------------------------- New project (ordered multi-select of recordings, VO list, B-roll list)
// the type cards (approved mockup home screen, 2026-10-29) + the general type: a kit user's touchscreen-laptop talk came back
// "don't know" and the old "gaming" default gave it Minecraft wipes. "other" is not a Studio type of its own: it is built as a
// phone-type project on the screen-recording / trim-only edit (recipes/trim.py, as "apple home lg" + chime), so no channel or game graphics.
const TYPE_CARDS = [
  { id: "review", icon: "📦", name: "Product review", phrase: "a product review", desc: "You talking about a product, with a camera on the item.", ex: "e.g. “Best DHgate sneakers”" },
  { id: "phone", icon: "📱", name: "App / phone tutorial", phrase: "an app / phone tutorial", desc: "Screen recording of a phone or app with your voice.", ex: "e.g. “Uber Eats promo code”" },
  { id: "gaming", icon: "⛏", name: "Gaming / Top 10", phrase: "a gaming video", desc: "Gameplay with a ranked list or showcase.", ex: "e.g. “Top 5 Minecraft realms”" },
  { id: "short", icon: "📲", name: "Short (vertical)", phrase: "a Short", desc: "A 9:16 clip for Shorts, TikTok or Reels.", ex: "e.g. “What is a lift kit?”" },
  { id: "other", icon: "💬", name: "Talking / tech review / other", phrase: "a talking / tech video", desc: "Anything else: you talking about a gadget, news or a website. A clean trim with a calm music bed, no game or channel graphics.", ex: "e.g. “The new touchscreen MacBook”" },
];
// the user's own saved styles (my_style.js "Train your style"); a leftover test one ("Test style - delete me") is never offered
// (user 2026-10-29 13:43: a screen recording came back as that test style, "I don't know what that even means")
const myCards = () => Object.fromEntries(Object.entries(window.MY_CARDS || {}).filter(([, c]) => !/\b(test|delete|tmp|temp|scratch)\b/i.test(c.name)));
const EXTRA_CARDS = { haul: { id: "haul", icon: "🛍", name: "Haul", phrase: "a haul", desc: "One long phone recording, many products back to back.", ex: "e.g. “30kg DHgate haul”" } };
function newProjectModal(prefill = {}) {
  const types = S.state.types, chans = S.state.settings.channels;
  const picked = { main: [].concat(prefill.main || []).filter(Boolean), intro: "", intro_vo: "", broll: [] };
  // no video yet = the general type, never gaming (a wrong guess there is the Minecraft template)
  let type = prefill.type || "other", recent = { recordings: [], vo: [] };
  const card = id => TYPE_CARDS.find(c => c.id === id) || EXTRA_CARDS[id] || myCards()[id] || (types[id] ? { id, icon: types[id].icon, name: types[id].label, phrase: types[id].label, desc: types[id].blurb || "", ex: "" } : null);
  // video first (user 2026-10-21: "I don't see just add video, I see the three types"): pick the recording(s), the detect
  // chip sets the type; the type is only a small override select
  const m = modal(`<h2>New project</h2>
    <div class="np-sec"><div class="row" style="justify-content:space-between;align-items:center"><h3 style="margin:0">1 · Add your video <span class="dim" id="np-main-count"></span></h3>
        <span class="row" style="gap:10px"><span class="muted tiny">or click your recent recordings below (several = joined in that order)</span><button class="primary" id="np-add-video">＋ Add video</button></span></div>
      <div class="recent six" id="np-recent"><span class="muted small">loading…</span></div>
      <div class="sel-strip" id="np-sel"></div></div>
    <div class="np-detect" id="np-detect" style="display:none"></div>
    <div class="row np-basics">
      <div class="field grow" style="margin:0"><label for="np-title">Title</label><input id="np-title" placeholder="filled in from your intro once a video is added" value="${esc(prefill.title || "")}"></div>
      <div class="field" style="margin:0"><label for="np-type">Type</label><select id="np-type">${Object.entries(types).map(([k, v]) => `<option value="${k}" ${k === type ? "selected" : ""}>${esc(v.icon)} ${esc(v.label)}</option>`).join("")}<option value="other" ${type === "other" ? "selected" : ""}>💬 Talking / tech review / other</option>${Object.values(myCards()).length ? `<optgroup label="Your saved styles (learned from your own videos)">${Object.values(myCards()).map(c => `<option value="${esc(c.id)}">✨ ${esc(c.name)}</option>`).join("")}</optgroup>` : ""}</select></div>
    </div>
    ${modeOptsHtml({}, type, `<div class="row np-more-row">
      <div class="field" style="margin:0"><label for="np-ch">Channel</label><select id="np-ch">${chans.map(c => `<option ${c.types.includes(type) ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></div>
      <div class="field" style="margin:0"><label for="np-due">Due</label><input id="np-due" type="date"></div></div>`,
    `<div class="mo-row"><label class="mo-lbl" for="np-vo-sel">Intro voice</label><select id="np-vo-sel" class="np-vo-sel"></select><span class="muted tiny" id="np-vo-why"></span></div>
    <div class="mo-row"><span class="mo-lbl">B-roll</span><span class="muted small" id="np-broll-hint"></span><button type="button" class="sm" id="np-broll-browse">＋ Add clips</button><span class="np-broll-list" id="np-broll-list"></span></div>`)}
    <div class="row" style="justify-content:flex-end;margin-top:14px"><button id="np-cancel">Cancel</button><button class="primary big" id="np-create">Create project</button></div>`, "wide");
  const syncOpts = wireModeOpts(m, () => type);
  const hint = () => { $("#np-broll-hint", m).textContent = type === "gaming" ? "picked for you from the pink Director flashes in your recording" : picked.broll.length ? "" : "picked for you; add your own clips if you have them"; };
  const renderMain = () => {
    $("#np-recent", m).innerHTML = recent.recordings.map(i => { const n = picked.main.indexOf(i.path); return `<div class="re ${n >= 0 ? "sel" : ""} ${i.used ? "used" : ""}" data-p="${esc(i.path)}" title="${esc(i.path)}">
        ${n >= 0 ? `<span class="order">${n + 1}</span>` : ""}<div class="rth" style="background-image:url('${thumbUrl(i.path, null, Math.max(2, Math.round(i.duration * 0.3)), 640)}')"><span class="dur">${fmtT(i.duration)}</span></div>
        <b>${esc(i.label || i.name)}</b><small>${esc(i.name)} · ${fmtSize(i.size)} · ${new Date(i.mtime * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}${i.broll ? " · B-roll ✓" : ""}${i.used ? " · in a project" : ""}</small>
        <div class="re-acts"><button class="sm" data-ren="${esc(i.path)}" title="rename the file (and its .mkv twin)">rename</button></div></div>`; }).join("");
    $$("#np-recent .re", m).forEach(el => el.onclick = e => { if (e.target.closest("button")) return; toggleMain(el.dataset.p); });
    $$("#np-recent [data-ren]", m).forEach(b => b.onclick = async e => { e.stopPropagation(); const i = recent.recordings.find(x => x.path === b.dataset.ren); const name = prompt("New file name (no extension):", (i.label || "").replace(/[<>:"/\\|?*]/g, "").slice(0, 60) || i.name.replace(/\.[^.]+$/, "")); if (!name) return; try { const r = await api("recent/rename", { path: i.path, name }); toast("Renamed", "ok"); const k = picked.main.indexOf(i.path); if (k >= 0) picked.main[k] = r.path; recent = await api("recent"); renderMain(); } catch (err) { toast(err.message, "bad"); } });
    const n = picked.main.length; $("#np-main-count", m).textContent = n > 1 ? `${n} clips, joined in this order` : "";
    renderSel(); detectType(); autoVo();
  };
  // ---- auto-detect: the first recording decides the type; the chip asks for one click to confirm
  let detFor = "", det = null, userPicked = !!prefill.type, userTitled = !!prefill.title;
  const setType = t => {
    type = t; $("#np-type", m).value = t;
    // the general type is the full-screen trim edit: tick Screen recording (a side-by-side one gets Trim only at Create)
    const sc = $("#mo-screen", m); if (t === "other" && sc) { sc.checked = det ? det.screen !== false : true; sc.onchange(); }
    const mc = myCards()[t];   // a custom video type (my_style.js): its base type's channel
    const ch = (t === "other" || (mc && mc.vtype === "phone")) ? chans.find(c => c.types.includes("phone")) : mc && chans.find(c => c.types.includes(mc.vtype)); if (ch) $("#np-ch", m).value = ch.name;   // it builds as a phone-type project
    hint(); syncOpts();
  };
  // detect result as one plain sentence + "change?"; when the detector isn't sure (or the user asks to change) the type cards
  let cardsOpen = false;
  const pickCard = t => { userPicked = true; cardsOpen = false; setType(t); const c = chans.find(c => c.types.includes(t)); if (c) $("#np-ch", m).value = c.name; applyChannel(); renderChip(); };
  const renderChip = () => {
    const el = $("#np-detect", m); if (!el || !det) return;
    const r = det, unsure = !card(r.type) || r.confidence === "low";
    const why = `${(r.reasons || []).map(esc).join(" · ")}${r.title ? ` · title from the intro: “${esc(r.title)}”` : ""}`;
    if (cardsOpen || (unsure && !userPicked)) {
      const list = TYPE_CARDS.filter(c => c.id === "other" || types[c.id]);
      list.splice(list.length - 1, 0, ...Object.values(myCards()));   // the user's own video types (my_style.js)
      for (const id of [r.type, r.guess, type]) if (id && !list.some(c => c.id === id) && card(id)) list.splice(list.length - 1, 0, card(id));
      const hintId = unsure ? r.guess : r.type;
      el.className = "np-detect ask";
      el.innerHTML = `<div class="grow"><div><b>What kind of video is it?</b> <span class="muted tiny">${unsure ? "couldn't tell for sure from the recording, pick the closest one" : "pick the one that fits"}</span></div>
        ${why ? `<div class="muted tiny">${why}</div>` : ""}
        <div class="np-cards">${list.map(c => `<button type="button" class="np-card ${c.id === type ? "on" : ""}" data-t="${esc(c.id)}"><b>${esc(c.icon)} ${esc(c.name)}${c.id === hintId ? ` <span class="pill">${unsure ? "closest match" : "detected"}</span>` : ""}</b><span>${esc(c.desc)}</span>${c.ex ? `<small>${esc(c.ex)}</small>` : ""}</button>`).join("")}</div></div>`;
      $$("#np-detect .np-card", m).forEach(b => b.onclick = () => pickCard(b.dataset.t));
      return;
    }
    const cur = card(type) || { icon: "", name: type, phrase: type, desc: "" }, mine = type !== r.type;
    el.className = "np-detect " + (mine ? "medium" : r.confidence);
    el.innerHTML = `<span class="ic">${esc(cur.icon)}</span><div class="grow"><div>${mine ? `You picked <b>${esc(cur.phrase)}</b>` : `Looks like <b>${esc(cur.phrase)}</b>`}${!mine && r.channel ? ` · ${esc(r.channel)}` : ""} — <a id="np-det-change">change?</a></div>
      <div class="muted tiny">${esc(cur.desc)}${why ? ` · ${why}` : ""}</div></div>
      <button class="primary" id="np-det-go">Start ${esc(cur.icon)} ${esc(cur.name)} ▸</button>`;
    $("#np-det-go", m).onclick = () => $("#np-create", m).click();
    $("#np-det-change", m).onclick = () => { cardsOpen = true; renderChip(); };
  };
  const applyChannel = () => { const opt = det && [...$("#np-ch", m).options].find(o => o.value === det.channel); if (opt && det.type === type) $("#np-ch", m).value = det.channel; };
  const detectType = async () => {
    const p = picked.main[0], el = $("#np-detect", m); if (!el) return;
    if (!p) { detFor = ""; det = null; el.style.display = "none"; return; }
    if (p === detFor) return;
    detFor = p; det = null; el.style.display = ""; el.className = "np-detect busy";
    el.innerHTML = `<span class="spin"></span><div class="grow">Checking your video…</div>`;
    const apply = r => {
      det = r;
      if (r.type && !userPicked) { setType(r.type); applyChannel(); }
      // the user's own saved style only when it clearly fits: same kind of video, a camera layout it was trained on that this
      // recording has, and a sure answer (a style with no layout used to "fit" every talking video)
      const mine = myCards();
      const myFit = (r.my_types || []).find(x => mine["my:" + x.slug] && x.layout && r.camera === x.layout && r.confidence === "high");
      if (myFit && !userPicked) { det = { ...r, type: "my:" + myFit.slug, guess: r.type }; setType(det.type); }
      if (r.title && !userTitled) { $("#np-title", m).value = r.title; autoVo(); }
      // plain 16:9 capture with no cam = screen recording (user 2026-10-22: the detector must catch these)
      const sc = $("#mo-screen", m); if (sc && r.screen !== undefined && r.type !== "gaming") { sc.checked = !!r.screen; sc.onchange(); }
      renderChip();
    };
    try {
      // the picture + file name answer first (~1-3 s). A sure answer is the end of it (user 2026-10-29 13:43: "why did it
      // just keep going"); only an unsure one listens to the opening, and a medium one is checked quietly in the background
      const q = await api("detect?quick=1&path=" + enc(p));
      if (detFor !== p || !$("#np-detect")) return;
      if (!q.quick || q.confidence === "high") return apply(q);
      if (q.confidence === "medium") apply(q);
      const r = await api("detect?path=" + enc(p));
      if (detFor !== p || !$("#np-detect")) return;
      apply(r);
    } catch (e) { if (detFor === p) { det = { type: null, confidence: "low", reasons: ["could not check this file: " + e.message] }; renderChip(); } }
  };
  const info = {};   // path -> {duration,label} for clips that came from browse
  const addFiles = async () => { const ps = await pickFiles("video", true); for (const p of ps) { if (!picked.main.includes(p)) { picked.main.push(p); api("probe?path=" + enc(p)).then(r => { info[p] = r; renderSel(); }).catch(() => {}); } } if (ps.length && !$("#np-title", m).value) $("#np-title", m).value = base(ps[0]).replace(/\.[^.]+$/, ""); renderMain(); };
  const renderSel = () => {
    const el = $("#np-sel", m); if (!el) return;
    const tiles = picked.main.map((p, i) => { const r = recent.recordings.find(x => x.path === p) || info[p] || {}; return `<div class="sel-tile" draggable="true" data-i="${i}" title="${esc(p)}"><span class="order">${i + 1}</span><div class="rth" style="background-image:url('${thumbUrl(p, null, Math.max(2, Math.round((r.duration || 10) * 0.3)), 320)}')"><span class="dur">${r.duration ? fmtT(r.duration) : "…"}</span></div><b>${esc(r.label && !r.label.startsWith("(") ? r.label : base(p))}</b><i class="x" data-x="${i}">✕</i></div>`; });
    if (!picked.main.length) { el.style.display = "none"; return; }
    el.style.display = "";
    el.innerHTML = `<div class="muted tiny" style="width:100%">${picked.main.length === 1 ? "Selected clip" : `${picked.main.length} clips, joined in this order — drag to reorder`}:</div>` + tiles.join("");
    $$("#np-sel [data-x]", m).forEach(x => x.onclick = e => { e.stopPropagation(); picked.main.splice(+x.dataset.x, 1); renderMain(); });
    let drag = null;
    $$("#np-sel .sel-tile", m).forEach(t => {
      t.ondragstart = e => { drag = +t.dataset.i; e.dataTransfer.effectAllowed = "move"; t.classList.add("dragging"); };
      t.ondragend = () => t.classList.remove("dragging");
      t.ondragover = e => { e.preventDefault(); e.stopPropagation(); t.classList.add("over"); };
      t.ondragleave = () => t.classList.remove("over");
      t.ondrop = e => { e.preventDefault(); e.stopPropagation(); t.classList.remove("over"); const to = +t.dataset.i; if (drag == null || drag === to) return; const [mv] = picked.main.splice(drag, 1); picked.main.splice(to, 0, mv); drag = null; renderMain(); };
    });
  };
  const toggleMain = p => { const k = picked.main.indexOf(p); if (k >= 0) picked.main.splice(k, 1); else picked.main.push(p); if (!$("#np-title", m).value && picked.main.length) { const i = recent.recordings.find(x => x.path === picked.main[0]); $("#np-title", m).value = (i && i.label && !i.label.startsWith("(")) ? i.label.replace(/[<>:"/\\|?*]/g, "").slice(0, 70) : base(picked.main[0]).replace(/\.[^.]+$/, ""); } renderMain(); };
  // intro voice-over: one select, picked for you when a take's name shares the video's words ("dhgate moncler.wav" for "Best
  // Moncler on DHgate"), or a take recorded within a day of the video; the user only changes it when it's wrong
  let voAuto = true;
  const STOPW = new Set(["the", "and", "for", "with", "best", "review", "video", "from", "this", "that", "intro", "final", "part", "wav", "mp3", "mp4", "new"]);
  const words = t => new Set(String(t || "").toLowerCase().replace(/\.[a-z0-9]+$/, "").split(/[^a-z0-9]+/).filter(w => w.length >= 3 && !STOPW.has(w) && !/^\d+$/.test(w)));
  const autoVo = () => {
    if (!voAuto || picked.intro) return;
    const rec = recent.recordings.find(x => x.path === picked.main[0]);
    const want = new Set([...words($("#np-title", m).value), ...words(base(picked.main[0] || "")), ...words(rec && rec.label)]);
    let best = null, bs = 0;
    for (const v of recent.vo) {
      const shared = [...words(v.name)].filter(w => want.has(w)).length;
      const near = rec && Math.abs(v.mtime - rec.mtime) < 36 * 3600 ? 1 : 0;
      const sc = shared * 2 + near;
      if (sc > bs && (shared >= 2 || (shared >= 1 && near))) { best = v; bs = sc; }
    }
    picked.intro_vo = best ? best.path : "";
    renderVo(best ? "picked for you: it matches this video" : "");
  };
  const renderVo = why => {
    const sel = $("#np-vo-sel", m); if (!sel) return;
    const cur = picked.intro || picked.intro_vo;
    const extra = cur && !recent.vo.some(v => v.path === cur) ? [{ path: cur, name: base(cur) }] : [];
    sel.innerHTML = `<option value="">No intro voice-over</option>` + [...extra, ...recent.vo].map(v => `<option value="${esc(v.path)}" ${v.path === cur ? "selected" : ""}>🎙 ${esc(v.name)}${v.duration ? ` · ${fmtT(v.duration)}` : ""}</option>`).join("") + `<option value="__browse">Browse for another file…</option>`;
    if (why !== undefined) $("#np-vo-why", m).textContent = why;
  };
  const renderBroll = () => { $("#np-broll-list", m).innerHTML = picked.broll.map((p, i) => `<span class="np-chip">${esc(base(p))}<button type="button" data-bx="${i}" aria-label="remove ${esc(base(p))}">✕</button></span>`).join(""); $$("#np-broll-list [data-bx]", m).forEach(b => b.onclick = () => { picked.broll.splice(+b.dataset.bx, 1); renderBroll(); }); hint(); };
  hint();
  $("#np-type", m).onchange = e => { userPicked = true; setType(e.target.value); const c = chans.find(c => c.types.includes(type)); if (c) $("#np-ch", m).value = c.name; applyChannel(); renderChip(); };
  $("#np-add-video", m).onclick = () => addFiles();
  $("#np-title", m).addEventListener("input", () => { userTitled = true; });
  $("#np-vo-sel", m).onchange = async e => {
    voAuto = false; const v = e.target.value;
    if (v === "__browse") { const ps = await pickFiles("media", false); if (ps[0]) { if (/\.(wav|mp3|m4a|flac)$/i.test(ps[0])) { picked.intro_vo = ps[0]; picked.intro = ""; } else { picked.intro = ps[0]; picked.intro_vo = ""; } } renderVo(""); return; }
    picked.intro_vo = v; picked.intro = ""; renderVo("");
  };
  $("#np-broll-browse", m).onclick = async () => { const ps = await pickFiles("video", true); picked.broll.push(...ps.filter(p => !picked.broll.includes(p))); renderBroll(); };
  const load = async () => { recent = await api("recent"); renderMain(); renderVo(); autoVo(); };
  load();
  const sig = r => JSON.stringify([r.recordings.map(x => [x.path, x.label]), r.vo.map(x => x.path)]);
  const refreshLists = async () => { const r = await api("recent"); if (sig(r) !== sig(recent)) { recent = r; renderMain(); renderVo(); autoVo(); } };
  const relabel = setInterval(() => { if (!$("#np-recent")) return clearInterval(relabel); refreshLists().catch(() => {}); }, 5000);
  $("#np-cancel", m).onclick = () => { clearInterval(relabel); closeModal(); };
  $("#np-create", m).onclick = async () => {
    const title = $("#np-title", m).value.trim(); if (!title) return toast("Give it a title", "bad");
    const b = $("#np-create", m); b.disabled = true; b.textContent = picked.main.length > 1 ? "Joining recordings…" : "Creating…";
    try {
      const files = {}; if (picked.main.length) files.main = picked.main; if (picked.intro) files.intro = picked.intro; if (picked.intro_vo) files.intro_vo = picked.intro_vo; if (picked.broll.length) files.broll = picked.broll;
      const settings = readModeOpts(m);
      // general type = a phone-type project on the trim path: full-screen screen-recording edit, or Trim only for a side-by-side
      if (type === "other") { settings.general = true; if (!settings.screen && !settings.trim_only) settings.trim_only = true; }
      const myc = myCards()[type]; if (myc) settings.my_type = myc.slug;   // custom video type: the server adds its settings
      const p = await api("projects", { title, type: myc ? myc.vtype : type === "other" ? "phone" : type, channel: $("#np-ch", m).value, due: $("#np-due", m).value, files, settings });
      clearInterval(relabel); closeModal(); await refresh(true); nav("project", p.id); toast("Project created", "ok");
    } catch (e) { toast(e.message, "bad"); b.disabled = false; b.textContent = "Create project"; }
  };
}

// ---------------------------------------------------------------- Editor (Gling-style: player + timeline + transcript with cuts)
const ED = { data: null, playing: "", sel: null };
function tOut(t) { // raw -> timeline time of the file being played
  const d = ED.data; if (ED.playing === d.source || !d.keep.length) return t;
  let acc = d.offset; for (const [a, b] of d.keep) { if (t < a) return acc; if (t <= b) return acc + (t - a); acc += b - a; } return acc;
}
function tRaw(t) { // timeline -> raw
  const d = ED.data; if (ED.playing === d.source || !d.keep.length) return t;
  let acc = d.offset; if (t < acc) return null;
  for (const [a, b] of d.keep) { if (t <= acc + (b - a)) return a + (t - acc); acc += b - a; } return null;
}
function inKeep(t) { const d = ED.data; if (!d.keep.length) return true; return d.keep.some(([a, b]) => t >= a - 0.02 && t <= b + 0.02); }
async function renderEditor(p) {
  const body = $("#tabbody"); body.innerHTML = `<div class="muted">loading the transcript…</div>`;
  try { ED.data = await api("editor?id=" + p.id); } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  const d = ED.data;
  const outs = d.outputs || [];
  const choices = [...outs.map(o => ({ label: o.kind.toUpperCase() + " · " + base(o.file), file: o.file })), ...(d.source ? [{ label: "RAW recording", file: d.source }] : [])];
  // only this project's own files: ED.playing is global, so a file left over from another project must never carry over
  const norm = f => String(f || "").replace(/\//g, "\\").toLowerCase(), home = norm(p.path).replace(/\\?$/, "\\");
  const mine = f => !!f && norm(f).startsWith(home);
  if (!mine(ED.playing)) ED.playing = "";
  const files = outs.map(o => o.file), newest = files.length ? files[files.length - 1] : d.source || "";
  if (ED.pid === p.id && ED.seen && files.some(f => !ED.seen.includes(f))) ED.playing = newest;   // a build just finished: show the new render
  ED.pid = p.id; ED.seen = files;
  if (ED.playing && /draft v\d+/i.test(ED.playing) && !choices.some(c => c.file === ED.playing)) choices.unshift({ label: "OLDER · " + base(ED.playing), file: ED.playing });
  if (!ED.playing || !choices.some(c => c.file === ED.playing)) ED.playing = newest;
  const dur = d.duration || 1;
  const SEC_COL = ["#5bd97a", "#3ec6ff", "#ffb13d", "#c9a6ff", "#ff6b6b", "#7c9cff", "#5bd9c9", "#ffd166"];
  const secBars = (d.sections || []).map((s, i) => `<div class="tl-sec" style="left:${(s[1] / dur) * 100}%;width:${((s[2] - s[1]) / dur) * 100}%;background:${SEC_COL[i % SEC_COL.length]}" title="${esc(s[0])} ${fmtT(s[1])}–${fmtT(s[2])}"><span>${esc(s[0])}</span></div>`).join("");
  const keepBars = d.keep.filter(([a]) => a >= 0).map(([a, b]) => `<div class="tl-keep" style="left:${(a / dur) * 100}%;width:${Math.max(0.1, ((b - a) / dur) * 100)}%"></div>`).join("");
  const noteBars = (d.notes || []).filter(n => n.raw0 != null && !n.done).map(n => `<div class="tl-note ${n.kind}" style="left:${(n.raw0 / dur) * 100}%;width:${Math.max(0.15, ((n.raw1 - n.raw0) / dur) * 100)}%" title="${esc(n.text)}"></div>`).join("");
  let html = "", para = [], last = 0;
  const flush = () => { if (para.length) { html += `<p class="tr-p">${para.join(" ")}</p>`; para = []; } };
  d.words.forEach((w, i) => {
    if (i && (w.s - last > 1.5 || (d.words[i - 1].w.endsWith(".") && para.length > 40))) flush();
    const cut = !inKeep((w.s + w.e) / 2);
    para.push(`<span class="wd ${cut ? "cut" : ""}" data-i="${i}" data-s="${w.s}" data-e="${w.e}">${esc(w.w)}</span>`);
    last = w.e;
  });
  flush();
  const kept = d.keep.reduce((a, [x, y]) => a + (y - x), 0);
  body.innerHTML = `<div class="editor">
    <div class="ed-left">
      <div class="row" style="margin-bottom:6px"><select id="ed-src">${choices.map(c => `<option value="${esc(c.file)}" ${c.file === ED.playing ? "selected" : ""}>${esc(c.label)}</option>`).join("")}</select>
        <span class="muted tiny grow">raw ${fmtT(dur)} → kept ${fmtT(kept)} in ${d.keep.length} pieces${d.offset ? ` · intro ${d.offset.toFixed(1)} s` : ""}</span>
        <label class="tiny muted" title="when playing the raw recording, jump over everything the cutter removed"><input type="checkbox" id="ed-skip" ${ED.skip !== false ? "checked" : ""}> skip cuts</label>
        <button class="sm" id="ed-full" title="full-screen editor (Esc to leave)">⛶ Full screen</button>
        <button class="sm" id="ed-rebuild" title="apply the notes and rebuild the draft">▶ Rebuild draft</button></div>
      ${ED.playing ? `<video id="ed-video" controls preload="metadata" src="${mediaUrl(ED.playing)}"></video>` : `<div class="empty">no footage</div>`}
      <div class="tl" id="ed-tl" title="click to seek (raw recording time)"><div class="tl-secs">${secBars}</div><div class="tl-keeps">${keepBars}</div><div class="tl-notes">${noteBars}</div><div class="tl-head" id="ed-head"></div></div>
      <div class="row tiny muted" style="margin-top:4px"><span><i class="lg keep"></i> kept</span><span><i class="lg cutlg"></i> cut by the cutter</span><span><i class="lg note"></i> your notes (next build)</span><span class="grow"></span><span id="ed-time">0:00</span></div>
      ${(d.shorts || []).length ? `<div class="ed-shorts"><h3 style="margin:10px 0 6px">Shorts <span class="dim">${d.shorts.length}</span></h3><div class="list">${d.shorts.map(x => `<div class="item" data-openf="${esc(x.file)}"><span class="pill">9:16</span><span class="t">${esc(x.name)}</span><span class="muted tiny">${fmtT(x.duration)} · ${fmtSize(x.size)}</span></div>`).join("")}</div></div>` : ""}
      <div class="ed-cuts"><h3 style="margin:10px 0 6px">What the cutter removed <span class="dim">${d.cuts.length}</span></h3><div class="list" style="max-height:220px;overflow:auto">${d.cuts.slice(0, 300).map(c => `<div class="item" data-seek="${c.s}"><span class="pill">${esc((c.why || "").split(" ")[0])}</span><span class="t" title="${esc(c.text)}">${esc(c.text || c.why)}</span><span class="muted tiny">${fmtT2(c.s)}–${fmtT2(c.e)}</span></div>`).join("") || `<div class="empty small">no cut list yet (build once)</div>`}</div></div>
    </div>
    <div class="ed-right">
      <div class="row" style="margin-bottom:6px"><h2 style="margin:0">Transcript</h2><span class="muted tiny grow">click a word to seek · select words, then Cut / Protect</span>
        <div id="ed-selbar" class="row" style="gap:6px;display:none"><span class="tiny muted" id="ed-selinfo"></span><button class="sm danger" id="ed-cut">✂ Cut</button><button class="sm" id="ed-protect">🛡 Protect</button><button class="sm" id="ed-broll">🎞 B-roll here</button><button class="sm ok" id="ed-short">📱 Make Short</button></div></div>
      <div class="tr-body" id="ed-tr">${html || `<div class="empty">No transcript yet. Build the draft once (the transcript is the first step).</div>`}</div>
    </div></div>`;
  wireEditor(p);
  if (typeof editorExtras === "function") editorExtras(p);
}
function wireEditor(p) {
  const d = ED.data, v = $("#ed-video"), dur = d.duration || 1;
  $("#ed-src").onchange = e => { ED.playing = e.target.value; if (v) { v.src = mediaUrl(ED.playing); v.load(); } };
  $("#ed-rebuild").onclick = async () => { try { await api("project/run?id=" + p.id, { action: "draft" }); S.tab[p.id] = "pipeline"; await loadProject(); pollJobs(p.id); } catch (e) { toast(e.message, "bad"); } };
  const seekRaw = t => { if (!v) return; const o = tOut(t); if (o == null) return toast("That part is cut from the draft; switch to the RAW recording to hear it", ""); v.currentTime = Math.max(0, o); v.play().catch(() => {}); };
  $$(".wd").forEach(el => el.onclick = e => { if (window.getSelection().toString().trim()) return; seekRaw(+el.dataset.s); });
  $$("[data-seek]").forEach(el => el.onclick = () => seekRaw(+el.dataset.seek));
  $$(".ed-shorts [data-openf]").forEach(el => el.onclick = () => api("open", { path: el.dataset.openf }));
  $("#ed-tl").onclick = e => { const r = e.currentTarget.getBoundingClientRect(); seekRaw(((e.clientX - r.left) / r.width) * dur); };
  let cur = -1;
  $("#ed-skip").onchange = e => { ED.skip = e.target.checked; };
  $("#ed-full").onclick = () => { document.body.classList.toggle("edit-full"); $("#ed-full").textContent = document.body.classList.contains("edit-full") ? "✕ Exit full screen" : "⛶ Full screen"; };
  document.onkeydown = e => { if (e.key === "Escape" && document.body.classList.contains("edit-full")) { document.body.classList.remove("edit-full"); const b = $("#ed-full"); if (b) b.textContent = "⛶ Full screen"; } };
  const nextKeep = t => { for (const [a, b] of d.keep) { if (t < a) return a; if (t <= b) return null; } return -1; };
  if (v) v.ontimeupdate = () => {
    if (ED.skip !== false && ED.playing === d.source && d.keep.length && !v.paused) {   // raw recording: hop over the cut parts
      const nk = nextKeep(v.currentTime);
      if (nk === -1) { v.pause(); return; }
      if (nk !== null && nk - v.currentTime > 0.05) { v.currentTime = nk + 0.01; return; }
    }
    const raw = tRaw(v.currentTime); if (raw == null) return;
    $("#ed-head").style.left = (raw / dur * 100) + "%"; $("#ed-time").textContent = fmtT2(raw) + " raw";
    const ws = d.words; let lo = 0, hi = ws.length - 1, i = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (ws[mid].s <= raw) { i = mid; lo = mid + 1; } else hi = mid - 1; }
    if (i !== cur) { const old = $(`.wd[data-i="${cur}"]`); if (old) old.classList.remove("now"); const el = $(`.wd[data-i="${i}"]`); if (el) { el.classList.add("now"); const box = $("#ed-tr"); const top = el.offsetTop - box.offsetTop; if (top < box.scrollTop || top > box.scrollTop + box.clientHeight - 40) box.scrollTop = top - box.clientHeight / 2; } cur = i; }
  };
  const selInfo = () => {
    const sel = window.getSelection(); if (!sel || sel.isCollapsed) { const bar = $("#ed-selbar"); if (bar) bar.style.display = "none"; ED.sel = null; return; }
    const r = sel.getRangeAt(0); const tr = $("#ed-tr"); if (!tr || !tr.contains(r.commonAncestorContainer)) return;
    const words = $$(".wd", tr).filter(w => sel.containsNode(w, true)); if (!words.length) return;
    const s = +words[0].dataset.s, e = +words[words.length - 1].dataset.e;
    ED.sel = { s, e, text: words.map(w => w.textContent).join(" ") };
    $("#ed-selinfo").textContent = `${fmtT2(s)}–${fmtT2(e)} · ${words.length} words`; $("#ed-selbar").style.display = "flex";
  };
  document.onselectionchange = selInfo;
  const addNote = async (kind, extra = {}) => {
    if (!ED.sel) return; const { s, e, text } = ED.sel;
    const pad = kind === "cut" ? 0.05 : 0;
    try { S.project = await api("project/notes?id=" + p.id, { kind, raw0: Math.max(0, s - pad), raw1: e + pad, text: `${kind} ${fmtT2(s)}-${fmtT2(e)} “${text.slice(0, 60)}${text.length > 60 ? "…" : ""}”`, ...extra }); toast(kind + " noted for the next build", "ok"); window.getSelection().removeAllRanges(); keepVideo("#ed-video", () => renderEditor(p)); } catch (err) { toast(err.message, "bad"); }
  };
  $("#ed-cut").onclick = () => addNote("cut");
  $("#ed-protect").onclick = () => addNote("protect");
  $("#ed-broll").onclick = () => { const clip = prompt("Which B-roll clip? (part of its file name, or leave empty for the next auto clip)", ""); if (clip === null) return; addNote("broll", { clip }); };
  $("#ed-short").onclick = () => { if (!ED.sel) return; shortModal(p, ED.sel); };
  // keyboard: space play/pause · ←/→ 5 s · J/L 10 s · C cut · P protect · S skip-cuts · F full screen · Esc leave full screen
  document.onkeydown = e => {
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    if (e.key === "Escape" && document.body.classList.contains("edit-full")) { document.body.classList.remove("edit-full"); const b = $("#ed-full"); if (b) b.textContent = "⛶ Full screen"; return; }
    if (!$("#ed-tr")) return;
    const k = e.key.toLowerCase();
    if (k === " ") { e.preventDefault(); if (v) v.paused ? v.play() : v.pause(); }
    else if (k === "arrowright" || k === "l") { if (v) v.currentTime += k === "l" ? 10 : 5; }
    else if (k === "arrowleft" || k === "j") { if (v) v.currentTime -= k === "j" ? 10 : 5; }
    else if (k === "c" && ED.sel) addNote("cut");
    else if (k === "p" && ED.sel) addNote("protect");
    else if (k === "s") { const c = $("#ed-skip"); c.checked = !c.checked; ED.skip = c.checked; }
    else if (k === "f") $("#ed-full").click();
  };
  if (ED.seekTo != null && v) { const t = ED.seekTo; ED.seekTo = null; v.addEventListener("loadedmetadata", () => seekRaw(t), { once: true }); }
}

// ---------------------------------------------------------------- Thumbnails board (needed first, briefs for the designer, copy / copy all)
function thumbBriefText(x, n) {
  const refs = (x.refs || []).map(r => "   - " + r).join("\n");
  return `${n != null ? n + ". " : ""}${x.title}  [${x.channel || "no channel"} · ${S.state.types[x.type].label}${x.due ? " · due " + x.due : ""}]\n` +
    `   What the video is: ${x.brief ? "" : (x.opener || x.desc || "(no notes yet)")}${x.brief ? x.brief : ""}\n` +
    (x.brief && (x.opener || x.desc) ? `   Opening line: ${x.opener || x.desc}\n` : "") +
    (x.file ? `   Current thumbnail / frame: ${x.file}\n` : x.preview ? `   Footage to grab frames from: ${x.preview}\n` : "") +
    (refs ? `   References:\n${refs}\n` : "   References: (none yet)\n") +
    (x.youtube ? `   Video: ${x.youtube}\n` : "") + `   Project folder: ${x.path}\n`;
}
async function viewThumbs() {
  const main = $("#main");
  main.innerHTML = `<h1>Thumbnails</h1><p class="sub">Every video that still needs a thumbnail, first. Write the idea for your designer, drop references, grab a frame, then copy one or all.</p><div id="th-body" class="muted">loading…</div>`;
  const r = await api("thumbnails");
  const sort = S.thumbSort || "due";
  const sorter = (a, b) => sort === "due" ? (a.due || "9999").localeCompare(b.due || "9999") || a.title.localeCompare(b.title) : sort === "channel" ? (a.channel || "").localeCompare(b.channel || "") || (a.due || "9999").localeCompare(b.due || "9999") : sort === "stage" ? S.state.stages.indexOf(b.stage) - S.state.stages.indexOf(a.stage) : a.title.localeCompare(b.title);
  const rows = r.rows.slice().sort((a, b) => a.done - b.done || sorter(a, b));
  const need = rows.filter(x => !x.done), done = rows.filter(x => x.done);
  const row = (x, n) => `<div class="th-row ${x.done ? "done" : ""}" data-id="${x.id}">
      <div class="th-prev" style="background-image:${x.preview ? `url('${thumbUrl(x.preview, x.crop, null, 400)}')` : "none"}" title="click to grab a frame" data-grab="${x.id}">${n != null ? `<span class="order">${n}</span>` : ""}</div>
      <div class="th-info"><b data-open="${x.id}">${esc(x.title)}</b><div class="muted small"><span class="pill type-${x.type}">${esc(S.state.types[x.type].icon)}</span> ${esc(x.channel || "no channel")} · <span class="pill st-${x.stage}">${esc(S.state.stage_labels[x.stage])}</span> ${x.due ? ` · due <b class="${x.due < S.state.tracker.today && !["shipped", "published"].includes(x.stage) ? "bad" : ""}">${esc(x.due)}</b>` : " · no due date"}</div>
        ${x.opener || x.desc ? `<div class="muted tiny" style="margin-top:3px">“${esc(x.opener || x.desc)}”</div>` : ""}
        <textarea class="th-brief" data-brief="${x.id}" placeholder="Thumbnail idea for the designer: what's on it, the big text, the mood…">${esc(x.brief || "")}</textarea>
        <div class="th-refs">${(x.refs || []).map(f => `<span class="th-ref" style="background-image:url('${thumbUrl(f, null, null, 200)}')" title="${esc(f)}" data-openf="${esc(f)}"><i data-refx="${x.id}" data-f="${esc(f)}">✕</i></span>`).join("")}<button class="sm" data-addref="${x.id}">+ reference</button></div></div>
      <div class="th-acts"><button class="sm" data-copy="${x.id}">copy brief</button><button class="sm" data-grab="${x.id}" ${x.has_source ? "" : "disabled"}>grab frame</button><button class="sm" data-addf="${x.id}">add PNG…</button>${x.file ? `<button class="sm" data-openf="${esc(x.file)}">open</button>` : ""}<button class="sm ${x.done ? "" : "ok"}" data-done="${x.id}" data-v="${x.done ? 0 : 1}">${x.done ? "undo" : "✓ done"}</button></div></div>`;
  $("#th-body").innerHTML = `<div class="row" style="margin-bottom:12px"><span class="pill ${need.length ? "bad" : "st-final"}">${need.length} needed</span><span class="muted small">sort by</span>
      ${["due", "channel", "stage", "title"].map(k => `<button class="sm ${sort === k ? "primary" : ""}" data-sort="${k}">${k}</button>`).join("")}<span class="grow"></span>
      <button class="primary sm" id="th-copyall" ${need.length ? "" : "disabled"}>📋 Copy all briefs (${need.length})</button><button class="sm" id="th-export" ${need.length ? "" : "disabled"} title="also saves data\\thumbnails-brief.md">save as file</button></div>
    <div class="th-list">${need.map((x, i) => row(x, i + 1)).join("") || `<div class="empty">every project has a thumbnail 🎉</div>`}</div>
    ${done.length ? `<h3 style="margin:18px 0 8px">Done <span class="dim">${done.length}</span></h3><div class="th-list">${done.map(x => row(x)).join("")}</div>` : ""}`;
  const all = () => `THUMBNAILS NEEDED — ${S.state.tracker.today} (sorted by ${sort})\n\n` + need.map((x, i) => thumbBriefText({ ...x, brief: ($(`[data-brief="${x.id}"]`)?.value || x.brief) }, i + 1)).join("\n");
  $$("[data-sort]").forEach(b => b.onclick = () => { S.thumbSort = b.dataset.sort; viewThumbs(); });
  wireCommon();
  $$("[data-openf]").forEach(el => el.onclick = e => { e.stopPropagation(); api("open", { path: el.dataset.openf }).catch(e => toast(e.message, "bad")); });
  $$(".th-brief").forEach(t => t.onchange = async () => { await api("project/update?id=" + t.dataset.brief, { thumb_brief: t.value }); toast("Brief saved", "ok"); });
  $$("[data-copy]").forEach(b => b.onclick = async () => { const x = rows.find(y => y.id === b.dataset.copy); await api("clipboard", { text: thumbBriefText({ ...x, brief: $(`[data-brief="${x.id}"]`).value }) }); toast("Brief copied", "ok"); });
  $("#th-copyall").onclick = async () => { await api("clipboard", { text: all() }); toast(`${need.length} briefs copied — paste to your designer`, "ok"); };
  $("#th-export").onclick = async () => { const r2 = await api("thumbnails/export", { text: all() }); await api("clipboard", { text: all() }); toast("Saved " + r2.file + " (and copied)", "ok"); };
  const proj = async id => await api("project?id=" + id);
  $$("[data-grab]").forEach(b => b.onclick = async () => { const p = await proj(b.dataset.grab); S.project = p; S.pid = p.id; S.view = "thumbs"; frameGrabber(p); });
  $$("[data-addf]").forEach(b => b.onclick = async () => { const ps = await pickFiles("image", false); if (!ps[0]) return; await api("project/slot?id=" + b.dataset.addf, { slot: "thumbnail", files: ps }); toast("Thumbnail added", "ok"); viewThumbs(); });
  $$("[data-addref]").forEach(b => b.onclick = async () => { const ps = await pickFiles("image", true); if (!ps.length) return; await api("project/slot?id=" + b.dataset.addref, { slot: "thumb_ref", files: ps }); toast("Reference added", "ok"); viewThumbs(); });
  $$("[data-refx]").forEach(i => i.onclick = async e => { e.stopPropagation(); await api("project/slot/remove?id=" + i.dataset.refx, { slot: "thumb_refs", path: i.dataset.f }); viewThumbs(); });
  $$("[data-done]").forEach(b => b.onclick = async () => { await api("project/update?id=" + b.dataset.done, { checklist: { thumbnail: b.dataset.v === "1" } }); viewThumbs(); refresh(true); });
}

// ---------------------------------------------------------------- Ask Claude (per-project chat through the Claude Code CLI, Opus 5.5)
const CH = { poll: null };
function mdLite(t) {
  let h = esc(t);
  h = h.replace(/```([\s\S]*?)```/g, (m, c) => `<pre>${c.trim()}</pre>`).replace(/`([^`\n]+)`/g, "<code>$1</code>")
       .replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>").replace(/^(?:- |• )(.*)$/gm, "<li>$1</li>").replace(/(<li>.*<\/li>\n?)+/g, m => `<ul>${m}</ul>`)
       .replace(/\n{2,}/g, "<br><br>").replace(/\n/g, "<br>");
  return h;
}
async function renderChat(p) {
  const body = $("#tabbody");
  body.innerHTML = `<div class="chat">
    <div class="row" style="margin-bottom:8px"><h2 style="margin:0">Revisions</h2><span class="muted tiny grow" id="ch-status">Opus 5.5 through your Claude Code sign-in · Claude can edit this project, add notes and rebuild</span>
      <button class="sm" id="ch-login" title="sign the Claude Code CLI in (opens a terminal + browser)">Sign in</button><button class="sm" id="ch-reset" title="start a fresh conversation for this project">New chat</button></div>
    <div class="ch-log" id="ch-log"></div>
    <div class="row" style="margin-top:8px"><textarea id="ch-in" rows="2" placeholder="e.g. the #3 section starts too late, move it to 34:40 and rebuild · make the corner cam smaller · write the YouTube description" style="min-height:52px"></textarea><button class="primary" id="ch-send">Send</button></div>
    <div class="muted tiny" style="margin-top:4px">Enter = send · Shift+Enter = new line · revisions only; big new builds (intros, articles) still go through the main Claude app</div></div>`;
  const log = $("#ch-log");
  const draw = st => {
    const ms = st.transcript.messages || [];
    log.innerHTML = ms.map(m => m.role === "system" ? `<div class="ch-sys">${esc(m.text)}</div>` : `<div class="ch-msg ${m.role}"><div class="ch-who">${m.role === "user" ? "You" : "Claude"} <span class="dim">${esc(m.t || "")}${m.meta?.duration_ms ? " · " + Math.round(m.meta.duration_ms / 1000) + " s" : ""}</span></div><div class="ch-body">${m.role === "user" ? esc(m.text).replace(/\n/g, "<br>") : mdLite(m.text)}</div></div>`).join("")
      + (st.busy ? `<div class="ch-msg assistant thinking"><div class="ch-who">Claude</div><div class="ch-body">working… ${st.elapsed}s<span class="dots"></span></div></div>` : "") || `<div class="empty">Ask for a revision. Claude sees this project's files, transcript, notes and the studio API.</div>`;
    log.scrollTop = log.scrollHeight;
    $("#ch-send").disabled = st.busy;
    if (st.login_needed) $("#ch-status").innerHTML = `<span class="bad">Claude Code is not signed in on this PC — click Sign in, finish in the browser, then send again.</span>`;
  };
  const load = async () => { try { const st = await api("chat?id=" + p.id); draw(st); if (st.busy && !CH.poll) CH.poll = setInterval(async () => { if (S.view !== "project" || S.tab[p.id] !== "chat" || !$("#ch-log")) { clearInterval(CH.poll); CH.poll = null; return; } const s2 = await api("chat?id=" + p.id); draw(s2); if (!s2.busy) { clearInterval(CH.poll); CH.poll = null; refresh(true); } }, 2000); } catch (e) { log.innerHTML = `<div class="empty">${esc(e.message)}</div>`; } };
  const send = async () => { const t = $("#ch-in").value.trim(); if (!t) return; $("#ch-in").value = ""; try { draw(await api("chat/send?id=" + p.id, { text: t })); load(); } catch (e) { toast(e.message, "bad"); } };
  $("#ch-send").onclick = send;
  $("#ch-in").onkeydown = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } };
  $("#ch-login").onclick = async () => { await api("chat/login", {}); toast("A terminal opened: finish the sign-in in the browser, then come back", "ok"); };
  $("#ch-reset").onclick = async () => { if (confirm("Start a new conversation for this project?")) draw(await api("chat/reset?id=" + p.id, {})); };
  load();
}

// ---------------------------------------------------------------- Make a Short (9:16 from the selection)
function shortModal(p, sel) {
  const m = modal(`<h2>Make a Short</h2><p class="muted small">${fmtT2(sel.s)}–${fmtT2(sel.e)} of the recording (${(sel.e - sel.s).toFixed(0)} s) · “${esc(sel.text.slice(0, 90))}…”</p>
    <div class="field"><label>Name</label><input id="sh-name" placeholder="hook-dragonforge" value=""></div>
    <div class="field"><label>Crop (which part of the 16:9 frame becomes the 9:16)</label><div class="typepick"><div class="tp on" data-s="center"><b>Center</b><small>game / phone in the middle</small></div><div class="tp" data-s="left"><b>Left third</b><small>corner cam + left of the game, phone PiP</small></div><div class="tp" data-s="right"><b>Right third</b><small>right side of the frame</small></div></div></div>
    <p class="muted tiny">Cut from the best render (final, else draft), loudness -14 LUFS, 1080x1920 H.264. Lands in the project's Shorts folder.</p>
    <div class="row" style="justify-content:flex-end"><button id="sh-cancel">Cancel</button><button class="primary" id="sh-go">Render Short</button></div>`);
  let side = "center";
  $$(".tp", m).forEach(el => el.onclick = () => { side = el.dataset.s; $$(".tp", m).forEach(x => x.classList.toggle("on", x === el)); });
  $("#sh-cancel", m).onclick = closeModal;
  $("#sh-go", m).onclick = async () => { try { const r = await api("project/short?id=" + p.id, { raw0: sel.s, raw1: sel.e, side, name: $("#sh-name", m).value }); closeModal(); toast(`Rendering ${base(r.file)} (${(r.t1 - r.t0).toFixed(0)} s from ${base(r.from)})`, "ok"); pollJobs(p.id); } catch (e) { toast(e.message, "bad"); } };
}

// ---------------------------------------------------------------- QC report viewer (Review tab)
async function renderQC(p, el) {
  try {
    const r = await api("project/qc?id=" + p.id);
    if (!r.reports.length) { el.innerHTML = `<div class="empty small">No QC report yet (it runs at the end of every build).</div>`; return; }
    const rep = r.reports[r.reports.length - 1];
    el.innerHTML = `<div class="row" style="margin-bottom:6px"><h2 style="margin:0">QC check</h2><span class="muted tiny grow">${esc(rep.kind)} · ${esc(rep.when)} · ${esc(rep.info || "")}${rep.loudness ? " · " + esc(JSON.stringify(rep.loudness).slice(0, 60)) : ""}</span>
        ${Object.entries(rep.counts).map(([k, n]) => `<span class="pill ${k === "flash" || k === "repeat" ? "bad" : ""}">${esc(k)} ${n}</span>`).join("")}</div>
      ${rep.format_issues.length ? `<div class="small" style="color:var(--warn);margin-bottom:6px">${rep.format_issues.map(esc).join("<br>")}</div>` : ""}
      <div class="qc-list">${rep.flags.map((f, i) => `<div class="qc" data-i="${i}"><span class="pill ${f.type === "cover" || f.type === "brief" ? "" : "bad"}">${esc(f.type)}</span><a class="mono" data-qt="${f.t}">${fmtT2(f.t)}</a><span class="t small">${esc(f.note)}</span>${f.sheet ? `<a class="tiny" data-sheet="${esc(f.sheet)}">sheet</a>` : ""}</div>`).join("") || `<div class="empty small">0 flags 🎉</div>`}</div>
      <div id="qc-sheet"></div>`;
    $$("[data-qt]", el).forEach(a => a.onclick = () => { const v = $("#p-video"); if (v) { v.currentTime = +a.dataset.qt - 1.5; v.play().catch(() => {}); } });
    $$("[data-sheet]", el).forEach(a => a.onclick = () => { $("#qc-sheet", el).innerHTML = `<img src="/file?path=${enc(a.dataset.sheet)}" style="width:100%;border-radius:8px;margin-top:8px;border:1px solid var(--line2)">`; });
  } catch (e) { el.innerHTML = `<div class="empty small">${esc(e.message)}</div>`; }
}

// ---------------------------------------------------------------- global search across transcripts
async function searchModal(q) {
  const m = modal(`<h2>Search transcripts</h2><div class="row"><input id="sq" class="grow" placeholder="what did I say… (e.g. promo code, dragonforge)" value="${esc(q || "")}"><button class="primary" id="sgo">Search</button></div><div id="sres" class="list" style="margin-top:10px;max-height:60vh;overflow:auto"></div>`);
  const go = async () => { const qq = $("#sq", m).value.trim(); if (qq.length < 2) return; $("#sres", m).innerHTML = `<div class="muted small">searching…</div>`; const r = await api("search?q=" + enc(qq));
    $("#sres", m).innerHTML = r.hits.map(h => `<div class="item" data-id="${h.id}" data-t="${h.t}"><span class="pill type-${h.type}">${esc(S.state.types[h.type].icon)}</span><span class="t"><b>${esc(h.title)}</b> <span class="mono dim">${fmtT2(h.t)}</span><br><span class="small muted">…${esc(h.context)}…</span></span></div>`).join("") || `<div class="empty small">nothing found</div>`;
    $$("#sres .item", m).forEach(el => el.onclick = () => { closeModal(); ED.seekTo = +el.dataset.t; S.tab[el.dataset.id] = "editor"; nav("project", el.dataset.id); }); };
  $("#sgo", m).onclick = go; $("#sq", m).onkeydown = e => { if (e.key === "Enter") go(); }; $("#sq", m).focus();
  if (q) go();
}
document.addEventListener("keydown", e => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); searchModal(); } });

$("#btn-search").onclick = () => searchModal();

// ---------------------------------------------------------------- one drop zone for every kind of video (dashboard)
// Drop or pick a recording; the New Project screen works out gaming / phone / review and asks for one click (api detect).
document.head.insertAdjacentHTML("beforeend", `<style>
.np-detect{display:flex;align-items:center;gap:12px;padding:10px 14px;margin:0 0 12px;border-radius:var(--r);border:1px solid rgba(124,156,255,.5);background:#16233a}
.np-detect.high{border-color:rgba(91,217,122,.55);background:#15281d}.np-detect.low{border-color:rgba(255,177,61,.5);background:#2a2214}
.np-detect .ic{font-size:24px;line-height:1}.np-detect .grow{flex:1;min-width:0}
.np-detect .spin{width:18px;height:18px;border-radius:50%;border:2px solid var(--line2);border-top-color:var(--accent);animation:npspin .8s linear infinite;flex:none}
@keyframes npspin{to{transform:rotate(360deg)}}
#np-type.flash{outline:2px solid var(--accent);outline-offset:2px}
.np-detect.ask{align-items:flex-start;border-color:rgba(255,177,61,.5);background:#1d1a14}
.np-detect a#np-det-change{font-weight:600}
.np-cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px;margin-top:10px}
.np-card{display:flex;flex-direction:column;align-items:flex-start;gap:4px;min-height:92px;padding:12px;text-align:left;border-radius:var(--r2);border:2px solid var(--line);background:var(--bg2);cursor:pointer}
.np-card:hover{border-color:var(--line2)}.np-card.on{border-color:var(--accent);background:#16233a}
.np-card span{font-size:12.5px;color:var(--muted);line-height:1.4}.np-card small{font-size:11.5px;color:var(--dim)}
.drop-any{display:flex;align-items:center;gap:14px;text-align:left;padding:16px 18px;margin:0 0 18px;cursor:pointer;border:1.5px dashed var(--line2);border-radius:var(--r);background:var(--bg)}
.drop-any:hover,.drop-any.over{border-color:var(--accent);background:#16233a}
.drop-any .big{font-size:26px}.drop-any b{font-size:15px}
</style>`);
function addDropAny() {
  const main = $("#main"); if (!main || S.view !== "dashboard" || $("#drop-any")) return;
  const sub = main.querySelector(".sub"); if (!sub) return;
  sub.insertAdjacentHTML("afterend", `<div class="drop-any dropz" id="drop-any"><span class="big">⤓</span><div class="grow"><b>Drop a recording to start a video</b>
    <div class="muted small">Gaming, phone/app or product review: Studio listens to the intro, works out which one it is and you confirm with one click. Several clips = joined in drop order.</div></div><button class="sm">browse…</button></div>`);
  const z = $("#drop-any");
  const start = ps => { const vids = ps.filter(p => /\.(mp4|mov|mkv|m4v|xml)$/i.test(p)); if (!vids.length) return toast("Drop a video (MP4/MOV/MKV) or a Gling XML", "bad"); newProjectModal({ main: vids }); };
  z.onclick = async () => start(await pickFiles("video", true));
  z.ondragover = e => { e.preventDefault(); z.classList.add("over"); };
  z.ondragleave = () => z.classList.remove("over");
  z.ondrop = e => { e.preventDefault(); z.classList.remove("over"); const ps = dropPaths(e); if (!ps.length) return toast("Drag-and-drop paths need the desktop window; click to browse here", "bad"); start(ps); };
}
const _renderNoDrop = render;
render = async function () { await _renderNoDrop(); addDropAny(); };

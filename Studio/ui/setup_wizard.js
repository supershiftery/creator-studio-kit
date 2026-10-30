// First-run setup wizard (kit): one question per screen, inside the Studio window (server: app/setup_wizard.py).
// Opens by itself until setup is done; Settings -> Setup -> "Run setup again" opens it any time.
const WZ = { st: null, step: 0, a: {}, sug: null, checks: null, poll: null, el: null };
const WZ_STEPS = [
  ["welcome", "Welcome"], ["check", "Check your PC"], ["recordings", "Your recordings"], ["projects", "Your projects"],
  ["music", "Your music"], ["captions", "Captions"], ["channel", "Channel name"], ["done", "Done"]];
const WZ_CAP = [["all", "Whole video", "Words on screen the whole time you talk."],
  ["bookends", "Intro and ending only", "Captions on the first and last part, a clean picture in between."],
  ["off", "No captions", "Turn them on for a single project when you want them."]];
const wzHasMusic = () => typeof msFind === "function";
const wzWin = p => String(p || "").replace(/\//g, "\\");   // settings keep forward slashes; show Windows paths
const wzAgo = t => { if (!t) return ""; const d = (Date.now() / 1000 - t) / 86400; return d < 1 ? "today" : d < 2 ? "yesterday" : d < 60 ? `${Math.round(d)} days ago` : new Date(t * 1000).toLocaleDateString(); };

async function wzPickFolder(start) {
  if (inWindow()) { try { const r = await window.pywebview.api.pick_folder(); return r && r[0]; } catch (e) { console.warn(e); } }
  const r = await browseModal({ dirsOnly: true, multiple: false, start: start || "" });
  return r && r[0];
}

async function wzOpen(stepId) {
  try { WZ.st = await api("setup/wizard"); } catch (e) { return toast(e.message, "bad"); }
  const a = WZ.st.answers;
  WZ.a = { recordings: wzWin(a.recordings), projects_root: wzWin(a.projects_root), music_root: wzWin(a.music_root), captions: a.captions || "off",
           channel: a.channel || "", music_find: wzHasMusic() };
  WZ.step = Math.max(0, WZ_STEPS.findIndex(s => s[0] === (stepId || "welcome")));
  if (!WZ.el) { WZ.el = document.createElement("div"); WZ.el.id = "wz"; document.body.appendChild(WZ.el); }
  api("setup/wizard/suggest").then(s => { WZ.sug = s; wzDefaults(); if (["recordings", "projects", "music"].includes(WZ_STEPS[WZ.step][0])) wzDraw(); }).catch(() => {});
  wzDraw();
}

function wzClose() { clearInterval(WZ.poll); WZ.poll = null; if (WZ.el) WZ.el.remove(); WZ.el = null; }

function wzDefaults() {   // fill empty answers from what the server found on this PC
  const s = WZ.sug; if (!s) return;
  if (!WZ.a.recordings && s.recordings.length) WZ.a.recordings = s.recordings[0].path;
  if (!WZ.a.projects_root) WZ.a.projects_root = s.projects_root;
  if (!WZ.a.music_root) WZ.a.music_root = s.music.new;
}

function wzDraw() {
  const el = WZ.el; if (!el) return;
  const [id] = WZ_STEPS[WZ.step];
  const rail = WZ_STEPS.map(([k, label], i) => `<li class="${i < WZ.step ? "done" : i === WZ.step ? "on" : ""}" ${i === WZ.step ? 'aria-current="step"' : ""}>
      <span class="wz-n">${i < WZ.step ? "✓" : i + 1}</span>${label}</li>`).join("");
  el.innerHTML = `<div class="wz-shell" role="dialog" aria-modal="true" aria-labelledby="wz-h">
    <aside class="wz-rail"><div class="wz-brand"><img src="studio.png" alt=""><b>Studio setup</b></div><ol>${rail}</ol>
      <p class="wz-railnote">Change any answer later in Settings.</p></aside>
    <section class="wz-main"><div class="wz-body" id="wz-body">${wzBody(id)}</div>
      <footer class="wz-foot" id="wz-foot">${wzFoot(id)}</footer></section></div>`;
  wzWire(id);
  const h = $("#wz-h", el); if (h) h.focus();
}

function wzBody(id) {
  const a = WZ.a, s = WZ.sug;
  const wait = `<p class="muted">Looking at this PC…</p>`;
  const choice = (val, cur, title, sub, extra = "") => `<button type="button" class="wz-opt ${val === cur ? "on" : ""}" data-val="${esc(val)}" role="radio" aria-checked="${val === cur}">
      <span class="wz-dot"></span><span class="wz-opt-t"><b>${title}</b>${sub ? `<small>${sub}</small>` : ""}</span>${extra}</button>`;
  if (id === "welcome") return `<h1 id="wz-h" tabindex="-1">Welcome! Let's set up your studio.</h1>
    <p class="wz-lead">This takes about 3 minutes. First we check this PC has everything, then you answer 5 quick questions.</p>
    <ul class="wz-list">
      <li><b>Check your PC</b>: video tools and Claude, with a fix button for anything missing.</li>
      <li><b>Pick your folders</b>: where your recordings are, where projects go, where your music is.</li>
      <li><b>Captions</b>: on or off for new videos.</li>
      <li><b>Done</b>: then you make your first project.</li></ul>
    <p class="muted">Nothing is uploaded anywhere. Your videos and music stay on this PC.</p>`;
  if (id === "check") {
    const c = WZ.checks, fx = WZ.fix || {};
    if (!c) return `<h1 id="wz-h" tabindex="-1">Checking your PC…</h1>${wait}`;
    const bad = c.filter(x => !x.ok);
    const rows = c.map(x => {
      const running = fx.running && fx.name === x.id;
      const icon = x.info ? `<span class="wz-ic info" aria-label="info">i</span>` : x.ok ? `<span class="wz-ic ok" aria-label="OK">✓</span>` : `<span class="wz-ic bad" aria-label="Missing">✕</span>`;
      return `<div class="wz-check ${x.ok ? "" : "bad"}">${icon}<div class="grow"><b>${esc(x.label)}</b><small>${running ? "Installing… this can take a few minutes. You can keep going." : esc(x.detail)}</small>
        ${!running && fx.name === x.id && fx.ok === false && fx.msg ? `<small class="wz-err">It didn't work: ${esc(fx.msg)}</small>` : ""}</div>
        ${running ? `<span class="wz-spin" aria-label="installing"></span>` : x.fix ? `<button class="primary" data-fix="${x.id}" ${fx.running ? "disabled" : ""}>${esc(x.fix)}</button>` : ""}</div>`;
    }).join("");
    return `<h1 id="wz-h" tabindex="-1">${bad.length ? `${bad.length} thing${bad.length > 1 ? "s" : ""} to fix` : "Everything is ready"}</h1>
      <p class="wz-lead">${bad.length ? "Click the button next to each problem. Windows may ask \"Allow changes?\": click Yes." : "This PC has everything the studio needs."}</p>
      <div class="wz-checks">${rows}</div>`;
  }
  if (id === "recordings") {
    const list = s ? s.recordings : null;
    const known = (list || []).some(r => r.path === a.recordings);
    return `<h1 id="wz-h" tabindex="-1">Where do your recordings save?</h1>
      <p class="wz-lead">The folder your recorder (OBS, phone, camera) saves raw videos to. New projects show the newest ones from here.</p>
      ${!list ? wait : `<div class="wz-opts" role="radiogroup" aria-label="Recordings folder">${list.map(r => choice(r.path, a.recordings, esc(r.path),
        `${r.videos} video${r.videos === 1 ? "" : "s"}${r.newest ? " · newest " + wzAgo(r.newest) : ""}`, r.obs ? `<span class="wz-tag">OBS saves here</span>` : "")).join("")}
        ${a.recordings && !known ? choice(a.recordings, a.recordings, esc(a.recordings), "Your folder") : ""}</div>`}
      <button class="wz-other" id="wz-browse">Choose another folder…</button>`;
  }
  if (id === "projects") {
    const p = a.projects_root || (s && s.projects_root);
    return `<h1 id="wz-h" tabindex="-1">Where should your projects go?</h1>
      <p class="wz-lead">Every video gets a folder here with its edits and drafts. A video needs 10 to 30 GB while you edit it, so pick a drive with space.</p>
      ${!p ? wait : `<div class="wz-opts" role="radiogroup" aria-label="Projects folder">${choice(p, p, esc(p),
        s && p === s.projects_root && s.projects_free != null ? `${s.projects_free} GB free on this drive · made for you if it isn't there yet` : "Made for you if it isn't there yet")}</div>`}
      <button class="wz-other" id="wz-browse">Choose another folder…</button>`;
  }
  if (id === "music") {
    if (!s) return `<h1 id="wz-h" tabindex="-1">Your music library</h1>${wait}`;
    const opts = [[s.music.new, s.music.new_exists ? "Your music library" : "Make a new music library", "Recommended. Sorted into mood folders: chill, upbeat, hype, dark, cinematic, lo-fi."],
      ...s.music.existing.filter(x => x.path !== s.music.new).map(x => [x.path, "Use " + esc(x.path), `${x.tracks} music files in it now`])];
    if (a.music_root && !opts.some(o => o[0] === a.music_root)) opts.push([a.music_root, esc(a.music_root), "Your folder"]);
    return `<h1 id="wz-h" tabindex="-1">Where should your music library be?</h1>
      <p class="wz-lead">Videos get background music picked by mood from this folder. Only use music you own or have a licence for.</p>
      <div class="wz-opts" role="radiogroup" aria-label="Music folder">${opts.map(([v, t, sub]) => choice(v, a.music_root, t, v === s.music.new ? esc(v) + " · " + sub : sub)).join("")}</div>
      <button class="wz-other" id="wz-browse">Choose another folder…</button>
      ${wzHasMusic() ? `<label class="wz-toggle"><input type="checkbox" id="wz-mfind" ${a.music_find ? "checked" : ""}>
        <span><b>Find the music already on this PC and sort it for me</b><small>Looks in Music, Downloads, Desktop, Videos and OneDrive and adds every instrumental by mood. Songs with singing, rapping or producer tags are left out. Your files stay where they are. Don't like a track later? Right-click it in the song picker to remove it or change its mood.</small></span></label>` : ""}`;
  }
  if (id === "captions") return `<h1 id="wz-h" tabindex="-1">Captions on your videos?</h1>
    <p class="wz-lead">Words on screen as you talk. This is the default for new projects; you can change it on any project.</p>
    <div class="wz-capwrap"><div class="wz-opts" role="radiogroup" aria-label="Captions">${WZ_CAP.map(([k, t, sub]) => choice(k, a.captions, t, sub)).join("")}</div>
      <figure class="wz-cap-prev"><img src="captions/bold.png" alt="Example of the Bold pop caption style" onerror="this.parentNode.remove()"><figcaption>Style: Bold pop. Pick another look on any project.</figcaption></figure></div>`;
  if (id === "channel") return `<h1 id="wz-h" tabindex="-1">Your channel name <span class="wz-opt-lbl">optional</span></h1>
    <p class="wz-lead">Projects are sorted by channel, and the editor listens for it in your intro ("welcome back to …"). Leave it empty if you like.</p>
    <label class="wz-field"><span>Channel name</span><input id="wz-ch" value="${esc(a.channel)}" maxlength="60" placeholder="e.g. Sam's Tech" autocomplete="off"></label>
    ${(WZ.st.answers.channels || []).length > 1 ? `<p class="muted small">You have ${WZ.st.answers.channels.length} channels set up already (${esc(WZ.st.answers.channels.join(", "))}). They stay as they are; Settings → Channels changes them.</p>` : ""}`;
  if (id === "apply") return `<h1 id="wz-h" tabindex="-1">Setting things up…</h1>
    <div class="wz-checks"><div class="wz-check"><span class="wz-spin"></span><div class="grow"><b>Filling in your folders</b><small>Making your project and music folders and pointing the studio at them.</small></div></div>
    <div class="wz-check" id="wz-rst" style="opacity:.5"><span class="wz-ic info">↻</span><div class="grow"><b>Restarting the studio</b><small>It closes and opens again by itself in a few seconds.</small></div></div></div>`;
  if (id === "done") {
    const af = (WZ.st && WZ.st.after) || {};
    const cap = (WZ_CAP.find(c => c[0] === a.captions) || WZ_CAP[2])[1];
    const noGpu = WZ.checks && WZ.checks.some(c => c.id === "gpu" && !/fast/.test(c.detail));
    return `<h1 id="wz-h" tabindex="-1">You're all set</h1>
      <p class="wz-lead">Your studio is ready. Here's what it uses:</p>
      <dl class="wz-sum"><dt>Recordings</dt><dd>${esc(wzWin(a.recordings))}</dd><dt>Projects</dt><dd>${esc(wzWin(a.projects_root))}</dd>
        <dt>Music</dt><dd>${esc(wzWin(a.music_root))}</dd><dt>Captions</dt><dd>${esc(cap)}</dd>${a.channel ? `<dt>Channel</dt><dd>${esc(a.channel)}</dd>` : ""}</dl>
      ${af.music_find ? `<p class="wz-note"><b>Sorting your music now.</b> It finds the music on this PC and adds every instrumental by mood (songs with words are left out). It keeps going while you work: the "Set up your music" card on Projects shows how far it is.</p>` : ""}
      <div class="wz-claude"><b>Optional: let Claude finish the rest (about 10 minutes)</b>
        <small>Claude learns your channel's style${noGpu ? ", installs its editing skills and <b>switches rendering to work without an NVIDIA card</b> (needed on this PC)" : " and installs its editing skills"}. A Claude window opens and asks you a few questions.</small>
        <button id="wz-claude">Open Claude</button></div>`;
  }
  return "";
}

function wzFoot(id) {
  if (id === "apply") return "";
  if (id === "done") return `<span class="grow"></span><button id="wz-close">Close</button><button class="primary big" id="wz-first">Make your first project</button>`;
  const first = WZ.step === 0, last = id === "channel";
  const bad = id === "check" && WZ.checks && WZ.checks.some(x => !x.ok);
  return `${first ? `<button class="wz-later" id="wz-later">Set up later</button>` : `<button id="wz-back">Back</button>`}${id === "check" ? `<button id="wz-recheck">Check again</button>` : ""}<span class="grow"></span>
    ${bad ? `<span class="muted small">You can fix these later in Settings → Setup.</span>` : ""}
    <button class="primary big" id="wz-next">${first ? "Start" : last ? "Finish setup" : bad ? "Continue anyway" : "Next"}</button>`;
}

function wzWire(id) {
  const el = WZ.el;
  const go = d => { WZ.step = Math.min(WZ_STEPS.length - 1, Math.max(0, WZ.step + d)); wzDraw(); };
  $$(".wz-opt", el).forEach(b => b.onclick = () => {
    const key = { recordings: "recordings", projects: "projects_root", music: "music_root", captions: "captions" }[id];
    WZ.a[key] = b.dataset.val; $$(".wz-opt", el).forEach(x => { x.classList.toggle("on", x === b); x.setAttribute("aria-checked", x === b); });
  });
  if ($("#wz-browse", el)) $("#wz-browse", el).onclick = async () => {
    const key = { recordings: "recordings", projects: "projects_root", music: "music_root" }[id];
    const p = await wzPickFolder(WZ.a[key]); if (p) { WZ.a[key] = p; wzDraw(); }
  };
  if ($("#wz-mfind", el)) $("#wz-mfind", el).onchange = e => { WZ.a.music_find = e.target.checked; };
  if ($("#wz-ch", el)) { const i = $("#wz-ch", el); i.oninput = () => { WZ.a.channel = i.value; }; i.onkeydown = e => { if (e.key === "Enter") $("#wz-next", el).click(); }; }
  if ($("#wz-back", el)) $("#wz-back", el).onclick = () => go(-1);
  if ($("#wz-later", el)) $("#wz-later", el).onclick = () => { try { sessionStorage.setItem("wz-later", "1"); } catch (e) {} wzClose(); toast("Setup opens again next time, or from Settings → Setup", "ok"); };
  if ($("#wz-next", el)) $("#wz-next", el).onclick = () => {
    if (id === "recordings" && !WZ.a.recordings) return toast("Pick the folder your recordings save to", "bad");
    if (id === "channel") return wzApply();
    go(1);
  };
  if (id === "check") {
    if (!WZ.checks) wzChecks();
    if ($("#wz-recheck", el)) $("#wz-recheck", el).onclick = () => { WZ.checks = null; wzDraw(); };
    $$("[data-fix]", el).forEach(b => b.onclick = async () => {
      b.disabled = true;
      try {
        const r = await api("setup/wizard/fix", { name: b.dataset.fix });
        if (!r.ok) { b.disabled = false; return toast(r.msg, "bad"); }
        if (r.msg) toast(r.msg, "ok");
        if (r.window) { b.disabled = false; if (b.dataset.fix === "signin") toast("Sign in in the new window, then click Check again", "ok"); return; }
      } catch (e) { b.disabled = false; return toast(e.message, "bad"); }
      wzChecks();
    });
  }
  if (id === "done") {
    $("#wz-close", el).onclick = wzClose;
    $("#wz-first", el).onclick = () => { wzClose(); nav("projects"); setTimeout(() => newProjectModal(), 150); };
    $("#wz-claude", el).onclick = async () => {
      try { const r = await api("setup/wizard/fix", { name: "claude_finish" }); toast(r.ok ? "Claude opened in its own window" : r.msg, r.ok ? "ok" : "bad"); }
      catch (e) { toast(e.message, "bad"); }
    };
  }
}

async function wzChecks() {
  clearInterval(WZ.poll);
  const tick = async () => {
    try { const r = await api("setup/wizard/checks"); WZ.checks = r.checks; WZ.fix = r.fix; } catch (e) { return; }
    if (!WZ.fix.running) { clearInterval(WZ.poll); WZ.poll = null; }
    if (WZ.el && WZ_STEPS[WZ.step][0] === "check") wzDraw();
  };
  await tick();
  if (WZ.fix && WZ.fix.running) WZ.poll = setInterval(tick, 3000);
}

async function wzApply() {
  const body = { ...WZ.a };
  const back = WZ.step;
  WZ.el.querySelector("#wz-body").innerHTML = wzBody("apply"); WZ.el.querySelector("#wz-foot").innerHTML = "";
  let r;
  try { r = await api("setup/wizard/apply", body); } catch (e) { r = { ok: false, msg: e.message }; }
  if (!r.ok) { WZ.step = back; wzDraw(); return toast(r.msg, "bad"); }
  const rst = $("#wz-rst", WZ.el); if (rst) { rst.style.opacity = 1; rst.querySelector(".wz-ic").outerHTML = `<span class="wz-spin"></span>`; }
  // the window version closes and opens again by itself; in a browser this page waits for the studio, then reloads
  let down = false;
  const t0 = Date.now();
  const iv = setInterval(async () => {
    try { await fetch("/api/setup/wizard", { cache: "no-store" }).then(x => { if (!x.ok) throw 0; }); if (down || Date.now() - t0 > 20000) { clearInterval(iv); location.reload(); } }
    catch (e) { down = true; }
  }, 1000);
}

// after the restart: the Done screen, and the music search the user asked for
async function wzBoot() {
  let st;
  try { st = await api("setup/wizard"); } catch (e) { return; }
  WZ.st = st;
  const af = st.after || {};
  if (af.show_done) {
    if (af.music_find && wzHasMusic()) { try { await api("music/setup/auto", {}); msStatus(); } catch (e) { console.warn(e); } }
    await api("setup/wizard/after", {}).catch(() => {});
    api("setup/wizard/checks").then(r => { WZ.checks = r.checks; if (WZ.el) wzDraw(); }).catch(() => {});
    await wzOpen("done"); WZ.st.after = af; wzDraw();
    return;
  }
  let later = false; try { later = sessionStorage.getItem("wz-later") === "1"; } catch (e) {}
  if (!st.done && !later) wzOpen("welcome");
}

// Settings: a Setup card (run the wizard again / check what's installed)
function wzCard() {
  const main = $("#main"); if (!main || S.view !== "settings" || $("#wz-card")) return;
  const c = document.createElement("div"); c.id = "wz-card"; c.className = "card"; c.style.marginBottom = "22px";
  const h = main.querySelector("h1"); (h && h.nextElementSibling ? h.nextElementSibling : h || main).after(c);
  c.innerHTML = `<div class="row" style="justify-content:space-between"><h2 style="margin:0">Setup</h2><span class="muted small">your folders, captions default, channel name</span></div>
    <p class="muted small">Walk through the setup again to change your folders or captions default, or check that FFmpeg and Claude are working.</p>
    <div class="row" style="margin-top:10px"><button class="primary" id="wz-rerun">Run setup again</button><button class="sm" id="wz-recheck2">Check what's installed</button></div>`;
  $("#wz-rerun", c).onclick = () => wzOpen("welcome");
  $("#wz-recheck2", c).onclick = () => { WZ.checks = null; wzOpen("check"); };
}
new MutationObserver(() => { if (S.view === "settings" && !$("#wz-card")) wzCard(); }).observe(document.body, { childList: true, subtree: true });

// New projects start with the captions default from setup (a project's own Edit options keep what it has)
if (typeof modeOptsHtml === "function") {
  const wzModeOpts = modeOptsHtml;
  modeOptsHtml = function (st = {}, ...rest) {
    const cd = S.state && S.state.settings && S.state.settings.captions_default;
    if (cd && st && !Object.keys(st).length) st = { captions: cd.where === "off" ? { on: false, style: cd.style || "bold" } : { on: true, where: cd.where, style: cd.style || "bold" } };
    return wzModeOpts(st, ...rest);
  };
}

setTimeout(wzBoot, 600);

const wzStyle = document.createElement("style");
wzStyle.textContent = `
#wz{position:fixed;inset:0;z-index:45;background:rgba(5,7,10,.88);display:grid;place-items:center;padding:16px;font-size:15px}
#wz .wz-shell{width:min(980px,100%);height:min(660px,100%);display:grid;grid-template-columns:220px 1fr;grid-template-rows:100%;background:#12151b;border:1px solid #39414f;border-radius:14px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.6)}
#wz .wz-rail{background:#0b0d11;border-right:1px solid #2a303c;padding:20px 14px;display:flex;flex-direction:column}
#wz .wz-brand{display:flex;align-items:center;gap:10px;margin:0 6px 20px;font-size:15px;color:#fff}#wz .wz-brand img{width:28px;height:28px}
#wz ol{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:3px}
#wz ol li{display:flex;align-items:center;gap:10px;padding:8px 8px;border-radius:8px;color:#9aa3b5;font-weight:500}
#wz ol li.on{background:#1e2430;color:#fff;box-shadow:inset 3px 0 0 var(--accent)}#wz ol li.done{color:#d6dbe6}
#wz .wz-n{width:24px;height:24px;flex:none;border-radius:50%;display:grid;place-items:center;font-size:12px;font-weight:700;border:1.5px solid #4a5366;color:#c3c9d6}
#wz li.on .wz-n{background:var(--accent);border-color:var(--accent);color:#0b0d12}#wz li.done .wz-n{background:#1f3a2a;border-color:#5bd97a;color:#5bd97a}
#wz .wz-railnote{margin-top:auto;color:#8d95a6;font-size:12px;padding:0 6px}
#wz .wz-main{display:flex;flex-direction:column;min-width:0;min-height:0}
#wz .wz-body{flex:1;min-height:0;overflow:auto;padding:22px 34px 12px}
#wz h1{font-size:24px;line-height:1.25;margin:0 0 8px;color:#fff;outline:none}
#wz .wz-lead{font-size:15.5px;color:#d5dae4;margin:0 0 20px;max-width:640px}
#wz .wz-list{margin:0 0 18px;padding-left:20px;color:#e8ebf1;line-height:1.75}
#wz .muted{color:#9aa3b5}
#wz .wz-foot{display:flex;align-items:center;gap:10px;padding:14px 34px;border-top:1px solid #2a303c;background:#0f1217;min-height:64px}
#wz button{font-size:14.5px;padding:9px 16px;border-radius:8px}
#wz button.big{font-size:15.5px;padding:11px 26px;font-weight:700}
#wz button:focus-visible,#wz input:focus-visible{outline:3px solid #fff;outline-offset:2px}
#wz .wz-later{background:none;border-color:transparent;color:#9aa3b5;text-decoration:underline}
#wz .wz-opts{display:flex;flex-direction:column;gap:8px;margin-bottom:10px}
#wz .wz-opt{display:flex;align-items:center;gap:12px;text-align:left;width:100%;padding:12px 14px;background:#181c24;border:1.5px solid #39414f;border-radius:10px}
#wz .wz-opt:hover{border-color:#6c7891}#wz .wz-opt.on{border-color:var(--accent);background:#1b2233}
#wz .wz-opt-t{display:flex;flex-direction:column;gap:3px;min-width:0;flex:1}#wz .wz-opt-t b{color:#fff;font-weight:600;overflow-wrap:anywhere}
#wz small{display:block;color:#a9b1c1;font-size:13px;line-height:1.4}
#wz .wz-dot{width:18px;height:18px;flex:none;border-radius:50%;border:2px solid #6c7891}
#wz .wz-opt.on .wz-dot{border-color:var(--accent);background:radial-gradient(circle,var(--accent) 45%,transparent 50%)}
#wz .wz-tag{flex:none;font-size:12px;font-weight:600;color:#5bd97a;border:1px solid #2f6b43;border-radius:20px;padding:2px 9px}
#wz .wz-other{background:none;border:1.5px dashed #4a5366;color:#d5dae4}
#wz .wz-toggle{display:flex;gap:12px;align-items:flex-start;margin-top:18px;padding:12px 14px;border:1.5px solid #39414f;border-radius:10px;cursor:pointer;background:#181c24}
#wz .wz-toggle input{width:20px;height:20px;margin-top:2px;accent-color:var(--accent);flex:none}#wz .wz-toggle b{color:#fff}
#wz .wz-checks{display:flex;flex-direction:column;gap:5px}
#wz .wz-check{display:flex;align-items:center;gap:12px;padding:9px 14px;background:#181c24;border:1px solid #2f3644;border-radius:10px}
#wz .wz-check:not(.bad){padding:6px 14px}#wz .wz-check:not(.bad) .grow{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
#wz .wz-check.bad{border-color:#7a3a3a;background:#211819}#wz .wz-check b{color:#fff}#wz .wz-check .grow{flex:1;min-width:0}
#wz .wz-ic{width:26px;height:26px;flex:none;border-radius:50%;display:grid;place-items:center;font-weight:800;font-size:14px}
#wz .wz-ic.ok{background:#1f3a2a;color:#5bd97a}#wz .wz-ic.bad{background:#4a1f1f;color:#ff8080}#wz .wz-ic.info{background:#1c2c3d;color:#6fc8ff;font-style:italic;font-family:Georgia,serif}
#wz .wz-err{color:#ff9a9a}
#wz .wz-spin{width:22px;height:22px;flex:none;border:3px solid #39414f;border-top-color:var(--accent);border-radius:50%;animation:wzspin .9s linear infinite}
@keyframes wzspin{to{transform:rotate(360deg)}}
#wz .wz-capwrap{display:grid;grid-template-columns:1fr 250px;gap:18px;align-items:start}
#wz .wz-cap-prev{margin:0;background:#0b0d11;border:1px solid #2f3644;border-radius:10px;padding:8px}#wz .wz-cap-prev img{width:100%;display:block;border-radius:6px}
#wz figcaption{font-size:12.5px;color:#a9b1c1;margin-top:6px}
#wz .wz-field{display:flex;flex-direction:column;gap:6px;max-width:440px;font-weight:600;color:#fff}
#wz .wz-field input{font-size:16px;padding:11px 12px;background:#0b0d11;border:1.5px solid #4a5366;border-radius:8px;color:#fff}
#wz .wz-opt-lbl{font-size:13px;font-weight:600;color:#9aa3b5;border:1px solid #4a5366;border-radius:20px;padding:2px 10px;vertical-align:middle;margin-left:6px}
#wz .wz-sum{display:grid;grid-template-columns:110px 1fr;gap:6px 14px;margin:0 0 16px}#wz .wz-sum dt{color:#9aa3b5}#wz .wz-sum dd{margin:0;color:#fff;overflow-wrap:anywhere}
#wz .wz-note{background:#16222f;border:1px solid #2c4a66;border-radius:10px;padding:11px 14px;color:#d5dae4}
#wz .wz-claude{margin-top:12px;padding:12px 14px;border:1px solid #39414f;border-radius:10px;display:flex;flex-direction:column;gap:6px;align-items:flex-start}#wz .wz-claude b{color:#fff}
@media (max-width:760px){#wz .wz-shell{grid-template-columns:1fr}#wz .wz-rail{display:none}#wz .wz-capwrap{grid-template-columns:1fr}}`;
document.head.appendChild(wzStyle);

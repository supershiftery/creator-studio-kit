// Set up your music (kit): a card on Projects while the library is empty, a Music card in Settings, and the
// find -> confirm -> sort flow (server: app/music_setup.py, tools/music_kit.py)
const MS = { st: null, poll: null };
const MS_MOODS = ["chill", "upbeat", "hype", "dark", "cinematic", "lo-fi"];

async function msStatus() {
  try { MS.st = await api("music/setup"); } catch (e) { MS.st = null; }
  msCards();
  return MS.st;
}

const msBusy = st => st && st.running && ["finding", "organising"].includes((st.progress || {}).state);

function msCards() {
  const main = $("#main"), st = MS.st; if (!main || !st) return;
  const p0 = st.progress || {};
  const sig = JSON.stringify([st.counts, st.clean, st.library, st.extra_roots, st.has_found, st.has_report, st.running, p0.state, p0.done, p0.msg]);
  const fresh = el => el && (el.dataset.sig === sig || el.contains(document.activeElement));   // no redraw under the user's typing
  const head = () => { const h = main.querySelector("h1"); return h && h.nextElementSibling ? h.nextElementSibling : h || main; };
  // Projects: only while there is no usable music yet
  let pc = $("#ms-card");
  if (S.view === "projects" && (st.needed || msBusy(st))) {
    if (fresh(pc)) return;
    if (!pc) { pc = document.createElement("div"); pc.id = "ms-card"; pc.className = "card"; pc.style.marginBottom = "18px"; head().after(pc); }
    pc.dataset.sig = sig;
    pc.innerHTML = `<div class="row" style="justify-content:space-between"><h2 style="margin:0">Set up your music</h2></div>
      <p class="small">Videos need background music, and the Studio picks it by mood for you. It finds the music already on this PC
      (Music, Downloads, Desktop, Videos, OneDrive and music folders on your other drives) and sorts every instrumental into a mood
      library: ${MS_MOODS.join(", ")}. Songs with singing, rapping or producer tags are left out. <b>Your files stay where they are</b>:
      nothing is moved or deleted. Don't like a track later? Right-click it in the song picker.</p>
      <p class="muted tiny" style="overflow-wrap:anywhere">Library: ${esc(st.library)} (change it in Settings → Music)</p>
      ${msProgress(st)}
      <div class="row" style="margin-top:10px">${msBusy(st) ? `<button class="sm" data-ms-open>Show progress</button>` : `<button class="primary" data-ms-find>Find and sort my music</button><button class="sm" data-ms-later>Later</button>`}</div>`;
    msWire(pc);
  } else if (pc) pc.remove();
  // Settings: always
  let sc = $("#ms-set");
  if (S.view === "settings") {
    if (fresh(sc)) return;
    if (!sc) { sc = document.createElement("div"); sc.id = "ms-set"; sc.className = "card"; sc.style.marginBottom = "22px"; head().after(sc); }
    sc.dataset.sig = sig;
    const counts = MS_MOODS.map(m => `<span class="pill">${esc(m)} <b>${st.counts[m] || 0}</b></span>`).join(" ");
    sc.innerHTML = `<div class="row" style="justify-content:space-between"><h2 style="margin:0">Music</h2><span class="muted small">${st.clean} clean tracks the picker can use</span></div>
      <div class="field"><label>Mood library (the picker uses this)</label><input id="ms-root" value="${esc(st.library)}"></div>
      <div class="field"><label>Also use music from (folders used as they are, nothing copied; comma separated)</label><input id="ms-extra" value="${esc((st.extra_roots || []).join(", "))}"></div>
      <div class="row small" style="gap:6px;margin:6px 0 4px">${counts}</div>
      ${msProgress(st)}
      <p class="muted small" style="margin:6px 0 0">Right-click a song in any song picker to remove it from the library or change its mood.</p>
      ${(st.removed || []).length ? `<details class="ms-rm"><summary class="small">Removed tracks (${st.removed.length})</summary>${st.removed.map(r => `<div class="row small" style="gap:8px;padding:3px 0"><span class="grow">${esc(r.name)} <span class="muted tiny">${esc(r.date || "")}</span></span><button class="sm" data-ms-restore="${esc(r.name)}">Put back</button></div>`).join("")}</details>` : ""}
      <div class="row" style="margin-top:10px"><button class="sm" id="ms-save">Save</button>${msBusy(st) ? `<button class="sm" data-ms-open>Show progress</button>` : `<button class="primary" data-ms-find>Find and sort my music</button>`}${st.has_report ? `<button class="sm" data-ms-report>Last report</button>` : ""}</div>`;
    $("#ms-save", sc).onclick = async () => {
      try { MS.st = await api("music/setup/settings", { music_root: $("#ms-root", sc).value, music_extra_roots: $("#ms-extra", sc).value.split(",").map(x => x.trim()).filter(Boolean) }); toast("Music folders saved", "ok"); msCards(); }
      catch (e) { toast(e.message, "bad"); }
    };
    msWire(sc);
  }
}

function msProgress(st) {
  const p = st.progress || {};
  if (msBusy(st)) return `<p class="small"><b>${p.state === "finding" ? "Looking for music…" : `Sorting ${p.done || 0} / ${p.total || "?"}`}</b> <span class="muted">${esc(p.msg || "")}</span></p>`;
  if (p.state === "error" || p.state === "stopped") return `<p class="bad small">The last music setup ${p.state === "stopped" ? "stopped before it finished" : "failed"}${p.msg ? ": " + esc(p.msg) : ""}. Run it again.</p>`;
  return "";
}

function msWire(el) {
  $$("[data-ms-find]", el).forEach(b => b.onclick = msFind);
  $$("[data-ms-open]", el).forEach(b => b.onclick = msOpen);
  $$("[data-ms-report]", el).forEach(b => b.onclick = msReport);
  $$("[data-ms-restore]", el).forEach(b => b.onclick = async () => {
    try { await api("music/library/restore", { name: b.dataset.msRestore }); if (typeof TL !== "undefined") TL.lib = null; toast(`“${b.dataset.msRestore}” is back in your library`, "ok"); msStatus(); }
    catch (e) { toast(e.message, "bad"); }
  });
  $$("[data-ms-later]", el).forEach(b => b.onclick = async () => { MS.st = await api("music/setup/settings", { dismissed: true }); msCards(); toast("You can set up music any time in Settings → Music", "ok"); });
}

// find + sort everything in one go (user 2026-10-29: no list to tick; the vocal / producer-tag check still keeps songs out)
async function msFind() {
  try { await api("music/setup/auto", {}); } catch (e) { return toast(e.message, "bad"); }
  msOpen();
}

// one modal that follows the run: progress, then the found list (finding) or the report (sorting)
function msOpen() {
  const m = modal(`<h2>Set up your music</h2><div id="ms-body"><p class="muted">Starting…</p></div>`, "wide");
  clearInterval(MS.poll);
  const tick = async () => {
    if (!document.body.contains(m)) return clearInterval(MS.poll);
    const st = await msStatus(); if (!st) return;
    const p = st.progress || {};
    if (msBusy(st)) {
      $("#ms-body", m).innerHTML = p.state === "finding"
        ? `<p><b>Looking for music on this PC…</b></p><p class="muted small">${esc(p.msg || "")}${p.found ? ` · ${p.found} audio files so far` : ""}</p>`
        : `<p><b>Sorting your music: ${p.done || 0} of ${p.total || "?"}</b></p><div class="bar" style="height:6px;background:var(--line);border-radius:4px;overflow:hidden"><div style="height:100%;width:${p.total ? Math.round(100 * p.done / p.total) : 3}%;background:var(--accent,#5b8cff)"></div></div>
           <p class="muted small" style="margin-top:8px">${esc(p.msg || "")}</p>
           <p class="muted small">Every track is listened to for vocals and producer tags (about 20-60 s each). It waits while a video renders. You can close this window: it keeps going.</p>`;
      return;
    }
    clearInterval(MS.poll);
    if (p.state === "found") return msFound(m);
    if (p.state === "done") return msReport(m);
    $("#ms-body", m).innerHTML = msProgress(st) || `<p class="muted">Nothing running.</p>`;
  };
  tick(); MS.poll = setInterval(tick, 2000);
}

async function msFound(m) {
  const r = await api("music/setup/found");
  m = m && document.body.contains(m) ? m : modal(`<h2>Set up your music</h2><div id="ms-body"></div>`, "wide");
  const sk = r.skipped || {};
  if (!r.files) {
    $("#ms-body", m).innerHTML = `<p>No music found in ${r.places.length} places (${esc(r.places.slice(0, 6).join(", "))}${r.places.length > 6 ? "…" : ""}).</p>
      <p class="muted small">Skipped: ${sk.short || 0} short / under 60 s, ${sk.system_or_sfx || 0} sound effects, ${sk.online_only || 0} online-only cloud files.</p>
      <p class="small">Put the music you own into <code>${esc(MS.st.library)}</code> (any folders), or add a folder in Settings → Music, then run this again.</p>
      <div class="row"><span class="grow"></span><button class="sm" id="ms-close">Close</button></div>`;
    $("#ms-close", m).onclick = closeModal; return;
  }
  const rows = r.folders.map((g, i) => `<details class="ms-f"><summary><label onclick="event.stopPropagation()"><input type="checkbox" data-ms-g="${i}" checked></label>
      <b>${g.count}</b> track${g.count > 1 ? "s" : ""} · ${g.minutes} min <span class="muted">${esc(g.folder)}</span></summary>
      <div class="small" style="padding:4px 0 8px 30px">${g.files.map((f, j) => `<label style="display:block"><input type="checkbox" data-ms-t="${i}" data-p="${esc(f.path)}" checked> ${esc(f.name)} <span class="muted tiny">${Math.round(f.dur / 60)}:${String(Math.round(f.dur % 60)).padStart(2, "0")}</span></label>`).join("")}</div></details>`).join("");
  $("#ms-body", m).innerHTML = `<p><b>Found ${r.files} tracks (${r.minutes} min)</b> in ${r.folders.length} folder${r.folders.length > 1 ? "s" : ""}. Untick anything that isn't yours to use or isn't background music.</p>
    <p class="muted small">Skipped: ${sk.short || 0} under 60 s, ${sk.system_or_sfx || 0} sound effects / system sounds, ${sk.online_only || 0} online-only cloud files, ${sk.duplicate || 0} duplicates, ${sk.in_library || 0} already in your library.</p>
    <div style="max-height:46vh;overflow:auto;border:1px solid var(--line);border-radius:8px;padding:6px 10px">${rows}</div>
    <div class="row small" style="margin-top:10px;gap:14px"><label><input type="radio" name="ms-mode" value="link" checked> Link (no extra disk space; copies when it's another drive)</label><label><input type="radio" name="ms-mode" value="copy"> Copy</label></div>
    <p class="muted small">Your originals are never moved or deleted. Tracks with vocals, lyrics or producer tags are left out and listed in the report.</p>
    <div class="row"><span class="grow"></span><button class="sm" id="ms-cancel">Cancel</button><button class="primary" id="ms-go">Sort <span id="ms-n">${r.files}</span> tracks</button></div>`;
  const count = () => { $("#ms-n", m).textContent = $$("[data-ms-t]:checked", m).length; };
  $$("[data-ms-g]", m).forEach(c => c.onchange = () => { $$(`[data-ms-t="${c.dataset.msG}"]`, m).forEach(t => t.checked = c.checked); count(); });
  $$("[data-ms-t]", m).forEach(c => c.onchange = count);
  $("#ms-cancel", m).onclick = closeModal;
  $("#ms-go", m).onclick = async () => {
    const paths = $$("[data-ms-t]:checked", m).map(c => c.dataset.p);
    if (!paths.length) return toast("Tick at least one track", "bad");
    try { await api("music/setup/organise", { paths, mode: ($("[name=ms-mode]:checked", m) || {}).value || "link" }); } catch (e) { return toast(e.message, "bad"); }
    msOpen();
  };
}

async function msReport(m) {
  const r = await api("music/setup/report");
  m = m && m.nodeType && document.body.contains(m) ? m : modal(`<h2>Set up your music</h2><div id="ms-body"></div>`, "wide");
  const counts = MS_MOODS.map(k => `<span class="pill">${esc(k)} <b>${(r.counts || {})[k] || 0}</b></span>`).join(" ");
  const added = (r.added || []).map(a => `<tr><td>${esc(a.name)}</td><td>${esc(a.mood)}</td><td>${esc(a.genre)}</td><td>${Math.round(a.bpm || 0)}</td></tr>`).join("");
  const rej = (r.rejected || []).map(a => `<tr><td>${esc(a.name)}</td><td class="small">${esc(a.reason)}</td></tr>`).join("");
  $("#ms-body", m).innerHTML = `<p><b>${(r.added || []).length} tracks added</b> to your mood library, ${(r.rejected || []).length} left out, ${(r.already || []).length} already there${(r.failed || []).length ? `, ${(r.failed || []).length} failed` : ""}. <span class="muted small">(${esc(r.when || "")}, ${r.took_min} min)</span></p>
    <div class="row small" style="gap:6px;margin-bottom:8px">${counts}</div>
    <div style="max-height:44vh;overflow:auto">
      ${added ? `<h3>Added</h3><table class="small"><tr><th>Track</th><th>Mood</th><th>Genre</th><th>BPM</th></tr>${added}</table>` : ""}
      ${rej ? `<h3 style="margin-top:12px">Left out (instrumentals only)</h3><table class="small"><tr><th>Track</th><th>Why</th></tr>${rej}</table>` : ""}
    </div>
    <p class="muted small">Moods are a best guess from the audio: move a file to another mood folder any time. Full report: <code>${esc(MS.st ? MS.st.report_md : "")}</code></p>
    <div class="row"><button class="sm" id="ms-lib">Open the library folder</button><button class="sm" id="ms-rep">Open the report</button><span class="grow"></span><button class="primary" id="ms-done">Done</button></div>`;
  $("#ms-done", m).onclick = closeModal;
  $("#ms-lib", m).onclick = () => api("open", { path: r.library }).catch(e => toast(e.message, "bad"));
  $("#ms-rep", m).onclick = () => api("open", { path: MS.st.report_md }).catch(e => toast(e.message, "bad"));
}

// Projects / Settings are redrawn by the app: add the cards whenever they show
new MutationObserver(() => {
  if (!MS.st) return;
  if ((S.view === "projects" && (MS.st.needed || msBusy(MS.st)) && !$("#ms-card")) || (S.view === "settings" && !$("#ms-set"))) msCards();
}).observe(document.body, { childList: true, subtree: true });
setTimeout(() => msStatus().then(st => { if (st && st.needed && !st.has_found && !msBusy(st) && S.view === "projects") msCards(); }), 1500);
setInterval(() => { if (msBusy(MS.st) || S.view === "settings" || S.view === "projects") msStatus(); }, 10000);

const msStyle = document.createElement("style");
msStyle.textContent = `.ms-f summary{cursor:pointer;padding:5px 0;display:flex;gap:8px;align-items:center}.ms-f summary .muted{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#ms-set .pill,#ms-body .pill{display:inline-block;padding:2px 9px;border:1px solid var(--line);border-radius:20px}
#ms-ctx{position:fixed;z-index:300;min-width:200px;display:flex;flex-direction:column;padding:6px}
#ms-ctx a{padding:7px 10px;border-radius:6px;color:var(--text);text-decoration:none;cursor:pointer;text-transform:capitalize}
#ms-ctx a:hover,#ms-ctx a:focus{background:var(--bg3);outline:none}#ms-ctx a.bad{color:var(--bad);text-transform:none}
#ms-ctx .ms-ctx-h{padding:6px 10px 8px;font-weight:700;max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;border-bottom:1px solid var(--line);margin-bottom:4px}
#ms-ctx .ms-ctx-l{padding:4px 10px 2px;font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em}
#ms-ctx .ms-ctx-sep{height:1px;background:var(--line);margin:5px 0}`;
document.head.appendChild(msStyle);

// ---------------------------------------------------------------- right-click a song: remove it for good / change its mood
// Works in every song picker (the editor's "Pick a song", the timeline's music panel, the project's Sections music picker).
const MS_ROW = "#e2-pick .e2-song.lib, #tle-lib .tle-item, #modal-root #m-list .fe[data-p]";
const msRowPath = row => row.dataset.p || ((row.querySelector("[data-use]") || {}).dataset || {}).use
  || ((row.querySelector("[data-prev]") || {}).dataset || {}).prev || "";
function msCtxClose() { const c = $("#ms-ctx"); if (c) c.remove(); }
document.addEventListener("contextmenu", e => {
  const row = e.target.closest && e.target.closest(MS_ROW); if (!row) return;
  const path = msRowPath(row); if (!path) return;
  e.preventDefault(); msCtxClose();
  const name = base(path).replace(/\.[^.]+$/, "");
  const cur = path.split(/[\\/]/).slice(-2, -1)[0];
  const c = document.createElement("div"); c.id = "ms-ctx"; c.className = "ctx"; c.setAttribute("role", "menu"); c.setAttribute("aria-label", "Song: " + name);
  c.innerHTML = `<div class="ms-ctx-h">${esc(name)}</div>
    <div class="ms-ctx-l">Mood</div>${MS_MOODS.map(m => `<a role="menuitem" tabindex="-1" data-ms-mood="${m}">${m === cur ? "✓ " : ""}${m}</a>`).join("")}
    <div class="ms-ctx-sep"></div><a role="menuitem" tabindex="-1" class="bad" data-ms-rm>Remove from library</a>`;
  document.body.appendChild(c);
  const r = c.getBoundingClientRect();
  c.style.left = Math.max(8, Math.min(e.clientX, innerWidth - r.width - 8)) + "px";
  c.style.top = Math.max(8, Math.min(e.clientY, innerHeight - r.height - 8)) + "px";
  const items = $$("[role=menuitem]", c); items[0].focus();
  c.onkeydown = ev => {
    const i = items.indexOf(document.activeElement);
    if (ev.key === "Escape") { msCtxClose(); const b = row.querySelector("button"); if (b) b.focus(); }
    else if (ev.key === "ArrowDown" || ev.key === "ArrowUp") { ev.preventDefault(); items[(i + (ev.key === "ArrowDown" ? 1 : items.length - 1)) % items.length].focus(); }
    else if (ev.key === "Enter") { ev.preventDefault(); document.activeElement.click(); }
  };
  $$("[data-ms-mood]", c).forEach(a => a.onclick = async () => {
    msCtxClose();
    try {
      const res = await api("music/library/mood", { path, mood: a.dataset.msMood });
      msLibUpdate(path, t => { t.path = res.path; t.cat = res.mood; t.moods = res.moods || t.moods; });
      $$("[data-use], [data-prev]", row).forEach(b => { if (b.dataset.use === path) b.dataset.use = res.path; if (b.dataset.prev === path) b.dataset.prev = res.path; });
      if (row.dataset.p) row.dataset.p = res.path;
      toast(`“${name}” is ${res.mood} now`, "ok");
    } catch (err) { toast(err.message, "bad"); }
  });
  $("[data-ms-rm]", c).onclick = async () => {
    msCtxClose();
    if (!confirm(`Remove “${name}” from your music library?\n\nIt's never picked again. Your own file stays where it is, and you can put it back in Settings → Music.`)) return;
    try {
      await api("music/library/remove", { path });
      msLibUpdate(path, null); row.remove(); msStatus();
      toast(`Removed “${name}”. Put it back any time in Settings → Music.`, "ok");
    } catch (err) { toast(err.message, "bad"); }
  };
});
document.addEventListener("mousedown", e => { if (!e.target.closest("#ms-ctx")) msCtxClose(); });

// the editor's song list is cached (TL.lib): keep it in step, and never show a removed track again
function msLibUpdate(path, fn) {
  if (typeof TL === "undefined" || !TL.lib) return;
  const i = TL.lib.tracks.findIndex(t => t.path === path); if (i < 0) return;
  if (fn) fn(TL.lib.tracks[i]); else TL.lib.tracks.splice(i, 1);
}
document.addEventListener("DOMContentLoaded", () => {   // the editor's scripts load after this one
  if (typeof tlMusicLib !== "function") return;
  const msTlLib = tlMusicLib;
  tlMusicLib = async function () {
    const lib = await msTlLib();
    const gone = new Set(((MS.st && MS.st.removed) || []).map(r => String(r.name).toLowerCase()));
    if (gone.size) lib.tracks = lib.tracks.filter(t => !gone.has(base(t.path).toLowerCase()));
    return lib;
  };
});
// a one-line hint in the editor's song picker
new MutationObserver(() => {
  const h = $("#e2-pick .e2-mhead");
  if (h && !$("#ms-hint")) h.insertAdjacentHTML("afterend", `<p class="e2-hint" id="ms-hint">Right-click a song to change its mood or remove it from your library.</p>`);
}).observe(document.body, { childList: true });

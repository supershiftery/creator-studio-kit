/* {{STUDIO_NAME}} UI, part 9 (2026-10-29): the timeline editor (user: "people should be able to edit the video themselves ...
   like Filmora, something easy to understand"; mockup https://claude.ai/artifact/Do4SiBF1FhnM9C5AsZPsdR).
   - The Editor tab becomes: panels on the left (Transcript / Clips / Music / Text / Captions / Transitions), the player in the
     middle, a Changes list on the right and a timeline underneath (Main video, B-roll, Text, Music, Captions), on the
     RECORDING's time axis so the parts the AI cut show as gaps.
   - Nothing here cuts video by itself: every timeline edit is a studio note in the existing grammar (cut / protect / broll,
     raw times from the editor) or a written revision ("note 1:24-1:27: ..."), applied by the next build through the same
     pipelines. The transcript cutter (app4.js: TX, txApply, txWire) is reused as is; the timeline drives it.
   - "More tools" hides / shows the other project tabs (Revisions, Build, Sections, Shorts, Deliverables) so nothing is lost.
   - The build bar speaks plain words: what it's doing now, steps done, time left, "still working, last update N s ago".
   Loaded after app8.js; replaces renderEditor and progressBar, wraps renderProject and txCount. */

const TL = { panel: "transcript", zoom: 1, sel: null, splits: {}, moved: {}, keys: {}, drag: null, justDragged: false };
const tlMore = () => { try { return localStorage.getItem("studio.moreTools") === "1"; } catch (e) { return true; } };
const tlSetMore = on => { try { localStorage.setItem("studio.moreTools", on ? "1" : "0"); } catch (e) { } };

// ---------------------------------------------------------------- plain-word build progress
// six steps everyone understands (mockup v5); every pipeline step / stage maps onto one of them by its name
const TL_GROUPS = [
  ["Getting your video ready", "Lines up your files and sound so they're easy to cut.", /normali|prep|import|probe|join|swap|mic|source|layout|privacy|blur|pii|crop/i],
  ["Listening to what you say", "Writes down every word so it knows what you said.", /transcri|whisper|listen|words/i],
  ["Cutting out mistakes", "Removes repeated takes, ums and dead air. Usually the longest step.", /cut|trim|take|filler|retake|section|chapter|silence/i],
  ["Adding music and titles", "B-roll, the intro, titles, music and captions.", /b-?roll|intro|graphic|card|wipe|callout|music|bed|beat|caption|subtit|zoom|thumb/i],
  ["Putting it all together", "Renders everything into one video file.", /assemble|body|main|render|encode|final|draft|join|mux|export/i],
  ["Checking the result", "Watches the result for glitches before you see it.", /qc|check|audit|review|verify/i],
];
function tlGroupOf(label, prev) {
  const head = String(label || "").split(/[:+(→,]/)[0];   // "Assemble: intro, wipes, cards, music → DRAFT" is putting it together
  for (const rx of [head, label || ""]) { const i = TL_GROUPS.findIndex(g => g[2].test(rx)); if (i >= 0) return i; }
  return prev == null ? 0 : prev;
}
function tlPlain(label) { const g = TL_GROUPS[tlGroupOf(label)]; return { name: g[0], desc: g[1] }; }
const tlJobKind = j => ({ draft: "Making your draft", final: "Making the final video", revise: "Applying your changes", intro: "Remaking the intro", check: "Checking the video" })[(j.title || "").split(": ").pop()] || "Working on your video";
const tlAgo = s => s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60 ? (s % 60) + " s" : ""}`.trim();
const tlLeft = s => s <= 0 ? "almost done" : s < 60 ? `about <b>${Math.max(1, Math.round(s))} s</b> left` : `about <b>${Math.round(s / 60)} min</b> left`;

// the bar never sits still (user 2026-10-29: "people quit when a bar stalls on one step"): inside the running step it creeps
// toward that step's end, fast first and slower near the end; it jumps when the server's number moves past it, never goes back,
// and the time left counts down every second between server updates
TL.cp = TL.cp || {};
function tlCreepState(j) {
  const pr = j.progress || {}, now = Date.now();
  let c = TL.cp[j.id];
  const srv = +pr.pct || 0, n = Math.max(1, pr.step_count || 1), k = Math.max(1, pr.step_index || 1);
  const stepEnd = Math.min(99, Math.max(srv + 1.5, srv + (100 - srv) / Math.max(1, n - k + 1)));   // what is left, shared by the steps still to go
  if (!c) c = TL.cp[j.id] = { shown: srv, at: now, end: stepEnd, eta: +pr.eta_s || 0, etaAt: now, step: pr.step };
  if (srv > c.shown) c.shown = srv;
  if (pr.step !== c.step) { c.step = pr.step; c.end = stepEnd; }
  else c.end = Math.max(c.end, stepEnd);
  if (pr.eta_s != null && Math.abs((+pr.eta_s) - (c.eta - (now - c.etaAt) / 1000)) > 20) { c.eta = +pr.eta_s; c.etaAt = now; }   // only re-sync on a real change
  return c;
}
function tlCreepTick() {
  const now = Date.now();
  for (const [id, c] of Object.entries(TL.cp)) {
    const dt = Math.min(5, (now - c.at) / 1000); c.at = now;
    c.shown = Math.min(99, c.shown + (c.end - c.shown) * (1 - Math.pow(1 - 0.015, dt)));
    const left = Math.max(0, c.eta - (now - c.etaAt) / 1000);
    $$(`[data-tl-pct="${id}"]`).forEach(el => el.textContent = Math.floor(c.shown) + "%");
    $$(`[data-tl-bar="${id}"]`).forEach(el => el.style.width = c.shown.toFixed(2) + "%");
    $$(`[data-tl-left="${id}"]`).forEach(el => el.innerHTML = tlLeft(left));
  }
  $$("[data-tl-ago]").forEach(el => { const t = TL.moved[el.dataset.tlAgo]; if (t) el.textContent = tlAgo(Math.round((now - t) / 1000)); });
}
setInterval(tlCreepTick, 1000);

function tlProgressCard(j, compact) {
  const pr = j.progress || { pct: 0, step: "", step_index: 1, step_count: (j.steps || []).length, elapsed_s: 0, eta_s: 0 };
  const key = `${pr.step}|${Math.floor(pr.pct)}|${(j.steps || []).filter(s => s.status === "done").length}`;
  if (TL.keys[j.id] !== key) { TL.keys[j.id] = key; TL.moved[j.id] = Date.now(); }
  const ago = Math.round((Date.now() - (TL.moved[j.id] || Date.now())) / 1000);
  const c = tlCreepState(j), left = Math.max(0, c.eta - (Date.now() - c.etaAt) / 1000);
  // the job's steps folded into the six plain ones
  const groups = TL_GROUPS.map(() => ({ n: 0, done: 0, run: false, fail: false, secs: 0 }));
  let prev = 0;
  for (const s of j.steps || []) {
    const g = groups[prev = tlGroupOf(s.label, prev)];
    g.n++; if (s.status === "done" || s.status === "skipped") g.done++; if (s.status === "running") g.run = true; if (s.status === "failed") g.fail = true;
    const sec = (j.step_secs || {})[String(s.id).split(":")[0]]; if (sec && !String(s.id).includes(":")) g.secs += sec;
  }
  const cur = groups.findIndex(g => g.run);
  const now = TL_GROUPS[cur >= 0 ? cur : tlGroupOf(pr.step)];
  const rows = groups.map((g, i) => {
    if (!g.n) return "";
    const st = g.fail ? "failed" : g.run ? "running" : g.done === g.n ? "done" : "pending";
    const mark = st === "done" ? "✓" : st === "running" ? "●" : st === "failed" ? "✕" : "";
    const time = st === "done" && g.secs ? fmtDur(g.secs) : st === "running" ? "now" : st === "pending" ? "waiting" : "";
    return `<li class="tlp-s ${st}"><i>${mark}</i><span>${esc(TL_GROUPS[i][0])}</span><em>${time}</em></li>`;
  }).join("");
  const stuck = pr.stuck_s ? `<div class="tlp-stuck">⚠ Nothing has moved for ${tlAgo(pr.stuck_s)}. It may be stuck. <button class="sm" data-tab-go="pipeline">See what it's doing</button></div>` : "";
  return `<div class="prog running tlp ${compact ? "compact" : ""}">
    <div class="tlp-head"><b>${esc(tlJobKind(j))}</b><span class="tlp-pct" data-tl-pct="${j.id}">${Math.floor(c.shown)}%</span><span class="muted" data-tl-left="${j.id}">${tlLeft(left)}</span>
      <span class="tlp-live ${pr.stuck_s ? "bad" : ""}"><i></i>Still working · last update <span data-tl-ago="${j.id}">${tlAgo(ago)}</span> ago</span></div>
    <div class="prog-bar"><i data-tl-bar="${j.id}" style="width:${c.shown.toFixed(2)}%"></i></div>
    ${compact ? "" : `<div class="tlp-now"><span class="muted tiny">RIGHT NOW</span><b>${esc(now[0])}</b><span class="muted small">${esc(now[1])}${pr.step ? ` <span class="dim">(${esc(String(pr.step).slice(0, 60))})</span>` : ""}</span></div>
    ${stuck}<ol class="tlp-list">${rows}</ol>
    <div class="muted tiny">You can keep working or close this window. It keeps going and sends you a message when it's ready.</div>`}</div>`;
}
const _progressBar9 = progressBar;
progressBar = function (p) {
  const j = p.jobs[0];
  if (!j || j.status !== "running" || (j.queue || {}).state === "waiting" || (j.queue || {}).state === "ai") return _progressBar9(p);
  return tlProgressCard(j);
};

// ---------------------------------------------------------------- the project page = the editor, full window (2026-10-29,
// user: "make it look and feel like real editing software"): no app sidebar, no big header, no tab row. The other pages
// (Revisions, Build log, Sections + music, Shorts, Deliverables) open from the editor's "⋯ More" menu with a Back bar.
window.TL_MORE_ITEMS = window.TL_MORE_ITEMS || [];   // other files add {label, run(p)} entries (e.g. Export to Premiere)
function tlMoreMenu(btn, p) {
  const old = $("#tl-menu"); if (old) { old.remove(); return; }
  // "All changes" gone: the editor's Revise tab is that screen now (2026-10-29)
  const tabs = [["pipeline", "Build log"], ...(p.type === "gaming" ? [["sections", "Sections + music"]] : []), ["shorts", "Shorts"], ["deliver", "Deliverables"]];
  const m = document.createElement("div"); m.className = "ctx tl-menu"; m.id = "tl-menu";
  m.innerHTML = tlSizeRow() + "<hr>" + tabs.map(([k, l]) => `<a data-tab9="${k}">${l}</a>`).join("") + `<hr><a data-x="details">Project details</a><a data-x="folder">Open folder</a>` +
    (window.TL_MORE_ITEMS.length ? "<hr>" + window.TL_MORE_ITEMS.map((x, i) => `<a data-ext="${i}">${esc(x.label)}</a>`).join("") : "");
  document.body.appendChild(m);
  // the page may be zoomed (Text size): rects come back zoomed, style px are not, so convert (Extra large put the menu off screen)
  const r = btn.getBoundingClientRect(), k = (m.getBoundingClientRect().width / (m.offsetWidth || 1)) || 1;
  const W = innerWidth / k, H = innerHeight / k;
  m.style.maxHeight = (H - 16) + "px"; m.style.overflowY = "auto";
  m.style.top = Math.max(8, Math.min(r.bottom / k + 6, H - m.offsetHeight - 8)) + "px";
  m.style.left = Math.max(8, Math.min(r.right / k - m.offsetWidth, W - m.offsetWidth - 8)) + "px";
  m.onclick = e => {
    e.stopPropagation(); const a = e.target.closest("a"); if (!a) return; m.remove();
    if (a.dataset.tab9) { S.tab[p.id] = a.dataset.tab9; renderProject(); }
    else if (a.dataset.x === "details") tlDetails(p.id);
    else if (a.dataset.x === "folder") api("open", { path: p.path });
    else if (a.dataset.ext) { try { window.TL_MORE_ITEMS[+a.dataset.ext].run(p); } catch (err) { toast(err.message, "bad"); } }
  };
  setTimeout(() => document.addEventListener("click", function off() { m.remove(); document.removeEventListener("click", off); }), 0);
}
const _renderProject9 = renderProject;
renderProject = function () {
  const p = S.project;
  if (p && TL.openPid !== p.id) { TL.openPid = p.id; TL.panel = "transcript"; S.tab[p.id] = "editor"; }   // a project always opens in the editor (Revise)
  if (p && S.tab[p.id] === "review") S.tab[p.id] = "editor";
  if (p && !S.tab[p.id]) S.tab[p.id] = "editor";
  _renderProject9();
  document.body.classList.toggle("tl-full", !!p && S.view === "project");
  // the build progress goes right under the editor's bar; the old header (thumbnail, pills, details, tabs) stays hidden
  const prog = $("#p-progress"), tb = $("#tabbody");
  if (prog && tb) tb.parentElement.insertBefore(prog, tb);
  if (p && S.tab[p.id] !== "editor" && tb && !$("#tl-backbar")) {
    const bar = document.createElement("div"); bar.id = "tl-backbar"; bar.className = "tle-top";
    const names = { review: "All changes", pipeline: "Build log", sections: "Sections + music", shorts: "Shorts", deliver: "Deliverables", chat: "Ask Claude" };
    bar.innerHTML = `<button class="ghost sm" id="tl-toeditor">← Back to the editor</button><b class="tle-name">${esc(p.title)}</b><span class="muted small">· ${esc(names[S.tab[p.id]] || "")}</span><span class="grow"></span><button class="ghost sm" id="tl-more2">⋯ More</button>`;
    tb.parentElement.insertBefore(bar, prog || tb);
    $("#tl-toeditor").onclick = () => { S.tab[p.id] = "editor"; renderProject(); };
    $("#tl-more2").onclick = e => { e.stopPropagation(); tlMoreMenu(e.currentTarget, p); };
  }
};
// leaving the project page brings the app sidebar back
const _nav9 = nav;
nav = function (view, pid) { document.body.classList.toggle("tl-full", view === "project"); return _nav9(view, pid); };

// ---------------------------------------------------------------- time helpers (recording time <-> draft time)
function tlKeep() { const k = (ED.data.keep || []).filter(([a]) => a >= 0); return k.length ? k : [[0, ED.data.duration || 0]]; }
function tlDraftOf(raw) {   // recording time -> time in the draft (intro included)
  const d = ED.data; let acc = d.offset || 0;
  if (!(d.keep || []).length) return raw + acc;
  for (const [a, b] of d.keep) { if (a >= 0 && raw < a) return acc; if (a >= 0 && raw <= b) return acc + raw - a; acc += b - a; }   // inserted clips (negative times) still take draft time
  return acc;
}
function tlRawOf(t) {   // draft time -> recording time
  const d = ED.data; let acc = d.offset || 0; if (t < acc) return tlKeep()[0][0];
  if (!(d.keep || []).length) return t - acc;
  for (const [a, b] of d.keep) { if (t <= acc + (b - a)) return a >= 0 ? a + t - acc : b; acc += b - a; }
  return d.duration || 0;
}
function tlNowRaw() { const v = $("#ed-video"); if (!v) return 0; const r = tRaw(v.currentTime); return r == null ? tlKeep()[0][0] : r; }
const tlPct = t => `${(t / (ED.data.duration || 1)) * 100}%`;

// kept pieces after your edits: the AI's keep, plus everything put back, minus everything you cut, split where you split
function tlSegments() {
  let segs = tlKeep().map(([a, b]) => [a, b]);
  const union = (S0, a, b) => { const out = []; for (const [x, y] of S0) { if (y < a - 0.02 || x > b + 0.02) out.push([x, y]); else { a = Math.min(a, x); b = Math.max(b, y); } } out.push([a, b]); return out.sort((m, n) => m[0] - n[0]); };
  const minus = (S0, a, b) => { const out = []; for (const [x, y] of S0) { if (y <= a || x >= b) { out.push([x, y]); continue; } if (a - x > 0.05) out.push([x, a]); if (y - b > 0.05) out.push([b, y]); } return out; };
  for (const n of [...TX.E.filter(n => n.kind === "protect"), ...(TX.prot || [])]) segs = union(segs, n.raw0, n.raw1);
  for (const n of TX.E.filter(n => n.kind === "cut")) segs = minus(segs, n.raw0, n.raw1);
  const cuts = (TL.splits[S.project.id] || []).slice().sort((a, b) => a - b);
  const out = [];
  for (const [a, b] of segs) { let s = a; for (const c of cuts) if (c > s + 0.1 && c < b - 0.1) { out.push([s, c]); s = c; } out.push([s, b]); }
  return out;
}
function tlSections() {
  const d = ED.data;
  if ((d.sections || []).length) return d.sections.map(s => ({ name: s[0], a: s[1], b: s[2] }));
  return (d.draft_sections || []).map(s => ({ name: s[0], a: tlRawOf(s[1]), b: tlRawOf(s[2]) }));
}
const tlNoteRaw = n => n.raw0 != null ? [n.raw0, n.raw1 ?? n.raw0 + 3] : n.t0 != null ? [tlRawOf(n.t0), tlRawOf(n.t1 ?? n.t0 + 3)] : null;
const TL_TEXT_RX = /on-?screen text|add (a )?(big )?title|text on screen/i;

// ---------------------------------------------------------------- render
async function renderEditor(p) {
  const body = $("#tabbody"); body.innerHTML = `<div class="muted">loading the editor…</div>`;
  try { ED.data = await api("editor?id=" + p.id); } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  const d = ED.data, outs = d.outputs || [];
  const choices = [...outs.map(o => ({ label: o.kind === "final" ? "Final" : "Draft (preview quality)", kind: o.kind === "final" ? "final" : "draft", sub: base(o.file), file: o.file })),
    ...(d.source ? [{ label: "Raw recording", kind: "raw", sub: base(d.source), file: d.source }] : [])];
  const norm = f => String(f || "").replace(/\//g, "\\").toLowerCase(), home = norm(p.path).replace(/\\?$/, "\\");
  if (!(ED.playing && norm(ED.playing).startsWith(home))) ED.playing = "";
  const files = outs.map(o => o.file), newest = files.length ? files[files.length - 1] : d.source || "";
  if (ED.pid === p.id && ED.seen && files.some(f => !ED.seen.includes(f))) ED.playing = newest;
  if (ED.pid !== p.id) { TX.undo = []; TX.redo = []; TL.sel = null; }
  ED.pid = p.id; ED.seen = files;
  if (!ED.playing || !choices.some(c => c.file === ED.playing)) ED.playing = newest;
  TX.E = txEditable(d.notes); TX.prot = txOtherProtects(d.notes);
  TX.sents = txSentences(d.words);
  TX.cur = -1;
  let html = "";
  TX.sents.forEach((s, k) => {
    let ws = "";
    for (let i = s.i0; i <= s.i1; i++) ws += `<span class="w" data-i="${i}">${esc(d.words[i].w)}</span> `;
    html += `${s.para && k ? `<div class="tx-gap"></div>` : ""}<div class="snt" data-k="${k}"><button class="snt-x" tabindex="-1" title="Cut / uncut this sentence">✂</button><span class="snt-t">${fmtT(d.words[s.i0].s)}</span><div class="snt-w">${ws}</div></div>`;
  });
  const cur = choices.find(c => c.file === ED.playing) || { kind: "raw", label: "" };
  const drafts = choices.filter(c => c.kind === "draft"), draftNo = drafts.findIndex(c => c.file === ED.playing) + 1;
  TL.nextDraft = drafts.length + 1;
  const hasDraft = outs.some(o => o.kind !== "final");
  const rail = [["transcript", "Words", "M4 6h16M4 12h16M4 18h10"], ["clips", "Clips", "M3 5h18v14H3zM10 9l5 3-5 3z"], ["music", "Music", "M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM21 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z"],
    ["text", "Text", "M4 7V4h16v3M9 20h6M12 4v16"], ["captions", "Captions", "M3 5h18v14H3zM7 13h4M13 13h4M7 16h10"], ["transitions", "Transitions", "M4 4h7v16H4zM13 4h7v16h-7"]];
  const I = TL_ICON;
  body.innerHTML = `<div class="tle ${TL.drawer ? "drawer-on" : ""}" ${tlTlh() ? `style="--tlh:${tlTlh()}px"` : ""}>
    <div class="tle-top">
      <button class="tlb ghost" id="tle-home" title="Back to all projects">${I.back}Projects</button>
      <b class="tle-name" title="${esc(p.title)}">${esc(p.title)}</b>
      <select id="ed-src" class="tle-badge ${cur.kind}" title="What the player shows">${choices.map(c => `<option value="${esc(c.file)}" ${c.file === ED.playing ? "selected" : ""}>${esc(c.kind === "final" ? "Final video" : c.kind === "draft" ? `Draft ${drafts.indexOf(c) + 1}` : "Raw recording")}</option>`).join("")}</select>
      <span class="grow"></span>
      <a class="tle-count" id="tx-count" title="Your cuts. They go into the next draft."></a><span id="tx-save" hidden></span>
      <button class="tlb" id="tle-chgtog" title="Open your list of changes">${I.list}Changes <b id="tle-chgn"></b></button>
      <button class="tlb ghost" id="tle-more" title="Text size, Revisions, Build log, Shorts, Deliverables, Project details">${I.dots}More</button>
      <button class="tlb ok" id="tle-final" ${p.jobs.length || !hasDraft ? "disabled" : ""} title="${hasDraft ? "Render the full-quality video from this edit" : "Make a draft first"}">${I.check}Make final video</button>
    </div>
    <div class="tle-upper">
      <section class="tle-lib">
        <nav class="tle-rail tle-tabs">${rail.map(([k, l]) => `<button data-panel="${k}" class="${TL.panel === k ? "on" : ""}">${I[k]}${l}</button>`).join("")}</nav>
        <div class="tle-panel">
          <div class="tx tle-tx ${TX.hide ? "hide-cuts" : ""}" data-pane="transcript" ${TL.panel === "transcript" ? "" : "hidden"}>
            <details class="tle-adv"><summary><span>Click a word to jump. Select words to cut.</span><span class="grow"></span><button class="tlb sm" id="tx-fill" title="Cut every um and uh">${I.cut}Remove ums</button><span class="tle-advlbl">More ▾</span></summary>
              <div class="tx-tools tle-txtools">
                <label class="tog" title="Hide everything that is cut (H)"><input type="checkbox" id="tx-hide" ${TX.hide ? "checked" : ""}><i></i>Hide cut words</label>
                <label class="tog" title="Playback jumps over your cuts"><input type="checkbox" id="tx-prev" ${TX.preview ? "checked" : ""}><i></i>Skip cuts when playing</label>
                <button class="tlb sm ghost" id="tx-keys">Keyboard keys</button>
              </div>
              <div class="tx-help" id="tx-help" style="display:none">
                <div><kbd>Space</kbd> play or pause</div><div><kbd>S</kbd> split at the playhead</div><div><kbd>Delete</kbd> cut the selected words or clip</div>
                <div><kbd>←</kbd> <kbd>→</kbd> step word by word</div><div><kbd>Ctrl</kbd>+<kbd>Z</kbd> undo · <kbd>Ctrl</kbd>+<kbd>Y</kbd> redo</div><div><kbd>Ctrl</kbd>+<kbd>+</kbd> / <kbd>−</kbd> text size</div>
              </div>
            </details>
            <div class="tx-body" id="ed-tr">${html || `<div class="empty">No words yet. They appear after the first draft is made.</div>`}</div>
            <div class="tx-bubble" id="tx-bubble"><button class="danger" id="tb-cut">✂ <span>Cut</span></button><button id="tb-prot" title="Keep these words even if the AI cut them">Keep</button><button id="tb-broll" title="Show a clip over these words">B-roll</button><button id="tb-short" title="Make a Short from this">Short</button><span class="tb-info" id="tb-info"></span></div>
            <div class="tx-flash" id="tx-flash"></div>
          </div>
          <div data-pane="other" id="tle-pane" ${TL.panel === "transcript" ? "hidden" : ""}></div>
          <div data-pane="clip" id="tle-clippane" hidden>
            <div class="tle-ph"><b id="tle-clipname">Selected clip</b><span class="tiny" id="tle-cliptime"></span></div>
            <div class="tle-clipbtns"><button class="tlb" data-clipdo="zoom">${I.zoomin}Zoom in closer</button><button class="tlb" data-clipdo="louder">${I.louder}Make it louder</button>
              <button class="tlb" data-clipdo="quieter">${I.quieter}Make it quieter</button><button class="tlb" data-clipdo="delete">${I.trash}Delete this clip</button></div>
            <button class="tlb ghost" id="tle-clipdone">${I.check}Done</button>
          </div>
        </div>
      </section>
      <section class="tle-player">
        ${ED.playing ? `<video id="ed-video" controls preload="metadata" src="${mediaUrl(ED.playing)}"></video>` : `<div class="empty">No video yet. Add your recording (More → Project details) and the draft is made for you.</div>`}
        <span id="tle-dt" hidden></span>
      </section>
    </div>
    <div class="tle-split" id="tle-split" title="Drag to make the timeline taller or shorter"></div>
    <div class="tle-tools">
      <button class="tlb" id="tx-undo" title="Undo (Ctrl+Z)">${I.undo}Undo</button>
      <button class="tlb" id="tx-redo" title="Redo (Ctrl+Y)">${I.redo}Redo</button>
      <span class="tle-sep"></span>
      <button class="tlb" id="tl-split" title="Split the clip at the playhead (S)">${I.cut}Split</button>
      <button class="tlb" id="tl-del" title="Remove the selected clip (Delete)" disabled>${I.trash}Delete</button>
      <button class="tlb" id="tl-back" title="Put the selected cut part back" disabled>${I.restore}Bring back</button>
      <span class="tle-selinfo" id="tl-selinfo"></span>
      <span class="grow"></span>
      <button class="tlb" id="tl-zout" title="Zoom the timeline out">${I.minus}Zoom out</button>
      <button class="tlb" id="tl-zin" title="Zoom the timeline in">${I.plus}Zoom in</button>
    </div>
    <div class="tle-tl">
      <div class="tle-body"><div class="tle-heads">${[["", "", ""], ["Parts", "parts", "The parts of your video"], ["Main video", "main", "Your recording"], ["B-roll", "clips", "Your extra clips"], ["Text", "text", "Titles and labels"], ["Music", "music", "Music added for you"], ["Captions", "captions", "Words on screen"]].map(([h, ic, t]) => `<div title="${t}">${ic ? I[ic] : ""}<span>${h}</span></div>`).join("")}</div>
        <div class="tle-scroll" id="tle-scroll"><div class="tle-inner" id="tle-inner" style="width:${TL.zoom * 100}%">
          <div class="tle-lanes" id="ed-tl"><div id="tle-lanes"></div><div class="tl-head tle-head" id="ed-head"><span id="ed-time">0:00</span></div></div>
        </div></div></div>
    </div>
    <aside class="tle-drawer" id="tle-changes" aria-label="Your changes"></aside>
  </div>`;
  tlChanges();   // first: it makes #tx-build, which txWire wires
  txWire(p);
  tlWire(p);
  txPaint();
  tlPanel(p);
}

// big line icons for the editor (24 px, currentColor)
const TL_ICON = (() => {
  const s = d => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${d}"/></svg>`;
  return {
    back: s("M15 5l-7 7 7 7"), list: s("M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"), dots: s("M5 12h.01M12 12h.01M19 12h.01"),
    check: s("M5 12l5 5L20 7"), undo: s("M9 14L4 9l5-5M4 9h11a5 5 0 0 1 0 10h-3"), redo: s("M15 14l5-5-5-5M20 9H9a5 5 0 0 0 0 10h3"),
    cut: s("M6 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM20 4L8.1 15.9M14.5 14.5L20 20M8.1 8.1L12 12"),
    trash: s("M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"), restore: s("M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5"),
    plus: s("M12 5v14M5 12h14"), minus: s("M5 12h14"), zoomin: s("M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14zM21 21l-4.3-4.3M11 8v6M8 11h6"),
    louder: s("M11 5L6 9H2v6h4l5 4zM15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"), quieter: s("M11 5L6 9H2v6h4l5 4zM15.5 8.5a5 5 0 0 1 0 7"),
    transcript: s("M4 6h16M4 12h16M4 18h10"), words: s("M4 6h16M4 12h16M4 18h10"), clips: s("M3 5h18v14H3zM10 9l5 3-5 3z"), main: s("M3 5h18v14H3zM10 9l5 3-5 3z"),
    music: s("M9 18V5l12-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM21 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z"), text: s("M4 7V4h16v3M9 20h6M12 4v16"),
    captions: s("M3 5h18v14H3zM7 13h4M13 13h4M7 16h10"), transitions: s("M4 4h7v16H4zM13 4h7v16h-7"), parts: s("M4 4v16M10 4v16M16 4v16M4 12h16"),
  };
})();
function tlTlh() { try { return +localStorage.getItem("studio.tlh") || 0; } catch (e) { return 0; } }
const TL_ZOOMS = [1, 1.5, 2, 3, 4, 6, 8, 12, 16, 24];

function tlDraw() {
  const el = $("#tle-lanes"); if (!el || !ED.data) return;
  const d = ED.data, dur = d.duration || 1;
  // ruler: labels at least ~120 px apart at this zoom, so they never crowd
  const W = ($("#tle-scroll") || el).clientWidth * TL.zoom || 1000, pxs = W / dur;
  const step = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600].find(s => s * pxs >= 120) || 3600;
  let ruler = ""; for (let t = 0; t <= dur; t += step) ruler += `<span style="left:${tlPct(t)}">${fmtT(t)}</span>`;
  const notes = S.project.notes || [];
  ruler += notes.map(n => !n.done && !n.batch && !n.off ? tlNoteRaw(n) : null).filter(Boolean)
    .map(r => `<i class="tle-tick" style="left:${tlPct(r[0])}" title="a change at ${fmtT2(tlDraftOf(r[0]))} in the draft"></i>`).join("");
  // parts
  const secs = tlSections();
  const parts = secs.length ? secs.map((s, i) => `<div class="tle-sec c${i % 6}" style="left:${tlPct(s.a)};width:${tlPct(Math.max(0.5, s.b - s.a))}" title="${esc(s.name)} · ${fmtT(s.a)}–${fmtT(s.b)}">${esc(s.name)}</div>`).join("")
    : `<div class="tle-empty"><span>${d.offset ? `The intro (${Math.round(d.offset)} s) is made for you and plays before this` : "This video has no parts"}</span></div>`;
  // main video: kept clips with a frame from each, gaps where the AI or you cut
  const segs = tlSegments(), secOf = t => (secs.find(s => t >= s.a - 0.01 && t < s.b) || {}).name;
  const youCut = TX.E.filter(n => n.kind === "cut"), youKept = TX.E.filter(n => n.kind === "protect");
  const sel = TL.sel || {}, crop = S.project.thumb_crop || null;
  let main = "", prev = 0;
  segs.forEach(([a, b], i) => {
    if (a - prev > 0.05) main += `<div class="tle-gap ${youCut.some(n => n.raw1 > prev + 0.05 && n.raw0 < a - 0.05) ? "you" : ""} ${sel.type === "gap" && Math.abs(sel.a - prev) < 0.01 ? "sel" : ""}" data-gap="${prev},${a}" style="left:${tlPct(prev)};width:${tlPct(a - prev)}" title="Cut out: ${fmtT2(prev)}–${fmtT2(a)} (${(a - prev).toFixed(1)} s). Click it, then Bring back."></div>`;
    const wide = (b - a) * pxs;
    const img = d.source && wide > 60 ? `<img loading="lazy" alt="" src="${thumbUrl(d.source, crop, Math.round((a + b) / 2), 200)}">` : "";
    main += `<div class="tle-clip main ${youKept.some(n => n.raw1 > a && n.raw0 < b) ? "you" : ""} ${sel.type === "main" && Math.abs(sel.a - a) < 0.01 ? "sel" : ""}" data-seg="${a},${b}" style="left:${tlPct(a)};width:${tlPct(b - a)}" title="${fmtT2(a)}–${fmtT2(b)} · ${(b - a).toFixed(1)} s">
      ${img}<i class="h l" data-edge="l"></i><span>${wide > 70 ? esc(secOf(a) || (i === segs.length - 1 && i > 1 ? "Ending" : `Part ${i + 1}`)) : ""}</span><i class="h r" data-edge="r"></i></div>`;
    prev = b;
  });
  if (dur - prev > 0.05) main += `<div class="tle-gap" data-gap="${prev},${dur}" style="left:${tlPct(prev)};width:${tlPct(dur - prev)}"></div>`;
  // b-roll + text notes
  const brolls = [], texts = [];
  notes.forEach((n, idx) => {
    if (n.off) return;
    const r = tlNoteRaw(n); if (!r) return;
    if (n.kind === "broll") brolls.push({ n, idx, a: r[0], b: Math.max(r[1], r[0] + 0.5) });
    else if (n.kind === "text" && TL_TEXT_RX.test(n.text || "")) texts.push({ n, idx, a: r[0], b: Math.max(r[1], r[0] + 1) });
  });
  const blk = (x, type, label) => `<div class="tle-clip ${type} ${x.n.done ? "done" : ""} ${sel.type === type && sel.idx === x.idx ? "sel" : ""}" data-note="${x.idx}" data-type="${type}" style="left:${tlPct(x.a)};width:${tlPct(x.b - x.a)}" title="${esc(x.n.text || "")}${x.n.done ? " (already in the draft)" : " (comes in on the next draft)"}">${type === "broll" ? `<i class="h l" data-edge="l"></i>` : ""}<span>${esc(label)}</span>${type === "broll" ? `<i class="h r" data-edge="r"></i>` : ""}</div>`;
  const broll = brolls.map((x, i) => blk(x, "broll", `Extra clip ${i + 1}`)).join("") || `<div class="tle-empty"><span>Drag a clip here from Clips</span></div>`;
  const text = texts.map(x => blk(x, "text", ((x.n.text || "").match(/[“"]([^”"]+)[”"]/) || [, "Text"])[1])).join("") || `<div class="tle-empty"><span>Add a title from Text</span></div>`;
  // music
  const m = d.music, mp = tlMusicParts();
  const mblk = (a, b, tr) => `<div class="tle-clip music" data-music="1" style="left:${tlPct(a)};width:${tlPct(Math.max(1, b - a))}" title="${esc(tr)}"><span>♪ ${esc(base(tr).replace(/\.[^.]+$/, ""))}</span></div>`;
  let music = "";
  if (mp.length && mp.every(x => x.a != null && x.b != null)) music = mp.map(x => mblk(x.a, x.b, x.track)).join("");
  else if (mp.length) { const k = tlKeep(), a0 = k[0][0], b0 = k[k.length - 1][1], w = (b0 - a0) / mp.length; music = mp.map((x, i) => mblk(a0 + i * w, a0 + (i + 1) * w, x.track)).join(""); }
  if (!music) music = `<div class="tle-clip music auto" data-music="1" style="left:0;width:100%"><span>♪ Music is picked for you · click to change it</span></div>`;
  const cap = (d.settings || {}).captions, capOn = cap === true || (cap && cap.on);
  const capLabel = capOn ? (CAP_META[(cap && cap.style) || "bold"] || {}).label || (cap && cap.style) || "on" : "";
  const caps = capOn ? `<div class="tle-clip caps" data-caps="1" style="left:0;width:100%"><span>Captions · ${esc(String(capLabel).split(" · ")[0])}</span></div>`
    : `<div class="tle-empty" data-caps="1"><span>Captions are off · turn them on in Captions</span></div>`;
  el.innerHTML = `<div class="tle-ruler">${ruler}</div><div class="tle-lane parts">${parts}</div><div class="tle-lane main" data-lane="main">${main}</div>
    <div class="tle-lane broll" data-lane="broll">${broll}</div><div class="tle-lane text" data-lane="text">${text}</div>
    <div class="tle-lane music">${music}</div><div class="tle-lane caps">${caps}</div>`;
  tlSelInfo();
}

function tlSelInfo() {
  const s = TL.sel, info = $("#tl-selinfo"); if (!info) return;
  $("#tl-del").disabled = !s || s.type === "gap";
  $("#tl-back").disabled = !s || s.type !== "gap";
  const cp = $("#tle-clippane"), clipOn = !!s && (s.type === "main" || s.type === "broll");
  if (cp) {
    cp.hidden = !clipOn;
    $("[data-pane=transcript]").hidden = clipOn || TL.panel !== "transcript"; $("#tle-pane").hidden = clipOn || TL.panel === "transcript";
    if (clipOn) { $("#tle-clipname").textContent = s.type === "broll" ? "B-roll clip" : "Clip from your recording"; $("#tle-cliptime").textContent = s.type === "main" ? `${fmtT(tlDraftOf(s.a))} to ${fmtT(tlDraftOf(s.b))} in the draft · ${(s.b - s.a).toFixed(1)} s` : ""; }
  }
  info.textContent = !s ? "" : s.type === "gap" ? `Cut part · ${(s.b - s.a).toFixed(1)} s` : s.type === "main" ? `Clip · ${(s.b - s.a).toFixed(1)} s` : s.type === "broll" ? "B-roll clip" : "Title";
}

// ---------------------------------------------------------------- changes (revisions in plain words)
const TL_CHIPS = ["Remove the ums", "Cut this part", "Add B-roll here"], TL_CHIPS_MORE = ["Make the intro shorter", "Zoom in here", "Music quieter under my voice", "Bigger title here", "Slow this part down"];
function tlChanges() {
  const box = $("#tle-changes"); if (!box) return;
  const p = S.project, notes = p.notes || [];
  const old = $("#tle-chg"), typed = old ? old.value : "", focused = old && document.activeElement === old;
  const pending = notes.map((n, idx) => ({ n, idx })).filter(x => !x.n.done && !x.n.batch && !x.n.off);
  const label = n => {
    const t = (n.text || "").replace(/^note\s+/i, "").replace(/“/g, "“");
    return t;
  };
  const cnt = $("#tle-chgn"); if (cnt) cnt.textContent = pending.length ? `(${pending.length})` : "";
  box.innerHTML = `<div class="tle-dhead"><b>Your changes</b><button class="tlb ghost" id="tle-dclose" title="Close">✕ Close</button></div>
    <div class="tle-add"><textarea id="tle-chg" data-mic="note" rows="3" placeholder="What should change here? e.g. cut the part where I cough"></textarea>
      <div class="row"><button class="primary sm" id="tle-addbtn">＋ Add change</button><span class="muted tiny" id="tle-at"></span></div>
      <div class="tle-chips">${TL_CHIPS.map(c => `<button class="chip" data-chip="${esc(c)}">${esc(c)}</button>`).join("")}<button class="chip ghost" id="tle-chipmore">more ▾</button></div>
      <div class="tle-chips" id="tle-chips2" hidden>${TL_CHIPS_MORE.map(c => `<button class="chip" data-chip="${esc(c)}">${esc(c)}</button>`).join("")}</div></div>
    <div class="tle-list">${pending.length ? pending.map(({ n, idx }) => `<div class="tle-chg ${n.status === "claude" ? "busy" : ""}" data-idx="${idx}" data-nid="${esc(n.nid || "")}">
        <span class="k ${n.kind}">${esc({ cut: "Cut", protect: "Keep", broll: "B-roll", text: "Change", section: "Part" }[n.kind] || n.kind)}</span>
        <span class="t" title="${esc(n.text || "")}">${esc(label(n))}</span><button class="x" title="remove this change">✕</button></div>`).join("")
      : `<div class="empty small">No changes yet. Edit the timeline or add one above.</div>`}</div>
    <div class="tle-apply"><button class="primary" id="tx-build" ${p.jobs.length || !pending.length ? "disabled" : ""}>▶ ${pending.length ? `Apply ${pending.length} change${pending.length > 1 ? "s" : ""} · make Draft ${TL.nextDraft || 2}` : "Apply changes"}</button>
      ${p.jobs.length ? `<span class="muted tiny">A build is running. New changes go into the next one.</span>` : ""}</div>`;
  // the Apply button reuses the cutter's handler (sends every revision, then rebuilds)
  const b = $("#tx-build");
  b.onclick = async e => {
    await TX.sync;
    withBusy(e.target, "sending…", async () => {
      const r = await api("project/rebuild-notes?id=" + p.id, {});
      toast(r.mode === "claude" ? `Sent ${r.text_notes} written change(s) to Claude; you get a message when the draft is ready` : "Making a new draft with your changes", "ok");
      await loadProject(); pollJobs(p.id);
    });
  };
  const at = tlAt;
  tlShowAt();
  if (typed) { $("#tle-chg").value = typed; if (focused) $("#tle-chg").focus(); }
  const add = async text => {
    text = (text || "").trim(); if (!text) return;
    const t = at(), hasTime = /\b\d{1,2}:\d{2}(\.\d+)?\b/.test(text);
    const line = /^(cut|protect|keep|broll|b-roll|section|note)\b/i.test(text) && hasTime ? text : hasTime ? `note ${text}` : `note ${fmtT2(t)}-${fmtT2(t + 3)}: ${text}`;
    try { S.project = await api("project/notes?id=" + p.id, { text: line }); ED.data.notes = S.project.notes; toast(`Change added at ${fmtT2(t)}`, "ok"); $("#tle-chg") && ($("#tle-chg").value = ""); tlChanges(); tlDraw(); }
    catch (err) { toast(err.message, "bad"); }
  };
  $("#tle-addbtn").onclick = () => add($("#tle-chg").value);
  $("#tle-dclose").onclick = () => tlDrawer(false);
  $("#tle-chipmore").onclick = e => { const c = $("#tle-chips2"); c.hidden = !c.hidden; e.currentTarget.textContent = c.hidden ? "more ▾" : "less ▴"; };
  $("#tle-chg").onkeydown = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); add(e.target.value); } };
  $$("[data-chip]", box).forEach(c => c.onclick = () => {
    if (c.dataset.chip === "Remove the ums") return $("#tx-fill").click();
    add(c.dataset.chip);
  });
  $$(".tle-chg .x", box).forEach(x => x.onclick = async () => {
    const row = x.closest(".tle-chg"), nid = row.dataset.nid;
    if (nid && TX.E.some(n => n.nid === nid)) { txApply(TX.E.filter(n => n.nid !== nid), "change removed"); return; }
    try { S.project = await api("project/notes?id=" + p.id, { remove: +row.dataset.idx }); ED.data.notes = S.project.notes; tlChanges(); tlDraw(); } catch (err) { toast(err.message, "bad"); }
  });
  $$(".tle-chg .t", box).forEach(t => t.onclick = () => {
    const n = notes[+t.closest(".tle-chg").dataset.idx]; const r = n && tlNoteRaw(n); const vv = $("#ed-video");
    if (r && vv) { vv.currentTime = Math.max(0, tOut(r[0])); }
  });
}

function tlAt() { const v = $("#ed-video"); const t = v ? (ED.playing === ED.data.source ? tlDraftOf(v.currentTime) : v.currentTime) : 0; return Math.max(0, t); }
function tlShowAt() { const el = $("#tle-at"); if (el) el.textContent = `at ${fmtT2(tlAt())} in the draft`; }

function tlDrawer(on) {
  TL.drawer = on; const t = $(".tle"); if (t) t.classList.toggle("drawer-on", on);
  const b = $("#tle-chgtog"); if (b) b.classList.toggle("on", on);
  if (on) setTimeout(() => $("#tle-chg") && $("#tle-chg").focus(), 50);
}
// clip settings (shown only while a clip is selected): each one is a change for the next draft
function tlClipDo(p, what) {
  const s = TL.sel; if (!s) return;
  let a = s.a, b = s.b;
  if (s.type === "broll") { const n = S.project.notes[s.idx], r = n && tlNoteRaw(n); if (r) [a, b] = r; }
  const da = tlDraftOf(a), db = tlDraftOf(b);
  if (what === "delete") return tlDelete();
  const say = { zoom: "zoom in closer on this part", louder: "make my voice louder in this part", quieter: "make this part quieter" }[what];
  api("project/notes?id=" + p.id, { text: `note ${fmtT2(da)}-${fmtT2(db)}: ${say}` })
    .then(r => { S.project = r; ED.data.notes = r.notes; tlChanges(); tlDraw(); toast("Added to your changes", "ok"); }).catch(e => toast(e.message, "bad"));
}

// the cutter calls txCount after every cut and every save: keep the timeline + Changes list in step
const _txCount9 = txCount;
txCount = function () {
  _txCount9();
  if (!$("#tle-lanes")) return;
  clearTimeout(TL.redraw);
  TL.redraw = setTimeout(() => { tlDraw(); tlChanges(); }, 60);
};

// ---------------------------------------------------------------- side panels
async function tlPanel(p) {
  if (TL.sel && (TL.sel.type === "main" || TL.sel.type === "broll")) { TL.sel = null; tlDraw(); }   // a library tab closes the clip settings
  const cp = $("#tle-clippane"); if (cp) cp.hidden = true;
  $$(".tle-rail button").forEach(b => b.classList.toggle("on", b.dataset.panel === TL.panel));
  const tx = $("[data-pane=transcript]"), other = $("#tle-pane");
  if (!tx || !other) return;
  tx.hidden = TL.panel !== "transcript"; other.hidden = TL.panel === "transcript";
  const d = ED.data, st = d.settings || {};
  const head = (t, s) => `<div class="tle-ph"><b>${t}</b><span class="muted tiny">${s}</span></div>`;
  if (TL.panel === "clips") {
    const items = d.broll_files || [];
    other.innerHTML = head("Clips", "Drag a clip onto the B-roll row of the timeline, where you want it to show.") +
      `<div class="tle-items">${d.source ? `<div class="tle-item main"><div class="tile-img" style="background-image:url('${thumbUrl(d.source, S.project.thumb_crop || null, 30, 320)}')"></div><span class="grow">Your recording</span></div>` : ""}
      ${items.map(f => `<div class="tle-item" draggable="true" data-clip="${esc(f)}" title="${esc(f)}"><div class="tile-img" style="background-image:url('${thumbUrl(f, null, 1, 320)}')"></div><span class="grow">${esc(base(f).replace(/\.[^.]+$/, ""))}</span><small>Drag onto the B-roll row</small></div>`).join("")}
      ${items.length ? "" : `<div class="muted small">No extra clips yet. Add close-ups, screen recordings or anything to show over your talking.</div>`}</div>
      <button class="sm" id="tle-addclips">＋ Add clips…</button>`;
    $("#tle-addclips").onclick = async () => { const ps = await pickFiles("video", true); if (ps.length) { await addToSlot(p, "broll", ps); TL.panel = "clips"; } };
    $$("[data-clip]", other).forEach(el => el.ondragstart = e => { e.dataTransfer.setData("text/tl-clip", el.dataset.clip); e.dataTransfer.effectAllowed = "copy"; document.body.classList.add("tl-dragging"); });
    $$("[data-clip]", other).forEach(el => el.ondragend = () => document.body.classList.remove("tl-dragging"));
  } else if (TL.panel === "music") {
    tlMusicPanel(p, other);
  } else if (TL.panel === "text") {
    const kinds = [["Big title", "a big title across the middle"], ["Label", "a small label near the bottom"], ["Price / number", "a price or number pop-up"], ["Subscribe reminder", "a subscribe reminder"]];
    other.innerHTML = head("Text", "Words that show on screen. They're added at the time the video is at, for about 3 seconds.") +
      `<label class="tle-field">Words to show<input id="tle-words" placeholder="e.g. Worth it?"></label>
      <div class="tle-kinds">${kinds.map(([k, w], i) => `<label class="tle-kind"><input type="radio" name="tle-kind" value="${i}" ${i ? "" : "checked"}><span><b>${k}</b><small>${w}</small></span></label>`).join("")}</div>
      <button class="primary sm" id="tle-addtext">＋ Add at the current time</button>`;
    $("#tle-addtext").onclick = () => {
      const w = $("#tle-words").value.trim(); if (!w) return toast("Type the words to show", "bad");
      const k = kinds[+($("[name=tle-kind]:checked") || { value: 0 }).value];
      $("#tle-chg").value = `add on-screen text “${w}” as ${k[1]}`; $("#tle-addbtn").click(); $("#tle-words").value = "";
    };
  } else if (TL.panel === "captions") {
    const cap = st.captions, on = cap === true || (cap && cap.on), style = (cap && cap.style) || "bold";
    const presets = Object.values(CAP_META || {}).filter(x => x.pick !== false);
    other.innerHTML = head("Captions", "The words you say, shown on screen as you talk. Pick a look; it's added on the next build.") +
      `<label class="tog tle-capon"><input type="checkbox" id="tle-capon" ${on ? "checked" : ""}><i></i>Show captions</label>
      <div class="tle-caps">${presets.map(x => `<button class="tle-cap ${x.key === style ? "on" : ""}" data-cap="${esc(x.key)}" title="${esc(x.label)}"><img src="${esc(x.png || "captions/" + x.key + ".png")}" alt=""><span>${esc(String(x.label).split(" · ")[0])}</span></button>`).join("") || `<div class="muted small">No caption styles found.</div>`}</div>
      <p class="muted tiny">Gaming list videos never get captions at the bottom.</p>`;
    const save = async (patch, msg) => { try { S.project = await api("project/update?id=" + p.id, { settings: { captions: patch } }); ED.data.settings = { ...st, captions: patch }; toast(msg, "ok"); tlPanel(p); tlDraw(); } catch (e) { toast(e.message, "bad"); } };
    $("#tle-capon").onchange = e => save({ on: e.target.checked, style }, e.target.checked ? "Captions on: they come in on the next build" : "Captions off");
    $$("[data-cap]", other).forEach(b => b.onclick = () => save({ on: true, style: b.dataset.cap }, "Caption style saved: it shows on the next build"));
  } else if (TL.panel === "transitions") {
    other.innerHTML = head("Transitions", "The animation between the parts of your video.") + `<div class="muted small">loading…</div>`;
    let r; try { r = await api("transitions?id=" + p.id); } catch (e) { other.innerHTML = head("Transitions", esc(e.message)); return; }
    if (TL.panel !== "transitions") return;
    const pick = r.chosen || "";
    other.innerHTML = head("Transitions", "The animation between the parts of your video.") +
      (r.applies ? `<div class="tle-items">
        <button class="tle-item tle-tr ${pick ? "" : "on"}" data-wipe=""><div class="tile-img">✦</div><span class="grow">Automatic</span><span><small>${r.auto ? "uses " + esc(base(r.auto).replace(/\.[^.]+$/, "")) : "picked for this video"}</small></span></button>
        ${r.items.map(x => `<button class="tle-item tle-tr ${pick.toLowerCase() === x.path.toLowerCase() ? "on" : ""}" data-wipe="${esc(x.path)}"><div class="tile-img">⇆</div><span class="grow">${esc(x.name)}</span><span><small>${x.where === "this video" ? "made for this video" : "library"}</small></span></button>`).join("")}</div>
        <p class="muted tiny">Shows on the next build. A video can have its own: put a file named “… transition.mov” in the project's Graphics folder.</p>`
        : `<p class="muted small">This kind of video goes from part to part with clean cuts. Transitions between parts are used in list videos (Gaming / Top 10).</p>
        <button class="chip" id="tle-wantwipe">Ask for a transition between parts</button>`);
    $$("[data-wipe]", other).forEach(b => b.onclick = async () => { try { S.project = await api("project/update?id=" + p.id, { settings: { wipe: b.dataset.wipe || null } }); toast(b.dataset.wipe ? "Transition saved: it shows on the next build" : "Back to the automatic transition", "ok"); tlPanel(p); } catch (e) { toast(e.message, "bad"); } });
    $("#tle-wantwipe") && ($("#tle-wantwipe").onclick = () => { $("#tle-chg").value = "add a short transition between each part of the video"; $("#tle-addbtn").click(); });
  }
}

// ---------------------------------------------------------------- Music panel: the real tracks (2026-10-29, user: "music can't be changed")
// "In this video" = the track each part got on the last build (timeline_info music), with a preview; the library = the music
// folder's _index.json (music_lib: moods, vocal scan), best tracks per mood. A pick is saved as the build's own input where one
// exists (gaming: settings.music per section) and as a written change everywhere else, applied on the next build.
const TL_MOODS = ["chill", "upbeat", "hype", "calm", "smooth", "emotional", "epic", "dark", "playful", "oldschool"];
function tlMusicParts() {
  const d = ED.data, m = d.music, out = [];
  if (m && !Array.isArray(m)) {
    for (const s of tlSections()) { const v = m[s.name]; if (v && v.track) out.push({ name: s.name, track: v.track, offset: v.offset || 0, a: s.a, b: s.b, key: s.name }); }
  } else if (Array.isArray(m)) {
    m.forEach((x, i) => {
      const tr = typeof x === "string" ? x : (x.track || x.file || "");
      const a = x.s != null ? tlRawOf(x.s) : null, b = x.e != null ? tlRawOf(x.e) : null;
      out.push({ name: x.part ? x.part[0].toUpperCase() + x.part.slice(1) : `Part ${i + 1}`, track: tr, offset: 0, a, b, ds: x.s, de: x.e, key: x.part || String(i) });
    });
  }
  if (!out.length && d.music_used) {   // review / phone builds: the tracks the music picker logged for this video
    const label = { intro: "Intro", main: "Body", outro: "Ending" };
    for (const [role, list] of Object.entries(d.music_used)) list.forEach((tr, i) => out.push({ name: (label[role] || role) + (list.length > 1 ? ` · beat ${i + 1}` : ""), track: tr, offset: 20, a: null, b: null, key: `${role}:${i}` }));
  }
  return out;
}
async function tlMusicLib() {
  if (TL.lib) return TL.lib;
  const root = (S.state?.settings || {}).music_root || "";
  if (!root) return (TL.lib = { root, tracks: [] });
  try {
    const r = await fetch(mediaUrl(root.replace(/[\\/]$/, "") + "\\_index.json")); if (!r.ok) throw new Error("no index");
    const j = await r.json(), t = j.tracks || {};
    // songs he right-clicked out (music/remove) stay hidden
    let gone = []; try { gone = (await api("music/removed")).removed || []; } catch (e) { gone = []; }
    TL.lib = { root, tracks: Object.entries(t).filter(([rel, v]) => (v.vocal || {}).verdict !== "rejected" && (v.usable || v.dur || 0) >= 40 && !gone.includes(rel.split(/[\\/]/).pop().toLowerCase()))
      .map(([rel, v]) => ({ rel, path: root.replace(/[\\/]$/, "") + "\\" + rel, name: rel.split(/[\\/]/).pop().replace(/\.[^.]+$/, ""), cat: v.cat || "", moods: v.moods || {}, bpm: v.bpm, dur: v.dur })) };
  } catch (e) { TL.lib = { root, tracks: [] }; }
  return TL.lib;
}
// right-click a song in either music list -> "Remove from library" (user 2026-10-29). The file stays on disk; the picker
// skips it from now on (music_lib.remove); the toast has Undo
// a toast with an Undo button (stays 8 s)
function toastUndo(msg, undo) {
  const t = document.createElement("div"); t.className = "toast ok"; t.textContent = msg + " ";
  const b = document.createElement("button"); b.className = "e2-btn sm"; b.textContent = "Undo"; b.style.marginLeft = "10px";
  b.onclick = () => { t.remove(); undo(); }; t.appendChild(b);
  $("#toasts").appendChild(t); setTimeout(() => t.remove(), 12000);
}
function tlSongMenu(e, path, redraw) {
  if (typeof MS_ROW !== "undefined") return;   // the kit's music_setup.js has its own song menu (remove + mood): that one wins
  e.preventDefault();
  $("#e2-ctx") && $("#e2-ctx").remove();
  const name = base(path).replace(/\.[^.]+$/, "");
  const m = document.createElement("div"); m.className = "ctx e2-ctx"; m.id = "e2-ctx";
  m.innerHTML = `<a data-a="rm" style="font-size:15px;font-weight:600">✕ Remove from my library</a>`;
  m.style.border = "1px solid #8a92a6"; m.style.boxShadow = "0 8px 28px rgba(0,0,0,.7)";   // stands out on the dark pop-up
  m.style.zIndex = 400;   // above the music pop-up (.e2-modal is 200)
  document.body.appendChild(m);
  const k = (m.getBoundingClientRect().width / (m.offsetWidth || 1)) || 1;
  m.style.left = Math.max(8, Math.min(e.clientX / k, innerWidth / k - m.offsetWidth - 8)) + "px"; m.style.top = Math.max(8, Math.min(e.clientY / k, innerHeight / k - m.offsetHeight - 8)) + "px";
  const keep = (TL.lib && TL.lib.tracks) || [];
  m.onclick = async ev => {
    if (!ev.target.closest("a")) return; m.remove();
    try { await api("music/remove", { path }); } catch (err) { return toast(/404|not found|unknown|no such route/i.test(err.message) ? "Close and reopen Studio once to turn this on" : err.message, "bad"); }
    try { TL.audio && TL.audio.pause(); const a = $("#tle-aud"); a && a.dataset.path === path && a.pause(); } catch (err) { }
    const i = keep.findIndex(t => t.path === path), gone = i >= 0 ? keep.splice(i, 1)[0] : null;
    redraw && redraw();
    toastUndo(`Removed “${name}”. It won't be picked again`, async () => {
      try { await api("music/remove", { path, undo: true }); if (gone) keep.splice(i, 0, gone); redraw && redraw(); toast(`“${name}” is back in your library`, "ok"); } catch (err) { toast(err.message, "bad"); }
    });
  };
  setTimeout(() => document.addEventListener("click", function off() { m.remove(); document.removeEventListener("click", off); }), 0);
}
function tlPreview(path, offset, btn) {
  let a = $("#tle-aud");
  if (!a) { a = document.createElement("audio"); a.id = "tle-aud"; document.body.appendChild(a); }
  if (a.dataset.path === path && !a.paused) { a.pause(); btn && (btn.textContent = "▶"); return; }
  $$(".tle-play").forEach(b => b.textContent = "▶");
  a.dataset.path = path; a.src = mediaUrl(path); a.currentTime = 0;
  a.onloadedmetadata = () => { a.currentTime = Math.min(offset || 0, Math.max(0, a.duration - 5)); };
  a.volume = 0.8; a.play().catch(() => {}); btn && (btn.textContent = "❚❚");
  a.onended = () => btn && (btn.textContent = "▶");
}
async function tlMusicPanel(p, el) {
  const parts = tlMusicParts();
  TL.mood = TL.mood || "chill";
  const pick = TL.musicFor != null ? parts.find(x => x.key === TL.musicFor) : null;
  const gaming = p.type === "gaming";
  el.innerHTML = `<div class="tle-ph"><b>Music</b><span class="muted tiny">Instrumentals only. Changes come in on the next build.</span></div>
    <div class="tle-sub">In this video</div>
    <div class="tle-items">${parts.length ? parts.map(x => `<div class="tle-item ${pick && pick.key === x.key ? "on" : ""}"><span class="grow" title="${esc(base(x.track))}">${esc(base(x.track).replace(/\.[^.]+$/, ""))}</span><small>${esc(x.name)}</small>
        <div class="row2"><button class="tle-play tlb" data-prev="${esc(x.track)}" data-off="${x.offset}" title="Listen">▶</button><button class="tlb sm" data-for="${esc(x.key)}">${pick && pick.key === x.key ? "Picking…" : "Change"}</button></div></div>`).join("")
      : `<div class="muted small">The next build picks music that fits. Pick one below to choose it yourself.</div>`}</div>
    <div class="tle-sub">${pick ? `Pick a track for <b>${esc(pick.name)}</b> <a id="tle-forall" class="tiny">or the whole video</a>` : "Library"}</div>
    ${!gaming ? `<label class="tle-field tle-join">Where the music changes <select id="tle-join"><option value="crossfade">Crossfade (1 s)</option><option value="cut">Hard cut</option><option value="fade">Fade out, then in</option></select></label>` : ""}
    <div class="tle-chips">${TL_MOODS.map(m => `<button class="chip ${TL.mood === m ? "on" : ""}" data-mood="${m}">${m}</button>`).join("")}</div>
    <input id="tle-msearch" placeholder="Search your music…" value="${esc(TL.msearch || "")}">
    <div class="tle-items" id="tle-lib"><div class="muted small">loading your music…</div></div>`;
  $$("[data-prev]", el).forEach(b => b.onclick = () => tlPreview(b.dataset.prev, +b.dataset.off, b));
  $$("[data-for]", el).forEach(b => b.onclick = () => { TL.musicFor = TL.musicFor === b.dataset.for ? null : b.dataset.for; tlMusicPanel(p, el); });
  $("#tle-forall") && ($("#tle-forall").onclick = () => { TL.musicFor = null; tlMusicPanel(p, el); });
  $$("[data-mood]", el).forEach(b => b.onclick = () => { TL.mood = b.dataset.mood; tlMusicPanel(p, el); });
  const lib = await tlMusicLib();
  const listEl = $("#tle-lib", el); if (!listEl) return;
  const draw = () => {
    const q = (TL.msearch || "").toLowerCase();
    const rows = lib.tracks.filter(t => !q || (t.rel || "").toLowerCase().includes(q))
      .sort((a, b) => (b.moods[TL.mood] || 0) - (a.moods[TL.mood] || 0)).slice(0, 40);
    listEl.innerHTML = rows.length ? rows.map(t => `<div class="tle-item"><span class="grow" title="${esc(t.name)}">${esc(t.name)}</span><small>${esc(t.cat)}${t.bpm ? ` · ${Math.round(t.bpm)} bpm` : ""}</small>
        <div class="row2"><button class="tle-play tlb" data-prev="${esc(t.path)}" data-off="20" title="Listen">▶</button>${pick ? `<button class="tlb sm" data-use="${esc(t.path)}" data-scope="part" title="Use for ${esc(pick.name)}">Use</button>` : ""}<button class="tlb sm ${pick ? "ghost" : ""}" data-use="${esc(t.path)}" data-scope="all" title="Use for the whole video">${pick ? "Whole video" : "Use"}</button></div></div>`).join("")
      : `<div class="muted small">${lib.tracks.length ? "Nothing matches." : "No music library found yet. Settings → music folder."}</div>`;
    $$("[data-prev]", listEl).forEach(b => b.onclick = () => tlPreview(b.dataset.prev, +b.dataset.off, b));
    $$("[data-use]", listEl).forEach(b => b.onclick = () => tlUseTrack(p, b.dataset.use, b.dataset.scope === "part" ? pick : null, parts));
    $$(".tle-item", listEl).forEach(r => { const u = r.querySelector("[data-use]"); u && (r.oncontextmenu = e => tlSongMenu(e, u.dataset.use, draw)); });
  };
  $("#tle-msearch", el).oninput = e => { TL.msearch = e.target.value; draw(); };
  draw();
}
async function tlUseTrack(p, path, part, parts) {
  const name = base(path).replace(/\.[^.]+$/, "");
  const join = ($("#tle-join") || {}).value || "crossfade";
  try {
    if (p.type === "gaming") {   // the gaming build reads settings.music[section].track (Sections + music uses the same)
      const keys = part ? [part.key] : (tlSections().map(s => s.name));
      const music = Object.fromEntries(keys.map(k => [k, { track: path }]));
      S.project = await api("project/update?id=" + p.id, { settings: { music } });
      ED.data.music = { ...(ED.data.music || {}), ...Object.fromEntries(keys.map(k => [k, { ...((ED.data.music || {})[k] || {}), track: path }])) };
      toast(`“${name}” saved for ${part ? part.name : "the whole video"}: the next build uses it`, "ok");
    } else {
      const how = { crossfade: "a 1 second crossfade", cut: "a hard cut", fade: "a fade out then fade in" }[join];
      const t0 = part && part.ds != null ? part.ds : 0, t1 = part && part.de != null ? part.de : tlDraftOf(ED.data.duration || 0);
      const text = `note ${fmtT2(t0)}-${fmtT2(t1)}: music: use “${name}” for ${part ? `the ${part.name.toLowerCase()} part` : "the whole video"} (file: ${path}), with ${how} where the music changes`;
      S.project = await api("project/notes?id=" + p.id, { text });
      ED.data.notes = S.project.notes;
      toast(`Added a change: “${name}” for ${part ? part.name : "the whole video"}`, "ok");
    }
    TL.musicFor = null; tlChanges(); tlDraw(); tlPanel(p);
  } catch (e) { toast(e.message, "bad"); }
}

// ---------------------------------------------------------------- wiring: timeline mouse + keys
function tlWire(p) {
  const d = ED.data, v = $("#ed-video"), dur = d.duration || 1;
  tlDraw(); tlChanges();
  const src = $("#ed-src");
  src.onchange = e => { ED.playing = e.target.value; renderEditor(p); };
  $$(".tle-rail button").forEach(b => b.onclick = () => { TL.panel = b.dataset.panel; tlPanel(p); });
  $("#tle-home").onclick = () => nav("projects");
  $("#tle-more").onclick = e => { e.stopPropagation(); tlMoreMenu(e.currentTarget, p); };
  $("#tle-chgtog").onclick = () => tlDrawer(!TL.drawer);
  // drag bar between the preview and the timeline (remembered)
  $("#tle-split").onmousedown = e => {
    e.preventDefault(); const tl = $(".tle-tl"), h0 = tl.offsetHeight, y0 = e.clientY, z = parseFloat(document.documentElement.style.zoom) || 1;
    const mv = ev => { const h = Math.max(150, Math.min(innerHeight / z - 260, h0 - (ev.clientY - y0) / z)); $(".tle").style.setProperty("--tlh", Math.round(h) + "px"); };
    const up = () => { window.removeEventListener("mousemove", mv); window.removeEventListener("mouseup", up); try { localStorage.setItem("studio.tlh", parseInt($(".tle").style.getPropertyValue("--tlh"))); } catch (err) { } tlDraw(); };
    window.addEventListener("mousemove", mv); window.addEventListener("mouseup", up);
  };
  $$("[data-clipdo]").forEach(b => b.onclick = () => tlClipDo(p, b.dataset.clipdo));
  $("#tle-clipdone").onclick = () => { TL.sel = null; tlDraw(); };
  $("#tle-final").onclick = async () => {
    if (!confirm("Make the final, full-quality video from this edit? Changes that aren't applied yet won't be in it.")) return;
    try { await api("project/run?id=" + p.id, { action: "final" }); toast("Making the final video. You get a message when it's ready", "ok"); await loadProject(); pollJobs(p.id); } catch (e) { toast(e.message, "bad"); }
  };
  if (v) v.addEventListener("timeupdate", () => {
    tlShowAt();
    const dt = $("#tle-dt"); if (dt) dt.textContent = ED.playing === d.source ? "recording time" : `draft ${fmtT(v.currentTime)}`;
    const sc = $("#tle-scroll"), head = $("#ed-head");
    if (sc && head && TL.zoom > 1 && !TL.drag) { const x = head.offsetLeft; if (x < sc.scrollLeft + 40 || x > sc.scrollLeft + sc.clientWidth - 40) sc.scrollLeft = x - sc.clientWidth / 3; }
  });
  const zoomTo = z => { TL.zoom = z; $("#tle-inner").style.width = TL.zoom * 100 + "%"; tlDraw(); $("#tl-zout").disabled = z <= TL_ZOOMS[0]; $("#tl-zin").disabled = z >= TL_ZOOMS[TL_ZOOMS.length - 1]; };
  $("#tl-zin").onclick = () => zoomTo(TL_ZOOMS.find(z => z > TL.zoom) || TL.zoom);
  $("#tl-zout").onclick = () => zoomTo([...TL_ZOOMS].reverse().find(z => z < TL.zoom) || TL.zoom);
  $("#tl-zout").disabled = TL.zoom <= 1;
  const lanes = $("#ed-tl");
  const rawAt = x => { const r = lanes.getBoundingClientRect(); return Math.max(0, Math.min(dur, ((x - r.left) / r.width) * dur)); };
  const snap = t => { let best = t, bd = 0.25; for (const w of d.words) { for (const e of [w.s, w.e]) { const dd = Math.abs(e - t); if (dd < bd) { bd = dd; best = e; } } } return best; };
  // a drag's mouseup also fires a click: swallow it so the playhead doesn't jump to where the drag ended
  $("#tle-scroll").addEventListener("click", e => { if (TL.justDragged) { e.stopPropagation(); TL.justDragged = false; } }, true);
  lanes.addEventListener("click", e => {
    const c = e.target.closest("[data-seg],[data-gap],[data-note],[data-music],[data-caps]");
    if (!c) { TL.sel = null; tlDraw(); return; }
    if (c.dataset.music) { TL.panel = "music"; tlPanel(p); return; }
    if (c.dataset.caps) { TL.panel = "captions"; tlPanel(p); return; }
    if (c.dataset.seg) { const [a, b] = c.dataset.seg.split(",").map(Number); TL.sel = { type: "main", a, b }; }
    else if (c.dataset.gap) { const [a, b] = c.dataset.gap.split(",").map(Number); TL.sel = { type: "gap", a, b }; }
    else if (c.dataset.note) { TL.sel = { type: c.dataset.type, idx: +c.dataset.note }; }
    tlDraw();
  });
  lanes.addEventListener("dblclick", e => { const g = e.target.closest("[data-gap]"); if (g) { const [a, b] = g.dataset.gap.split(",").map(Number); TL.sel = { type: "gap", a, b }; tlBringBack(); } });
  // edges: drag a clip edge out (bring cut material back) or in (cut it); drag a B-roll block to move it
  lanes.addEventListener("mousedown", e => {
    const h = e.target.closest("[data-edge]"), blk = e.target.closest("[data-note][data-type=broll]");
    if (!h && !blk) return;
    e.preventDefault(); e.stopPropagation();
    const c = (h || blk).closest(".tle-clip");
    const seg = c.dataset.seg ? c.dataset.seg.split(",").map(Number) : null;
    const note = c.dataset.note != null ? +c.dataset.note : null;
    const n = note != null ? S.project.notes[note] : null, r = n ? tlNoteRaw(n) : null;
    TL.drag = { c, edge: h ? h.dataset.edge : "move", seg, note, r, x0: e.clientX, t0: rawAt(e.clientX), moved: false };
    c.classList.add("drag");
  });
  window.onmousemove = e => {
    const g = TL.drag; if (!g) return;
    if (Math.abs(e.clientX - g.x0) > 3) g.moved = true;
    const t = snap(rawAt(e.clientX));
    let a, b;
    if (g.seg) { [a, b] = g.seg; const e2 = snap((g.edge === "l" ? a : b) + rawAt(e.clientX) - g.t0); if (g.edge === "l") a = Math.min(e2, b - 0.2); else b = Math.max(e2, a + 0.2); }
    else { [a, b] = g.r; const dt = t - g.t0; if (g.edge === "l") a = Math.min(a + dt, b - 0.5); else if (g.edge === "r") b = Math.max(b + dt, a + 0.5); else { a += dt; b += dt; } }
    a = Math.max(0, a); b = Math.min(dur, b);
    g.a = a; g.b = b;
    g.c.style.left = tlPct(a); g.c.style.width = tlPct(b - a);
    const info = $("#tl-selinfo"); if (info) info.textContent = `${fmtT2(a)}–${fmtT2(b)} (${(b - a).toFixed(1)} s)`;
  };
  window.onmouseup = async () => {
    const g = TL.drag; if (!g) return;
    TL.drag = null; g.c.classList.remove("drag");
    if (!g.moved || g.a == null) { tlDraw(); return; }
    TL.justDragged = true; setTimeout(() => { TL.justDragged = false; }, 50);
    if (g.seg) {
      const [a0, b0] = g.seg; let E = TX.E;
      if (g.edge === "l") { if (g.a < a0) E = txAdd(txSubtract(E, "cut", g.a, a0), "protect", g.a, a0); else E = txAdd(txSubtract(E, "protect", a0, g.a), "cut", a0, g.a); }
      else { if (g.b > b0) E = txAdd(txSubtract(E, "cut", b0, g.b), "protect", b0, g.b); else E = txAdd(txSubtract(E, "protect", g.b, b0), "cut", g.b, b0); }
      TL.sel = null;
      txApply(E, (g.edge === "l" ? g.a < g.seg[0] : g.b > g.seg[1]) ? "brought back" : "trimmed");
      return;
    }
    const n = S.project.notes[g.note]; if (!n) return tlDraw();
    try {
      S.project = await api("project/notes?id=" + p.id, { remove: g.note, kind: "broll", raw0: g.a, raw1: g.b, clip: n.clip || "", text: `broll ${fmtT2(g.a)}-${fmtT2(g.b)} “${txWordsText(g.a, g.b)}”` });
      ED.data.notes = S.project.notes; TL.sel = null; tlDraw(); tlChanges(); toast("B-roll moved", "ok");
    } catch (err) { toast(err.message, "bad"); tlDraw(); }
  };
  // drops from the Clips panel onto the B-roll row
  lanes.addEventListener("dragover", e => { if (e.dataTransfer.types.includes("text/tl-clip")) { e.preventDefault(); e.stopPropagation(); e.dataTransfer.dropEffect = "copy"; $("#drop-veil").classList.remove("on"); } });
  lanes.addEventListener("drop", async e => {
    const clip = e.dataTransfer.getData("text/tl-clip"); if (!clip) return;
    e.preventDefault(); e.stopPropagation(); document.body.classList.remove("tl-dragging"); $("#drop-veil").classList.remove("on");
    const a = snap(rawAt(e.clientX)), b = Math.min(dur, a + 4);
    try { S.project = await api("project/notes?id=" + p.id, { kind: "broll", raw0: a, raw1: b, clip: base(clip).replace(/\.[^.]+$/, ""), text: `broll ${fmtT2(a)}-${fmtT2(b)} “${txWordsText(a, b)}”` }); ED.data.notes = S.project.notes; tlDraw(); tlChanges(); toast("B-roll added: it comes in on the next build", "ok"); }
    catch (err) { toast(err.message, "bad"); }
  });
  $("#tl-split").onclick = () => tlSplit();
  $("#tl-del").onclick = () => tlDelete();
  $("#tl-back").onclick = () => tlBringBack();
  // keys: S splits, Delete / Backspace removes a selected clip; everything else stays the cutter's
  const txKeys = document.onkeydown;
  document.onkeydown = e => {
    if (!$("#tle-lanes")) return txKeys && txKeys(e);
    const tag = (e.target.tagName || "").toLowerCase();
    if (!(tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable) && !(e.ctrlKey || e.metaKey)) {
      if ((e.key === "s" || e.key === "S") && !TX.sel) { e.preventDefault(); tlSplit(); return; }
      if ((e.key === "Delete" || e.key === "Backspace") && TL.sel && !TX.sel) { e.preventDefault(); TL.sel.type === "gap" ? tlBringBack() : tlDelete(); return; }
    }
    return txKeys && txKeys(e);
  };
}
function tlSplit() {
  const t = tlNowRaw(), segs = tlSegments();
  if (!segs.some(([a, b]) => t > a + 0.1 && t < b - 0.1)) return toast("Move the playhead onto a clip to split it", "bad");
  const L = TL.splits[S.project.id] = TL.splits[S.project.id] || [];
  L.push(t); TL.sel = null; tlDraw(); txFlash("split at " + fmtT2(t));
}
function tlDelete() {
  const s = TL.sel; if (!s) return;
  if (s.type === "main") { TL.sel = null; txApply(txAdd(txSubtract(TX.E, "protect", s.a, s.b), "cut", s.a, s.b), "clip cut"); return; }
  if (s.type === "broll" || s.type === "text") {
    api("project/notes?id=" + S.project.id, { remove: s.idx }).then(r => { S.project = r; ED.data.notes = r.notes; TL.sel = null; tlDraw(); tlChanges(); toast("Removed", "ok"); }).catch(e => toast(e.message, "bad"));
  }
}
function tlBringBack() {
  const s = TL.sel; if (!s || s.type !== "gap") return;
  TL.sel = null; txApply(txAdd(txSubtract(TX.E, "cut", s.a, s.b), "protect", s.a, s.b), "brought back");
}

// ---------------------------------------------------------------- when videos get made (Queue page setting, 2026-10-29)
// settings.build_mode: "now" (default) | "overnight" (new builds + changes wait for settings.overnight_at, then run one after
// another) | "ask" (every build asks). The server only defers a build that says when; this wrapper adds it to the builds the
// user starts in the UI. Builds started by the revision AI (curl) and the scheduler never pass here, so they always run.
const tlMode = () => (S.state?.settings || {}).build_mode || "now";
const tlNight = () => (S.state?.settings || {}).overnight_at || "01:00";
function tlAskWhen(what) {
  return new Promise(resolve => {
    const m = modal(`<h2>When should this be made?</h2><p class="muted small">${esc(what)}</p>
      <div class="tlw-opts"><button class="primary" data-w="now">Right away</button><button data-w="tonight">Tonight at ${esc(tlNight())}</button>
      <label class="tlw-pick">Pick a time <input type="datetime-local" id="tlw-at"></label><button data-w="pick">Use that time</button></div>
      <div class="row" style="justify-content:flex-end;margin-top:10px"><button id="tlw-x">Cancel</button></div>`);
    $$("[data-w]", m).forEach(b => b.onclick = () => { const w = b.dataset.w === "pick" ? $("#tlw-at", m).value : b.dataset.w; if (!w) return toast("Pick a time first", "bad"); closeModal(); resolve(w); });
    $("#tlw-x", m).onclick = () => { closeModal(); resolve(null); };
  });
}
const _api9 = api;
api = async function (path, body, method) {
  const isRun = /^project\/run\?/.test(path) && body && ["draft", "final", "intro", undefined].includes(body.action) && !body.when;
  const isNotes = /^project\/rebuild-notes\?/.test(path) && body && !body.when;
  if ((isRun || isNotes) && tlMode() !== "now") {
    let when = "tonight";
    if (tlMode() === "ask") { when = await tlAskWhen(isNotes ? "Your changes, then a new draft" : body.action === "final" ? "The final video" : "A new draft"); if (!when) throw new Error("Not started"); }
    body = { ...body, when };
  }
  const r = await _api9(path, body, method);
  if (r && r.mode === "scheduled") setTimeout(() => toast(`Waiting in the Queue: starts at ${r.at.slice(11)}${r.at.slice(0, 10) === tlToday() ? " today" : " tonight"}`, "ok"), 300);
  return r;
};
const tlToday = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };

// ---------------------------------------------------------------- Queue page, simplified (mockup v7)
function tlEst(pid) {   // how long a build of this project takes: its last finished build, else 20 min
  const p = (S.state.projects || []).find(x => x.id === pid) || {};
  const b = (p.builds || []).filter(x => x.status === "done").slice(-1)[0];
  return b && b.secs ? b.secs : 20 * 60;
}
viewQueue = function () {
  const isTest = p => (p.title || "").startsWith("_");
  const P = S.state.projects.filter(p => !isTest(p) || p.activity), Q = S.state.queue || {};
  const jobs = (S.state.jobs || []).filter(j => j.status === "running" || j.status === "queued");
  const by = st => P.filter(p => (p.activity || {}).state === st);
  const making = by("importing").concat(by("rendering"), by("revising"));
  const waitingJobs = by("waiting").sort((a, b) => a.activity.pos - b.activity.pos);
  const sched = (S.state.schedule || []).filter(e => e.state === "pending").sort((a, b) => a.at.localeCompare(b.at));
  const finished = P.filter(p => !p.activity && p.stage === "review").slice(0, 8);
  const mode = tlMode(), night = tlNight();
  const th = p => p && p.thumb ? `style="background-image:url('${thumbUrl(p.thumb, p.thumb_crop, null, 240)}')"` : "";
  const proj = id => (S.state.projects || []).find(x => x.id === id);
  // all done by: tonight's start (or now) + every waiting build back to back
  const totalWait = waitingJobs.reduce((a, p) => a + tlEst(p.id), 0) + sched.reduce((a, e) => a + tlEst(e.project_id), 0);
  const startAt = (() => { if (mode !== "overnight") return new Date(); const [h, mi] = night.split(":").map(Number); const d = new Date(); d.setHours(h, mi, 0, 0); if (d < new Date() && new Date().getHours() >= 7) d.setDate(d.getDate() + 1); return d; })();
  const doneBy = new Date(startAt.getTime() + totalWait * 1000);
  const hhmm = d => d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const opt = (k, title, sub) => `<label class="tlq-opt ${mode === k ? "on" : ""}"><input type="radio" name="tlq-mode" value="${k}" ${mode === k ? "checked" : ""}><span><b>${title}</b><small>${sub}</small></span></label>`;
  const whenSel = (attrs, cur) => `<select class="tlq-when" ${attrs}><option value="">${esc(cur)}</option><option value="now">Right away</option><option value="tonight">Tonight at ${esc(night)}</option><option value="pick">Pick a time…</option></select>`;
  const row = (p, title, right, extra = "") => `<div class="tlq-row" ${p ? `data-open="${p.id}"` : ""}><div class="qth" ${th(p)}></div><div class="tlq-main"><b>${esc(title)}</b>${right}</div>${extra}</div>`;
  const makingRows = making.map(p => {
    const j = jobs.find(x => x.project_id === p.id && x.status === "running");
    const body = j && (j.queue || {}).state !== "ai" ? tlProgressCard(j, true)
      : `<div class="muted small">${p.activity.state === "revising" ? "✎ The AI is reading your changes. The render starts right after." : esc(p.activity.detail || p.activity.label || "")}</div><div class="prog-bar qbar"><i class="${p.activity.state === "revising" ? "ai" : ""}" style="width:${p.activity.state === "revising" ? 100 : (p.activity.pct || 0)}%"></i></div>`;
    return row(p, p.title, body);
  });
  const mine = waitingJobs.filter(p => p.activity.job);
  const waitRows = waitingJobs.map(p => {
    const j = p.activity.job, i = mine.indexOf(p);
    const btns = j ? `${i > 0 ? `<button class="sm icon" data-qmove="${j}" data-where="up" title="earlier">↑</button>` : ""}${i < mine.length - 1 ? `<button class="sm icon" data-qmove="${j}" data-where="down" title="later">↓</button>` : ""}${whenSel(`data-wjob="${j}"`, "Next in line")}<button class="sm icon" data-qcancel="${j}" title="take it out of the queue">×</button>` : "";
    return row(p, p.title, `<span class="muted small">#${p.activity.pos} in line${p.activity.wait_s ? ` · starts in about ${fmtEta(p.activity.wait_s)}` : " · starts next"}</span>`, `<div class="tlq-acts">${btns}</div>`);
  }).concat(sched.map(e => {
    const p = proj(e.project_id), d = new Date(e.at.replace(" ", "T")), tm = new Date(); tm.setDate(tm.getDate() + 1);
    const when = `${d.toDateString() === new Date().toDateString() ? "today" : d.toDateString() === tm.toDateString() ? "tomorrow" : e.at.slice(0, 10)} at ${hhmm(d)}`;
    return row(p, e.title, `<span class="muted small">${esc({ notes: "Your changes + new draft", final: "Final video", draft: "Draft", intro: "Intro" }[e.action] || e.action)} · starts ${esc(when)}</span>`,
      `<div class="tlq-acts">${whenSel(`data-wid="${e.id}"`, "Starts " + when)}<button class="sm icon" data-scancel9="${e.id}" title="take it out of the queue">×</button></div>`);
  }));
  const doneRows = finished.map(p => row(p, p.title, `<span class="muted small">Draft ready · click to watch it and add changes</span>`));
  const card = (t, sub, rows, empty) => `<div class="card tlq-sec"><div class="tlq-h"><h2>${t} <span class="dim small">${rows.length}</span></h2><span class="muted small">${sub}</span></div>${rows.join("") || `<div class="empty">${empty}</div>`}</div>`;
  const R = S.state.remote?.workers || [];
  return `<h1>Queue</h1><p class="sub">Videos being made, waiting their turn and finished. One video is rendered at a time.</p>
    <div class="card tlq-mode"><h2>When should videos be made?</h2><div class="tlq-opts">
      ${opt("now", "Right away", "Starts as soon as you add a video or apply changes.")}
      ${opt("overnight", "Overnight", `Waits until <input type="time" id="tlq-night" value="${esc(night)}"> and makes them back to back.${totalWait && mode === "overnight" ? ` All done by about <b>${hhmm(doneBy)}</b>.` : ""}`)}
      ${opt("ask", "I'll choose each time", "Asks Right away / Tonight / Pick a time whenever something is about to be made.")}</div></div>
    ${Q.outside ? `<div class="card" style="margin-bottom:14px"><b>Still rendering from before a Studio restart:</b> ${esc(Q.outside.title || "")} · ${esc(Q.outside.step || "")}.</div>` : ""}
    ${R.length ? `<p class="muted small">Machines: ${esc(S.state.machine || "This PC")}${R.map(w => ` · ${esc(w.name)} ${w.ok ? (w.jobs.length ? "busy" : "idle") : "offline"}`).join("")}</p>` : ""}
    <div class="tlq">${card("Making now", "", makingRows, "Nothing is being made right now.")}
    ${card("Waiting", mode === "overnight" && totalWait ? `all done by about ${hhmm(doneBy)}` : "starts on its own, top first", waitRows, "Nothing waiting.")}
    ${card("Finished", "drafts ready for you", doneRows, "No drafts waiting for you.")}</div>`;
};
function tlQueueWire() {
  if (S.view !== "queue") return;
  const reload = async () => { await refresh(true); if (S.view === "queue") render(); };
  $$("[name=tlq-mode]").forEach(r => r.onchange = async () => {
    try { S.state.settings = await api("settings", { build_mode: r.value }); } catch (e) { return toast(e.message, "bad"); }
    toast({ now: "Videos are made right away", overnight: `Videos wait until ${tlNight()} and are made back to back`, ask: "You'll be asked each time" }[r.value], "ok"); reload();
  });
  const n = $("#tlq-night"); if (n) { n.onclick = e => e.stopPropagation(); n.onchange = async () => { S.state.settings = await api("settings", { overnight_at: n.value || "01:00", build_mode: "overnight" }); reload(); }; }
  $$(".tlq-when").forEach(s => { s.onclick = e => e.stopPropagation(); s.onchange = async () => {
    let w = s.value; if (!w) return;
    if (w === "pick") { w = await tlAskWhen("Pick when this one is made"); if (!w) return reload(); }
    try { await api("schedule/when", s.dataset.wjob ? { job: s.dataset.wjob, when: w } : { id: s.dataset.wid, when: w }); toast("Updated", "ok"); } catch (e) { toast(e.message, "bad"); }
    reload();
  }; });
  $$("[data-scancel9]").forEach(b => b.onclick = async e => { e.stopPropagation(); try { await api("schedule/cancel", { id: b.dataset.scancel9 }); reload(); } catch (err) { toast(err.message, "bad"); } });
}
new MutationObserver(() => { const el = $(".tlq-mode"); if (S.view === "queue" && el && !el.dataset.wired) { el.dataset.wired = "1"; tlQueueWire(); } })
  .observe(document.getElementById("main") || document.body, { childList: true, subtree: true });

// ---------------------------------------------------------------- Project details popup (right-click a project, or Details)
async function tlDetails(pid) {
  const p = (S.state.projects || []).find(x => x.id === pid); if (!p) return;
  const m = modal(`<h2>Project details</h2><div class="muted">loading…</div>`, "tld");
  const [d, full] = await Promise.all([api("editor?id=" + pid).catch(() => null), api("project?id=" + pid).catch(() => null)]);
  if (!document.body.contains(m)) return;
  const f = full || p, builds = (f.builds || []).filter(b => b.status === "done"), last = builds.slice(-1)[0];
  const raw = d ? d.duration : 0, kept = d ? (d.keep || []).filter(([a]) => a >= 0).reduce((s, [a, b]) => s + b - a, 0) : 0;
  const cuts = d ? ((d.cuts || []).length || Math.max(0, (d.keep || []).filter(([a]) => a >= 0).length - 1)) : 0, pct = raw && kept ? Math.round((1 - kept / raw) * 100) : 0;
  const music = d && d.music ? (Array.isArray(d.music) ? d.music.map(x => typeof x === "string" ? x : x.track || "") : Object.values(d.music).map(x => (x || {}).track || "")).filter(Boolean) : [];
  const T = S.state.types[p.type] || { label: p.type };
  const kv = (k, v) => `<b>${k}</b><span>${v}</span>`;
  m.innerHTML = `<h2>Project details</h2><div class="muted small" style="margin:-6px 0 10px">${esc(p.title)}</div>
    <div class="kv tld-kv">${kv("Type", esc(T.label || p.type))}${kv("Status", esc(p.activity ? p.activity.label : (S.state.stage_labels || {})[p.stage] || p.stage))}
      ${kv("Raw length", raw ? fmtT(raw) : "—")}${kv("After cuts", kept ? fmtT(kept) + (d && d.offset ? ` + ${Math.round(d.offset)} s intro` : "") : "—")}
      ${kv("Mistakes cut", cuts ? String(cuts) : "—")}${kv("Builds", builds.length ? `${builds.length} · last ${esc(last.when || "")}` : "none yet")}
      ${kv("Last build took", last && last.secs ? fmtDur(last.secs) : "—")}${kv("Music", music.length ? esc(base(music[0]).replace(/\.[^.]+$/, "")) + (music.length > 1 ? ` + ${music.length - 1} more` : "") : "picked on the next build")}</div>
    ${raw && kept ? `<div class="tld-cut"><span class="muted small">How much was cut</span><div class="prog-bar"><i style="width:${pct}%"></i></div><span class="small">${pct}% cut · ${fmtT(raw - kept)} removed</span></div>` : ""}
    <div class="tld-acts"><button data-a="folder">Open folder</button><button data-a="rename">Rename</button><button data-a="type">Change video type</button><button data-a="history">Build history</button><button class="danger" data-a="remove">Remove project</button><span class="grow"></span><button data-a="close">Close</button></div>`;
  const act = async a => {
    try {
      if (a === "close") return closeModal();
      if (a === "folder") return api("open", { path: p.path });
      if (a === "rename") { const t = prompt("New name for this video", p.title); if (!t || t === p.title) return; await api("project/rename?id=" + pid, { title: t, folder: true }); toast("Renamed", "ok"); closeModal(); return refresh(); }
      if (a === "history") { closeModal(); tlSetMore(true); S.tab[pid] = "pipeline"; return nav("project", pid); }
      if (a === "remove") { if (!confirm("Remove this project from the list? Its files stay on your drive.")) return; await api("project/delete?id=" + pid, {}); closeModal(); return refresh(); }
      if (a === "type") {
        const types = Object.entries(S.state.types || {});
        const mm = modal(`<h2>Change video type</h2><p class="muted small">The next build starts over with the new type's editing style.</p><div class="tld-types">${types.map(([k, t]) => `<button class="${k === p.type ? "on" : ""}" data-t="${k}">${esc(t.icon || "")} ${esc(t.label || k)}</button>`).join("")}</div><div class="row" style="justify-content:flex-end;margin-top:10px"><button id="tld-x">Cancel</button></div>`);
        $("#tld-x", mm).onclick = closeModal;
        $$("[data-t]", mm).forEach(b => b.onclick = async () => { if (b.dataset.t === p.type) return closeModal(); try { await api("project/update?id=" + pid, { type: b.dataset.t }); toast("Type changed: the next build uses it", "ok"); closeModal(); refresh(); } catch (e) { toast(e.message, "bad"); } });
      }
    } catch (e) { toast(e.message, "bad"); }
  };
  $$("[data-a]", m).forEach(b => b.onclick = () => act(b.dataset.a));
}
// the right-click menu already exists (app3.js projectMenu): "Project details…" goes in at the top of it
document.addEventListener("contextmenu", e => {
  const el = e.target.closest("[data-open], .pcard, .bc, .th-row, .item[data-id]"), pid = el && (el.dataset.open || el.dataset.id);
  setTimeout(() => {
    const m = $("#ctx"); if (!m || !pid || m.querySelector("[data-a=details9]")) return;
    const a = document.createElement("a"); a.dataset.a = "details9"; a.textContent = "Project details…";
    a.onclick = ev => { ev.stopPropagation(); closeCtx(); tlDetails(pid); };
    m.querySelector(".ctx-h").insertAdjacentElement("afterend", a);
  }, 0);
});
const _pcard9 = pcard;
pcard = function (p) { return _pcard9(p).replace(/<div class="b">/, `<button class="tld-btn" data-tld="${p.id}" title="Project details (or right-click the project)">Details</button><div class="b">`); };
document.addEventListener("click", e => { const b = e.target.closest("[data-tld]"); if (!b) return; e.preventDefault(); e.stopPropagation(); tlDetails(b.dataset.tld); }, true);

// the finished-build line on the project page says what to do next; build statistics moved to Project details
const _progressBar9b = progressBar;
progressBar = function (p) {
  const j = p.jobs[0] || p.last_job, outs = p.outputs || [];
  if (!p.external && (!j || (j.status !== "running" && j.status !== "queued" && j.status !== "failed")) && outs.length) {
    const o = outs[outs.length - 1];
    return `<div class="prog done"><div class="prog-head"><b>${o.kind === "final" ? "✓ Final video ready" : "✓ Draft ready"}</b><span class="muted small">${o.kind === "final" ? "Full quality. Send it or keep editing." : "Watch it below and add your changes."}</span><button class="sm" data-tld="${p.id}">Project details</button></div></div>`;
  }
  return _progressBar9b(p);
};

// the Queue link's count (sidebar, every screen) includes videos waiting for tonight / a picked time
const _renderSideJobs9 = renderSideJobs;
renderSideJobs = function () {
  _renderSideJobs9();
  const n = (S.state?.projects || []).filter(p => p.activity).length + (S.state?.schedule || []).filter(e => e.state === "pending").length, b = $("#queue-count");
  if (b) { b.textContent = n || ""; b.style.display = n ? "" : "none"; b.title = n ? `${n} being made or waiting` : ""; }
};

// ---------------------------------------------------------------- sidebar: Projects, Queue, Settings + "Channel tools" (2026-10-29)
// the business tools (Dashboard, Tracker, To-do, Ideas, Competitors, Thumbnails, Uploads, Search transcripts) are one click away
// on a tiles page instead of eight sidebar rows. Nothing is removed: the tiles click the hidden rows.
const TL_KEEP_NAV = ["projects", "queue", "tools"];
function tlSideNav() {
  const nv = $("#side nav:not(.nav-foot)"); if (!nv) return;
  if (!$('a[data-view="tools"]', nv)) {
    const a = document.createElement("a"); a.dataset.view = "tools";
    a.innerHTML = `<svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>Channel tools`;
    a.onclick = () => nav("tools");
    const q = $('a[data-view="queue"]', nv); q ? q.insertAdjacentElement("afterend", a) : nv.appendChild(a);
  }
  $$("a[data-view]", nv).forEach(a => a.classList.toggle("tl-hide", !TL_KEEP_NAV.includes(a.dataset.view)));
  const proj = $('a[data-view="projects"]', nv); if (proj && proj !== nv.firstElementChild) nv.prepend(proj);
  const sb = $("#btn-search"); if (sb) sb.classList.add("tl-hide");
}
new MutationObserver(tlSideNav).observe($("#side"), { childList: true, subtree: true });
tlSideNav();
function viewTools() {
  const tiles = $$("#side nav:not(.nav-foot) a[data-view]").filter(a => !TL_KEEP_NAV.includes(a.dataset.view));
  const desc = { dashboard: "What needs you today and this week", tracker: "Uploads per channel against your targets", todo: "Your to-do list", ideas: "Video ideas from trends", competitors: "What other channels are posting", thumbs: "Thumbnails each video still needs", uploads: "Send finished videos to YouTube", ...(window.CT_DESC || {}) };
  // three groups instead of one long grid (overnight 2026-10-29: 14 tiles were too many to scan); a tile no group names
  // (a new tool) lands in the last group
  const tile = a => `<button class="tl-tile" data-tile="${esc(a.dataset.view)}">${a.querySelector("svg") ? a.querySelector("svg").outerHTML : ""}<b>${esc(a.textContent.replace(/\d+$/, "").trim())}</b><small>${esc(desc[a.dataset.view] || "")}</small></button>`;
  const search = $("#btn-search") ? `<button class="tl-tile" data-tile="search"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg><b>Search transcripts</b><small>Find anything you said in any video (Ctrl K)</small></button>` : "";
  const groups = [["Plan your week", ["dashboard", "tracker", "todo"]],
    ["Find video ideas", ["ideas", "ct_brainstorm", "competitors", "ct_insights", "ct_comment_miner"]],
    ["Make and publish", ["ct_planner", "ct_title_lab", "ct_thumb_check", "ct_hook_doctor", "ct_repurpose", "thumbs", "uploads"]],
    ["Handy tools", ["ct_download"]]];
  const named = new Set(groups.flatMap(g => g[1]));
  const extra = tiles.filter(a => !named.has(a.dataset.view));
  return `<h1>Channel tools</h1><p class="sub">Everything around the editing: planning, ideas and publishing.</p>
    ${groups.map(([name, keys], gi) => { const ts = keys.map(k => tiles.find(a => a.dataset.view === k)).filter(Boolean).concat(gi === groups.length - 1 ? extra : []);
      return ts.length || (gi === 0 && search) ? `<h2 class="tl-group">${esc(name)}</h2><div class="tl-tiles">${ts.map(tile).join("")}${gi === 0 ? search : ""}</div>` : ""; }).join("")}`;
}
const _render9 = render;
render = async function () {
  if (S.view === "tools") { $("#main").innerHTML = viewTools(); $$("[data-tile]").forEach(b => b.onclick = () => b.dataset.tile === "search" ? $("#btn-search").click() : $(`#side nav a[data-view="${b.dataset.tile}"]`).click()); wireCommon(); return; }
  return _render9();
};
if (S.view === "dashboard") { S.view = "projects"; $$("nav a").forEach(a => a.classList.toggle("active", a.dataset.view === "projects")); try { history.replaceState({ view: "projects", pid: null }, ""); } catch (e) { } }

// ---------------------------------------------------------------- Text size (2026-10-29, the user is visually impaired: "everything small")
// Normal / Large / Extra large zoom the whole Studio; saved in settings.ui_text_size (default Large), Ctrl + / Ctrl − / Ctrl 0
const TL_SIZES = { normal: 1, large: 1.2, xl: 1.4 }, TL_SIZE_NAMES = { normal: "Normal", large: "Large", xl: "Extra large" };
const tlSizeKey = () => (S.state?.settings || {}).ui_text_size || (() => { try { return localStorage.getItem("studio.textSize"); } catch (e) { return null; } })() || "normal";
function tlApplySize(k) {
  const z = TL_SIZES[k] || TL_SIZES.large;
  document.documentElement.style.zoom = z; document.documentElement.style.setProperty("--z", z);
  try { localStorage.setItem("studio.textSize", k); } catch (e) { }
}
async function tlSetSize(k) {
  if (!TL_SIZES[k]) return;
  tlApplySize(k);
  try { S.state.settings = await api("settings", { ui_text_size: k }); } catch (e) { }
  toast("Text size: " + TL_SIZE_NAMES[k], "ok");
  if ($("#tle-lanes")) tlDraw();
  $$("[data-size]").forEach(b => b.classList.toggle("on", b.dataset.size === k));
}
tlApplySize(tlSizeKey());
const _refresh9 = refresh;
refresh = async function (keep) { const r = await _refresh9(keep); tlApplySize(tlSizeKey()); return r; };
window.addEventListener("keydown", e => {
  if (!(e.ctrlKey || e.metaKey) || $(".e2")) return;   // in the editor Ctrl + / - zoom the timeline (app10)
  const order = ["normal", "large", "xl"], i = order.indexOf(tlSizeKey());
  if (e.key === "+" || e.key === "=") { e.preventDefault(); e.stopPropagation(); tlSetSize(order[Math.min(2, i + 1)]); }
  else if (e.key === "-" || e.key === "_") { e.preventDefault(); e.stopPropagation(); tlSetSize(order[Math.max(0, i - 1)]); }
  else if (e.key === "0") { e.preventDefault(); e.stopPropagation(); tlSetSize("normal"); }
}, true);
const tlSizeRow = () => `<div class="tl-sizes"><span>Text size</span>${Object.keys(TL_SIZES).map(k => `<button class="tlb sm ${tlSizeKey() === k ? "on" : ""}" data-size="${k}">${TL_SIZE_NAMES[k]}</button>`).join("")}</div>`;
document.addEventListener("click", e => { const b = e.target.closest("[data-size]"); if (!b) return; e.stopPropagation(); tlSetSize(b.dataset.size); }, true);
const _viewSettings9 = viewSettings;
viewSettings = function () { return _viewSettings9().replace(/(<h1[^>]*>[\s\S]*?<\/h1>(?:\s*<p class="sub">[\s\S]*?<\/p>)?)/, `$1<div class="card tl-sizecard"><h2>Text size</h2><p class="muted">Makes everything in Studio bigger or smaller. Also Ctrl + and Ctrl −.</p>${tlSizeRow()}</div>`); };

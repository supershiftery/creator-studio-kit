/* {{STUDIO_NAME}} UI - vanilla JS, talks to the local API */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const fmtT = t => { t = Math.max(0, +t || 0); const m = Math.floor(t / 60), s = Math.floor(t % 60); return `${m}:${String(s).padStart(2, "0")}`; };
const fmtT2 = t => { t = Math.max(0, +t || 0); const m = Math.floor(t / 60), s = (t % 60).toFixed(1); return `${m}:${s.padStart(4, "0")}`; };
const fmtSize = b => b > 1e9 ? (b / 1e9).toFixed(2) + " GB" : b > 1e6 ? (b / 1e6).toFixed(0) + " MB" : (b / 1e3).toFixed(0) + " KB";
const base = p => String(p || "").split(/[\\/]/).pop();
const enc = encodeURIComponent;
const mediaUrl = p => `/media?path=${enc(p)}`;
const thumbUrl = (p, crop, t, w = 480) => `/thumb?path=${enc(p)}${crop ? "&crop=" + crop : ""}${t != null ? "&t=" + t : ""}&w=${w}`;

const S = { state: null, view: "projects", pid: null, project: null, pollers: {}, tab: {}, logOpen: true };

async function api(path, body, method) {
  const r = await fetch("/api/" + path, body !== undefined ? { method: method || "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const d = await r.json();
  if (d && d.error) throw new Error(d.error + (d.trace ? "\n" + d.trace.split("\n").slice(-3).join("\n") : ""));
  return d;
}
function toast(msg, kind = "") {
  const t = document.createElement("div"); t.className = "toast " + kind; t.textContent = msg;
  $("#toasts").appendChild(t); setTimeout(() => t.remove(), kind === "bad" ? 9000 : 4000);
}
function modal(html, cls = "") {
  const root = $("#modal-root"); root.innerHTML = `<div class="modal ${cls}">${html}</div>`;
  root.onclick = e => { if (e.target === root) closeModal(); };
  return root.firstElementChild;
}
function closeModal() { $("#modal-root").innerHTML = ""; }
const inWindow = () => !!(window.pywebview && window.pywebview.api);

// ---------------------------------------------------------------- file picking (drop, native dialog, server browser)
function dropPaths(e) {
  const out = [];
  for (const f of e.dataTransfer?.files || []) { const p = f.pywebviewFullPath || f.path; if (p) out.push(p); }
  return out;
}
async function pickFiles(kind = "any", multiple = true) {
  if (inWindow()) { try { return await window.pywebview.api.pick_files(kind, multiple); } catch (e) { console.warn(e); } }
  return browseModal({ kind, multiple });
}
const EXT = { video: ".mp4,.mov,.mkv,.m4v,.avi", audio: ".wav,.mp3,.m4a,.flac", image: ".png,.jpg,.jpeg,.webp", text: ".txt,.md,.html", media: ".mp4,.mov,.mkv,.m4v,.avi,.wav,.mp3,.m4a,.flac", any: "" };
function browseModal({ kind = "any", multiple = true, dirsOnly = false, start = "" } = {}) {
  return new Promise(resolve => {
    let dir = start, sel = new Set();
    const m = modal(`<h2>${dirsOnly ? "Choose a folder" : "Choose file" + (multiple ? "s" : "")}</h2>
      <div class="browser"><div class="crumbs"></div><div class="files"></div>
      <div class="row"><span class="muted small grow" id="bsel"></span><button id="bcancel">Cancel</button><button class="primary" id="bok">Choose</button></div></div>`, "wide");
    const files = $(".files", m), crumbs = $(".crumbs", m);
    async function load(d) {
      dir = d;
      const r = await api(`browse?dir=${enc(d)}&ext=${enc(EXT[kind] || "")}`);
      crumbs.innerHTML = d ? `<a data-d="">Places</a> › ` + d.split(/[\\/]/).filter(Boolean).map((p, i, a) => `<a data-d="${esc(a.slice(0, i + 1).join("\\") + (i === 0 ? "\\" : ""))}">${esc(p)}</a>`).join(" › ") : "Places";
      $$("a", crumbs).forEach(a => a.onclick = () => load(a.dataset.d));
      files.innerHTML = (r.parent !== undefined && d ? `<div class="fe" data-d="${esc(r.parent)}"><span>↰</span><span>..</span><span></span><span></span></div>` : "") +
        r.items.map(i => `<div class="fe ${sel.has(i.path) ? "sel" : ""}" data-p="${esc(i.path)}" data-dir="${i.dir ? 1 : ""}"><span>${i.dir ? "📁" : "▫"}</span><span>${esc(i.name)}</span><span class="sz">${i.dir ? "" : fmtSize(i.size)}</span><span class="dt">${i.mtime ? new Date(i.mtime * 1000).toLocaleDateString() : ""}</span></div>`).join("");
      $$(".fe", files).forEach(el => {
        el.ondblclick = () => { if (el.dataset.dir || el.dataset.d !== undefined) load(el.dataset.d ?? el.dataset.p); else { sel = new Set([el.dataset.p]); done(); } };
        el.onclick = () => {
          if (el.dataset.d !== undefined) return load(el.dataset.d);
          if (el.dataset.dir && !dirsOnly) return load(el.dataset.p);
          if (!multiple) sel.clear();
          sel.has(el.dataset.p) ? sel.delete(el.dataset.p) : sel.add(el.dataset.p);
          $$(".fe", files).forEach(x => x.classList.toggle("sel", sel.has(x.dataset.p)));
          $("#bsel", m).textContent = sel.size ? [...sel].map(base).join(", ") : "";
        };
      });
    }
    function done() { closeModal(); resolve([...(sel.size ? sel : (dirsOnly && dir ? new Set([dir]) : new Set()))]); }
    $("#bok", m).onclick = done; $("#bcancel", m).onclick = () => { closeModal(); resolve([]); };
    load(start);
  });
}

// ---------------------------------------------------------------- boot + nav
async function refresh(keep) {
  S.state = await api("state");
  $("#mode-tag").textContent = (S.state.mode === "window" ? "desktop" : "browser mode") + " · " + S.state.projects.length + " projects";
  renderSideJobs();
  if (!keep) render();
}
function nav(view, pid) {
  S.view = view; S.pid = pid || null;
  $$("nav a").forEach(a => a.classList.toggle("active", a.dataset.view === view));
  render();
}
async function render() {
  const main = $("#main");
  if (S.view === "dashboard") { main.innerHTML = viewDashboard(); loadHub(); loadTodo($("#todo-card"), false); enhanceDashboard(); }
  else if (S.view === "projects") main.innerHTML = viewProjects();
  else if (S.view === "queue") main.innerHTML = viewQueue();
  else if (S.view === "tracker") main.innerHTML = viewTracker();
  else if (S.view === "thumbs") { await viewThumbs(); return; }
  else if (S.view === "todo") { main.innerHTML = `<h1>To-do</h1><p class="sub">Shared with TickTick: the Apple widget and the Telegram check-ins see the same list. Add here → it lands in TickTick; tick here → done in TickTick.</p><div id="todo-full"></div>`; loadTodo($("#todo-full"), true); }
  else if (S.view === "settings") { main.innerHTML = viewSettings(); wireSettings(); }
  else if (S.view === "project") { main.innerHTML = `<div class="muted">Loading…</div>`; await loadProject(); }
  wireCommon();
}
// a draft waiting for him opens on Review + notes: watch, talk notes, send revisions (user 2026-10-23: "all set up for me ...
// instead of having it go to the editor")
function openProject(pid) {
  const p = (S.state.projects || []).find(x => x.id === pid);
  if (p && p.stage === "review" && !p.activity) S.tab[pid] = "review";
  nav("project", pid);
}
function wireCommon() {
  $$("[data-open]").forEach(el => el.onclick = e => { e.stopPropagation(); openProject(el.dataset.open); });
  $$("[data-nav]").forEach(el => el.onclick = () => nav(el.dataset.nav));
}
function renderSideJobs() {
  // one row per video (user 2026-10-26: a laptop build showed twice, as "revision in progress", next to test projects):
  // our "Building on Laptop" job stands for the laptop's copy
  const test = j => (j.title || "").startsWith("_");
  const tag = j => test(j) ? { ...j, title: "TEST · " + j.title.slice(1) } : j;   // test copies show while they run, labeled
  const local = (S.state?.jobs || []).filter(j => j.status === "running" || j.status === "queued").map(tag);
  const mine = new Set(local.map(j => j.project_id));
  const remoteJobs = (S.state?.remote?.workers || []).flatMap(w => (w.jobs || []).map(j => ({ ...j, where: w.name }))).filter(j => !mine.has(j.project_id)).map(tag);
  const running = local.concat(remoteJobs);
  const what = j => {
    const q = j.queue || {}, on = j.where ? ` · on ${j.where}` : "", pr = j.progress || {};
    if (j.current === "remote") return `${pr.step || "Building on the laptop"} · ${Math.round(pr.pct || 0)}%`;
    return (q.state === "waiting" ? `⏳ #${q.pos} in line` : q.state === "ai" ? "✎ revision in progress" : (j.steps.find(s => s.status === "running")?.label || j.status)) + on;
  };
  $("#side-jobs").innerHTML = running.map(j => `<div class="sjob ${(j.queue || {}).state === "waiting" ? "waiting" : ""}" data-job="${j.id}" data-open="${j.project_id}"><b>${esc(j.title)}</b><span class="muted">${esc(what(j))}</span><div class="bar"><i></i></div></div>`).join("");
  $$(".sjob").forEach(el => el.onclick = () => nav("project", el.dataset.open));
  const n = (S.state?.projects || []).filter(p => p.activity).length, b = $("#queue-count");
  if (b) { b.textContent = n || ""; b.style.display = n ? "" : "none"; }
}
// render-queue buttons live in several views (queue page, project page): one delegated handler for all of them
document.addEventListener("click", async e => {
  const mv = e.target.closest("[data-qmove]"), cx = e.target.closest("[data-qcancel]");
  if (!mv && !cx) return;
  e.stopPropagation();
  try {
    if (mv) await api("job/move?id=" + mv.dataset.qmove, { where: mv.dataset.where || "up" });
    else if (confirm("Take this video out of the render queue? Its notes stay; build it again any time.")) await api("job/cancel?id=" + cx.dataset.qcancel, {});
    else return;
    await refresh(true); if (S.view === "queue") render(); else if (S.view === "project") loadProject();
  } catch (err) { toast(err.message, "bad"); }
}, true);

// ---------------------------------------------------------------- queue (everything in progress, user 2026-10-23)
function viewQueue() {
  // test projects ("_remote test prada": copies for checking the two-machine setup, user 2026-10-26 "what's going on with
  // the remote tests?"): shown with a TEST label while something runs on them (he does give them notes), never in
  // "Ready for your review"; one line says how many idle ones are hidden
  const isTest = p => (p.title || "").startsWith("_");
  const P = S.state.projects.filter(p => !isTest(p) || p.activity), Q = S.state.queue || {};
  const nTest = S.state.projects.filter(p => isTest(p) && !p.activity && p.stage === "review").length;
  const by = st => P.filter(p => (p.activity || {}).state === st);
  const rendering = by("importing").concat(by("rendering")), waiting = by("waiting").sort((a, b) => a.activity.pos - b.activity.pos), revising = by("revising");
  const review = P.filter(p => !p.activity && p.stage === "review").slice(0, 12);
  const th = p => p.thumb ? `style="background-image:url('${thumbUrl(p.thumb, p.thumb_crop, null, 240)}')"` : "";
  const row = (p, right) => `<div class="qrow" data-open="${p.id}"><div class="qth" ${th(p)}></div><div class="qmain"><div class="row" style="gap:6px"><span class="pill type-${p.type}">${esc(S.state.types[p.type].icon)}</span><b>${esc(p.title)}</b>${isTest(p) ? `<span class="pill" title="a test copy (two-machine checks), not a real video">TEST</span>` : ""}<span class="muted small">${esc(p.channel || "")}</span></div>${right}</div></div>`;
  const bar = (pct, cls = "") => `<div class="prog-bar qbar"><i class="${cls}" style="width:${pct}%"></i></div>`;
  const sec = (title, hint, rows) => `<div class="card qsec"><div class="row" style="justify-content:space-between;margin-bottom:8px"><h2 style="margin:0">${title} <span class="dim small">${rows.length}</span></h2><span class="muted small">${hint}</span></div>${rows.join("") || `<div class="empty">nothing here</div>`}</div>`;
  const on = p => p.activity.where || p.activity.via ? `<span class="pill act">on ${esc(p.activity.where || (p.activity.detail || "").split(" ").pop() || "the laptop")}</span> ` : "";
  // move / cancel act on THIS machine's queue, so only local waiting videos get them (remote ones have no job id)
  const mine = waiting.filter(p => p.activity.job);
  const qbtns = p => {
    const i = mine.indexOf(p), j = p.activity.job;
    if (i < 0) return "";
    return `${i > 0 ? `<button class="sm" data-qmove="${j}" data-where="top" title="render this one next">⤒ next</button><button class="sm" data-qmove="${j}" data-where="up">▲</button>` : ""}${i < mine.length - 1 ? `<button class="sm" data-qmove="${j}" data-where="down">▼</button>` : ""}<button class="sm" data-qcancel="${j}">cancel</button>`;
  };
  const R = S.state.remote?.workers || [];
  const busy = n => n ? `rendering ${n}` : "idle";
  const localN = rendering.filter(p => !p.activity.where && !p.activity.via).length;   // via = sent to the laptop: not this PC's GPU
  const machines = R.length ? `<div class="card" style="margin-bottom:14px"><div class="row" style="gap:14px;flex-wrap:wrap"><b>Machines</b>
      <span><span class="pill act">${esc(S.state.machine || "This PC")}</span> <span class="muted small">${busy(localN)} · this PC</span></span>
      ${R.map(w => {
        // a build THIS PC sends there shows while its footage is still crossing over (the worker has no job yet)
        const via = rendering.filter(p => p.activity.via && p.activity.where === w.name && !w.jobs.some(j => j.project_id === p.id));
        const nm = j => esc((j.title || "").replace(/: \w+$/, "")), now = w.jobs.filter(j => (j.queue || {}).state !== "waiting"), next = w.jobs.filter(j => (j.queue || {}).state === "waiting");
        const txt = w.jobs.length ? (now.length ? `rendering ${now.map(nm).join(", ")}` : "idle") + (next.length ? ` · next: ${next.map(nm).join(", ")}` : "")
          : via.length ? via.map(p => `${esc((p.activity.detail || "").replace(/ (to|on|from) .*$/, "").toLowerCase() || "sending")} ${esc(p.title)} ${Math.round(p.activity.pct || 0)}%`).join(", ") : "idle";
        return `<span><span class="pill act ${w.ok ? "" : "act-waiting"}">${esc(w.name)}</span> <span class="muted small">${w.ok ? txt : `offline${w.error ? ` (${esc(w.error)})` : ""}`}</span></span>`;
      }).join("")}</div></div>` : "";
  const r1 = rendering.map(p => row(p, `<div class="muted small">${on(p)}${esc(p.activity.detail || "")} · ${Math.round(p.activity.pct || 0)}%${p.activity.eta_s ? ` · ~${fmtEta(p.activity.eta_s)} left` : ""}${stuckNote(p.activity)}</div>${bar(p.activity.pct || 0)}`));
  const r2 = waiting.map((p, i) => row(p, `<div class="row" style="gap:6px;margin-top:4px">${on(p)}<span class="pill act act-waiting">#${p.activity.pos} in line</span><span class="muted small">${p.activity.wait_s ? `starts in ~${fmtEta(p.activity.wait_s)}` : "starts next"}</span><span class="grow"></span>
      ${qbtns(p)}</div>`));
  const r3 = revising.map(p => row(p, `<div class="muted small">✎ ${esc(p.activity.detail || "AI is working on your notes")}${p.activity.elapsed ? ` · ${fmtEta(p.activity.elapsed)}` : ""}</div>${bar(100, "ai")}`));
  const r4 = review.map(p => row(p, `<div class="muted small">draft ready · open it, watch, add notes, send revisions</div>`));
  const outside = Q.outside ? `<div class="card" style="margin-bottom:14px"><b>Still rendering from before a Studio restart:</b> ${esc(Q.outside.title || "")} · ${esc(Q.outside.step || "")}. The line starts when it finishes.</div>` : "";
  return `<h1>Queue</h1><p class="sub">Every video in progress. Send revisions on one, jump to the next; the AI part runs for all of them at once, the renders go one at a time in this order${Q.on === false ? " (render queue is OFF in settings: builds start at once)" : ""}.</p>
    ${machines}${outside}${nTest ? `<p class="muted small" style="margin:-6px 0 12px">${nTest} test project${nTest > 1 ? "s" : ""} hidden (names starting with _; find them in Projects)</p>` : ""}<div class="qgrid">${sec("Rendering now", "uses the GPU", r1)}${sec("Waiting to render", "starts on its own, in this order", r2)}${sec("Revision in progress", "the AI is reading your notes / fixing", r3)}${sec("Ready for your review", "drafts nobody is working on", r4)}</div>`;
}

// ---------------------------------------------------------------- dashboard
function pcard(p) {
  const done = Object.values(p.checklist).filter(Boolean).length, total = Object.keys(p.checklist).length;
  const thumb = p.thumb ? `url('${thumbUrl(p.thumb, p.thumb_crop)}')` : "";
  return `<div class="pcard" data-open="${p.id}">
    <div class="th" style="background-image:${thumb}">
      <span class="pill type-${p.type} ty">${esc(S.state.types[p.type].icon)} ${esc(p.type_label)}</span>
      ${p.activity ? `<span class="pill act act-${p.activity.state} stg">${esc(p.activity.label)}</span>` : `<span class="pill st-${p.stage} stg">${esc(S.state.stage_labels[p.stage])}</span>`}
      ${p.due ? `<span class="due ${p.due < S.state.tracker.today && p.stage !== "published" ? "bad" : ""}">due ${esc(p.due)}</span>` : ""}
    </div>
    <div class="b"><b title="${esc(p.title)}">${esc(p.title)}</b><span class="muted small">${esc(p.channel || "no channel")} · ${done}/${total} done</span>
    <div class="prog"><i style="width:${(done / total) * 100}%"></i></div></div>
    ${!p.jobs.length && p.external ? `<div class="busy"></div><div class="cardprog"><i style="width:${p.external.pct}%"></i><span>${esc(p.external.step)} · outside the app</span></div>` : ""}
    ${p.activity && p.activity.state === "importing" ? `<div class="busy"></div><div class="cardprog"><i style="width:${p.activity.pct || 0}%"></i><span>⇣ ${esc(p.activity.detail || p.activity.label)}${p.activity.eta_s ? " · " + fmtEta(p.activity.eta_s) + " left" : ""}</span></div>`
      : p.activity && p.activity.state === "waiting" ? `<div class="cardprog"><i style="width:0%"></i><span>⏳ ${esc(p.activity.label)}${p.activity.wait_s ? " · starts in ~" + fmtEta(p.activity.wait_s) : ""}</span></div>`
      : p.activity && p.activity.state === "revising" ? `<div class="busy"></div><div class="cardprog"><i class="ai" style="width:100%"></i><span>✎ ${esc(p.activity.detail || "AI is working on your notes")}</span></div>`
      : p.jobs.length ? `<div class="busy"></div><div class="cardprog"><i style="width:${(p.jobs[0].progress || {}).pct || 0}%"></i><span>${esc((p.jobs[0].progress || {}).step || "building…")}${(p.jobs[0].progress || {}).eta_s ? " · " + fmtEta(p.jobs[0].progress.eta_s) + " left" : ""}${stuckNote(p.jobs[0].progress)}</span></div>` : ""}</div>`;
}
const fmtEta = s => s < 60 ? "<1 min" : s < 3600 ? Math.round(s / 60) + " min" : (s / 3600).toFixed(1) + " h";
// the build has printed nothing, written no file and used no CPU for a while (2026-10-23: a hung edit_review sat on "49%" for 50 min)
const stuckNote = pr => pr && pr.stuck_s ? ` · <b style="color:var(--warn)">⚠ no activity for ${fmtEta(pr.stuck_s)}: may be stuck, check the log</b>` : "";
const fmtDur = s => { s = Math.round(s || 0); return s >= 3600 ? `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m` : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
function buildHistory(p) {
  const bs = (p.builds || []).slice().reverse();
  if (!bs.length) return "";
  return `<div class="card" style="margin-top:14px"><h2>Build history <span class="dim small">${bs.length}</span></h2><p class="muted small" style="margin:0 0 8px">How long each build took, so you can see it getting faster. Speed = build time ÷ footage length.</p>
    <div class="list">${bs.map(b => `<div class="bh ${b.status}"><div class="row"><span class="pill ${b.status === "done" ? "st-final" : b.status === "failed" ? "bad" : ""}">${esc(b.action)}</span><b>${fmtDur(b.secs)}</b><span class="muted small">${b.minutes ? `${b.minutes} min of footage · ${(b.secs / 60 / b.minutes).toFixed(2)}×` : ""} · ${esc(b.when)}${b.status !== "done" ? " · " + esc(b.status) : ""}</span></div>
      <div class="bh-steps">${(b.steps || []).filter(s => s.secs != null && s.status !== "skipped").map(s => `<span class="bh-step ${s.status}" title="${esc(s.label)}" style="flex:${Math.max(1, s.secs)}"><i>${esc(s.label.split(" (")[0].split(":")[0])}</i> ${fmtDur(s.secs)}</span>`).join("")}${(b.steps || []).some(s => s.status === "skipped") ? `<span class="muted tiny">(${(b.steps || []).filter(s => s.status === "skipped").length} steps skipped, already up to date)</span>` : ""}</div></div>`).join("")}</div></div>`;
}
function progressBar(p) {
  if (!p.jobs.length && p.external) {
    const x = p.external;
    return `<div class="prog running"><div class="prog-head"><b>Building · ${esc(x.label)}${x.step_count > 1 ? ` · step ${Math.min(x.step_index, x.step_count)}/${x.step_count}` : ""}: ${esc(x.step)}</b><span class="muted small">${Math.round(x.pct)}% · ${fmtEta(x.elapsed_s)} elapsed${x.eta_s ? ` · ~${fmtEta(x.eta_s)} left` : ""} · ${x.resumed ? "kept running through an app restart" : "started outside the app"}</span></div>
      <div class="prog-bar"><i style="width:${x.pct}%"></i></div></div>`;
  }
  const j = p.jobs[0] || p.last_job;
  const outs = p.outputs || [];
  if (!j || (j.status !== "running" && j.status !== "queued")) {
    if (j && j.status === "failed") return `<div class="prog failed"><div class="prog-head"><b>Build failed</b><span class="bad">${esc(j.error)}</span><button class="sm" data-rebuild="1">retry</button></div></div>`;
    if (outs.length) { const o = outs[outs.length - 1]; const lb = (p.builds || []).filter(b => b.status === "done").slice(-1)[0]; return `<div class="prog done"><div class="prog-head"><b>${o.kind === "final" ? "Final rendered" : "Draft ready"}</b><span class="muted small">${esc(base(o.file))}${lb ? ` · built in ${fmtDur(lb.secs)}${lb.minutes ? ` (${(lb.secs / 60 / lb.minutes).toFixed(2)}× footage length)` : ""} on ${esc(lb.when)}` : ""}</span><button class="sm" data-tab-go="review">watch + notes →</button></div><div class="prog-bar"><i style="width:100%"></i></div></div>`; }
    if (!p.source) return `<div class="prog idle"><div class="prog-head"><b>Waiting for footage</b><span class="muted small">add the recording and the draft builds itself</span></div></div>`;
    return `<div class="prog idle"><div class="prog-head"><b>Not built yet</b><span class="muted small">the draft normally starts on its own when footage is added</span><button class="primary sm" data-rebuild="1">▶ Build draft now</button></div></div>`;
  }
  const q = j.queue || {};
  if (q.state === "waiting") return `<div class="prog idle waiting"><div class="prog-head"><b>⏳ Waiting to render · #${q.pos} in line</b><span class="muted small">one video renders at a time; this starts on its own${q.wait_s ? ` in about ${fmtEta(q.wait_s)}` : ""}</span>${q.pos > 1 ? `<button class="sm" data-qmove="${j.id}" data-where="top">move to front</button>` : ""}<button class="sm" data-nav="queue">queue →</button><button class="sm" data-qcancel="${j.id}">cancel</button></div></div>`;
  if (q.state === "ai") return `<div class="prog running"><div class="prog-head"><b>✎ Revision in progress · ${esc(q.step || "AI is reading your notes")}</b><span class="muted small">no GPU needed for this part; the render waits its turn after it</span><button class="sm" data-tab-go="pipeline">log</button></div><div class="prog-bar"><i class="ai" style="width:100%"></i></div></div>`;
  const pr = j.progress || { pct: 0, step: j.steps.find(s => s.status === "running")?.label || "", step_index: 1, step_count: j.steps.length, elapsed_s: 0, eta_s: 0 };
  const segs = j.steps.map(s => `<i class="seg ${s.status}" title="${esc(s.label)}"></i>`).join("");
  return `<div class="prog running"><div class="prog-head"><b>Building ${esc(j.title.split(": ").pop())} · step ${pr.step_index}/${pr.step_count}: ${esc(pr.step)}</b><span class="muted small">${Math.round(pr.pct)}% · ${fmtEta(pr.elapsed_s)} elapsed · ~${fmtEta(pr.eta_s)} left${pr.live ? " (from the render)" : ""}${stuckNote(pr)}</span><button class="sm" data-tab-go="pipeline">log</button></div>
    <div class="prog-bar"><i style="width:${pr.pct}%"></i></div><div class="prog-segs">${segs}</div></div>`;
}
function listRows(rows, extra) {
  if (!rows.length) return `<div class="empty">nothing here</div>`;
  return `<div class="list">${rows.map(r => `<div class="item" data-open="${r.id}"><span class="pill type-${r.type}">${esc(S.state.types[r.type].icon)}</span><span class="t">${esc(r.title)}</span><span class="muted small">${esc(r.channel || "")}</span>${extra ? extra(r) : ""}</div>`).join("")}</div>`;
}
function viewDashboard() {
  const t = S.state.tracker, P = S.state.projects;
  const kpis = t.channels.map(c => {
    const pct = c.per_week ? Math.min(100, (c.published / c.per_week) * 100) : 0;
    return `<div class="kpi"><div class="l">${esc(c.name)} · this week</div><b>${c.published}<span class="muted" style="font-size:14px;font-weight:500"> / ${c.per_week}</span></b>
      <div class="l">${c.planned} planned · ${c.in_progress} in progress</div><div class="bar"><i class="${c.published < c.per_week ? "behind" : ""}" style="width:${pct}%"></i></div></div>`;
  }).join("");
  const recent = P.slice(0, 8).map(pcard).join("");
  return `<h1>Dashboard</h1><p class="sub">${t.today} · week ${t.week[0]} → ${t.week[1]}</p>
    <div class="grid" style="grid-template-columns:minmax(360px,1.1fr) 2fr;margin-bottom:18px"><div class="card" id="todo-card"><div class="muted">loading to-do…</div></div><div><div class="kpis" style="margin:0">${kpis}</div></div></div>
    <div class="grid g3" style="margin-bottom:22px">
      <div class="card"><h3>Overdue</h3>${listRows(t.overdue, r => `<span class="pill bad">${r.days}d late</span>`)}</div>
      <div class="card"><h3>Due in 14 days</h3>${listRows(t.due_soon, r => `<span class="pill">${r.days === 0 ? "today" : "in " + r.days + "d"}</span>`)}</div>
      <div class="card"><h3>Drafts waiting for your review</h3>${listRows(t.in_review)}</div>
      <div class="card"><h3>Finals not yet on Drive</h3>${listRows(t.ready_to_ship)}</div>
      <div class="card"><h3>Needs a thumbnail <a data-nav="thumbs" class="tiny">board →</a></h3>${listRows(t.needs_thumbnail)}</div>
      <div class="card"><h3>Needs a description</h3>${listRows(t.needs_description)}</div>
    </div>
    <div class="row" style="justify-content:space-between;margin-bottom:10px"><h2 style="margin:0">Recent projects</h2><a data-nav="projects">all projects →</a></div>
    <div class="pgrid">${recent || `<div class="empty">No projects yet. Click <b>New project</b> or drop a recording in.</div>`}</div>
    <div class="row" style="justify-content:space-between;margin:26px 0 10px"><h2 style="margin:0">Everything else</h2><span class="muted small">competitors · Minecraft library · live realms · watchers · Drive · recordings · intros · music <a id="hub-refresh">refresh</a></span></div>
    <div id="hub" class="grid g3"><div class="empty">loading the hub…</div></div>`;
}
async function loadHub(fresh) {
  const el = $("#hub"); if (!el) return;
  try { const h = await api("hub" + (fresh ? "?fresh=1" : "")); if ($("#hub")) $("#hub").innerHTML = renderHub(h); wireCommon(); wireHub(h); } catch (e) { el.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}
function renderHub(h) {
  const c = h.competitors || {}, L = h.library || {}, R = h.realms || {}, D = h.drive || {};
  const card = (title, body, extra = "") => `<div class="card tight"><div class="row" style="justify-content:space-between;margin-bottom:6px"><h3 style="margin:0">${title}</h3><span class="muted tiny">${extra}</span></div>${body}</div>`;
  const recs = (h.recordings || []).map(r => `<div class="item" data-newfrom="${esc(r.path)}" title="start a project from this recording"><span class="t">${esc(r.name)}</span><span class="muted tiny">${fmtSize(r.size)} · ${esc(r.when)}${r.broll ? " · B-roll ✓" : ""}</span><button class="sm">new project</button></div>`).join("");
  const outl = (c.outliers || []).slice(0, 8).map(o => `<div class="item" data-url="${esc(o.url)}"><span class="pill ${o.status === "added" ? "st-final" : ""}" title="${esc(o.status)}">${esc(o.niche || "?")}</span><span class="t" title="${esc(o.title)}">${esc(o.title)}</span><span class="muted tiny">${(o.views || 0).toLocaleString()} · ${(+o.score || 0).toFixed(1)}×</span></div>`).join("");
  const vids = (L.videos || []).slice(0, 8).map(v => `<div class="item" ${v.folder ? `data-openf="${esc(v.folder)}"` : ""}><span class="t" title="${esc(v.title)}">${esc(v.title)}</span><span class="muted tiny">${v.entries} entries${v.website_posts ? " · " + v.website_posts + " drafts" : ""}${v.screenshots ? " · " + v.screenshots + " stills" : ""}${v.slug === L.current ? " · current" : ""}</span></div>`).join("");
  const live = (R.live || []).slice(0, 10).map(r => `<div class="item"><span class="pill ${r.status === "PLAYABLE" ? "st-final" : ""}">${r.status === "PLAYABLE" ? "live" : "opt-in"}</span><span class="t" title="${esc(r.code)}">${esc(r.name || r.code)}</span><span class="muted tiny">${esc(r.category || "")} · ${esc(r.checked)}</span></div>`).join("");
  const wat = (h.watchers || []).map(w => `<div style="margin-bottom:8px"><div class="row" style="gap:6px"><span class="pill ${w.alive === true ? "st-final" : w.alive === false ? "bad" : ""}">${w.alive === true ? "running" : w.alive === false ? "stopped" : "log"}</span><b class="small">${esc(w.name)}</b><a class="tiny" data-openf="${esc(w.log_path)}">log</a></div><div class="tiny muted" style="margin:3px 0 0 2px">${esc(w.what)}</div><div class="log tiny" style="max-height:70px;padding:6px 8px;margin-top:4px">${(w.log || []).map(esc).join("\n") || "no log"}</div></div>`).join("");
  const drv = (D.files || []).slice(0, 8).map(f => `<div class="item" data-openf="${esc(f.path)}"><span class="pill">${esc(f.channel)}</span><span class="t" title="${esc(f.name)}">${esc(f.name)}</span><span class="muted tiny">${esc(f.when)}</span></div>`).join("");
  const intros = (h.intros || []).slice(0, 10).map(i => `<div class="item" data-openf="${esc(i.render || i.path)}"><span class="pill">${esc(i.kind)}</span><span class="t">${esc(i.name)}</span><span class="muted tiny">${esc(i.when)}${i.render ? "" : " · no render"}</span></div>`).join("");
  const vo = (h.vo || []).map(v => `<div class="item" data-openf="${esc(v.path)}"><span class="t">${esc(v.name)}</span><span class="muted tiny">${esc(v.when)}</span></div>`).join("");
  const mus = (h.music || []).map(m => `<div class="item" data-openf="${esc(m.path)}"><span class="t">${esc(m.name)}</span><span class="muted tiny">${m.count}</span></div>`).join("");
  return card("Recordings not in a project", `<div class="list">${recs || `<div class="empty">every recording is assigned</div>`}</div>`, "{{RECORDINGS}}")
    + card("Competitor outliers", `<div class="list">${outl || `<div class="empty">no outliers (run tracker.py scan)</div>`}</div>`, `${c.total || 0} open · scan ${esc(c.last_scan || "never")}${c.report ? ` · <a data-openf="${esc(c.report)}">report</a>` : ""}`)
    + card("Minecraft library (mc.py)", `<div class="list">${vids || `<div class="empty">no videos in library.json</div>`}</div>`, `${L.mods || 0} add-ons · ${L.servers || 0} servers · ${L.clients || 0} clients`)
    + card("Live realms (Realm Checker)", `<div class="list">${live || `<div class="empty">no realms database</div>`}</div>`, `${R.live_total || 0} live of ${Object.values(R.counts || {}).reduce((a, b) => a + b, 0)} checked`)
    + card("Watchers", wat || `<div class="empty">no watchers</div>`)
    + card("Drive · finished videos", `<div class="list">${drv || `<div class="empty">${D.ok ? "nothing on Drive yet" : "Drive root not mounted"}</div>`}</div>`, `${D.total || 0} files`)
    + card("Intro + graphic templates (HyperFrames)", `<div class="list">${intros || `<div class="empty">none</div>`}</div>`, "_Assets\Graphics")
    + card("Voice-over takes", `<div class="list">${vo || `<div class="empty">none</div>`}</div>`, "Audacity")
    + card("Music library", `<div class="list">${mus || `<div class="empty">none</div>`}</div>`, "{{MUSIC_ROOT}}");
}
function wireHub(h) {
  $$("[data-newfrom]").forEach(el => el.onclick = () => newProjectModal({ main: el.dataset.newfrom }));
  $$("[data-url]").forEach(el => el.onclick = () => window.open(el.dataset.url, "_blank"));
  $$("[data-openf]").forEach(el => el.onclick = e => { e.stopPropagation(); api("open", { path: el.dataset.openf }).catch(e => toast(e.message, "bad")); });
  $("#hub-refresh") && ($("#hub-refresh").onclick = () => loadHub(true));
}

// ---------------------------------------------------------------- projects grid
function viewProjects() {
  const f = S.filter || {};
  const P = S.state.projects.filter(p => (!f.type || p.type === f.type) && (!f.stage || p.stage === f.stage) && (!f.q || p.title.toLowerCase().includes(f.q)));
  setTimeout(() => {
    $("#f-type").onchange = e => { S.filter = { ...f, type: e.target.value }; render(); };
    $("#f-stage").onchange = e => { S.filter = { ...f, stage: e.target.value }; render(); };
    $("#f-q").oninput = e => { S.filter = { ...f, q: e.target.value.toLowerCase() }; $(".pgrid").innerHTML = S.state.projects.filter(p => (!S.filter.type || p.type === S.filter.type) && (!S.filter.stage || p.stage === S.filter.stage) && p.title.toLowerCase().includes(S.filter.q)).map(pcard).join(""); wireCommon(); };
  });
  return `<h1>Projects</h1><p class="sub">Every video, resumable. Click one to pick it back up.</p>
    <div class="row" style="margin-bottom:16px">
      <input id="f-q" placeholder="search…" value="${esc(f.q || "")}" style="width:240px">
      <select id="f-type"><option value="">all types</option>${Object.entries(S.state.types).map(([k, v]) => `<option value="${k}" ${f.type === k ? "selected" : ""}>${esc(v.label)}</option>`).join("")}</select>
      <select id="f-stage"><option value="">all stages</option>${S.state.stages.map(s => `<option value="${s}" ${f.stage === s ? "selected" : ""}>${esc(S.state.stage_labels[s])}</option>`).join("")}</select>
      <span class="muted small">${P.length} shown</span></div>
    <div class="pgrid">${P.map(pcard).join("") || `<div class="empty">nothing matches</div>`}</div>`;
}

// ---------------------------------------------------------------- tracker (board + calendar)
function viewTracker() {
  const P = S.state.projects, today = S.state.tracker.today;
  const cols = S.state.stages.map(s => `<div class="col"><h4>${esc(S.state.stage_labels[s])}<span>${P.filter(p => p.stage === s).length}</span></h4>
    ${P.filter(p => p.stage === s).map(p => `<div class="bc" data-open="${p.id}"><span class="pill type-${p.type}" style="margin-right:6px">${esc(S.state.types[p.type].icon)}</span>${esc(p.title)}<small>${esc(p.channel || "")}${p.due ? " · due " + p.due : ""}${!p.checklist.thumbnail && s !== "idea" ? " · 🖼 thumb" : ""}</small></div>`).join("")}</div>`).join("");
  const d0 = new Date(today + "T00:00:00"); d0.setDate(d0.getDate() - d0.getDay() + 1);
  const days = [];
  for (let i = 0; i < 21; i++) { const d = new Date(d0); d.setDate(d0.getDate() + i); days.push(d); }
  const iso = d => d.toISOString().slice(0, 10);
  const cal = days.map(d => { const k = iso(d); const ev = P.filter(p => p.due === k || (p.stage === "published" && p.published_on === k));
    return `<div class="day ${k === today ? "today" : ""}"><div class="d">${d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })}</div>${ev.map(p => `<div class="ev ${p.type} ${p.due < today && p.stage !== "published" ? "late" : ""}" data-open="${p.id}" title="${esc(p.title)}">${p.stage === "published" ? "✓ " : ""}${esc(p.title)}</div>`).join("")}</div>`; }).join("");
  return `<h1>Tracker</h1><p class="sub">Stages are worked out from each project's checklist (override in the project header). Due dates drive the calendar.</p>
    <div class="board" style="margin-bottom:22px">${cols}</div>
    <h2>Three weeks</h2><div class="cal">${cal}</div>
    <div class="card" style="margin-top:22px"><div class="row" style="justify-content:space-between"><h2 style="margin:0">TickTick boards</h2><button id="tt-load" class="sm">Load from TickTick</button></div><div id="tt-boards" class="muted small" style="margin-top:8px">Reads the channel boards through the TickTick bot's token (read only).</div></div>`;
}
async function loadTickTick(el) {
  el.innerHTML = "loading…";
  try {
    const r = await api("ticktick/boards");
    if (!r.ok) { el.innerHTML = `<span class="bad">${esc(r.error)}</span>`; return; }
    el.innerHTML = `<div class="grid g2">` + r.channels.map(c => `<div><b>${esc(c.name)}</b> <span class="muted">${c.target ? c.target[0] + "x/" + c.target[1] : ""} · ${c.cards.length} cards</span>
      <div class="list" style="margin-top:6px">${c.cards.slice(0, 12).map(k => `<div class="item"><span class="t">${esc(k.title)}</span><span class="pill">${esc(k.column)}</span><span class="muted small">${esc(k.due)}</span></div>`).join("")}${c.cards.length > 12 ? `<div class="muted small">+${c.cards.length - 12} more</div>` : ""}</div></div>`).join("") + `</div>`;
  } catch (e) { el.innerHTML = `<span class="bad">${esc(e.message)}</span>`; }
}

// ---------------------------------------------------------------- settings
function viewSettings() {
  const s = S.state.settings;
  return `<h1>Settings</h1><p class="sub">Where things live. Saved to data\\settings.json.</p>
    <div class="grid g2">
    <div class="card"><h3>Folders</h3>
      <div class="field"><label>Gaming projects ({{GAMING_ROOT}}\\&lt;title&gt;)</label><input id="s-gaming" value="${esc(s.roots.gaming)}"></div>
      <div class="field"><label>Phone + review projects ({{PROJECTS_ROOT}}\\&lt;name&gt;)</label><input id="s-phone" value="${esc(s.roots.phone)}"></div>
      <div class="field"><label>Google Drive hand-off root (one folder per channel)</label><input id="s-drive" value="${esc(s.drive_root)}"></div>
      <div class="field"><label>OBS recording folders (comma separated)</label><input id="s-rec" value="${esc(s.recordings.join(", "))}"></div>
      <div class="field"><label>Voice-over folder (Audacity)</label><input id="s-vo" value="${esc(s.vo_folder)}"></div>
      <div class="field"><label>Music library</label><input id="s-music" value="${esc(s.music_root)}"></div>
      <button class="primary" id="s-save">Save</button></div>
    <div class="card"><h3>Channels + weekly targets</h3>
      <table id="s-ch"><tr><th>Channel</th><th>Type</th><th>/week</th><th>Drive folder</th><th></th></tr>
      ${s.channels.map((c, i) => `<tr><td><input value="${esc(c.name)}" data-k="name"></td><td><select data-k="type">${["gaming", "phone", "review", "haul", "short"].map(t => `<option ${c.types[0] === t ? "selected" : ""}>${t}</option>`).join("")}</select></td><td><input class="t" type="number" value="${c.per_week}" data-k="per_week" style="width:60px"></td><td><input value="${esc(c.drive || "")}" data-k="drive"></td><td><button class="sm danger" data-del="${i}">✕</button></td></tr>`).join("")}
      </table><div class="row" style="margin-top:10px"><button class="sm" id="s-ch-add">+ channel</button><span class="grow"></span><button class="primary" id="s-ch-save">Save channels</button></div>
      <p class="muted small" style="margin-top:12px">The tracker counts published videos per channel per week against these targets.</p></div>
    </div>
    <div class="card" style="margin-top:14px"><h3>How it fits together</h3><div class="kv">
      <b>Gaming</b><span>app\\gaming\\*.py — a generalized port of the Top 5 Realms edit. Work in &lt;project&gt;\\Edit\\studio, output in &lt;project&gt;\\Edit.</span>
      <b>Phone / app</b><span>{{KIT}}/tools\\phone_edit\\pipeline.py (the Uber Eats pipeline), resumable. Output in &lt;project&gt;\\output.</span>
      <b>Product review</b><span>review_pipeline\\scripts\\edit_review.py. Output in &lt;project&gt;\\output.</span>
      <b>Notes</b><span>"cut 1:22-1:30", "protect 2:03-2:10", "broll 3:20 6s castle", "section #5 Dragonforge 11:09-15:30" — times are from the draft you watched, they get mapped back to the recording.</span>
      <b>Drive</b><span>Only FINAL renders go to Drive.</span>
    </div></div>`;
}
function wireSettings() {
  $("#s-save").onclick = async () => {
    await api("settings", { roots: { gaming: $("#s-gaming").value, phone: $("#s-phone").value, review: $("#s-phone").value }, drive_root: $("#s-drive").value,
      recordings: $("#s-rec").value.split(",").map(x => x.trim()).filter(Boolean), vo_folder: $("#s-vo").value, music_root: $("#s-music").value });
    toast("Settings saved", "ok"); refresh();
  };
  const readCh = () => $$("#s-ch tr").slice(1).map(tr => ({ name: $("[data-k=name]", tr).value.trim(), types: [$("[data-k=type]", tr).value], per_week: +$("[data-k=per_week]", tr).value || 0, drive: $("[data-k=drive]", tr).value.trim() })).filter(c => c.name);
  $("#s-ch-save").onclick = async () => { await api("settings", { channels: readCh() }); toast("Channels saved", "ok"); refresh(); };
  $("#s-ch-add").onclick = () => { S.state.settings.channels = readCh().concat([{ name: "", types: ["gaming"], per_week: 1, drive: "" }]); render(); };
  $$("#s-ch [data-del]").forEach(b => b.onclick = () => { const ch = readCh(); ch.splice(+b.dataset.del, 1); S.state.settings.channels = ch; render(); });
  if ($("#s-ch-tt")) $("#s-ch-tt").onclick = async () => {
    const r = await api("ticktick/boards"); if (!r.ok) return toast(r.error, "bad");
    const cur = readCh();
    for (const c of r.channels) { const ex = cur.find(x => x.name.toLowerCase() === c.name.toLowerCase()); const pw = c.target && c.target[1] === "week" ? c.target[0] : (c.target ? Math.max(1, Math.round(c.target[0] / 4)) : 1);
      if (ex) ex.per_week = pw; else cur.push({ name: c.name, types: [/studio\s*mc/i.test(c.name) ? "gaming" : /review/i.test(c.name) && /shift/i.test(c.name) ? "phone" : "review"], per_week: pw, drive: c.name }); }
    S.state.settings.channels = cur; render(); toast("Imported " + r.channels.length + " boards (save to keep)", "ok");
  };
}

// ---------------------------------------------------------------- new project
function newProjectModal(prefill = {}) {
  const types = S.state.types, chans = S.state.settings.channels;
  const picked = { main: prefill.main || "", intro: "", intro_vo: "", broll: [] };
  let type = prefill.type || "gaming";
  const m = modal(`<h2>New project</h2>
    <div class="typepick">${Object.entries(types).map(([k, v]) => `<div class="tp ${k === type ? "on" : ""}" data-t="${k}"><b>${esc(v.icon)} ${esc(v.label)}</b><small>${esc(v.blurb)}</small></div>`).join("")}</div>
    <div class="grid g2">
      <div class="field"><label>Title (becomes the folder name)</label><input id="np-title" placeholder="Top 10 Minecraft Bedrock Dragon Addons" value="${esc(prefill.title || "")}"></div>
      <div class="row"><div class="field grow"><label>Channel</label><select id="np-ch">${chans.map(c => `<option ${c.types.includes(type) ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></div>
      <div class="field"><label>Due</label><input id="np-due" type="date"></div></div>
    </div>
    <div class="field"><label>Main footage (the OBS recording). Gaming projects reference it in place; phone/review projects copy it into raw\\.</label>
      <div class="dropz" id="np-main">Drop the recording here, pick from recent recordings below, or <a id="np-main-browse">browse…</a><div class="picked"></div></div>
      <div class="recent" id="np-recent"><span class="muted small">loading recent recordings…</span></div></div>
    <div class="grid g2">
      <div class="field"><label>Intro: a rendered intro MP4, or a voice-over WAV for the automatic intro (optional)</label><div class="dropz" id="np-intro">Drop or <a id="np-intro-browse">browse…</a><div class="picked"></div></div></div>
      <div class="field"><label>B-roll clips (optional, more can be added later)</label><div class="dropz" id="np-broll">Drop or <a id="np-broll-browse">browse…</a><div class="picked"></div></div></div>
    </div>
    <div class="row" style="justify-content:flex-end;margin-top:8px"><button id="np-cancel">Cancel</button><button class="primary big" id="np-create">Create project</button></div>`, "wide");
  const show = () => { $("#np-main .picked", m).textContent = picked.main ? base(picked.main) : ""; $("#np-intro .picked", m).textContent = base(picked.intro || picked.intro_vo); $("#np-broll .picked", m).textContent = picked.broll.map(base).join(", "); };
  $$(".tp", m).forEach(el => el.onclick = () => { type = el.dataset.t; $$(".tp", m).forEach(x => x.classList.toggle("on", x === el)); const c = chans.find(c => c.types.includes(type)); if (c) $("#np-ch", m).value = c.name; });
  const dz = (id, fn, kind) => { const el = $(id, m); el.ondragover = e => { e.preventDefault(); el.classList.add("over"); }; el.ondragleave = () => el.classList.remove("over");
    el.ondrop = e => { e.preventDefault(); el.classList.remove("over"); const ps = dropPaths(e); if (!ps.length) { toast("Drag-and-drop paths need the desktop window; use browse… here", "bad"); return; } fn(ps); show(); };
    $(id + "-browse", m).onclick = async e => { e.stopPropagation(); const ps = await pickFiles(kind, kind !== "video1"); if (ps.length) { fn(ps); show(); } }; };
  dz("#np-main", ps => { picked.main = ps[0]; if (!$("#np-title", m).value) $("#np-title", m).value = base(ps[0]).replace(/\.[^.]+$/, ""); }, "video");
  dz("#np-intro", ps => { const p = ps[0]; if (/\.(wav|mp3|m4a|flac)$/i.test(p)) { picked.intro_vo = p; picked.intro = ""; } else { picked.intro = p; picked.intro_vo = ""; } }, "media");
  dz("#np-broll", ps => { picked.broll.push(...ps); }, "video");
  api("recent").then(r => { $("#np-recent", m).innerHTML = r.items.map(i => `<div class="re" data-p="${esc(i.path)}" data-k="${i.kind}"><b>${esc(i.name)}</b><small>${fmtSize(i.size)} · ${new Date(i.mtime * 1000).toLocaleString()}</small></div>`).join("") || `<span class="muted small">no recordings found</span>`;
    $$(".re", m).forEach(el => el.onclick = () => { if (el.dataset.k === "audio") { picked.intro_vo = el.dataset.p; picked.intro = ""; } else { picked.main = el.dataset.p; if (!$("#np-title", m).value) $("#np-title", m).value = base(el.dataset.p).replace(/\.[^.]+$/, ""); } $$(".re", m).forEach(x => x.classList.toggle("sel", x.dataset.p === picked.main || x.dataset.p === picked.intro_vo)); show(); }); });
  $("#np-cancel", m).onclick = closeModal;
  $("#np-create", m).onclick = async () => {
    const title = $("#np-title", m).value.trim(); if (!title) return toast("Give it a title", "bad");
    const b = $("#np-create", m); b.disabled = true; b.textContent = "Creating…";
    try {
      const files = {}; if (picked.main) files.main = picked.main; if (picked.intro) files.intro = picked.intro; if (picked.intro_vo) files.intro_vo = picked.intro_vo; if (picked.broll.length) files.broll = picked.broll;
      const p = await api("projects", { title, type, channel: $("#np-ch", m).value, due: $("#np-due", m).value, files });
      closeModal(); await refresh(true); nav("project", p.id); toast("Project created", "ok");
    } catch (e) { toast(e.message, "bad"); b.disabled = false; b.textContent = "Create project"; }
  };
}
async function adoptFolder() {
  const ps = await browseModal({ dirsOnly: true });
  if (!ps.length) return;
  const m = modal(`<h2>Open existing folder</h2><p class="muted">${esc(ps[0])}</p>
    <div class="typepick">${Object.entries(S.state.types).map(([k, v]) => `<div class="tp" data-t="${k}"><b>${esc(v.icon)} ${esc(v.label)}</b><small>${esc(v.blurb)}</small></div>`).join("")}</div>
    <div class="row"><div class="field grow"><label>Channel</label><select id="ad-ch">${S.state.settings.channels.map(c => `<option>${esc(c.name)}</option>`).join("")}</select></div>
    <div class="field grow"><label>Recording (optional, if it isn't in raw\\)</label><div class="row"><input id="ad-src" class="grow" placeholder="{{RECORDINGS}}\\….mp4"><button id="ad-src-b" class="sm">browse</button></div></div></div>
    <div class="row" style="justify-content:flex-end"><button id="ad-cancel">Cancel</button><button class="primary" id="ad-ok">Open as project</button></div>`);
  let type = ""; $$(".tp", m).forEach(el => el.onclick = () => { type = el.dataset.t; $$(".tp", m).forEach(x => x.classList.toggle("on", x === el)); const c = S.state.settings.channels.find(c => c.types.includes(type)); if (c) $("#ad-ch", m).value = c.name; });
  $("#ad-src-b", m).onclick = async () => { const r = await pickFiles("video", false); if (r[0]) $("#ad-src", m).value = r[0]; };
  $("#ad-cancel", m).onclick = closeModal;
  $("#ad-ok", m).onclick = async () => { try { const p = await api("projects/adopt", { path: ps[0], type: type || undefined, channel: $("#ad-ch", m).value, source: $("#ad-src", m).value || undefined }); closeModal(); await refresh(true); nav("project", p.id); } catch (e) { toast(e.message, "bad"); } };
}

// ---------------------------------------------------------------- project page
async function loadProject() {
  try { S.project = await api(`project?id=${S.pid}`); } catch (e) { $("#main").innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  renderProject();
}
const SLOT_DEFS = {
  gaming: [["main", "Recording", "video", "The OBS capture (webcam + game). Referenced in place."], ["intro", "Intro", "media", "Rendered intro MP4 (HyperFrames). Drop a VO wav to park it for a hand-made intro."], ["broll", "B-roll", "video", "Clips for the talking-intro reel and cutaways (or the Director sidecar is used)."], ["card", "Cards", "video", "Transparent MOVs (code / IP cards) → Graphics\\cards. Auto-matched to #N sections."], ["thumbnail", "Thumbnail", "image", "YouTube thumbnail (PNG/JPG) or grab a frame."], ["description", "Description", "text", "youtube-description.txt (chapters get filled in)."], ["article", "Articles", "text", "Roundup / entry articles / listings for website + listings."]],
  phone: [["main", "Recording", "video", "3840x1080 OBS capture (webcam left, mirrored phone right). Copied to raw\\source.mp4."], ["intro_vo", "Intro VO", "audio", "Your intro voice-over WAV → automatic intro (or drop a finished intro MP4)."], ["broll", "B-roll", "video", "Optional cutaways."], ["thumbnail", "Thumbnail", "image", "YouTube thumbnail or grab a frame."], ["description", "Description", "text", "youtube-description.txt with the codes."]],
  short: [["main", "Vertical clip(s)", "video", "The raw vertical recording(s) in order. Copied to raw\clips, normalised to 1080x1920 60 fps into raw\source.mp4."], ["broll", "B-roll", "video", "Optional cutaways."], ["thumbnail", "Cover", "image", "Optional Short cover frame."], ["description", "Description", "text", "Short title / description."]],
  haul: [["main", "Phone clips", "video", "The phone recording(s) in recording order (IMG_6814.MOV, IMG_6815.MOV ...). Copied to raw\clips, normalised to 1080p60 into raw\source.mp4."], ["broll", "B-roll", "video", "Optional cutaways."], ["thumbnail", "Thumbnail", "image", "YouTube thumbnail or grab a frame."], ["description", "Description", "text", "YouTube description."]],
  review: [["main", "Camera / Gling XML", "any", "raw\\camera.mp4 (dual camera) or the Gling edit.xml (preferred)."], ["screen", "Screen recording", "video", "Optional raw\\screen.mp4."], ["broll", "B-roll", "video", "Clips into raw\\broll (re-render picks them up)."], ["thumbnail", "Thumbnail", "image", "YouTube thumbnail or grab a frame."], ["description", "Description", "text", "YouTube description."]],
};
function slotValue(p, slot) {
  if (slot === "main") return p.source ? [p.source] : [];
  if (slot === "intro") return [p.slots.intro, p.slots.intro_vo].filter(Boolean);
  if (slot === "intro_vo") return [p.slots.intro_vo, p.slots.intro].filter(Boolean);
  if (slot === "broll") return p.slots.broll || [];
  if (slot === "article") return p.slots.articles || [];
  if (slot === "card") return (p.timeline && p.timeline.cards) ? Object.values(p.timeline.cards) : [];
  if (slot === "screen") return [];
  return p.slots[slot] ? [p.slots[slot]] : [];
}
// redraw without restarting the player: adding a note mid-watch keeps the draft playing from the same spot
function keepVideo(sel, redraw) {
  const v = $(sel), st = v && v.getAttribute("src") && { src: v.getAttribute("src"), t: v.currentTime, playing: !v.paused && !v.ended, vol: v.volume, muted: v.muted, rate: v.playbackRate };
  const put = () => { const n = $(sel); if (!st || !n || n === v || n.getAttribute("src") !== st.src) return;
    const go = () => { n.currentTime = st.t; n.volume = st.vol; n.muted = st.muted; n.playbackRate = st.rate; if (st.playing) n.play().catch(() => {}); };
    n.readyState ? go() : n.addEventListener("loadedmetadata", go, { once: true }); };
  const r = redraw();
  return r && r.then ? r.then(x => (put(), x)) : (put(), r);
}
// every note is a "revision": its status, and its draft time as a button that jumps the player there
const NOTE_STATUS = { applied: ["✓ applied", "st-final"], partly: ["◐ partly done", "warn"], claude: ["Claude is on it…", ""], check: ["Claude finished · check the chat", ""], failed: ["✕ couldn't apply", "bad"], pending: ["applied on next rebuild", ""] };
function noteStatus(n) { const st = n.status || (n.done ? "applied" : "pending"); return st === "applied" && /\bnot done\b/i.test(n.how || "") ? "partly" : st; }
// revisions grouped by the round they were sent in (user 2026-10-23): newest batch on top, finished ones fold up
const BATCH_OPEN = {};
const BATCH_STATUS = { working: ["AI working", "act-revising"], open: [null, "warn"], done: ["done", "st-final"], next: ["not sent yet", ""] };
function notesHtml(p) {
  const B = p.batches || [];
  if (!B.length) return notesFlat(p, (p.notes || []).map((n, i) => i));
  const hhmm = s => (s || "").slice(11, 16);
  const latestDone = B.find(b => b.status !== "next");
  return `<div class="bsum muted tiny">${B.filter(b => b.n !== "next").length} batch${B.filter(b => b.n !== "next").length === 1 ? "" : "es"} · ${(p.notes || []).length} notes</div>` + B.map(b => {
    const key = p.id + ":" + b.n;
    const open = key in BATCH_OPEN ? BATCH_OPEN[key] : (b.status !== "done" || b === latestDone);
    const [lab, cls] = BATCH_STATUS[b.status] || BATCH_STATUS.done;
    const pill = `<span class="pill ${cls}">${esc(b.status === "open" ? `${b.open} open` : lab)}</span>`;
    const when = b.n === "next" ? "press Apply revisions + rebuild to send them" : `sent ${hhmm(b.sent)}${b.last_added && hhmm(b.last_added) !== hhmm(b.sent) ? "–" + hhmm(b.last_added) : ""}`;
    const drew = b.draft ? ` · built ${esc(b.draft.label)} at ${hhmm(b.draft.when)}` : b.status === "working" ? " · new draft on the way" : "";
    const q = (p.activity || {}).state === "waiting" && b.status === "working" ? ` · <span class="pill act act-waiting">#${p.activity.pos} in line</span>` : "";
    return `<div class="batch ${b.status === "working" ? "live" : ""} ${open ? "" : "shut"}" data-batch="${esc(key)}">
      <div class="bhead"><span class="chev">${open ? "▾" : "▸"}</span><b>${b.n === "next" ? "Next batch" : "Batch " + b.n}</b>${pill}<span class="muted small">${b.notes.length} note${b.notes.length === 1 ? "" : "s"} · ${when}${drew}${q}</span></div>
      <div class="bbody">${notesFlat(p, b.notes)}</div></div>`;
  }).join("");
}
function notesFlat(p, idxs) {
  return idxs.map(i => {
    const n = p.notes[i];
    const st = noteStatus(n), [label, cls] = NOTE_STATUS[st] || NOTE_STATUS.pending;
    const at = n.t0 != null ? `<button class="sm tjump" data-seekd="${n.t0}" title="jump the player here">▶ ${fmtT2(n.t0)}${n.t1 != null ? "–" + fmtT2(n.t1) : ""}</button>` : "";
    const text = esc(n.text).replace(/\b(\d{1,2}:\d{2}(?:\.\d)?)\b/g, m => `<a class="tlink" data-seekd="${parseT(m)}">${m}</a>`);
    return `<div class="note ${st === "applied" ? "done" : ""}"><span class="k revision">revision</span><div class="t">${at} ${text}
      <div class="raw"><span class="pill ${cls}">${label}</span> <button class="sm scope ${n.applies === "rule" ? "rule" : "one"}" data-nscope="${esc(n.nid || "")}" data-v="${n.applies === "rule" ? "video" : "rule"}" title="${esc(n.applies_why || "")} (click to flip). This video = fixed only here; rule = changes every video and must pass the rule gate">${n.applies === "rule" ? "rule" : "this video"}</button>${n.how ? " " + esc(n.how) : ""}</div>
      ${n.unresolved ? `<div class="unres">⚠ ${esc(n.unresolved)}</div>` : ""}</div>
      ${st === "applied" || st === "failed" || st === "check" ? `<button data-ntoggle="${i}" title="run it again on the next rebuild">↻</button>` : ""}<button data-ndel="${i}" title="remove">✕</button></div>`;
  }).join("");
}
// while Claude applies revisions: a live panel with what it is doing right now (no chat), elapsed time and its last steps
function claudeBox(p) {
  const c = p.claude;
  if (!c || !c.busy) return "";
  const steps = c.steps || [], now = steps[steps.length - 1];
  return `<div class="prog running" style="margin-top:10px"><div class="prog-head"><b>Claude is working on your revisions · ${esc(now ? now.text : "reading the notes and the project…")}</b><span class="muted small">${fmtEta(c.elapsed)} elapsed · ${steps.length} step${steps.length === 1 ? "" : "s"} so far</span></div>
    <div class="prog-bar"><i style="width:100%"></i></div>
    ${steps.length > 1 ? `<div class="cl-steps">${steps.slice(0, -1).reverse().map(s => `<div><span class="muted tiny">${Math.floor(s.t / 60)}:${String(s.t % 60).padStart(2, "0")}</span> ${esc(s.text)}</div>`).join("")}</div>` : ""}</div>`;
}
const REV_POLL = {};
function pollRevisions(pid, redraw) {
  if (REV_POLL[pid]) return;
  REV_POLL[pid] = setInterval(async () => {
    if (S.view !== "project" || S.pid !== pid) { clearInterval(REV_POLL[pid]); delete REV_POLL[pid]; return; }
    try {
      S.project = await api("project?id=" + pid); redraw();
      const cb = $("#rv-claude"); if (cb) cb.innerHTML = claudeBox(S.project);
      const pg = $("#p-progress"); if (pg) pg.innerHTML = progressBar(S.project);
      if (S.project.jobs.length) pollJobs(pid);   // Claude started the rebuild through the app: show its steps too
      if (!(S.project.claude || {}).busy && !(S.project.notes || []).some(n => n.status === "claude")) { clearInterval(REV_POLL[pid]); delete REV_POLL[pid]; toast("Claude finished the revisions", "ok"); }
    } catch (e) { }
  }, 3000);
}
function parseT(s) { const p = s.split(":").map(Number); return p.length === 2 ? p[0] * 60 + p[1] : +s; }
function wireNotes(p) {
  const redraw = () => { const box = $("#p-notes"); if (box) { box.innerHTML = notesHtml(S.project) || `<div class="empty">no revisions yet</div>`; wireNotes(S.project); } };
  $$("[data-ndel]").forEach(b => b.onclick = async () => { S.project = await api("project/notes?id=" + p.id, { remove: +b.dataset.ndel }); redraw(); });
  $$("[data-nscope]").forEach(b => b.onclick = async () => { S.project = await api("project/notes?id=" + p.id, { applies_nid: b.dataset.nscope, value: b.dataset.v }); redraw(); });
  $$("[data-ntoggle]").forEach(b => b.onclick = async () => { S.project = await api("project/notes?id=" + p.id, { toggle: +b.dataset.ntoggle }); redraw(); });
  $$(".batch .bhead").forEach(h => h.onclick = () => { const el = h.parentElement, k = el.dataset.batch; BATCH_OPEN[k] = el.classList.contains("shut"); el.classList.toggle("shut"); h.querySelector(".chev").textContent = BATCH_OPEN[k] ? "▾" : "▸"; });
  $$("[data-seekd]").forEach(b => b.onclick = () => { const v = $("#p-video"); if (!v) return; v.currentTime = Math.max(0, +b.dataset.seekd - 1); v.play().catch(() => {}); v.scrollIntoView({ behavior: "smooth", block: "center" }); });
  return redraw;
}
// the player remembers where it was per file, so no redraw (adding a revision, a build finishing) sends it back to 0:00
const VPOS = {};
document.addEventListener("timeupdate", e => { const v = e.target; if (v.tagName === "VIDEO" && v.currentTime > 0.5) VPOS[v.getAttribute("src")] = v.currentTime; }, true);
document.addEventListener("loadedmetadata", e => { const v = e.target; if (v.tagName !== "VIDEO") return; const t = VPOS[v.getAttribute("src")]; if (t && v.currentTime < 0.5 && t < v.duration - 1) v.currentTime = t; }, true);
function renderProject() {
  const p = S.project, T = S.state.types[p.type];
  const info = p.source_info;
  const done = Object.values(p.checklist).filter(Boolean).length;
  const running = p.jobs[0];
  const outs = p.outputs, latest = outs[outs.length - 1];
  const tab = (S.tab[p.id] === "chat" ? (S.tab[p.id] = "editor") : S.tab[p.id]) || "pipeline";
  const slots = SLOT_DEFS[p.type].map(([id, label, kind, hint]) => {
    const vals = slotValue(p, id);
    const multi = ["broll", "article", "card"].includes(id);
    return `<div class="slot ${vals.length ? "filled" : ""}" data-slot="${id}" data-kind="${kind}">
      <h4>${esc(label)}${vals.length && !multi ? "" : `<span class="dim">${vals.length ? vals.length : ""}</span>`}</h4>
      ${vals.length ? (multi ? `<div class="f">${vals.slice(0, 4).map(v => `<div class="fn" title="${esc(v)}">${esc(base(v))}</div>`).join("")}${vals.length > 4 ? `<div class="fi">+${vals.length - 4} more</div>` : ""}</div>` :
        `<div class="f"><div class="fn" title="${esc(vals[0])}">${esc(base(vals[0]))}</div>${id === "main" && info ? `<div class="fi">${info.width}x${info.height} · ${Math.round(info.fps)} fps · ${fmtT(info.duration)} · ${fmtSize(info.size)} · ${esc(p.layout)}${info.audio.length ? " · " + info.audio.length + " audio" : ""}</div>` : ""}</div>`)
        : `<div class="hint">${esc(hint)}</div>`}
      <div class="acts"><button class="sm" data-pick="${id}">${vals.length && !multi ? "replace" : "add"}…</button>
        ${vals.length ? `<button class="sm" data-openf="${esc(vals[0])}">open</button>` : ""}
        ${id === "thumbnail" && p.source ? `<button class="sm" data-grab="1">grab frame</button>` : ""}
        ${id === "main" && !vals.length ? `<button class="sm" data-recent="1">recent recordings</button>` : ""}</div>
      ${vals.length && !multi && !["description", "article"].includes(id) ? `<button class="x" data-clear="${id}" title="remove">✕</button>` : ""}</div>`;
  }).join("");
  const steps = p.steps.map(s => { const js = running?.steps.find(x => x.id === s.id); const st = js && js.status !== "pending" ? (js.status === "skipped" ? "done" : js.status) : s.status;
    return `<div class="step ${st}"><span class="dot"></span><span class="l">${esc(s.label)}</span><span class="s">${st === "n/a" ? "" : st}</span>${!running && ((p.type === "gaming" && ["prep", "transcribe", "sections", "cuts"].includes(s.id)) || s.id === "graphics") ? `<button data-run="${s.id}" title="${s.id === "graphics" ? "make the motion graphic again (new article / phrases), then Build to put it in" : "re-run just this step"}">re-run</button>` : ""}</div>`; }).join("");
  const notes = notesHtml(p);
  $("#main").innerHTML = `
    <div class="ph">
      <div class="ph-main">
        <a class="ph-back" data-nav="projects" title="all projects">←</a>
        <div class="th" id="p-thumb" hidden style="background-image:${p.thumb ? `url('${thumbUrl(p.thumb, p.thumb_crop, null, 640)}')` : "none"}" title="click to grab a thumbnail frame"><span>${p.slots.thumbnail ? "thumbnail" : "set thumbnail"}</span></div>
        <div class="ph-id"><input class="title-in" id="p-title" value="${esc(p.title)}" spellcheck="false">
          <div class="ph-pills"><span class="pill type-${p.type}">${esc(T.icon)} ${esc(T.label)}</span><span class="pill st-${p.stage}">${esc(S.state.stage_labels[p.stage])}</span>${p.activity ? `<span class="pill act act-${p.activity.state}" data-nav="queue" title="open the queue">${esc(p.activity.label)}</span>` : ""}<span class="ph-meta">${esc(p.channel || "no channel")}${p.due ? ` · due ${esc(p.due)}` : ""}</span></div></div>
        <div class="ph-acts"><button class="ghost sm ph-det-t" id="p-det-t" title="channel, due date, checklist and files">Details <b>${done}/${Object.keys(p.checklist).length}</b> <span class="car">▾</span></button>
          <div class="menu-wrap"><button class="ghost icon" id="p-more" title="more">⋯</button><div class="menu" id="p-menu"><button id="p-folder">Open folder</button><button id="p-brief">Brief for Claude</button><button class="danger" id="p-forget" title="forget this project (files stay)">Forget project</button></div></div></div>
      </div>
      <div id="p-progress">${progressBar(p)}</div>
      <div class="ph-details" id="p-details" ${(S.det || {})[p.id] || !p.source ? "" : "hidden"}>
        <div class="meta">
          <label>Channel <select id="p-ch"><option value="">—</option>${S.state.settings.channels.map(c => `<option ${c.name === p.channel ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></label>
          <label>Due <input id="p-due" type="date" value="${esc(p.due || "")}"></label>
          <label>Stage <select id="p-stage"><option value="">auto (${esc(S.state.stage_labels[p.stage])})</option>${S.state.stages.map(s => `<option value="${s}" ${p.stage_manual === s ? "selected" : ""}>${esc(S.state.stage_labels[s])}</option>`).join("")}</select></label>
          <span class="muted tiny grow" style="text-align:right">${esc(p.path)}</span></div>
        <div class="check">${p.checklist_labels.map(([k, l]) => `<div class="chk ${p.checklist[k] ? "on" : ""}" data-chk="${k}"><i>${p.checklist[k] ? "✓" : ""}</i>${esc(l)}</div>`).join("")}</div>
        <div class="slots">${slots}</div>
      </div>
    </div>
    <div class="tabs">${[["editor", "Editor"], ["review", "Revisions"], ["pipeline", "Build"], ...(p.type === "gaming" ? [["sections", "Sections + music"]] : []), ["shorts", "Shorts"]].map(([k, l]) => `<a data-tab="${k}" class="${tab === k ? "active" : ""}">${esc(l)}${k === "review" && (p.notes || []).some(n => !n.done && !n.batch) ? `<b class="tab-n">${(p.notes || []).filter(n => !n.done && !n.batch).length}</b>` : ""}</a>`).join("")}</div>
    <div id="tabbody"></div>`;
  const body = $("#tabbody");
  if (tab === "pipeline") body.innerHTML = `<div class="grid g2">
      <div class="card"><div class="row" style="justify-content:space-between;margin-bottom:10px"><h2 style="margin:0">Pipeline</h2><label class="small muted"><input type="checkbox" id="p-force"> force rebuild</label></div>
        <div class="steps">${steps}</div>
        <div class="row" style="margin-top:14px">${running ? `<button class="danger" id="p-cancel">Cancel job</button><span class="muted small">${esc(running.steps.find(s => s.status === "running")?.label || "")}</span>` :
          `<button class="primary big" id="p-draft" ${!p.source ? "disabled" : ""}>▶ Build DRAFT</button><button class="ok big" id="p-final" ${!p.source ? "disabled" : ""}>Render FINAL</button>${p.type === "review" ? `<button id="p-brollplan">B-roll shot list</button>` : ""}<button id="p-check">QC check</button>`}</div>
        <p class="muted small" style="margin-top:10px">${p.type === "gaming" ? "Draft = 960x540 30 fps review copy (fast). Final = 1080p60. Steps whose outputs are newer than their inputs are skipped, so a second build only redoes what changed." : p.type === "phone" ? "Runs the phone_edit pipeline (transcribe → trim → privacy blur → layout → graphics → intro → main → join + QC). It resumes: notes only redo the stale steps." : "Runs edit_review.py (two-mic swap, cuts from the Gling XML, camera switching, callouts, music). Force = --fresh."}</p></div>
      <div class="card"><div class="row" style="justify-content:space-between;margin-bottom:8px"><h2 style="margin:0">Log</h2><span class="muted small" id="p-logstat">${running ? "running…" : "last run"}</span></div><div class="log" id="p-log">${(p.log_tail || []).map(esc).join("\n") || "no log yet"}</div></div></div>${buildHistory(p)}`;
  else if (tab === "review") body.innerHTML = `<div class="grid g2">
      <div class="card"><div class="row" style="justify-content:space-between;margin-bottom:8px"><h2 style="margin:0">Watch</h2><select id="p-out">${outs.map((o, i) => `<option value="${esc(o.file)}" ${i === outs.length - 1 ? "selected" : ""}>${o.kind.toUpperCase()} · ${esc(base(o.file))}</option>`).join("") || "<option value=''>no render yet</option>"}</select></div>
        ${latest ? `<video id="p-video" controls preload="metadata" src="${mediaUrl(latest.file)}"></video>` : `<div class="empty">Build a draft first</div>`}
        <div class="row" style="margin-top:8px"><button class="sm" id="p-in" title="set the START of the range to where the player is">⇤ Mark start</button><button class="sm" id="p-outm" title="set the END of the range to where the player is">Mark end ⇥</button><button class="sm" id="p-mark">⏱ note at this time</button><button class="sm" data-openf="${esc(latest?.file || "")}" ${latest ? "" : "disabled"}>open in player</button><button class="sm" id="p-reveal" ${latest ? "" : "disabled"}>show in folder</button><span class="grow"></span>${p.timeline?.report?.length ? `<button class="sm" id="p-report">report</button>` : ""}</div></div>
      <div class="card"><h2>Revisions</h2>
        <div class="row" style="margin-bottom:6px"><button class="sm talk" id="p-talk" title="stamps the player time, keeps playing, records what you say">🎙 Talk a note here</button><button class="sm" id="p-talk-end" style="display:none" title="stamp where the thing you're describing ends">⇥ End here</button><span class="muted tiny" id="p-talk-status">press it at the moment something's wrong, keep watching and talk; press ⇥ End here when it ends, then ■ to stop</span></div>
        <div class="note-box"><textarea id="p-note" data-mic="note" rows="3" placeholder="cut 1:00-1:30 · protect 2:03-2:10 · broll 3:20 6s castle
or in your own words: note 1:12-1:19: there's a weird animation here, take it out
Enter adds the note · Shift+Enter new line · 🎙 to talk"></textarea><button class="primary" id="p-note-add">Add</button></div>
        <div id="p-note-preview" class="note-preview muted tiny"></div>
        <p class="muted small" style="margin:6px 0 0">Times are from the video you are watching (intro included). Exact notes (<code>cut 1:22-1:30</code>, <code>protect …</code>) go straight to the cutter.${p.type === "phone" ? " Notes in your own words (“2:20 remove ‘to’”, “cut at 3:02, pick back up at 3:24”) are read by Opus when you rebuild." : ""}</p>
        <div class="notes" id="p-notes">${notes || `<div class="empty">no revisions yet</div>`}</div>
        <div class="row" style="margin-top:10px"><button class="primary" id="p-rebuild-notes" ${p.jobs.length ? "disabled" : ""}>▶ Apply revisions + rebuild</button><span class="muted tiny">${p.jobs.length ? "a build is running; its steps are below" : "you get a notification when it starts and when the new draft is ready"}</span></div>
        <div id="rv-claude">${claudeBox(p)}</div>
        <div id="rv-prog">${p.jobs.length ? reviseProgress(p.jobs[0]) : ""}</div>
        ${p.timeline?.cuts_md?.length ? `<details style="margin-top:12px"><summary class="muted small">Cutter's review list (${p.timeline.cuts_md.length} lines)</summary><div class="log" style="max-height:260px">${p.timeline.cuts_md.map(esc).join("\n")}</div></details>` : ""}</div></div>`;
  else if (tab === "editor") { wireProject(p, tab); renderEditor(p); return; }
  else if (tab === "chat") { wireProject(p, tab); renderChat(p); return; }
  else if (tab === "shorts") { wireProject(p, tab); renderFactory(p); return; }
  else if (tab === "sections") body.innerHTML = renderSections(p);
  else if (tab === "deliver") body.innerHTML = renderDeliver(p);
  wireProject(p, tab);
}
function renderSections(p) {
  const tl = p.timeline || {}, secs = tl.sections || [], music = tl.music || {}, cards = tl.cards || {}, uMusic = p.settings.music || {};
  const rows = secs.map((s, i) => `<tr data-i="${i}"><td><input value="${esc(s[0])}" data-k="name"></td><td><input class="t" value="${fmtT2(s[1])}" data-k="s"></td><td><input class="t" value="${fmtT2(s[2])}" data-k="e"></td>
    <td class="muted small">${fmtT(s[2] - s[1])}</td>
    <td><div class="row" style="gap:4px"><span class="small" title="${esc((uMusic[s[0]] || music[s[0]] || {}).track || "")}">${esc(base((uMusic[s[0]] || music[s[0]] || {}).track || "")).replace(/\.mp3$/i, "") || "<span class='dim'>auto</span>"}</span><button class="sm" data-music="${esc(s[0])}">pick</button>${uMusic[s[0]] ? `<button class="sm" data-music-clear="${esc(s[0])}">auto</button>` : ""}</div></td>
    <td><input value="${esc((p.settings.cards_codes || {})[s[0]] || "")}" data-k="code" placeholder="realm code" style="width:120px"></td>
    <td class="small">${cards[s[0]] ? esc(base(cards[s[0]])) : "<span class='dim'>—</span>"}</td><td><button class="sm danger" data-sdel="${i}">✕</button></td></tr>`).join("");
  const lines = (p.transcript_lines || []).map(l => { const inSec = secs.find(s => l.t >= s[1] && l.t <= s[2]); return `<div class="tr-line ${inSec ? "in" : ""}" data-t="${l.t}" data-e="${l.e}" title="${inSec ? esc(inSec[0]) : "outside every section (cut)"}"><span class="t">${fmtT2(l.t)}</span><span>${esc(l.text)}</span></div>`; }).join("");
  return `<div class="grid g2">
    <div class="card"><div class="row" style="justify-content:space-between;margin-bottom:8px"><h2 style="margin:0">Sections</h2><div class="row"><button class="sm" id="s-add">+ section</button><button class="sm" id="s-redetect" title="re-run the automatic detection (overwrites your edits)">re-detect</button><button class="sm" id="s-cards" title="type each realm's code in the Code column, then render the typed-code cards (HyperFrames) for the next build">🃏 Render code cards</button><button class="primary sm" id="s-save">Save sections</button></div></div>
      <p class="muted small">Recording times. Everything outside a section is cut. Names like <code>#5 Dragonforge</code>, <code>HM Village City</code>, <code>intro</code>, <code>outro</code> drive the wipes, cards, chapters and music. Click a transcript line to set the selected row's start (shift+click: end).</p>
      <table><tr><th>Name</th><th>Start</th><th>End</th><th></th><th>Music</th><th>Code</th><th>Card</th><th></th></tr>${rows || `<tr><td colspan="7" class="dim">No sections yet: build the draft once (transcript + auto-detect) or add rows by hand.</td></tr>`}</table>
      <h3 style="margin-top:16px">Rules</h3><div class="kv small"><b>Music</b><span>soft game OSTs from the vetted pool, rotating per section; Pokémon sections get Pokémon music; intro/outro have their own. Pick overrides from {{MUSIC_ROOT}} (unvetted tracks are marked).</span>
      <b>Cards</b><span>transparent MOVs in Graphics\\ matched by rank number / name (code cards, IP cards). Drop more in the Cards slot.</span>
      <b>Game audio</b><span>track ${esc(String(tl.source?.game_track ?? "—"))} at ${p.settings.game_volume ?? 0.3} · mic track ${esc(String(tl.source?.mic_track ?? "—"))} · webcam ${esc(tl.source?.webcam_side || "?")}</span></div></div>
    <div class="card"><h2>Transcript</h2>${lines ? `<div class="tr-lines">${lines}</div>` : `<div class="empty">No transcript yet. Build the draft (or re-run “Transcript”).</div>`}</div></div>`;
}
function renderDeliver(p) {
  const d = p.drive, arts = p.articles || [], mp = p.website || { posts: [] };
  return `<div class="grid g2">
    <div class="card"><div class="row" style="justify-content:space-between"><h2 style="margin:0">YouTube description</h2><div class="row"><button class="sm" id="d-chapters" title="fill chapter times from the last build">chapters</button><button class="primary sm" id="d-save">Save</button></div></div>
      <textarea id="d-desc" style="min-height:260px;margin-top:8px" placeholder="Paste or write the description. Chapter lines like '0:00 #5 Name' get the real times after a build.">${esc(p.description_text || "")}</textarea>
      ${p.timeline?.chapters?.length ? `<div class="mono muted" style="margin-top:6px">${p.timeline.chapters.map(esc).join("<br>")}</div>` : ""}</div>
    <div class="card"><h2>Google Drive hand-off</h2>
      <div class="kv small"><b>Folder</b><span class="mono">${esc(d.folder)}</span><b>Status</b><span>${d.root_ok ? (d.exists ? `<span style="color:var(--ok)">folder exists · ${d.files.length} files</span>` : "not sent yet") : `<span style="color:var(--bad)">Drive root not found (is Google Drive running?)</span>`}</span></div>
      ${d.files.length ? `<div class="list" style="margin-top:8px">${d.files.map(f => `<div class="item"><span class="t">${esc(f.name)}</span><span class="muted small">${fmtSize(f.size)} · ${esc(f.when)}</span></div>`).join("")}</div>` : ""}
      <div class="row" style="margin-top:10px"><button class="ok" id="d-drive" ${p.outputs.some(o => o.kind === "final") && d.root_ok ? "" : "disabled"}>Send FINAL + description + thumbnail to Drive</button>${d.exists ? `<button class="sm" data-openf="${esc(d.folder)}">open</button>` : ""}</div>
      <p class="muted small">Finals only. The TickTick bot watches this folder and checks the card off when the video lands, so drafts never go here.</p>
      <hr><h2>TickTick</h2><div class="row"><button id="d-tt" class="sm">Create card on ${esc(p.channel || "channel")} board</button><span class="muted small">${p.checklist.ticktick ? "card created ✓" : "adds an idea card with the folder path"}</span></div>
      <hr><h2>Published</h2><div class="row"><input id="d-yt" class="grow" placeholder="YouTube URL once it is up" value="${esc(p.links.youtube || "")}"><input id="d-pubon" type="date" value="${esc(p.published_on || "")}" title="published on"><button class="sm" id="d-yt-save">Save</button></div></div>
    ${p.type === "gaming" ? `<div class="card"><div class="row" style="justify-content:space-between"><h2 style="margin:0">Articles + listings</h2><button class="sm" data-pick="article">add file…</button></div>
      ${arts.length ? `<div class="list" style="margin-top:8px">${arts.map(a => `<div class="item" data-openf="${esc(a.file)}"><span class="pill">${esc(a.kind)}</span><span class="t">${esc(a.name)}</span><span class="muted small">${esc(a.when)}</span></div>`).join("")}</div>` : `<div class="empty">No articles found in the project folder (mc.py organize writes Roundup article.html + #NN/article.html).</div>`}
      <h3 style="margin-top:14px">website drafts</h3>${mp.posts.length ? `<div class="list">${mp.posts.map(x => `<div class="item"><span class="t">${esc(x.entry)}</span><span class="pill">${esc(x.status)}</span><a href="${esc(x.url)}" target="_blank" class="small">post ${esc(x.post_id)}</a></div>`).join("")}</div>` : `<span class="muted small">none recorded in library.json${mp.slug ? " for " + esc(mp.slug) : ""} (mc.py website uploads drafts; IDs land there)</span>`}
      <h3 style="margin-top:14px">listings</h3><span class="muted small">After a realm video: every featured realm gets a listing + article (approve only realms that pass the join test). Tick “Articles / listings” above when done.</span></div>` : ""}
    <div class="card"><h2>Renders</h2>${p.renders.length ? `<div class="list">${[...p.renders].reverse().map(r => `<div class="item" data-openf="${esc(r.file)}"><span class="pill ${r.kind === "final" ? "st-final" : ""}">${esc(r.kind)}</span><span class="t">${esc(base(r.file))}</span><span class="muted small">${fmtSize(r.size)} · ${esc(r.when)}</span></div>`).join("")}</div>` : `<div class="empty">no renders yet</div>`}</div></div>`;
}

function wireProject(p, tab) {
  const save = async patch => { S.project = await api("project/update?id=" + p.id, patch); await refresh(true); renderProject(); };
  $("#p-title").onchange = async e => { const t = e.target.value.trim(); if (!t || t === p.title) return; try { const r = await api("project/rename?id=" + p.id, { title: t, folder: true }); toast(`Renamed to “${r.title}” (folder + files too)`, "ok"); await refresh(true); await loadProject(); } catch (err) { toast(err.message, "bad"); e.target.value = p.title; } };
  $("#p-ch").onchange = e => save({ channel: e.target.value });
  $("#p-due").onchange = e => save({ due: e.target.value });
  $("#p-stage").onchange = e => save({ stage_manual: e.target.value });
  $$("[data-chk]").forEach(el => el.onclick = () => save({ checklist: { [el.dataset.chk]: !p.checklist[el.dataset.chk] } }));
  $("#p-folder").onclick = () => api("open", { path: p.path });
  $("#p-forget").onclick = async () => { if (confirm("Forget this project? Files stay where they are.")) { await api("project/delete?id=" + p.id, {}); await refresh(true); nav("projects"); } };
  $("#p-brief").onclick = async () => { const task = prompt("What do you want Claude to do with this project?", "Hand-polish the intro / fix the notes / write the articles"); if (task === null) return; const r = await api("project/brief?id=" + p.id, { task }); await api("clipboard", { text: r.text }); toast("Brief copied to the clipboard — paste it to Claude", "ok"); };
  if ($("#p-thumb")) $("#p-thumb").onclick = () => frameGrabber(p);
  $$("[data-rebuild]").forEach(b => b.onclick = async () => { try { await api("project/run?id=" + p.id, { action: "draft" }); await loadProject(); pollJobs(p.id); } catch (e) { toast(e.message, "bad"); } });
  $$("[data-tab-go]").forEach(b => b.onclick = () => { S.tab[p.id] = b.dataset.tabGo; renderProject(); });
  if (p.jobs.length) pollJobs(p.id);
  if (!p.jobs.length && p.external) pollExternal(p.id);
  $$("[data-openf]").forEach(el => el.onclick = e => { e.stopPropagation(); if (el.dataset.openf) api("open", { path: el.dataset.openf }).catch(e => toast(e.message, "bad")); });
  $$("[data-tab]").forEach(a => a.onclick = () => { S.tab[p.id] = a.dataset.tab; S.scrollTabs = true; renderProject(); });
  if (S.scrollTabs) { S.scrollTabs = false; const t = $(".tabs"), m = $("#main"); if (t && m) m.scrollTop = t.offsetTop - 4; }
  // slots
  $$(".slot").forEach(el => {
    el.ondragover = e => { e.preventDefault(); e.stopPropagation(); el.classList.add("over"); };
    el.ondragleave = () => el.classList.remove("over");
    el.ondrop = async e => { e.preventDefault(); e.stopPropagation(); el.classList.remove("over"); $("#drop-veil").classList.remove("on"); const ps = dropPaths(e); if (!ps.length) return toast("Dropped files have no path here (browser mode). Use add…", "bad"); await addToSlot(p, el.dataset.slot, ps); };
  });
  $$("[data-pick]").forEach(b => b.onclick = async () => { const slot = b.dataset.pick; const kind = SLOT_DEFS[p.type].find(s => s[0] === slot)?.[2] || "any"; const ps = await pickFiles(kind, ["broll", "article", "card"].includes(slot)); if (ps.length) await addToSlot(p, slot, ps); });
  $$("[data-clear]").forEach(b => b.onclick = async () => { S.project = await api("project/slot/remove?id=" + p.id, { slot: b.dataset.clear }); renderProject(); });
  $$("[data-grab]").forEach(b => b.onclick = () => frameGrabber(p));
  $$("[data-recent]").forEach(b => b.onclick = async () => { const r = await api("recent"); const m = modal(`<h2>Recent recordings</h2><div class="recent">${r.items.filter(i => i.kind === "video").map(i => `<div class="re" data-p="${esc(i.path)}"><b>${esc(i.name)}</b><small>${fmtSize(i.size)} · ${new Date(i.mtime * 1000).toLocaleString()}</small></div>`).join("")}</div>`); $$(".re", m).forEach(el => el.onclick = async () => { closeModal(); await addToSlot(p, "main", [el.dataset.p]); }); });
  // pipeline
  const run = async (action, extra = {}) => { try { await api("project/run?id=" + p.id, { action, force: $("#p-force")?.checked, ...extra }); S.tab[p.id] = "pipeline"; await loadProject(); pollJobs(p.id); } catch (e) { toast(e.message, "bad"); } };
  if (tab === "pipeline") {
    $("#p-draft") && ($("#p-draft").onclick = () => run("draft"));
    $("#p-final") && ($("#p-final").onclick = () => { if (confirm("Render the FINAL (full quality)? Make sure the draft is approved.")) run("final"); });
    $("#p-check") && ($("#p-check").onclick = () => run("check"));
    $("#p-brollplan") && ($("#p-brollplan").onclick = () => run("broll_plan"));
    $("#p-cancel") && ($("#p-cancel").onclick = async () => { await api("job/cancel?id=" + p.jobs[0].id, {}); setTimeout(loadProject, 800); });
    $$("[data-run]").forEach(b => b.onclick = () => run(b.dataset.run, { force: true }));
    if (p.jobs.length) pollJobs(p.id);
  if (!p.jobs.length && p.external) pollExternal(p.id);
  }
  if (tab === "review") {
    const v = $("#p-video");
    $("#p-out") && ($("#p-out").onchange = e => { if (v) { v.src = mediaUrl(e.target.value); v.load(); } });
    const MARK = S.mark || (S.mark = {});
    const setRange = () => { if (MARK.a == null) return; const b = MARK.b != null && MARK.b > MARK.a ? MARK.b : null; const i = $("#p-note"); const rest = i.value.replace(/^\s*(cut|protect|broll|b-roll)?\s*\d+:\d{2}(\.\d)?(\s*-\s*\d+:\d{2}(\.\d)?)?\s*/i, ""); const verb = (i.value.match(/^\s*(cut|protect|broll|b-roll)/i) || [, "cut"])[1]; i.value = `${verb} ${fmtT2(MARK.a)}${b != null ? "-" + fmtT2(b) : ""} ${rest}`.trimEnd() + " "; i.dispatchEvent(new Event("input")); i.focus(); };
    $("#p-in").onclick = () => { const v = $("#p-video"); if (!v) return; MARK.a = v.currentTime; MARK.b = null; setRange(); toast("Start marked at " + fmtT2(MARK.a) + ": now play to the end and press Mark end", "ok"); };
    $("#p-outm").onclick = () => { const v = $("#p-video"); if (!v) return; if (MARK.a == null) return toast("Press Mark start first", "bad"); MARK.b = v.currentTime; setRange(); };
    let pvT = null;
    $("#p-note").oninput = () => { clearTimeout(pvT); pvT = setTimeout(async () => { const t = $("#p-note").value.trim(); const el = $("#p-note-preview"); if (!el) return; if (!t) { el.textContent = ""; return; } try { const r = await api("note-preview", { text: t }); el.innerHTML = notePreviewText(r, p); } catch (e) { } }, 250); };
    $("#p-mark").onclick = () => { const t = v ? v.currentTime : 0; const i = $("#p-note"); i.value = (i.value ? i.value + " " : "") + fmtT2(t) + "-" + fmtT2(t + 2) + " "; i.focus(); };
    // a note with no time of its own is stamped where the video was when he started writing it (2026-10-25, user: "when I
    // click add note it should automatically time stamp where I am in the video if I don't set one"); like the phone page
    const AT = { t: null };
    const grabAt = () => { const vv = $("#p-video"); if (AT.t == null && vv && vv.currentTime > 0) AT.t = vv.currentTime; };
    const hasTime = s => /\b\d{1,2}:\d{2}(\.\d+)?\b/.test(s);
    const add = async () => { const lines = $("#p-note").value.split(/\n+/).map(x => x.trim()).filter(Boolean); if (!lines.length) return;
      grabAt(); const at = AT.t; let stamped = false;
      const out = lines.map(t => { if (hasTime(t) || at == null) return t; stamped = true; return `note ${fmtT2(at)}-${fmtT2(at + 3)}: ${t}`; });
      try { for (const t of out) S.project = await api("project/notes?id=" + p.id, { text: t }); toast((lines.length > 1 ? `${lines.length} revisions added` : "Revision added") + (stamped ? ` at ${fmtT2(at)}` : ""), "ok"); $("#p-note").value = ""; $("#p-note-preview").textContent = ""; AT.t = null; redrawNotes(); } catch (e) { toast(e.message, "bad"); } };
    $("#p-note").addEventListener("focus", () => { const vv = $("#p-video"); if (vv && vv.paused) grabAt(); });   // paused on the problem
    $("#p-note").addEventListener("input", () => { if (!$("#p-note").value.trim()) AT.t = null; else grabAt(); });
    $("#p-note-add").onclick = add; $("#p-note").onkeydown = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); add(); } };
    const ta = $("#p-note"); const grow = () => { ta.style.height = "auto"; ta.style.height = Math.min(260, Math.max(70, ta.scrollHeight + 2)) + "px"; }; ta.addEventListener("input", grow);
    wireTalkNote(p);
    wireCutWatch(p);
    const redrawNotes = wireNotes(p);
    if ((p.claude || {}).busy || (p.notes || []).some(n => n.status === "claude")) pollRevisions(p.id, redrawNotes);   // reopened mid-revision
    $("#p-reveal") && ($("#p-reveal").onclick = () => latestOut(p) && api("open", { path: latestOut(p), reveal: true }));
    $("#p-report") && ($("#p-report").onclick = () => modal(`<h2>Pipeline report</h2><div class="log">${p.timeline.report.map(esc).join("\n")}</div>`));
    $("#p-rebuild-notes") && ($("#p-rebuild-notes").onclick = async () => {
      try { const r = await api("project/rebuild-notes?id=" + p.id, {}); if (r.mode === "claude") { toast(`Claude is applying ${r.text_notes} revision(s); you get a message when the new draft is ready`, "ok"); S.project = await api("project?id=" + p.id); redrawNotes(); pollRevisions(p.id, redrawNotes); return; } toast("Rebuilding the draft with your revisions", "ok"); await loadProject(); pollJobs(p.id); } catch (e) { toast(e.message, "bad"); }
    });
  }
  if (tab === "sections") wireSections(p);
  if (tab === "deliver") enhanceDeliver(p);
  if (tab === "pipeline") enhanceBuild(p);
  if (tab === "deliver") {
    $("#d-save").onclick = async () => { S.project = await api("project/description?id=" + p.id, { text: $("#d-desc").value }); toast("Description saved", "ok"); renderProject(); };
    $("#d-chapters").onclick = async () => { await $("#d-save").onclick(); try { await api("project/run?id=" + p.id, { action: "chapters_only" }); } catch (e) { toast("Build a draft first, then chapters get filled automatically", "bad"); } };
    $("#d-drive").onclick = async () => { if (!confirm("Copy the FINAL to Google Drive? The TickTick card gets checked off when it lands.")) return; try { const r = await api("project/drive?id=" + p.id, {}); toast("Sent: " + r.result.copied.map(c => c[0]).join(", "), "ok"); S.project = r.project; renderProject(); } catch (e) { toast(e.message, "bad"); } };
    $("#d-tt").onclick = async () => { try { const r = await api("project/ticktick?id=" + p.id, {}); toast("TickTick: " + r.result.result, "ok"); S.project = r.project; renderProject(); } catch (e) { toast(e.message, "bad"); } };
    $("#d-yt-save").onclick = () => save({ links: { youtube: $("#d-yt").value.trim() }, published_on: $("#d-pubon").value, checklist: { published: !!$("#d-yt").value.trim() } });
  }
}
const latestOut = p => p.outputs.length ? p.outputs[p.outputs.length - 1].file : "";
async function addToSlot(p, slot, paths) {
  try { const r = await api("project/slot?id=" + p.id, { slot, files: paths }); S.project = r.project; toast(`Added ${paths.length} file${paths.length > 1 ? "s" : ""} to ${slot}`, "ok"); renderProject(); refresh(true); } catch (e) { toast(e.message, "bad"); }
}
function wireSections(p) {
  const tl = p.timeline || {}; let secs = (tl.sections || []).map(s => [...s]); let selRow = 0;
  const readRows = () => $$("#tabbody table tr[data-i]").map(tr => [$("[data-k=name]", tr).value.trim(), parseT($("[data-k=s]", tr).value), parseT($("[data-k=e]", tr).value)]);
  const parseT = s => { const m = String(s).trim().match(/^(\d+):(\d+(?:\.\d+)?)$/); return m ? +m[1] * 60 + +m[2] : (+s || 0); };
  $$("#tabbody table tr[data-i]").forEach(tr => tr.onclick = () => { selRow = +tr.dataset.i; $$("#tabbody table tr[data-i]").forEach(x => x.style.outline = x === tr ? "1px solid var(--accent)" : ""); });
  $$(".tr-line").forEach(el => el.onclick = e => { const tr = $(`#tabbody table tr[data-i="${selRow}"]`); if (!tr) return toast("Add a section row first", "bad"); const k = e.shiftKey ? "e" : "s"; $(`[data-k=${k}]`, tr).value = fmtT2(e.shiftKey ? +el.dataset.e : +el.dataset.t); });
  const saveSecs = async rows => { S.project = await api("project/sections?id=" + p.id, { sections: rows.map(r => ({ name: r[0], s: r[1], e: r[2] })) }); renderProject(); toast("Sections saved — rebuild to apply", "ok"); };
  $("#s-save").onclick = () => saveSecs(readRows());
  const readCodes = () => Object.fromEntries($$("#tabbody table tr[data-i]").map(tr => [$("[data-k=name]", tr).value.trim(), $("[data-k=code]", tr).value.trim()]).filter(([n, c]) => n && c));
  $("#s-cards").onclick = async () => { const codes = readCodes(); if (!Object.keys(codes).length) return toast("Type a code in the Code column first", "bad"); try { await saveSecs(readRows()); await api("project/cards?id=" + p.id, { codes }); toast("Rendering cards… they get overlaid on the next build", "ok"); S.tab[p.id] = "pipeline"; await loadProject(); pollJobs(p.id); } catch (e) { toast(e.message, "bad"); } };
  $("#s-add").onclick = () => { const rows = readRows(); rows.push(["#" + Math.max(0, rows.filter(r => r[0].startsWith("#")).length) + " ", rows.length ? rows[rows.length - 1][2] : 0, (rows.length ? rows[rows.length - 1][2] : 0) + 60]); S.project.timeline.sections = rows; renderProject(); };
  $$("[data-sdel]").forEach(b => b.onclick = e => { e.stopPropagation(); const rows = readRows(); rows.splice(+b.dataset.sdel, 1); S.project.timeline.sections = rows; renderProject(); });
  $("#s-redetect").onclick = async () => { if (!confirm("Re-run the automatic detection? Your edits to the sections are replaced.")) return; try { await api("project/run?id=" + p.id, { action: "sections", force: true }); pollJobs(p.id); toast("Re-detecting…"); } catch (e) { toast(e.message, "bad"); } };
  $$("[data-music]").forEach(b => b.onclick = () => musicPicker(p, b.dataset.music));
  $$("[data-music-clear]").forEach(b => b.onclick = async () => { const m = { ...(p.settings.music || {}) }; delete m[b.dataset.musicClear]; S.project = await api("project/update?id=" + p.id, { settings: { music: m } }); renderProject(); });
}
async function musicPicker(p, section) {
  let sub = "Game Music";
  const m = modal(`<h2>Music for ${esc(section)}</h2><div class="row" style="margin-bottom:8px"><select id="m-sub"></select><input id="m-q" class="grow" placeholder="filter…"><span class="muted small">★ = vetted (no vocals / tags)</span></div><div class="files" style="max-height:60vh;overflow:auto;border:1px solid var(--line);border-radius:8px" id="m-list"></div>
    <div class="row" style="margin-top:8px"><label class="small muted">start at (s) <input id="m-off" type="number" value="0" style="width:80px"></label><span class="grow"></span><button id="m-cancel">Cancel</button></div>`, "wide");
  async function load() {
    const r = await api("music?sub=" + enc(sub));
    $("#m-sub", m).innerHTML = r.folders.map(f => `<option ${f === sub ? "selected" : ""}>${esc(f)}</option>`).join("");
    const q = ($("#m-q", m).value || "").toLowerCase();
    $("#m-list", m).innerHTML = r.items.filter(i => !q || i.name.toLowerCase().includes(q)).map(i => `<div class="fe" data-p="${esc(i.path)}" style="grid-template-columns:22px 1fr 200px 120px"><span title="${esc(i.scan || "")}">${i.vetted ? "★" : i.scan === "vocal" ? "🚫" : i.scan === "tag" ? "⚠" : "♪"}</span><span>${esc(i.name)}${i.scan ? ` <span class="tiny muted">(${esc(i.scan)}${i.words != null ? ", " + i.words + " words" : ""})</span>` : ""}</span><span class="dt">${esc(i.folder)}</span><span><button class="sm" data-play="${esc(i.path)}" title="preview">▶</button><button class="sm" data-scan="${esc(i.path)}" title="Whisper scan for vocals / producer tags (medium model, ~1 min)">${i.scan ? "rescan" : "scan"}</button></span></div>`).join("") || `<div class="empty">nothing here</div>`;
    $$("[data-play]", m).forEach(b => b.onclick = e => { e.stopPropagation(); playPreview(b.dataset.play, b); });
    $$("[data-scan]", m).forEach(b => b.onclick = async e => { e.stopPropagation(); try { await api("music/scan", { paths: [b.dataset.scan] }); b.textContent = "scanning…"; toast("Scanning in the background; the mark updates when it is done", "ok"); } catch (err) { toast(err.message, "bad"); } });
    $$(".fe", m).forEach(el => el.onclick = async () => { const music = { ...(p.settings.music || {}), [section]: { track: el.dataset.p, offset: +$("#m-off", m).value || 0 } }; S.project = await api("project/update?id=" + p.id, { settings: { music } }); closeModal(); renderProject(); toast("Music set — rebuild to apply", "ok"); });
  }
  $("#m-sub", m).onchange = e => { sub = e.target.value; load(); }; $("#m-q", m).oninput = load; $("#m-cancel", m).onclick = closeModal;
  load();
}
async function frameGrabber(p) {
  const src = latestOut(p) || p.source; if (!src) return toast("No footage to grab from yet", "bad");
  const info = p.source_info; const dur = (latestOut(p) ? null : info?.duration) || 600;
  const crop = latestOut(p) ? "" : p.thumb_crop || "";
  const n = 12, ts = [...Array(n)].map((_, i) => Math.round((dur * (i + 0.5)) / n));
  const m = modal(`<h2>Pick a thumbnail frame</h2><p class="muted small">From ${esc(base(src))}. Click a frame, or type a time.</p>
    <div class="frames">${ts.map(t => `<img src="${thumbUrl(src, crop, t, 320)}" data-t="${t}" title="${fmtT(t)}">`).join("")}</div>
    <div class="row" style="margin-top:10px"><input id="fg-t" placeholder="m:ss" style="width:90px"><button id="fg-go" class="sm">grab at time</button><span class="grow"></span><button id="fg-cancel">Cancel</button></div>`, "wide");
  const grab = async t => { try { S.project = await api("project/thumb?id=" + p.id, { file: src, t, crop }); closeModal(); if (S.view === "thumbs") viewThumbs(); else renderProject(); refresh(true); toast("Thumbnail frame saved (Thumbnail\\frame.png)", "ok"); } catch (e) { toast(e.message, "bad"); } };
  $$(".frames img", m).forEach(im => im.onclick = () => grab(+im.dataset.t));
  $("#fg-go", m).onclick = () => { const v = $("#fg-t", m).value.trim(); const mm = v.match(/^(\d+):(\d+)$/); grab(mm ? +mm[1] * 60 + +mm[2] : +v || 0); };
  $("#fg-cancel", m).onclick = closeModal;
  enhanceGrabber(p, m);
}
function pollJobs(pid) {
  if (S.pollers[pid]) return;
  S.pollers[pid] = setInterval(async () => {
    try {
      const st = await api("jobs"); const mine = st.jobs.filter(j => j.project_id === pid); const run = mine.find(j => j.status === "running" || j.status === "queued");
      S.state.jobs = st.jobs; renderSideJobs();
      if (S.view === "project" && S.pid === pid) {
        const j = run || mine.sort((a, b) => (b.started || 0) - (a.started || 0))[0];
        if (run && $("#rv-prog") && S.project) { S.project.jobs = [run]; $("#rv-prog").innerHTML = reviseProgress(run); }
        if (run && $("#p-progress") && S.project) { S.project.jobs = [run]; $("#p-progress").innerHTML = progressBar(S.project); $$("#p-progress [data-tab-go]").forEach(b => b.onclick = () => { S.tab[pid] = b.dataset.tabGo; renderProject(); }); }
        if (j && $("#p-log")) { const full = await api(`job?id=${j.id}&from=0`); const el = $("#p-log"); el.innerHTML = full.log.map(l => `<span class="${l.startsWith("==") || l.startsWith("--") ? "hl" : l.startsWith("!!") ? "bad" : ""}">${esc(l)}</span>`).join("\n"); el.scrollTop = el.scrollHeight; $("#p-logstat").textContent = full.status + (full.error ? " · " + full.error : "");
          full.steps.forEach(s => { const row = [...$$(".step")].find(r => $(".l", r).textContent.startsWith(s.label.split(" (")[0].slice(0, 12))); });
        }
        if (!run) { clearInterval(S.pollers[pid]); delete S.pollers[pid]; const last = mine[0]; toast(last?.status === "done" ? "Build finished" : "Job " + (last?.status || "ended") + (last?.error ? ": " + last.error : ""), last?.status === "done" ? "ok" : "bad"); await refresh(true); await loadProject(); }
      } else if (!run) { clearInterval(S.pollers[pid]); delete S.pollers[pid]; refresh(true); }
    } catch (e) { console.warn(e); }
  }, 1500);
}

// ---------------------------------------------------------------- global drop + boot
document.addEventListener("dragover", e => { e.preventDefault(); if (S.view === "project" && !e.target.closest(".slot") && !e.target.closest(".dropz")) $("#drop-veil").classList.add("on"); });
document.addEventListener("dragleave", e => { if (e.relatedTarget === null) $("#drop-veil").classList.remove("on"); });
document.addEventListener("drop", async e => {
  e.preventDefault(); $("#drop-veil").classList.remove("on");
  if (e.target.closest(".slot") || e.target.closest(".dropz")) return;
  const ps = dropPaths(e); if (!ps.length) return;
  if (S.view !== "project" || !S.project) { newProjectModal({ main: ps.find(p => /\.(mp4|mov|mkv|m4v)$/i.test(p)) || "" }); return; }
  const p = S.project;
  const m = modal(`<h2>Where do these go?</h2><p class="muted small">${ps.map(x => esc(base(x))).join(", ")}</p><div class="typepick" style="grid-template-columns:repeat(2,1fr)">${SLOT_DEFS[p.type].map(([id, label, kind, hint]) => `<div class="tp" data-s="${id}"><b>${esc(label)}</b><small>${esc(hint)}</small></div>`).join("")}</div><div class="row" style="justify-content:flex-end"><button id="w-cancel">Cancel</button></div>`);
  $$(".tp", m).forEach(el => el.onclick = async () => { closeModal(); await addToSlot(p, el.dataset.s, ps); });
  $("#w-cancel", m).onclick = closeModal;
});
$$("nav a").forEach(a => a.onclick = () => nav(a.dataset.view));
$("#btn-new").onclick = () => newProjectModal();
$("#btn-adopt").onclick = adoptFolder;
document.addEventListener("click", e => { if (e.target.id === "tt-load") loadTickTick($("#tt-boards")); });
refresh().then(() => { setInterval(() => { if (S.view !== "project") refresh(true).then(() => { if (S.view === "dashboard" || S.view === "tracker" || S.view === "projects") render(); }); }, 15000); });
// the queue page moves faster than the rest (renders finish, the next starts): every 4 s while it is open
setInterval(() => { if (S.view === "queue" && !document.hidden) refresh(true).then(() => { if (S.view === "queue") render(); }); }, 4000);

// ---------------------------------------------------------------- to-do (TickTick two-way)
async function loadTodo(el, full, fresh) {
  if (!el) return;
  try { const t = await api("todo" + (fresh ? "?fresh=1" : "")); el.innerHTML = renderTodo(t, full); wireTodo(el, t, full); } catch (e) { el.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}
function todoRow(r) {
  return `<div class="item todo" data-pid="${esc(r.pid)}" data-tid="${esc(r.tid)}"><i class="tick" title="complete in TickTick">○</i><span class="t" title="${esc(r.content || "")}">${esc(r.title)}</span><span class="muted tiny">${esc(r.list)}${r.priority >= 3 ? " · !" : ""}</span>${r.due ? `<span class="pill ${r.days < 0 ? "bad" : ""}">${r.days < 0 ? Math.abs(r.days) + "d late" : r.days === 0 ? "today" : r.due}</span>` : ""}<button class="sm" data-push="1" title="push to tomorrow">→ tmrw</button></div>`;
}
function renderTodo(t, full) {
  const head = `<div class="row" style="justify-content:space-between;margin-bottom:8px"><h2 style="margin:0">${full ? "Due today + overdue" : "To-do"}</h2><span class="muted tiny">${t.ok ? `${t.overdue.length + t.today.length} due · ${t.total_open} open` : `<span class="bad">TickTick offline</span>`}${t.queued?.length ? ` · ${t.queued.length} queued` : ""} <a data-todo-refresh="1">refresh</a>${full ? "" : ` · <a data-nav="todo">all →</a>`}</span></div>
    <div class="row" style="margin-bottom:8px"><input id="todo-new" class="grow" placeholder="add a task… (Enter)"><input id="todo-due" type="date" title="due" style="width:150px"><select id="todo-list" title="list"><option value="">Inbox</option></select><button class="primary sm" id="todo-add">Add</button></div>`;
  if (!t.ok) return head + `<div class="empty small">${esc(t.error || "no TickTick")}. Tasks you add are queued and pushed when it is back.</div>` + (t.queued?.length ? `<div class="list" style="margin-top:8px">${t.queued.map(q => `<div class="item"><span class="t">${esc(q.title)}</span><span class="muted tiny">queued</span></div>`).join("")}</div>` : "");
  const sec = (title, rows) => rows.length ? `<h3 style="margin:10px 0 6px">${title} <span class="dim">${rows.length}</span></h3><div class="list">${rows.map(todoRow).join("")}</div>` : "";
  let body = sec("Overdue", t.overdue) + sec("Today", t.today);
  if (!body) body = `<div class="empty small">Nothing due today 🎉</div>`;
  if (full) body += sec("Next 7 days", t.soon) + sec("No date", t.someday);
  else if (t.soon.length) body += `<div class="muted tiny" style="margin-top:8px">${t.soon.length} more this week</div>`;
  body += `<div class="row" style="margin-top:10px"><button class="sm" id="todo-tg" title="send today's list to your Telegram">📨 send to Telegram</button></div>`;
  return head + body;
}
function wireTodo(el, t, full) {
  const reload = fresh => loadTodo(el, full, fresh);
  $("[data-todo-refresh]", el).onclick = () => reload(true);
  api("todo/lists").then(r => { const sel = $("#todo-list", el); if (sel) sel.innerHTML = r.lists.map(l => `<option value="${esc(l.name)}">${esc(l.name)}</option>`).join(""); }).catch(() => {});
  const add = async () => { const title = $("#todo-new", el).value.trim(); if (!title) return; const r = await api("todo/add", { title, due: $("#todo-due", el).value, list: $("#todo-list", el).value }); toast(r.ok ? "Added to TickTick" : "TickTick offline: queued", r.ok ? "ok" : "bad"); reload(true); };
  $("#todo-add", el).onclick = add; $("#todo-new", el).onkeydown = e => { if (e.key === "Enter") add(); };
  $$(".todo", el).forEach(row => {
    $(".tick", row).onclick = async () => { row.style.opacity = .4; try { await api("todo/complete", { pid: row.dataset.pid, tid: row.dataset.tid }); toast("Done ✓", "ok"); reload(true); } catch (e) { toast(e.message, "bad"); row.style.opacity = 1; } };
    $("[data-push]", row).onclick = async () => { try { await api("todo/push", { pid: row.dataset.pid, tid: row.dataset.tid, days: 1 }); toast("Pushed to tomorrow", "ok"); reload(true); } catch (e) { toast(e.message, "bad"); } };
  });
  $("#todo-tg", el) && ($("#todo-tg", el).onclick = async () => { const rows = [...t.overdue, ...t.today]; const text = "📋 <b>To-do</b>\n\n" + (rows.length ? rows.map(r => `${r.days < 0 ? "⏰" : "•"} ${esc(r.title)} <i>(${esc(r.list)})</i>`).join("\n") : "Nothing due today 🎉"); try { await api("todo/telegram", { text }); toast("Sent to Telegram", "ok"); } catch (e) { toast(e.message, "bad"); } });
}

// builds started outside the app: refresh the bar every 4 s, reload the project when it ends
const EXT_POLL = {};
function pollExternal(pid) {
  if (EXT_POLL[pid]) return;
  EXT_POLL[pid] = setInterval(async () => {
    if (S.view !== "project" || S.pid !== pid) { clearInterval(EXT_POLL[pid]); delete EXT_POLL[pid]; return; }
    try {
      const r = await api("external?id=" + pid);
      if (!S.project) return;
      S.project.external = r.external;
      const el = $("#p-progress"); if (el) el.innerHTML = progressBar(S.project);
      if (!r.external) { clearInterval(EXT_POLL[pid]); delete EXT_POLL[pid]; toast("Outside build finished", "ok"); await refresh(true); await loadProject(); }
    } catch (e) { }
  }, 4000);
}

function notePreviewText(r, p) {
  const n = r.note, d = (a, b) => `${fmtT2(a)} → ${fmtT2(b)} (${Math.round(b - a)} s)`;
  if (n.kind === "cut") return (n.t1 - n.t0 <= 1.01 && !/-/.test(r.text)) ? `⚠ <b>cut ${fmtT2(n.t0)}</b> removes only 1 second. To cut a stretch, give an end time: <code>cut ${fmtT2(n.t0)}-${fmtT2(n.t0 + 30)}</code> or use Mark start / Mark end.` : `✂ will cut <b>${d(n.t0, n.t1)}</b> of this video`;
  if (n.kind === "protect") return `🛡 will protect <b>${d(n.t0, n.t1)}</b> (the cutter won't touch it)`;
  if (n.kind === "broll") return `🎞 B-roll over <b>${d(n.t0, n.t1)}</b>${n.clip ? " · clip “" + esc(n.clip) + "”" : ""}`;
  if (n.kind === "section") return `📍 section “${esc(n.name || "")}” <b>${d(n.t0, n.t1)}</b>`;
  return `💬 a revision for Claude${n.t0 != null ? ` about <b>${fmtT2(n.t0)}${n.t1 != null ? " → " + fmtT2(n.t1) : ""}</b>` : " (no time: add one so Opus knows where)"}: Claude reads it and applies it when you press Apply revisions`;
}

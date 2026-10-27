/* {{STUDIO_NAME}} UI, part 3: feature batch (writing with Opus, thumbnail suggestions, new-recording banner, disk cleanup,
   edit stats, music preview, weekly report, VA copy pack) + the Shorts Factory. Loaded after app.js and app2.js. */

// ---------------------------------------------------------------- shared
async function withBusy(btn, label, fn) {
  const old = btn.textContent; btn.disabled = true; btn.textContent = label;
  try { return await fn(); } catch (e) { toast(e.message, "bad"); } finally { btn.disabled = false; btn.textContent = old; }
}
const FILLER = /^(um+|uh+|uhm+|erm+|er|ah+|hmm+|mm+|eh)$/i;

// ---------------------------------------------------------------- 1. fillers + pauses in the editor
function fillerNotes() {
  const d = ED.data; if (!d) return [];
  const out = [];
  d.words.forEach((w, i) => {
    const clean = w.w.toLowerCase().replace(/[^a-z]/g, "");
    if (!FILLER.test(clean) || !inKeep((w.s + w.e) / 2)) return;
    const prev = d.words[i - 1], next = d.words[i + 1];
    // only fillers with a little air on one side, so the cut never clips a real word
    const airL = prev ? w.s - prev.e : 1, airR = next ? next.s - w.e : 1;
    if (airL < 0.08 && airR < 0.08) return;
    out.push({ kind: "cut", raw0: Math.max(0, w.s - 0.02), raw1: w.e + 0.02, text: `cut filler “${w.w}” ${fmtT2(w.s)}` });
  });
  return out;
}
function editorExtras(p) {
  const d = ED.data; if (!d || !$("#ed-tr")) return;
  // mark fillers + long pauses inside kept speech
  const spans = $$(".wd", $("#ed-tr"));
  spans.forEach(el => { const w = d.words[+el.dataset.i]; if (w && FILLER.test(w.w.toLowerCase().replace(/[^a-z]/g, ""))) el.classList.add("filler"); });
  spans.forEach(el => {
    const i = +el.dataset.i, w = d.words[i], nx = d.words[i + 1];
    if (!nx) return; const gap = nx.s - w.e;
    if (gap >= 1.2 && inKeep(w.e - 0.05) && inKeep(nx.s + 0.05)) el.insertAdjacentHTML("afterend", ` <span class="pz" title="pause inside the kept edit">⏸ ${gap.toFixed(1)}s</span>`);
  });
  const fn = fillerNotes();
  const bar = $("#ed-rebuild").parentElement;
  if (!$("#ed-fill")) bar.insertAdjacentHTML("beforeend", `<button class="sm" id="ed-fill" ${fn.length ? "" : "disabled"} title="add a cut note for every filler word (um, uh…) that has air around it">✂ Cut ${fn.length} fillers</button>`);
  $("#ed-fill").onclick = async () => {
    if (!fn.length) return;
    if (!confirm(`Add ${fn.length} cut notes for filler words (um, uh, er…)? Only fillers with a gap on at least one side are included, so neighbouring words are not clipped. They apply on the next build; untick any in Review + notes.`)) return;
    try { S.project = await api("project/notes?id=" + p.id, { notes: fn }); toast(`${fn.length} filler cuts noted for the next build`, "ok"); keepVideo("#ed-video", () => renderEditor(p)).then(() => editorExtras(p)); } catch (e) { toast(e.message, "bad"); }
  };
}

// ---------------------------------------------------------------- 2, 3, 10. Deliverables: write description, title ideas, VA pack
function enhanceDeliver(p) {
  const desc = $("#d-desc"); if (!desc) return;
  const head = desc.previousElementSibling;
  head.querySelector(".row").insertAdjacentHTML("afterbegin", `<button class="sm" id="d-write" title="Opus 5.5 writes it from the transcript, chapters and your codes (about a minute)">✍ Write with Opus</button>`);
  desc.insertAdjacentHTML("beforebegin", `<div class="row" style="margin-top:8px"><input id="d-yt" class="grow" placeholder="YouTube title (what the video goes up as)" value="${esc(p.yt_title || "")}"><button class="sm" id="d-titles" title="10 title ideas from Opus 5.5">💡 Title ideas</button></div>
    <div id="d-ideas" class="ideas">${(p.title_ideas || []).map(t => `<span class="idea" data-t="${esc(t)}">${esc(t)}</span>`).join("")}</div>`);
  const card = desc.closest(".card");
  card.insertAdjacentHTML("beforeend", `<div class="row" style="margin-top:10px"><button class="primary sm" id="d-va" title="title, description, files, Drive folder and Shorts in one copy">📋 Copy for VA</button><span class="muted tiny">everything your VA needs to upload, in one paste</span></div>`);
  $("#d-write").onclick = e => withBusy(e.target, "writing…", async () => { const r = await api("project/write-description?id=" + p.id, {}); desc.value = r.text; toast("Draft description written: read it, then Save", "ok"); });
  const wireIdeas = () => $$("#d-ideas .idea").forEach(el => el.onclick = async () => { $("#d-yt").value = el.dataset.t; await api("project/update?id=" + p.id, { yt_title: el.dataset.t }); toast("YouTube title set", "ok"); });
  wireIdeas();
  $("#d-titles").onclick = e => withBusy(e.target, "thinking…", async () => { const r = await api("project/titles?id=" + p.id, {}); $("#d-ideas").innerHTML = r.titles.map(t => `<span class="idea" data-t="${esc(t)}">${esc(t)}</span>`).join(""); wireIdeas(); });
  $("#d-yt").onchange = async e => { await api("project/update?id=" + p.id, { yt_title: e.target.value.trim() }); toast("YouTube title saved", "ok"); };
  $("#d-va").onclick = async () => { const r = await api("project/va?id=" + p.id); await api("clipboard", { text: r.text }); toast("Copied: title, description, files, Drive folder, Shorts", "ok"); };
}

// ---------------------------------------------------------------- 4. thumbnail frame suggestions
async function enhanceGrabber(p, m) {
  const frames = $(".frames", m); if (!frames) return;
  frames.insertAdjacentHTML("beforebegin", `<h3 style="margin:4px 0 6px">Suggested <span class="muted tiny" id="fg-sug-note">finding expressive faces and sharp frames…</span></h3><div class="frames" id="fg-sug"></div><h3 style="margin:12px 0 6px">Evenly spaced</h3>`);
  try {
    const r = await api("project/frames?id=" + p.id);
    if (!$("#fg-sug", m)) return;
    $("#fg-sug-note", m).textContent = "faces ranked by expression (mouth open, brows up), scenes by sharpness";
    $("#fg-sug", m).innerHTML = r.frames.map(f => `<div class="sug"><img src="${thumbUrl(f.file, f.crop, f.t, 320)}" data-t="${f.t}" data-f="${esc(f.file)}" data-c="${f.crop || ""}" title="${fmtT(f.t)} · ${f.kind}"><span>${f.kind === "face" ? "🙂" : "🎮"} ${fmtT(f.t)}</span></div>`).join("") || `<span class="muted small">nothing found</span>`;
    $$("#fg-sug img", m).forEach(im => im.onclick = async () => { try { S.project = await api("project/thumb?id=" + p.id, { file: im.dataset.f, t: +im.dataset.t, crop: im.dataset.c }); closeModal(); if (S.view === "thumbs") viewThumbs(); else renderProject(); refresh(true); toast("Thumbnail frame saved", "ok"); } catch (e) { toast(e.message, "bad"); } });
  } catch (e) { const n = $("#fg-sug-note", m); if (n) n.textContent = e.message; }
}

// ---------------------------------------------------------------- 5 + 9. dashboard: new-recording banner, weekly report
async function enhanceDashboard() {
  const main = $("#main"); if (!main || S.view !== "dashboard") return;
  try {
    const nr = await api("new-recordings");
    if (nr.items.length && S.view === "dashboard" && !$("#nr-banner")) {
      main.querySelector(".sub").insertAdjacentHTML("afterend", `<div id="nr-banner" class="banner">${nr.items.map(i => `<div class="row"><span>🎬 New recording: <b>${esc(i.label && !i.label.startsWith("(") ? i.label : i.name)}</b> <span class="muted tiny">${esc(i.name)} · ${esc(i.when)}</span></span><span class="grow"></span><button class="primary sm" data-nr="${esc(i.path)}">Create project</button></div>`).join("")}</div>`);
      $$("[data-nr]").forEach(b => b.onclick = () => newProjectModal({ main: b.dataset.nr }));
    }
  } catch (e) { }
  try {
    const r = await api("report");
    if (S.view !== "dashboard" || $("#wk-card")) return;
    const max = Math.max(1, ...r.weeks.map(w => w.shipped));
    const bars = r.weeks.map(w => `<div class="wk" title="${esc(w.titles.join(" · ") || "nothing shipped")}"><div class="wkbar"><i style="height:${(w.shipped / max) * 100}%"></i></div><b>${w.shipped}</b><span>${esc(w.label)}</span></div>`).join("");
    const cur = r.weeks[r.weeks.length - 1];
    $(".kpis").insertAdjacentHTML("afterend", `<div class="card" id="wk-card" style="margin-top:12px"><div class="row" style="justify-content:space-between"><h3 style="margin:0">Output, last 6 weeks</h3><span class="muted tiny">${r.total_shipped} shipped · streak ${r.streak} week${r.streak === 1 ? "" : "s"}${r.speed ? ` · builds run at ${r.speed}× footage length` : ""}</span></div>
      <div class="wks">${bars}</div><div class="muted tiny">This week: ${cur.builds} builds · ${cur.footage_min} min of footage edited · ${cur.build_min} min of build time</div></div>`);
  } catch (e) { }
}

// ---------------------------------------------------------------- 6 + 7. Build tab: edit stats + disk cleanup
async function enhanceBuild(p) {
  const body = $("#tabbody"); if (!body) return;
  body.insertAdjacentHTML("beforeend", `<div class="grid g2" style="margin-top:14px"><div class="card" id="st-card"><div class="muted small">loading edit stats…</div></div><div class="card" id="cl-card"><div class="muted small">measuring disk use…</div></div></div>`);
  try {
    const r = await api("project/stats?id=" + p.id); const s = r.stats;
    $("#st-card").innerHTML = !s ? `<h2>Edit stats</h2><div class="empty small">build once to see them</div>` : `<h2>Edit stats</h2>
      <div class="statgrid"><div><b>${fmtT(s.raw)}</b><span>raw recording</span></div><div><b>${fmtT(s.kept)}</b><span>in the edit</span></div><div><b>${s.cut_pct}%</b><span>cut</span></div>
      <div><b>${s.pieces}</b><span>pieces · avg ${s.avg_piece}s</span></div><div><b>${s.wpm}</b><span>words / min</span></div><div><b>${s.kept_words}</b><span>words kept</span></div></div>
      <div class="row" style="gap:6px;margin-top:8px;flex-wrap:wrap">${Object.entries(s.reasons).sort((a, b) => b[1] - a[1]).map(([k, n]) => `<span class="pill">${esc(k)} ${n}</span>`).join("")}</div>`;
  } catch (e) { $("#st-card").innerHTML = `<div class="empty small">${esc(e.message)}</div>`; }
  try {
    const c = await api("project/cleanup?id=" + p.id, {});
    $("#cl-card").innerHTML = `<h2>Disk space</h2><p class="muted small" style="margin:0 0 8px">Intermediate files the pipeline can regenerate (pieces, old draft cuts, stale QC sheets). Your recording, drafts, finals and Shorts are never touched. Files go to the Recycle Bin.</p>
      ${c.files ? `<div class="list">${c.groups.slice(0, 6).map(g => `<div class="item"><span class="t">${esc(g.folder)}</span><span class="muted tiny">${g.files} files · ${fmtSize(g.bytes)}</span></div>`).join("")}</div>
      <div class="row" style="margin-top:8px"><button class="warn sm" id="cl-run">🧹 Free ${fmtSize(c.bytes)}</button><span class="muted tiny">the next build regenerates what it needs (slower once)</span></div>` : `<div class="empty small">nothing to clean</div>`}`;
    $("#cl-run") && ($("#cl-run").onclick = e => withBusy(e.target, "cleaning…", async () => { if (!confirm(`Move ${c.files} regenerable files (${fmtSize(c.bytes)}) to the Recycle Bin?`)) return; const r2 = await api("project/cleanup?id=" + p.id, { run: true }); toast(`Freed ${fmtSize(r2.bytes)} (${r2.moved} files in the Recycle Bin)`, "ok"); renderProject(); }));
  } catch (e) { $("#cl-card").innerHTML = `<div class="empty small">${esc(e.message)}</div>`; }
}

// ---------------------------------------------------------------- 8. music preview
let PREVIEW = null;
function playPreview(path, btn) {
  if (PREVIEW && PREVIEW.dataset.path === path && !PREVIEW.paused) { PREVIEW.pause(); btn.textContent = "▶"; return; }
  if (PREVIEW) { PREVIEW.pause(); $$("[data-play]").forEach(b => b.textContent = "▶"); }
  PREVIEW = new Audio(mediaUrl(path)); PREVIEW.dataset.path = path; PREVIEW.volume = 0.6;
  PREVIEW.addEventListener("loadedmetadata", () => { PREVIEW.currentTime = Math.min(30, PREVIEW.duration * 0.25); PREVIEW.play().catch(() => {}); });
  PREVIEW.onended = () => btn.textContent = "▶";
  btn.textContent = "⏸";
}
const _closeModal = closeModal;
closeModal = function () { if (PREVIEW) { PREVIEW.pause(); PREVIEW = null; } _closeModal(); };

// ---------------------------------------------------------------- BIG: Shorts Factory
async function renderFactory(p) {
  const body = $("#tabbody"); body.innerHTML = `<div class="muted">loading…</div>`;
  let st;
  try { st = await api("project/factory?id=" + p.id); } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  const titles = st.titles || {};
  const pick = new Set(Object.entries(titles).filter(([n, t]) => t.score >= 7).map(([n]) => n));
  const side0 = { gaming: "center", phone: "left", review: "center", haul: "center", short: "center" }[p.type];
  body.innerHTML = `<div class="factory">
    <div class="row" style="margin-bottom:10px"><h2 style="margin:0">Shorts Factory</h2><span class="muted small grow">finds the strongest 18–58 s moments in the ${esc(st.kind || "render")}, you tick the ones you want, it renders them 9:16</span>
      ${p.type === "review" ? `<button class="sm" id="sf-review" ${st.has_render ? "" : "disabled"} title="3 styled product-review Shorts from the final: hook first, punch-ins every ~1.6 s, green product title + pill, caps captions, LINK IN BIO (tools/review_shorts.py)">📦 Review Shorts</button>` : ""}
      ${p.type === "gaming" ? `<button class="sm" id="sf-pack" title="the polished gaming package: one Short per ranked section with entry card, series badge, keyword pops and end card">🎮 Gaming package</button>` : ""}
      <button class="sm" id="sf-scan" ${st.has_render ? "" : "disabled"}>${st.moments.length ? "↻ Rescan" : "🔍 Find moments"}</button>
      <button class="sm" id="sf-titles" ${st.moments.length ? "" : "disabled"} title="Opus 5.5 titles and scores every moment">✍ Title + score with Opus</button></div>
    ${!st.has_render ? `<div class="empty">Build a draft (or final) first. The factory cuts Shorts from the finished edit.</div>` : !st.moments.length ? `<div class="empty">Press <b>Find moments</b>. It takes a few seconds.</div>` : `
    <div class="sf-list">${st.moments.map(mo => { const t = titles[String(mo.n)]; return `<div class="sf ${pick.has(String(mo.n)) ? "on" : ""}" data-n="${mo.n}">
      <div class="sf-prev" style="background-image:url('${thumbUrl(st.render, null, (mo.t0 + mo.t1) / 2, 360)}')"><span class="order">${mo.n}</span><span class="dur">${Math.round(mo.dur)}s</span><button class="sm sf-play" data-t0="${mo.t0}" data-t1="${mo.t1}">▶ preview</button></div>
      <div class="sf-info"><div class="row" style="gap:6px"><label class="sf-chk"><input type="checkbox" ${pick.has(String(mo.n)) ? "checked" : ""}> <b>${esc(t ? t.title : mo.hook)}</b></label>${t ? `<span class="pill ${t.score >= 7 ? "st-final" : ""}">Opus ${t.score}/10</span>` : ""}</div>
        <div class="muted tiny">${fmtT2(mo.t0)}–${fmtT2(mo.t1)} · score ${mo.score}${mo.reasons.length ? " · " + esc(mo.reasons.join(", ")) : ""}</div>
        <div class="sf-text">${esc(mo.text)}</div></div></div>`; }).join("")}</div>
    <div class="row sf-bar"><span class="muted small" id="sf-count"></span><span class="grow"></span><label class="small muted">crop <select id="sf-side"><option value="center" ${side0 === "center" ? "selected" : ""}>center</option><option value="left" ${side0 === "left" ? "selected" : ""}>left third</option><option value="right">right third</option></select></label>
      <button class="primary" id="sf-render">Render selected Shorts</button></div>`}
    <video id="sf-video" style="display:none;max-height:420px;margin-top:10px" controls></video>
    ${(st.shorts || []).length ? `<h3 style="margin:16px 0 6px">Made <span class="dim">${st.shorts.length}</span></h3><div class="sf-made">${st.shorts.map(x => `<div class="sf-m" data-openf="${esc(x.file)}"><div class="sf-mv" style="background-image:url('${thumbUrl(x.file, null, Math.min(3, x.duration / 2), 240)}')"></div><b>${esc(x.name)}</b><span class="muted tiny">${fmtT(x.duration)} · ${fmtSize(x.size)}</span></div>`).join("")}</div>` : ""}
  </div>`;
  const count = () => { const n = $$(".sf.on").length; const c = $("#sf-count"); if (c) c.textContent = n ? `${n} selected` : "tick the moments to render"; };
  count();
  $$(".sf").forEach(el => { const cb = $("input", el); cb.onchange = () => { el.classList.toggle("on", cb.checked); count(); }; });
  $$("[data-openf]", body).forEach(el => el.onclick = () => api("open", { path: el.dataset.openf }));
  const vid = $("#sf-video");
  $$(".sf-play").forEach(b => b.onclick = () => { vid.style.display = "block"; if (!vid.src.includes(enc(st.render))) vid.src = mediaUrl(st.render); const t0 = +b.dataset.t0, t1 = +b.dataset.t1; const go = () => { vid.currentTime = t0; vid.play().catch(() => {}); }; vid.readyState >= 1 ? go() : vid.addEventListener("loadedmetadata", go, { once: true }); vid.ontimeupdate = () => { if (vid.currentTime >= t1) vid.pause(); }; vid.scrollIntoView({ behavior: "smooth", block: "center" }); });
  const runJob = async (body_, msg) => { try { await api("project/factory?id=" + p.id, body_); toast(msg, "ok"); pollFactory(p); } catch (e) { toast(e.message, "bad"); } };
  $("#sf-scan") && ($("#sf-scan").onclick = () => runJob({ action: "scan", n: 8 }, "Finding moments…"));
  $("#sf-review") && ($("#sf-review").onclick = async () => { try { await api("project/run?id=" + p.id, { action: "shorts" }); toast("Review Shorts: building (about 2 min)", "ok"); pollFactory(p); } catch (e) { toast(e.message, "bad"); } });
  $("#sf-pack") && ($("#sf-pack").onclick = () => { if (confirm("Render the gaming package (one Short per ranked section, with entry card, badge, pops and end card)? Existing files of the same name are replaced.")) runJob({ action: "package" }, "Rendering the gaming package…"); });
  $("#sf-titles") && ($("#sf-titles").onclick = e => withBusy(e.target, "Opus is reading…", async () => { await api("project/factory?id=" + p.id, { action: "titles" }); renderFactory(p); }));
  $("#sf-render") && ($("#sf-render").onclick = () => { const picks = $$(".sf.on").map(el => +el.dataset.n); if (!picks.length) return toast("Tick at least one moment", "bad"); runJob({ action: "render", picks, side: $("#sf-side").value }, `Rendering ${picks.length} Shorts…`); });
}
function pollFactory(p) {
  const t = setInterval(async () => {
    const st = await api("jobs"); const run = st.jobs.find(j => j.project_id === p.id && (j.status === "running" || j.status === "queued"));
    S.state.jobs = st.jobs; renderSideJobs();
    if (!run) { clearInterval(t); const last = st.jobs.find(j => j.project_id === p.id); if (last && last.status === "failed") toast("Failed: " + last.error, "bad"); else toast("Shorts Factory: done", "ok"); if (S.view === "project" && S.pid === p.id && S.tab[p.id] === "shorts") renderFactory(p); }
  }, 2000);
}

// ---------------------------------------------------------------- Revise draft (phone): notes -> cuts -> rebuilt draft, draft history, seams
async function phoneRevisions(p) {
  const host = $("#tabbody"); if (!host || p.type !== "phone" || $("#rv-card")) return;
  host.insertAdjacentHTML("afterbegin", `<div class="card" id="rv-card" style="margin-bottom:14px"><div class="muted small">loading drafts…</div></div>`);
  let r;
  try { r = await api("project/revisions?id=" + p.id); } catch (e) { $("#rv-card").innerHTML = `<div class="empty small">${esc(e.message)}</div>`; return; }
  const revs = (r.revisions || []).slice().reverse();
  const running = (p.jobs || []).length > 0;
  $("#rv-card").innerHTML = `<div class="row" style="justify-content:space-between"><h2 style="margin:0">Revise draft</h2><span class="muted tiny">Opus turns your notes into exact cuts on audio quiet, then the draft rebuilds (the old one is kept as DRAFT vN)</span></div>
    <textarea id="rv-notes" style="min-height:110px;margin-top:8px;font-family:inherit;font-size:13px" placeholder="Write notes the way you talk, with DRAFT times:
2:20 remove 'to'
cut at 3:02, pick back up at 3:24 where I say another way to save money
8:29 weird clip, should move on">${esc(r.notes || "")}</textarea>
    <div class="row" style="margin-top:8px"><button class="primary" id="rv-go" ${running ? "disabled" : ""}>✂ Revise draft</button><span class="muted tiny">${running ? "a build is running; its steps are below" : "about a minute for the notes, then the rebuild · you get a notification after each step"}</span></div>
    <div id="rv-prog">${running ? reviseProgress(p.jobs[0]) : ""}</div>
    <div class="grid g2" style="margin-top:12px">
      <div><h3 style="margin:0 0 6px">Drafts</h3><div class="list">${r.drafts.slice().reverse().map(d => `<div class="item" data-play="${esc(d.file)}"><span class="pill ${d.current ? "st-final" : ""}">${d.current ? "current" : d.version ? "v" + d.version : "old"}</span><span class="t">${esc(d.name)}</span><span class="muted tiny">${fmtT(d.duration)} · ${esc(d.when)}</span></div>`).join("") || `<div class="empty small">no drafts yet</div>`}</div></div>
      <div><h3 style="margin:0 0 6px">Revision history</h3><div class="list">${revs.map(v => `<div class="rv"><div class="row"><b>Revision ${v.n}</b><span class="muted tiny">${esc(v.when || "")} · ${(v.cuts || []).length} cuts${v.cost ? " · $" + (+v.cost).toFixed(2) : ""}</span></div>
        <div class="tiny muted rv-notes">${esc(v.notes || "")}</div>${(v.other || []).length ? `<div class="tiny" style="color:var(--warn);margin-top:4px">Needs a hand fix: ${(v.other || []).map(o => esc(typeof o === "string" ? o : (o.note || o.instruction || JSON.stringify(o)))).join(" · ")}</div>` : ""}</div>`).join("") || `<div class="empty small">no revisions yet</div>`}</div></div></div>
    ${r.seams ? `<details style="margin-top:10px"><summary class="muted small">Every join in the draft (seams.md)</summary><div class="log" style="max-height:320px">${esc(r.seams)}</div></details>` : ""}`;
  $("#rv-go").onclick = async () => { const notes = $("#rv-notes").value.trim(); if (!notes) return toast("Write at least one note", "bad"); try { await api("project/revisions?id=" + p.id, { notes }); toast("Revision started: the steps update live below", "ok"); await loadProject(); pollJobs(p.id); } catch (e) { toast(e.message, "bad"); } };
  $$("#rv-card [data-play]").forEach(el => el.onclick = () => { ED.playing = el.dataset.play; S.tab[p.id] = "editor"; renderProject(); });
}

// live step list for a running revision / build, shown inside the Revise draft card
function reviseProgress(j) {
  if (!j) return "";
  const pr = j.progress || { pct: 0, step: "", elapsed_s: 0, eta_s: 0 };
  const icon = st => st === "done" || st === "skipped" ? "✓" : st === "running" ? "●" : st === "failed" ? "✕" : "○";
  return `<div class="rv-steps"><div class="row" style="margin-bottom:6px"><b class="small">${esc({ revise: "Revision in progress", intro: "Intro-only rebuild in progress (main edit kept)" }[j.title.split(": ").pop()] || "Build in progress")}</b><span class="muted tiny">${Math.round(pr.pct)}% · ${fmtEta(pr.elapsed_s)} elapsed${pr.eta_s ? " · ~" + fmtEta(pr.eta_s) + " left" : ""}${typeof stuckNote === "function" ? stuckNote(pr) : ""}</span></div>
    <div class="prog-bar" style="margin:0 0 8px"><i style="width:${pr.pct}%"></i></div>
    ${(j.steps || []).map((s, i) => `<div class="rvs ${s.status}"><span class="ic">${icon(s.status)}</span><span>${i + 1}. ${esc(s.label)}</span>${s.status === "running" && pr.step && pr.step !== s.label ? `<span class="muted tiny">· ${esc(pr.step)}</span>` : ""}</div>`).join("")}</div>`;
}

// ---------------------------------------------------------------- 🎙 speech buttons on every text box (local Whisper, no Claude usage)
const MIC = { rec: null, chunks: [], btn: null, field: null };
async function micToggle(btn, field) {
  if (MIC.rec && MIC.rec.state === "recording") { MIC.rec.stop(); return; }
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); } catch (e) { return toast("Microphone blocked: allow it for {{STUDIO_NAME}} and try again", "bad"); }
  MIC.chunks = []; MIC.btn = btn; MIC.field = field;
  const rec = new MediaRecorder(stream, { mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "" });
  MIC.rec = rec;
  rec.ondataavailable = e => { if (e.data.size) MIC.chunks.push(e.data); };
  rec.onstop = async () => {
    stream.getTracks().forEach(t => t.stop());
    btn.classList.remove("rec"); btn.classList.add("busy"); btn.textContent = "…";
    try {
      const blob = new Blob(MIC.chunks, { type: "audio/webm" });
      const mode = field.dataset.mic === "note" ? "note" : "text";
      const r = await fetch("/api/transcribe?mode=" + mode, { method: "POST", body: blob }).then(x => x.json());
      if (r.error) throw new Error(r.error);
      if (r.text) {
        const v = field.value, sel = field.selectionStart ?? v.length;
        const pad = v && sel > 0 && !/\s$/.test(v.slice(0, sel)) ? " " : "";
        field.value = v.slice(0, sel) + pad + r.text + v.slice(field.selectionEnd ?? sel);
        field.dispatchEvent(new Event("input", { bubbles: true })); field.dispatchEvent(new Event("change", { bubbles: true }));
        field.focus();
      } else toast("Didn't catch that, try again a little closer to the mic", "bad");
    } catch (e) { toast(e.message, "bad"); }
    btn.classList.remove("busy"); btn.textContent = "🎙";
  };
  rec.start(); btn.classList.add("rec"); btn.textContent = "■";
}
const MIC_SEL = "[data-mic]";   // only the notes box (user: not on every text box)
function attachMics(root) {
  $$(MIC_SEL, root || document).forEach(f => {
    if (f.dataset.micDone || f.type === "date" || f.readOnly) return;
    f.dataset.micDone = "1";
    const b = document.createElement("button");
    b.type = "button"; b.className = "mic" + (f.tagName === "TEXTAREA" ? " mic-ta" : ""); b.textContent = "🎙"; b.title = "talk instead of typing (click, speak, click again)";
    b.onclick = e => { e.preventDefault(); e.stopPropagation(); micToggle(b, f); };
    if (f.tagName === "TEXTAREA") { const w = document.createElement("div"); w.className = "mic-wrap"; f.parentNode.insertBefore(w, f); w.appendChild(f); w.appendChild(b); }
    else f.insertAdjacentElement("afterend", b);
  });
}
new MutationObserver(() => attachMics()).observe(document.body, { childList: true, subtree: true });
attachMics();

// ---------------------------------------------------------------- 🎙 Talk a note here: time-stamped voice notes for Claude
function wireTalkNote(p) {
  const b = $("#p-talk"), endB = $("#p-talk-end"), st = $("#p-talk-status"), v = $("#p-video"), field = $("#p-note");
  if (!b || !field) return;
  const T = { t0: null, t1: null, rec: null, chunks: [] };
  const stamp = () => v ? v.currentTime : 0;
  b.onclick = async () => {
    if (T.rec && T.rec.state === "recording") { if (T.t1 == null) T.t1 = stamp(); T.rec.stop(); return; }
    if (!v) return toast("Pick a draft to watch first", "bad");
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); } catch (e) { return toast("Microphone blocked: allow it for {{STUDIO_NAME}} and try again", "bad"); }
    T.t0 = stamp(); T.t1 = null; T.chunks = [];
    if (v.paused) v.play().catch(() => {});
    const rec = new MediaRecorder(stream); T.rec = rec;
    rec.ondataavailable = e => { if (e.data.size) T.chunks.push(e.data); };
    rec.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      b.classList.remove("rec"); b.textContent = "…"; endB.style.display = "none";
      st.textContent = "turning your words into text…";
      try {
        const r = await fetch("/api/transcribe?mode=note", { method: "POST", body: new Blob(T.chunks, { type: "audio/webm" }) }).then(x => x.json());
        const said = (r.text || "").trim();
        if (!said) { toast("Didn't catch that, try again", "bad"); }
        else {
          const a = T.t0, z = Math.max(T.t1 ?? a + 3, a + 1);
          // only a short spoken command ("cut 1:20-1:30") goes in as-is; anything longer is a note stamped with where he was
          const exact = /^(cut|protect|keep)\b/i.test(said) && /\d+:\d{2}/.test(said) && said.split(/\s+/).length <= 8;
          const line = exact ? said : `note ${fmtT2(a)}-${fmtT2(z)}: ${said}`;
          field.value = (field.value.trim() ? field.value.trim() + "\n" : "") + line;
          field.dispatchEvent(new Event("input", { bubbles: true })); field.focus();
          st.innerHTML = `added to the box: <b>${fmtT2(a)} → ${fmtT2(z)}</b> · read it over, then Enter (or ✕ to clear)`;
        }
      } catch (e) { toast(e.message, "bad"); }
      b.textContent = "🎙 Talk a note here";
    };
    rec.start();
    b.classList.add("rec"); b.textContent = "■ Stop"; endB.style.display = "";
    st.innerHTML = `recording from <b>${fmtT2(T.t0)}</b>… say what's wrong; press ⇥ End here when it ends`;
  };
  endB.onclick = () => { T.t1 = stamp(); st.innerHTML = `range <b>${fmtT2(T.t0)} → ${fmtT2(T.t1)}</b> · keep talking or press ■ Stop`; };
}

// ---------------------------------------------------------------- ✂ Watch cuts: every join of the draft, one by one
// (user 2026-10-23: "I want to just watch the transitions one by one ... 5 seconds before where you cut it, then jump to the
// next one ... most of the information in these videos is correct, it's really down to the cut"). The joins come from the
// draft's own timeline (kept ranges as rendered + the intro in front), the words around each from the transcript. Each cut
// can be rated clean / bad: the ratings are kept in settings.cut_ratings as data for the cut rules.
function wireCutWatch(p) {
  const v = $("#p-video"), row = $("#p-mark") && $("#p-mark").parentNode;
  if (!v || !row || !(p.timeline && (p.timeline.keep || []).length)) return;
  const keep = p.timeline.keep, off = +p.timeline.offset || 0;
  const cuts = [];
  if (off > 0.5) cuts.push({ t: off, kind: "intro", label: "intro → video" });
  let acc = off;
  keep.forEach(([a, b], i) => {
    if (i > 0) {
      const [pa, pb] = keep[i - 1];
      const ins = pa < 0 || a < 0;
      if (ins || a - pb > 0.03) cuts.push({ t: acc, kind: ins ? "cutaway" : "cut", prev: pb, next: a, removed: ins ? 0 : a - pb });
    }
    acc += Math.abs(b - a);
  });
  if (!cuts.length) return;
  const W = { words: null, i: -1, stopAt: null, lead: 5 };
  const outs = p.outputs || [], latest = outs[outs.length - 1];
  const btn = document.createElement("button");
  btn.className = "sm"; btn.id = "p-cutwatch"; btn.textContent = `✂ Watch cuts (${cuts.length})`;
  btn.title = "jump from cut to cut: plays a few seconds before each join and stops just after it";
  row.appendChild(btn);
  const box = document.createElement("div");
  box.id = "cw-box"; box.className = "cw-box"; box.style.display = "none";
  row.parentNode.insertBefore(box, row.nextSibling);
  const rated = () => (p.settings && p.settings.cut_ratings) || [];
  const ctx = c => {
    if (!W.words || c.kind !== "cut") return "";
    const before = W.words.filter(w => w.e <= c.prev + 0.05).slice(-7).map(w => w.w).join(" ");
    const gone = W.words.filter(w => (w.s + w.e) / 2 > c.prev && (w.s + w.e) / 2 < c.next).map(w => w.w);
    const after = W.words.filter(w => w.s >= c.next - 0.05).slice(0, 7).map(w => w.w).join(" ");
    return `<div class="tiny cw-words">…${esc(before)} <b class="cw-cut">✂${gone.length ? ` ${esc(gone.slice(0, 18).join(" "))}${gone.length > 18 ? " …" : ""}` : ""} ✂</b> ${esc(after)}…</div>`;
  };
  const draw = () => {
    const c = cuts[W.i], r = rated().find(x => Math.abs(x.t - c.t) < 0.05);
    box.innerHTML = `<div class="row" style="gap:6px;flex-wrap:wrap">
        <b class="small">Cut ${W.i + 1}/${cuts.length} · ${fmtT2(c.t)}</b>
        <span class="muted tiny">${c.kind === "intro" ? "intro → video" : c.kind === "cutaway" ? "cutaway clip" : `${c.removed.toFixed(1)} s removed (recording ${fmtT2(c.prev)} → ${fmtT2(c.next)})`}${r ? ` · rated ${r.verdict === "good" ? "👍 clean" : "👎 bad"}` : ""}</span>
        <span class="grow"></span>
        <select id="cw-lead" class="sm" title="seconds before the cut">${[3, 5, 8].map(s => `<option ${s === W.lead ? "selected" : ""} value="${s}">${s} s before</option>`).join("")}</select>
        <button class="sm" id="cw-prev" title="previous cut (P)">◀</button><button class="sm" id="cw-again" title="replay (R)">↻</button><button class="sm primary" id="cw-next" title="next cut (N)">Next ▶</button>
        <button class="sm ok" id="cw-good" title="this cut is clean (G)">👍</button><button class="sm danger" id="cw-bad" title="bad cut: rate it and write a note (B)">👎</button><button class="sm" id="cw-close">✕</button></div>${ctx(c)}`;
    $("#cw-prev").onclick = () => go(W.i - 1); $("#cw-next").onclick = () => go(W.i + 1); $("#cw-again").onclick = () => go(W.i);
    $("#cw-good").onclick = () => rate("good"); $("#cw-bad").onclick = () => rate("bad");
    $("#cw-close").onclick = () => { box.style.display = "none"; W.stopAt = null; };
    $("#cw-lead").onchange = e => { W.lead = +e.target.value; go(W.i); };
  };
  const go = i => {
    if (i < 0 || i >= cuts.length) return toast(i < 0 ? "That's the first cut" : "That was the last cut", "ok");
    W.i = i; draw();
    const c = cuts[i];
    v.currentTime = Math.max(0, c.t - W.lead);
    W.stopAt = c.t + 2.5;
    v.play().catch(() => {});
  };
  const rate = async verdict => {
    const c = cuts[W.i];
    const list = rated().filter(x => Math.abs(x.t - c.t) >= 0.05).concat([{ t: +c.t.toFixed(2), kind: c.kind, prev: c.prev ?? null, next: c.next ?? null,
      removed: c.removed ? +c.removed.toFixed(2) : 0, verdict, when: new Date().toISOString().slice(0, 16).replace("T", " ") }]);
    try {
      await api("project/update?id=" + p.id, { settings: { cut_ratings: list } });
      p.settings = Object.assign(p.settings || {}, { cut_ratings: list });
    } catch (e) { return toast(e.message, "bad"); }
    if (verdict === "bad") {   // straight into a note for that moment: type or 🎙 talk what's wrong, Enter adds it
      const f = $("#p-note");
      f.value = (f.value.trim() ? f.value.trim() + "\n" : "") + `note ${fmtT2(Math.max(0, c.t - 1))}-${fmtT2(c.t + 1)}: bad cut — `;
      f.dispatchEvent(new Event("input", { bubbles: true })); f.focus();
      toast("Rated 👎 · say or type what's wrong with this cut, Enter adds the note", "ok");
      draw();
    } else { toast("Rated 👍", "ok"); go(W.i + 1); }
  };
  v.addEventListener("timeupdate", () => { if (W.stopAt != null && v.currentTime >= W.stopAt) { v.pause(); W.stopAt = null; } });
  btn.onclick = async () => {
    const sel = $("#p-out");
    if (sel && latest && sel.value && sel.value !== latest.file) toast("The cut times are for the newest draft: switch the player to it", "bad");
    box.style.display = "";
    if (!W.words) { try { W.words = (await api("editor?id=" + p.id)).words || []; } catch (e) { W.words = []; } }
    go(W.i < 0 ? 0 : W.i);
  };
  document.addEventListener("keydown", e => {
    if (box.style.display === "none" || !document.body.contains(box) || /input|textarea|select/i.test(document.activeElement.tagName)) return;
    const k = e.key.toLowerCase();
    if (k === "n") go(W.i + 1); else if (k === "p") go(W.i - 1); else if (k === "r") go(W.i);
    else if (k === "g") rate("good"); else if (k === "b") rate("bad"); else return;
    e.preventDefault();
  });
}

// ---------------------------------------------------------------- right-click a project: rename, settings, open folder, forget
function projectMenu(e, pid) {
  e.preventDefault(); e.stopPropagation();
  closeCtx();
  const p = (S.state.projects || []).find(x => x.id === pid); if (!p) return;
  const m = document.createElement("div"); m.className = "ctx"; m.id = "ctx";
  m.innerHTML = `<div class="ctx-h">${esc(p.title)}</div>
    <a data-a="open">Open</a><a data-a="rename">Rename…</a><a data-a="settings">Project settings…</a>
    <hr><a data-a="testdone" title="approved + final ticked, never sent to Drive or TickTick; Claude saves it to memory as a reference edit">✓ Done: test video, study it</a>
    <hr><a data-a="build">▶ Build draft</a><a data-a="folder">Open folder</a><a data-a="copy">Copy folder path</a>
    <hr><a data-a="forget" class="bad">Remove from the app (files stay)</a>`;
  document.body.appendChild(m);
  const W = m.offsetWidth, H = m.offsetHeight;
  m.style.left = Math.min(e.clientX, innerWidth - W - 8) + "px"; m.style.top = Math.min(e.clientY, innerHeight - H - 8) + "px";
  $$("a", m).forEach(a => a.onclick = async () => {
    closeCtx();
    const act = a.dataset.a;
    try {
      if (act === "open") openProject(pid);
      else if (act === "testdone") {
        if (!confirm(`Mark “${p.title}” done as a TEST video?\n\nApproved + final get ticked, it leaves Ready for your review, and Claude saves it to memory as a reference edit to study. Nothing goes to Drive or TickTick.`)) return;
        const r = await api("project/test-done?id=" + pid, {});
        toast(r.studying ? "Done ✓ Claude is saving it to memory (you'll get a notification)" : "Done ✓ (Claude is busy on this project: send “study this approved video” from Ask Claude later)", "ok");
        await refresh(true); render();
      }
      else if (act === "rename") renameModal(p);
      else if (act === "settings") settingsModal(pid);
      else if (act === "build") { await api("project/run?id=" + pid, { action: "draft" }); toast("Draft build started", "ok"); refresh(); }
      else if (act === "folder") await api("open", { path: p.path });
      else if (act === "copy") { await api("clipboard", { text: p.path }); toast("Folder path copied", "ok"); }
      else if (act === "forget") { if (confirm(`Remove “${p.title}” from {{STUDIO_NAME}}? The folder and files stay on disk; you can open it again with Open existing folder.`)) { await api("project/delete?id=" + pid, {}); await refresh(true); nav(S.view === "project" ? "projects" : S.view); } }
    } catch (err) { toast(err.message, "bad"); }
  });
}
function closeCtx() { const c = $("#ctx"); if (c) c.remove(); }
document.addEventListener("click", closeCtx);
document.addEventListener("keydown", e => { if (e.key === "Escape") closeCtx(); });
document.addEventListener("contextmenu", e => {
  const el = e.target.closest("[data-open], .pcard, .bc, .th-row, .item[data-id]");
  const pid = el && (el.dataset.open || el.dataset.id);
  if (pid && (S.state.projects || []).some(x => x.id === pid)) projectMenu(e, pid);
});
function renameModal(p) {
  const m = modal(`<h2>Rename project</h2><div class="field"><label>Name</label><input id="rn-t" value="${esc(p.title)}"></div>
    <label class="small"><input type="checkbox" id="rn-f" checked> also rename the folder and the files named after it, so it's the same everywhere (Explorer, Claude, Drive hand-off)</label>
    <p class="muted tiny">${esc(p.path)}</p><div class="row" style="justify-content:flex-end"><button id="rn-c">Cancel</button><button class="primary" id="rn-ok">Rename</button></div>`);
  const go = async () => { try { const r = await api("project/rename?id=" + p.id, { title: $("#rn-t", m).value, folder: $("#rn-f", m).checked }); closeModal(); toast(`Renamed to “${r.title}”${r.renamed.length ? ` (${r.renamed.length} folder/file renames)` : ""}`, "ok"); await refresh(true); if (S.view === "project") loadProject(); else render(); } catch (e) { toast(e.message, "bad"); } };
  $("#rn-ok", m).onclick = go; $("#rn-t", m).onkeydown = e => { if (e.key === "Enter") go(); }; $("#rn-c", m).onclick = closeModal;
  const i = $("#rn-t", m); i.focus(); i.select();
}
async function settingsModal(pid) {
  const p = await api("project?id=" + pid);
  const st = p.settings || {};
  const g = p.type === "gaming";
  const m = modal(`<h2>Project settings</h2>
    <div class="grid g2">
      <div class="field"><label>Name</label><input id="ps-title" value="${esc(p.title)}"></div>
      <div class="field"><label>Channel</label><select id="ps-ch"><option value="">—</option>${S.state.settings.channels.map(c => `<option ${c.name === p.channel ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></div>
      <div class="field"><label>Due date</label><input id="ps-due" type="date" value="${esc(p.due || "")}"></div>
      <div class="field"><label>Stage</label><select id="ps-stage"><option value="">auto (${esc(S.state.stage_labels[p.stage])})</option>${S.state.stages.map(s => `<option value="${s}" ${p.stage_manual === s ? "selected" : ""}>${esc(S.state.stage_labels[s])}</option>`).join("")}</select></div>
      <div class="field"><label>YouTube title</label><input id="ps-yt" value="${esc(p.yt_title || "")}" placeholder="what it goes up as"></div>
      <div class="field"><label>YouTube link (once it's up)</label><input id="ps-link" value="${esc(p.links.youtube || "")}"></div>
    </div>
    ${g ? `<h3 style="margin:8px 0 6px">Gaming edit</h3><div class="grid g2">
      <div class="field"><label>Game audio volume under your voice (0–1)</label><input id="ps-gv" type="number" step="0.05" min="0" max="1" value="${st.game_volume ?? 0.3}"></div>
      <div class="field"><label>Music bed loudness (LUFS, lower = quieter)</label><input id="ps-bed" type="number" step="1" value="${st.music_bed_lufs ?? -36}"></div>
      <div class="field"><label>Inventory / menu zooms</label><select id="ps-zoom"><option value="1" ${st.ui_zooms !== false ? "selected" : ""}>on</option><option value="0" ${st.ui_zooms === false ? "selected" : ""}>off</option></select></div>
      <div class="field"><label>Windowed sections (taskbar visible), comma separated</label><input id="ps-win" value="${esc((st.windowed_sections || []).join(", "))}" placeholder="#1 Rennmon"></div>
    </div>` : ""}
    <h3 style="margin:8px 0 6px">Edit options</h3>${modeOptsHtml(st, p.type)}
    <p class="muted tiny">${esc(p.path)}</p>
    <div class="row" style="justify-content:flex-end"><button id="ps-c">Cancel</button><button class="primary" id="ps-ok">Save</button></div>`, "wide");
  wireModeOpts(m, () => p.type);
  $("#ps-c", m).onclick = closeModal;
  $("#ps-ok", m).onclick = async () => {
    try {
      const t = $("#ps-title", m).value.trim();
      if (t && t !== p.title) await api("project/rename?id=" + pid, { title: t, folder: true });
      const settings = { ...readModeOpts(m), ...(g ? { game_volume: +$("#ps-gv", m).value, music_bed_lufs: +$("#ps-bed", m).value, ui_zooms: $("#ps-zoom", m).value === "1",
        windowed_sections: $("#ps-win", m).value.split(",").map(x => x.trim()).filter(Boolean) } : {}) };
      const yt = $("#ps-link", m).value.trim();
      await api("project/update?id=" + pid, { channel: $("#ps-ch", m).value, due: $("#ps-due", m).value, stage_manual: $("#ps-stage", m).value, yt_title: $("#ps-yt", m).value.trim(),
        links: { youtube: yt }, ...(yt ? { checklist: { published: true } } : {}), settings });
      closeModal(); toast("Settings saved (rebuild to apply the edit settings)", "ok"); await refresh(true); if (S.view === "project" && S.pid === pid) loadProject(); else render();
    } catch (e) { toast(e.message, "bad"); }
  };
}

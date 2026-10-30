/* {{STUDIO_NAME}} UI, part 10 (2026-10-29): the project editor rebuilt to the approved picture (mockup artboard Editor2,
   https://claude.ai/artifact/Do4SiBF1FhnM9C5AsZPsdR; the user is visually impaired: big text, big targets, nothing raw).
   - It shows THE EDITED VIDEO: the player plays the newest draft and every time on screen is draft time. The raw recording and
     its cut-to-cut gaps never show; draft <-> recording times are mapped through the cut list (tlDraftOf / tlRawOf, app9).
   - Left: tabs Words / Clips / Music / Text / Captions / Transitions. Words = the draft's transcript as paragraphs (cut words
     hidden unless "Show cut words"); select words -> Cut / Bring back (app4's TX cutter: cut / protect notes).
   - Filmora proportions (user's screenshot 2026-10-29): tabs left / player middle / Changes panel right (change box, mic,
     Add change, the list), over a full-width timeline that takes ~40% of the height.
   - Timeline: Video (Intro + Your video, continuous) / B-roll / Music (song names where they play) / Captions; zoom with
     Ctrl + scroll, Ctrl + / Ctrl − / Ctrl 0, or the − + Fit buttons (the plain wheel scrolls sideways once zoomed in).
   - Every manual edit (B-roll moved / trimmed / deleted, song swapped, captions changed, words cut) is a change in the list,
     applied by the next draft through the existing notes grammar. "Make Draft N+1 · K changes" sends them all.
   Loaded after app9.js (uses its helpers: tlDraftOf, tlRawOf, tlKeep, tlMusicParts, tlMusicLib, tlPreview, tlUseTrack,
   tlMoreMenu, tlDetails, TL); replaces renderEditor. */

const E2 = { tab: "revise", showCuts: false, splits: [], sel: null, drag: null, editIdx: null, zoom: 1 };
const E2_WATCH_ICON = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5h18v14H3zM10 9v6l5-3z"/></svg>`;

// ---------------------------------------------------------------- draft-time helpers
function e2Dur() { const d = ED.data; return (d.offset || 0) + (d.keep || []).reduce((a, [x, y]) => a + Math.abs(y - x), 0) || d.duration || 0; }
const e2Pct = t => `${Math.max(0, Math.min(100, (t / (e2Dur() || 1)) * 100))}%`;
function e2Pending() { return (S.project.notes || []).map((n, idx) => ({ n, idx })).filter(x => !x.n.done && !x.n.batch && !x.n.off); }
function e2NoteDraft(n) {   // where a note sits in the draft
  if (n.t0 != null) return [n.t0, n.t1 ?? n.t0 + 3];
  if (n.raw0 != null) return [tlDraftOf(n.raw0), tlDraftOf(n.raw1 ?? n.raw0 + 3)];
  return null;
}
function e2Plain(n) {   // a change in plain words
  const t = String(n.text || "");
  const words = (t.match(/[“"](.+?)[”"]/) || [, ""])[1];
  if (n.kind === "cut" && n.from === "editor") return words ? `Cut “${words}”` : "Cut a part";
  if (n.kind === "protect" && n.from === "editor") return words ? `Brought back “${words}”` : "Brought back a part";
  if (n.kind === "broll" && !/^broll\s/i.test(t)) return t;
  if (n.kind === "broll") return `B-roll${n.clip ? " " + n.clip : ""} over “${words || "this part"}”`;
  return t.replace(/^note\s+[\d:.]+\s*(?:-\s*[\d:.]+)?\s*:\s*/i, "").replace(/^\s*(cut|protect|keep)\s+[\d:.]+\s*-\s*[\d:.]+\s*/i, (m, k) => (k === "cut" ? "Cut " : "Keep "));
}
async function e2AddNote(body, msg) {
  S.project = await api("project/notes?id=" + S.project.id, body);
  ED.data.notes = S.project.notes;
  if (msg) toast(msg, "ok");
  e2Refresh();
}

// ---------------------------------------------------------------- render
renderEditor = async function (p) {
  const body = $("#tabbody"); body.innerHTML = `<div class="e2-loading">Loading your video…</div>`;
  try { ED.data = await api("editor?id=" + p.id); } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  const d = ED.data, outs = d.outputs || [];
  const drafts = outs.filter(o => o.kind !== "final"), finals = outs.filter(o => o.kind === "final");
  // always the edit: the newest draft (or the final when that is newer); never the raw recording
  const newest = outs.length ? outs[outs.length - 1] : null;
  ED.playing = newest ? newest.file : "";
  if (ED.pid !== p.id) { TX.undo = []; TX.redo = []; E2.splits = []; E2.sel = null; E2.zoom = 1; E2.tab = "revise"; }
  ED.pid = p.id;
  TX.E = txEditable(d.notes); TX.prot = txOtherProtects(d.notes); TX.sents = txSentences(d.words); TX.cur = -1;
  const N = drafts.length;
  E2.draftNo = N; E2.isFinal = !!newest && newest.kind === "final";
  const I = TL_ICON;
  // Words = read it (Gling), Watch = big video + changes side by side, the rest = timeline (Filmora). Text tab dropped
  // (user 2026-10-29: people want it done for them; on-screen text is just a typed change).
  // round 2 (user 2026-10-29): Revise first and where every project opens (video + your changes, like the old Revisions
  // screen he liked); Transitions tab gone (picked automatically; a custom one is a typed change)
  if (!["revise", "words", "clips", "music", "captions"].includes(E2.tab)) E2.tab = "revise";
  const tabs = [["revise", "Revise", E2_WATCH_ICON], ["words", "Words", I.words], ["clips", "Clips", I.clips], ["music", "Music", I.music], ["captions", "Captions", I.captions]];
  body.innerHTML = `<div class="e2">
    <header class="e2-top">
      <button class="e2-btn" id="e2-home">${I.back}Projects</button>
      <span class="e2-title" id="e2-title" tabindex="0" role="button" title="Click to rename">${esc(p.title)}</span>
      <span class="e2-badge ${E2.isFinal ? "final" : ""}">${E2.isFinal ? "Final video" : N ? `Draft ${N}` : "No draft yet"}</span>
      <span class="grow"></span>
      <button class="e2-btn" id="tx-undo" title="Undo (Ctrl+Z)">${I.undo}Undo</button>
      <button class="e2-btn primary" id="e2-make"></button>
      <button class="e2-btn final" id="e2-final" ${p.jobs.length || !N ? "disabled" : ""}>${I.check}Export final video</button>
      <button class="e2-btn" id="e2-more" title="Text size, Revisions, Build log, Shorts, Deliverables, Project details">${I.dots}More</button>
    </header>
    <div class="e2-mid">
      <aside class="e2-side">
        <div class="e2-tabs" role="tablist">${tabs.map(([k, l, ic]) => `<button role="tab" data-e2tab="${k}" class="${E2.tab === k ? "on" : ""}">${ic}${l}</button>`).join("")}</div>
        <div class="e2-pane" id="e2-pane"></div>
      </aside>
      <section class="e2-main" aria-label="Your video">
        <div class="e2-player">${ED.playing ? `<video id="ed-video" preload="metadata" src="${mediaUrl(ED.playing)}"></video>` : `<div class="e2-novideo">Your video appears here once the first draft is made.</div>`}</div>
        <div class="e2-seek" id="e2-seek" role="slider" aria-label="Move through the video" tabindex="0"><div class="e2-seekfill" id="e2-seekfill"></div><span class="e2-seektip" id="e2-seektip">0:00</span></div>
        <div class="e2-ctrl">
          <button class="e2-play" id="e2-play" aria-label="Play">▶</button>
          <span class="e2-time"><b id="e2-now">0:00</b> <span>/ ${fmtT(e2Dur())}</span></span>
        </div>
      </section>
      <aside class="e2-right" aria-label="Your changes">
        <h2>Changes <span id="e2-k"></span></h2>
        <input id="e2-chg" type="text" placeholder="Type a change…" aria-label="Describe a change">
        <div class="e2-chgbtns"><button class="e2-btn" id="e2-mic" title="Say the change instead of typing">${E2MIC_ICON}Speak</button>
          <button class="e2-btn accent" id="e2-add">${I.plus}Add change</button></div>
        <div class="e2-dlist" id="e2-dlist"></div>
      </aside>
    </div>
    <section class="e2-tl" aria-label="Timeline">
      <div class="e2-tlbar"><span class="e2-selinfo" id="e2-selinfo">How your video is edited. Click or drag to move through it. Right-click a song to change it.</span><span class="grow"></span>
        <button class="e2-btn sm e2-zb" id="e2-zout" title="Zoom out (Ctrl −, or Ctrl + scroll)" aria-label="Zoom out">−</button><span class="e2-zl">Zoom</span>
        <button class="e2-btn sm e2-zb" id="e2-zin" title="Zoom in (Ctrl +, or Ctrl + scroll)" aria-label="Zoom in">+</button>
        <button class="e2-btn sm" id="e2-zfit" title="Show the whole video (Ctrl 0)">Fit</button></div>
      <div class="e2-rows" id="e2-rows"></div>
    </section>
    <div class="tx-bubble e2-bubble" id="e2-bubble"><button class="e2-btn sm danger" id="e2-bcut">${I.cut}Cut</button><button class="e2-btn sm" id="e2-bback">${I.restore}Bring back</button></div>
  </div>`;
  e2Wire(p);
  e2Pane();
  e2Refresh();
  e2Progress(p);
  e2CapsLoad(p);
};

// ---------------------------------------------------------------- caption fixes (friend's request 2026-10-29: "pause the
// video, double-click the caption, retype it"). The draft's burned captions come from GET project/captions (groups
// {s, e, text} in draft time); a fix goes to POST project/caption-fix {old, new, t, all, video} and is burned by the next
// draft (app/tools/caption_fixes.py; the AI typo pass runs there too).
async function e2CapsLoad(p) {
  E2.caps = null;
  if (!ED.playing) return;
  try { const r = await api(`project/captions?id=${p.id}&video=${enc(base(ED.playing))}`); E2.caps = (r.groups || []).length ? r : null; } catch (e) { E2.caps = null; }
  // ...and whether this video starts with a review intro whose words can be changed the same way
  let intro = false;
  if (p.type === "review") { try { const r = await api(`project/intro-text?id=${p.id}&video=${enc(base(ED.playing))}`); intro = r.dur > 0 && r.in_video; } catch (e) { intro = false; } }
  const pl = $(".e2-player"); if (!pl || !(E2.caps || intro) || S.project.id !== p.id) return;
  if (!$("#e2-caphint")) { const h = document.createElement("div"); h.id = "e2-caphint"; h.className = "e2-caphint"; pl.appendChild(h); }
  $("#e2-caphint").textContent = E2.caps && intro ? "✎ Double-click a caption or the intro's words to change them" : intro ? "✎ Double-click the intro's words to change them" : "✎ Double-click a caption to fix a word";
  if (E2.tab === "captions") e2Pane();
}
// Captions tab: your fixes + the AI's, each with Undo
async function e2CapFixes(p) {
  let r; try { r = await api("project/caption-fix?id=" + p.id); } catch (e) { return; }
  const el = $("#e2-capfixes"); if (!el) return;
  const rej = new Set(r.ai_reject || []);
  const ai = ((E2.caps && E2.caps.changes) || []).filter(c => c.source === "ai");
  const rows = [...(r.fixes || []).map(f => ({ id: f.id, txt: `“${f.old}” → “${f.new}”`, who: f.all ? "you · everywhere" : `you · ${f.t != null ? fmtT(f.t) : ""}`, on: true })),
    ...ai.map(c => ({ id: c.id, txt: `“${c.old}” → “${c.new}”`, who: `AI · ${fmtT(c.s)}`, on: !rej.has(c.id) }))];
  if (!rows.length) return;
  el.innerHTML = rows.map(x => `<div class="e2-ch"><span class="e2-cht">${esc(x.txt)} <small class="e2-hint">${esc(x.who)}</small></span>
    <button class="e2-btn sm" data-capid="${esc(x.id)}" data-on="${x.on ? 1 : 0}">${x.on ? "Undo" : "Redo"}</button></div>`).join("");
  $$("[data-capid]", el).forEach(b => b.onclick = async () => {
    const id = b.dataset.capid, on = b.dataset.on === "1";
    try { await api("project/caption-fix?id=" + p.id, on ? { undo: id } : { allow: id }); toast(on ? "Undone. The next draft uses the original word" : "Back on", "ok"); e2CapFixes(p); } catch (e) { toast(e.message, "bad"); }
  });
}
function e2CapAt(t, caps) {
  caps = caps || E2.caps;
  const g = (caps && caps.groups) || [];
  return g.find(x => t >= x.s - 0.05 && t <= x.e + 0.05) || g.slice().sort((a, b) => Math.abs(a.s - t) - Math.abs(b.s - t)).find(x => Math.abs(x.s - t) < 1.5) || null;
}
function e2CapEdit(ctx) {
  ctx = ctx || e2Ctx();
  const v = ctx.v, pl = ctx.host; if (!v || !pl) return;
  v.pause();
  if (!ctx.caps) return toast("This video has no captions to fix. Turn captions on in the Captions tab", "bad");
  const g = e2CapAt(v.currentTime, ctx.caps); if (!g) return toast("No caption at this moment. Pause where the caption shows, then double-click", "bad");
  $("#e2-capbox") && $("#e2-capbox").remove();
  const box = document.createElement("div"); box.id = "e2-capbox"; box.className = "e2-capbox";
  box.innerHTML = `<label>Fix this caption</label><input class="e2-input" id="e2-capin" value="${esc(g.text)}">
    <div class="e2-capbtns"><label class="e2-capall"><input type="checkbox" id="e2-capall"> Fix this word everywhere</label><span class="grow"></span>
    <button class="e2-btn sm" id="e2-capx">Cancel</button><button class="e2-btn sm accent" id="e2-capok">Save</button></div>`;
  pl.appendChild(box);
  const inp = $("#e2-capin"); inp.focus(); inp.select();
  const close = () => box.remove();
  const save = async () => {
    const neu = inp.value.trim(); if (!neu || neu === g.text) return close();
    // word-for-word when the count matches (each changed word is its own fix), else the whole caption as one fix
    const a = g.text.split(/\s+/), b = neu.split(/\s+/), pairs = a.length === b.length ? a.map((w, i) => [w, b[i]]).filter(([x, y]) => x !== y) : [[g.text, neu]];
    const all = $("#e2-capall").checked;
    try {
      for (const [o, n] of pairs) await api("project/caption-fix?id=" + S.project.id, { old: o, new: n, t: g.s, all, video: ctx.video });
      close();
      const note = { text: `note ${fmtT2(g.s)}-${fmtT2(g.e)}: caption fix ${pairs.map(([o, n]) => `“${o}” → “${n}”`).join(", ")}${all ? " (everywhere)" : ""} (already saved; it comes in when the draft is made)` };
      if (ctx.editor) await e2AddNote(note, "Caption fixed. The next draft shows it");
      else { S.project = await api("project/notes?id=" + S.project.id, note); toast("Caption fixed. The next draft shows it", "ok"); }
    } catch (e) { toast(/404|not found|unknown|no such route/i.test(e.message) ? "Close and reopen Studio once to turn on caption fixing" : e.message, "bad"); }
  };
  inp.onkeydown = e => { e.stopPropagation(); if (e.key === "Enter") save(); else if (e.key === "Escape") close(); };
  $("#e2-capok").onclick = save; $("#e2-capx").onclick = close;
}

// ---------------------------------------------------------------- intro words (user 2026-10-29: "why can't I click on the
// intro text inside of my intro? ... double-click on it, type it in, and it'll change it", in the Editor AND the Revisions
// tab's Watch player). GET project/intro-text gives what the intro shows at that moment (the line being said + the title);
// each change goes to POST project/intro-text and the intro is rendered again with the new words: same shots, no new AI
// plan, ~4-5 min ("Save + update intro now") or with the next draft ("Save"). Product review intros (app/tools/intro_text.py).
function e2Ctx() { return { v: $("#ed-video"), host: $(".e2-player"), video: base(ED.playing || ""), caps: E2.caps, editor: true }; }
const e2Bare = s => String(s).replace(/^[^\w$]+|[^\w$%]+$/g, "");
async function e2DblFix(ctx) {
  const v = ctx.v; if (!v) return;
  v.pause();
  const t = v.currentTime, p = S.project;
  if (p.type === "review") {
    let r = null; try { r = await api(`project/intro-text?id=${p.id}&video=${enc(ctx.video)}&t=${t.toFixed(2)}`); } catch (e) { r = null; }
    if (r && (r.items || []).length) return e2IntroEdit(ctx, r, t);
  }
  e2CapEdit(ctx);
}
function e2IntroEdit(ctx, r, t) {
  $("#e2-capbox") && $("#e2-capbox").remove();
  const id = S.project.id, box = document.createElement("div"); box.id = "e2-capbox"; box.className = "e2-capbox";
  const fixRows = fx => fx.map(f => `<div class="e2-ch"><span class="e2-cht">“${esc(f.old)}” → “${esc(f.new)}”</span><button class="e2-btn sm" data-ifx="${esc(f.id)}">Undo</button></div>`).join("");
  box.innerHTML = `<label>Change the intro's words</label>
    ${r.items.map((it, i) => `<div class="e2-introf"><small>${esc(it.label)}</small><input class="e2-input" data-ii="${i}" value="${esc(it.text)}"></div>`).join("")}
    <div class="e2-introfx" id="e2-introfx">${(r.fixes || []).length ? `<small>Your intro changes</small>${fixRows(r.fixes)}` : ""}</div>
    <div class="e2-capbtns"><span class="grow"></span><button class="e2-btn sm" id="e2-capx">Cancel</button>
      <button class="e2-btn sm" id="e2-capok" title="The next draft shows the new words">Save</button>
      <button class="e2-btn sm accent" id="e2-capnow" title="Renders the intro again with your words, about 5 minutes. Same shots">Save + update intro now</button></div>`;
  ctx.host.appendChild(box);
  const ins = $$("[data-ii]", box); ins[0].focus(); ins[0].select();
  const close = () => box.remove();
  const wireUndo = () => $$("[data-ifx]", box).forEach(b => b.onclick = async () => {
    try {
      const res = await api("project/intro-text?id=" + id, { undo: b.dataset.ifx });
      $("#e2-introfx").innerHTML = res.fixes.length ? `<small>Your intro changes</small>${fixRows(res.fixes)}` : ""; wireUndo();
      toast("Undone. The intro goes back with the next draft, or press Save + update intro now", "ok");
    } catch (e) { toast(e.message, "bad"); }
  });
  wireUndo();
  const save = async now => {
    // word-for-word when the count matches (each changed word is its own fix), else the whole line as one fix; the edge
    // punctuation stays out ("Civic," -> "Corolla," changes Civic everywhere the intro shows it)
    const pairs = [];
    r.items.forEach((it, i) => {
      const neu = ins[i].value.trim(); if (!neu || neu === it.text) return;
      const a = it.text.split(/\s+/), b = neu.split(/\s+/);
      (a.length === b.length ? a.map((w, k) => [w, b[k]]) : [[it.text, neu]])
        .map(([o, n]) => [e2Bare(o), e2Bare(n)]).filter(([o, n]) => o && n && o !== n).forEach(x => pairs.push(x));
    });
    if (!pairs.length && !now) return close();
    try {
      for (const [o, n] of pairs) await api("project/intro-text?id=" + id, { old: o, new: n, t });
      close();
      if (now) {
        await api("project/intro-text?id=" + id, { apply: true });
        toast("Updating the intro with your words. About 5 minutes", "ok");
        await refresh(true); renderProject();
      } else toast(`Saved${pairs.length ? ": " + pairs.map(([o, n]) => `“${o}” → “${n}”`).join(", ") : ""}. The next draft shows it`, "ok");
    } catch (e) { toast(/404|not found|unknown|no such route/i.test(e.message) ? "Close and reopen Studio once to turn on intro text changes" : e.message, "bad"); }
  };
  ins.forEach(x => x.onkeydown = e => { e.stopPropagation(); if (e.key === "Enter") save(false); else if (e.key === "Escape") close(); });
  $("#e2-capok").onclick = () => save(false); $("#e2-capnow").onclick = () => save(true); $("#e2-capx").onclick = close;
}
// the Revisions tab's Watch player gets the same double-click (captions + intro words); app.js wireProject calls this
async function watchFixWire(p) {
  const v = $("#p-video"); if (!v) return;
  const host = v.parentElement; if (getComputedStyle(host).position === "static") host.style.position = "relative";
  const ctx = { v, host, video: "", caps: null, editor: false };
  const load = async () => {
    ctx.video = base(($("#p-out") && $("#p-out").value) || "");
    try { const r = await api(`project/captions?id=${p.id}&video=${enc(ctx.video)}`); ctx.caps = (r.groups || []).length ? r : null; } catch (e) { ctx.caps = null; }
  };
  $("#p-out") && $("#p-out").addEventListener("change", load);
  v.ondblclick = e => { e.preventDefault(); e2DblFix(ctx); };
  if (!$("#p-fixhint")) v.insertAdjacentHTML("afterend", `<div class="e2-hint" id="p-fixhint">✎ Double-click the video to change a caption${p.type === "review" ? " or the intro's words" : ""}</div>`);
  await load();
}

// progress over the video while a draft / final is made (user 2026-10-29: after Create project "I don't even know what's
// going on ... where's the steps"). Reads the project's activity contract (New Project session, 2026-10-29):
//   p.activity = null | {state: importing|waiting|rendering|revising, label, pct, eta_s, detail, pos, wait_s, where}
//   p.jobs[0] = {status, progress: {pct, step, eta_s}, steps: [{label, status: pending|running|done|skipped}]}
// A laptop build only shows in p.activity. Polls the project every 2.5 s while something is going on; right after Create
// (nothing yet, no outputs) it says "Starting your first draft…" for up to 25 s, then offers the button.
// ONE number that always climbs (user 2026-10-29: "people want to know where their stuff is ... the bar can't just stop").
// Phases share one 0-100: getting ready / AI reading the changes 0-12, making the video 12-100 (its real %). Between real
// updates the shown % creeps toward a cap a little above the last real value, so it never sits still and never jumps back.
function e2Target(p) {
  const a = p.activity || {}, j = (p.jobs || []).find(x => x.status === "running" || x.status === "queued"), pr = (j && j.progress) || {};
  const pct = a.state === "rendering" && a.pct != null ? +a.pct : pr.pct != null ? +pr.pct : null;
  if (a.state === "waiting" || (j && j.status === "queued")) return { t: 1, cap: 4, wait: a.pos || (j && (j.queue || {}).pos) || 0 };
  if (pct != null && (a.state === "rendering" || j)) return { t: 12 + pct * 0.87, cap: Math.min(99, 12 + pct * 0.87 + 7), eta: a.eta_s || pr.eta_s || 0 };
  return { t: 2, cap: 11 };   // importing / AI reading the changes / just started
}
// the one % shown everywhere (editor working screen + project cards): never goes back for the same project
const STUDIO_PCT = {};
function studioPct(p) { const g = e2Target(p); STUDIO_PCT[p.id] = Math.max(STUDIO_PCT[p.id] || 0, g.t); return { s: STUDIO_PCT[p.id], g }; }
const studioLeft = eta => eta > 20 ? (typeof tlLeft === "function" ? tlLeft(eta) : "about " + Math.ceil(eta / 60) + " min left") : "";
// While a draft / final is made the editor is replaced by ONE clean screen (user 2026-10-29: no steps, not over the video,
// you can't edit while it renders; a Cancel button and "go back to the other projects")
function e2ProgHtml(p) {
  const { s, g } = studioPct(p); E2.shown = STUDIO_PCT; E2.cap = g.cap;
  const j = (p.jobs || []).find(x => x.status === "running" || x.status === "queued");
  return `<div class="e2w-card">
    <div class="e2w-spark">✨</div>
    <h2>${g.wait ? `Waiting for its turn${g.wait > 1 ? ` · ${g.wait - 1} ahead` : ""}` : "AI is working on your video"}</h2>
    <div class="e2w-pct" id="e2p-pct">${Math.floor(s)}%</div>
    <div class="e2w-bar"><i id="e2p-fill" style="width:${s}%"></i></div>
    <div class="e2w-eta">${studioLeft(g.eta) || "&nbsp;"}</div>
    <div class="e2w-btns"><button class="e2-btn" id="e2w-back">${TL_ICON.back}Back to projects</button>${j ? `<button class="e2-btn" id="e2w-cancel">Cancel</button>` : ""}</div>
    <p class="e2w-note">You can close this page or work on other videos. It keeps going.</p></div>`;
}
function e2WorkWire(p) {
  $("#e2w-back") && ($("#e2w-back").onclick = () => nav("projects"));
  const c = $("#e2w-cancel"); if (!c) return;
  c.onclick = async () => {
    const j = (S.project.jobs || []).find(x => x.status === "running" || x.status === "queued"); if (!j) return;
    if (!confirm("Stop making this video? Your changes stay, so you can start it again later.")) return;
    try { await api("job/cancel?id=" + j.id, {}); toast("Stopped", "ok"); delete STUDIO_PCT[p.id]; setTimeout(async () => { await refresh(true); await loadProject(); }, 1200); } catch (e) { toast(e.message, "bad"); }
  };
}
// creep: every 0.5 s the shown % moves a bit toward the cap (fast when far, slower when close; never past the cap)
function e2Creep(pid) {
  clearInterval(E2.creepT);
  E2.creepT = setInterval(() => {
    const f = $("#e2p-fill"), n = $("#e2p-pct"); if (!f || !S.project || S.project.id !== pid) return clearInterval(E2.creepT);
    const s = E2.shown[pid] || 0, cap = E2.cap || 99; if (s >= cap - 0.05) return;
    const next = Math.min(cap - 0.05, s + Math.max(0.03, (cap - s) * 0.02)); E2.shown[pid] = next;
    f.style.width = next + "%"; n.textContent = Math.floor(next) + "%";
  }, 500);
}
const e2Busy = p => !!p.activity || (p.jobs || []).some(j => j.status === "running" || j.status === "queued");
function e2Progress(p) {
  const pl = $(".e2-player"); if (!pl) return;
  clearInterval(E2.progT); $("#e2-prog") && $("#e2-prog").remove();
  const outs0 = (p.outputs || []).length;
  E2.startAt = E2.startAt || {};
  const starting = !e2Busy(p) && !outs0 && !ED.playing && (E2.startAt[p.id] = E2.startAt[p.id] || Date.now()) > Date.now() - 25000;
  if (e2Busy(p) || starting) {
    const ov = document.createElement("div"); ov.id = "e2-prog"; ov.className = "e2-prog"; ov.setAttribute("role", "status"); ov.innerHTML = e2ProgHtml(p);
    $(".e2-top").insertAdjacentElement("afterend", ov); $(".e2").classList.add("working"); e2WorkWire(p); e2Creep(p.id);
    const pp = $("#p-progress"); if (pp) pp.style.display = "none";   // the strip above the editor would say the same
    let was = e2Busy(p);
    E2.progT = setInterval(async () => {
      if (!$(".e2") || !S.project || S.project.id !== p.id) return clearInterval(E2.progT);
      let f; try { f = await api("project?id=" + p.id); } catch (e) { return; }
      S.project.activity = f.activity; S.project.jobs = f.jobs;
      const busy = e2Busy(f), more = (f.outputs || []).length > outs0;
      if (busy) { was = true; const o = $("#e2-prog"); if (o) { o.innerHTML = e2ProgHtml(f); e2WorkWire(f); } return; }
      if (more || was) { clearInterval(E2.progT); await refresh(true); await loadProject(); return; }   // done: show the new video
      if (Date.now() - E2.startAt[p.id] > 25000) { clearInterval(E2.progT); e2Progress(f); }   // nothing ever started
    }, 2500);
    return;
  }
  if (ED.playing) return;
  const nv = $(".e2-novideo", pl); if (!nv) return;
  nv.innerHTML = `<div class="e2-wait"><b>No draft yet</b><button class="e2-btn accent" id="e2-first">Make the first draft</button></div>`;
  $("#e2-first").onclick = async e => withBusy(e.currentTarget, "Starting…", async () => {
    const r = await api("project/run?id=" + p.id, { action: "draft" });
    if (r.mode !== "scheduled") toast("Making your first draft", "ok");
    E2.startAt[p.id] = Date.now(); await loadProject();
  });
}

// everything that depends on the notes (timeline, counts, drawer, words) redraws from here
function e2Refresh() {
  if (!$(".e2")) return;
  TX.E = txEditable(S.project.notes); TX.prot = txOtherProtects(S.project.notes);
  const K = e2Pending().length, mk = $("#e2-make");
  if (mk) {
    mk.disabled = !K || !!S.project.jobs.length;
    mk.innerHTML = S.project.jobs.length ? "Making your draft…" : K ? `${TL_ICON.check}Make Draft ${(E2.draftNo || 0) + 1} · ${K} change${K > 1 ? "s" : ""}` : "No changes yet";
  }
  const k = $("#e2-k"); if (k) k.textContent = K ? `(${K})` : "";
  $("#tx-undo") && ($("#tx-undo").disabled = !TX.undo.length);
  e2Timeline();
  e2Drawer();
  if (E2.tab === "words") e2WordsPaint();
}
// app4's cutter calls txCount after every cut / save: route it here
const _txCount10 = txCount;
txCount = function () { if ($(".e2")) { clearTimeout(E2.rt); E2.rt = setTimeout(e2Refresh, 40); return; } return _txCount10(); };
const _txPaint10 = txPaint;
txPaint = function () { if ($(".e2")) { e2WordsPaint(); txCount(); return; } return _txPaint10(); };

// ---------------------------------------------------------------- timeline (draft time, no gaps)
function e2Timeline() {
  const el = $("#e2-rows"); if (!el || !ED.data) return;
  const d = ED.data, D = e2Dur(), off = d.offset || 0, sel = {};
  const sc0 = $("#e2-scroll") ? $("#e2-scroll").scrollLeft : 0;
  const step = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800].find(s => D / E2.zoom / s <= 8) || 3600;
  let ticks = ""; for (let t = 0; t <= D; t += step) ticks += `<span style="left:${e2Pct(t)}">${fmtT(t)}</span>`;
  ticks += e2Pending().map(({ n }) => e2NoteDraft(n)).filter(Boolean).map(([a]) => `<i class="e2-tick" style="left:${e2Pct(a)}"></i>`).join("");
  // Video: Intro + Your video, split where you split
  const cuts = [off, ...E2.splits.filter(t => t > off + 0.3 && t < D - 0.3).sort((a, b) => a - b), D];
  let video = off > 0.3 ? `<div class="e2-blk intro ${sel.type === "vid" && sel.a === 0 ? "sel" : ""}" data-vid="0,${off}" style="left:0;width:${e2Pct(off)}"><span>Intro</span></div>` : "";
  for (let i = 0; i < cuts.length - 1; i++) {
    const a = cuts[i], b = cuts[i + 1];
    video += `<div class="e2-blk vid ${sel.type === "vid" && Math.abs(sel.a - a) < 0.01 ? "sel" : ""}" data-vid="${a},${b}" style="left:${e2Pct(a)};width:${e2Pct(b - a)}"><span>${cuts.length > 2 ? `Part ${i + 1}` : "Your video"}</span></div>`;
  }
  // B-roll (and titles): the notes that place them
  const notes = S.project.notes || [];
  let broll = "";
  notes.forEach((n, idx) => {
    if (n.off) return;
    const isB = n.kind === "broll", isT = n.kind === "text" && TL_TEXT_RX.test(n.text || "");
    if (!isB && !isT) return;
    const r = e2NoteDraft(n); if (!r) return;
    const [a, b] = [r[0], Math.max(r[1], r[0] + 0.8)];
    const label = isB ? (n.clip || "next B-roll clip") : "T “" + (((n.text || "").match(/[“"]([^”"]+)[”"]/) || [, "Text"])[1]) + "”";
    broll += `<div class="e2-blk ${isB ? "broll" : "title"}" data-note="${idx}" style="left:${e2Pct(a)};width:${e2Pct(b - a)}" title="${esc(e2Plain(n))}"><span>${esc(label)}</span></div>`;
  });
  if (!broll) broll = `<div class="e2-empty">B-roll is placed for you when the draft is made</div>`;
  // Music: song names exactly where they play
  const parts = tlMusicParts();
  let music = "";
  const mb = (a, b, tr, i) => `<div class="e2-blk music" data-song="${i}" style="left:${e2Pct(a)};width:${e2Pct(Math.max(0.5, b - a))}" title="${esc(base(tr))}"><span>♪ ${esc(base(tr).replace(/\.[^.]+$/, ""))}</span></div>`;
  if (parts.length && parts.every(x => x.ds != null)) music = parts.map((x, i) => mb(x.ds, x.de, x.track, i)).join("");
  else if (parts.length && parts.every(x => x.a != null)) music = parts.map((x, i) => mb(tlDraftOf(x.a), tlDraftOf(x.b), x.track, i)).join("");
  else if (parts.length) { const w = (D - off) / parts.length; music = parts.map((x, i) => mb(off + i * w, off + (i + 1) * w, x.track, i)).join(""); }
  if (!music) music = `<div class="e2-blk music auto" data-song="-1" style="left:0;width:100%"><span>♪ Music is picked for you on the next draft</span></div>`;
  // Captions
  const cap = (d.settings || {}).captions, on = cap === true || (cap && cap.on), where = on ? ((cap && cap.where) || "all") : "off";
  const capb = (a, b, l) => `<div class="e2-blk caps" data-caps="1" style="left:${e2Pct(a)};width:${e2Pct(b - a)}"><span>${l}</span></div>`;
  const caps = where === "off" ? `<div class="e2-empty" data-caps="1">No captions</div>` : where === "bookends" ? capb(0, Math.max(off, 15), "Captions") + capb(D - Math.min(30, D * 0.1), D, "Captions") : capb(0, D, "Captions · whole video");
  // names stay put on the left; the lanes scroll sideways when zoomed in (E2.zoom = how many screens wide)
  const lanes = [["Video", video, "v"], ["B-roll", broll, "b"], ["Music", music, "m"], ["Captions", caps, "c"]];
  el.innerHTML = `<div class="e2-labels"><span class="e2-rl r"></span>${lanes.map(([n, , c]) => `<span class="e2-rl ${c}">${n}</span>`).join("")}</div>
    <div class="e2-scroll" id="e2-scroll"><div class="e2-inner" id="e2-inner" style="width:${E2.zoom * 100}%">
      <div class="e2-ticks">${ticks}</div>
      ${lanes.map(([, h, c]) => `<div class="e2-lane ${c}" data-lane="${c}">${h}</div>`).join("")}
      <div class="e2-head" id="e2-head"><span id="e2-bub">0:00</span></div>
    </div></div>`;
  $("#e2-scroll").scrollLeft = sc0;
  e2Head();
}
function e2Head(follow) {
  const v = $("#ed-video"), h = $("#e2-head"), sf = $("#e2-seekfill");
  if (sf && !E2.scrub) sf.style.width = e2Pct(v ? v.currentTime : 0);   // the seek bar under the video
  if (!h || E2.scrub) return;
  const t = v ? v.currentTime : 0, sc = $("#e2-scroll");
  h.style.left = e2Pct(t);
  const f = t / (e2Dur() || 1); $("#e2-bub").style.transform = f < 0.04 ? "none" : f > 0.96 ? "translateX(-100%)" : "";   // flag stays inside at the ends
  // zoomed in: keep the red line on screen while it plays or jumps
  if (follow === true && sc && E2.zoom > 1) {
    const x = sc.scrollWidth * t / (e2Dur() || 1);
    if (x < sc.scrollLeft + 20 || x > sc.scrollLeft + sc.clientWidth - 40) sc.scrollLeft = x - sc.clientWidth / 3;
  }
  const s = fmtT(t); $("#e2-bub").textContent = s; const n = $("#e2-now"); if (n) n.textContent = s;
}

// zoom the timeline by f, keeping the time under the mouse (or the red line) where it is
function e2Zoom(f, clientX) {
  const sc = $("#e2-scroll"); if (!sc) return;
  const z = f === 0 ? 1 : Math.max(1, Math.min(60, E2.zoom * f)); if (z === E2.zoom) return;
  const r = sc.getBoundingClientRect(), v = $("#ed-video");
  let fx, at;
  if (clientX != null) { fx = Math.max(0, Math.min(1, (clientX - r.left) / r.width)); at = (sc.scrollLeft + fx * sc.clientWidth) / sc.scrollWidth; }
  else { at = (v ? v.currentTime : 0) / (e2Dur() || 1); fx = Math.max(0.1, Math.min(0.9, (at * sc.scrollWidth - sc.scrollLeft) / sc.clientWidth)); }
  E2.zoom = z; e2Timeline();
  const s2 = $("#e2-scroll"); s2.scrollLeft = at * s2.scrollWidth - fx * s2.clientWidth;
}

// ---------------------------------------------------------------- Words: the draft's transcript
function e2WordsHtml() {
  const d = ED.data; if (!d.words.length) return `<div class="e2-hint">No words yet. They appear once the first draft is made.</div>`;
  let html = "", para = "";
  const flush = () => { if (para) html += para + "</p>"; para = ""; };
  TX.sents.forEach((s, k) => {
    if (s.para || !para) { flush(); let t0 = null; for (let i = s.i0; i <= s.i1 && t0 == null; i++) if (txKept(d.words[i])) t0 = tlDraftOf(d.words[i].s); para = `<p class="e2-para"><span class="e2-pt">${t0 == null ? "Cut part" : fmtT(t0)}</span>`; }
    for (let i = s.i0; i <= s.i1; i++) para += `<span class="w" data-i="${i}">${esc(d.words[i].w)}</span> `;
  });
  flush();
  return html;
}
function e2WordsPaint() {
  const tr = $("#ed-tr"); if (!tr || !ED.data) return;
  tr.classList.toggle("hide-cuts", !E2.showCuts);
  $$(".w", tr).forEach(el => { const s = txState(+el.dataset.i); el.className = "w" + (s ? " " + (s === "p" ? "p" : "cut " + s) : "") + (+el.dataset.i === TX.cur ? " now" : ""); });
  // a paragraph with nothing left in it hides with its cut words
  $$(".e2-para", tr).forEach(pe => pe.classList.toggle("allcut", !pe.querySelector(".w:not(.cut)")));
}

// ---------------------------------------------------------------- tabs
async function e2Pane() {
  const pane = $("#e2-pane"); if (!pane) return;
  $$("[data-e2tab]").forEach(b => b.classList.toggle("on", b.dataset.e2tab === E2.tab));
  // Words = Gling: big transcript, video + changes beside it, no timeline. Every other tab = Filmora: 3 panels over the timeline.
  $(".e2") && $(".e2").classList.toggle("words-mode", E2.tab === "words");
  $(".e2") && $(".e2").classList.toggle("watch-mode", E2.tab === "revise");
  if (E2.tab === "revise") { pane.innerHTML = ""; return; }
  const p = S.project, d = ED.data, I = TL_ICON;
  if (E2.tab === "words") {
    pane.innerHTML = `<div class="e2-wbar"><span>Click a word to jump there.</span><label><input type="checkbox" id="e2-showcuts" ${E2.showCuts ? "checked" : ""}> Show cut words</label></div>
      <div class="e2-words" id="ed-tr">${e2WordsHtml()}</div>
      <div class="e2-wfoot">Select words, then press <b>Cut</b> or <b>Bring back</b>.</div>`;
    $("#e2-showcuts").onchange = e => { E2.showCuts = e.target.checked; e2WordsPaint(); };
    e2WordsPaint(); e2WireWords();
  } else if (E2.tab === "clips") {
    const files = d.broll_files || [];
    // AI does the placing (user 2026-10-29): add clips here, the next draft puts them where they fit, muted over your voice
    pane.innerHTML = `<div class="e2-pbody"><h2>Your B-roll clips</h2>
      <button class="e2-btn accent" id="e2-addclips">${I.plus}Add video clips</button>
      <p class="e2-hint">The next draft puts them where they fit, muted over your voice. Want one in a certain spot? Type it as a change, e.g. “show the box clip when I open it”.</p>
      <div class="e2-tiles">${files.map(f => `<div class="e2-tile" title="${esc(f)}"><div class="e2-thumb" style="background-image:url('${thumbUrl(f, null, 1, 320)}')"></div><b>${esc(base(f))}</b></div>`).join("") || `<p class="e2-hint">No clips added yet.</p>`}</div></div>`;
    $("#e2-addclips").onclick = async () => {
      let ps = [];
      try { ps = await pickFiles("video", true) || []; } catch (e) { toast(e.message, "bad"); }
      if (!ps.length) return;
      await addToSlot(p, "broll", ps);
      await e2AddNote({ text: `note 0:00-0:03: use the new B-roll clip${ps.length > 1 ? "s" : ""} ${ps.map(x => base(x)).join(", ")} where they fit` }, `Added ${ps.length} clip${ps.length > 1 ? "s" : ""}. The next draft places them`);
    };
  } else if (E2.tab === "music") {
    // the songs and when they play; Change (or right-click a song on the timeline) opens the whole catalog in a pop-up
    const parts = tlMusicParts(), D = e2Dur(), off = d.offset || 0;
    const when = (x, i) => x.ds != null ? `${fmtT(x.ds)}–${fmtT(x.de)}` : x.a != null ? `${fmtT(tlDraftOf(x.a))}–${fmtT(tlDraftOf(x.b))}` : parts.length ? `${fmtT(off + i * (D - off) / parts.length)}–${fmtT(off + (i + 1) * (D - off) / parts.length)} (about)` : "";
    pane.innerHTML = `<div class="e2-pbody"><h2>Music in this video</h2>
      ${parts.length ? parts.map((x, i) => `<div class="e2-song"><button class="e2-pbtn" data-prev="${esc(x.track)}" data-off="${x.offset || 20}" aria-label="Play this song">▶</button>
        <span class="e2-sname"><b>${esc(base(x.track).replace(/\.[^.]+$/, ""))}</b><span>${esc(x.name)} · ${when(x, i)}</span></span><button class="e2-btn sm" data-songfor="${i}">Change</button></div>`).join("")
      : `<p class="e2-hint">The next draft picks music that fits.</p>`}
      <button class="e2-btn" data-songfor="-1">${TL_ICON.music}Pick one song for the whole video</button>
      <p class="e2-hint">Tip: right-click a song on the timeline to change it. Songs blend with a 1-second crossfade.</p></div>`;
    $$("[data-songfor]", pane).forEach(b => b.onclick = () => e2MusicPicker(+b.dataset.songfor));
    $$("[data-prev]", pane).forEach(b => b.onclick = () => tlPreview(b.dataset.prev, +b.dataset.off, b));
  } else if (E2.tab === "text") {
    const kinds = [["Big title", "a big title across the middle"], ["Label (price, name)", "a small label near the bottom"], ["Subscribe reminder", "a subscribe reminder"]];
    pane.innerHTML = `<div class="e2-pbody"><h2>Text on screen</h2><p class="e2-hint">Type the words, then pick where they go. They show at the red line for about 3 seconds.</p>
      <input id="e2-words" class="e2-input" placeholder="Words to show, e.g. Worth it?">
      ${kinds.map(([k, w], i) => `<button class="e2-bigbtn" data-kind="${i}">+ ${k}</button>`).join("")}</div>`;
    $$("[data-kind]", pane).forEach(b => b.onclick = () => {
      const k = kinds[+b.dataset.kind], w = $("#e2-words").value.trim() || (k[0] === "Subscribe reminder" ? "Subscribe" : "");
      if (!w) { toast("Type the words to show first", "bad"); $("#e2-words").focus(); return; }
      const t = $("#ed-video") ? $("#ed-video").currentTime : 0;
      e2AddNote({ text: `note ${fmtT2(t)}-${fmtT2(t + 3)}: add on-screen text “${w}” as ${k[1]}` }, `Added “${w}” at ${fmtT(t)}`);
      $("#e2-words").value = "";
    });
  } else if (E2.tab === "captions") {
    const cap = d.settings.captions, on = cap === true || (cap && cap.on), where = on ? ((cap && cap.where) || "all") : "off", style = (cap && cap.style) || "bold";
    const metas = Object.values(CAP_META || {}).filter(x => x.pick !== false);
    const four = metas;   // all of them, scroll (no hidden "More styles")
    pane.innerHTML = `<div class="e2-pbody"><h2>Captions</h2><p class="e2-hint">The words you say, shown on screen.</p>
      ${[["all", "Whole video"], ["bookends", "Intro and ending only"], ["off", "No captions"]].map(([k, l]) => `<button class="e2-bigbtn ${where === k ? "on" : ""}" data-where="${k}">${l}</button>`).join("")}
      <h3>Fixed words</h3><div id="e2-capfixes"><p class="e2-hint">Double-click a caption on the video to fix a word. The AI also fixes misheard names for you.</p></div>
      <h3>Look</h3><div class="e2-caps">${four.map(x => `<button class="e2-cap ${x.key === style ? "on" : ""}" data-cap="${esc(x.key)}"><img src="${esc(x.png || "captions/" + x.key + ".png")}" alt=""><span>${esc(String(x.label).split(" · ")[0])}</span></button>`).join("")}</div>
</div>`;
    e2CapFixes(p);
    const save = async (c, said) => {
      S.project = await api("project/update?id=" + p.id, { settings: { captions: c } }); ED.data.settings.captions = c;
      await e2AddNote({ text: `note 0:00-0:03: ${said} (already set in the project settings; it comes in when the draft is made)` }, said);
      e2Pane();
    };
    $$("[data-where]", pane).forEach(b => b.onclick = () => { const w = b.dataset.where; save(w === "off" ? { on: false, style } : { on: true, style, where: w }, w === "off" ? "Captions off" : w === "all" ? "Captions on the whole video" : "Captions on the intro and ending only"); });
    $$("[data-cap]", pane).forEach(b => b.onclick = () => save({ on: true, style: b.dataset.cap, where: where === "off" ? "all" : where }, `Caption look: ${b.textContent.trim()}`));
  } else if (E2.tab === "transitions") {
    pane.innerHTML = `<div class="e2-pbody"><h2>Transitions</h2><p class="e2-hint">Loading…</p></div>`;
    let r; try { r = await api("transitions?id=" + p.id); } catch (e) { r = { items: [], applies: false }; }
    if (E2.tab !== "transitions") return;
    const pick = (r.chosen || "").toLowerCase();
    pane.innerHTML = `<div class="e2-pbody"><h2>Transitions</h2><p class="e2-hint">Picked for you automatically. Choose one only if you want your own.</p>` + (r.applies
      ? [{ name: "Automatic (recommended)", path: "", sub: r.auto ? base(r.auto).replace(/\.[^.]+$/, "") : "" }, ...r.items.map(x => ({ name: x.name, path: x.path, sub: x.where === "this video" ? "made for this video" : "" }))]
        .map(x => `<button class="e2-bigbtn ${(x.path || "").toLowerCase() === pick ? "on" : ""}" data-wipe="${esc(x.path)}">${esc(x.name)}${x.sub ? ` <small>${esc(x.sub)}</small>` : ""}</button>`).join("")
      : `<button class="e2-bigbtn on" disabled>Automatic (recommended)</button><p class="e2-hint">This kind of video uses clean cuts between parts. Want something else? Type it as a change.</p>`) + `</div>`;
    $$("[data-wipe]", pane).forEach(b => b.onclick = async () => {
      S.project = await api("project/update?id=" + p.id, { settings: { wipe: b.dataset.wipe || null } });
      await e2AddNote({ text: `note 0:00-0:03: transitions: ${b.dataset.wipe ? "use “" + b.textContent.trim() + "”" : "back to automatic"} (already set in the project settings)` }, "Transition saved");
      e2Pane();
    });
  }
}
// the music catalog as a pop-up (user 2026-10-29: "we can't jam all this... we might need a pop-up window")
async function e2MusicPicker(i) {
  E2.songFor = i >= 0 ? i : null;
  const parts = tlMusicParts(), part = i >= 0 ? parts[i] : null;
  $("#e2-pick") && $("#e2-pick").remove();
  const m = document.createElement("div"); m.className = "e2-modal"; m.id = "e2-pick";
  m.innerHTML = `<div class="e2-mbox" role="dialog" aria-label="Pick a song"><div class="e2-mhead"><h2>${part ? `New song for ${esc(part.name)}` : "One song for the whole video"}</h2><button class="e2-btn sm" id="e2-mx">✕ Close</button></div>
    ${part ? `<p class="e2-hint">Now: ${esc(base(part.track).replace(/\.[^.]+$/, ""))}</p>` : ""}
    <div class="e2-chips">${TL_MOODS.map(x => `<button class="e2-chip ${TL.mood === x ? "on" : ""}" data-mood="${x}">${x}</button>`).join("")}</div>
    <input class="e2-input" id="e2-msearch" placeholder="Search your music…">
    <div class="e2-mlist" id="e2-mlist"><p class="e2-hint">Loading your music…</p></div></div>`;
  document.body.appendChild(m);
  const close = () => { m.remove(); E2.songFor = null; try { TL.audio && TL.audio.pause(); } catch (e) { } };
  m.onclick = e => { if (e.target === m) close(); };
  $("#e2-mx").onclick = close;
  m.onkeydown = e => { if (e.key === "Escape") close(); };
  TL.mood = TL.mood || "chill";
  const lib = await tlMusicLib();
  const paint = () => {
    const q = ($("#e2-msearch").value || "").toLowerCase().trim();
    // each song keeps its OWN mood (its top score); the chip only decides which songs come first
    const top = t => { const e = Object.entries(t.moods || {}).sort((a, b) => b[1] - a[1])[0]; return e ? e[0] : (t.cat || ""); };
    const found = lib.tracks.filter(t => !q || t.name.toLowerCase().includes(q));
    const by = (a, b) => ((b.moods || {})[TL.mood] || 0) - ((a.moods || {})[TL.mood] || 0);
    const match = found.filter(t => top(t) === TL.mood).sort(by), other = found.filter(t => top(t) !== TL.mood).sort(by);
    const row = t => `<div class="e2-song lib"><button class="e2-pbtn dark" data-prev="${esc(t.path)}" data-off="20" aria-label="Play">▶</button><span class="e2-sname"><b>${esc(t.name)}</b><span>${esc(top(t))}${t.bpm ? ` · ${Math.round(t.bpm)} bpm` : ""}</span></span><button class="e2-btn sm accent" data-use="${esc(t.path)}">Use</button></div>`;
    const rows = match.slice(0, 80), rest = other.slice(0, Math.max(0, 80 - rows.length));
    $("#e2-mlist").innerHTML = rows.length || rest.length ? (rows.length ? rows.map(row).join("") : `<p class="e2-hint">No ${esc(TL.mood)} songs yet.</p>`)
      + (rest.length ? `<p class="e2-divider">Other songs</p>` + rest.map(row).join("") : "")
      : `<p class="e2-hint">${lib.tracks.length ? "No song matches." : "No music library found. Set your music folder in Settings."}</p>`;
    $$("[data-prev]", m).forEach(b => b.onclick = () => tlPreview(b.dataset.prev, +b.dataset.off, b));
    $$("[data-use]", m).forEach(b => b.onclick = async () => { await e2UseSong(b.dataset.use); m.remove(); });
    $$(".e2-song.lib", m).forEach(r => r.oncontextmenu = e => tlSongMenu(e, r.querySelector("[data-use]").dataset.use, paint));
  };
  $$("[data-mood]", m).forEach(b => b.onclick = () => { TL.mood = b.dataset.mood; $$("[data-mood]", m).forEach(x => x.classList.toggle("on", x === b)); paint(); });
  $("#e2-msearch").oninput = paint;
  paint(); $("#e2-msearch").focus();
}
async function e2UseSong(path) {
  const parts = tlMusicParts(), i = E2.songFor, part = i != null ? parts[i] : null, name = base(path).replace(/\.[^.]+$/, "");
  const p = S.project;
  if (p.type === "gaming") {   // the gaming build reads settings.music[section].track
    const keys = part ? [part.key] : tlSections().map(s => s.name);
    S.project = await api("project/update?id=" + p.id, { settings: { music: Object.fromEntries(keys.map(k => [k, { track: path }])) } });
    ED.data.music = { ...(ED.data.music || {}), ...Object.fromEntries(keys.map(k => [k, { ...((ED.data.music || {})[k] || {}), track: path }])) };
  }
  const t0 = part && part.ds != null ? part.ds : 0, t1 = part && part.de != null ? part.de : e2Dur();
  await e2AddNote({ text: `note ${fmtT2(t0)}-${fmtT2(t1)}: music: use “${name}” for ${part ? part.name.toLowerCase() : "the whole video"} (file: ${path}), 1 second crossfade where the music changes${p.type === "gaming" ? " (already set in the project settings)" : ""}` },
    `“${name}” for ${part ? part.name : "the whole video"}: added to your changes`);
  E2.songFor = null; e2Pane();
}

// ---------------------------------------------------------------- changes drawer
// the Changes panel on the right (always open, like Filmora's info panel)
function e2Drawer() {
  const dr = $("#e2-dlist"); if (!dr) return;
  const list = e2Pending();
  dr.innerHTML = `${list.length ? list.map(({ n, idx }) => { const r = e2NoteDraft(n); return `<div class="e2-ch" data-idx="${idx}" data-nid="${esc(n.nid || "")}">
        <button class="e2-chtime" data-jump="${r ? r[0] : ""}" title="Play from here">${r ? `▶ ${fmtT(r[0])}${r[1] - r[0] > 3.05 ? "–" + fmtT(r[1]) : ""}` : "—"}</button>
        ${E2.editIdx === idx ? `<input class="e2-input e2-edit" value="${esc(e2Plain(n))}">` : `<span class="e2-cht" data-jump="${r ? r[0] : ""}">${esc(e2Plain(n))}</span>`}
        ${n.kind === "text" || n.kind === "revision" || !n.kind ? `<button class="e2-btn sm" data-edit="${idx}" aria-label="Edit">✎</button>` : ""}<button class="e2-btn sm" data-del="${idx}" aria-label="Delete">✕</button></div>`; }).join("")
      : `<p class="e2-hint">No changes yet. Watch your video, and when something's wrong, pause and type or say what to change. It's added at that moment.</p>`}`;
  $$("[data-jump]", dr).forEach(b => b.onclick = () => { const t = parseFloat(b.dataset.jump), v = $("#ed-video"); if (v && !isNaN(t)) { v.currentTime = Math.max(0, t - 1); e2Head(); if (b.classList.contains("e2-chtime")) v.play(); } });
  $$("[data-del]", dr).forEach(b => b.onclick = async () => {
    const idx = +b.dataset.del, n = S.project.notes[idx];
    if (n && n.nid && TX.E.some(x => x.nid === n.nid)) { txApply(TX.E.filter(x => x.nid !== n.nid), "change removed"); return; }
    try { await e2AddNote({ remove: idx }); } catch (e) { toast(e.message, "bad"); }
  });
  $$("[data-edit]", dr).forEach(b => b.onclick = () => { E2.editIdx = +b.dataset.edit; e2Drawer(); const i = $(".e2-edit"); i && (i.focus(), i.select()); });
  const ed = $(".e2-edit");
  if (ed) ed.onkeydown = async e => {
    if (e.key === "Escape") { E2.editIdx = null; e2Drawer(); return; }
    if (e.key !== "Enter") return;
    const idx = E2.editIdx, n = S.project.notes[idx], r = e2NoteDraft(n) || [0, 3], txt = ed.value.trim(); E2.editIdx = null;
    if (!txt) return e2Drawer();
    try { await e2AddNote({ remove: idx }); await e2AddNote({ text: `note ${fmtT2(r[0])}-${fmtT2(r[1])}: ${txt}` }, "Change updated"); } catch (err) { toast(err.message, "bad"); }
  };
}

// ---------------------------------------------------------------- dictation: the Studio's own mic (local Whisper)
const E2MIC_ICON = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM5 11a7 7 0 0 0 14 0M12 18v3"/></svg>`;
function e2Mic() {
  const btn = $("#e2-mic"), field = $("#e2-chg"); if (!btn || !field) return;
  E2.micDummy = E2.micDummy || document.createElement("button");
  micToggle(E2.micDummy, field);
  clearInterval(E2.micT);
  E2.micT = setInterval(() => {
    const b = $("#e2-mic"); if (!b) return clearInterval(E2.micT);
    const rec = MIC.rec && MIC.rec.state === "recording", busy = E2.micDummy.classList.contains("busy");
    b.classList.toggle("listening", rec); b.classList.toggle("busy", busy);
    b.innerHTML = rec ? `<i class="e2-dot"></i>Listening… click to stop` : busy ? "Writing it down…" : `${E2MIC_ICON}Speak`;
    if (!rec && !busy) clearInterval(E2.micT);
  }, 200);
}

// ---------------------------------------------------------------- wiring
function e2Wire(p) {
  const v = $("#ed-video");
  $("#e2-home").onclick = () => nav("projects");
  $("#e2-more").onclick = e => { e.stopPropagation(); tlMoreMenu(e.currentTarget, p); };
  $("#e2-final").onclick = () => e2ExportDialog(p);
  $("#e2-make").onclick = async e => {
    await TX.sync;
    withBusy(e.currentTarget, "Sending…", async () => {
      const r = await api("project/rebuild-notes?id=" + p.id, {});
      if (r.mode !== "scheduled") toast(`Making Draft ${(E2.draftNo || 0) + 1}. You get a message when it's ready`, "ok");
      await loadProject(); pollJobs(p.id);
    });
  };
  $("#tx-undo").onclick = () => { if (!TX.undo.length) return; TX.redo.push(TX.E); TX.E = TX.undo.pop(); txPaint(); txSync("undo"); };
  // rename in place
  const title = $("#e2-title");
  const startRename = () => {
    const inp = document.createElement("input"); inp.className = "e2-input e2-tin"; inp.value = p.title; title.replaceWith(inp); inp.focus(); inp.select();
    const done = async ok => {
      const t = inp.value.trim();
      if (ok && t && t !== p.title) {
        try {
          let r;
          // Windows locks the folder while its video is open in the player ("Access is denied"): keep the folder name then
          try { r = await api("project/rename?id=" + p.id, { title: t, folder: true }); }
          catch (err) { if (!/denied|in use|being used|WinError (5|32)/i.test(err.message)) throw err; r = await api("project/rename?id=" + p.id, { title: t, folder: false }); }
          toast(`Renamed to “${r.title}”`, "ok"); await refresh(true); await loadProject(); return;
        } catch (err) { toast(err.message, "bad"); }
      }
      inp.replaceWith(title);
    };
    let fin = false; const once = ok => { if (fin) return; fin = true; done(ok); };
    inp.onkeydown = e => { if (e.key === "Enter") once(true); else if (e.key === "Escape") once(false); };
    inp.onblur = () => once(true);   // clicking off saves (user 2026-10-29)
  };
  title.onclick = startRename; title.onkeydown = e => { if (e.key === "Enter") startRename(); };
  // tabs
  $$("[data-e2tab]").forEach(b => b.onclick = () => { E2.tab = b.dataset.e2tab; e2Pane(); });
  // player
  const play = $("#e2-play");
  if (v) {
    play.onclick = () => v.paused ? v.play() : v.pause();
    v.onplay = () => { play.textContent = "❚❚"; play.setAttribute("aria-label", "Pause"); e2Tick(); };
    v.onpause = () => { play.textContent = "▶"; play.setAttribute("aria-label", "Play"); };
    // one click plays / pauses (a short wait so a double-click doesn't also toggle it); double-click fixes the caption
    v.onclick = () => { clearTimeout(E2.clickT); E2.clickT = setTimeout(() => v.paused ? v.play() : v.pause(), 220); };
    v.ondblclick = e => { e.preventDefault(); clearTimeout(E2.clickT); e2DblFix(e2Ctx()); };
    v.ontimeupdate = () => e2Head(true); v.onseeked = () => e2Head(true);
  } else play.disabled = true;
  // the ⟲10 / 10⟳ / speed bar (app5) goes into the control row instead of covering the video
  setTimeout(() => { const pb = $(".e2-player .pbar"), c = $(".e2-ctrl"); if (pb && c) c.appendChild(pb); }, 0);
  // changes
  const add = async () => {
    const f = $("#e2-chg"), text = f.value.trim(); if (!text) { f.focus(); return; }
    const t = v ? v.currentTime : 0, hasTime = /\b\d{1,2}:\d{2}(\.\d+)?\b/.test(text);
    try { await e2AddNote({ text: hasTime ? `note ${text}` : `note ${fmtT2(t)}-${fmtT2(t + 3)}: ${text}` }, `Change added at ${fmtT(t)}`); f.value = ""; } catch (e) { toast(e.message, "bad"); }
  };
  $("#e2-add").onclick = add;
  $("#e2-chg").onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); add(); } };
  $("#e2-mic").onclick = e2Mic;
  // timeline
  $("#e2-zin").onclick = () => e2Zoom(1.5);
  $("#e2-zout").onclick = () => e2Zoom(1 / 1.5);
  $("#e2-zfit").onclick = () => e2Zoom(0);
  const rows = $("#e2-rows");
  // Ctrl + scroll wheel zooms; the plain wheel scrolls sideways when zoomed in
  rows.addEventListener("wheel", e => {
    if (e.ctrlKey || e.metaKey) { e.preventDefault(); e2Zoom(e.deltaY < 0 ? 1.25 : 1 / 1.25, e.clientX); return; }
    const sc = $("#e2-scroll"); if (sc && E2.zoom > 1 && Math.abs(e.deltaY) > Math.abs(e.deltaX)) { e.preventDefault(); sc.scrollLeft += e.deltaY; }
  }, { passive: false });
  const tAt = x => { const r = $("#e2-inner").getBoundingClientRect(); return Math.max(0, Math.min(e2Dur(), ((x - r.left) / r.width) * e2Dur())); };
  rows.onclick = e => {
    if (E2.justDragged) { E2.justDragged = false; return; }
    const lane = e.target.closest(".e2-lane, .e2-ticks"); if (!lane) return;
    if (v) { v.currentTime = tAt(e.clientX); e2Head(); }
  };
  // right-click a song -> change it (the catalog pop-up); right-click captions -> the Captions tab
  rows.oncontextmenu = e => {
    const song = e.target.closest("[data-song]"), caps = e.target.closest("[data-caps]");
    if (!song && !caps) return;
    e.preventDefault();
    $("#e2-ctx") && $("#e2-ctx").remove();
    const m = document.createElement("div"); m.className = "ctx e2-ctx"; m.id = "e2-ctx";
    m.innerHTML = song ? `<a data-a="song">${TL_ICON.music}Change this song…</a><a data-a="whole">Pick one song for the whole video…</a>` : `<a data-a="caps">${TL_ICON.captions}Caption settings…</a>`;
    document.body.appendChild(m);
    const k = (m.getBoundingClientRect().width / (m.offsetWidth || 1)) || 1;
    m.style.left = Math.min(e.clientX / k, innerWidth / k - m.offsetWidth - 8) + "px"; m.style.top = Math.min(e.clientY / k, innerHeight / k - m.offsetHeight - 8) + "px";
    m.onclick = ev => {
      const a = ev.target.closest("a"); if (!a) return; m.remove();
      if (a.dataset.a === "song") e2MusicPicker(+song.dataset.song);
      else if (a.dataset.a === "whole") e2MusicPicker(-1);
      else { E2.tab = "captions"; e2Pane(); }
    };
    setTimeout(() => document.addEventListener("click", function off() { m.remove(); document.removeEventListener("click", off); }), 0);
  };
  // the timeline is for seeing the edit (user 2026-10-29: "have the AI do all the heavy lifting"): no split / delete /
  // drag-and-drop; click or drag anywhere to move the red line (scrub), it follows the mouse at once
  rows.onmousedown = e => {
    if (e.button !== 0 || !v || !e.target.closest(".e2-scroll")) return;
    e.preventDefault(); E2.scrub = { x0: e.clientX, moved: false }; e2ScrubTo(tAt(e.clientX));
  };
  // seek bar under the video (every view, also Words / Watch where the timeline is hidden): hover shows the time
  const seek = $("#e2-seek"), sAt = x => { const r = seek.getBoundingClientRect(); return Math.max(0, Math.min(e2Dur(), ((x - r.left) / r.width) * e2Dur())); };
  if (seek) {
    seek.onmousemove = e => { const r = seek.getBoundingClientRect(), tip = $("#e2-seektip"), f = (e.clientX - r.left) / r.width; tip.textContent = fmtT(sAt(e.clientX)); tip.style.left = Math.max(0, Math.min(100, f * 100)) + "%"; };
    seek.onmousedown = e => { if (e.button !== 0 || !v) return; e.preventDefault(); E2.scrub = { x0: e.clientX, moved: false, bar: true }; e2ScrubTo(sAt(e.clientX)); };
    seek.onkeydown = e => { if (!v || (e.key !== "ArrowLeft" && e.key !== "ArrowRight")) return; e.preventDefault(); e.stopPropagation(); v.currentTime = Math.max(0, v.currentTime + (e.key === "ArrowRight" ? 5 : -5)); };
  }
  window.onmousemove = e => { if (E2.scrub) { if (Math.abs(e.clientX - E2.scrub.x0) > 3) E2.scrub.moved = true; e2ScrubTo(E2.scrub.bar ? sAt(e.clientX) : tAt(e.clientX)); } };
  window.onmouseup = () => {
    if (!E2.scrub) return;
    if (E2.scrub.moved) E2.justDragged = true; E2.scrub = null;
    const vv = $("#ed-video"); if (vv && E2.scrubT != null) vv.currentTime = E2.scrubT;
  };
  // keys
  document.onkeydown = e => {
    if (!$(".e2")) return;
    const tag = (e.target.tagName || "").toLowerCase();
    const typing = (tag === "input" && !["checkbox", "radio", "button"].includes(e.target.type)) || tag === "textarea" || tag === "select" || e.target.isContentEditable;
    const ctrl = e.ctrlKey || e.metaKey;
    if (ctrl && ["+", "=", "-", "_", "0"].includes(e.key)) { e.preventDefault(); e2Zoom(e.key === "0" ? 0 : e.key === "-" || e.key === "_" ? 1 / 1.5 : 1.5); return; }
    if (ctrl && (e.key === "z" || e.key === "Z") && !typing) { e.preventDefault(); if (e.shiftKey) { if (TX.redo.length) { TX.undo.push(TX.E); TX.E = TX.redo.pop(); txPaint(); txSync("redo"); } } else $("#tx-undo").click(); return; }
    if (ctrl && (e.key === "y" || e.key === "Y") && !typing) { e.preventDefault(); if (TX.redo.length) { TX.undo.push(TX.E); TX.E = TX.redo.pop(); txPaint(); txSync("redo"); } return; }
    if (typing || ctrl) return;
    if (e.key === "Escape") { e2HideBubble(); return; }
    if (e.key === " ") { e.preventDefault(); if (document.activeElement && document.activeElement !== document.body) document.activeElement.blur(); if (v) v.paused ? v.play() : v.pause(); return; }
    if ((e.key === "Delete" || e.key === "Backspace") && E2.wsel) { e.preventDefault(); const s = E2.wsel; e2HideBubble(); txToggle(s.i0, s.i1); return; }
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); if (v) { v.currentTime = Math.max(0, v.currentTime + (e.key === "ArrowRight" ? 5 : -5)); e2Head(); } }
  };
}
// Export pop-up (user 2026-10-29: "let's add some export settings just like Filmora ... an export window that pops up").
// Only real choices: when, which computer, plus what comes out and where. Finals are always full-quality H.264 MP4.
async function e2ExportDialog(p) {
  const K = e2Pending().length;
  const m = modal(`<h2>Export your final video</h2>
    <div class="e2x">
      <div class="e2x-row"><span>Format</span><b>MP4 video (H.264), full quality</b></div>
      <div class="e2x-row"><span>Saved to</span><b class="e2x-path">${esc(p.path)}\\output</b></div>
      ${K ? `<div class="e2x-warn">You have ${K} change${K > 1 ? "s" : ""} that ${K > 1 ? "aren't" : "isn't"} in a draft yet. They won't be in this export. Make a draft first to include ${K > 1 ? "them" : "it"}.</div>` : ""}
      <div class="e2x-row"><span>When</span><div class="e2x-seg" id="e2x-when"><button class="on" data-v="now">Now</button><button data-v="tonight">Tonight</button></div></div>
      <div class="e2x-row" id="e2x-machrow" hidden><span>On</span><select id="e2x-mach"></select></div>
      <p class="muted small" style="margin:4px 0 0">Need it in Premiere or Resolve instead? <a href="#" id="e2x-nle">Export a timeline</a>.</p>
    </div>
    <div class="row" style="gap:8px;justify-content:flex-end;margin-top:14px"><button id="e2x-cancel">Cancel</button><button class="primary" id="e2x-go">Export</button></div>`, "e2x-modal");
  let when = "now";
  $$("#e2x-when button", m).forEach(b => b.onclick = () => { when = b.dataset.v; $$("#e2x-when button", m).forEach(x => x.classList.toggle("on", x === b)); });
  $("#e2x-cancel", m).onclick = closeModal;
  $("#e2x-nle", m).onclick = e => { e.preventDefault(); closeModal(); const it = (window.TL_MORE_ITEMS || []).find(x => /Premiere/.test(x.label)); it && it.run(p); };
  try {   // another computer that can build: only then ask where
    const r = await api("machines"), names = (r.machines || []).map(x => x.name || x).filter(Boolean);
    if (names.length > 1) { $("#e2x-mach", m).innerHTML = names.map(n => `<option ${n === r.default ? "selected" : ""}>${esc(n)}</option>`).join(""); $("#e2x-machrow", m).hidden = false; }
  } catch (e) { /* one computer */ }
  $("#e2x-go", m).onclick = async () => {
    const mach = $("#e2x-machrow", m).hidden ? undefined : $("#e2x-mach", m).value;
    try {
      const r = await api("project/run?id=" + p.id, { action: "final", when, ...(mach ? { machine: mach } : {}) });
      closeModal();
      toast(r.mode === "scheduled" ? "Your final video will be made tonight" : "Making the final video. You get a message when it's ready", "ok");
      await loadProject(); pollJobs(p.id);
    } catch (e) { toast(e.message, "bad"); }
  };
}
// Escape closes whatever is open on top: a pop-up (export, music, settings), the More menu, a right-click menu
// (user 2026-10-29: "I'm pressing escape and it's not letting me close this menu")
document.addEventListener("keydown", e => {
  if (e.key !== "Escape") return;
  const menus = ["#tl-menu", "#e2-ctx", "#e2-pick"].map(s => $(s)).filter(Boolean);
  const mod = document.querySelector(".modal-bg, .modal, #modal");
  if (!menus.length && !mod) return;
  e.preventDefault(); e.stopPropagation();
  menus.forEach(m => m.remove());
  if (mod && !menus.length && typeof closeModal === "function") closeModal();
}, true);
// Space is only ever play / pause in the editor: a focused checkbox or button must not also flip on the key-up
// (user 2026-10-29: Space un-ticked "Show cut words")
document.addEventListener("keyup", e => {
  if (e.key !== " " || !$(".e2")) return;
  const tag = (e.target.tagName || "").toLowerCase();
  if ((tag === "input" && e.target.type !== "checkbox") || tag === "textarea" || e.target.isContentEditable) return;
  e.preventDefault();
}, true);
// scrubbing: move the red line right away, seek the video at most every 60 ms (seeking every mousemove made it lag)
function e2ScrubTo(t) {
  const v = $("#ed-video"); if (!v) return;
  E2.scrubT = t;
  // the line / bar follow the mouse every frame (drawing only, no seeking in the frame)
  if (!E2.scrubRaf) E2.scrubRaf = requestAnimationFrame(() => {
    E2.scrubRaf = 0; const tt = E2.scrubT, s = fmtT(tt), h = $("#e2-head");
    if (h) { h.style.left = e2Pct(tt); $("#e2-bub").textContent = s; }
    $("#e2-now") && ($("#e2-now").textContent = s); $("#e2-seekfill") && ($("#e2-seekfill").style.width = e2Pct(tt));
  });
  // the video seeks only when the last seek finished (queued seeks were the lag), then catches up to the newest spot
  if (v.seeking) { if (!E2.seekWait) { E2.seekWait = true; v.addEventListener("seeked", () => { E2.seekWait = false; if (E2.scrub) e2ScrubTo(E2.scrubT); }, { once: true }); } return; }
  if (Math.abs(v.currentTime - t) > 0.04) { if (v.fastSeek) v.fastSeek(t); else v.currentTime = t; }
}
// playback: follow the words, and skip the parts you cut since this draft (until the next draft cuts them for real)
function e2Tick() {
  cancelAnimationFrame(E2.raf);
  const v = $("#ed-video"); if (!v || v.paused || !document.body.contains(v)) return;
  E2.raf = requestAnimationFrame(e2Tick);
  e2Head(true);   // smooth: every frame, not only on timeupdate
  const raw = tlRawOf(v.currentTime);
  const n = TX.E.find(x => x.kind === "cut" && raw >= x.raw0 && raw < x.raw1 - 0.03 && v.currentTime >= (ED.data.offset || 0));
  if (n) { const to = tlDraftOf(n.raw1); if (to > v.currentTime + 0.05) { v.currentTime = to; return; } }
  if (E2.tab === "words") {
    const ws = ED.data.words; let lo = 0, hi = ws.length - 1, i = -1; while (lo <= hi) { const m = (lo + hi) >> 1; if (ws[m].s <= raw + 0.01) { i = m; lo = m + 1; } else hi = m - 1; }
    if (i !== TX.cur) {
      const tr = $("#ed-tr"), old = tr && $(`.w[data-i="${TX.cur}"]`, tr); if (old) old.classList.remove("now");
      TX.cur = i; const el = tr && $(`.w[data-i="${i}"]`, tr);
      if (el) { el.classList.add("now"); const top = el.offsetTop - tr.offsetTop; if (top < tr.scrollTop + 30 || top > tr.scrollTop + tr.clientHeight - 60) tr.scrollTo({ top: top - tr.clientHeight / 3, behavior: "smooth" }); }
    }
  }
}
function e2WireWords() {
  const tr = $("#ed-tr"); if (!tr) return;
  tr.onclick = e => {
    const w = e.target.closest(".w"); if (!w || E2.wsel) return;
    const v = $("#ed-video"), i = +w.dataset.i; if (!v) return;
    v.currentTime = tlDraftOf(ED.data.words[i].s); e2Head();
  };
  tr.onmouseup = () => setTimeout(() => {
    const s = txSnap(); if (!s) { e2HideBubble(); return; }
    E2.wsel = s;
    const b = $("#e2-bubble"), r = s.els[0].getBoundingClientRect(), host = $(".e2").getBoundingClientRect(), z = parseFloat(document.documentElement.style.zoom) || 1;
    b.style.left = Math.max(8, (r.left - host.left) / z) + "px"; b.style.top = Math.max(8, (r.top - host.top) / z - 58) + "px"; b.classList.add("on");
    const allCut = Array.from({ length: s.i1 - s.i0 + 1 }, (_, k) => txState(s.i0 + k)).every(x => x === "u" || x === "a");
    $("#e2-bcut").disabled = allCut; $("#e2-bback").disabled = !Array.from({ length: s.i1 - s.i0 + 1 }, (_, k) => txState(s.i0 + k)).some(x => x === "u" || x === "a");
  }, 0);
  $("#e2-bcut").onmousedown = e => { e.preventDefault(); const s = E2.wsel; if (!s) return; e2HideBubble(); txApply(txAdd(txSubtract(TX.E, "protect", ...txBounds(s.i0, s.i1)), "cut", ...txBounds(s.i0, s.i1)), "cut"); };
  $("#e2-bback").onmousedown = e => { e.preventDefault(); const s = E2.wsel; if (!s) return; e2HideBubble(); txProtect(s.i0, s.i1); };
}
function e2HideBubble() { E2.wsel = null; const b = $("#e2-bubble"); if (b) b.classList.remove("on"); window.getSelection().removeAllRanges(); }

// ---------------------------------------------------------------- project cards: "AI is working · 42%" (same number as the editor)
const _pcard10 = pcard;
pcard = function (p) {
  const html = _pcard10(p);
  const busy = p.activity || (p.jobs || []).some(j => j.status === "running" || j.status === "queued");
  if (!busy || (p.activity && p.activity.state === "importing")) return html;
  const { s, g } = studioPct(p);
  const strip = `<div class="busy"></div><div class="cardprog e2card"><i style="width:${s}%"></i><span>${g.wait ? "Waiting for its turn" : "AI is working"} · <b>${Math.floor(s)}%</b>${g.eta > 20 ? " · " + fmtEta(g.eta) + " left" : ""}</span></div>`;
  const rx = /<div class="busy"><\/div><div class="cardprog">[\s\S]*?<\/div>(?=<\/div>$)|<div class="cardprog"><i style="width:0%"><\/i>[\s\S]*?<\/div>(?=<\/div>$)/;
  return rx.test(html) ? html.replace(rx, strip) : html.replace(/<\/div>$/, strip + "</div>");   // laptop builds had no strip at all
};

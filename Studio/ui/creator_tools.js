// Creator tools (overnight 2026-10-29, user: "build out new tools that YouTubers would actually benefit from ... speed up
// their work, get video ideas, make their life easier"). Backend = app/creator_tools.py.
// Each tool is a Channel tools tile (a hidden side-nav link, so app9's tiles pick it up) with its own page:
//   What's working (competitor insights, instant), Title Lab, Idea Brainstorm, Comment Miner, Hook Doctor, Repurpose Kit
// Claude tools run as background jobs: the page polls, and every result is kept in History.
(function () {
  const ICON = {
    insights: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/></svg>`,
    planner: `<svg viewBox="0 0 24 24"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>`,
    title_lab: `<svg viewBox="0 0 24 24"><path d="M4 7V4h16v3M9 20h6M12 4v16"/></svg>`,
    brainstorm: `<svg viewBox="0 0 24 24"><path d="M12 2v3M4.2 5.2l2.1 2.1M2 13h3M19 13h3M17.7 7.3l2.1-2.1"/><circle cx="12" cy="14" r="5"/><path d="M10 21h4"/></svg>`,
    comment_miner: `<svg viewBox="0 0 24 24"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.4A8 8 0 1 1 21 12z"/><path d="M8 11h8M8 14h5"/></svg>`,
    hook_doctor: `<svg viewBox="0 0 24 24"><path d="M12 21s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 11c0 5.6-7 10-7 10z"/><path d="M9 12h2l1-2 1 4 1-2h1"/></svg>`,
    thumb_check: `<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="12" rx="2"/><path d="m3 14 5-4 4 3 3-2 6 4M8 21h8"/></svg>`,
    repurpose: `<svg viewBox="0 0 24 24"><path d="M4 9a8 8 0 0 1 14-3l2 2M20 15a8 8 0 0 1-14 3l-2-2"/><path d="M20 4v4h-4M4 20v-4h4"/></svg>`,
    download: `<svg viewBox="0 0 24 24"><path d="M12 3v12M7 10l5 5 5-5M4 19h16"/></svg>`,
  };
  const TOOLS = [
    ["insights", "What's working", "Title words and styles that win in your niche, and topics you haven't made"],
    ["brainstorm", "Idea Brainstorm", "10 video ideas from this month's winners and your own channel"],
    ["planner", "Video Planner", "Idea in, filming plan out: hook, outline, B-roll list, intro voice-over"],
    ["title_lab", "Title Lab", "10 scored titles + thumbnail text for a video"],
    ["thumb_check", "Thumbnail Check", "See your thumbnail in a YouTube feed next to your niche's top videos"],
    ["comment_miner", "Comment Miner", "Paste any video link: what viewers ask for = video ideas"],
    ["hook_doctor", "Hook Doctor", "Grades your first 45 seconds and rewrites the hook"],
    ["repurpose", "Repurpose Kit", "Turns a video into posts, Shorts, chapters and tags"],
    ["download", "Video Downloader", "Save YouTube videos, Shorts and playlists, TikToks and Instagram reels as MP4 or MP3"],
  ];
  window.CT_DESC = Object.fromEntries(TOOLS.map(([k, , d]) => ["ct_" + k, d]));
  // the editor's "More" menu (app9 TL_MORE_ITEMS): run a tool on the project that's open, filled in and started
  window.TL_MORE_ITEMS = window.TL_MORE_ITEMS || [];
  const fromEditor = (tool, pre) => p => { CT.prefill = Object.assign({ project: p.id, autorun: true }, pre ? pre(p) : {}); nav("ct_" + tool); };
  window.TL_MORE_ITEMS.push(
    { label: "Check my hook (Hook Doctor)", run: fromEditor("hook_doctor") },
    { label: "Titles for this video (Title Lab)", run: fromEditor("title_lab", p => ({ topic: p.title, channel: p.channel, autorun: false })) },
    { label: "Posts, Shorts + chapters (Repurpose Kit)", run: fromEditor("repurpose") },
    { label: "Check my thumbnail (Thumbnail Check)", run: fromEditor("thumb_check", p => ({ title: p.title, autorun: false })) },
    { label: "Copy YouTube chapters", run: copyChapters });

  // chapters from the video's own parts (gaming sections / haul + Short parts), in the edited video's time: instant, no AI.
  // YouTube needs the first at 0:00, at least 3, each 10 s or longer
  function copyChapters(p) {
    const d = typeof ED !== "undefined" && ED.data; if (!d) return toast("Open the video in the editor first", "bad");
    const secs = typeof tlSections === "function" ? tlSections() : [];
    const mmss = t => { t = Math.max(0, Math.round(t)); const h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = t % 60; return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s).padStart(2, "0"); };
    // part names are working labels ("? #5 (check start)", "#3 (re-done later)"): drop re-done parts, notes in brackets, "?"
    const clean = n => String(n || "").replace(/\([^)]*\)|\[[^\]]*\]/g, "").replace(/[?]/g, "").replace(/\s+/g, " ").trim().replace(/^./, c => c.toUpperCase());
    let ch = secs.filter(s => !/re-?done|redo|unused|skip/i.test(s.name || "")).map(s => ({ t: tlDraftOf(s.a), name: clean(s.name) }))
      .filter(c => isFinite(c.t) && c.name).sort((a, b) => a.t - b.t);
    if ((d.offset || 0) > 0 || (ch.length && ch[0].t > 1)) ch = [{ t: 0, name: (d.offset || 0) > 0 ? "Intro" : "Start" }, ...ch];
    ch = ch.filter((c, i) => i === 0 || (c.t - ch[i - 1].t >= 10 && c.name.toLowerCase() !== ch[i - 1].name.toLowerCase()));
    if (ch.length < 3) return toast("This video has no parts to make chapters from. Use “Posts, Shorts + chapters” instead (Claude reads the video)", "bad");
    const txt = ch.map(c => `${mmss(c.t)} ${c.name}`).join(String.fromCharCode(10));
    navigator.clipboard.writeText(txt).then(() => toast(`Copied ${ch.length} chapters. Paste them into the YouTube description`, "ok"), () => toast("Couldn't copy", "bad"));
  }
  const CT = { meta: null, poll: null, ins: { niche: localStorage.getItem("ct.niche") || "", days: 90 } };
  const fmtN = n => n == null ? "–" : n >= 1e6 ? (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M" : n >= 1e3 ? (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K" : String(Math.round(n));
  const when = ts => ts ? new Date(ts * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "";
  const copyBtn = text => `<button class="sm ct-copy" data-copy="${esc(text)}" title="Copy">Copy</button>`;

  // ---------------------------------------------------------------- side nav links (hidden; they become Channel tools tiles)
  function addNav() {
    const nv = $("#side nav:not(.nav-foot)"); if (!nv || $('a[data-view="ct_insights"]', nv)) return;
    const after = $('a[data-view="competitors"]', nv) || nv.lastElementChild;
    let at = after;
    TOOLS.forEach(([k, label]) => {
      const a = document.createElement("a"); a.dataset.view = "ct_" + k; a.innerHTML = ICON[k] + label; a.onclick = () => nav("ct_" + k);
      at ? at.insertAdjacentElement("afterend", a) : nv.appendChild(a); at = a;
    });
  }
  addNav();
  new MutationObserver(addNav).observe($("#side"), { childList: true, subtree: true });

  window.ctOpen = (tool, pre) => { CT.prefill = pre || null; nav("ct_" + tool); };
  const _render = render;
  render = async function () {
    if (S.view === "ct_insights") return viewInsights();
    if (S.view === "ct_download") return viewDownload();
    if (S.view && S.view.startsWith("ct_")) return viewTool(S.view.slice(3));
    return _render();
  };
  document.addEventListener("click", e => {
    const b = e.target.closest("[data-copy]"); if (!b) return;
    navigator.clipboard.writeText(b.dataset.copy).then(() => toast("Copied", "ok"), () => toast("Couldn't copy", "bad"));
  });

  async function meta(force) {
    if (!CT.meta || force) CT.meta = await api("tools/meta");
    return CT.meta;
  }
  const head = (k, extra = "") => { const t = TOOLS.find(x => x[0] === k); return `<div class="ct-head"><button class="sm ghost" onclick="nav('tools')">← Channel tools</button><h1>${ICON[k]}${esc(t[1])}</h1><p class="sub">${esc(t[2])}.${extra}</p></div>`; };
  const nicheSel = (m, cur, id = "ct-niche") => `<select id="${id}"><option value="">All niches</option>${m.niches.map(n => `<option ${n === cur ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>`;
  const chanSel = (m, cur) => `<select id="ct-chan"><option value="">Any channel</option>${m.channels.map(n => `<option ${n === cur ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>`;
  const projSel = (m, cur) => `<select id="ct-proj" class="ct-wide"><option value="">Pick a project…</option>${m.projects.filter(p => p.transcript).map(p => `<option value="${esc(p.id)}" ${p.id === cur ? "selected" : ""}>${esc(p.title)}${p.channel ? " · " + esc(p.channel) : ""}</option>`).join("")}</select>`;

  // ---------------------------------------------------------------- What's working (competitor insights)
  async function viewInsights() {
    const main = $("#main");
    main.innerHTML = head("insights") + `<div class="muted">Reading the competitor tracker…</div>`;
    let m, d;
    try { m = await meta(); d = await api(`tools/insights?niche=${enc(CT.ins.niche)}&days=${CT.ins.days}`); }
    catch (e) { main.innerHTML = head("insights") + `<div class="empty">${esc(e.message)}<br>Close and reopen Studio once to turn the creator tools on.</div>`; return; }
    if (S.view !== "ct_insights") return;
    const bar = (v, max) => `<i class="ct-bar"><b style="width:${Math.min(100, Math.round(v / max * 100))}%"></b></i>`;
    const maxW = Math.max(2, ...d.words.map(w => w.lift)), maxS = Math.max(1.5, ...d.styles.map(s => s.lift));
    main.innerHTML = head("insights", ` Based on ${fmtN(d.videos)} videos from ${d.channels_n} channels. "1.8×" = those videos got 1.8 times the views that channel usually gets.`) + `
      <div class="ct-form row"><label>Niche ${nicheSel(m, CT.ins.niche)}</label>
        <label>From the last <select id="ct-days">${[30, 60, 90, 180].map(n => `<option value="${n}" ${n === CT.ins.days ? "selected" : ""}>${n} days</option>`).join("")}</select></label>
        <span class="muted small">Tracker scan: ${esc(when(d.last_scan) || "never")}</span></div>
      <div class="ct-grid2">
        <div class="card"><h2>Title words that win</h2><p class="muted small">Words in titles that beat the channel's usual views (at least 2 channels use them).</p>
          ${d.words.length ? `<table class="ct-tbl">${d.words.map(w => `<tr><td><b>${esc(w.term)}</b></td><td class="ct-num">${w.lift}×</td><td>${bar(w.lift, maxW)}</td><td class="muted small">${w.videos} videos</td></tr>`).join("")}</table>` : `<p class="muted">Not enough videos yet.</p>`}
          ${d.weak.length ? `<h3 class="ct-sub">Words that do worse</h3><p class="ct-chips">${d.weak.map(w => `<span class="pill bad">${esc(w.term)} ${w.lift}×</span>`).join(" ")}</p>` : ""}</div>
        <div class="card"><h2>Title styles</h2><p class="muted small">Compared with titles that don't do it. Above 1× helps, below 1× hurts.</p>
          <table class="ct-tbl">${d.styles.map(s => `<tr><td><b>${esc(s.style)}</b></td><td class="ct-num ${s.lift >= 1.1 ? "ok" : s.lift <= 0.9 ? "bad" : ""}">${s.lift}×</td><td>${bar(s.lift, maxS)}</td><td class="muted small">${Math.round(s.share * 100)}% use it</td></tr>`).join("")}</table></div>
      </div>
      <div class="card"><h2>Winning topics you haven't made</h2><p class="muted small">This month's outliers whose topic isn't in any of your project titles.</p>
        <div class="ct-gaps">${d.gaps.map(g => `<div class="ct-gap"><a href="${esc(g.url)}" target="_blank" style="background-image:url('${esc(g.thumb)}')"><span>${fmtN(g.views)} · ${g.x}×</span></a>
          <div class="ct-gt" title="${esc(g.title)}">${esc(g.title)}</div><div class="muted small">${esc(g.channel)}</div>
          <div class="row" style="gap:6px"><button class="sm" data-gap-title="${esc(g.title)}">Title Lab →</button><button class="sm" data-gap-idea="${esc(g.id)}">→ Ideas</button></div></div>`).join("") || `<p class="muted">Nothing new: you've covered this month's winners.</p>`}</div></div>
      <div class="card"><h2>Channels you track</h2><p class="muted small">"Heating up" = their videos this month get more than their usual views.</p>
        <table class="ct-tbl ct-chan"><tr><th>Channel</th><th>Subscribers</th><th>Usual views</th><th>Uploads (30 d)</th><th>Outliers (30 d)</th><th>Trend</th><th>Last upload</th></tr>
        ${d.channels.map(c => `<tr><td><a href="${esc(c.url)}" target="_blank">${esc(c.name)}</a> <span class="muted small">${esc(c.niche)}</span></td><td>${fmtN(c.subs)}</td><td>${fmtN(c.median)}</td><td>${c.uploads30}</td><td>${c.outliers30 ? `<b class="ok">${c.outliers30}</b>` : "0"}</td>
          <td>${c.trend == null ? `<span class="muted">–</span>` : c.trend >= 1.3 ? `<b class="ok">▲ heating up ${c.trend}×</b>` : c.trend <= 0.7 ? `<span class="bad">▼ cooling ${c.trend}×</span>` : `<span class="muted">steady ${c.trend}×</span>`}</td>
          <td>${c.last_upload_days == null ? "–" : c.last_upload_days < 1 ? "today" : Math.round(c.last_upload_days) + " d ago"}</td></tr>`).join("")}</table></div>`;
    $("#ct-niche").onchange = e => { CT.ins.niche = e.target.value; localStorage.setItem("ct.niche", CT.ins.niche); viewInsights(); };
    $("#ct-days").onchange = e => { CT.ins.days = +e.target.value; viewInsights(); };
    $$("[data-gap-title]").forEach(b => b.onclick = () => { CT.prefill = { topic: b.dataset.gapTitle, niche: CT.ins.niche }; nav("ct_title_lab"); });
    $$("[data-gap-idea]").forEach(b => b.onclick = async () => {
      b.disabled = true; b.textContent = "Adding…";
      try { const r = await api("competitors/idea", { id: b.dataset.gapIdea }); b.textContent = "✓ In Ideas"; toast("Idea added: " + r.idea.title, "ok"); }
      catch (e) { b.disabled = false; b.textContent = "→ Ideas"; toast(e.message, "bad"); }
    });
  }

  // ---------------------------------------------------------------- Claude tools
  function form(k, m, pre) {
    const p = pre || {};
    if (k === "title_lab") return `<label class="ct-wide">What is the video about?<textarea id="ct-topic" rows="2" placeholder="e.g. I bought the cheapest Moncler jacket on DHgate and compared it to the real one">${esc(p.topic || "")}</textarea></label>
      <label>Niche ${nicheSel(m, p.niche || CT.ins.niche)}</label><label>Channel ${chanSel(m, p.channel)}</label>
      <label class="ct-wide">Anything else? <span class="muted small">(optional)</span><input id="ct-notes" value="${esc(p.notes || "")}" placeholder="e.g. it was surprisingly good; price was $45"></label>`;
    if (k === "planner") return `<label class="ct-wide">Video idea or title<textarea id="ct-idea" rows="2" placeholder="e.g. I tested the 5 most viewed DHgate watches">${esc(p.idea || p.topic || "")}</textarea></label>
      <label>Niche ${nicheSel(m, p.niche || CT.ins.niche)}</label><label>Channel ${chanSel(m, p.channel)}</label>
      <label>Length <select id="ct-len">${["under 5 minutes", "5-8 minutes", "8-12 minutes", "15-20 minutes"].map(x => `<option ${x === "8-12 minutes" ? "selected" : ""}>${x}</option>`).join("")}</select></label>
      <label class="ct-wide">Anything else? <span class="muted small">(optional)</span><input id="ct-notes" value="${esc(p.notes || "")}" placeholder="e.g. I have 5 watches here, one is a real Rolex"></label>`;
    if (k === "brainstorm") return `<label>Niche ${nicheSel(m, p.niche || CT.ins.niche)}</label><label>Channel ${chanSel(m, p.channel)}</label>
      <label class="ct-wide">What kind of ideas? <span class="muted small">(optional)</span><input id="ct-notes" value="${esc(p.notes || "")}" placeholder="e.g. cheap to film, under $100 of products"></label>`;
    if (k === "thumb_check") return `<label>Project <select id="ct-tproj"><option value="">Pick a project…</option>${m.projects.filter(x => x.thumbnail).map(x => `<option value="${esc(x.id)}" ${x.id === p.project ? "selected" : ""}>${esc(x.title)}</option>`).join("")}</select></label>
      <div class="ct-drop" id="ct-drop" tabindex="0">or drop a thumbnail image here<br><span class="muted small">PNG / JPG, or click to choose</span><input type="file" id="ct-file" accept="image/png,image/jpeg,image/webp" hidden></div>
      <label class="ct-wide">Title <input id="ct-ttitle" value="${esc(p.title || "")}" placeholder="the video's title"></label>
      <label>Compare with niche ${nicheSel(m, p.niche || CT.ins.niche)}</label>
      <div id="ct-feed" class="ct-wide"></div>`;
    if (k === "comment_miner") return `<label class="ct-wide">YouTube video link <span class="muted small">(yours or a competitor's)</span><input id="ct-url" value="${esc(p.url || "")}" placeholder="https://www.youtube.com/watch?v=…"></label>
      ${(m.my_videos || []).length ? `<div class="ct-wide"><span class="muted small">Your videos:</span> ${m.my_videos.map(v => `<button class="sm" data-myurl="${esc(v.url)}">${esc(v.title)}</button>`).join(" ")}</div>` : ""}`;
    return `<label class="ct-wide">Project ${projSel(m, p.project)}</label>`;
  }
  function readForm(k) {
    const v = id => ($("#" + id) || {}).value || "";
    if (k === "title_lab") return { topic: v("ct-topic").trim(), niche: v("ct-niche"), channel: v("ct-chan"), notes: v("ct-notes").trim() };
    if (k === "brainstorm") return { niche: v("ct-niche"), channel: v("ct-chan"), notes: v("ct-notes").trim() };
    if (k === "planner") return { idea: v("ct-idea").trim(), niche: v("ct-niche"), channel: v("ct-chan"), length: v("ct-len"), notes: v("ct-notes").trim() };
    if (k === "comment_miner") return { url: v("ct-url").trim() };
    if (k === "thumb_check") return { image: CT.thumb || "", title: v("ct-ttitle").trim(), niche: v("ct-niche") };
    return { project: v("ct-proj") };
  }

  async function viewTool(k) {
    const main = $("#main"), t = TOOLS.find(x => x[0] === k); if (!t) { nav("tools"); return; }
    let m; try { m = await meta(); } catch (e) { main.innerHTML = head(k) + `<div class="empty">${esc(e.message)}<br>Close and reopen Studio once to turn the creator tools on.</div>`; return; }
    if (S.view !== "ct_" + k) return;
    const pre = CT.prefill; CT.prefill = null;
    main.innerHTML = head(k) + `<div class="card ct-form">${form(k, m, pre)}<div class="ct-go"><button class="primary big" id="ct-run">${k === "hook_doctor" ? "Check my hook" : k === "repurpose" ? "Make the posts" : k === "comment_miner" ? "Read the comments" : k === "brainstorm" ? "Give me ideas" : k === "thumb_check" ? "Ask Claude what to fix" : k === "planner" ? "Plan my video" : "Write titles"}</button><span class="muted small">Uses Claude, about a minute. You can leave this page; it keeps going.</span></div></div>
      <div id="ct-result"></div><div class="card ct-hist"><h2>History</h2><div id="ct-hist" class="muted small">Loading…</div></div>`;
    $("#ct-run").onclick = async () => {
      const inp = readForm(k);
      try { const r = await api("tools/run", { tool: k, input: inp }); show(k, r.id); history(k); }
      catch (e) { toast(e.message, "bad"); }
    };
    $$("#ct-topic, #ct-url, #ct-notes, #ct-idea").forEach(x => x.onkeydown = e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#ct-run").click(); } });
    history(k);
    if (k === "thumb_check") thumbWire(m, pre || {});
    $$("[data-myurl]").forEach(b => b.onclick = () => { $("#ct-url").value = b.dataset.myurl; $("#ct-run").click(); });
    if (pre && pre.autorun) $("#ct-run").click();
  }

  // ---------------------------------------------------------------- YouTube Downloader (no AI: yt-dlp, user 2026-10-31)
  // MP4 (H.264 first, up to the size picked) or MP3; a playlist link saves every video into a folder named after it
  const DL = { kind: localStorage.getItem("ct.dl.kind") || "mp4", q: localStorage.getItem("ct.dl.q") || "1080" };
  async function viewDownload() {
    const main = $("#main");
    let f = { folder: "" }; try { f = await api("tools/download-folder"); } catch (e) { }
    if (S.view !== "ct_download") return;
    const seg = (name, cur, opts) => `<div class="ct-seg" data-seg="${name}">${opts.map(([v, l]) => `<button class="${v === cur ? "on" : ""}" data-v="${v}">${l}</button>`).join("")}</div>`;
    main.innerHTML = head("download", " For your own videos, or ones you have permission to use.") + `<div class="card ct-form">
      <label class="ct-wide">Link <span class="muted small">(YouTube video, Short or playlist · TikTok · Instagram)</span><input id="dl-url" placeholder="Paste a link here"></label>
      <div class="ct-wide row" style="gap:16px;align-items:flex-end;flex-wrap:wrap">
        <div><div class="muted small">Save as</div>${seg("kind", DL.kind, [["mp4", "MP4 video"], ["mp3", "MP3 audio"]])}</div>
        <div id="dl-qbox" ${DL.kind === "mp3" ? "hidden" : ""}><div class="muted small">Picture size</div>${seg("q", DL.q, [["720", "720p"], ["1080", "1080p"], ["best", "Best (4K)"]])}</div></div>
      <div class="ct-wide row" style="gap:8px;align-items:center"><span class="muted small">Saves to</span><b id="dl-folder">${esc(f.folder)}</b>
        <button class="sm" id="dl-pick">Change…</button><button class="sm" id="dl-open">Open folder</button></div>
      <div class="ct-go"><button class="primary big" id="ct-run">Download</button><span class="muted small">Playlists download every video (you can untick some first). Start as many as you like: they all run at the same time.</span></div></div>
      <div class="card"><h2>Downloads</h2><div id="dl-list" class="muted small">Loading…</div></div>`;
    const url = $("#dl-url");
    url.focus();
    $$("[data-seg]").forEach(g => $$("button", g).forEach(b => b.onclick = () => {
      $$("button", g).forEach(x => x.classList.toggle("on", x === b));
      DL[g.dataset.seg] = b.dataset.v; try { localStorage.setItem("ct.dl." + g.dataset.seg, b.dataset.v); } catch (e) { }
      $("#dl-qbox").hidden = DL.kind === "mp3";
    }));
    $("#dl-pick").onclick = async () => {
      const ps = await browseModal({ dirsOnly: true, start: $("#dl-folder").textContent }); if (!ps.length) return;
      const r = await api("tools/download-folder", { folder: ps[0] }); $("#dl-folder").textContent = r.folder;
    };
    $("#dl-open").onclick = () => api("open", { path: $("#dl-folder").textContent }).catch(e => toast(e.message, "bad"));
    const go = async inp => {
      try { await api("tools/run", { tool: "download", input: inp }); dlList(); }
      catch (e) { toast(e.message, "bad"); }
    };
    $("#ct-run").onclick = async () => {
      const link = url.value.trim(), btn = $("#ct-run");
      if (!/^https?:[/][/]/.test(link)) return toast("Paste a link first", "bad");
      const inp = { url: link, kind: DL.kind, quality: DL.q, folder: $("#dl-folder").textContent };
      btn.disabled = true; btn.textContent = "Checking the link…";
      let pr; try { pr = await api("tools/dl-probe?url=" + enc(link)); } catch (e) { toast(e.message, "bad"); }
      btn.disabled = false; btn.textContent = "Download";
      if (!pr) return;
      url.value = "";
      if (!pr.playlist) return go(inp);
      pickList(pr, inp, go);
    };
    url.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); $("#ct-run").click(); } };
    dlList();
  }

  // a playlist / channel / profile link: every video ticked, untick the ones you don't want
  function pickList(pr, inp, go) {
    const mmss = t => t ? Math.floor(t / 60) + ":" + String(Math.round(t % 60)).padStart(2, "0") : "";
    const m = modal(`<h2>${esc(pr.title)}</h2><p class="muted">${pr.entries.length} videos${pr.entries.length >= 1000 ? " (the first 1000)" : ""}. All of them are ticked: untick any you don't want.</p>
      <div class="row" style="gap:8px;margin-bottom:8px"><button class="sm" id="pl-all">Tick all</button><button class="sm" id="pl-none">Untick all</button><span class="grow"></span><b id="pl-n"></b></div>
      <div class="dl-pick">${pr.entries.map(e => `<label><input type="checkbox" data-n="${e.n}" checked><span class="muted small">${e.n}</span><span class="grow">${esc(e.title)}</span><span class="muted small">${mmss(e.duration)}</span></label>`).join("")}</div>
      <div class="row" style="gap:8px;margin-top:12px;justify-content:flex-end">${pr.this_video ? `<button id="pl-one">Only the video I linked</button>` : ""}<button id="pl-x">Cancel</button><button class="primary" id="pl-go"></button></div>`, "wide");
    const boxes = $$("[data-n]", m);
    const count = () => { const n = boxes.filter(b => b.checked).length; $("#pl-n", m).textContent = `${n} picked`; $("#pl-go", m).textContent = n === boxes.length ? `Download all ${n}` : `Download ${n}`; $("#pl-go", m).disabled = !n; };
    boxes.forEach(b => b.onchange = count); count();
    $("#pl-all", m).onclick = () => { boxes.forEach(b => b.checked = true); count(); };
    $("#pl-none", m).onclick = () => { boxes.forEach(b => b.checked = false); count(); };
    $("#pl-x", m).onclick = closeModal;
    $("#pl-one", m) && ($("#pl-one", m).onclick = () => { closeModal(); go(inp); });
    $("#pl-go", m).onclick = () => {
      const picked = boxes.filter(b => b.checked).map(b => +b.dataset.n);
      closeModal(); go(Object.assign({}, inp, { playlist: true, items: picked.length === boxes.length ? null : picked }));
    };
  }

  // every download, newest first: running ones with their own bar + Cancel, then done / failed ones (polls while any run)
  const SITE = { youtube: "YouTube", tiktok: "TikTok", instagram: "Instagram" };
  CT.dlStopping = new Set();
  // a running download's name, overall %, state + the line under the bar
  function runLive(h) {
    const pg = h.progress || {}, tot = pg.total || 0;
    const pct = tot ? Math.min(100, ((pg.done || 0) + (pg.pct || 0) / 100 * (pg.item > (pg.done || 0) ? 1 : 0)) / tot * 100) : (pg.pct || 0);
    return { name: h.label || "Starting…", pct, state: `Downloading ${Math.round(pct)}%`,
             sub: (tot ? `${pg.done || 0} of ${tot} done · ` : "") + ((h.log || [])[0] || "Starting") };
  }
  async function dlList() {
    clearTimeout(CT.dlPoll);
    const el = $("#dl-list"); if (!el || S.view !== "ct_download") return;
    let r; try { r = await api("tools/history?tool=download"); } catch (e) { el.textContent = e.message; return; }
    if (!$("#dl-list")) return;
    const row = h => {
      const pg = h.progress || {}, what = (h.kind === "mp3" ? "MP3" : "MP4") + (h.files === 1 ? "" : "s");
      const tag = `<span class="pill">${esc(SITE[h.site] || "Link")}</span>`;
      if (h.running) {
        const stop = CT.dlStopping.has(h.id), live = runLive(h);
        return `<div class="dl-row run" data-row="${esc(h.id)}"><div class="dl-top">${tag}<b class="grow dl-name">${esc(live.name)}</b><span class="dl-state">${stop ? "Stopping…" : live.state}</span><button class="sm" data-dlx="${esc(h.id)}" ${stop ? "disabled" : ""}>${stop ? "Stopping…" : "Cancel"}</button></div>
          <i class="dl-bar"><b style="width:${live.pct.toFixed(1)}%"></b></i><div class="muted small dl-sub">${esc(live.sub)}</div></div>`;
      }
      if (h.state === "done") return `<div class="dl-row ok"><div class="dl-top">${tag}<b class="grow">${esc(h.label || "")}</b><span class="dl-state ok">✓ Done · ${h.files} ${what}${h.failed ? ` · ${h.failed} couldn't download` : ""}</span>
          ${h.files === 1 ? `<button class="sm" data-dlplay="${esc(h.first)}">Open</button>` : ""}<button class="sm" data-dlopen="${esc(h.first || h.folder)}">Show in folder</button><button class="ghost sm" data-hdel="${esc(h.id)}" title="Remove from this list (the files stay)">✕</button></div>
          <div class="muted small">${esc(when(h.started))}${h.took ? ` · took ${h.took >= 90 ? Math.round(h.took / 60) + " min" : Math.round(h.took) + " s"}` : ""}</div></div>`;
      const cancelled = /^Cancelled/.test(h.error || "");
      return `<div class="dl-row bad"><div class="dl-top">${tag}<b class="grow">${esc(h.label || "")}</b><span class="dl-state bad">${cancelled ? "Cancelled" : "✗ Didn't work"}</span>
          <button class="sm" data-dlre="${esc(h.id)}">Try again</button><button class="ghost sm" data-hdel="${esc(h.id)}" title="Remove from this list">✕</button></div>
        <div class="small">${esc(h.error || "")}</div>
        ${h.needs_login ? `<div class="row" style="gap:6px;margin-top:6px">${["chrome", "edge", "firefox"].map(b => `<button class="sm" data-dlre="${esc(h.id)}" data-ck="${b}">Try with my ${b[0].toUpperCase() + b.slice(1)} sign-in</button>`).join("")}</div>` : ""}</div>`;
    };
    // 2026-10-31 user: "the cancel button doesn't work": the list was rebuilt every 1.5 s, so the Cancel button was replaced
    // under the mouse and the click got lost. While the same downloads are running, only the bars and words change now.
    const sig = r.items.slice(0, 40).map(h => h.id + (h.running ? "r" : h.state)).join(",");
    if (sig === CT.dlSig && el.querySelector(".dl-row")) {
      r.items.filter(h => h.running).forEach(h => {
        const rw = el.querySelector(`[data-row="${CSS.escape(h.id)}"]`); if (!rw) return;
        const live = runLive(h);
        rw.querySelector(".dl-name").textContent = live.name;
        rw.querySelector(".dl-bar b").style.width = live.pct.toFixed(1) + "%";
        rw.querySelector(".dl-sub").textContent = live.sub;
        if (!CT.dlStopping.has(h.id)) rw.querySelector(".dl-state").textContent = live.state;
      });
      CT.dlPoll = setTimeout(dlList, 1500); return;
    }
    CT.dlSig = sig;
    el.innerHTML = r.items.length ? r.items.slice(0, 40).map(row).join("") : `<p class="muted">Nothing yet. Paste a link above.</p>`;
    $$("[data-dlx]", el).forEach(b => b.onclick = async () => {
      CT.dlStopping.add(b.dataset.dlx); b.disabled = true; b.textContent = "Stopping…";
      b.closest(".dl-row").querySelector(".dl-state").textContent = "Stopping…";
      try { await api("tools/cancel", { id: b.dataset.dlx }); } catch (e) { toast(e.message, "bad"); CT.dlStopping.delete(b.dataset.dlx); }
      dlList();
    });
    $$("[data-dlopen]", el).forEach(b => b.onclick = () => api("open", { path: b.dataset.dlopen, reveal: true }));
    $$("[data-dlplay]", el).forEach(b => b.onclick = () => api("open", { path: b.dataset.dlplay }));
    $$("[data-hdel]", el).forEach(b => b.onclick = async () => { await api("tools/forget", { id: b.dataset.hdel }); dlList(); });
    $$("[data-dlre]", el).forEach(b => b.onclick = async () => {
      const j = await api("tools/job?id=" + enc(b.dataset.dlre)), inp = Object.assign({}, j.input || {});
      delete inp.title; if (b.dataset.ck) inp.cookies = b.dataset.ck;
      await api("tools/forget", { id: b.dataset.dlre });
      try { await api("tools/run", { tool: "download", input: inp }); } catch (e) { toast(e.message, "bad"); }
      dlList();
    });
    if (r.items.some(h => h.running)) CT.dlPoll = setTimeout(dlList, 1500);
  }

  // Thumbnail Check: the feed preview is instant (no AI); the Claude check is the button
  function thumbWire(m, pre) {
    CT.thumb = ""; CT.thumbUrl = "";
    const set = (path, url) => { CT.thumb = path; CT.thumbUrl = url; drawFeed(); };
    const pick = id => { const x = m.projects.find(y => y.id === id); if (!x) return; if (!$("#ct-ttitle").value) $("#ct-ttitle").value = x.title || ""; set(x.thumbnail, mediaUrl(x.thumbnail)); };
    $("#ct-tproj").onchange = e => { $("#ct-ttitle").value = ""; pick(e.target.value); };
    const drop = $("#ct-drop"), file = $("#ct-file");
    const take = f => {
      if (!f || !/^image[/]/.test(f.type)) return toast("Drop a PNG or JPG image", "bad");
      const rd = new FileReader();
      rd.onload = async () => { try { const r = await api("tools/upload", { data: rd.result, name: f.name }); $("#ct-tproj").value = ""; set(r.path, rd.result); } catch (e) { toast(e.message, "bad"); } };
      rd.readAsDataURL(f);
    };
    drop.onclick = () => file.click(); drop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") file.click(); };
    file.onchange = () => take(file.files[0]);
    drop.ondragover = e => { e.preventDefault(); e.stopPropagation(); drop.classList.add("on"); };
    drop.ondragleave = () => drop.classList.remove("on");
    drop.ondrop = e => { e.preventDefault(); e.stopPropagation(); drop.classList.remove("on"); take(e.dataTransfer.files[0]); };
    $("#ct-ttitle").oninput = () => drawFeed();
    $("#ct-niche").onchange = () => drawFeed(true);
    if (pre.project) pick(pre.project); else drawFeed(true);
  }
  async function drawFeed(reload) {
    const el = $("#ct-feed"); if (!el) return;
    if (reload || !CT.feed) { try { CT.feed = (await api("tools/feed?niche=" + enc(($("#ct-niche") || {}).value || ""))).items; } catch (e) { CT.feed = []; } }
    if (!CT.thumbUrl) { el.innerHTML = `<p class="muted">Pick a project or drop an image to see it in a YouTube feed.</p>`; return; }
    const me = { me: true, title: ($("#ct-ttitle") || {}).value || "Your video", channel: "You", thumb: CT.thumbUrl };
    const items = (CT.feed || []).slice(0, 11); items.splice(Math.min(1, items.length), 0, me);
    const card = x => `<div class="ct-fc ${x.me ? "me" : ""}"><div class="ct-fimg" style="background-image:url('${esc(x.thumb)}')"></div><div class="ct-ft">${esc(x.title)}</div><div class="ct-fm">${esc(x.channel)}${x.views ? ` · ${fmtN(x.views)} views` : ""}${x.age != null ? ` · ${Math.max(1, Math.round(x.age))} days ago` : ""}</div></div>`;
    el.innerHTML = `<div class="row" style="gap:10px;align-items:center;margin-bottom:8px"><b>How it looks in a feed</b><span class="muted small">Yours has the blue outline. Can you read it in a second?</span><span class="grow"></span>
      <button class="sm ${CT.phone ? "" : "on"}" data-fsz="0">Computer</button><button class="sm ${CT.phone ? "on" : ""}" data-fsz="1">Phone</button></div>
      <div class="ct-feed ${CT.phone ? "phone" : ""}">${items.map(card).join("")}</div>`;
    $$("[data-fsz]", el).forEach(b => b.onclick = () => { CT.phone = b.dataset.fsz === "1"; drawFeed(); });
  }

  async function history(k) {
    const el = $("#ct-hist"); if (!el) return;
    let r; try { r = await api("tools/history?tool=" + k); } catch (e) { el.textContent = e.message; return; }
    if (!$("#ct-hist")) return;
    el.innerHTML = r.items.length ? r.items.slice(0, 15).map(h => `<div class="ct-hrow"><button class="ghost sm" data-hshow="${esc(h.id)}">${h.running ? "⏳ " : ""}${esc(h.label || h.name)}</button><span class="muted small">${esc(when(h.started))}${h.took ? ` · ${Math.round(h.took)} s` : ""}</span><span class="grow"></span>${h.running ? "" : `<button class="ghost sm" data-hdel="${esc(h.id)}" title="Delete">✕</button>`}</div>`).join("")
      : `<p class="muted">Nothing yet.</p>`;
    $$("[data-hshow]", el).forEach(b => b.onclick = () => show(k, b.dataset.hshow));
    $$("[data-hdel]", el).forEach(b => b.onclick = async () => { await api("tools/forget", { id: b.dataset.hdel }); history(k); });
    const run = r.items.find(h => h.running); if (run && !CT.poll) show(k, run.id);
  }

  async function show(k, id) {
    clearTimeout(CT.poll); CT.poll = null;
    const el = $("#ct-result"); if (!el || S.view !== "ct_" + k) return;
    let j; try { j = await api("tools/job?id=" + enc(id)); } catch (e) { el.innerHTML = `<div class="card bad">${esc(e.message)}</div>`; return; }
    if (j.state === "running") {
      el.innerHTML = `<div class="card ct-wait"><div class="spin"></div><div class="grow"><b>${k === "download" ? "Downloading…" : "Working…"}</b><div class="muted small">${esc((j.log || []).slice(-1)[0] || "Starting")}</div></div>${k === "download" ? `<button class="sm" id="dl-cancel">Cancel</button>` : ""}</div>`;
      $("#dl-cancel") && ($("#dl-cancel").onclick = () => api("tools/cancel", { id }));
      CT.poll = setTimeout(() => show(k, id), 2000); return;
    }
    if (j.state === "error") { el.innerHTML = `<div class="card ct-err"><b>That didn't work.</b> ${esc(j.error)}</div>`; history(k); return; }
    el.innerHTML = `<div class="card ct-res">${RENDER[k](j.result || {}, j)}</div>`;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    $$("[data-lab]", el).forEach(b => b.onclick = () => { CT.prefill = { topic: b.dataset.lab, channel: (j.input || {}).channel, niche: (j.input || {}).niche }; nav("ct_title_lab"); });
    $$("[data-start]", el).forEach(b => b.onclick = () => startFromPlan(j));
    $$("[data-dlopen]", el).forEach(b => b.onclick = () => api("open", { path: b.dataset.dlopen, reveal: true }));
    $$("[data-dlplay]", el).forEach(b => b.onclick = () => api("open", { path: b.dataset.dlplay }));
    $$("[data-plan]", el).forEach(b => b.onclick = () => { CT.prefill = { idea: b.dataset.plan, channel: (j.input || {}).channel, niche: (j.input || {}).niche }; nav("ct_planner"); });
    history(k);
  }

  // Video Planner -> a Studio project (stage Filming) with the plan saved in its folder as "Filming plan.md"
  function startFromPlan(j) {
    const r = j.result || {}, inp = j.input || {}, chans = (S.state.settings || {}).channels || [];
    const ch = chans.find(c => c.name === inp.channel), types = (S.state.types || {});
    const tkeys = Object.keys(types).filter(k => !ch || !(ch.types || []).length || ch.types.includes(k));
    const m = modal(`<h2>Start this video</h2><p class="muted">Makes the project now (stage: Filming) and saves the plan in its folder as “Filming plan.md”. Add your recording later.</p>
      <div class="field"><label>Title</label><input id="sp-t" value="${esc(r.title || inp.idea || "")}"></div>
      <div class="row" style="gap:10px"><div class="field grow"><label>Type</label><select id="sp-type">${(tkeys.length ? tkeys : Object.keys(types)).map(k => `<option value="${esc(k)}">${esc((types[k] || {}).label || k)}</option>`).join("")}</select></div>
      <div class="field grow"><label>Channel</label><select id="sp-ch"><option value="">No channel</option>${chans.map(c => `<option ${c.name === inp.channel ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></div></div>
      <div class="row" style="justify-content:flex-end;gap:8px"><button id="sp-x">Cancel</button><button class="primary" id="sp-go">Make the project</button></div>`);
    $("#sp-x", m).onclick = closeModal;
    $("#sp-go", m).onclick = async () => {
      const title = $("#sp-t", m).value.trim(); if (!title) return toast("Give it a title", "bad");
      try {
        const d = await api("projects", { title, type: $("#sp-type", m).value, channel: $("#sp-ch", m).value, stage: "filming" });
        const pid = d.id || (d.project || {}).id;
        await api("tools/save-plan", { project: pid, job: j.id });
        closeModal(); await refresh(true); toast(`Project made: ${title}. The plan is in its folder`, "ok"); nav("project", pid);
      } catch (e) { toast(e.message, "bad"); }
    };
  }
  const list = (arr, fn) => (arr || []).length ? `<ul class="ct-list">${arr.map(fn).join("")}</ul>` : `<p class="muted">–</p>`;
  const RENDER = {
    planner: (r, j) => `<div class="row" style="gap:10px;align-items:center"><h2 class="grow">${esc(r.title || "")} ${copyBtn(r.title || "")}</h2><button class="primary" data-start="${esc(j.id)}">Start this video →</button></div><p class="muted">${esc(r.promise || "")}</p>
      <div class="ct-grid2"><div><h3 class="ct-sub">Intro voice-over ${copyBtn(r.intro_vo || "")}</h3><p class="ct-pre">${esc(r.intro_vo || "")}</p>
        <h3 class="ct-sub">First words on camera ${copyBtn(r.hook || "")}</h3><p class="ct-pre">${esc(r.hook || "")}</p></div>
      <div><h3 class="ct-sub">Thumbnail moment</h3><p class="ct-pre">${esc(r.thumbnail_moment || "")}</p><h3 class="ct-sub">Tease early, pay off later</h3><p class="ct-pre">${esc(r.open_loop || "")}</p><h3 class="ct-sub">Ending</h3><p class="ct-pre">${esc(r.ending || "")}</p></div></div>
      <h3 class="ct-sub">Outline ${copyBtn((r.outline || []).map(o => `${o.part} (~${o.minutes} min)` + String.fromCharCode(10) + (o.points || []).map(x => "- " + x).join(String.fromCharCode(10))).join(String.fromCharCode(10) + String.fromCharCode(10)))}</h3>
      ${list(r.outline, o => `<li><b>${esc(o.part)}</b> <span class="muted small">~${esc(o.minutes)} min</span><ul class="ct-pts">${(o.points || []).map(x => `<li>${esc(x)}</li>`).join("")}</ul>${o.show ? `<div class="muted small">Show: ${esc(o.show)}</div>` : ""}</li>`)}
      <div class="ct-grid2"><div><h3 class="ct-sub">B-roll to film</h3>${list(r.broll, x => `<li>☐ ${esc(x)}</li>`)}</div><div><h3 class="ct-sub">Before you film</h3>${list(r.checklist, x => `<li>☐ ${esc(x)}</li>`)}</div></div>`,
    thumb_check: r => `<div class="ct-grade"><span class="ct-big g${r.score >= 80 ? "A" : r.score >= 65 ? "B" : r.score >= 50 ? "C" : "D"}">${esc(r.score)}</span><div><p><b>${esc(r.verdict || "")}</b></p><p class="muted">At feed size: ${esc(r.small_size || "")}</p></div></div>
      <div class="ct-grid2"><div><h3 class="ct-sub">What works</h3>${list(r.works, x => `<li>${esc(x)}</li>`)}</div><div><h3 class="ct-sub">What to change</h3>${list(r.fixes, x => `<li><b>${esc(x.fix)}</b><div class="muted small">${esc(x.why || "")}</div></li>`)}</div></div>
      <h3 class="ct-sub">Text ideas</h3><p class="ct-chips">${(r.text_ideas || []).map(x => `<span class="ct-chip">${esc(x)} ${copyBtn(x)}</span>`).join("")}</p>`,
    title_lab: r => `<h2>Titles</h2>${list(r.titles, x => `<li class="ct-title"><span class="ct-score s${Math.round(x.score || 0) >= 8 ? "hi" : Math.round(x.score || 0) >= 6 ? "mid" : "lo"}">${esc(x.score)}</span><div class="grow"><b>${esc(x.title)}</b> <span class="muted small">${esc((x.title || "").length)} letters · ${esc(x.angle || "")}</span><div class="muted small">${esc(x.why || "")}</div></div>${copyBtn(x.title || "")}</li>`)}
      <div class="ct-grid2"><div><h3 class="ct-sub">Thumbnail text</h3><p class="ct-chips">${(r.thumb_text || []).map(x => `<span class="ct-chip">${esc(x)} ${copyBtn(x)}</span>`).join("")}</p></div>
      <div><h3 class="ct-sub">Thumbnail ideas</h3>${list(r.thumb_ideas, x => `<li><b>${esc(x.concept)}</b><div class="muted small">${esc(x.why || "")}</div></li>`)}</div></div>
      ${(r.avoid || []).length ? `<h3 class="ct-sub">Avoid</h3>${list(r.avoid, x => `<li>${esc(x)}</li>`)}` : ""}`,
    brainstorm: r => `<h2>Video ideas</h2>${list(r.ideas, x => `<li class="ct-idea"><div class="grow"><b>${esc(x.title)}</b> <span class="pill">${esc(x.format || "")}</span> <span class="pill">${esc(x.effort || "")} effort</span>
        <div class="small">Opening line: “${esc(x.hook || "")}”</div><div class="muted small">${esc(x.why || "")}</div></div><div class="ct-acts">${copyBtn(x.title || "")}<button class="sm" data-plan="${esc(x.title || "")}">Plan it →</button><button class="sm" data-lab="${esc(x.title || "")}">Title Lab →</button></div></li>`)}`,
    comment_miner: r => { const v = r.video || {}; return `<div class="ct-vid">${v.thumb ? `<a href="${esc(v.url)}" target="_blank"><img src="${esc(v.thumb)}" alt=""></a>` : ""}<div><b>${esc(v.title || "")}</b><div class="muted small">${esc(v.channel || "")} · ${fmtN(v.views)} views · ${v.comments_read || 0} comments read</div><p>${esc(r.summary || "")}</p></div></div>
      <h2>Video ideas from the comments</h2>${list(r.video_ideas, x => `<li class="ct-idea"><div class="grow"><b>${esc(x.title)}</b> <span class="pill">${esc(x.count)} asked</span><div class="small">${esc(x.demand || "")}</div><div class="muted small">“${esc(x.quote || "")}”</div></div><div class="ct-acts">${copyBtn(x.title || "")}<button class="sm" data-plan="${esc(x.title || "")}">Plan it →</button><button class="sm" data-lab="${esc(x.title || "")}">Title Lab →</button></div></li>`)}
      <div class="ct-grid2"><div><h3 class="ct-sub">Questions people ask</h3>${list(r.questions, x => `<li>${esc(x.question)} <span class="muted small">×${esc(x.count)}</span></li>`)}</div>
      <div><h3 class="ct-sub">Complaints</h3>${list(r.complaints, x => `<li>${esc(x.issue)} <span class="muted small">×${esc(x.count)}</span></li>`)}<h3 class="ct-sub">What they loved</h3>${list(r.loved, x => `<li>${esc(x)}</li>`)}</div></div>
      ${(r.reply_to || []).length ? `<h3 class="ct-sub">Worth a reply</h3>${list(r.reply_to, x => `<li>“${esc(x.comment)}” <div class="muted small">${esc(x.why || "")}</div></li>`)}` : ""}`; },
    hook_doctor: r => { const s = r.stats || {}; return `<div class="ct-grade"><span class="ct-big g${esc((r.grade || "C")[0])}">${esc(r.grade || "?")}</span><div><b>${esc((r.project || {}).title || "")}</b><p>${esc(r.verdict || "")}</p>
        <div class="muted small">${s.wpm ? `${s.wpm} words/min · ` : ""}${s.fillers != null ? `${s.fillers} filler words in 45 s · ` : ""}${s.topic_at != null ? `topic first said at ${s.topic_at} s` : "the topic isn't said in the first 45 s"}${r.start_at && r.start_at !== "0:00" ? ` · start at <b>${esc(r.start_at)}</b>` : ""}</div></div></div>
      <div class="ct-grid2"><div><h3 class="ct-sub">What works</h3>${list(r.works, x => `<li>${esc(x)}</li>`)}</div><div><h3 class="ct-sub">Where viewers leave</h3>${list(r.problems, x => `<li><b>${esc(x.at || "")}</b> ${esc(x.issue)}<div class="muted small">Fix: ${esc(x.fix || "")}</div></li>`)}</div></div>
      <h3 class="ct-sub">New hooks, ready to say</h3>${list(r.new_hooks, x => `<li class="ct-title"><div class="grow">“${esc(x)}”</div>${copyBtn(x)}</li>`)}
      ${r.open_loop ? `<h3 class="ct-sub">Tease for later in the video</h3><p>“${esc(r.open_loop)}” ${copyBtn(r.open_loop)}</p>` : ""}`; },
    download: r => `<div class="row" style="gap:10px;align-items:center"><h2 class="grow">✓ ${r.files.length} ${r.kind === "mp3" ? "MP3" : "MP4"} file${r.files.length === 1 ? "" : "s"} saved${r.playlist ? ` · ${esc(r.title || "")}` : ""}</h2>
        <button class="primary" data-dlopen="${esc(r.files[0] || r.folder)}">Show in folder</button></div>
      ${list(r.files.slice(0, 50), x => `<li class="ct-title"><div class="grow">${esc(x.split(/[\\/]/).pop())}</div><button class="sm" data-dlplay="${esc(x)}">Open</button></li>`)}
      ${r.files.length > 50 ? `<p class="muted small">…and ${r.files.length - 50} more</p>` : ""}
      ${(r.failed || []).length ? `<h3 class="ct-sub">Couldn't download ${r.failed.length}</h3>${list(r.failed, x => `<li class="muted small">${esc(x)}</li>`)}` : ""}`,
    repurpose: r => `<div class="muted small" style="margin-bottom:8px">${esc((r.project || {}).title || "")} · ${r.times === "edit" ? "times are in your edited video, after the intro" : "times are in the raw recording"}</div>
      <div class="ct-grid2"><div><h3 class="ct-sub">Community post ${copyBtn(r.community_post || "")}</h3><p class="ct-pre">${esc(r.community_post || "")}</p>
        <h3 class="ct-sub">Pinned comment ${copyBtn(r.pinned_comment || "")}</h3><p class="ct-pre">${esc(r.pinned_comment || "")}</p>
        <h3 class="ct-sub">TikTok caption ${copyBtn(r.tiktok_caption || "")}</h3><p class="ct-pre">${esc(r.tiktok_caption || "")}</p></div>
      <div><h3 class="ct-sub">X thread ${copyBtn((r.x_thread || []).join("\n\n"))}</h3>${list(r.x_thread, x => `<li class="ct-pre">${esc(x)}</li>`)}</div></div>
      <h3 class="ct-sub">Shorts to cut</h3>${list(r.shorts, x => `<li><b>${esc(x.start)}–${esc(x.end)}</b> ${esc(x.title)}<div class="muted small">${esc(x.why || "")}</div></li>`)}
      <div class="ct-grid2"><div><h3 class="ct-sub">Chapters ${copyBtn((r.chapters || []).map(c => `${c.at} ${c.title}`).join("\n"))}</h3><p class="ct-pre">${(r.chapters || []).map(c => `${esc(c.at)} ${esc(c.title)}`).join("<br>")}</p></div>
      <div><h3 class="ct-sub">Tags ${copyBtn((r.tags || []).join(", "))}</h3><p class="ct-chips">${(r.tags || []).map(x => `<span class="pill">${esc(x)}</span>`).join(" ")}</p></div></div>`,
  };
})();

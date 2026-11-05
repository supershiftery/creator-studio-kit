// Train your style (my_style, 2026-10-29): one simple screen to teach the Studio how YOUR videos look, from anything you have
// (finished videos, a raw recording, another editor's Premiere / Final Cut / CapCut project, a clip with a feature you want,
// your logo / opening card / music, videos already made here). Every revision note on a video of that style teaches it more.
// Settings -> "Train your style"; New Project shows each style as a card (app2.js reads window.MY_CARDS).
// Server: app/mystyle.py (+ tools/style_learn.py). Everything lives in <kit>/my_style, which updates never touch.
const MY = { types: [], bases: {}, roles: {}, poll: null };
window.MY_CARDS = {};
const MY_LAYOUT = { "1cam": "1 camera", "2cam": "2 cameras on screen", screen_cam: "screen + camera", vertical: "vertical (9:16)", no_face: "no face (screen / gameplay)", unknown: "not sure" };
const MY_BASE_VT = { talking: "phone", review: "review", phone: "phone", haul: "haul", short: "short", gaming: "gaming" };
const MY_BASE_HINT = { talking: "You talking: vlogs, tech, faith, news", review: "A product on camera", phone: "A phone or app screen", haul: "Lots of products, filmed on a phone", short: "Vertical 9:16 clips", gaming: "Gameplay with your voice" };
const MY_KINDS = { finished: "Finished video in my style", raw: "Raw recording (how I film)", reference: "A feature I want from this video", project: "Editor project file", asset: "My piece (logo, opening, music…)" };

async function myLoad() {
  try {
    const r = await api("mystyle/types");
    MY.types = r.types; MY.bases = r.bases; MY.roles = r.roles || {}; MY.root = r.root;
    window.MY_CARDS = Object.fromEntries(MY.types.map(t => ["my:" + t.slug, {
      id: "my:" + t.slug, slug: t.slug, vtype: MY_BASE_VT[t.base] || "phone", icon: "✨", name: t.name, phrase: `your “${t.name}” style`,
      desc: `Your own style. ${myStyleLine(t)}`, ex: (t.rules || []).length ? `learned ${t.rules.length} thing(s) from your notes` : "learns from every note you give" }]));
  } catch (e) { /* the Studio still works without it */ }
  myCard();
}

function myStyleLine(t) {
  const s = t.style || {}, p = s.pace || {}, bits = [];
  if (s.layout) bits.push(MY_LAYOUT[s.layout] || s.layout);
  if (p.avg_shot_s) bits.push(`a cut every ${p.avg_shot_s} s`);
  if (p.tightness) bits.push(`${p.tightness} pauses`);
  if (s.captions) bits.push(s.captions.on ? "captions" : "no captions");
  if (s.music && s.music.on != null) bits.push(s.music.on ? `music${s.music.mood ? " (" + s.music.mood + ")" : ""}` : "no music");
  return bits.join(" · ");
}

// ---------------------------------------------------------------- Settings card
function myCard() {
  const main = $("#main"); if (!main || S.view !== "settings") return;
  const sig = JSON.stringify(MY.types.map(t => [t.slug, t.name, t.updated, (t.rules || []).length]));
  let c = $("#my-set");
  if (c && c.dataset.sig === sig) return;
  if (!c) {
    c = document.createElement("div"); c.id = "my-set"; c.className = "card"; c.style.marginBottom = "22px";
    const h = main.querySelector("h1"); (h && h.nextElementSibling ? h.nextElementSibling : h || main).after(c);
  }
  c.dataset.sig = sig;
  c.innerHTML = `<div class="row" style="justify-content:space-between"><h2 style="margin:0">Train your style</h2><button class="primary" id="my-new">＋ Make a video type from examples</button></div>
    <p class="small">Show the Studio how <b>your</b> videos look and it edits the same way. Then every note you give on a video teaches it a bit more. Updates never erase what it learned.</p>
    <div class="list">${MY.types.map(t => `<div class="item my-row" data-slug="${esc(t.slug)}" style="cursor:pointer"><span class="t"><b>✨ ${esc(t.name)}</b> <span class="muted tiny">${esc(myStyleLine(t))}</span></span><span class="pill">${(t.rules || []).length} learned</span></div>`).join("") || `<span class="muted small">No styles yet. Train one in about a minute.</span>`}</div>`;
  $("#my-new", c).onclick = () => myTrain();
  $$(".my-row", c).forEach(r => r.onclick = () => myTypeModal(r.dataset.slug));
}

// ---------------------------------------------------------------- one style: what it learned, its rules, its pieces
async function myTypeModal(slug) {
  let t;
  try { t = await api("mystyle/type?slug=" + enc(slug)); } catch (e) { return toast(e.message, "bad"); }
  const s = t.style || {}, p = s.pace || {};
  const row = (k, v) => v == null || v === "" ? "" : `<tr><td class="muted">${esc(k)}</td><td>${esc(v)}</td></tr>`;
  const m = modal(`<h2>✨ ${esc(t.name)}</h2>
    <p class="muted small">Edits like ${esc((MY.bases[t.base] || t.base).toLowerCase())} videos, in your style · learned from ${t.examples || 0} video(s) · keeps learning from your notes</p>
    <div class="np-grid"><div>
      <h3>What it saw in your videos</h3><table class="small">
        ${row("Camera", MY_LAYOUT[s.layout] || s.layout)}${row("Cuts", p.avg_shot_s && `every ${p.avg_shot_s} s on average`)}
        ${row("Pauses", p.tightness && `${p.tightness}${p.median_pause_s ? " (about " + p.median_pause_s + " s)" : ""}`)}
        ${row("Zooms", s.zooms && (s.zooms.on ? "yes" + (s.zooms.note ? " · " + s.zooms.note : "") : "rarely"))}
        ${row("Head turns", ((t.effective || {}).turn_follow || (s.head_turns || {}).follow) === "cut" ? "cuts to the other angle when you turn" : "")}
        ${row("Captions", s.captions && (s.captions.on ? "on" + (s.captions.style ? " (" + s.captions.style + ")" : "") : "off"))}
        ${row("Music", s.music && (s.music.on === false ? "none" : [s.music.mood, s.music.energy && s.music.energy + " energy"].filter(Boolean).join(" · ")))}
        ${row("Text on screen", [s.text_on_screen, s.text_style].filter(Boolean).join(" · "))}${row("Transitions", s.transitions)}${row("Intro", s.intro)}${row("Structure", s.sections)}
      </table>
      <h3 style="margin-top:14px">Your pieces</h3>
      <div class="list" id="my-assets">${(t.assets || []).map(a => `<div class="item"><span class="t">${esc(a.file)}${a.note ? ` <span class="muted tiny">${esc(a.note)}</span>` : ""}</span>
        <select data-role="${esc(a.file)}">${Object.entries(MY.roles).map(([k, v]) => `<option value="${k}" ${k === a.role ? "selected" : ""}>${esc(v)}</option>`).join("")}</select><button class="sm" data-arm="${esc(a.file)}">✕</button></div>`).join("") || `<span class="muted small">None. Add your logo, an opening card or a clip that should be in every video.</span>`}</div>
      <div class="row" style="margin-top:6px"><button class="sm" id="my-asset-add">＋ Add a piece</button></div>
    </div><div>
      <h3>What it has learned from your notes</h3>
      <div class="list" id="my-rules">${(t.rules || []).map(r => `<div class="item"><span class="t" style="white-space:normal">${esc(r.text)}${r.seen > 1 ? ` <span class="muted tiny">said ${r.seen}×</span>` : ""}</span><button class="sm" data-rm="${esc(r.id)}" title="forget this">✕</button></div>`).join("") || `<span class="muted small">Nothing yet. Every note you write on a “${esc(t.name)}” video becomes a rule here, and the next video follows it.</span>`}</div>
      <div class="row" style="margin-top:8px"><input id="my-add" class="grow" placeholder="Tell it something, e.g. “never zoom during the intro”"><button class="sm" id="my-add-go">Add</button></div>
      <details style="margin-top:14px"><summary class="muted small">Advanced: the written playbook</summary>
        <textarea id="my-pb" rows="9" style="width:100%">${esc(t.playbook || "")}</textarea><div class="row"><button class="sm" id="my-pb-save">Save</button></div></details>
    </div></div>
    <div class="row" style="justify-content:space-between;margin-top:14px"><button class="sm" id="my-del">Delete this style</button><span class="row"><button id="my-more">Teach it more</button><button class="primary" id="my-close">Done</button></span></div>`, "wide");
  const again = () => myTypeModal(slug);
  $("#my-close", m).onclick = () => { closeModal(); myLoad(); };
  $("#my-more", m).onclick = () => myTrain(t);
  $$("[data-rm]", m).forEach(b => b.onclick = async () => { try { await api("mystyle/type", { slug, remove_rule: b.dataset.rm }); toast("Forgotten", "ok"); again(); } catch (e) { toast(e.message, "bad"); } });
  $$("[data-arm]", m).forEach(b => b.onclick = async () => { try { await api("mystyle/asset", { slug, remove: b.dataset.arm }); again(); } catch (e) { toast(e.message, "bad"); } });
  $$("[data-role]", m).forEach(sel => sel.onchange = async () => { try { await api("mystyle/asset", { slug, file: sel.dataset.role, role: sel.value }); toast("Saved", "ok"); } catch (e) { toast(e.message, "bad"); } });
  $("#my-asset-add", m).onclick = async () => { const ps = await pickFiles("any", false); if (!ps[0]) return; try { await api("mystyle/asset", { slug, path: ps[0], role: /\.(png|jpe?g|webp)$/i.test(ps[0]) ? "logo" : /\.(mp3|wav|m4a|flac)$/i.test(ps[0]) ? "music" : "start" }); again(); } catch (e) { toast(e.message, "bad"); } };
  $("#my-add-go", m).onclick = async () => { const v = $("#my-add", m).value.trim(); if (!v) return; try { await api("mystyle/type", { slug, add_rule: v }); again(); } catch (e) { toast(e.message, "bad"); } };
  $("#my-pb-save", m).onclick = async () => { try { await api("mystyle/type", { slug, playbook: $("#my-pb", m).value }); toast("Saved", "ok"); } catch (e) { toast(e.message, "bad"); } };
  $("#my-del", m).onclick = async () => { if (!confirm(`Delete the style “${t.name}” and everything it learned? Videos already made keep their settings.`)) return; try { await api("mystyle/type", { slug, delete: true }); closeModal(); toast("Style deleted", "ok"); myLoad(); } catch (e) { toast(e.message, "bad"); } };
}

// ---------------------------------------------------------------- Train (new style, or teach an existing one more)
// 2026-11-04 testers don't know what type of video to pick: one box (links or files), the Studio works out the type and the name.
// opts.onDone(slug): New Project comes back with the new style picked
function myTrain(existing, opts = {}) {
  const items = [], past = new Set(), links = [];
  let base = existing ? existing.base : "auto", pastList = null;
  const bases = { auto: "Work it out for me", ...MY.bases };
  const m = modal(`<h2>${existing ? `Teach “${esc(existing.name)}” more` : "Show it how your videos should look"}</h2>
    <p class="small">Give it examples you like. It studies them and makes a video type just for you. No settings to pick.</p>
    <div class="field"><label for="my-link">Paste a link <span class="muted tiny">(a YouTube playlist, channel or video, a TikTok, an Instagram reel)</span></label>
      <div class="row" style="gap:8px"><input id="my-link" class="grow" placeholder="https://www.youtube.com/playlist?list=…"><button id="my-link-add">Add</button></div></div>
    <div class="field"><label>and / or add files</label>
      <div id="my-drop" tabindex="0" style="border:2px dashed var(--line);border-radius:12px;padding:18px;text-align:center;cursor:pointer">
        <b>Drop files here</b> or click to choose<div class="muted small" style="margin-top:4px">videos · XML, FCPXML or EDL · projects from Premiere, CapCut, Filmora, Kdenlive or Shotcut · your logo or intro</div></div></div>
    <div class="list" id="my-links"></div><div class="list" id="my-items" style="margin-top:6px"></div>
    <details style="margin-top:10px"><summary class="small">More options (not needed)</summary>
      ${existing ? "" : `<div class="field" style="margin-top:8px"><label for="my-name">Name <span class="muted tiny">(blank = it names it)</span></label><input id="my-name" placeholder="e.g. Sunday message, Car vlog"></div>
      <div class="field"><label for="my-base">These videos are closest to</label><select id="my-base">${Object.entries(bases).map(([k, v]) => `<option value="${esc(k)}" ${k === base ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></div>`}
      <div class="field" style="margin-top:8px"><label for="my-wish">Anything it should always do?</label><textarea id="my-wish" rows="2" style="width:100%" placeholder="e.g. Keep it calm. Captions always on. No flashy transitions."></textarea></div>
      <div class="field"><label for="my-open">Start every video with a text card (a verse, a quote, a message)</label><textarea id="my-open" rows="2" style="width:100%" placeholder="e.g. For God so loved the world… - John 3:16"></textarea></div>
      <a id="my-past-open" class="small">Learn from videos you already made in the Studio ▸</a><div id="my-past" class="list" style="display:none;max-height:220px;overflow:auto;margin-top:6px"></div></details>
    <div id="my-prog" style="display:none;margin-top:10px" class="small"></div>
    <div class="row" style="justify-content:flex-end;margin-top:14px"><button id="my-cancel">Cancel</button><button class="primary big" id="my-go">${existing ? "Teach it" : "Make my video type"}</button></div>`, "wide");
  if ($("#my-base", m)) $("#my-base", m).onchange = e => { base = e.target.value; };
  const drawLinks = () => {
    $("#my-links", m).innerHTML = links.map((l, i) => `<div class="item"><span class="t">🔗 ${esc(l.title || l.url)} <span class="muted tiny">${l.list ? `studies the first ${Math.min(5, l.count)} of ${l.count} videos` : "one video"}</span></span><button class="sm" data-lx="${i}" aria-label="Remove">✕</button></div>`).join("");
    $$("[data-lx]", m).forEach(b => b.onclick = () => { links.splice(+b.dataset.lx, 1); drawLinks(); });
  };
  const addLink = async () => {
    const inp = $("#my-link", m), url = inp.value.trim(), btn = $("#my-link-add", m); if (!url) return;
    if (links.some(l => l.url === url)) { inp.value = ""; return; }
    btn.disabled = true; btn.textContent = "Checking…";
    try {
      const r = await api("tools/dl-probe?url=" + enc(url));
      links.push({ url, title: r.playlist ? r.title : "", list: !!r.playlist, count: r.playlist ? r.entries.length : 1 });
      inp.value = ""; drawLinks();
    } catch (e) { toast(e.message, "bad"); }
    btn.disabled = false; btn.textContent = "Add";
  };
  $("#my-link-add", m).onclick = addLink;
  $("#my-link", m).onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); addLink(); } };
  const short = p => String(p).split(/[\\/]/).pop();
  const draw = () => {
    $("#my-items", m).innerHTML = items.map((it, i) => `<div class="item" style="flex-wrap:wrap"><span class="t">${esc(short(it.path))}</span>
      <select data-k="${i}">${Object.entries(MY_KINDS).map(([k, v]) => `<option value="${k}" ${k === it.kind ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
      ${it.kind === "asset" ? `<select data-r="${i}">${Object.entries(MY.roles).map(([k, v]) => `<option value="${k}" ${k === (it.role || "use") ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>` : ""}
      <button class="sm" data-x="${i}">✕</button>
      ${it.warn ? `<div class="small" style="width:100%;color:var(--bad,#ff6b6b)">${esc(it.warn)}</div>` : it.info ? `<div class="muted tiny" style="width:100%">${esc(it.info)}</div>` : ""}
      ${it.kind === "reference" ? `<input data-n="${i}" style="width:100%;margin-top:4px" placeholder="What do you want from this video? e.g. the verse at the start, the zoom on the face" value="${esc(it.note || "")}">` : ""}</div>`).join("");
    $$("[data-k]", m).forEach(s => s.onchange = () => { items[+s.dataset.k].kind = s.value; draw(); });
    $$("[data-r]", m).forEach(s => s.onchange = () => { items[+s.dataset.r].role = s.value; });
    $$("[data-n]", m).forEach(s => s.oninput = () => { items[+s.dataset.n].note = s.value; });
    $$("[data-x]", m).forEach(b => b.onclick = () => { items.splice(+b.dataset.x, 1); draw(); });
  };
  const add = async ps => {
    ps = ps.filter(p => p && !items.some(i => i.path === p)); if (!ps.length) return;
    let g = { items: ps.map(p => ({ path: p, kind: "finished" })) };
    try { g = await api("mystyle/guess", { paths: ps }); } catch (e) { /* keep "finished" */ }
    for (const it of g.items) { if (it.kind === "asset") it.role = /\.(mp3|wav|m4a|flac)$/i.test(it.path) ? "music" : "logo"; items.push(it); }
    draw();
  };
  const dz = $("#my-drop", m);
  dz.onclick = async () => add(await pickFiles("any", true));
  dz.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); dz.click(); } };
  dz.ondragover = e => { e.preventDefault(); dz.style.borderColor = "var(--accent, #3ec6ff)"; };
  dz.ondragleave = () => { dz.style.borderColor = ""; };
  dz.ondrop = e => { e.preventDefault(); dz.style.borderColor = ""; add(dropPaths(e)); };
  $("#my-past-open", m).onclick = async () => {
    const el = $("#my-past", m); el.style.display = el.style.display === "none" ? "" : "none";
    if (pastList) return;
    el.innerHTML = `<span class="muted small">loading…</span>`;
    try { pastList = (await api("mystyle/past")).projects; } catch (e) { pastList = []; }
    el.innerHTML = pastList.map(p => `<label class="item" style="cursor:pointer"><input type="checkbox" data-pid="${esc(p.id)}"> <span class="t">${esc(p.title)} <span class="muted tiny">${esc(p.kind || "")}${p.notes ? ` · ${p.notes} note(s)` : ""}</span></span></label>`).join("") || `<span class="muted small">No finished videos in the Studio yet.</span>`;
    $$("[data-pid]", el).forEach(c => c.onchange = () => c.checked ? past.add(c.dataset.pid) : past.delete(c.dataset.pid));
  };
  $("#my-cancel", m).onclick = () => { closeModal(); if (opts.onCancel) opts.onCancel(); };
  $("#my-go", m).onclick = async () => {
    const name = existing ? existing.name : $("#my-name", m).value.trim();
    if ($("#my-link", m).value.trim()) await addLink();
    const wishes = $("#my-wish", m).value.trim(), opening_text = $("#my-open", m).value.trim();
    if (!items.length && !links.length && !past.size && !wishes && !opening_text) return toast("Give it something to learn from: paste a link or drop a video or project file", "bad");
    const b = $("#my-go", m), again = existing ? "Teach it" : "Make my video type"; b.disabled = true; b.textContent = "Studying…";
    try {
      const r = await api("mystyle/wizard", { name, base, items, links: links.map(l => l.url), past: [...past], wishes, opening_text, slug: existing ? existing.slug : "" });
      const pr = $("#my-prog", m); pr.style.display = "";
      clearInterval(MY.poll);
      MY.poll = setInterval(async () => {
        let s; try { s = await api("mystyle/wizard?job=" + enc(r.job)); } catch (e) { return; }
        pr.innerHTML = `<div class="row"><span class="spin"></span><span>${esc(s.step)}</span><span class="muted">${s.pct || 0}%</span></div><div class="muted tiny">This takes a few minutes. You can close this window: it keeps going.</div>`;
        if (s.state === "done") {
          clearInterval(MY.poll); await myLoad();
          toast(`“${s.name || name}” is ready${s.claude ? "" : " (Claude wasn't reachable: it learned from the numbers only)"}${(s.link_errors || []).length ? `. ${s.link_errors.length} link(s) couldn't be read` : ""}`, "ok");
          if (!pr.isConnected) return;   // they closed it and moved on: don't pop anything over what they're doing
          opts.onDone ? opts.onDone(s.slug) : myTypeModal(s.slug);
        }
        else if (s.state === "failed") { clearInterval(MY.poll); toast(s.step, "bad"); b.disabled = false; b.textContent = again; }
      }, 2000);
    } catch (e) { toast(e.message, "bad"); b.disabled = false; b.textContent = again; }
  };
}

new MutationObserver(() => { if (S.view === "settings" && !$("#my-set")) myCard(); }).observe(document.body, { childList: true, subtree: true });
setTimeout(myLoad, 800);

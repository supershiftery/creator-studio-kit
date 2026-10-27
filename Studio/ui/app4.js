/* {{STUDIO_NAME}} UI, part 4 (2026-10-24): the transcript cutter, rebuilt the way Gling 1.66 does it (studied from its
   shipped source maps: TextEditor/index.tsx, ParagraphActions.tsx, Bubble.tsx, lib/selection.ts, lib/keyboard.ts).
   - Every sentence is a row with a ✂ in the gutter (Gling cuts a whole "take" from its paragraph gutter).
   - Select words: the selection snaps to whole words and a bubble opens; Backspace / Delete / D cuts (uncuts when all
     selected words are already cut). Shift+Backspace cuts the sentence under the playhead.
   - ←/→ word by word, Shift+←/→ sentence by sentence, Space play/pause, Ctrl+Z / Ctrl+Shift+Z undo / redo.
   - Cuts show at once (struck through) and playback hops over them, before any rebuild.
   Each cut is a Studio note (from "editor", recording times), so it is listed in Review + notes and goes into the next
   revision batch; uncut / undo remove or trim those notes. Loaded after app.js, app2.js, app3.js; replaces renderEditor. */

const TX = { E: [], undo: [], redo: [], sents: [], sync: Promise.resolve(), dirty: false, hide: false, preview: true, cur: -1, anchor: -1 };
const R3 = x => Math.round(x * 1000) / 1000;
const txKey = n => `${n.kind}|${R3(n.raw0).toFixed(3)}|${R3(n.raw1).toFixed(3)}`;

// notes the cutter owns: its own cut/protect notes, unless a revision AI is working on them right now
function txEditable(notes) {
  return (notes || []).filter(n => n.from === "editor" && (n.kind === "cut" || n.kind === "protect") && n.raw0 != null && n.status !== "claude" && !n.off)
    .map(n => ({ kind: n.kind, raw0: R3(n.raw0), raw1: R3(n.raw1), text: n.text, nid: n.nid }));
}
function txOtherProtects(notes) {
  return (notes || []).filter(n => n.kind === "protect" && n.raw0 != null && !n.off && !(n.from === "editor" && n.status !== "claude"));
}
function txWordsText(a, b) {
  const ws = ED.data.words.filter(w => (w.s + w.e) / 2 > a && (w.s + w.e) / 2 < b).map(w => w.w).join(" ");
  return ws.length > 60 ? ws.slice(0, 60) + "…" : ws;
}
function txNote(kind, a, b) { a = R3(a); b = R3(b); return { kind, raw0: a, raw1: b, text: `${kind} ${fmtT2(a)}-${fmtT2(b)} “${txWordsText(a, b)}”` }; }

// take [a,b] out of every note of this kind (the parts outside stay as their own notes)
function txSubtract(E, kind, a, b) {
  const out = [];
  for (const n of E) {
    if (n.kind !== kind || n.raw1 <= a || n.raw0 >= b) { out.push(n); continue; }
    if (a - n.raw0 > 0.08) out.push(txNote(kind, n.raw0, a));
    if (n.raw1 - b > 0.08) out.push(txNote(kind, b, n.raw1));
  }
  return out;
}
// add [a,b], merged with touching notes of the same kind so a run of cuts stays one revision
function txAdd(E, kind, a, b) {
  const touch = E.filter(n => n.kind === kind && n.raw0 <= b + 0.25 && n.raw1 >= a - 0.25);
  for (const n of touch) { a = Math.min(a, n.raw0); b = Math.max(b, n.raw1); }
  return [...E.filter(n => !touch.includes(n)), txNote(kind, a, b)];
}

// word state: "u" = you cut it, "a" = the automatic cutter cut it, "p" = put back (protected), "" = kept
function txState(i) {
  const w = ED.data.words[i], m = (w.s + w.e) / 2;
  if (TX.E.some(n => n.kind === "cut" && m > n.raw0 && m < n.raw1)) return "u";
  const prot = TX.E.some(n => n.kind === "protect" && m > n.raw0 && m < n.raw1) || TX.prot.some(n => m > n.raw0 && m < n.raw1);
  if (!txKept(w)) return prot ? "p" : "a";
  return "";
}
// Whisper's word times are loose (top 5 resell: "it." ran 75.66-76.72 while the cutter's edge, placed on the audio, is
// 75.90), so a word's midpoint can sit outside a kept piece it is really in. A word is kept when a real part of it is.
function txKept(w) {
  const keep = ED.data.keep; if (!keep.length) return true;
  if (w.e - w.s < 0.05) { const m = (w.s + w.e) / 2; return keep.some(([a, b]) => m >= a - 0.05 && m <= b + 0.05); }   // Whisper gives some words no length
  let ov = 0;
  for (const [a, b] of keep) if (b > w.s && a < w.e) ov += Math.min(b, w.e) - Math.max(a, w.s);
  return ov >= Math.min(0.12, 0.3 * Math.max(0.01, w.e - w.s));
}
// edges of a word range: from just after the previous word (so the pause before goes too) to just after the last word
function txBounds(i0, i1) {
  const ws = ED.data.words, w0 = ws[i0], w1 = ws[i1], pv = ws[i0 - 1], nx = ws[i1 + 1];
  let a = pv ? (w0.s - pv.e > 0.14 ? Math.max(pv.e + 0.07, w0.s - 0.6) : (pv.e + w0.s) / 2) : Math.max(0, w0.s - 0.05);
  let b = nx ? Math.min(w1.e + 0.04, (w1.e + nx.s) / 2) : w1.e + 0.05;
  return [Math.min(a, w0.s), Math.max(b, w1.e)];
}

function txApply(E, label) {
  TX.undo.push(TX.E); if (TX.undo.length > 200) TX.undo.shift();
  TX.redo = [];
  TX.E = E; txPaint(); txSync(label);
}
function txToggle(i0, i1) {
  if (i0 > i1) [i0, i1] = [i1, i0];
  const idx = []; for (let i = i0; i <= i1; i++) idx.push(i);
  const st = idx.map(txState), [a, b] = txBounds(i0, i1);
  let E = TX.E;
  if (st.every(s => s === "u" || s === "a")) {          // all cut: bring them back
    E = txSubtract(E, "cut", a, b);
    const auto = idx.filter((i, k) => st[k] === "a");
    if (auto.length) { const [pa, pb] = txBounds(auto[0], auto[auto.length - 1]); E = txAdd(E, "protect", pa, pb); }
    txApply(E, `uncut ${idx.length} word${idx.length > 1 ? "s" : ""}`);
  } else {
    E = txSubtract(E, "protect", a, b);
    E = txAdd(E, "cut", a, b);
    txApply(E, `cut ${idx.length} word${idx.length > 1 ? "s" : ""}`);
  }
}
function txProtect(i0, i1) {
  if (i0 > i1) [i0, i1] = [i1, i0];
  const [a, b] = txBounds(i0, i1);
  txApply(txAdd(txSubtract(TX.E, "cut", a, b), "protect", a, b), "protected");
}

// write the cutter's notes to the project: remove what's gone, add what's new (one request per removal, in order)
function txSync(label) {
  TX.dirty = true;
  const pid = S.project.id;
  TX.sync = TX.sync.then(async () => {
    if (!TX.dirty || !S.project || S.project.id !== pid) return;
    TX.dirty = false;
    const want = new Map(TX.E.map(n => [txKey(n), n]));
    const have = txEditable(S.project.notes), haveKeys = new Set(have.map(txKey));
    const gone = have.filter(n => !want.has(txKey(n))).map(n => n.nid);
    const add = [...want.values()].filter(n => !haveKeys.has(txKey(n))).map(n => ({ kind: n.kind, raw0: n.raw0, raw1: n.raw1, text: n.text }));
    if (!gone.length && !add.length) return;
    $("#tx-save") && ($("#tx-save").textContent = "saving…");
    try {
      // the server removes first, then adds, so the new notes ride along with the first removal
      let rest = add;
      for (const nid of gone) {
        const idx = S.project.notes.findIndex(n => n.nid === nid);
        if (idx < 0) continue;
        S.project = await api("project/notes?id=" + pid, { remove: idx, notes: rest });
        rest = [];
      }
      if (rest.length) S.project = await api("project/notes?id=" + pid, { notes: rest });
      if (!TX.dirty) TX.E = txEditable(S.project.notes);   // pick up the note ids
      ED.data.notes = S.project.notes;
      txCount();
    } catch (e) { toast("Could not save the cut: " + e.message, "bad"); }
  });
  if (label) txFlash(label);
}
function txFlash(msg) { const el = $("#tx-flash"); if (!el) return; el.textContent = msg; el.classList.add("on"); clearTimeout(TX.ft); TX.ft = setTimeout(() => el.classList.remove("on"), 1400); }

// ---------------------------------------------------------------- render
function txSentences(words) {
  const out = []; let cur = null;
  words.forEach((w, i) => {
    const pv = words[i - 1], gap = pv ? w.s - pv.e : 99;
    const end = pv && /[.?!…]["”']?$/.test(pv.w);
    if (!cur || end || gap > 0.9) {
      cur = { i0: i, i1: i, para: !pv || gap > 1.6 || (out.length && out[out.length - 1].para0 >= 4 && end) };
      cur.para0 = cur.para ? 0 : (out[out.length - 1].para0 + 1);
      out.push(cur);
    }
    cur.i1 = i;
  });
  return out;
}

async function renderEditor(p) {
  const body = $("#tabbody"); body.innerHTML = `<div class="muted">loading the transcript…</div>`;
  try { ED.data = await api("editor?id=" + p.id); } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  const d = ED.data, outs = d.outputs || [];
  const choices = [...outs.map(o => ({ label: o.kind === "final" ? "Final" : "Draft", sub: base(o.file), file: o.file })), ...(d.source ? [{ label: "Raw recording", sub: base(d.source), file: d.source }] : [])];
  const norm = f => String(f || "").replace(/\//g, "\\").toLowerCase(), home = norm(p.path).replace(/\\?$/, "\\");
  if (!(ED.playing && norm(ED.playing).startsWith(home))) ED.playing = "";
  const files = outs.map(o => o.file), newest = files.length ? files[files.length - 1] : d.source || "";
  if (ED.pid === p.id && ED.seen && files.some(f => !ED.seen.includes(f))) ED.playing = newest;
  if (ED.pid !== p.id) { TX.undo = []; TX.redo = []; }
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
  const dur = d.duration || 1;
  const SEC_COL = ["#5bd97a", "#3ec6ff", "#ffb13d", "#c9a6ff", "#ff6b6b", "#7c9cff", "#5bd9c9", "#ffd166"];
  const secBars = (d.sections || []).map((s, i) => `<div class="tl-sec" style="left:${(s[1] / dur) * 100}%;width:${((s[2] - s[1]) / dur) * 100}%;background:${SEC_COL[i % SEC_COL.length]}" title="${esc(s[0])}"></div>`).join("");
  const keepBars = d.keep.filter(([a]) => a >= 0).map(([a, b]) => `<div class="tl-keep" style="left:${(a / dur) * 100}%;width:${Math.max(0.1, ((b - a) / dur) * 100)}%"></div>`).join("");
  const kept = d.keep.reduce((a, [x, y]) => a + Math.abs(y - x), 0);
  body.innerHTML = `<div class="tx ${TX.hide ? "hide-cuts" : ""}">
    <section class="tx-main">
      <header class="tx-bar">
        <div class="tx-tools">
          <button class="icon" id="tx-undo" title="Undo (Ctrl+Z)">↶</button><button class="icon" id="tx-redo" title="Redo (Ctrl+Shift+Z)">↷</button>
          <span class="sep"></span>
          <label class="tog" title="hide everything that is cut (H)"><input type="checkbox" id="tx-hide" ${TX.hide ? "checked" : ""}><i></i>Hide cuts</label>
          <label class="tog" title="playback jumps over your cuts before the rebuild"><input type="checkbox" id="tx-prev" ${TX.preview ? "checked" : ""}><i></i>Preview</label>
          <button class="ghost sm" id="tx-fill" title="cut every um / uh that has a little air around it">✂ Fillers</button>
          <button class="ghost sm" id="tx-keys" title="keyboard shortcuts">⌨</button>
        </div>
        <span class="grow"></span>
        <a class="tx-count" id="tx-count" title="these cuts are revisions: they apply on the next build">0 cuts</a>
        <span class="tiny muted" id="tx-save"></span>
        <button class="primary sm" id="tx-build" ${p.jobs.length ? "disabled" : ""} title="send the revisions and rebuild the draft">▶ Apply + rebuild</button>
      </header>
      <div class="tx-body" id="ed-tr">${html || `<div class="empty">No transcript yet. Build the draft once (the transcript is the first step).</div>`}</div>
      <div class="tx-bubble" id="tx-bubble"><button class="danger" id="tb-cut">✂ <span>Cut</span> <kbd>⌫</kbd></button><button id="tb-prot" title="keep these words even if the cutter took them out (P)">Keep</button><button id="tb-broll" title="B-roll over these words (B)">B-roll</button><button id="tb-short" title="make a Short from this">Short</button><span class="tb-info" id="tb-info"></span></div>
      <div class="tx-flash" id="tx-flash"></div>
    </section>
    <aside class="tx-side">
      <div class="tx-src"><select id="ed-src">${choices.map(c => `<option value="${esc(c.file)}" ${c.file === ED.playing ? "selected" : ""}>${esc(c.label)} · ${esc(c.sub)}</option>`).join("")}</select></div>
      ${ED.playing ? `<video id="ed-video" controls preload="metadata" src="${mediaUrl(ED.playing)}"></video>` : `<div class="empty">no footage</div>`}
      <div class="tl" id="ed-tl" title="click to seek (recording time)"><div class="tl-secs">${secBars}</div><div class="tl-keeps">${keepBars}</div><div class="tl-notes" id="tx-tlnotes"></div><div class="tl-head" id="ed-head"></div></div>
      <div class="tx-stats"><span id="ed-time">0:00</span><span class="grow"></span><span>recording ${fmtT(dur)} → kept ${fmtT(kept)}</span></div>
      <div class="tx-legend"><span><i class="lg u"></i>your cuts</span><span><i class="lg a"></i>auto-cut</span><span><i class="lg p"></i>kept back</span></div>
      <div class="tx-help" id="tx-help" style="display:none">
        <div><kbd>Space</kbd> play / pause</div><div><kbd>⌫</kbd> <kbd>Del</kbd> <kbd>D</kbd> cut / uncut selection</div>
        <div><kbd>Shift</kbd>+<kbd>⌫</kbd> cut sentence at playhead</div><div><kbd>←</kbd> <kbd>→</kbd> word · <kbd>Shift</kbd> sentence</div>
        <div><kbd>Ctrl</kbd>+<kbd>Z</kbd> undo · <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>Z</kbd> redo</div><div><kbd>P</kbd> keep · <kbd>B</kbd> B-roll · <kbd>H</kbd> hide cuts · <kbd>F</kbd> full screen</div>
      </div>
    </aside></div>`;
  txWire(p);
  txPaint();
}

function txPaint() {
  const tr = $("#ed-tr"); if (!tr || !ED.data) return;
  const st = ED.data.words.map((_, i) => txState(i));
  $$(".w", tr).forEach(el => { const s = st[+el.dataset.i]; el.className = "w" + (s ? " " + (s === "p" ? "p" : "cut " + s) : "") + (+el.dataset.i === TX.cur ? " now" : ""); });
  $$(".snt", tr).forEach(el => {
    const s = TX.sents[+el.dataset.k]; let all = true, any = false;
    for (let i = s.i0; i <= s.i1; i++) { const c = st[i] === "u" || st[i] === "a"; all = all && c; any = any || c; }
    el.classList.toggle("all-cut", all); el.classList.toggle("some-cut", any && !all);
    el.querySelector(".snt-x").title = all ? "Bring this sentence back" : "Cut this whole sentence";
  });
  const dur = ED.data.duration || 1, tn = $("#tx-tlnotes");
  if (tn) tn.innerHTML = TX.E.map(n => `<div class="tl-note ${n.kind}" style="left:${(n.raw0 / dur) * 100}%;width:${Math.max(0.15, ((n.raw1 - n.raw0) / dur) * 100)}%"></div>`).join("");
  txCount();
}
function txCount() {
  const el = $("#tx-count"); if (!el) return;
  const cuts = TX.E.filter(n => n.kind === "cut"), secs = cuts.reduce((a, n) => a + (n.raw1 - n.raw0), 0);
  const pending = txEditable(S.project.notes).filter(n => { const full = S.project.notes.find(x => x.nid === n.nid); return full && !full.done && !full.batch; }).length;
  el.innerHTML = cuts.length ? `<b>${cuts.length}</b> cut${cuts.length > 1 ? "s" : ""} · −${fmtT2(secs)}${pending ? ` · <span class="hl">${pending} new in Revisions</span>` : ""}` : `no cuts yet`;
  $("#tx-undo") && ($("#tx-undo").disabled = !TX.undo.length);
  $("#tx-redo") && ($("#tx-redo").disabled = !TX.redo.length);
  const s = $("#tx-save"); if (s && s.textContent === "saving…") s.textContent = "saved";
}

// ---------------------------------------------------------------- selection (snaps to whole words, like Gling's snapSelectionToWord)
function txSelected() {
  const sel = window.getSelection(), tr = $("#ed-tr");
  if (!sel || sel.isCollapsed || !tr || !sel.rangeCount) return null;
  const r = sel.getRangeAt(0); if (!tr.contains(r.commonAncestorContainer)) return null;
  const ws = $$(".w", tr).filter(el => sel.containsNode(el, true) && el.offsetParent !== null);
  if (!ws.length) return null;
  return { i0: +ws[0].dataset.i, i1: +ws[ws.length - 1].dataset.i, els: ws };
}
function txSnap() {
  const s = txSelected(); if (!s) return null;
  const sel = window.getSelection(), r = document.createRange();
  r.setStartBefore(s.els[0]); r.setEndAfter(s.els[s.els.length - 1]);
  sel.removeAllRanges(); sel.addRange(r);
  return s;
}
function txBubble() {
  const b = $("#tx-bubble"); if (!b) return;
  const s = TX.sel;
  if (!s) { b.classList.remove("on"); return; }
  const allCut = Array.from({ length: s.i1 - s.i0 + 1 }, (_, k) => txState(s.i0 + k)).every(x => x === "u" || x === "a");
  $("#tb-cut span").textContent = allCut ? "Uncut" : "Cut";
  $("#tb-cut").classList.toggle("danger", !allCut);
  const w = ED.data.words;
  $("#tb-info").textContent = `${s.i1 - s.i0 + 1} words · ${(w[s.i1].e - w[s.i0].s).toFixed(1)} s`;
  const rect = s.els[0].getBoundingClientRect(), host = b.parentElement.getBoundingClientRect();
  b.style.left = Math.max(8, Math.min(rect.left - host.left, host.width - 360)) + "px";
  b.style.top = (rect.top - host.top - 44) + "px";
  b.classList.add("on");
}
function txClearSel() { TX.sel = null; window.getSelection().removeAllRanges(); txBubble(); }

// ---------------------------------------------------------------- wiring
function txWire(p) {
  const d = ED.data, v = $("#ed-video"), tr = $("#ed-tr"), dur = d.duration || 1;
  const seekRaw = (t, play = true) => { if (!v) return; v.currentTime = Math.max(0, tOut(t)); if (play) v.play().catch(() => {}); };
  const wordAt = raw => { const ws = d.words; let lo = 0, hi = ws.length - 1, i = -1; while (lo <= hi) { const m = (lo + hi) >> 1; if (ws[m].s <= raw + 0.01) { i = m; lo = m + 1; } else hi = m - 1; } return i; };
  const sentOf = i => TX.sents.findIndex(s => i >= s.i0 && i <= s.i1);
  const here = () => TX.cur >= 0 ? TX.cur : (v ? wordAt(tRaw(v.currentTime) ?? 0) : 0);
  const mark = i => {
    if (i === TX.cur) return;
    const old = $(`.w[data-i="${TX.cur}"]`, tr); if (old) old.classList.remove("now");
    TX.cur = i; const el = $(`.w[data-i="${i}"]`, tr);
    if (el) { el.classList.add("now"); const top = el.offsetTop - tr.offsetTop; if (top < tr.scrollTop + 30 || top > tr.scrollTop + tr.clientHeight - 60) tr.scrollTo({ top: top - tr.clientHeight / 3, behavior: "smooth" }); }
  };
  $("#ed-src").onchange = e => { ED.playing = e.target.value; if (v) { v.src = mediaUrl(ED.playing); v.load(); } };
  $("#tx-build").onclick = async e => {
    await TX.sync;
    withBusy(e.target, "sending…", async () => {
      const r = await api("project/rebuild-notes?id=" + p.id, {});
      toast(r.mode === "claude" ? `Sent with ${r.text_notes} written revision(s) to Claude; you get a message when the draft is ready` : "Rebuilding the draft with your cuts", "ok");
      await loadProject(); pollJobs(p.id);
    });
  };
  $("#tx-count").onclick = () => { S.tab[p.id] = "review"; renderProject(); };
  $("#tx-undo").onclick = () => { if (!TX.undo.length) return; TX.redo.push(TX.E); TX.E = TX.undo.pop(); txPaint(); txSync("undo"); };
  $("#tx-redo").onclick = () => { if (!TX.redo.length) return; TX.undo.push(TX.E); TX.E = TX.redo.pop(); txPaint(); txSync("redo"); };
  $("#tx-hide").onchange = e => { TX.hide = e.target.checked; $(".tx").classList.toggle("hide-cuts", TX.hide); };
  $("#tx-prev").onchange = e => { TX.preview = e.target.checked; };
  $("#tx-keys").onclick = () => { const h = $("#tx-help"); h.style.display = h.style.display === "none" ? "" : "none"; };
  $("#tx-fill").onclick = () => {
    const fn = typeof fillerNotes === "function" ? fillerNotes() : [];
    let E = TX.E, n = 0;
    for (const f of fn) { const m = (f.raw0 + f.raw1) / 2; if (!E.some(x => x.kind === "cut" && m > x.raw0 && m < x.raw1)) { E = txAdd(E, "cut", f.raw0, f.raw1); n++; } }
    if (!n) return toast("No filler words left to cut", "");
    txApply(E, `cut ${n} fillers`);
  };
  $("#ed-tl").onclick = e => { const r = e.currentTarget.getBoundingClientRect(); seekRaw(((e.clientX - r.left) / r.width) * dur); };

  // sentence scissors
  $$(".snt-x", tr).forEach(b => b.onmousedown = e => { e.preventDefault(); e.stopPropagation(); const s = TX.sents[+b.closest(".snt").dataset.k]; txClearSel(); txToggle(s.i0, s.i1); });
  // click a word = seek there; drag = select (snaps to words on mouse up)
  tr.onmouseup = () => setTimeout(() => {
    const s = txSnap();
    if (s) { TX.sel = s; txBubble(); return; }
    TX.sel = null; txBubble();
  }, 0);
  tr.onclick = e => {
    const w = e.target.closest(".w"); if (!w || TX.sel) return;
    const i = +w.dataset.i; mark(i); seekRaw(d.words[i].s, !v || !v.paused || e.detail === 1);
  };
  tr.ondblclick = e => { const w = e.target.closest(".w"); if (!w) return; const s = TX.sents[sentOf(+w.dataset.i)]; const r = document.createRange(); r.setStartBefore($(`.w[data-i="${s.i0}"]`, tr)); r.setEndAfter($(`.w[data-i="${s.i1}"]`, tr)); const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(r); TX.sel = txSelected(); txBubble(); };
  tr.onscroll = () => { if (TX.sel) txBubble(); };
  $("#tb-cut").onmousedown = e => { e.preventDefault(); const s = TX.sel; if (!s) return; txClearSel(); txToggle(s.i0, s.i1); };
  $("#tb-prot").onmousedown = e => { e.preventDefault(); const s = TX.sel; if (!s) return; txClearSel(); txProtect(s.i0, s.i1); };
  $("#tb-broll").onmousedown = async e => {
    e.preventDefault(); const s = TX.sel; if (!s) return;
    const clip = prompt("Which B-roll clip? (part of its file name, or leave empty for the next auto clip)", ""); if (clip === null) return;
    const [a, b] = [d.words[s.i0].s, d.words[s.i1].e]; txClearSel();
    try { S.project = await api("project/notes?id=" + p.id, { kind: "broll", raw0: a, raw1: b, clip, text: `broll ${fmtT2(a)}-${fmtT2(b)} “${txWordsText(a, b)}”` }); ED.data.notes = S.project.notes; txCount(); toast("B-roll added to the revisions", "ok"); } catch (err) { toast(err.message, "bad"); }
  };
  $("#tb-short").onmousedown = e => { e.preventDefault(); const s = TX.sel; if (!s || typeof shortModal !== "function") return; const sel = { s: d.words[s.i0].s, e: d.words[s.i1].e, text: s.els.map(x => x.textContent).join(" ") }; txClearSel(); shortModal(p, sel); };

  // playback: highlight the word being said and hop over cuts (yours always when previewing; the cutter's on the raw file)
  cancelAnimationFrame(TX.raf);
  const tick = () => {
    if (!document.body.contains(v)) return;
    TX.raf = requestAnimationFrame(tick);
    const raw = tRaw(v.currentTime); if (raw == null) return;
    if (!v.paused && TX.preview) {
      const n = TX.E.find(x => x.kind === "cut" && raw >= x.raw0 && raw < x.raw1 - 0.03);
      if (n) { let end = n.raw1; for (const x of TX.E) if (x.kind === "cut" && x.raw0 <= end + 0.05 && x.raw1 > end) end = x.raw1; const o = tOut(end); if (o > v.currentTime + 0.02) { v.currentTime = o; return; } }
      if (ED.playing === d.source && d.keep.length && !inKeep(raw)) { const nk = d.keep.find(([a]) => a > raw); if (!nk) { v.pause(); return; } v.currentTime = nk[0] + 0.01; return; }
    }
    $("#ed-head").style.left = (raw / dur * 100) + "%"; $("#ed-time").textContent = fmtT2(raw);
    if (!v.paused) mark(wordAt(raw));
  };
  if (v) { v.onplay = () => { cancelAnimationFrame(TX.raf); tick(); }; v.onseeked = () => { const raw = tRaw(v.currentTime); if (raw != null) { $("#ed-head").style.left = (raw / dur * 100) + "%"; $("#ed-time").textContent = fmtT2(raw); } }; }
  if (ED.seekTo != null && v) { const t = ED.seekTo; ED.seekTo = null; v.addEventListener("loadedmetadata", () => seekRaw(t), { once: true }); }

  document.onselectionchange = null;
  document.onkeydown = e => {
    if (!$("#ed-tr")) return;
    const tag = (e.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable) return;
    const k = e.key, ctrl = e.ctrlKey || e.metaKey;
    if (k === "Escape") { if (TX.sel) return txClearSel(); if (document.body.classList.contains("edit-full")) document.body.classList.remove("edit-full"); return; }
    if (ctrl && (k === "z" || k === "Z")) { e.preventDefault(); (e.shiftKey ? $("#tx-redo") : $("#tx-undo")).click(); return; }
    if (ctrl && (k === "y" || k === "Y")) { e.preventDefault(); $("#tx-redo").click(); return; }
    if (ctrl) return;
    if (k === "Backspace" || k === "Delete" || k === "d" || k === "D") {
      e.preventDefault();
      if (TX.sel) { const s = TX.sel; txClearSel(); txToggle(s.i0, s.i1); return; }
      if (e.shiftKey || k === "Delete") { const s = TX.sents[sentOf(here())]; if (s) txToggle(s.i0, s.i1); return; }
      const i = here(); if (i >= 0) txToggle(i, i);
      return;
    }
    if (k === " ") { e.preventDefault(); if (v) v.paused ? v.play() : v.pause(); return; }
    if (k === "ArrowRight" || k === "ArrowLeft") {
      e.preventDefault(); txClearSel();
      const dir = k === "ArrowRight" ? 1 : -1;
      let i = here();
      if (e.shiftKey) { const si = Math.max(0, Math.min(TX.sents.length - 1, sentOf(i) + dir)); i = TX.sents[si].i0; }
      else i = Math.max(0, Math.min(d.words.length - 1, i + dir));
      if (TX.hide) while (i > 0 && i < d.words.length - 1 && txState(i) && txState(i) !== "p") i += dir;
      mark(i); seekRaw(d.words[i].s, v && !v.paused);
      return;
    }
    if ((k === "p" || k === "P") && TX.sel) { const s = TX.sel; txClearSel(); txProtect(s.i0, s.i1); return; }
    if ((k === "b" || k === "B") && TX.sel) { $("#tb-broll").dispatchEvent(new MouseEvent("mousedown")); return; }
    if (k === "h" || k === "H") { const c = $("#tx-hide"); c.checked = !c.checked; c.onchange({ target: c }); return; }
    if (k === "f" || k === "F") { document.body.classList.toggle("edit-full"); return; }
    if (k === "j" || k === "J") { if (v) v.currentTime -= 5; return; }
    if (k === "l" || k === "L") { if (v) v.currentTime += 5; return; }
  };
}

// the old filler button lived in the editor's tool row; the new editor has its own (#tx-fill)
editorExtras = function () {};
wireEditor = txWire;

// ---------------------------------------------------------------- redesign (2026-10-24, user: "it feels cluttered")
// Dashboard: what needs you first, then recent work, then the week; empty lists and idle channels stay out of the way.
function viewDashboard() {
  const t = S.state.tracker, P = S.state.projects;
  const hour = new Date().getHours(), hi = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const active = t.channels.filter(c => c.per_week || c.planned || c.in_progress || c.published);
  const idle = t.channels.length - active.length;
  const kpis = active.map(c => {
    const pct = c.per_week ? Math.min(100, (c.published / c.per_week) * 100) : 0;
    return `<div class="kpi"><div class="l">${esc(c.name)}</div><b>${c.published}<span class="of"> / ${c.per_week}</span></b>
      <div class="bar"><i class="${c.published < c.per_week ? "behind" : ""}" style="width:${pct}%"></i></div><div class="l2">${c.planned} planned · ${c.in_progress} in progress</div></div>`;
  }).join("");
  const real = rows => (rows || []).filter(r => !(r.title || "").startsWith("_"));   // test projects ("_remote test ...") out of "Needs you"
  const box = (title, rows, extra, more) => (rows = real(rows)).length ? `<div class="card need"><h3>${title} <span class="n">${rows.length}</span>${more || ""}</h3>${listRows(rows.slice(0, 6), extra)}${rows.length > 6 ? `<div class="muted tiny" style="margin-top:6px">+${rows.length - 6} more</div>` : ""}</div>` : "";
  const needs = [
    box("Drafts to review", t.in_review),
    box("Overdue", t.overdue, r => `<span class="pill bad">${r.days}d late</span>`),
    box("Finals not on Drive", t.ready_to_ship),
    box("Due in 14 days", t.due_soon, r => `<span class="pill">${r.days === 0 ? "today" : "in " + r.days + "d"}</span>`),
    box("Needs a thumbnail", t.needs_thumbnail, null, ` <a data-nav="thumbs" class="tiny">board →</a>`),
    box("Needs a description", t.needs_description),
  ].filter(Boolean).join("");
  return `<div class="pg-head"><div><h1>${hi}</h1><p class="sub">${esc(t.today)} · week ${esc(t.week[0])} → ${esc(t.week[1])}</p></div></div>
    <h2 class="sec-t">Needs you</h2>
    <div class="needs">${needs || `<div class="empty">All caught up. Drop a recording to start the next video.</div>`}</div>
    <div class="sec-row"><h2 class="sec-t">Recent projects</h2><a data-nav="projects">All projects →</a></div>
    <div class="pgrid">${P.filter(p => !(p.title || "").startsWith("_")).slice(0, 8).map(pcard).join("") || `<div class="empty">No projects yet. Click <b>New project</b> or drop a recording in.</div>`}</div>
    <div class="grid dash-split"><div class="card" id="todo-card"><div class="muted">loading to-do…</div></div>
      <div><div class="sec-row" style="margin-top:0"><h2 class="sec-t" style="margin:0">This week</h2>${idle ? `<span class="muted tiny">${idle} channel${idle > 1 ? "s" : ""} with no target hidden</span>` : ""}</div><div class="kpis">${kpis || `<div class="empty">No weekly targets set (Settings → channels)</div>`}</div></div></div>
    <details class="hub-wrap"><summary><span>Everything else</span><span class="muted small">competitors · Minecraft library · realms · watchers · Drive · recordings · intros · music</span><a id="hub-refresh" class="small">refresh</a></summary>
      <div id="hub" class="grid g3"><div class="empty">loading the hub…</div></div></details>`;
}

// project header: Details drawer + ⋯ menu
const _wireProject4 = wireProject;
wireProject = function (p, tab) {
  _wireProject4(p, tab);
  const t = $("#p-det-t"), d = $("#p-details");
  if (t && d) {
    t.classList.toggle("open", !d.hidden);
    t.onclick = () => { d.hidden = !d.hidden; S.det = S.det || {}; S.det[p.id] = !d.hidden; t.classList.toggle("open", !d.hidden); };
  }
  const m = $("#p-more"), menu = $("#p-menu");
  if (m && menu) {
    m.onclick = e => { e.stopPropagation(); menu.classList.toggle("on"); };
    $$("button", menu).forEach(b => b.addEventListener("click", () => menu.classList.remove("on")));
  }
};
document.addEventListener("click", e => { const menu = $("#p-menu"); if (menu && !e.target.closest(".menu-wrap")) menu.classList.remove("on"); });

/* Export to a video editor (2026-10-29, like Gling's export): the editor's "⋯ More" menu -> a timeline file of the current
   cut, linked to the original recording. app/tools/nle_export.py writes it into the project's "Editor export" folder and
   reads it back to check the clips and length. Loaded after app9.js; it only adds an entry to window.TL_MORE_ITEMS.
   Round 1 (user 2026-10-29): Final Cut Pro taken out ("doesn't work"), OTIO / CapCut / Filmora rows gone, and the result is
   just "Done" + how to open it + Show in folder (the clip counts and read-back only show when something is wrong). */
const NLE_FORMATS = [
  ["xml", "Premiere Pro", "In Premiere Pro: File → Import, then pick the file."],
  ["xml", "DaVinci Resolve", "In DaVinci Resolve: File → Import → Timeline, then pick the file."],
  ["xml", "Vegas Pro", "In Vegas Pro: File → Import → Final Cut Pro 7 XML, then pick the file."],
  ["edl", "Other editor", "In your editor: File → Import → EDL. Only the main video comes in (no B-roll or music)."],
];

function nleDialog(p) {
  let pick = Math.min(NLE_FORMATS.length - 1, Math.max(0, +(localStorage.getItem("nle.pick2") || 0)));
  const m = modal(`<h2>Export to another editor</h2>
    <p class="muted small">Get this cut as a timeline you can finish in another editor. Pick yours:</p>
    <div class="nle-picks">${NLE_FORMATS.map((f, i) => `<button class="nle-pick ${i === pick ? "on" : ""}" data-i="${i}">${esc(f[1])}</button>`).join("")}</div>
    <p class="muted tiny">CapCut and Filmora can't open timelines from other apps. DaVinci Resolve is free and can.</p>
    <div id="nle-out"></div>
    <div class="row" style="gap:8px;justify-content:flex-end;margin-top:14px"><button id="nle-cancel">Close</button><button class="primary" id="nle-go">Export</button></div>`, "nle");
  const out = $("#nle-out", m), go = $("#nle-go", m);
  $$(".nle-pick", m).forEach(b => b.onclick = () => {
    pick = +b.dataset.i; try { localStorage.setItem("nle.pick2", pick); } catch (e) { /* private window */ }
    $$(".nle-pick", m).forEach(x => x.classList.toggle("on", x === b)); out.innerHTML = ""; go.hidden = false;
  });
  $("#nle-cancel", m).onclick = closeModal;
  go.onclick = async () => {
    const [key, name, how] = NLE_FORMATS[pick];
    go.disabled = true; out.innerHTML = `<div class="muted small">Making your timeline…</div>`;
    try {
      const r = await api("project/nle-export?id=" + p.id, { format: key });
      const ck = r.check || {};
      out.innerHTML = `<div class="card nle-done">
        <div class="nle-ok">${ck.ok === false ? "⚠ Saved, but check it" : "✓ Done"}</div>
        <p>${esc(how)}</p>
        <p class="muted small">Keep your recording where it is. The timeline uses it.</p>
        ${ck.ok === false ? `<p class="small" style="color:var(--bad)">${esc(ck.error || `It came back with ${ck.clips} clips / ${ck.duration} s instead of ${ck.want_clips} / ${ck.want_duration} s.`)}</p>` : ""}
        <button class="primary" id="nle-show">Show in folder</button></div>`;
      go.hidden = true;
      $("#nle-show", m).onclick = () => api("open", { path: r.file, reveal: true }).catch(e => toast(e.message, "bad"));
    } catch (e) { out.innerHTML = `<div class="card small" style="color:var(--bad)">${esc(e.message.split("\n")[0])}</div>`; }
    go.disabled = false;
  };
}
(function () {
  const st = document.createElement("style");
  st.textContent = `.nle-picks{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:6px 0 8px}
.nle-pick{min-height:44px;border-radius:10px;border:2px solid #2c2f39;background:#1b1d24;color:#f2f3f7;font:inherit;font-weight:600}
.nle-pick.on{border-color:#7fdcf0;background:#123a45}
.nle-done{margin-top:10px}.nle-done p{margin:6px 0}.nle-ok{font-size:18px;font-weight:700;color:var(--ok,#8ff0ae)}`;
  document.head.appendChild(st);
})();

window.TL_MORE_ITEMS = window.TL_MORE_ITEMS || [];
window.TL_MORE_ITEMS.push({ label: "Export to Premiere / Resolve…", run: nleDialog });

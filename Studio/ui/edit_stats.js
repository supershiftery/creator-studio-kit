// Anonymous edit stats: a card in Settings with the on/off switch, what is sent, and "Delete my stats" (server: app/edit_stats.py)
async function esCard() {
  const main = $("#main"); if (!main || S.view !== "settings" || $("#es-card")) return;
  const c = document.createElement("div");
  c.id = "es-card"; c.className = "card"; c.style.marginBottom = "22px";
  const anchor = $("#ku-card") || main.querySelector("h1");
  (anchor || main).after(c);
  let r = {};
  try { r = await api("stats"); } catch (e) { r = { error: e.message }; }
  c.innerHTML = `<h2 style="margin:0 0 6px">Help improve the cutting</h2>
    <p class="small">This beta is free in exchange for anonymous edit stats. When a video is finished, Creator Studio sends
      <b>numbers only</b>: the video type, its length before and after cuts, how many drafts and changes it took, and how long the
      cuts you added or undid were. <b>Never</b> your words, names, files, audio or video.</p>
    <label class="row" style="gap:8px;margin:10px 0"><input type="checkbox" id="es-on" ${r.enabled ? "checked" : ""}> Send anonymous edit stats</label>
    <p class="muted small">Your anonymous id: ${esc(r.install_id || "?")} · ${r.sent || 0} video(s) sent</p>
    <div class="row" style="margin-top:8px"><button class="sm" id="es-del">Delete my stats</button></div>`;
  $("#es-on", c).onchange = async (e) => { await api("stats/set", { enabled: e.target.checked }); toast(e.target.checked ? "Stats on" : "Stats off"); };
  $("#es-del", c).onclick = async () => {
    const d = await api("stats/delete", {});
    toast(d.ok ? `Deleted ${d.deleted} row(s) from the stats server` : d.error, d.ok ? "" : "bad");
  };
}
new MutationObserver(() => { if (S.view === "settings" && !$("#es-card")) esCard(); }).observe(document.body, { childList: true, subtree: true });

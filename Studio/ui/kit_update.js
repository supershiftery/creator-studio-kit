// Kit updates: "Update available" in the sidebar + an Updates card in Settings (server: app/kit_update.py)
const KU = { res: null };

async function kuCheck(force) {
  try { KU.res = await api("kit/update" + (force ? "?force=1" : "")); } catch (e) { KU.res = { error: e.message }; }
  kuBadge(); kuCard();
  return KU.res;
}

function kuBadge() {
  const foot = $(".nav-foot"); if (!foot) return;
  let b = $("#ku-badge");
  if (!KU.res || !KU.res.available) { if (b) b.remove(); return; }
  if (!b) { b = document.createElement("a"); b.id = "ku-badge"; b.className = "ku-badge"; foot.prepend(b); b.onclick = () => nav("settings"); }
  b.innerHTML = `<span class="ku-dot"></span>Update available <b>v${KU.res.latest}</b>`;
}

function kuCard() {
  const main = $("#main"); if (!main || S.view !== "settings") return;
  let c = $("#ku-card");
  if (!c) { c = document.createElement("div"); c.id = "ku-card"; c.className = "card"; c.style.marginBottom = "22px"; const h = main.querySelector("h1"); (h && h.nextElementSibling ? h.nextElementSibling : h || main).after(c); }
  const r = KU.res || {};
  const changes = (r.changes || []).map(x => `<li>${esc(x)}</li>`).join("");
  c.innerHTML = `<div class="row" style="justify-content:space-between"><h2 style="margin:0">Updates</h2>
      <span class="muted small">You have version ${r.current || "?"}${r.released ? " (" + esc(r.released) + ")" : ""}</span></div>
    ${r.error ? `<p class="bad small">${esc(r.error)}</p>` : r.available
      ? `<p><b>Version ${r.latest} is out${r.latest_released ? " (" + esc(r.latest_released) + ")" : ""}.</b> What's new:</p><ul class="small">${changes}</ul>
         <p class="muted small">Updating keeps your settings, channels, codes, projects and taught examples. The Studio closes, updates in its own window (a few minutes) and opens again.</p>`
      : r.latest ? `<p class="muted small">You're up to date.</p>` : `<p class="muted small">Checking…</p>`}
    <div class="row" style="margin-top:10px">${r.available ? `<button class="primary" id="ku-go">Update now</button>` : ""}<button class="sm" id="ku-check">Check again</button></div>`;
  $("#ku-check", c).onclick = () => { c.querySelector(".row:last-child").insertAdjacentHTML("beforeend", `<span class="muted small">checking…</span>`); kuCheck(true); };
  if ($("#ku-go", c)) $("#ku-go", c).onclick = async () => {
    if (!confirm(`Update to version ${r.latest} now? The Studio closes and opens again when it's done.`)) return;
    try {
      const a = await api("kit/update/apply", {});
      if (!a.ok) return toast(a.error, "bad");
      document.body.innerHTML = `<div style="padding:60px;font:16px system-ui;color:#ddd;background:#111;height:100vh">Updating… follow the update window. The Studio opens again when it's done.</div>`;
    } catch (e) { toast(e.message, "bad"); }
  };
}

// the Settings page is redrawn by the app: add the card whenever it shows
new MutationObserver(() => { if (S.view === "settings" && !$("#ku-card")) kuCard(); }).observe(document.body, { childList: true, subtree: true });
setTimeout(() => kuCheck(false), 4000);
setInterval(() => kuCheck(false), 6 * 3600 * 1000);

const kuStyle = document.createElement("style");
kuStyle.textContent = `.ku-badge{display:flex;align-items:center;gap:8px;cursor:pointer;color:#7ee2a8}.ku-badge b{margin-left:auto;font-weight:600}
.ku-dot{width:8px;height:8px;border-radius:50%;background:#3ddc84;box-shadow:0 0 8px #3ddc84}`;
document.head.appendChild(kuStyle);

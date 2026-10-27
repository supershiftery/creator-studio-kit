// Machines + scheduling (2026-10-25, user: "a schedule option inside the studio ... choose what device to schedule it on,
// or build it right now"; "most of the time it's going to be on the laptop"). Adds to the project page a "Build on" picker
// (Laptop / Desktop / Both, saved per project, laptop by default) and a "Schedule…" button; the Queue page gets a
// Scheduled list. The server routes every build (server.pick_machine) and falls back to the other machine when one is off.
(function () {
  const machines = () => {
    const me = S.state?.machine || "Desktop";
    const others = (S.state?.remote?.workers || []).map(w => w.name);
    return [...new Set([me, ...others])];
  };
  const isOn = name => name === (S.state?.machine || "Desktop") || !!(S.state?.remote?.workers || []).find(w => w.name === name && w.ok);
  const current = p => (p.settings && p.settings.machine) || S.state?.default_machine || "Laptop";
  const label = n => n === "Both" ? "Both (laptop first)" : `${n}${isOn(n) ? "" : " (off)"}`;
  const options = (sel, withBoth = true) => [...machines(), ...(withBoth && machines().length > 1 ? ["Both"] : [])]
    .map(n => `<option value="${esc(n)}" ${n.toLowerCase() === String(sel).toLowerCase() ? "selected" : ""}>${esc(label(n))}</option>`).join("");

  function bar(p) {
    const el = document.createElement("div");
    el.className = "row mbar";
    el.style.cssText = "gap:8px;align-items:center;margin:0 0 10px 0;flex-wrap:wrap";
    const gaming = p.type === "gaming";
    el.innerHTML = `<span class="muted small">Build on</span>
      <select class="sm" data-mpick ${gaming ? "disabled title='gaming videos build on the desktop (their assets live there)'" : ""}>${gaming ? `<option>${esc(S.state?.machine || "Desktop")}</option>` : options(current(p))}</select>
      <button class="sm" data-msched title="build it later, on the machine you pick">🕒 Schedule…</button>
      <span class="muted small" data-mnote>${gaming ? "gaming builds here" : (machines().length < 2 ? "" : "falls back to the other machine if this one is off")}</span>`;
    el.querySelector("[data-mpick]").onchange = async e => {
      try { await api("project/update?id=" + p.id, { settings: { machine: e.target.value } }); p.settings = { ...(p.settings || {}), machine: e.target.value }; toast(`Builds of this video now run on ${e.target.value}`, "ok"); }
      catch (err) { toast(err.message, "bad"); }
    };
    el.querySelector("[data-msched]").onclick = () => scheduleModal(p);
    if (machines().length < 2) { el.querySelector("[data-mpick]").style.display = "none"; el.firstElementChild.style.display = "none"; }
    return el;
  }

  function scheduleModal(p) {
    const d = new Date(Date.now() + 60 * 60 * 1000); d.setSeconds(0, 0);
    const pad = n => String(n).padStart(2, "0");
    const val = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    const m = modal(`<h2>Schedule a build</h2><p class="muted small">${esc(p.title)}. It starts on its own at that time. If the machine you pick is off then, the other one builds it.</p>
      <div class="row" style="gap:10px;flex-wrap:wrap;margin:12px 0">
        <label class="small">When <input type="datetime-local" id="sc-at" value="${val}"></label>
        <label class="small">On <select id="sc-m">${options(current(p))}</select></label>
        <label class="small">What <select id="sc-a"><option value="draft">Draft</option><option value="final">Final (full quality)</option></select></label>
      </div><div class="row" style="gap:8px;justify-content:flex-end"><button id="sc-cancel">Cancel</button><button class="primary" id="sc-go">Schedule</button></div>`);
    $("#sc-cancel", m).onclick = closeModal;
    $("#sc-go", m).onclick = async () => {
      try {
        const r = await api("project/schedule?id=" + p.id, { at: $("#sc-at", m).value, machine: $("#sc-m", m).value, action: $("#sc-a", m).value });
        closeModal(); toast(`Scheduled ${r.item.action} on ${r.item.machine} at ${r.item.at}`, "ok"); refresh(true);
      } catch (e) { toast(e.message, "bad"); }
    };
  }

  function scheduledCard() {
    // only what is still coming (user 2026-10-26: finished test runs "done on Laptop" read like upcoming work)
    const items = (S.state?.schedule || []).filter(e => ["pending", "started"].includes(e.state)).slice().sort((a, b) => a.at.localeCompare(b.at));
    const el = document.createElement("div");
    el.className = "card qsched";
    el.style.marginBottom = "14px";
    const st = e => e.state === "pending" ? `<span class="pill act act-waiting">${esc(e.at.slice(11))} · ${esc(e.machine)}</span>`
      : `<span class="pill act">${esc(e.state)}${e.ran_on ? " on " + esc(e.ran_on) : ""}</span>`;
    el.innerHTML = `<div class="row" style="justify-content:space-between;margin-bottom:8px"><h2 style="margin:0">Scheduled <span class="dim small">${items.length}</span></h2><span class="muted small">starts on its own; the other machine takes over if one is off</span></div>` +
      (items.map(e => `<div class="qrow" data-open="${e.project_id}"><div class="qmain"><div class="row" style="gap:6px"><b>${esc(e.title)}</b><span class="muted small">${esc(e.action)} · ${esc(e.at)}</span><span class="grow"></span>${st(e)}${e.state === "pending" ? `<button class="sm" data-scancel="${e.id}">cancel</button>` : ""}</div>${e.note ? `<div class="muted small">${esc(e.note)}</div>` : ""}</div></div>`).join("") || `<div class="empty">nothing scheduled · use 🕒 Schedule… on a video</div>`);
    el.querySelectorAll("[data-scancel]").forEach(b => b.onclick = async ev => {
      ev.stopPropagation();
      try { await api("schedule/cancel", { id: b.dataset.scancel }); await refresh(true); if (S.view === "queue") render(); } catch (e) { toast(e.message, "bad"); }
    });
    el.querySelectorAll("[data-open]").forEach(r => r.onclick = () => nav("project", r.dataset.open));
    return el;
  }

  function decorate() {
    const p = S.project;
    if (S.view === "project" && p) {
      // the Pipeline card (has the force-rebuild box) and the "Not built yet" card (▶ Build draft now)
      const pipe = $("#p-force")?.closest(".card");
      if (pipe && !pipe.querySelector(".mbar")) pipe.children[0].insertAdjacentElement("afterend", bar(p));
      const idle = document.querySelector("[data-rebuild]")?.closest(".prog");
      if (idle && !idle.querySelector(".mbar")) idle.insertAdjacentElement("beforeend", bar(p));
    }
    if (S.view === "queue") {
      const grid = document.querySelector(".qgrid");
      const upcoming = (S.state?.schedule || []).some(e => ["pending", "started"].includes(e.state));
      if (grid && upcoming && !document.querySelector(".qsched")) grid.insertAdjacentElement("beforebegin", scheduledCard());
    }
  }

  new MutationObserver(() => { try { decorate(); } catch (e) { /* never break the page */ } })
    .observe(document.getElementById("main") || document.body, { childList: true, subtree: true });
})();

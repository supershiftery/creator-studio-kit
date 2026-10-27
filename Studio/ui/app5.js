// Player bar for every video in the desktop app (2026-10-25, user: "a button ... to go from 1x 1.5 and 2x, this is easier
// than clicking playback each time; also the +10 seconds and -10 seconds was helpful on mobile so let's add it to the
// desktop app"). Any <video> the app draws gets ⟲10 / 10⟳ and 1× 1.5× 2× right under it; the speed sticks across videos
// and app restarts (localStorage "rate", same key as the phone page).
(function () {
  const RATES = [1, 1.5, 2];
  const getRate = () => { try { return +localStorage.getItem("rate") || 1; } catch (e) { return 1; } };
  const setRate = r => { try { localStorage.setItem("rate", r); } catch (e) {} };

  function paint(bar, r) {
    bar.querySelectorAll("[data-rate]").forEach(b => b.classList.toggle("on", +b.dataset.rate === r));
  }

  function attach(v) {
    if (v.dataset.pbar) return;
    v.dataset.pbar = "1";
    const bar = document.createElement("div");
    bar.className = "pbar";
    bar.innerHTML = `<button class="sm" data-skip="-10" title="back 10 seconds">⟲ 10</button>` +
      `<button class="sm" data-skip="10" title="forward 10 seconds">10 ⟳</button>` +
      `<span class="pbar-seg">${RATES.map(r => `<button class="sm" data-rate="${r}" title="play at ${r}× speed">${r}×</button>`).join("")}</span>`;
    v.insertAdjacentElement("afterend", bar);
    const apply = () => { const r = getRate(); if (v.playbackRate !== r) v.playbackRate = r; v.defaultPlaybackRate = r; paint(bar, r); };
    bar.addEventListener("click", e => {
      const b = e.target.closest("button"); if (!b) return;
      e.preventDefault(); e.stopPropagation();
      if (b.dataset.skip) {
        const d = +b.dataset.skip;
        v.currentTime = Math.min(Math.max(0, v.currentTime + d), isFinite(v.duration) ? v.duration : v.currentTime + d);
      } else if (b.dataset.rate) {
        setRate(+b.dataset.rate);
        document.querySelectorAll("video[data-pbar]").forEach(x => { x.playbackRate = x.defaultPlaybackRate = getRate(); });
        document.querySelectorAll(".pbar").forEach(x => paint(x, getRate()));
      }
    });
    // a new source (switching draft / footage) resets the rate in the browser: put it back
    v.addEventListener("loadedmetadata", apply);
    v.addEventListener("play", apply);
    apply();
  }

  const scan = () => document.querySelectorAll("#main video").forEach(attach);
  new MutationObserver(scan).observe(document.body, { childList: true, subtree: true });
  scan();
})();

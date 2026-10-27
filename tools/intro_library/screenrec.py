"""Real web screen recordings for intros (2026-10-23, ultimate dhgate free reselling spreadsheet, 0:07: "I talk about
influencers putting you on the wrong path. Maybe we could have just put a lot of reseller clips ... grabbed a screen
recording of that. We need to incorporate new types of screen recordings into our videos for the intro ... a lot of real
editors do that"). His published edit of that video (WeYdVk-DqyU) cut YouTube pages and comment sections into the intro.

    record_search(query, out_mp4, seconds=4.0, site="youtube")

Headless Chromium (Playwright) opens the search results, hides every date (upload ages, years and month-day dates in
titles: no dates on screen, ever), waits for the thumbnails, then scrolls smoothly while it records. Output is H.264
1920x1080 30 fps, cached by query in _cache/screenrec/. Returns the mp4 path or None (no network, consent wall, etc.).
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "_cache", "screenrec")

# strip dates from every text node: years, "Oct 12", "12/10/24", "3 days ago"
SANITIZE_JS = r"""
() => {
  const re = /\b(19|20)\d\d\b|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s*\d{1,2}\b|\b\d{1,2}\/\d{1,2}(\/\d{2,4})?\b|\b\d+\s+(second|minute|hour|day|week|month|year)s?\s+ago\b|\bstreamed\b|\b(january|february|march|april|june|july|august|september|october|november|december)\b/gi;
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n; while ((n = walk.nextNode())) { if (re.test(n.nodeValue)) { re.lastIndex = 0; n.nodeValue = n.nodeValue.replace(re, '').replace(/\s{2,}/g, ' '); } re.lastIndex = 0;
    // news-card ages ("Complex · 11y", "1mon", "28d"): a node that is only an age, or an age after a dot separator
    if (/^\s*[·•]?\s*\d+\s?(y|yr|yrs|mo|mon|w|d|h|m)\s*$/.test(n.nodeValue)) n.nodeValue = '';
    n.nodeValue = n.nodeValue.replace(/[·•]\s*\d+\s?(y|yr|yrs|mo|mon|w|d|h|m)\b/g, ''); }
}
"""
# HIS OWN videos never show in a filmed search (dhgae prada glasses 2026-10-26, intro 0:18: the "best prada sunglasses
# dhgate" scroll had our own video ranked #1 right after "these influencers are lying to you"). Every result card whose
# channel name / @handle is one of his (creator_sources.json "own" exact, "own_contains" anywhere in the name) is removed
# from the page before the first frame and again as new results load. Same list as creator_clips.is_own.
OWN_JS = r"""
([own, contains]) => {
  const norm = s => (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  const mine = s => { const n = norm(s); return !!n && (own.includes(n) || contains.some(c => n.includes(c))); };
  const cards = 'ytd-video-renderer, ytd-channel-renderer, ytd-reel-item-renderer, ytd-playlist-renderer, ytd-radio-renderer, '
    + 'ytd-grid-video-renderer, ytd-rich-item-renderer, ytd-shelf-renderer ytd-video-renderer, yt-lockup-view-model, '
    + 'ytm-shorts-lockup-view-model, ytm-shorts-lockup-view-model-v2, ytd-universal-watch-card-renderer, '
    + '[data-e2e="search_top-item"], [data-e2e="search_video-item"], [data-e2e="search-user-container"], [data-e2e="search-card-item"]';
  let hidden = 0;
  for (const c of document.querySelectorAll(cards)) {
    if (c.dataset.ownHidden) continue;
    const names = [];
    for (const el of c.querySelectorAll('#channel-name, ytd-channel-name, #channel-title, .ytd-channel-name, '
        + '[data-e2e*="user-unique-id"], [data-e2e*="author"], [data-e2e="search-card-user-unique-id"], a[href*="/@"], a[href*="/channel/"]')) {
      names.push(el.textContent);
      const h = (el.getAttribute('href') || '').match(/\/@([^/?#]+)/);
      if (h) names.push(decodeURIComponent(h[1]));
    }
    if (names.some(mine)) { c.style.setProperty('display', 'none', 'important'); c.dataset.ownHidden = '1'; hidden++; }
  }
  return hidden;
}
"""


def _own():
    try:
        import json
        d = json.load(open(os.path.join(HERE, "creator_sources.json"), encoding="utf-8"))
        return [re.sub(r"[^a-z0-9]", "", x.lower()) for x in d.get("own", [])], [re.sub(r"[^a-z0-9]", "", x.lower()) for x in d.get("own_contains", [])]
    except (OSError, ValueError):
        return [], ["{{REVIEW_CHANNEL}}", "studio"]


_SHORT_OWNER = {}   # short id -> channel name (YouTube oEmbed), per run


def _short_owner(vid):
    if vid not in _SHORT_OWNER:
        try:
            import json
            import urllib.request
            u = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(f"https://www.youtube.com/shorts/{vid}")
            _SHORT_OWNER[vid] = json.loads(urllib.request.urlopen(u, timeout=6).read()).get("author_name", "")
        except Exception:  # noqa: unknown owner = left alone
            _SHORT_OWNER[vid] = ""
    return _SHORT_OWNER[vid]


def hide_own(pg):
    """-> how many of his own result cards were removed from the page. Shorts cards carry no channel name, so their
    owners come from YouTube's oEmbed (his review Shorts rank for the same searches)."""
    try:
        n = pg.evaluate(OWN_JS, list(_own()))
        ids = pg.evaluate(r"""() => [...new Set([...document.querySelectorAll('a[href*="/shorts/"]')]
            .filter(a => !a.closest('[data-own-hidden]')).map(a => (a.getAttribute('href').match(/shorts\/([\w-]{6,})/) || [])[1]).filter(Boolean))]""")
        own, contains = _own()
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(8) as ex:
            owners = dict(zip(ids, ex.map(_short_owner, ids)))
        mine = [v for v, o in owners.items() if o and (re.sub(r"[^a-z0-9]", "", o.lower()) in own
                                                         or any(c in re.sub(r"[^a-z0-9]", "", o.lower()) for c in contains))]
        if mine:
            n += pg.evaluate("""(ids) => { let k = 0; for (const id of ids) for (const a of document.querySelectorAll(`a[href*="/shorts/${id}"]`)) {
                const c = a.closest('ytm-shorts-lockup-view-model-v2, ytm-shorts-lockup-view-model, ytd-reel-item-renderer, yt-lockup-view-model, ytd-rich-item-renderer') || a;
                if (!c.dataset.ownHidden) { c.style.setProperty('display', 'none', 'important'); c.dataset.ownHidden = '1'; k++; } } return k; }""", mine)
        return n
    except Exception:  # noqa: a page without result cards
        return 0


# upload ages live in their own spans: hide them outright
HIDE_CSS = """
#metadata-line span:nth-of-type(2), .inline-metadata-item:nth-child(2), ytd-video-meta-block #separator,
.badge-shape-wiz--thumbnail-default, tp-yt-paper-dialog, ytd-popup-container, #guide, ytd-mini-guide-renderer,
ytd-ad-slot-renderer, ytd-in-feed-ad-layout-renderer, ytd-promoted-sparkles-web-renderer, ytd-search-pyv-renderer,
ytd-promoted-video-renderer { display: none !important; }
"""
# per-site page setup (dhgate jordan 3 2026-10-23, intro: "there's no 3D motion graphics of like a page scroll or something.
# Go get articles"): StockX search = the resale prices he talks about, Bing News = real headlines about resellers / sell-outs.
# Bing's "Trending now" strip is world news: hidden. Cookie/sign-in pop-ups hidden.
SITES = {
    "youtube": {"url": "https://www.youtube.com/results?search_query=", "wait": "ytd-video-renderer, [data-e2e='search_top-item']",
                "scheme": "dark", "css": HIDE_CSS},
    # YouTube filtered to this month's uploads (top 5 reselling products spring 2026-10-25: "you could filter it to this
    # month ... different searches"): fresh results every time; ages are still stripped from the page
    "youtube_month": {"url": "https://www.youtube.com/results?sp=EgIIBA%253D%253D&search_query=",
                      "wait": "ytd-video-renderer, [data-e2e='search_top-item']", "scheme": "dark", "css": HIDE_CSS},
    "tiktok": {"url": "https://www.tiktok.com/search?q=", "wait": "[data-e2e='search_top-item']", "scheme": "dark", "css": HIDE_CSS},
    "stockx": {"url": "https://stockx.com/search?s=", "wait": "[data-testid='productTile'], img[alt]", "scheme": "light",
               "css": "[role='dialog'], #onetrust-banner-sdk, [data-testid='modal'] { display: none !important; }",
               "scroll": 0.6},
    "bing_news": {"url": "https://www.bing.com/news/search?q=", "wait": ".news-card, .newsitem", "scheme": "light",
                  "scroll": 0.3, "css": "#nttcrsl, .verptob, .trending, .tn_main, #b_header .b_scopebar ~ div[class*='trend'], .cc_overlay, #bnp_container "
                         "{ display: none !important; }", "need": ".news-card, .newsitem", "need_n": 3},
    # any page by URL (ultimate dhgate free reselling spreadsheet 2026-10-23, 0:08: lines about OTHER resellers' bad vendor
    # links show another reseller's site, him scrolling their supplier list, never his own DHgate listings): query = URL,
    # "start" = how far down the page the recording begins
    "page": {"url": "", "wait": "img", "scheme": "light", "scroll": 0.8,
             "css": "[role='dialog'], [aria-modal='true'], #onetrust-banner-sdk, .cookie, [class*='cookie'], [class*='popup'], "
                    "[class*='Popup'], [id*='popup'], [class*='newsletter'], [class*='klaviyo'], .needsclick { display: none !important; }"},
}


# human checks ("Please drag the slider to verify", Alibaba 2026-10-23: the headless recorder filmed the slider page for 4 s).
# A wall is never solved by us: the recording fails, or with verify=True a VISIBLE window opens on the saved profile and HE
# solves it once; the profile (_cache/browser_profile) keeps the pass for later recordings.
WALL_RE = re.compile(r"drag the slider|slide to verify|please slide|captcha|verify (that )?you are (a )?human|are you a robot|"
                     r"unusual traffic|press (&|and) hold|checking your browser|access denied|robot check", re.I)
PROFILE = os.path.join(HERE, "_cache", "browser_profile")
_VERIFY = False


def record_page(url, seconds=4.0, start=0, verify=None):
    """A real scroll through a web page (competitor sites, named sites for intros). Cached like record_search.
    verify: open a visible window when the site shows a human check (default: env SCREENREC_VERIFY=1)."""
    global _VERIFY
    _VERIFY = os.environ.get("SCREENREC_VERIFY") == "1" if verify is None else verify
    return record_search(url + (f"#__start={int(start)}" if start else ""), seconds=seconds, site="page")


def _walled(pg, unknown=False):
    """unknown: the answer while the page is mid-navigation (the text can't be read)."""
    try:
        return bool(WALL_RE.search(pg.evaluate("() => (document.title + ' ' + (document.body ? document.body.innerText : '')).slice(0, 4000)")))
    except Exception:
        return unknown


def _open_page(p, cfg, url, headless):
    """Page recordings run on the saved profile (a solved human check carries over); search recordings stay fresh."""
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    os.makedirs(PROFILE, exist_ok=True)
    ctx = p.chromium.launch_persistent_context(PROFILE, headless=headless, args=["--disable-smooth-scrolling"],
                                               viewport={"width": 1280, "height": 720}, locale="en-US",
                                               color_scheme=cfg["scheme"], user_agent=ua)
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    pg.goto(url, wait_until="domcontentloaded", timeout=30000)
    pg.wait_for_timeout(2000)
    _no_cookie_banner(pg)
    return ctx, pg


# a cookie banner over a store page reads as sloppy (asset-mix test 2026-10-25: Shein home page with "Accept All / Reject
# All" across the middle). Decline it (most privacy-preserving choice), else hide any leftover consent layer.
COOKIE_BTN = r"^\s*(reject all|reject|decline|decline all|necessary only|only necessary|refuse|deny|continue without accepting)\s*$"


def _no_cookie_banner(pg):
    try:
        for frame in [pg.main_frame] + list(pg.main_frame.child_frames):
            # by role, then by visible text: Shein's "Reject All" is a plain div (cmp_c_51), not a button
            done = False
            for btn in (frame.get_by_role("button", name=re.compile(COOKIE_BTN, re.I)), frame.get_by_text(re.compile(COOKIE_BTN, re.I))):
                for k in range(min(btn.count(), 6)):   # the first match can be a hidden copy (Shein has two)
                    try:
                        if btn.nth(k).is_visible():
                            btn.nth(k).click(timeout=1500)
                            pg.wait_for_timeout(600)
                            done = True
                            break
                    except Exception:
                        continue
                if done:
                    break
            if done:
                break
        pg.add_style_tag(content="[id*='onetrust'],[class*='onetrust'],[id*='cookie' i],[class*='cookie-banner' i],"
                                 "[class*='cookieBanner' i],[id*='consent' i],[class*='consent-banner' i],[class*='cmp-' i],[class*='_privacy']"
                                 "{display:none!important}"
                                 # a removed consent modal leaves the page scroll-locked (Shein: the scroll never moved)
                                 "html,body{overflow:auto!important;overflow-y:auto!important;position:static!important}")
        # whatever is left: a fixed / high-z box that talks about cookies is removed (with its dimmed backdrop)
        pg.evaluate("""() => { for (const el of document.querySelectorAll('body *')) {
            const s = getComputedStyle(el);
            // no height test: Shein's fixed _shein_privacy holder is 0 px tall (its box is absolutely positioned inside)
            if ((s.position === 'fixed' || s.position === 'sticky' || +s.zIndex > 999) &&
                /cookie/i.test((el.innerText || el.textContent || '').slice(0, 800))) el.remove(); } }""")
    except Exception:
        pass


def _key(site, query, seconds):
    # v6: frame-by-frame capture (no judder); pages v7: cookie banner declined/hidden (older page files can carry one)
    return hashlib.sha1(f"{'v7' if site == 'page' else 'v6'}|{site}|{query}|{seconds}".encode()).hexdigest()[:12]


# A screen recording is never reused in another video (top 5 products to resell in winter 2024, 2026-10-24, 0:18: "you
# reused this before in a previous video, we can't reuse screen recordings ... we got to remake it"; the YouTube search
# 'best dhgate reselling vendors' and the piaresells.com scroll were the reselling spreadsheet's own cached files).
# _state/screenrec_used.json = cached file -> the first project that used it. With PROJECT set (review_intro does), a file
# owned by another project is re-recorded fresh for this one: its own cache name, and the scroll starts further down the
# page so the viewer sees other results, not the same scroll again.
PROJECT = os.environ.get("SCREENREC_PROJECT", "")
LEDGER = os.path.join(HERE, "_state", "screenrec_used.json")


def _ledger():
    try:
        import json
        return json.load(open(LEDGER, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _claim(path):
    if not PROJECT or not path:
        return
    import json
    led = _ledger()
    if os.path.basename(path) not in led:
        led[os.path.basename(path)] = PROJECT
        os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
        json.dump(led, open(LEDGER, "w", encoding="utf-8"), indent=1)


def used_elsewhere(path):
    """The project that used this cached recording first, when it is not the current one (else "")."""
    owner = _ledger().get(os.path.basename(path or ""), "")
    return owner if owner and PROJECT and owner != PROJECT else ""


def record_search(query, out_mp4=None, seconds=4.0, site="youtube"):
    """site: youtube | tiktok | stockx | bing_news (SITES)."""
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, f"{site}-{re.sub(r'[^a-z0-9]+', '-', query.lower())[:40]}-{_key(site, query, seconds)}.mp4")
    owner = used_elsewhere(cached)
    if owner:
        base, _, frag = query.partition("#__start=")
        query = base + f"#__start={int(frag or 0) + 900}"   # further down: other results / other suppliers
        tag = re.sub(r"[^a-z0-9]+", "-", PROJECT.lower())[:24]
        cached = os.path.join(CACHE, f"{site}-{re.sub(r'[^a-z0-9]+', '-', base.lower())[:40]}-{tag}-{_key(site, query + PROJECT, seconds)}.mp4")
        print(f"screenrec: {base!r} was used in '{owner}': recording a fresh one", file=sys.stderr)
    if not os.path.exists(cached):
        try:
            _record(query, cached, seconds, site)
        except Exception as e:   # no network / page changed: the intro falls back to his own footage
            print(f"screenrec: {query!r} failed ({type(e).__name__}: {str(e)[:120]})", file=sys.stderr)
            return None
    if not os.path.exists(cached):
        return None
    _claim(cached)
    if out_mp4:
        shutil.copy(cached, out_mp4)
        return out_mp4
    return cached


def _record(query, out_mp4, seconds, site):
    from playwright.sync_api import sync_playwright
    cfg = SITES[site]
    query, _, frag = query.partition("#__start=")
    start = int(frag or 0)
    url = query if site == "page" else cfg["url"] + urllib.parse.quote_plus(query)
    tmp = tempfile.mkdtemp(prefix="screenrec_")
    try:
        with sync_playwright() as p:
            # frame-by-frame, not Playwright's live video (ultimate dhgate free reselling spreadsheet 2026-10-23, intro "very
            # shaky"): the live recorder grabbed frames on its own clock, so 15-35 % of the scroll frames were repeats and
            # the page went move-stop-move. Now: smooth scrolling off, one wheel step, one screenshot = one frame.
            b = None
            if site == "page":
                ctx, pg = _open_page(p, cfg, url, headless=True)
                if _walled(pg):
                    ctx.close()
                    if not _VERIFY:
                        raise RuntimeError("human check on the page (run screenrec.py --verify URL and solve it once)")
                    ctx, pg = _open_page(p, cfg, url, headless=False)
                    print(f"screenrec: {url} asks for a human check: solve it in the browser window (3 min)", file=sys.stderr)
                    clear = 0
                    for _ in range(180):   # clear for 3 s in a row: the slider page reloads into another check sometimes
                        clear = 0 if _walled(pg, unknown=True) else clear + 1
                        if clear >= 3:
                            break
                        pg.wait_for_timeout(1000)
                    else:
                        ctx.close()
                        raise RuntimeError("human check not solved")
                    pg.wait_for_load_state("domcontentloaded")
                    pg.wait_for_timeout(2500)
            else:
                b = p.chromium.launch(headless=True, args=["--disable-smooth-scrolling"])
                ctx = b.new_context(viewport={"width": 1280, "height": 720}, locale="en-US", color_scheme=cfg["scheme"],
                                    # a headless user agent gets the bot wall on StockX
                                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                                               "Chrome/130.0.0.0 Safari/537.36")
                pg = ctx.new_page()
                pg.goto(url, wait_until="domcontentloaded", timeout=30000)
            t0 = time.time()
            for label in ("Reject all", "Accept all"):   # EU consent wall
                try:
                    pg.get_by_role("button", name=label).first.click(timeout=1500)
                    pg.wait_for_load_state("domcontentloaded")
                    break
                except Exception:
                    pass
            pg.add_style_tag(content=cfg["css"] + " html, body, * { scroll-behavior: auto !important; }")
            try:
                pg.wait_for_selector(cfg["wait"], timeout=15000)
            except Exception:
                pass
            if cfg.get("need") and len(pg.query_selector_all(cfg["need"])) < cfg.get("need_n", 1):
                raise RuntimeError("no results on the page")   # "We didn't find any results": try the next query
            if _walled(pg):
                raise RuntimeError("human check on the page")  # never film a captcha page
            pg.wait_for_timeout(2500)          # thumbnails load
            if start:                          # begin further down the page (a supplier list below the hero)
                pg.mouse.move(640, 300)
                for _ in range(max(1, start // 200)):
                    pg.mouse.wheel(0, 200)
                    pg.wait_for_timeout(60)
                pg.wait_for_timeout(1200)      # lazy images below the fold
            _no_cookie_banner(pg)              # late banners (Shein shows its consent box ~3 s after load)
            pg.evaluate(SANITIZE_JS)
            n_own = hide_own(pg)
            if n_own:
                print(f"screenrec: hid {n_own} of his own result(s) from the page", file=sys.stderr)
                left = pg.evaluate("sel => [...document.querySelectorAll(sel)].filter(e => e.offsetParent !== null).length", cfg["wait"])
                if left < 3:   # a search that is mostly his own videos: never film an empty page, the caller tries the next query
                    raise RuntimeError(f"only {left} result(s) left after hiding his own videos")
            pg.mouse.move(640, 300)   # 1280x720 page scaled up: big readable thumbnails
            steps = int(seconds * 30)
            for i in range(steps):             # eased scroll: slow-fast-slow, like a hand on the wheel
                x = i / steps
                pg.mouse.wheel(0, (2 + 15 * (1 - abs(2 * x - 1))) * cfg.get("scroll", 1.0))   # news: stay on the top stories
                if i % 15 == 0:
                    pg.evaluate(SANITIZE_JS)   # newly loaded results
                    hide_own(pg)
                    if site == "page":
                        _no_cookie_banner(pg)  # a consent box that shows up mid-scroll
                pg.wait_for_timeout(1000 / 30)  # lazy images keep loading at a natural pace
                pg.screenshot(path=os.path.join(tmp, f"f{i:04d}.jpg"), type="jpeg", quality=92)
            ctx.close()
            if b:
                b.close()
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "30", "-i", os.path.join(tmp, "f%04d.jpg"),
                        "-vf", "scale=1920:1080:flags=lanczos,format=yuv420p", "-c:v", "libx264", "-profile:v", "high",
                        "-crf", "18", "-preset", "fast", "-an", out_mp4], check=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--verify"]:   # screenrec.py --verify URL [start]: record a walled page, he solves the check once
        print(record_page(sys.argv[2], start=int(sys.argv[3]) if len(sys.argv) > 3 else 0, verify=True))
        sys.exit(0)
    print(record_search(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None, site=sys.argv[3] if len(sys.argv) > 3 else "youtube"))

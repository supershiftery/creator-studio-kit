"""Recreated website pages for intros, when the real site can't be recorded (2026-10-23, ultimate dhgate free reselling
spreadsheet: Alibaba shows "drag the slider to verify" to every automated browser; user: "Maybe we should recreate the page
... I want it automatic ... if the site doesn't load, then try something else that's creative").

    recreate(site, data, seconds=4.0) -> mp4 | None

The page is built locally in the site's own look (brand colour, wordmark, search bar, its layout) and filmed by screenrec's
frame-by-frame scroller from file://, so no site can block it. data:
  {"kind": "listing", "title", "price", "sold", "rating", "moq", "supplier", "country", "chips": [...], "attrs": {...},
   "images": [paths]}       one product page (real numbers only: from the project's raw/site_<site>.json)
  {"kind": "search", "query", "images": [paths], "names": [...]}   search results (no invented prices)
Pictures: his own product footage frames first, then free pictures (pics.fetch). Cached by content in _cache/sitepage/.
"""
import hashlib
import html
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "_cache", "sitepage")

THEMES = {
    "alibaba": {"brand": "#FF6A00", "word": "Alibaba.com", "nav": ["All categories", "Verified manufacturers", "Dropshipping", "Help Center", "Sell on Alibaba.com"],
                "cta": "Start order", "cta2": "Chat now"},
    "aliexpress": {"brand": "#E62E04", "word": "AliExpress", "nav": ["Categories", "Choice", "SuperDeals", "Bundle deals", "Help"], "cta": "Buy now", "cta2": "Add to cart"},
    "amazon": {"brand": "#FF9900", "head": "#131921", "word": "amazon", "nav": ["All", "Today's Deals", "Customer Service", "Registry", "Gift Cards"],
               "cta": "Buy Now", "cta2": "Add to Cart"},
    "temu": {"brand": "#FB7701", "word": "TEMU", "nav": ["Best-Selling Items", "5-Star Rated", "New In", "Categories"], "cta": "Add to cart", "cta2": "Buy now"},
    "ebay": {"brand": "#3665F3", "word": "ebay", "nav": ["Saved", "Electronics", "Fashion", "Collectibles", "Deals"], "cta": "Buy It Now", "cta2": "Add to cart"},
    "etsy": {"brand": "#F1641E", "word": "Etsy", "nav": ["Gifts", "Home Favorites", "Fashion Finds", "Registry"], "cta": "Buy it now", "cta2": "Add to basket"},
    "canva": {"brand": "#7D2AE8", "word": "Canva", "nav": ["Design spotlight", "Business", "Education", "Plans and pricing"], "cta": "Customize this template", "cta2": "Share"},
}
GENERIC = {"brand": "#222222", "nav": ["Shop", "Deals", "New", "Help"], "cta": "Buy now", "cta2": "Add to cart"}

CSS = """
*{box-sizing:border-box;margin:0;padding:0} body{font-family:Inter,Segoe UI,Arial,sans-serif;background:#fff;color:#222;width:1280px}
.top{display:flex;align-items:center;gap:28px;padding:18px 40px;background:var(--head)}
.word{font-weight:800;font-size:30px;color:var(--brand);letter-spacing:-.5px;white-space:nowrap}
.search{flex:1;display:flex;border:2px solid var(--brand);border-radius:28px;overflow:hidden;height:46px;background:#fff}
.search span{flex:1;padding:11px 20px;font-size:17px;color:#666}
.search b{background:var(--brand);color:#fff;padding:12px 26px;font-size:16px}
.acct{background:var(--brand);color:#fff;border-radius:24px;padding:11px 22px;font-weight:700;font-size:15px;white-space:nowrap}
.nav{display:flex;gap:30px;padding:10px 40px 14px;border-bottom:1px solid #e6e6e6;font-size:15px;color:#333}
.crumb{padding:16px 40px;font-size:13px;color:#555}
.main{display:grid;grid-template-columns:90px 380px 1fr 300px;gap:18px;padding:0 40px}
.thumbs img{width:84px;height:84px;object-fit:cover;border-radius:8px;border:2px solid #eee;margin-bottom:10px}
.thumbs img:first-child{border-color:#222}
.hero{background:#f5f5f5;border-radius:14px;height:420px;display:flex;align-items:center;justify-content:center;overflow:hidden}
.hero img{width:100%;height:100%;object-fit:cover}
h1{font-size:23px;line-height:1.3;font-weight:700;margin-bottom:10px}
.stars{color:#f5a623;font-size:17px} .meta{font-size:15px;color:#444;margin:6px 0 14px}
.price{font-size:38px;font-weight:800;margin:14px 0 4px} .moq{color:#666;font-size:15px;margin-bottom:18px}
.chips{display:flex;flex-wrap:wrap;gap:10px;margin:10px 0 18px} .chips span{background:#f2f2f2;border-radius:8px;padding:9px 16px;font-size:15px}
.chips span:first-child{border:2px solid #222;background:#fff}
.side{border:1px solid #eee;border-radius:14px;padding:20px;background:#f8faff;font-size:14px;line-height:1.6}
.side h3{font-size:17px;margin:4px 0 8px}
.cta{display:block;text-align:center;background:var(--brand);color:#fff;border-radius:28px;padding:14px;font-weight:700;margin-top:16px;font-size:17px}
.cta2{display:block;text-align:center;border:2px solid #222;border-radius:28px;padding:12px;font-weight:700;margin-top:10px}
.supp{margin:18px 40px 0;border:1px solid #eee;border-radius:14px;padding:18px 22px;width:510px;font-size:14px}
.supp b{text-decoration:underline;font-size:17px}
.attrs{margin:26px 40px;border:1px solid #eee;border-radius:12px;display:grid;grid-template-columns:repeat(3,1fr)}
.attrs div{padding:14px 18px;border-bottom:1px solid #eee;font-size:14px;color:#666} .attrs div b{display:block;color:#222;font-size:17px;margin-top:3px}
.sec{margin:10px 40px 14px;font-size:22px;font-weight:700}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:18px;padding:0 40px 60px}
.card{border-radius:12px;overflow:hidden;border:1px solid #eee} .card img{width:100%;height:230px;object-fit:cover;background:#f4f4f4}
.card p{padding:10px 12px 4px;font-size:14px;line-height:1.35;height:48px;overflow:hidden} .card i{display:block;padding:0 12px 12px;color:#f5a623;font-style:normal}
.big img{width:100%;border-radius:14px;margin-bottom:16px}
"""


def _img_tags(imgs, d):
    out = []
    for i, p in enumerate(imgs):
        dst = f"i{i}{os.path.splitext(p)[1] or '.jpg'}"
        shutil.copy(p, os.path.join(d, dst))
        out.append(dst)
    return out


def _page(site, data, d):
    t = {**GENERIC, "word": site.title(), **THEMES.get(site, {})}
    e = html.escape
    imgs = _img_tags(data.get("images") or [], d) or [""]
    pick = lambda i: imgs[i % len(imgs)]
    top = (f'<div class="top"><div class="word">{e(t["word"])}</div><div class="search"><span>{e(data.get("query") or data.get("title", "")[:40])}</span>'
           f'<b>Search</b></div><div class="acct">Sign in</div></div><div class="nav">' + "".join(f"<span>{e(n)}</span>" for n in t["nav"]) + "</div>")
    if data.get("kind") == "listing":
        attrs = "".join(f"<div>{e(k)}<b>{e(v)}</b></div>" for k, v in (data.get("attrs") or {}).items())
        body = f"""
<div class="crumb">{' &rsaquo; '.join(e(c) for c in data.get('crumbs', []))}</div>
<div class="main"><div class="thumbs">{''.join(f'<img src="{pick(i)}">' for i in range(4))}</div>
<div class="hero"><img src="{pick(0)}"></div>
<div><h1>{e(data['title'])}</h1>
<div class="meta"><span class="stars">&#9733;&#9733;&#9733;&#9733;&#9733;</span> {e(data.get('rating', ''))} &nbsp;|&nbsp; {e(data.get('sold', ''))}</div>
<div class="price">{e(data.get('price', ''))}</div><div class="moq">{e(data.get('moq', ''))}</div>
<b>model number</b><div class="chips">{''.join(f'<span>{e(c)}</span>' for c in data.get('chips', []))}</div></div>
<div class="side"><h3>{e(data.get('stock', ''))}</h3><h3>Shipping</h3>{e(data.get('shipping', ''))}<h3>Order protection</h3>Secure payments
<span class="cta">{e(t['cta'])}</span><span class="cta2">{e(t['cta2'])}</span></div></div>
<div class="supp"><b>{e(data.get('supplier', ''))}</b><br>{e(data.get('country', ''))}<br><br>{e(data.get('store', ''))}</div>
<div class="sec">Key attributes</div><div class="attrs">{attrs}</div>
<div class="sec">Product descriptions from the supplier</div>
<div class="big" style="padding:0 40px">{''.join(f'<img src="{pick(i)}">' for i in range(1, 3))}</div>"""
    else:
        names = data.get("names") or [data.get("query", "")]
        body = f'<div class="crumb">Showing results for "{e(data.get("query", ""))}"</div><div class="grid" style="padding-top:6px">' + "".join(
            f'<div class="card"><img src="{pick(i)}"><p>{e(names[i % len(names)])}</p><i>&#9733;&#9733;&#9733;&#9733;&#9733;</i></div>' for i in range(len(imgs))) + "</div>"
    head = t.get("head", "#fff")
    style = CSS + f":root{{--brand:{t['brand']};--head:{head}}}" + (".nav{background:#232f3e;color:#fff}.search span{color:#444}" if head != "#fff" else "")
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{style}</style></head><body>{top}{body}</body></html>"


def recreate(site, data, seconds=4.0):
    key = hashlib.sha1(json.dumps([site, data, seconds, 1], sort_keys=True).encode()).hexdigest()[:12]
    d = os.path.join(CACHE, f"{site}-{key}")
    mp4 = os.path.join(d, "page.mp4")
    if os.path.exists(mp4):
        return mp4
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
        f.write(_page(site, data, d))
    sys.path.insert(0, HERE)
    import screenrec
    got = screenrec.record_page("file:///" + os.path.join(d, "index.html").replace("\\", "/"), seconds=seconds, verify=False)
    if not got:
        return None
    shutil.copy(got, mp4)
    return mp4


if __name__ == "__main__":   # sitepage.py <site> <data.json>
    print(recreate(sys.argv[1], json.load(open(sys.argv[2], encoding="utf-8"))))

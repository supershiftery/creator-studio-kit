"""Outside B-roll for a phone video's intro (dhgate coupons 2026-10-24, user: "something just doesn't feel crispy about it ...
maybe we just don't have enough B-roll from the original video ... it's still lacking character"). The coupons video is
3.5 min after the cut and its screen is mostly a codes spreadsheet (never shown in an intro), so intro_footage.py found only
5 website moments and the director filled 7 of 11 lines with designed cards and type. The intro he loves (ultimate dhgate
free reselling spreadsheet) got its character from material OUTSIDE the video: his own product footage from other videos and
real site recordings. This does the same for store apps (apps.json kind "shop": DHgate, Shein, Temu...):

  1. his own HAUL footage of that store (intro_library/product_library.py over {{DRIVE_RAW}}: "dhgate haul #8",
     vision-picked moments where the products are shown), for the cheap / products / order / save-money lines
  2. a live scroll of the store's own website (screenrec.py), for the "on the surface / looked into it" lines

    python intro_extras.py <app key> <footage.json to extend> [--hauls 4]

Appends to the footage.json intro_footage.py wrote; never fails the build (prints why and leaves the file as it was).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.join(os.path.dirname(HERE), "intro_library")
sys.path.insert(0, LIB)

# which VO words each kind of extra answers (build_intro.for_hit matches these against the line)
# haul footage only on lines about the store / its products ("save money" got a colour-changing LED gadget, 2026-10-24 test):
# money / code lines keep their designed coupon graphics
HAUL_FOR = [["cheap", "platform", "surface"], ["products", "items", "bought", "haul", "stuff"], ["order", "ordered", "package"]]   # never fee / filler lines (the LED lamp sat on "you guys name it", 2026-10-24)
SITE_FOR = ["looked", "deeper", "website", "site", "check out", "checkout", "browse", "browsing"]
HOME = {"dhgate": "https://www.dhgate.com/", "shein": "https://us.shein.com/", "temu": "https://www.temu.com/",
        "amazon": "https://www.amazon.com/"}


def extras(app, n_hauls=3):
    apps = json.load(open(os.path.join(HERE, "apps.json"), encoding="utf-8"))
    a = apps.get(app) or {}
    if a.get("kind") != "shop":
        return []
    out = []
    try:
        import product_library as PL
        clips = PL.find_clips(f"{a.get('name', app)} haul", n=n_hauls, max_files=3)
        for k, c in enumerate(clips):
            c = dict(c, tag=f"product: {a.get('name', app)} haul ({os.path.basename(os.path.dirname(c['src']))})",
                     kind="cam", **{"for": HAUL_FOR[k % len(HAUL_FOR)]})
            out.append(c)
    except Exception as e:
        print(f"intro extras: haul footage skipped ({type(e).__name__}: {str(e)[:120]})", flush=True)
    url = HOME.get(app)
    if url:
        try:
            import screenrec
            mp4 = screenrec.record_page(url, seconds=4.0)
            if mp4:
                out.append({"src": mp4, "t": 0.0, "kind": "cam", "tag": f"screen recording: {app} home page", "for": SITE_FOR,
                            "no_stab": True})
        except Exception as e:
            print(f"intro extras: site recording skipped ({type(e).__name__}: {str(e)[:120]})", flush=True)
    return out


def plus(vo, title, channel, cache):
    """Outside sources for ANY app (2026-10-25 asset mix, intro_library/assets_plus.py): YouTube thumbnail wall on
    "everyone / trending" lines, his viewers' real comments on "you guys asked" lines, city maps. Needs the VO words."""
    try:
        import build_intro
        import assets_plus
        words = build_intro.transcribe(vo, cache, title)
        return assets_plus.plus_footage(" ".join(w["w"] for w in words), title, channel, creators=True,
                                        say=lambda m: print(m, flush=True))
    except Exception as e:
        print(f"intro extras: outside sources skipped ({type(e).__name__}: {str(e)[:120]})", flush=True)
        return []


def _arg(flag, default=""):
    return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default


if __name__ == "__main__":
    app, fj = sys.argv[1], sys.argv[2]
    n = int(_arg("--hauls", "3"))
    have = json.load(open(fj, encoding="utf-8")) if os.path.exists(fj) else []
    add = []
    if any(str(f.get("tag", "")).startswith(("product: ", "screen recording: ")) for f in have):
        print("intro extras: store extras already added", flush=True)
    else:
        add = extras(app, n)
    # outside sources (pipeline passes --vo; older callers don't): once per footage.json
    if _arg("--vo") and not any(str(f.get("tag", "")).startswith(("youtube thumbnails", "viewer comments", "map:")) for f in have):
        add += plus(_arg("--vo"), _arg("--title"), _arg("--channel", "{{PHONE_CHANNEL}}"),
                    os.path.join(os.path.dirname(os.path.abspath(fj)), "intro_vo_words.json"))
    json.dump(have + add, open(fj, "w", encoding="utf-8"), indent=1)
    print(f"intro extras: +{len(add)} clips ({', '.join(x['tag'] for x in add)})", flush=True)

r"""Realm code card: a Bedrock "Join Realm" screen shows the realm's name, types its code, clicks Join, then flies into a lower third.

python build.py <rank> [--transparent] [--hold 7] [--picks {{KIT}}/tools/minecraft\Research\realms-2026-10.json]
  Fills src/template.html.tpl from the realm picks JSON (rank, name, code) and writes index.html. Then `npx hyperframes render`.
"""
import argparse, json
from pathlib import Path

HERE = Path(__file__).parent

ap = argparse.ArgumentParser()
ap.add_argument("rank", type=int)
ap.add_argument("--transparent", action="store_true"); ap.add_argument("--hold", type=float, default=7.0)
ap.add_argument("--picks", default=r"{{KIT}}/tools/minecraft\Research\realms-2026-10.json")
a = ap.parse_args()

if a.rank >= 91:  # 91, 92, ... = honorable mentions, in order, from the alternates file (mention: true); card shows "HM"
    alts = Path(a.picks.replace("realms-2026-10.json", "realms-alternates-2026-10.json"))
    realm = [r for r in json.loads(alts.read_text(encoding="utf-8")) if r.get("mention")][a.rank - 91]
else:
    realm = next(r for r in json.loads(Path(a.picks).read_text(encoding="utf-8")) if r["rank"] == a.rank)
name, code = realm["name"], realm["code"]

per = 0.09                                  # codes are random letters, so type them a bit slower than server IPs
t_code = 0.75
code_end = t_code + len(code) * per
punch = code_end + 0.1
cursor = punch + 0.25
click = cursor + 0.42
fly = click + 0.22
fly_end = fly + 0.35
lt = fly_end - 0.05
dur = round(lt + a.hold + 0.4, 2)
lt_out = dur - 0.4
T = dict(code=t_code, per=per, punch=punch, cursor=cursor, click=click, fly=fly, flyEnd=fly_end, lt=lt, ltOut=lt_out)
cfg = dict(rank="HM" if a.rank >= 91 else a.rank, name=name, code=code, seed=sum(map(ord, name)), hue=(sum(map(ord, name)) * 37) % 360, transparent=a.transparent, t=T)

aud, n = [], 0
def add(src, t, d, vol, media=0.0):
    global n; n += 1
    ms = f' data-media-start="{media}"' if media else ""
    aud.append(f'<audio id="a{n}" src="assets/sfx/{src}" data-start="{t:.3f}" data-duration="{d:.3f}"{ms} data-track-index="{10 + n % 3}" data-volume="{vol}"></audio>')
add("whoosh-short.mp3", 0.0, 0.57, 0.22)
left, t = len(code) * per, t_code
while left > 0.05:                          # typing.mp3 is 1.5 s; chain it for long codes
    d = min(left, 1.45); add("typing.mp3", t, d, 0.2); t += d; left -= d
add("click.mp3", click, 0.36, 0.3)
add("whoosh-short.mp3", fly - 0.05, 0.57, 0.22)
add("ping.mp3", lt + 0.3, 0.9, 0.13)
add("whoosh-short.mp3", lt_out - 0.05, 0.57, 0.16)

html = (HERE / "src" / "template.html.tpl").read_text(encoding="utf-8")
for k, val in {"__DUR__": dur, "__T_FLYEND__": round(fly_end + 0.05, 3), "__T_LT__": round(lt, 3), "__LT_DUR__": round(dur - lt, 3),
               "__NAME_UP__": name.upper(), "__CFG__": json.dumps(cfg, ensure_ascii=False), "__AUDIO__": "\n      ".join(aud)}.items():
    html = html.replace(k, str(val))
(HERE / "index.html").write_text(html, encoding="utf-8")
print(f"#{a.rank} {name}  {code}  dur {dur}s  (typing {t_code:.2f}-{code_end:.2f}, lower third {lt:.2f}-{dur})")

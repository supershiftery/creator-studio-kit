r"""Server IP card: a Bedrock "Add Server" screen types the server's name, address and port, then flies into a lower third.

python build.py <video-slug> <rank> [--server <library key>] [--transparent] [--hold 7] [--classic]  (rank badge = KV pixel box unless --classic)
  Fills src/template.html.tpl from {{KIT}}/tools/minecraft\library.json and writes index.html. Then `npx hyperframes render`.
"""
import argparse, json
from pathlib import Path

HERE = Path(__file__).parent
LIB = Path(r"{{KIT}}/tools/minecraft\library.json")

ap = argparse.ArgumentParser()
ap.add_argument("video"); ap.add_argument("rank", type=int)
ap.add_argument("--transparent", action="store_true"); ap.add_argument("--hold", type=float, default=7.0)
# the rank badge is KV Digital's pixel box by DEFAULT (user approved the KV numbers 2026-10-24); --classic = old yellow pixel badge
ap.add_argument("--kv", action="store_true", help="(default now) rank badge in the KV pixel box")
ap.add_argument("--classic", action="store_true", help="old yellow pixel-text rank badge")
ap.add_argument("--server", help="library.json servers key; overrides the rank lookup (the rank is still shown)")
a = ap.parse_args()

lib = json.loads(LIB.read_text(encoding="utf-8"))
v = lib["videos"][a.video]
order = v["servers"]                        # first = #N (countdown)
srv = lib["servers"][a.server or order[len(order) - a.rank]]
name, ip, port = srv["name"], srv["address"], srv.get("port") or 19132

per = [0.07, 0.075, 0.08]
t_name = 0.6
t_addr = t_name + len(name) * per[0] + 0.3
t_port = t_addr + len(ip) * per[1] + 0.25
port_end = t_port + len(str(port)) * per[2]
punch = port_end + 0.1
cursor = punch + 0.2
click = cursor + 0.42
fly = click + 0.22
fly_end = fly + 0.35
lt = fly_end - 0.05
dur = round(lt + a.hold + 0.4, 2)
lt_out = dur - 0.4
T = dict(name=t_name, addr=t_addr, port=t_port, per=per, punch=punch, cursor=cursor, click=click, fly=fly, flyEnd=fly_end, lt=lt, ltOut=lt_out)
cfg = dict(rank=a.rank, name=name, ip=ip, port=port, seed=sum(map(ord, name)), hue=(sum(map(ord, name)) * 37) % 360, transparent=a.transparent, kv=not a.classic, t=T)

aud, n = [], 0
def add(src, t, d, vol, media=0.0):
    global n; n += 1
    ms = f' data-media-start="{media}"' if media else ""
    aud.append(f'<audio id="a{n}" src="assets/sfx/{src}" data-start="{t:.3f}" data-duration="{d:.3f}"{ms} data-track-index="{10 + n % 3}" data-volume="{vol}"></audio>')
add("whoosh-short.mp3", 0.0, 0.57, 0.22)
for t0, s, p in ((t_name, name, per[0]), (t_addr, ip, per[1]), (t_port, str(port), per[2])):
    left, t = len(s) * p, t0
    while left > 0.05:                      # typing.mp3 is 1.5 s; chain it for long addresses
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
print(f"#{a.rank} {name}  {ip}:{port}  dur {dur}s  (typing {t_name:.2f}-{port_end:.2f}, lower third {lt:.2f}-{dur})")

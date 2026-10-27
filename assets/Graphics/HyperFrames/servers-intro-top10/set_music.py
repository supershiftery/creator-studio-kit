# usage: python set_music.py <assets/music-file.mp3> <pre> <drop> <bed> <title>
import re, sys, json
src, pre, drop, bed, title = sys.argv[1], *map(float, sys.argv[2:6])
pts = [(0,0),(0.5,pre),(14.7,pre),(14.86,0),(15.1,0),(15.14,drop),(15.9,drop*0.86),(16.4,bed),(30.2,bed),(30.34,title),(32.6,title*0.9),(33.6,0)]
auto = json.dumps({"version":1,"lanes":[{"target":"volume","points":[{"t":t,"v":round(v,3)} for t,v in pts]}]}, separators=(",",":"))
p = "index.html"; s = open(p, encoding="utf-8").read()
s, n = re.subn(r'<audio id="music" src="[^"]*"(.*?)data-automation=\'[^\']*\'', lambda m: f'<audio id="music" src="{src}"{m.group(1)}data-automation=\'{auto}\'', s, flags=re.S)
assert n == 1
open(p, "w", encoding="utf-8").write(s)

"""Step 1b: find Director add-on B-roll in the recording (and in dropped clips) by the MAGENTA start/end flashes,
split reels on the fades to black, cut every shot into <project>\\B-roll\\ and register the clips in studio.json.
python broll.py <project>
Detection is modpipe\\brollmap.py (shared with mc.py's watcher): it looks at the GAME half only, reads the reel code the
Director flashes after the pink, and trims every shot at full frame rate so no black fade or pink frame is left in.
Each clip is named after what it shows ("CobbleDrock 01 Charizard (attack)") and mapped in broll.json "map" +
<project>\\B-roll\\B-roll map.csv. "reels" = where the B-roll sits in the main recording, so cuts.py keeps it out of the
gameplay (it only ever comes back as B-roll)."""
import json
import os
import subprocess
import sys
from pathlib import Path

from glib import NVENC, Project, fmt, say

sys.path.insert(0, r"{{KIT}}/tools/minecraft/modpipe")
import brollmap  # noqa: E402

VERSION = 2   # bump to rescan every source (v2 = brollmap: codes, exact edges, names)
P = Project(sys.argv[1])
SI = P.source_info
out_dir = P.path / "B-roll"
out_dir.mkdir(exist_ok=True)
state = P.read("broll.json", {})
old_made = set(state.get("clips", []))   # shots cut by an earlier scan (v1 too): never scanned again as sources
if state.get("version") != VERSION:
    state = {"version": VERSION, "sources": {}}
sources = [(P.src, SI.get("game_crop"))] if P.src else []
for c in P.doc.get("slots", {}).get("broll", []):   # dropped clips can carry flashes too (a whole Director recording)
    if os.path.exists(c) and c not in old_made:
        sources.append((c, "auto"))
catalog = brollmap.load_reels()
for src, crop in sources:
    key = f"{src}|{os.path.getmtime(src)}"
    if key in state["sources"]:
        say(f"{Path(src).name}: already scanned ({len(state['sources'][key]['rows'])} shots)")
        continue
    if crop == "auto":
        crop = brollmap.game_crop(src)
    reels = brollmap.describe(brollmap.find_reels(src, crop), catalog)
    say(f"{Path(src).name}: {len(reels)} reels, {sum(len(r['shots']) for r in reels)} shots")
    clips = {}
    for ri, r in enumerate(reels):
        say(f"  reel {fmt(r['start'])}-{fmt(r['end'])}  {r['reel_title']} (mapped by {r['mapped'] or 'nothing'})")
        for s in r["shots"]:
            name = brollmap.clip_name(Path(src).stem, r, s) if r.get("mapped") else f"{Path(src).stem} - reel{ri + 1} shot{s['n']:02d}"
            clip = out_dir / f"{name}.mp4"
            # fast seek to 3 s before, then an exact one: the refined edges are to the frame and a keyframe seek could
            # land on a fade frame
            pre = min(3.0, s["start"])
            cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{s['start'] - pre:.3f}", "-i", src, "-ss", f"{pre:.3f}",
                   "-t", f"{s['end'] - s['start']:.3f}"]
            if crop:
                cmd += ["-vf", f"crop={crop}"]
            cmd += ["-an"] + NVENC + ["-cq", "18", str(clip)]
            if subprocess.run(cmd, capture_output=True).returncode == 0 and clip.exists():
                clips[(ri, s["n"])] = clip
                say(f"    {s['n']:2d}  {fmt(s['start'])}-{fmt(s['end'])}  {clip.name}")
    rows = brollmap.map_rows(src, reels, clips)
    for row in rows:
        row["main"] = src == P.src          # filmed inside the main recording: its time says which section it belongs to
    state["sources"][key] = {"rows": rows, "reels": [[r["start"], r["end"]] for r in reels] if src == P.src else []}
live = {k: v for k, v in state["sources"].items() if os.path.exists(k.rsplit("|", 1)[0])}
state["sources"] = live
state["map"] = [row for v in live.values() for row in v["rows"] if os.path.exists(row["clip"])]
state["clips"] = sorted({row["clip"] for row in state["map"]})
state["reels"] = sorted(r for k, v in live.items() if k.rsplit("|", 1)[0] == P.src for r in v["reels"])
P.write("broll.json", state)
if state["map"]:
    brollmap.write_map(state["map"], out_dir / "B-roll map.csv")
# register in studio.json: dropped clips stay, detected shots are added, shots an older scan cut (and this one didn't) go
doc_path = P.path / "studio.json"
doc = json.loads(doc_path.read_text(encoding="utf-8-sig"))
# a dropped clip that held reels is the raw Director recording (pink, fades): its clean shots replace it in the pool
spent = {k.rsplit("|", 1)[0] for k, v in live.items() if v["rows"]}
state["spent"] = sorted(spent - {P.src})
P.write("broll.json", state)
have = [c for c in doc["slots"].get("broll", []) if os.path.exists(c) and c not in spent and not (c in old_made and c not in state["clips"])]
doc["slots"]["broll"] = sorted(set(have) | set(state["clips"]))
doc_path.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
say(f"B-roll clips in the project: {len(doc['slots']['broll'])} ({len(state['map'])} from the pink flashes, "
    f"{len(state['reels'])} reels kept out of the gameplay)")

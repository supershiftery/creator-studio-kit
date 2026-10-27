"""Dry run of music_lib over recent projects: what each would get (no log written, nothing rendered).
python music_dryrun.py [out.md]   -> prints + writes a markdown table"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import music_lib as M

PROJECTS = [  # (project folder, kind, how many tracks, style)
    (r"{{PROJECTS_ROOT}}\canada goose jacket dhgate", "review", 4, None),
    (r"{{PROJECTS_ROOT}}\top 5 products to resell in winter 2024", "review", 4, None),
    (r"{{PROJECTS_ROOT}}\lv skatesta", "review", 4, None),
    (r"{{PROJECTS_ROOT}}\Dhgate coupon codes", "phone", 4, None),
    (r"{{PROJECTS_ROOT}}\chime sign up bonus", "screen", 4, "chill"),
    (r"{{GAMING_ROOT}}\Top 10 Minecraft Servers", "gaming", 5, None),
]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    idx = M.load_index()
    rows, taken = [], []
    for proj, kind, n, style in PROJECTS:
        p, k, ch, title, text = M.project_context(proj)
        key, want, why, c = M.candidates(kind, title, text, style, project=p, idx=idx)
        # the dry run walks the projects in order like real builds would, so later ones avoid earlier ones' picks
        tr = M.pick(kind, n, title=title, text=text, style=style, channel=ch, project=p, log=False, keep=False, exclude=taken)
        taken += tr
        top = sorted(want.items(), key=lambda x: -x[1])[:3]
        rows.append({"project": os.path.basename(p), "kind": key, "channel": ch or M.CHANNEL_OF.get(kind), "pool": len(c),
                     "mood": ", ".join(f"{m}" for m, v in top if v > 0), "topic": ", ".join(dict.fromkeys(why))[:60],
                     "tracks": [(t, M.info(t, idx)) for t in tr]})
    out = []
    for r in rows:
        out.append(f"## {r['project']}  ({r['kind']}, {r['channel']})")
        out.append(f"mood: {r['mood']}   topic words: {r['topic'] or '-'}   fitting clean tracks: {r['pool']}")
        for t, i in r["tracks"]:
            mo = ", ".join(k for k, v in sorted((i.get('moods') or {}).items(), key=lambda x: -x[1])[:2])
            out.append(f"- {os.path.relpath(t, M.ROOT)}  [{mo}; energy {i.get('energy', 0):.2f}; {i.get('bpm', 0):.0f} bpm; "
                       f"{i.get('usable', 0) / 60:.1f} min; vocal scan {(i.get('vocal') or {}).get('verdict')}]")
        out.append("")
    txt = "\n".join(out)
    print(txt)
    if len(sys.argv) > 1:
        open(sys.argv[1], "w", encoding="utf-8").write(txt)


if __name__ == "__main__":
    main()

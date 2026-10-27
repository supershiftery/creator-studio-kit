"""Compare a draft/final against the playbook targets measured from the approved finals (tools/targets.json).
python targets_check.py <project folder> [video]
Checks intro length, time to first content (first #entry / first code card), section lengths, visual pace (big changes
per minute: ffmpeg scene score > 0.3, the same measure the study used), loudness (integrated, LRA, true peak), how much
of the recording was kept and talk speed. Writes "<video> targets.md/.json" next to the video and prints a summary.
Never fails the build: a miss is a flag for the editor, not an error (user 2026-10-22: "flag misses")."""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGETS = json.loads((HERE / "targets.json").read_text(encoding="utf-8"))


def duration(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def read(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def fm(t):
    return "-" if t is None else f"{int(t // 60)}:{t % 60:04.1f}"


def scenes(video):
    """times of big visual changes (scene score > 0.3 at 10 fps, 320 px), the measure used on the approved finals"""
    vf = "fps=10,scale=320:-2,select='gt(scene,0.30)',showinfo"
    for pre in (["-hwaccel", "cuda"], []):
        r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats"] + pre + ["-i", str(video), "-an", "-vf", vf, "-f", "null", "-"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        t = [float(x) for x in re.findall(r"pts_time:([\d.]+)", r.stderr)]
        if t or r.returncode == 0:
            return t
    return []


def loudness(video):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = r.stderr[r.stderr.rfind("Summary:"):]
    g = lambda k: float(m.group(1)) if (m := re.search(k + r":\s+(-?[\d.]+)", tail)) else None
    return {"lufs": g("I"), "lra": g("LRA"), "true_peak": g("Peak")}


def words_list(p):
    w = read(p, [])
    w = w if isinstance(w, list) else (w.get("words") or w.get("segments") or [])
    out = []
    for x in w:
        if isinstance(x, dict) and isinstance(x.get("words"), list):
            out += [float(y.get("start", y.get("s", 0))) for y in x["words"]]
        elif isinstance(x, dict):
            out.append(float(x.get("s", x.get("start", 0))))
    return out


def gather(proj, doc, video):
    """what this project type can tell us: intro length, first content time, sections, kept ranges, words, raw length"""
    kind, info = doc.get("type", "gaming"), {}
    if kind == "gaming":
        mode = "final" if "final" in video.stem.lower() else "draft"
        tl = read(proj / "Edit" / "studio" / f"timeline-{mode}.json", {}) or {}
        info["intro"] = tl.get("intro")
        secs = [(s["section"], s.get("t_final", s.get("t"))) for s in tl.get("sections", [])]
        ranked = [(n, t) for n, t in secs if n.startswith("#") or n.startswith("HM")]
        info["first_content"] = min((t for _, t in ranked), default=None)
        bounds = secs + [("end", duration(video))]
        info["sections"] = [(n, bounds[i + 1][1] - t) for i, (n, t) in enumerate(secs) if (n.startswith("#") or n.startswith("HM")) and i + 1 < len(bounds)]
        info["keep"] = [k for k in tl.get("keep", []) if k[0] >= 0]
        info["words"] = words_list(proj / "Edit" / "studio" / "words.json")
        info["raw"] = (read(proj / "Edit" / "studio" / "source.json", {}) or {}).get("duration") or (duration(doc["source"]) if doc.get("source") else 0)
    elif kind == "phone":
        intro_mp4 = proj / "edit" / "intro" / "renders" / "intro.mp4"
        intro = duration(intro_mp4) if intro_mp4.exists() else 0.0
        info["intro"] = intro or None
        ev = read(proj / "edit" / "graphics" / "events.json", []) or []
        codes = [e["t"] for e in ev if isinstance(e, dict) and e.get("kind") == "code"]
        info["first_content"] = (min(codes) + intro) if codes else None
        c = read(proj / "work" / "cuts.json", {}) or {}
        info["keep"] = c.get("keep", []) if isinstance(c, dict) else []
        info["words"] = words_list(proj / "work" / "words.json")
        info["raw"] = duration(proj / "raw" / "source.mp4")
    elif kind in ("haul", "short"):   # phone recordings (tools/haul_render.py writes timeline-haul.json / timeline-short.json)
        tl = read(proj / "Edit" / "studio" / f"timeline-{kind}.json", {}) or {}
        info["intro"] = tl.get("intro_end")
        secs = [(s[0], s[1]) for s in tl.get("sections", []) if s[0] not in ("Intro", "Outro")]
        info["first_content"] = min((t for _, t in secs), default=None)
        bounds = secs + [("end", tl.get("outro_start") or duration(video))]
        info["sections"] = [(n, bounds[i + 1][1] - t) for i, (n, t) in enumerate(secs)]
        info["keep"] = tl.get("keep", [])
        info["words"] = words_list(proj / "Edit" / "studio" / "words.json")
        info["raw"] = (read(proj / "Edit" / "studio" / "source.json", {}) or {}).get("duration") or 0
    else:   # review
        final, fi = proj / "output" / "final.mp4", proj / "output" / "final_intro.mp4"
        info["intro"] = (duration(fi) - duration(final)) if video.name == fi.name and final.exists() else None
        c = read(proj / "work" / "cuts.json", {}) or {}
        info["keep"] = c.get("kept", []) if isinstance(c, dict) else []
        info["words"] = []
        info["raw"] = duration(proj / "raw" / "camera.mp4")
    return kind, info


def judge(value, rng):
    if value is None or not rng:
        return "n/a"
    lo, hi = rng
    if lo is not None and value < lo:
        return "low"
    if hi is not None and value > hi:
        return "high"
    return "ok"


def main():
    proj = Path(sys.argv[1])
    doc = read(proj / "studio.json", {}) or {}
    doc.setdefault("type", "gaming")
    if len(sys.argv) > 2:
        video = Path(sys.argv[2])
    else:
        pats = {"gaming": ["Edit/*final.mp4", "Edit/*draft.mp4"], "phone": ["output/* - FINAL.mp4", "output/* - DRAFT.mp4"],
                "review": ["output/final_intro.mp4", "output/final.mp4"],
                "haul": ["* - FINAL.mp4", "* - DRAFT.mp4"], "short": ["* - FINAL.mp4", "* - DRAFT.mp4"]}[doc["type"]]
        found = [f for pat in pats for f in proj.glob(pat) if "preview" not in f.name.lower()]
        if not found:
            sys.exit("no draft/final to check yet")
        video = max(found, key=lambda f: f.stat().st_mtime)
    kind, info = gather(proj, doc, video)
    T = TARGETS.get(kind, TARGETS["gaming"])
    dur = duration(video)
    intro = info.get("intro") or 0.0
    cuts = scenes(video)
    in_intro = [t for t in cuts if t < intro] if intro else []
    body = [t for t in cuts if t >= intro]
    intro_rate = len(in_intro) / (intro / 60) if intro > 1 else None
    body_rate = len(body) / ((dur - intro) / 60) if dur - intro > 30 else None
    loud = loudness(video)
    kept = sum(b - a for a, b in info.get("keep", []))
    kept_pct = 100 * kept / info["raw"] if info.get("raw") and kept else None
    wpm = None
    if info.get("words") and kept > 60:
        kw = sum(1 for s in info["words"] if any(a <= s < b for a, b in info["keep"]))
        wpm = kw / (kept / 60)

    rows = []   # (metric, value shown, target shown, verdict, hint)

    def row(metric, value, rng, shown=None, hint_low="", hint_high="", fmt=lambda v: f"{v:.1f}"):
        v = judge(value, rng)
        tgt = "-" if not rng else f"{'' if rng[0] is None else fmt(rng[0])}–{'' if rng[1] is None else fmt(rng[1])}"
        hint = hint_low if v == "low" else hint_high if v == "high" else ""
        rows.append({"metric": metric, "value": shown if shown is not None else ("-" if value is None else fmt(value)), "target": tgt, "verdict": v, "hint": hint})

    row("Intro length", info.get("intro"), T.get("intro_s"), fmt=fm,
        hint_low="intro feels thin: add scenes or keep the title on screen ~1 s", hint_high="trim the intro (gaming: settings.intro_out ~1 s after the title) or cut slow scenes")
    row("Time to first content", info.get("first_content"), T.get("first_content_s"), fmt=fm,
        hint_high=f"talking intro too long: get to the first entry/code by ~{fm(T.get('first_content_ideal_s'))}")
    for name, length in info.get("sections", []):
        row(f"Section {name}", length, T.get("section_s"), fmt=fm,
            hint_low="thin entry: keep more gameplay/explanation", hint_high="drags: tighten (cut repeats, dead space, long menus)")
    row("Big visual changes / min (intro)", intro_rate, T.get("intro_changes_per_min"),
        hint_low="intro is too static: a new visual every 1-2 s, one literal scene per line")
    row("Big visual changes / min (body)", body_rate, T.get("body_changes_per_min"),
        hint_low=f"body is too static (approved ~{T.get('body_changes_ideal')}/min): add punch-ins on jump cuts, UI/text zooms, B-roll, transitions")
    row("Loudness (LUFS integrated)", loud["lufs"], T.get("lufs"), hint_low="too quiet: raise the voice target", hint_high="too loud: lower the voice target")
    row("Loudness range (LRA)", loud["lra"], T.get("lra"), hint_high="levels jump around: check the voice leveler and music swells")
    row("True peak (dBTP)", loud["true_peak"], T.get("true_peak"), hint_high="peaks too hot: limiter / lower gain")
    row("Recording kept (%)", kept_pct, T.get("kept_pct"), fmt=lambda v: f"{v:.0f}",
        hint_low="cut very hard: check nothing meaningful was lost", hint_high="kept a lot: look for retakes, dead air, long menus")
    row("Talk speed (words/min kept)", wpm, T.get("wpm"), fmt=lambda v: f"{v:.0f}",
        hint_low="slow: shrink pauses between sentences", hint_high="very fast: check for clipped joins")

    misses = [r for r in rows if r["verdict"] in ("low", "high")]
    out_md = video.with_name(video.stem + " targets.md")
    lines = [f"# Targets check: {video.name}", "", f"Type **{kind}**, {fm(dur)} long. Reference: {T.get('reference', '')}", "",
             f"**{len(misses)} miss(es)** out of {sum(1 for r in rows if r['verdict'] != 'n/a')} checked.", "",
             "| | metric | value | target | fix |", "|---|---|---|---|---|"]
    icon = {"ok": "✅", "low": "⚠️ low", "high": "⚠️ high", "n/a": "–"}
    lines += [f"| {icon[r['verdict']]} | {r['metric']} | {r['value']} | {r['target']} | {r['hint']} |" for r in rows]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_md.with_suffix(".json").write_text(json.dumps({"video": str(video), "type": kind, "misses": len(misses), "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"targets: {len(misses)} miss(es) -> {out_md}")
    for r in rows:
        if r["verdict"] != "n/a":
            print(f"   {icon[r['verdict']]:8} {r['metric']}: {r['value']} (target {r['target']}){'  -> ' + r['hint'] if r['hint'] else ''}")


if __name__ == "__main__":
    main()

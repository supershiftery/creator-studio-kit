"""Claude reviews the QC flags of a render (2026-10-22, user: "call Claude at the right times to be efficient").
    python claude_review.py <project id> <video.mp4>

check_video.py flags every possible problem (repeats, flashes, frozen frames, brief shots ...); most are fine (a title
hold, a deliberate quick cut). This looks at all flag sheets at once (one contact sheet) plus the words spoken around each
flag, and marks each flag "real" (with a fix in Studio note syntax) or "fine". The verdict goes into the flag's note in
<video>_check/report.json, so the Review + notes panel shows it with no UI change, and the full list goes to
<video>_check/claude_review.md. Nothing is cut automatically: fixes are suggestions for the user to add as notes.

Cost: no flags = no call. Otherwise one Sonnet call (lean, cached by claude_brain: a rerun on the same render is free).
Never fails the build."""
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, r"{{KIT}}/tools")
import claude_brain as B   # noqa: E402

API = "http://127.0.0.1:%d/api/" % int(os.environ.get("STUDIO_PORT", "8765"))
MAX_FLAGS = 12


def fmt(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def draft_words(pid):
    """Spoken words in the render's own time (Studio editor API: recording words + kept ranges + intro offset)."""
    try:
        ed = json.load(urllib.request.urlopen(API + f"editor?id={pid}", timeout=60))
    except Exception:
        return []
    keep, acc = [tuple(k) for k in ed.get("keep") or []], float(ed.get("offset") or 0)
    if not keep:
        return [(w["s"] + acc, w["w"]) for w in ed.get("words") or []]
    out, starts = [], []
    for a, b in keep:
        starts.append((a, b, acc))
        acc += b - a
    for w in ed.get("words") or []:
        for a, b, base in starts:
            if a - 0.02 <= w["s"] <= b + 0.02:
                out.append((base + max(0.0, w["s"] - a), w["w"]))
                break
    return out


def main():
    pid, video = sys.argv[1], Path(sys.argv[2])
    rj = video.parent / (video.stem + "_check") / "report.json"
    if not rj.exists():
        print(f"no QC report for {video.name}: nothing to review")
        return
    rep = json.loads(rj.read_text(encoding="utf-8"))
    flags = [f for f in rep.get("flags", []) if not f.get("claude")][:MAX_FLAGS]
    if not flags:
        print("no open QC flags: no Claude call needed")
        return
    words = draft_words(pid)
    items, blocks = [], []
    for n, f in enumerate(flags):
        if f.get("sheet") and (rj.parent / f["sheet"]).exists():
            items.append((str(rj.parent / f["sheet"]), None, f"F{n} {f['type']} {fmt(f['t'])}"))
        t0, t1 = f["t"], f.get("end") or f["t"]
        said = " ".join(w for s, w in words if t0 - 6 <= s <= t1 + 6)
        blocks.append(f"F{n} [{fmt(t0)}-{fmt(t1)}] {f['type']}: {f.get('note', '')}\n   words around it: {said or '(none / no transcript)'}")
    sheet = B.contact_sheet(items, str(rj.parent / "claude_sheet.png"), cols=3, w=520) if items else None
    prompt = f"""Automatic QC flagged these moments in a rendered YouTube video ({video.name}, {rep.get('info', {}).get('duration', '?')} s).
The attached image shows each flag's frame sheet, labelled F<n>.

{chr(10).join(blocks)}

For each flag decide: "real" (a viewer would notice a mistake: a cut mid-word or mid-sentence, a glitch, a shot that plays
twice by accident, a stuck/black frame, a flash of the wrong thing) or "fine" (intentional: title hold, quick deliberate
cut, still product shot, normal talking). Changes INSIDE a screen recording are the creator's own actions and are fine:
clicking through product photos, scrolling, a page loading, a static page while he talks. Only call a flash/repeat real
when the frames show an edit seam (a different camera/scene for a split second, a black or garbage frame). For real ones give a fix in Studio note syntax using the video's own times:
"cut 1:22.0-1:23.4" (remove), "protect 2:03-2:10" (keep), or a short plain instruction.
Reply with ONLY JSON: {{"flags":[{{"n":0,"verdict":"real|fine","why":"<10 words>","fix":"<note or empty>"}}], "summary":"<one sentence>"}}"""
    ans = B.ask("draft_qc", prompt, images=[sheet] if sheet else [], model="sonnet")
    if not isinstance(ans, dict):
        print("Brain QC review skipped (no answer); the QC flags stand as they are")
        return
    by = {int(d["n"]): d for d in ans.get("flags") or [] if str(d.get("n", "")).isdigit()}
    md = [f"# AI QC review: {video.name}", "", ans.get("summary", ""), "", "| time | flag | verdict | why | suggested note |", "|---|---|---|---|---|"]
    real = 0
    for n, f in enumerate(flags):
        d = by.get(n)
        if not d:
            continue
        ok = d.get("verdict") != "real"
        real += not ok
        f["claude"] = {"verdict": "fine" if ok else "real", "why": d.get("why", ""), "fix": d.get("fix", "")}
        f["note"] = (f"✔ AI: fine ({d.get('why', '')}). " if ok else f"⚠ AI: REAL ({d.get('why', '')}) fix: {d.get('fix', '')}. ") + f.get("note", "")
        md.append(f"| {fmt(f['t'])} | {f['type']} | {'fine' if ok else '**REAL**'} | {d.get('why', '')} | {d.get('fix', '')} |")
    rj.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    (rj.parent / "claude_review.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"Brain QC: {real} real problem(s), {len(by) - real} fine  - {ans.get('summary', '')}")
    for n, f in enumerate(flags):
        if f.get("claude", {}).get("verdict") == "real":
            print(f"  REAL {fmt(f['t'])} {f['type']}: {f['claude']['why']}  ->  {f['claude']['fix']}")


def max_secs():
    """wall-clock cap for the whole review (user 2026-10-26: "cap the AI QC step so a slow reply can't hold the build up";
    a slow Claude reply took 9 min on top 5 reselling spring): env STUDIO_QC_MAX_S, else data/settings.json
    claude_qc_max_s, else 180 s. 0 = no cap."""
    try:
        s = json.loads((Path(__file__).resolve().parents[2] / "data" / "settings.json").read_text(encoding="utf-8"))
    except Exception:
        s = {}
    return float(os.environ.get("STUDIO_QC_MAX_S") or s.get("claude_qc_max_s", 180))


def give_up(secs):
    print(f"Brain QC review skipped: no answer within {secs:.0f} s; the QC flags stand as they are", flush=True)
    os._exit(0)   # exit 0 = done, not failed (a failed step is retried by jobs.py)


if __name__ == "__main__":
    cap = max_secs()
    if cap > 0:
        import threading
        t = threading.Timer(cap, give_up, args=(cap,))
        t.daemon = True
        t.start()
    try:
        main()
    except Exception as e:   # a review is a bonus: never fail the build
        print(f"Brain QC review skipped: {e}")

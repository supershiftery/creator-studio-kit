"""Revision: the user watches a draft and writes notes the way they talk ("2:20 remove 'to'", "cut at 3:02, pick back up
at 3:24 where I say another way to save money", "8:29 weird clip, should move on"). Claude maps every note onto the draft
transcript (same sentence ids as take_review), each cut lands on measured audio quiet, and the notes go into
work/extra_cuts.json as exact user cuts. The current draft is kept as "<name> - DRAFT vN.mp4", so the pipeline's resumed
rebuild produces vN+1. Every note is also saved as a lesson that the next videos' take review learns from.
(User 2026-10-21: "a revision button ... it would do most of the work, but I would still have to watch through the video".)

Usage: python revise.py <project> [notes.txt]     (default: work/revision_notes.txt)
"""
import json, os, re, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import take_review as R  # noqa: E402

PROMPT = """The creator of a YouTube tutorial watched a draft of their video and wrote revision notes. The times in the \
notes are DRAFT times (the intro is included); the transcript below shows each kept sentence with its id and draft time. \
"[cut N s]" marks where material was already removed.

Turn every note into edits on this transcript:
- "cuts": remove from a sentence (optionally from given words inside it) up to where the kept part resumes.
- "words": drop word(s) at the START of one sentence.
- "other": anything that is not a cut (music, graphics, layout, restoring removed material) -> a short instruction.
- "lessons": for each note, one line in their voice that would help an editor catch the same kind of mistake in their NEXT \
video without being told (general, not tied to this video's times), e.g. "When I start explaining something, stop, and \
explain it again in different words, cut the first try up to where the second one starts."
Notes are casual and times can be off by a few seconds: match them to the transcript by what is said. Keep both sides of \
every cut whole and grammatical so the join sounds natural.

Answer with ONLY a JSON object:
{"cuts": [{"from": "S12", "from_text": "", "to": "S15", "to_text": "", "why": "note it answers"}],
 "words": [{"sid": "S20", "drop": "to", "why": "note"}], "other": ["..."], "lessons": ["..."]}

NOTES
"""


def draft_path(project):
    out = os.path.join(project, "output")
    name = os.path.basename(project.rstrip("\\/"))
    return os.path.join(out, f"{name} - DRAFT.mp4"), name


def revise(project, notes_path=None):
    work = os.path.join(project, "work")
    notes_path = notes_path or os.path.join(work, "revision_notes.txt")
    notes = open(notes_path, encoding="utf-8").read().strip()
    if not notes:
        raise SystemExit("no revision notes")
    words = json.load(open(os.path.join(work, "words.json")))
    keep = json.load(open(os.path.join(work, "cuts.json")))["keep"]
    intro = os.path.join(project, "edit", "intro", "renders", "intro.mp4")
    ilen = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", intro],
                                capture_output=True, text=True).stdout or 0) if os.path.exists(intro) else 0.0
    kw, sents = R.kept_sentences(words, keep)
    ans, cost = R.ask_claude(PROMPT + notes + "\n\nTRANSCRIPT\n" + R.transcript_lines(kw, sents, ilen), work)
    env, thr = R.load_audio_env(work)
    hist_path = os.path.join(work, "revisions.json")
    hist = json.load(open(hist_path)) if os.path.exists(hist_path) else []
    n = len(hist) + 1
    cuts = R.to_cuts(kw, sents, ans, env, thr, f"revision {n}")
    ex_path = os.path.join(work, "extra_cuts.json")
    extra = json.load(open(ex_path)) if os.path.exists(ex_path) else []
    json.dump(extra + cuts, open(ex_path, "w"), indent=1)
    # keep the draft these notes were written on: "<name> - DRAFT v<n>.mp4"
    cur, name = draft_path(project)
    if os.path.exists(cur):
        shutil.move(cur, os.path.join(project, "output", f"{name} - DRAFT v{n}.mp4"))
    les = [l.strip() for l in ans.get("lessons", []) if l.strip()]
    if les:
        with open(R.LESSONS, "a", encoding="utf-8") as f:
            f.write("".join(f"- {l}\n" for l in les))
    hist.append({"n": n, "when": time.strftime("%Y-%m-%d %H:%M"), "notes": notes, "cuts": cuts, "other": ans.get("other", []),
                 "lessons": les, "cost": cost})
    json.dump(hist, open(hist_path, "w"), indent=1)
    print(f"revision {n}: {len(cuts)} cuts from {len(notes.splitlines())} note lines; draft v{n} kept; {len(les)} lessons saved")
    for c in cuts:
        print(f"  {c['s']:8.2f}-{c['e']:8.2f}  {c['why'][:100]}")
    for o in ans.get("other", []):
        print(f"  NOT A CUT (needs a hand fix): {o}")
    return hist[-1]


if __name__ == "__main__":
    revise(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)

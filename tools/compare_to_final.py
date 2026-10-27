"""Learn from the user's own finished edit: align its words to the raw transcript and diff against my cut.
Usage: python compare_to_final.py <raw words.json> <finished words.json> <my cuts.json> [--report out.md]
Prints: where the finished video starts using raw footage (intro length), and
  OVER-KEPT = raw words I kept that the user cut,  OVER-CUT = raw words the user kept that I cut."""
import difflib, json, re, sys
norm = lambda w: re.sub(r"[^a-z0-9$]", "", w.lower())
raw = [w for w in json.load(open(sys.argv[1])) if norm(w["w"])]
fin = [w for w in json.load(open(sys.argv[2])) if norm(w["w"])]
keep = json.load(open(sys.argv[3]))["keep"]
mine = [any(s <= w["s"] < e for s, e in keep) for w in raw]
final = [False] * len(raw)
sm = difflib.SequenceMatcher(None, [norm(w["w"]) for w in raw], [norm(w["w"]) for w in fin], autojunk=False)
first = None
for a, b, n in sm.get_matching_blocks():
    if n >= 3:  # ignore 1-2 word coincidences
        for k in range(n):
            final[a + k] = True
        if first is None:
            first = (fin[b]["s"], raw[a]["s"])
print(f"finished video reaches raw footage at {first[0]:.1f} s (= intro length); raw time there {first[1]:.1f} s")


def runs(flag):
    out, i = [], 0
    while i < len(raw):
        if flag(i):
            j = i
            while j + 1 < len(raw) and flag(j + 1):
                j += 1
            if j - i >= 2:
                out.append((raw[i]["s"], raw[j]["e"], " ".join(w["w"] for w in raw[i:j + 1])))
            i = j + 1
        else:
            i += 1
    return out


fmt = lambda t: f"{int(t // 60)}:{t % 60:05.2f}"
lines = ["## OVER-KEPT (I kept, user cut)"] + [f"- {fmt(s)}-{fmt(e)} ({e - s:.1f} s): {t}" for s, e, t in runs(lambda i: mine[i] and not final[i])]
lines += ["", "## OVER-CUT (user kept, I cut)"] + [f"- {fmt(s)}-{fmt(e)} ({e - s:.1f} s): {t}" for s, e, t in runs(lambda i: final[i] and not mine[i])]
txt = "\n".join(lines)
print(txt)
if "--report" in sys.argv:
    open(sys.argv[sys.argv.index("--report") + 1], "w", encoding="utf-8").write(txt + "\n")

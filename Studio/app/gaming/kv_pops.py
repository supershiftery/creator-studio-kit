"""REJECTED 2026-10-24 for game-mode callouts (user: a late "Prison" box repeats what was said at the entry start and reads
random; keep the KV rank numbers only). Not called by any build; kept for a possible segment-label variant.

KV Digital body pack (user 2026-10-24: "build the 3 rule-based KV elements ... No memes"): pick keyword moments by RULE,
render each as a KV pixel box (transparent 60 fps MOV), write a settings overlay for assemble.py.

  python kv_pops.py <project> [--dry] [--out <overlay.json>]

Rules (no taste calls, so a build needs no revision for them):
- keyword = one of that section's server game modes (library.json servers[*].gamemodes), spoken in a KEPT piece;
- first mention per mode per section; never the server's own name; never right after don't/never/didn't (negative mention);
- not in the first CARD_ZONE s of a section (the Add Server card + lower third live there), not in a UI zoom (ui.json),
  not over an inserted clip or another settings.graphics item;
- at least GAP s between boxes, at most PER_SECTION per section;
- the box: KV pixel box (Minecraftia, stepped charcoal/red/orange) centred above the hotbar, 1.3 s, with ONE soft pitchless
  swoosh (the approved intro sound, k_pop1/2 at a low level).
Element 1 (the KV rank badge) is the IP card's --kv option: server-ip-card/build.py <video> <rank> --transparent --kv.
"""
import argparse
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

from glib import Project, say

CARD_ZONE, GAP, PER_SECTION, DUR = 12.6, 25.0, 3, 1.3
NEG = {"dont", "don", "never", "doesnt", "didnt", "hate", "wont"}
LIB = Path(r"{{KIT}}/tools/minecraft\library.json")
POP_HF = Path(r"{{KIT}}/assets\Graphics\HyperFrames\kv-pop")
SFX = [str(POP_HF / "assets" / "k_pop1.wav"), str(POP_HF / "assets" / "k_pop2.wav")]
SFX_VOL = 0.08


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]", " ", s).split()


def terms_for(server):
    """game mode -> list of token sequences that count as saying it ("Survival SMP" also counts as "survival")."""
    # a short form only when it names ONE mode of this server (PokéFind: "Pokémon" alone is every mode, so only the full
    # "Pokémon Survival" counts; the first dry run labelled a plain "Pokemon" as "Pokémon World")
    out = {}
    name = norm(server["name"])
    modes = server.get("gamemodes") or []
    cores = {}
    for mode in modes:
        toks = norm(mode)
        core = [t for t in toks if t not in ("smp", "world") and t not in name]
        cores[mode] = core[:1] if core and core[0] in ("survival", "skyblock", "prison", "pokemon") else core
    for mode in modes:
        toks = norm(mode)
        alts = [toks]
        c = cores[mode]
        if len(toks) > 1 and c and c != toks and sum(1 for m in modes if cores[m] and cores[m][0] == c[0]) == 1 \
                and sum(1 for m in modes if c[0] in norm(m)) == 1:
            alts.append(c)
        out[mode] = alts
    return out


def stem(t):
    return re.sub(r"(es|s)$", "", t) if len(t) > 4 else t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project"); ap.add_argument("--dry", action="store_true"); ap.add_argument("--out")
    a = ap.parse_args()
    P = Project(a.project, "final")
    lib = json.loads(LIB.read_text(encoding="utf-8"))
    # the library video = the one whose servers' names best match this project's section names
    sec_txt = " ".join(" ".join(norm(n)) for n, _, _ in P.sections).replace(" ", "")
    def score(v):
        return sum("".join(norm(lib["servers"][k]["name"])) in sec_txt for k in v.get("servers") or [] if k in lib["servers"])
    vid = P.doc.get("library_video") or max(lib["videos"], key=lambda k: score(lib["videos"][k]), default=None)
    order = lib["videos"][vid]["servers"] if vid in lib.get("videos", {}) else []
    tl = P.read("timeline-final.json") or {}
    keep = tl.get("keep") or P.keep
    secs = P.sections
    words = P.words
    ui = P.read("ui.json", []) or []
    busy = [(float(z["s"]) - 0.3, float(z["e"]) + 0.5) for z in ui]
    busy += [(float(g["raw"]) - 0.5, float(g["raw"]) + float(g.get("dur") or 5) + 0.5) for g in P.settings.get("graphics", []) or [] if "raw" in g]

    def kept(t):
        return any(x <= t <= y - DUR for x, y in keep)

    def body_t(t):   # spacing is judged in VIDEO time: two mentions 69 s apart in the recording can land 6 s apart after cuts
        acc = 0.0
        for x, y in keep:
            if x <= t <= y:
                return acc + t - x
            acc += y - x
        return None

    events = []
    for name, s0, s1 in secs:
        m = re.match(r"#(\d+)", name)
        if not m or not order:
            continue
        rank = int(m.group(1))
        srv = lib["servers"][order[len(order) - rank]]
        terms = terms_for(srv)
        ws = [w for w in words if s0 <= w["s"] < s1]
        toks = [stem(t) for w in ws for t in (norm(w["w"]) or [""])[:1]]
        first = next((x for x, y in keep if y > s0 and x >= s0 - 1), s0)   # the section's first kept second
        shown, last = set(), -1e9
        for i, w in enumerate(ws):
            if len([e for e in events if e["section"] == name]) >= PER_SECTION:
                break
            t = w["s"]
            bt = body_t(t)
            if bt is None or bt - (body_t(first) or 0) < CARD_ZONE or bt - last < GAP or not kept(t) or any(a_ <= t <= b_ for a_, b_ in busy)                     or any(abs(bt - (body_t(e["raw"]) or -1e9)) < GAP for e in events):
                continue
            # full mode names first, short forms after (longest match wins)
            cands = sorted(((len(alt), mode, alt) for mode, alts in terms.items() if mode not in shown for alt in alts), reverse=True)
            for _, mode, alt in cands:
                if [stem(x) for x in alt] == toks[i:i + len(alt)]:
                    # never on a negative mention (PokéFind: "I don't really play Pokemon survival, I think it's kind of weird")
                    if set(toks[max(0, i - 4):i]) & NEG:
                        break
                    events.append({"section": name, "raw": round(t - 0.05, 2), "mode": mode,
                                   "said": " ".join(x["w"] for x in ws[i:i + 3])})
                    shown.add(mode); last = bt
                    break
    for e in events:
        say(f"  {e['section']:22s} raw {e['raw']:8.2f}  [{e['mode']}]  heard: {e['said']}")
    say(f"{len(events)} KV keyword boxes")
    if a.dry:
        return
    out_dir = P.path / "Graphics" / "_kv test" / "keywords"
    out_dir.mkdir(parents=True, exist_ok=True)
    rendered = {}
    for e in events:
        if e["mode"] in rendered:
            continue
        f = out_dir / (re.sub(r"[^a-z0-9]+", "-", " ".join(norm(e["mode"]))).strip("-") + ".mov")
        if not f.exists():
            cfg = POP_HF / "cfg.json"
            cfg.write_text(json.dumps({"text": e["mode"]}, ensure_ascii=False), encoding="utf-8")
            subprocess.run([sys.executable, str(POP_HF / "build.py")], check=True)
            subprocess.run("npx --yes hyperframes@0.8.180 render --fps 60 --format mov --output " + f'"{f}"', cwd=POP_HF, shell=True, check=True,
                           capture_output=True)
        rendered[e["mode"]] = str(f)
    overlay = {"graphics": [{"raw": e["raw"], "file": rendered[e["mode"]], "dur": DUR, "sfx": SFX[n % 2], "sfx_vol": SFX_VOL}
                            for n, e in enumerate(events)]}
    out = Path(a.out) if a.out else P.path / "Graphics" / "_kv test" / "kv-overlay.json"
    out.write_text(json.dumps(overlay, indent=1, ensure_ascii=False), encoding="utf-8")
    say("wrote", out)


if __name__ == "__main__":
    main()

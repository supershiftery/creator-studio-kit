"""Half-size draft of a cut list (fast review render; full quality only after the user approves the cut).
Usage: python render_draft.py <source.mp4> <cuts.json> <out.mp4> [--audio-track N] [--privacy privacy.json] [--width 3840] [--fps 30] [--cq 19]
Keeps exactly the frames / audio packets of a select/aselect pass on frame-snapped times, so picture and sound drop the
same ranges and cannot drift.
Fast path (2026-10-24 speed pass): each kept piece is its own input, seeked to its first frame and trimmed to the exact
frame count / audio length the select pass keeps, so only the kept minutes are decoded (dhgate coupons, 17 min source,
14 pieces: 65 s -> 27.5 s; same 6210 frames; 4 frames differ by 1/60 s where the old fps filter rounded onto the next
source frame). The old single select pass is used when the source rate is not a whole multiple of --fps, with more than
60 pieces (one decoder per piece) or with RD_SELECT=1."""
import json, os, subprocess, sys
import numpy as np
src, cuts, out = sys.argv[1], json.load(open(sys.argv[2])), sys.argv[3]
track = sys.argv[sys.argv.index("--audio-track") + 1] if "--audio-track" in sys.argv else "0"
expr = "+".join(f"between(t,{s:.4f},{e - 0.0001:.4f})" for s, e in cuts["keep"])
width = sys.argv[sys.argv.index("--width") + 1] if "--width" in sys.argv else "1920"
fps_out = sys.argv[sys.argv.index("--fps") + 1] if "--fps" in sys.argv else "30"


def probe(stream, entry):
    return subprocess.run(["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", entry, "-of", "csv=p=0", src],
                          capture_output=True, text=True).stdout.split()


def seek_graph():
    """(inputs, graph) for the fast path, or None when it does not apply"""
    keep = cuts["keep"]
    if os.environ.get("RD_SELECT") == "1" or not keep or len(keep) > 60:
        return None
    num, den = (int(x) for x in probe("v:0", "stream=r_frame_rate")[0].split("/"))
    step = num / den / float(fps_out)
    if abs(step - round(step)) > 1e-6 or round(step) < 1:
        return None
    vp = np.sort(np.array([float(x) for x in probe("v:0", "packet=pts_time") if x not in ("", "N/A")]))
    ap = np.sort(np.array([float(x) for x in probe(f"a:{track}", "packet=pts_time") if x not in ("", "N/A")]))
    sr = int(probe(f"a:{track}", "stream=sample_rate")[0])
    dv, da = den / num, 1024 / sr
    inputs, chains, parts, k = [], [], [], 0
    for s, e in keep:
        v = vp[(vp >= s) & (vp <= e - 0.0001)]
        a = ap[(ap >= s) & (ap <= e - 0.0001)]
        if not len(v) or not len(a):
            return None
        inputs += ["-ss", f"{v[0] - dv / 4:.6f}", "-i", src, "-ss", f"{a[0]:.6f}", "-i", src]
        chains.append(f"[{k}:v]trim=end_frame={len(v)}[v{k}];"
                      f"[{k + 1}:a:{track}]atrim=end_sample={int(round((a[-1] + da - a[0]) * sr))}[a{k}]")
        parts.append(f"[v{k}][a{k}]")
        k += 2
    # every step-th frame of the joined 60 fps run = what fps=30 picks on N/FRAME_RATE timestamps
    pick = f"select='not(mod(n\\,{round(step)}))'," if round(step) > 1 else ""
    graph = (";".join(chains) + ";" + "".join(parts) + f"concat=n={len(keep)}:v=1:a=1[cv][ca];"
             f"[cv]{pick}setpts=N/{fps_out}/TB,scale={width}:-2[v];[ca]asetpts=N/SR/TB[a]")
    return inputs, graph


fast = seek_graph()
if fast:
    inputs, graph = fast
else:
    inputs = ["-i", src]
    graph = (f"[0:v]select='{expr}',setpts=N/FRAME_RATE/TB,scale={width}:-2,fps={fps_out}[v];"
             f"[0:a:{track}]aselect='{expr}',asetpts=N/SR/TB[a]")
vout = "v"
if "--privacy" in sys.argv:  # blur the address / phone number boxes found by privacy.py (always, in every render)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import privacy
    chain, vout = privacy.filter(json.load(open(sys.argv[sys.argv.index("--privacy") + 1])), cuts, scale=0.5)
    if chain:
        graph += ";" + chain
open(out + ".graph.txt", "w").write(graph)
subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-/filter_complex", out + ".graph.txt", "-map", f"[{vout}]", "-map", "[a]",
                "-c:v", "h264_nvenc", "-profile:v", "high", "-pix_fmt", "yuv420p", "-cq", sys.argv[sys.argv.index("--cq") + 1] if "--cq" in sys.argv else "26",
                "-c:a", "aac", "-b:a", "320k", out], check=True)  # 320k: this audio is re-encoded twice more (main, join)

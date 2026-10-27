import json, subprocess, os, shutil, time, hashlib
from concurrent.futures import ThreadPoolExecutor

# Renders every graphic in batch.json that is missing. Several at once (user 2026-10-21: graphics rendered one by one
# took ~9 min; keep the GPU sane): HF_JOBS renders in parallel (default 3), each with HF_WORKERS Chrome workers
# (default 4) instead of HyperFrames' "auto" (which assumes it has the whole machine). Rows that are identical apart
# from their output name (wipe1 / wipe2 ...) render once and are copied.
JOBS = int(os.environ.get("HF_JOBS", "3"))
WORKERS = os.environ.get("HF_WORKERS", "4")

rows = json.load(open("batch.json"))
os.makedirs("vars", exist_ok=True)  # new projects have no vars folder (Doordash builds failed here 2026-10-21)
# render cache (user 2026-10-22: faster revisions): a graphic is fully defined by its variables + the template, so a revision
# that re-plans the graphics only renders the cards whose text/look changed; the rest come back from renders\_cache.
CACHE = os.path.join("renders", "_cache")
os.makedirs(CACHE, exist_ok=True)
TPL = hashlib.sha1(b"".join(open(f, "rb").read() for f in ("index.html", "hyperframes.json") if os.path.exists(f))).hexdigest()[:12]


def ckey(r):
    return hashlib.sha1((TPL + json.dumps(r, sort_keys=True)).encode()).hexdigest() + ".mov"


todo, copies, from_cache = {}, [], 0
for r in rows:
    out = r.pop("outputPath")
    if os.path.exists(out) and os.path.getsize(out) > 100000:
        continue
    c = os.path.join(CACHE, ckey(r))
    if os.path.exists(c) and os.path.getsize(c) > 100000:
        shutil.copyfile(c, out)
        os.utime(c)   # recently used: survives the clean-up
        from_cache += 1
        continue
    key = json.dumps(r, sort_keys=True)
    if key in todo:
        copies.append((todo[key][0], out))
    else:
        todo[key] = (out, r)


def render(item):
    out, r = item
    vf = os.path.join("vars", os.path.basename(out) + ".json")
    json.dump(r, open(vf, "w"))
    t0 = time.time()
    res = subprocess.run(f'npx --yes hyperframes@0.8.181 render --format mov --quiet --workers {WORKERS} -o "{out}" --variables-file "{vf}"',
                         capture_output=True, text=True, shell=True)
    ok = res.returncode == 0 and os.path.exists(out)
    if ok:
        shutil.copyfile(out, os.path.join(CACHE, ckey(r)))
    print(out, f"OK {time.time() - t0:.0f}s" if ok else "FAIL " + (res.stderr or res.stdout)[-400:], flush=True)


t0 = time.time()
with ThreadPoolExecutor(max(1, JOBS)) as ex:
    list(ex.map(render, todo.values()))
for src, out in copies:
    if os.path.exists(src):
        shutil.copyfile(src, out)
        print(out, f"OK (same as {src})", flush=True)
for f_ in os.listdir(CACHE):   # unused for 7 days = stale
    if time.time() - os.path.getmtime(os.path.join(CACHE, f_)) > 7 * 86400:
        os.remove(os.path.join(CACHE, f_))
print(f"graphics: {len(todo)} rendered ({JOBS} at a time), {len(copies)} copied, {from_cache} from cache, {time.time() - t0:.0f}s", flush=True)

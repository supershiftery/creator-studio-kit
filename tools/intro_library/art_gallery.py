"""Write the shareable gallery page (claude.ai Artifact) + copy its media into a publish folder.
    python art_gallery.py <publish dir>
The page lists every template with a preview, and has Keep / Tweak / Drop + a note per template (stored in the
artifact's db collection "verdicts", one doc per template id) so the user can steer the library from their phone."""
import html, json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_intro as B  # noqa: E402

GAL = os.path.join(HERE, "gallery")
TYPE = {"review": ("Product review", "{{REVIEW_CHANNEL}} · DHgate", "Demo: the Moncler VO + Moncler B-roll"),
        "phone": ("Phone & app codes", "{{PHONE_CHANNEL}}", "Demo: the DoorDash test VO"),
        "gaming": ("Gaming", "{{GAMING_CHANNEL}} · Minecraft", "Demo: the Top 10 Servers VO, gameplay slots left empty")}


def main(dst, only=None):
    os.makedirs(os.path.join(dst, "previews"), exist_ok=True)
    os.makedirs(os.path.join(dst, "posters"), exist_ok=True)
    items = []
    for t in B.templates():
        pv = os.path.join(GAL, "previews", t["id"] + ".mp4")
        if not os.path.exists(pv) or (only and t["id"] not in only):
            continue
        shutil.copy(pv, os.path.join(dst, "previews", t["id"] + ".mp4"))
        shutil.copy(os.path.join(GAL, "posters", t["id"] + ".jpg"), os.path.join(dst, "posters", t["id"] + ".jpg"))
        meta = json.load(open(os.path.join(GAL, "previews", t["id"] + ".json")))
        items.append({"id": t["id"], "type": t["type"], "name": t.get("name", ""), "blurb": t.get("blurb", ""), "dur": meta.get("dur")})
    feat = os.path.join(dst, "moncler.mp4")
    mon = r"{{PROJECTS_ROOT}}/Moncler Intro/Moncler intro v3 - Smoke Words.mp4"
    if os.path.exists(mon):
        os.system(f'ffmpeg -v error -y -i "{mon}" -vf scale=1280:720 -c:v libx264 -crf 24 -c:a aac -b:a 160k -movflags +faststart "{feat}"')
    counts = {k: sum(1 for i in items if i["type"] == k) for k in TYPE}
    data = json.dumps(items)
    page = open(os.path.join(HERE, "art_gallery.html"), encoding="utf-8").read()
    page = page.replace("/*DATA*/[]", data).replace("/*TYPES*/{}", json.dumps(TYPE)).replace("/*COUNTS*/{}", json.dumps(counts))
    open(os.path.join(dst, "index.html"), "w", encoding="utf-8").write(page)
    files = ["moncler.mp4"] if os.path.exists(feat) else []
    files += [f"previews/{i['id']}.mp4" for i in items] + [f"posters/{i['id']}.jpg" for i in items]
    json.dump(files, open(os.path.join(dst, "files.json"), "w"))
    print(len(items), "templates;", "files:", len(files))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:] or None)

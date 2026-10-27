"""Build the merged Gen 5 Pokémon SFX library from The Sounds Resource rips.

Black/White (asset 487564) + Black 2/White 2 (asset 493224) are compared by waveform:
  identical          -> one copy (B2W2, native 65 kHz)
  same but fuller    -> B2W2 version (longer tail / native rate)
  actually different -> B2W2 as main + B/W kept as "<name>-bw"
  only in one game   -> kept
Internal names (SEQ_SE_KAIDAN...) are translated to plain names where known; the rest go under unlabelled/.
Output: <lib>/gen5/<category>/<name>.wav (trimmed, peak -3 dB, 48 kHz stereo) + catalog + audition page.

Usage: python pokemon_sfx.py <packs_dir> <library_dir>
"""
import html
import json
import os
import re
import subprocess
import sys

NAMES = {
    "SEQ_SE/SEQ_SE_DECIDE1": "ui/confirm-1", "SEQ_SE/SEQ_SE_DECIDE2": "ui/confirm-2", "SEQ_SE/SEQ_SE_DECIDE3": "ui/confirm-3",
    "SEQ_SE/SEQ_SE_DECIDE4": "ui/confirm-4", "SEQ_SE/SEQ_SE_DECIDE5": "ui/confirm-5", "SEQ_SE/SEQ_SE_DECIDE6": "ui/confirm-6",
    "SEQ_SE/SEQ_SE_CANCEL1": "ui/cancel-1", "SEQ_SE/SEQ_SE_CANCEL2": "ui/cancel-2", "SEQ_SE/SEQ_SE_CANCEL3": "ui/cancel-3",
    "SEQ_SE/SEQ_SE_SELECT1": "ui/cursor-1", "SEQ_SE/SEQ_SE_SELECT2": "ui/cursor-2", "SEQ_SE/SEQ_SE_SELECT3": "ui/cursor-3",
    "SEQ_SE/SEQ_SE_SELECT4": "ui/cursor-4", "SEQ_SE/SEQ_SE_DP_SELECT": "ui/cursor-dp",
    "SEQ_SE/SEQ_SE_OPEN1": "ui/menu-open-1", "SEQ_SE/SEQ_SE_OPEN2": "ui/menu-open-2", "SEQ_SE/SEQ_SE_CLOSE1": "ui/menu-close",
    "SEQ_SE/SEQ_SE_MESSAGE": "ui/text-blip", "SEQ_SE/SEQ_SE_BEEP": "ui/beep", "SEQ_SE/SEQ_SE_SAVE": "ui/save",
    "SEQ_SE/SEQ_SE_PC_ON": "world/pc-on", "SEQ_SE/SEQ_SE_PC_LOGIN": "world/pc-login", "SEQ_SE/SEQ_SE_PC_LOGOFF": "world/pc-logoff",
    "SEQ_SE/SEQ_SE_KAIDAN": "world/door-stairs-warp", "SEQ_SE/SEQ_SE_DANSA": "world/ledge-hop", "SEQ_SE/SEQ_SE_WALL_HIT": "world/wall-bump",
    "SEQ_SE/SEQ_SE_BICYCLE": "world/bike-bell", "SEQ_SE/SEQ_SE_RECOVERY": "world/heal-pokemon-center", "SEQ_SE/SEQ_SE_KON": "world/knock",
    "SEQ_SE/SEQ_SE_OCHIBA_01": "world/fallen-leaves-1", "SEQ_SE/SEQ_SE_OCHIBA_02": "world/fallen-leaves-2",
    "SEQ_SE/SEQ_SE_PASA1": "world/rustle-1", "SEQ_SE/SEQ_SE_PASA2": "world/rustle-2",
    "SEQ_SE/SEQ_SE_NAGERU": "battle/ball-throw", "SEQ_SE/SEQ_SE_NAGERU2": "battle/ball-throw-2",
    "SEQ_SE/SEQ_SE_BOWA1": "battle/ball-pop-1", "SEQ_SE/SEQ_SE_BOWA2": "battle/ball-pop-2", "SEQ_SE/SEQ_SE_BOWA3": "battle/ball-pop-3",
    "SEQ_SE/SEQ_SE_GETTING": "battle/ball-shake-catch", "SEQ_SE/SEQ_SE_HINSHI": "battle/faint", "SEQ_SE/SEQ_SE_NIGERU": "battle/run-away",
    "SEQ_SE/SEQ_SE_EXP": "battle/exp-fill", "SEQ_SE/SEQ_SE_EXPMAX": "battle/exp-full", "SEQ_SE/SEQ_SE_LVUP": "battle/level-up-blip",
    "SEQ_SE/SEQ_SE_KOUKA_H": "battle/hit-super-effective", "SEQ_SE/SEQ_SE_KOUKA_M": "battle/hit-normal", "SEQ_SE/SEQ_SE_KOUKA_L": "battle/hit-not-very-effective",
    "SEQ_SE/SEQ_SE_MEET_01": "battle/encounter-1", "SEQ_SE/SEQ_SE_MEET_02": "battle/encounter-2", "SEQ_SE/SEQ_SE_MEET_03": "battle/encounter-3",
    "SEQ_SE/SEQ_SE_MEET_04": "battle/encounter-4", "SEQ_SE/SEQ_SE_TOUJOU_INTRO": "battle/entrance-intro", "SEQ_SE/SEQ_SE_TOUJOU_SMALL": "battle/entrance-small",
    "SEQ_SE/SEQ_SE_TOUJOU_MID": "battle/entrance-mid", "SEQ_SE/SEQ_SE_TOUJOU_LARGE": "battle/entrance-large",
    "SEQ_SE/SEQ_SE_ROTATION_B": "battle/rotation-b", "SEQ_SE/SEQ_SE_ROTATION_S": "battle/rotation-s", "SEQ_SE/SEQ_SE_TRIPLE_S": "battle/triple-shift",
    "SEQ_SE/SEQ_SE_DEAD": "battle/dead", "SEQ_SE/SEQ_SE_ZORO_01": "battle/zoroark-illusion",
    "SEQ_SE/SEQ_SE_LOGO_01": "misc/logo-1", "SEQ_SE/SEQ_SE_LOGO_02": "misc/logo-2", "SEQ_SE/SEQ_SE_LOGO_03": "misc/logo-3",
    "SEQ_ME/SEQ_ME_POKEGET": "jingle/caught-a-pokemon", "SEQ_ME/SEQ_ME_LVUP": "jingle/level-up", "SEQ_ME/SEQ_ME_ITEM": "jingle/item-obtained",
    "SEQ_ME/SEQ_ME_KEYITEM": "jingle/key-item-obtained", "SEQ_ME/SEQ_ME_ITEM_MYSTERY": "jingle/mystery-gift", "SEQ_ME/SEQ_ME_BADGE": "jingle/badge-get",
    "SEQ_ME/SEQ_ME_SHINKAOME": "jingle/evolution-congrats", "SEQ_ME/SEQ_ME_TAMAGO_GET": "jingle/egg-received", "SEQ_ME/SEQ_ME_WAZA": "jingle/move-learned",
    "SEQ_ME/SEQ_ME_WASURE": "jingle/move-forgotten", "SEQ_ME/SEQ_ME_KINOMI": "jingle/berry-obtained", "SEQ_ME/SEQ_ME_ACCE": "jingle/accessory-obtained",
    "SEQ_ME/SEQ_ME_BPGET": "jingle/bp-obtained", "SEQ_ME/SEQ_ME_ASA": "jingle/morning", "SEQ_ME/SEQ_ME_CALL": "jingle/xtransceiver-call",
    "SEQ_ME/SEQ_ME_CALL_LONG": "jingle/xtransceiver-call-long", "SEQ_ME/SEQ_ME_QUIZ": "jingle/quiz",
    "SEQ_ME/SEQ_ME_MISSION_START": "jingle/mission-start", "SEQ_ME/SEQ_ME_MISSION_CLEAR": "jingle/mission-clear", "SEQ_ME/SEQ_ME_MISSION_FAILED": "jingle/mission-failed",
    "SEQ_ME/SEQ_ME_END": "jingle/end", "SEQ_ME/SEQ_ME_DEL_POWER": "jingle/power-off", "SEQ_ME/SEQ_ME_KEY_OPEN": "jingle/key-unlock",
    "SEQ_ME/SEQ_ME_ZUKAN_01": "jingle/pokedex-1", "SEQ_ME/SEQ_ME_ZUKAN_02": "jingle/pokedex-2", "SEQ_ME/SEQ_ME_POKEWOOD": "jingle/pokestar-studios",
    "SEQ_ME/SEQ_ME_OTAMARO": "jingle/tympole",
}
for i in range(1, 7):
    NAMES[f"SEQ_ME/SEQ_ME_HYOUKA{i}"] = f"jingle/pokedex-rating-{i}"
for k in ("H", "M", "L", "KIDOU"):
    NAMES[f"SEQ_ME/SEQ_ME_AISHOU_{k}"] = f"jingle/compatibility-{k.lower()}"
for i in (1, 2, 3):
    NAMES[f"SEQ_ME/SEQ_ME_AVENUE_0{i}"] = f"jingle/join-avenue-{i}"
GROUPS = {"SEQ_SE_FLD": "field", "SEQ_SE_SYS": "system", "SEQ_SE_BE": "battle-effects", "SEQ_SE_MSCL": "musical", "SEQ_DEMO": "cutscene",
          "SEQ_SE_SW": "sw", "SEQ_SE_GYM": "gym-puzzles", "SEQ_SE_BREC": "battle-recorder", "SEQ_ME": "jingles", "SEQ_SE": "misc"}
SKIP = re.compile(r"DUMMY|DMY_")


def files(root):
    out = {}
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.lower().endswith(".wav"):
                out[os.path.relpath(os.path.join(dp, f), root).replace("\\", "/")[:-4]] = os.path.join(dp, f)
    return out


def peak(p):
    o = subprocess.run(["ffmpeg", "-hide_banner", "-i", p, "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.search(r"max_volume: ([-\d.]+)", o)
    return float(m.group(1)) if m else -99.0


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def plain(key):
    if key in NAMES:
        return NAMES[key]
    folder, name = key.split("/", 1)
    short = re.sub(r"^SEQ_(SE|ME)_", "", name).lower()
    return f"unlabelled/{GROUPS.get(folder, 'misc')}/{short}"


def main(packs, lib):
    bw = files(os.path.join(packs, "bw-sound-effects", "Sound Effects"))
    b2 = files(os.path.join(packs, "b2w2-sound-effects", "Sound Effects"))
    cmp_ = json.load(open(os.path.join(packs, "compare-bw-b2w2.json"), encoding="utf-8"))
    really_changed = {c[0][:-4] for c in cmp_["changed"] if c[1] < 0.98}
    jobs = []  # (key, src_path, out_name, origin)
    for key in sorted(set(bw) | set(b2)):
        if SKIP.search(key):
            continue
        name = plain(key)
        if key in b2:
            jobs.append((key, b2[key], name, "b2w2"))
            if key in bw and key in really_changed:
                jobs.append((key, bw[key], name + "-bw", "bw (different from b2w2)"))
        else:
            jobs.append((key, bw[key], name, "bw only"))
    out_root = os.path.join(lib, "gen5")
    cat = []
    for key, src, name, origin in jobs:
        pk = peak(src)
        if pk < -90:
            continue  # silent placeholder
        out = os.path.join(out_root, name + ".wav")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-af",
                        "silenceremove=start_periods=1:start_threshold=-60dB,areverse,silenceremove=start_periods=1:start_threshold=-60dB,areverse,"
                        f"volume={-3 - pk}dB", "-ar", "48000", "-ac", "2", out], check=True)
        cat.append({"name": name, "source": key, "from": origin, "seconds": round(dur(out), 2), "file": f"gen5/{name}.wav"})
    json.dump(cat, open(os.path.join(lib, "catalog-gen5.json"), "w", encoding="utf-8"), indent=1)
    rows = "".join(
        f'<tr><td>{html.escape(e["name"])}</td><td>{e["seconds"]}s</td><td><audio controls preload="none" src="{html.escape(e["file"])}"></audio></td>'
        f'<td class=s>{html.escape(e["source"])} · {html.escape(e["from"])}</td></tr>' for e in cat)
    page = ("<!doctype html><meta charset=utf-8><title>Gen 5 Pokemon SFX</title><style>body{font:14px system-ui;background:#16181d;color:#eee;margin:20px}"
            "td{padding:3px 10px;border-bottom:1px solid #2a2d35}.s{color:#888}input{padding:6px;width:340px;margin-bottom:10px}</style>"
            f"<h2>Gen 5 Pokémon SFX: Black/White + Black 2/White 2 merged ({len(cat)})</h2>"
            "<input placeholder='filter… (door, ball, jingle, field, -bw)' oninput=\"for(const r of document.querySelectorAll('tr'))"
            "r.style.display=r.innerText.toLowerCase().includes(this.value.toLowerCase())?'':'none'\"><table>" + rows + "</table>")
    open(os.path.join(lib, "audition-gen5.html"), "w", encoding="utf-8").write(page)
    named = sum(1 for e in cat if not e["name"].startswith("unlabelled"))
    print(f"gen5 library: {len(cat)} sounds ({named} named, {len(cat) - named} unlabelled, {sum(1 for e in cat if e['name'].endswith('-bw'))} B/W alternates)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

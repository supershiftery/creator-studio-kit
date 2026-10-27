"""Replay the intro checks on intros he has judged (2026-10-24). Approved ones should come out clean; the ones he called boring
(lv skatesta) must be FLAGGED for what he said. Run before/after any change to intro_check / build_intro:
    python regress_intros.py
Older approved intros (prada, asics, sp5der, s25) carry flags that match notes he gave on them before approving."""
import sys,os,json
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import intro_check as C
AE="{{PROJECTS_ROOT}}/"
sets=[("reselling","ultimate dhgate free reselling spreadsheet","good"),("amiri","amiri jeans dhgate","good"),("prada","dhgate prada cups","good"),("rick","dhgate rick owens","good"),("lvtrainer","lv trainer","good"),("cartier","dhgate cartier watch","good"),("jordan3","dhgate jordan 3","good"),("sp5der","best sp5der hoodie dhgate","good"),("s25","s25 ultra","good"),("yeezy","dhgate yeezy slides","good"),("asics","dhgate asics","good"),("skatesta","lv skatesta","bad")]
for lab,d,v in sets:
    b=AE+d+"/intro/build"
    I=json.load(open(b+"/intro.json",encoding="utf-8")); W=C._words(b)
    P=[p for p in C.measured(b,I,W) if p["kind"] in ("long","repeat","blank","same_kind","name")]
    print(f"{lab:10} {v:4} {'FLAGGED' if P else 'clean':8}", "; ".join(p["what"][:70] for p in P))

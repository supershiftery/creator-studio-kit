"""KV keyword box (transparent, 1.3 s): cfg.json {"text": "..."} -> index.html. Used by {{STUDIO_NAME}} gaming/kv_pops.py."""
import html, json
from pathlib import Path
HERE = Path(__file__).parent
cfg = json.loads((HERE / "cfg.json").read_text(encoding="utf-8"))
words = cfg["text"].split()
spans = "".join(f"<span>{html.escape(w)}</span>" for w in words)
tpl = (HERE / "src" / "template.html.tpl").read_text(encoding="utf-8")
(HERE / "index.html").write_text(tpl.replace("__SPANS__", spans), encoding="utf-8")
print("kv-pop:", cfg["text"])

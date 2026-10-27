"""Text-based privacy matching: Windows' built-in OCR (local, free) reads the phone screen and every line that holds
one of the user's private terms (home addresses, real name) gets boxed. Works in any app, unlike the old Uber-only
template snippets (user 2026-10-21: the DoorDash address was never caught).

The terms live in privacy_terms.json next to this file (local only; never copy them into notes, logs or chats).
  {"addresses": ["123 Main St Town ST 00000", ...], "names": ["First Last", ...]}
"""
import asyncio
import difflib
import json
import os
import re

import cv2
import numpy as np
from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter

TERMS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "privacy_terms.json")
# words too common to flag on their own ("hidden fees", "Main course"); they count only next to a strong word
STREET_WORDS = {"dr", "drive", "ter", "terrace", "st", "street", "rd", "road", "ave", "avenue", "ln", "lane", "ct", "court", "blvd",
                "way", "pl", "place", "cir", "circle", "pkwy", "hwy", "apt", "unit", "suite", "east", "west", "north", "south"}
STATES = {"ga", "ma", "georgia", "massachusetts"}

_engine = None
_loop = None


def _norm(s):
    return re.sub(r"[^a-z0-9 ]+", " ", s.lower()).split()


def load_terms(path=TERMS_FILE):
    """-> (strong words, weak words, zips/numbers, name pairs). Strong = the distinctive street/town words."""
    t = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    strong, weak, numbers = set(), set(), set()
    for a in t.get("addresses", []):
        for w in _norm(a):
            if w.isdigit():
                numbers.add(w)
            elif w in STREET_WORDS or w in STATES or len(w) < 4:
                weak.add(w)
            else:
                strong.add(w)
    names = [tuple(_norm(n)) for n in t.get("names", [])]
    return strong, weak, numbers, names


def _like(w, target, cut=0.8):
    return w == target or (len(w) >= 4 and difflib.SequenceMatcher(None, w, target).ratio() >= cut)


import threading
_tls = threading.local()


def engine():
    """one OCR engine + event loop PER THREAD (2026-10-22: the privacy scan runs its passes in parallel; a shared loop
    can't be driven from two threads)"""
    if getattr(_tls, "engine", None) is None:
        _tls.engine = OcrEngine.try_create_from_user_profile_languages()
        _tls.loop = asyncio.new_event_loop()
    return _tls.engine


def ocr(img):
    """img: gray or BGR ndarray -> [(line text, [(word, x, y, w, h), ...])] in img pixels."""
    eng = engine()
    bgra = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA if img.ndim == 2 else cv2.COLOR_BGR2BGRA)
    h, w = bgra.shape[:2]
    dw = DataWriter()
    dw.write_bytes(bgra.tobytes())
    bmp = SoftwareBitmap.create_copy_from_buffer(dw.detach_buffer(), BitmapPixelFormat.BGRA8, w, h)
    res = _tls.loop.run_until_complete(eng.recognize_async(bmp))
    out = []
    for ln in res.lines:
        words = []
        for wd in ln.words:
            r = wd.bounding_rect
            words.append((wd.text, int(r.x), int(r.y), int(r.width), int(r.height)))
        out.append((ln.text, words))
    return out


def private_boxes(lines, terms, strict=False):
    """Lines that reveal a private term -> [(what, [x, y, w, h])]. A line is private when it holds a strong address word
    (street / town name), a ZIP or house number NEXT TO a street word, or a full name; a wrapped address ("Deliver to
    17 Hidden" / "Ponds Dr") is caught because every strong word is enough on its own."""
    strong, weak, numbers, names = terms
    out = []
    toks = [[w for w in _norm(t)] for t, _ in lines]
    for i, (text, words) in enumerate(lines):
        tk = toks[i]
        hit, also = None, None
        exact = any(w in strong for w in tk)
        fuzzy = any(_like(w, s) for w in tk for s in strong)
        if exact or (fuzzy and not strict):
            hit = "address"
        elif fuzzy:
            # strict (the final pass/fail sweep): a one-letter-off word alone is OCR noise ("ponse nc n" from an app
            # screen failed a clean draft, Doordash 2026-10-21); it needs a second address piece on this or a next line
            near = [t for j in (i - 1, i, i + 1) if 0 <= j < len(toks) for t in toks[j]]
            others = sum(1 for t in near if t in numbers or t in weak or any(_like(t, s) for s in strong))
            if others >= 2:
                hit = "address"
        elif any(w in numbers and len(w) == 5 for w in tk):
            hit = "zip"
        else:
            for nm in names:
                if len(nm) >= 2 and any(_like(tk[k], nm[0]) and _like(tk[k + 1], nm[1]) for k in range(len(tk) - 1)):
                    hit = "name"
                # last name alone on the line after/before the first name (a wrapped name): the box takes in BOTH lines
                # (Uber codes october 2026-10-25: the Uber account header "FIRST / LAST" had only the last name blurred)
                elif len(nm) >= 2 and any(_like(w, nm[-1]) for w in tk):
                    j = next((j for j in (i - 1, i + 1) if 0 <= j < len(toks) and any(_like(w, nm[0]) for w in toks[j])), None)
                    if j is not None:
                        hit, also = "name", lines[j][1]
        if hit and words:
            ws = list(words) + list(also or [])
            x0 = min(w[1] for w in ws)
            y0 = min(w[2] for w in ws)
            x1 = max(w[1] + w[3] for w in ws)
            y1 = max(w[2] + w[4] for w in ws)
            out.append((hit, [x0, y0, x1 - x0, y1 - y0]))
    return out

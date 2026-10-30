from pathlib import Path

from recipes import gaming, haul, phone, review, short, trim

RECIPES = {"gaming": gaming, "phone": phone, "review": review, "haul": haul, "short": short}
_ROUTED = ("steps", "job_steps", "apply_notes", "outputs", "timeline_info")


class _Recipe:
    """A type's recipe with the New Project options applied per project (user 2026-10-22):
    settings.trim_only -> recipes/trim.py instead of the full pipeline; settings.music / settings.privacy = False ->
    STUDIO_NO_MUSIC / STUDIO_NO_PRIVACY in every step's environment (the pipelines read those)."""

    def __init__(self, mod):
        self._m = mod

    def __getattr__(self, name):
        f = getattr(self._m, name)
        if name == "paths":   # trim-only: the type's paths, with the transcript / cut list / log of the trim steps
            return lambda doc, *a, **k: {**f(doc, *a, **k), **trim.paths(doc)} if trim.on(doc) else f(doc, *a, **k)
        if name not in _ROUTED:
            return f

        def call(doc, *a, **k):
            if name == "job_steps":   # a custom video type (my_style): its style + learned rules go into the project first
                import mystyle
                mystyle.sync(doc)
            out = (getattr(trim, name) if trim.on(doc) else f)(doc, *a, **k)
            if name == "job_steps":
                env = flags(doc)
                # the draft audit (~6 min re-transcribe after every render) is OFF unless asked for (user 2026-10-25: "why
                # is the draft still auditing? I thought we removed the audit"; he reviews + notes himself, it caught too little)
                from store import settings as _settings
                # one-take mode (2026-10-25, user: "if we got them down to one take, the speed wouldn't matter because
                # everything would be running overnight"): FIRST drafts built unattended (laptop worker / overnight) keep the
                # audit and its AI fix rounds, so the draft he opens already passed it; his own revision builds stay fast
                first_draft = (a[0] if a else k.get("action")) in ("draft", "all")
                if not ((doc.get("settings") or {}).get("draft_audit", _settings().get("draft_audit", False))
                        or (first_draft and one_take(doc))):
                    out = [st for st in out if st.get("id") != "audit"]
                for st in out:
                    st["env"] = {**(st.get("env") or {}), **env}
                out = with_captions(doc, (a[0] if a else k.get("action")), out)
                if (doc.get("settings") or {}).get("my_type"):   # a custom type's opening / ending / logo (my_style)
                    import mystyle
                    out = mystyle.with_bookends(doc, (a[0] if a else k.get("action")), out, _QC_IDS)
            return out
        return call


def one_take(doc):
    """settings.one_take (machine setting, ON on the laptop worker) unless the project turns it off (settings.one_take=false)"""
    from store import settings as _settings
    s = (doc.get("settings") or {}).get("one_take")
    return bool(_settings().get("one_take", False) if s is None else s)


def flags(doc):
    s = doc.get("settings") or {}
    env = {}
    if s.get("music") is False:
        env["STUDIO_NO_MUSIC"] = "1"
    if s.get("privacy") is False:
        env["STUDIO_NO_PRIVACY"] = "1"
    # Claude at the judgment points (intro director + picture check, QC flag review; {{KIT}}/tools\claude_brain.py)
    if s.get("claude") is False:
        env["CLAUDE_BRAIN"] = "0"
    # filler words per speaker (user 2026-10-22): project setting, else the channel's, else light. Light = the user's own
    # channels (um / uh only), heavy = talkers who fill (a friend's videos: "and yeah", "ya", "alright"). take_cuts reads it.
    from store import settings as _settings
    ch = next((c for c in _settings().get("channels", []) if c.get("name") == doc.get("channel")), {})
    # nothing set = auto (2026-10-23, "we shouldn't be filtering by friend"): take_cuts measures the talker's filler habit
    env["STUDIO_FILLERS"] = s.get("fillers") or ch.get("fillers") or "auto"
    # pause style (2026-10-23): natural (default) or tight = jump-cut pacing like the friend's Chime editor (take_cuts.py)
    env["STUDIO_PAUSES"] = s.get("pauses") or ch.get("pauses") or "natural"
    # the AI take review is frozen after draft 1 (take_review.py, 2026-10-22); settings.take_review = "fresh" re-asks
    if s.get("take_review") == "fresh":
        env["TAKE_REVIEW"] = "fresh"
    if s.get("my_type"):   # a custom video type: claude_brain puts the type's playbook + learned rules first (my_style)
        import mystyle
        env.update(mystyle.env(doc))
    return env


_QC_IDS = ("check", "claude_qc", "targets")


def with_captions(doc, action, steps):
    """settings.captions.on (OFF by default, user 2026-10-23) -> a Captions step right after the render is made, before the QC
    steps, on the video they check (tools/captions.py burns it in place, keeping the clean render in <project>/_captions).
    Also runs when captions were turned off, so an earlier burned render gets its clean copy back.
    Once a render was burned, every build first puts its clean copy back (--restore) and burns again after, so a pipeline
    that re-uses its last render (review "intro" re-joins onto output/final.mp4) never gets captions on top of captions. Phone "revise" has no QC step: captions go last, on the draft."""
    cap = (doc.get("settings") or {}).get("captions") or {}
    cap = {"on": True} if cap is True else cap   # older projects stored a plain true
    burned = (Path(doc["path"]) / "_captions" / "state.json").exists()
    # screen / trim-only edits burn their captions inside the one render (tools/trim_render.py, Chime 2026-10-23)
    if trim.on(doc) or action not in ("draft", "final", "all", "revise", "intro") or not (cap.get("on") or burned):
        return steps
    from recipes import common as C
    script = str(Path(__file__).resolve().parents[1] / "tools" / "captions.py")
    rp = {}
    try:
        rp = get(doc["type"]).paths(doc)
    except Exception:  # noqa
        pass
    i = next((n for n, st in enumerate(steps) if st.get("id") in _QC_IDS), None)
    video = next((c for c in (steps[i].get("cmd") or []) if str(c).lower().endswith(".mp4")), None) if i is not None else None
    pre = []
    if action == "revise":
        i, video = len(steps), rp.get("draft")
    elif action == "intro":
        video = rp.get("final")
        i = next((n for n, st in enumerate(steps) if st.get("id") == "intro"), -1) + 1
    if not video or i is None:
        return steps
    if burned:   # a pipeline that re-uses its last render (review intro re-join, resumed builds) must never get captions twice
        pre = [{"id": "captions_restore", "label": "Captions: clean render back before the build", "cwd": doc["path"], "force": True,
                "cmd": [C.python(), "-X", "utf8", script, "--restore", doc["path"], str(video)]}]
    st = {"id": "captions", "label": "Captions (" + str(cap.get("style") or "bold") + ")" if cap.get("on") else "Captions off: restore the clean render",
          "cmd": [C.python(), "-X", "utf8", script, doc["path"], str(video)], "cwd": doc["path"], "force": True,
          "env": dict((steps[i] if i < len(steps) else steps[-1]).get("env") or {})}
    return pre + steps[:i] + [st] + steps[i:]


def get(vtype):
    return _Recipe(RECIPES[vtype])

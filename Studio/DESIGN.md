# {{STUDIO_NAME}} — design notes (built overnight 2026-10-20/21)

One desktop app for the three kinds of videos the user makes, on top of the tools that already work:

| type | pipeline it drives | project home |
|---|---|---|
| gaming (Minecraft / realms / servers) | NEW `app/gaming/*` — a generalized port of the Top 5 Realms `Edit\work` scripts (take_cuts cutter, corner cam, B-roll reel, UI zooms, wipes, cards, sectioned music, chapters) | `{{GAMING_ROOT}}\<title>\` (+ `Edit\studio\`) |
| phone / app tutorial | `{{KIT}}/tools\phone_edit\pipeline.py` (resumable) + final render | `{{PROJECTS_ROOT}}\<name>\` |
| product review | `review_pipeline\scripts\edit_review.py` | `{{PROJECTS_ROOT}}\<name>\` |

Every project folder carries a `studio.json` (type, slots, settings, notes, tracker checklist). `data/projects.json` is only an index of paths.
Slots = drop zones: main footage, intro (rendered MP4 or VO wav), B-roll clips, thumbnail, description, articles, music overrides.
Jobs run as subprocesses with a live log; steps are skipped when their outputs are newer than their inputs (same idea as pipeline.py).
Tracker = per-project checklist (footage, intro, draft, approved, final, thumbnail, description, articles, Drive, to-do, published)
+ dashboard (per-channel weekly target, overdue, next 14 days). Drive hand-off copies FINALS only to `{{DRIVE_FINISHED}}\<Channel>\<title>\`.
To-do = a local list in data/todo.json (Inbox + one list per channel).

Backend: Python stdlib HTTP server (no framework), pywebview window (Edge WebView2). UI: vanilla HTML/JS/CSS, dark studio theme.

# UPDATE PROMPT

Run this after `UPDATE.cmd` finished. Open Claude Code in your **installed** kit folder (the one you use every day, not the
download) and paste everything under the line as your message.

---

I just updated my Creator Studio Kit with `update.py`. Finish the update with me:

1. Read `KIT_VERSION.json` (what's new) and tell me in a few plain lines what changed for the videos I make.
2. Run `python configure.py --check`: it must report 0 files with unfilled tokens. If not, fix it from `setup/answers.json`.
3. If `setup/LOCAL CHANGES.md` exists: those files had changes made on this PC (by me or by you during setup, e.g. the
   `libx264` switch for a PC without an NVIDIA card, my own rules, a fixed path). My old copies are in the newest zip in
   `_update_backups/`. For each file, compare my old copy with the new one, put MY changes back on top of the NEW version
   (keep the new features; never just copy the old file back), and tell me in one line per file what you kept. If a change
   is no longer needed because the new version already does it, say so and leave it out. Then delete `setup/LOCAL CHANGES.md`.
4. No NVIDIA GPU on this PC (`nvidia-smi` fails)? Check the new files still encode with `libx264` everywhere (new pipelines
   may have brought `h264_nvenc` back) and switch any that don't.
5. My skills in `~/.claude/skills/` are my rewritten copies. Compare each with the new `skills/*/SKILL.md` in the kit and
   merge in the new rules and steps that apply to my videos, in my wording, without undoing my own rules. New skills in the
   kit (for example `haul-edit`, `short-edit`): ask me with buttons whether I make that kind of video, and install + adapt
   only the ones I say yes to.
6. `python -m pip install -r setup/requirements.txt` (new packages, if any), then the selftest `python tools/claude_brain.py`.
7. Start the Studio (`Studio\Studio.cmd`), check it opens on Projects, and build a short trim of one of my existing
   recordings to make sure everything still works. Tell me how long it took.

Don't change my settings, channels, codes, privacy terms or projects unless I ask.

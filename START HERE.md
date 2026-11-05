# START HERE

This is a complete video editing studio that runs on your own PC, driven by Claude. It edits talking videos, phone/app tutorials,
product reviews, hauls, vertical Shorts, gaming list videos and screen recordings, then builds intros, picks the music, checks every render, and
cuts Shorts. It is editing software only: projects in, edited videos out (no thumbnails, to-do lists, uploads or website tools). You give it your raw recording; it gives you a draft. Your notes make it (and you) better.

## What you need
- A Windows 10/11 PC. An NVIDIA graphics card makes it much faster, but it isn't required. About 40 GB free on a fast drive.
- A Claude plan (Pro or Max). You don't need to install anything yourself: setup installs Claude Code, FFmpeg, Python and the rest.
- Your own raw recordings, and music you own or have a licence for. None is included.

## 2 steps
1. **Unzip** this folder somewhere permanent, for example `D:\Creator Studio Kit`. Don't leave it in Downloads.
2. **Double-click `SETUP.cmd`.** It installs everything (Windows may ask "allow changes?" a few times: click Yes) and puts a
   **Creator Studio** shortcut on your Desktop. Then the **Studio opens with a setup window** that walks you through the rest,
   one question per screen (about 3 minutes):
   - **Check your PC**: FFmpeg, Node.js, Claude Code and your Claude sign-in. Anything missing has a fix button (signing in opens
     your browser: press Authorize and the Studio notices by itself).
   - **Your recordings**: the folder your recorder saves to (it shows the folders it found with videos in them).
   - **Your projects**: where edits and drafts go (it suggests the drive with the most free space).
   - **Your music**: a mood library, and it can find the music already on your PC and sort it for you.
   - **Captions** on or off for new videos, and your **channel name** (optional).
   - **Done**: make your first project. Optionally let Claude finish the extras (its editing skills, your style, and
     switching renders over if you have no NVIDIA card).

   Change any answer later: Studio → **Settings → Setup → Run setup again**.

Setup takes about an hour, mostly downloads. Have one raw recording of each type of video you make ready to drop in.

Asked Claude Code to "set this up for me" instead? Same thing: Claude runs the installer, opens the Studio and its setup window
does the questions. If SETUP.cmd says **[MISSING]** for Python, double-click it once more. Still missing? Open Claude Code in
this folder and say "SETUP failed, read setup\setup_log.txt and fix it".

## Already have an older version? Update it (5 minutes)
Don't unzip the new kit over your old one, and don't set it up again.
1. Close the Studio.
2. Unzip the new `Creator Studio Kit.zip` somewhere temporary, for example your Downloads folder.
3. In that new folder, double-click **`UPDATE.cmd`**. It finds your installed kit, backs it up (`_update_backups/`), copies in the
   new files and fills them in with your saved answers. Your settings, channels, codes, privacy terms, projects and taught
   examples stay as they are.
4. Open Claude Code in your **installed** kit folder and paste **`UPDATE PROMPT.md`**. Claude explains what's new, puts back any
   changes you'd made to the old files, updates your skills and test-builds one video.
5. Delete the temporary folder. `KIT_VERSION.json` in your kit says which version you have.

## What's in the box
| Folder / file | What it is |
|---|---|
| `MASTER PROMPT.md` | the prompt that turns Claude into your editor + coach |
| `SETUP QUESTIONS.md` | what Claude will ask you (read it ahead if you like) |
| `EDITING PLAYBOOK.md` | every editing rule and the reason behind it: read this, it's the "eye" |
| `EYE TRAINING.md` | the weekly loop and drills for training your eye |
| `Studio/` | the desktop editor: your projects, build draft/final, the Gling-style editor, review notes + revisions, Shorts |
| `tools/` | the cutter, phone-video pipeline, intro library (60 intro templates), privacy blur, checkers |
| `review_pipeline/` | the product-review pipeline (two cameras, two mics, face cam, zooms, music) |
| `assets/` | motion-graphic templates (cards, wipes, intros) + QC tools |
| `skills/` | Claude skills for each video type (Claude rewrites them for you during setup) |
| `configure.py` + `setup/` | installer + the script that fills in your folders and channel names |
| `UPDATE.cmd` + `update.py` + `UPDATE PROMPT.md` | updates an installed kit to a newer version |
| `KIT_VERSION.json` | this version's number and what's new |

## Good to know
- Everything runs locally. Your footage never gets uploaded anywhere unless you ask for it.
- Claude never spends AI-generation credits, downloads music/videos, or posts anything without asking you first.
- The tools came from a creator who makes Minecraft, app-promo-code and product-review videos, so you'll see examples from those
  niches. Setup adapts it to yours.

# START HERE

This is a complete video editing studio that runs on your own PC, driven by Claude. It edits talking videos, phone/app tutorials,
product reviews, hauls, vertical Shorts, gaming list videos and screen recordings, then builds intros, picks the music, checks every render, and
cuts Shorts. It is editing software only: projects in, edited videos out (no thumbnails, to-do lists, uploads or website tools). You give it your raw recording; it gives you a draft. Your notes make it (and you) better.

## What you need
- A Windows 10/11 PC. An NVIDIA graphics card makes it much faster, but it isn't required. About 40 GB free on a fast drive.
- **Claude Code**, signed in with a Claude plan (Pro or Max). The desktop app or the terminal both work: https://claude.com/claude-code
- Your own raw recordings, and music you own or have a licence for. None is included.

## 3 steps
1. **Unzip** this folder somewhere permanent, for example `D:\Creator Studio Kit`. Don't leave it in Downloads.
2. **Open Claude Code in this folder** (desktop app: New session → choose this folder. Terminal: `cd` here, then type `claude`).
3. **Open `MASTER PROMPT.md`**, copy everything under the line, and paste it as your first message. Claude reads the kit, installs
   what's missing, asks you the setup questions (mostly click-buttons), configures everything, and does your first edit with you.

Setup takes about an hour, mostly downloads. Have one raw recording of each type of video you make ready to drop in.

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

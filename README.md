# Browser Video Recorder

**A Claude Code skill that records videos playing in your web browser to MP4 files, so you can watch
them offline.** Recorded lectures, course replays, webinars, meeting recordings, training videos.
Give your agent one course link and it finds the videos, downloads what the site offers, and records
the rest overnight with OBS Studio.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Platform: Windows](https://img.shields.io/badge/platform-Windows-0078D6)
![Claude Code skill](https://img.shields.io/badge/Claude%20Code-skill%20%2B%20plugin-D97757)
![Agent Skills](https://img.shields.io/badge/format-Agent%20Skills%20(SKILL.md)-555)
[![Last commit](https://img.shields.io/github/last-commit/Natboa/browser-video-recorder)](https://github.com/Natboa/browser-video-recorder/commits/main)

> Windows only · OBS Studio 28+ · Python 3.10+ · ffmpeg · Microsoft Edge or Google Chrome

## Who is this for?

- **Students** whose course site lets them *watch* lessons but has no download button.
- **Anyone catching up on missed lectures or webinars** who wants to watch on a plane, a train, or with slow internet.
- **People who archive** training videos or meeting recordings before access expires.

If a site already offers a download button, the skill uses that. It records only what can't be downloaded.

## Quick start

1. **Install the skill into your agent** (once). In Claude Code:

   ```
   /plugin marketplace add Natboa/browser-video-recorder
   /plugin install browser-video-recorder@browser-video-recorder
   ```

   No command line? Open Claude Code and paste this instead, and the agent installs it itself:

   > *Install the Claude Code skill from https://github.com/Natboa/browser-video-recorder, then run its setup check.*

2. **Restart Claude Code**, or open a new session. A running session doesn't pick up a newly installed skill.
3. **Ask for your videos.** The agent first checks that OBS, Python and ffmpeg are installed (and asks before installing anything):

   ```
   /record-videos https://your-course-site.example/course
   ```

   or in plain words: *"Record these 6 lessons so I can watch them offline: …"*

## Contents

- [Who is this for?](#who-is-this-for)
- [Quick start](#quick-start)
- [Install](#install)
- [Requirements](#requirements)
- [Use it](#use-it)
- [What you get](#what-you-get)
- [How it works](#how-it-works)
- [Quality checks](#quality-checks)
- [Trimming silences (optional)](#trimming-silences-optional)
- [Boundaries](#boundaries)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)
- [Project layout](#project-layout)

## Install

"Installing" means making the skill's folder (`SKILL.md` and its scripts) available to your agent, so
it knows the skill exists and can follow it. The skill is just files; nothing runs until you ask for videos.

### Option A: Claude Code plugin (recommended)

```
/plugin marketplace add Natboa/browser-video-recorder
/plugin install browser-video-recorder@browser-video-recorder
```

The first line registers this GitHub repo as a source. The second downloads the skill from it.
It stays available in all future sessions. To update later: `/plugin marketplace update browser-video-recorder`.

### Option B: from a local clone

```powershell
git clone https://github.com/Natboa/browser-video-recorder
```

Then in Claude Code, point the plugin system at the folder:

```
/plugin marketplace add C:\path\to\browser-video-recorder
/plugin install browser-video-recorder@browser-video-recorder
```

### Option C: copy the skill folder only

Copy [`skills/browser-video-recorder`](skills/browser-video-recorder) to your personal skills folder
(this route doesn't include the `/record-videos` command):

```powershell
git clone https://github.com/Natboa/browser-video-recorder
Copy-Item -Recurse browser-video-recorder\skills\browser-video-recorder "$env:USERPROFILE\.claude\skills\"
```

### Other agents

The skill follows the open [Agent Skills](https://agentskills.io/) format (`SKILL.md` + `scripts/` +
`references/`). For an agent that supports it, copy the same folder into that agent's skills directory.
For one that doesn't, clone the repo, open the agent inside it, and tell it to read
`skills/browser-video-recorder/SKILL.md` and follow it. The scripts are plain Python and PowerShell.

## Requirements

Everything it needs. The agent checks these for you with
[`check_setup.py`](skills/browser-video-recorder/scripts/check_setup.py) and asks before installing
anything:

| Needed | Why | Install |
|---|---|---|
| **Windows 10/11** | OBS window capture, per-app audio capture, power requests | n/a |
| **[OBS Studio](https://obsproject.com/) 28 or newer** | does the recording; 28+ has the WebSocket remote control built in (no plugin) | `winget install OBSProject.OBSStudio` |
| **[Python](https://www.python.org/) 3.10+** on PATH | runs the scripts | `winget install Python.Python.3.12` |
| **[ffmpeg](https://ffmpeg.org/) + ffprobe** on PATH | saves MP4s, runs the checks, trims silences | `winget install Gyan.FFmpeg` |
| **Microsoft Edge** or **Google Chrome** | plays the videos (the installed browser is used; nothing extra downloads) | Edge comes with Windows · `winget install Google.Chrome` |
| Python packages [`obsws-python`](https://pypi.org/project/obsws-python/), [`playwright`](https://pypi.org/project/playwright/) | control OBS and the browser | `pip install -r skills/browser-video-recorder/scripts/requirements.txt` |

No admin rights or OBS plugins needed. An NVIDIA GPU is optional (OBS then uses NVENC; otherwise x264).

Check your machine any time:

```powershell
python skills\browser-video-recorder\scripts\check_setup.py
```

At run time you also need a **stable sound output** (built-in speakers; USB DACs, Bluetooth and
monitor audio can drop out and freeze playback), **the laptop lid open** and **the charger in**.

## Use it

Once installed, use the slash command:

```
/record-videos <link to a course, playlist or video page>
```

or just ask. The skill activates on phrases like:

- "Record these lessons so I can watch them offline"
- "Save this webinar replay, there is no download button"
- "Screen-record these 3 videos automatically while I sleep"
- "Record this course and cut out the long silences"
- "I need this lecture without internet"

The agent will:

1. **Ask first:** which videos, where to save them, whether you want silences trimmed (minimum
   length, padding, keep short remarks?), where the trimmed copies go, and whether to keep the
   originals. **One link is enough** for a course outline, playlist, channel or series page: the
   finder lists the videos it leads to (title, length) for you to confirm. If the site needs an
   account, it opens the page and you sign in yourself; nothing is ever typed for you.
2. **Download first:** videos whose site offers the file itself (a Download button, a "download
   options" list, a visible link to the MP4) are simply downloaded, instantly and in original quality. Only the
   rest is recorded. For a cloud folder (OneDrive, Google Drive, Dropbox) it tells you to use that
   service's Download instead.
3. **Set up:** OBS remote control (your setting is backed up and restored), a dedicated browser
   profile (you sign in once), a short sound check.
4. **Test:** record a test clip that runs past your screen-off timeout and check it, including a
   contact sheet of frames (so a recorded web page or overlay is caught, not just bad numbers).
5. **Run unattended** (lid open, charger in), checking the first finished video before trusting the
   rest of the night.
6. **Report** a table of every file (length vs expected, size, sound OK), then trim if you asked.

## What you get

- **Unattended batch recording.** Give it a list of video pages; it records them one after
  another in real time (a 3-hour lecture takes 3 hours), overnight if you like, and survives the
  chat being closed.
- **Clean recordings.** The video plays full screen in a dedicated browser window. OBS records only
  that window and only that browser's sound, so notifications, other windows, other monitors,
  your system volume and YouTube in your normal browser don't end up in the file.
- **Silent nights, usable PC.** You can **mute your master volume** (the recording still gets full
  sound, so nothing plays out loud overnight), and you can **open other programs on top of the
  recording window**. The one thing to avoid is *minimising* it.
- **Right shape, no extra black bars.** The recording takes the video's own shape and resolution
  (up to 1080p), whatever your screen's shape: no bars on all four sides on 16:10, ultrawide or
  portrait screens, or with old 4:3 films and vertical videos.
- **Works on most sites.** It finds the main `<video>` on the page by itself, including inside
  embedded players (iframes) and players that don't load until you press play. Sign in once in the
  recorder's own browser profile and it stays signed in.
- **No wasted nights.** Every run starts with a test clip that has to pass before hours of recording
  begin. Each file is checked afterwards.
- **Robust to real-world problems** found the hard way: buffering (recording pauses while the video
  stalls, then reloads and resumes), players that stop a second before the end without saying so,
  the screen turning off, laptops going to sleep, and USB audio devices dropping out.
- **Optional silence trimming.** Copies with long silent stretches removed. Every bit of talking is
  kept, with exact cut points (3 s after the last sound, 2 s before talking resumes, both
  configurable). There's also a review video of short remarks inside silent blocks, so you can
  decide whether they matter.

## How it works

```
videos.json ─► run_session.ps1 ─► record_videos.py ──► Edge/Chrome (own profile, full screen)
                    │                    │                   ▲  plays the <video>, pinned title
                    │                    ├── OBS WebSocket ───┘  window capture + that app's audio only
                    │                    ├── keep_awake (system + display power request)
                    │                    └── stall: pause OBS · stuck 5 min: reload & resume
                    │                        end: "ended", or no progress near the end → save MP4
                    └── check_recording.py (test clip first, then every file)
```

Why some things are done the way they are:

- **Hold at the start, start OBS, then play.** Nothing at the beginning is lost.
- **End detection by last known position.** Many players stop ~1 s before the end, never fire
  `ended`, and some remove the `<video>` element entirely. Without this the recorder would loop on
  the last second all night.
- **Display-required power request.** Browsers stop playing when the screen turns off. `SetThreadExecutionState`
  is ignored on Modern Standby laptops, so the skill uses `PowerCreateRequest`.
- **Separate browser profile with sandbox on and occlusion throttling off.** Playback keeps
  rendering when covered by other windows, and no "unsupported flag" warning bar appears in the video.

## Quality checks

`check_recording.py` runs on the test clip (strict) and on every finished file:

| Check | Catches |
|---|---|
| Length vs expected | stalls, early stops, repeated parts |
| Sound level per 2-min (test) / 30-min window | sound device dropped out, wrong window captured |
| Sampled frame brightness | black picture: DRM-protected video or a minimised window |
| Audio vs video stream length | sync problems |
| Long digital silences (listed) | breaks/breakout rooms in the source, worth knowing before trimming |
| Cut points (trimmed copies) | quiet before each cut, talking right after |

Things worth checking once per machine, with a 2-minute test: turn the system volume down to ~10%
(the recording must not get quieter) and play a YouTube video in your normal browser (it must not
appear in the recording).

## Trimming silences (optional)

```powershell
python scripts\trim_silence.py --input-dir "D:\Courses\My course" --dry-run   # see what would be cut
python scripts\trim_silence.py --input-dir "D:\Courses\My course" --min-minutes 4 --after 3 --before 2
python scripts\review_short_talk.py --input-dir "D:\Courses\My course" --output "D:\Courses\My course\Without silence\Review.mp4"
```

Originals are never modified. Trimmed copies are re-encoded (libx264, ~13× real time) so every cut
lands exactly where intended. In real course recordings this removed 20–45% of each lecture.

## Boundaries

This skill records what you are **already allowed to watch**, the same way you could with OBS or
Xbox Game Bar by hand. It is built to stay that way:

- **Official downloads first, recording second.** If the site itself offers a video as a download
  (a Download button or link, a "download options" list), it is downloaded, with your signed-in
  session when the site requires one, exactly as clicking that link would. If the download is
  refused, the video is recorded instead. For a cloud folder (OneDrive, Google Drive, Dropbox) it
  tells you to use that service's own Download.
- **Never pulls a stream out of a player.** It doesn't fetch a player's video address or get around
  a site that turned downloads off; that is what recording by playing is for.
- **No DRM circumvention.** Protected streams (Netflix-style) record as black frames by design. The
  recorder detects encrypted media and stops instead of trying to get around it.
- **Personal use.** Recordings are for your own offline viewing. Check the site's terms; some forbid
  recording.

## Troubleshooting

See [`references/troubleshooting.md`](skills/browser-video-recorder/references/troubleshooting.md):
player stuck or no sound (audio device), playback stopping when the screen turns off, the laptop
sleeping, the last-second reload loop, OBS "crash detected" / "not ready", stale file sizes while
recording, and the "filename too long" DLL error.

## FAQ

**Does it work on macOS or Linux?** Not yet. It relies on Windows window capture, per-app audio
capture and power requests. Contributions welcome.

**Can it record faster than real time?** No. It records playback, so a 3-hour video takes 3 hours.

**Can I use my computer while it records?** Yes. Open other programs, even on top of the
recording window, watch YouTube in your normal browser, move windows between screens. Just don't
**minimise** the recording window or click inside it, don't change the sound output device, and
keep the lid open.

**Will it play sound out loud all night?** Only if you let it. **Mute your master volume** (or turn
it down): the recording captures the browser's sound directly, so it still gets full, normal-level
audio while your speakers stay silent.

**My screen isn't 16:9 / the video is 4:3 or vertical. Will I get black bars?** No extra ones. The
recorder crops to where the video actually is on screen and records in the video's own shape.

**Which sites does it work on?** Anything that plays in an HTML5 `<video>` element without DRM or bot protection. Over 35 sites were tested end-to-end in October 2026: Vimeo, TED, Zoom replays, Internet Archive, PeerTube, Microsoft Learn, OneDrive/SharePoint and more. YouTube, DRM services and sites with a "checking your browser" wall don't work. Full table: [docs/compatibility.md](docs/compatibility.md).

**Why OBS and not ffmpeg screen capture?** OBS captures one window (even when covered) plus that
one app's audio, and its WebSocket API allows pausing exactly while the video buffers.

## Project layout

```
.claude-plugin/              plugin + marketplace manifests (Claude Code /plugin install)
commands/record-videos.md    the /record-videos slash command
docs/compatibility.md        tested sites and what fails
CHANGELOG.md                 release notes
skills/browser-video-recorder/
├── SKILL.md                 workflow the agent follows (when to use, questions to ask, steps)
├── scripts/
│   ├── check_setup.py       checks every prerequisite, prints install commands
│   ├── requirements.txt     Python packages
│   ├── find_videos.py       one link → list of videos to confirm (sign-in step, download offers)
│   ├── download_videos.py   downloads what the sites themselves offer, before any recording
│   ├── record_videos.py     browser + OBS recorder
│   ├── run_session.ps1      unattended run: download → test → record the rest → check each
│   ├── check_recording.py   file checks (length, audio, black frames, sync, cut points)
│   ├── obs_websocket.py     enable/restore OBS remote control (backs up your config)
│   ├── keep_awake.py        system + display power request; display-timeout check
│   ├── stop_and_save.py     stop early and save the partial recording
│   ├── diag_playback.py     "stuck / no sound" diagnosis
│   ├── trim_silence.py      silence-trimmed copies
│   ├── review_short_talk.py review video of short remarks inside silent blocks
│   └── common.py
└── references/troubleshooting.md
```

## License

[MIT](LICENSE)

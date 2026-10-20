# Browser Video Recorder

**A Claude Code skill that records videos playing in your browser to MP4, so you can watch them
offline.** Lectures, course replays, webinars, meeting recordings. Give your agent one course link:
it finds the videos, downloads what the site offers, and records the rest overnight with OBS Studio.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Platform: Windows](https://img.shields.io/badge/platform-Windows-0078D6)
![Claude Code skill](https://img.shields.io/badge/Claude%20Code-skill%20%2B%20plugin-D97757)
[![Last commit](https://img.shields.io/github/last-commit/Natboa/browser-video-recorder)](https://github.com/Natboa/browser-video-recorder/commits/main)

## Who is it for?

Students whose course site has no download button, anyone catching up on missed lectures or
webinars offline, and people archiving training videos before access expires. If a site offers a
download, the skill uses it and records only what can't be downloaded.

## Quick start

1. **Install the skill** (once). In Claude Code:

   ```
   /plugin marketplace add Natboa/browser-video-recorder
   /plugin install browser-video-recorder@browser-video-recorder
   ```

   Or paste this to your agent: *"Install the Claude Code skill from
   https://github.com/Natboa/browser-video-recorder, then run its setup check."*
2. **Restart Claude Code** (a running session doesn't see a new skill).
3. **Ask:**

   ```
   /record-videos https://your-course-site.example/course
   ```

   or in plain words: *"Record these 6 lessons so I can watch them offline."*

The agent checks your setup first and asks before installing anything.

## Install

"Installing" just makes the skill's folder (`SKILL.md` plus scripts) available to your agent. Nothing
runs until you ask for videos.

- **Plugin (recommended):** the two commands above. Update later with `/plugin marketplace update browser-video-recorder`.
- **Local clone:** `git clone https://github.com/Natboa/browser-video-recorder`, then
  `/plugin marketplace add C:\path\to\browser-video-recorder` and the same `/plugin install` line.
- **Just the skill:** copy [`skills/browser-video-recorder`](skills/browser-video-recorder) into
  `%USERPROFILE%\.claude\skills\` (no `/record-videos` command this way).
- **Other agents:** it follows the open [Agent Skills](https://agentskills.io/) format. Copy the
  same folder into that agent's skills directory, or open the agent in the cloned repo and tell it
  to follow `skills/browser-video-recorder/SKILL.md`.

## Requirements

Windows 10/11, [OBS Studio](https://obsproject.com/) 28+, Python 3.10+, ffmpeg, and Edge or Chrome.
The agent checks all of it for you. Details and install commands: [docs/requirements.md](docs/requirements.md).

## What you get

- **Unattended batch recording:** videos are recorded one after another, overnight if you like.
- **One link is enough:** a course, playlist or series page is listed for you to confirm.
- **Clean files:** only the video window and its sound, no notifications, no black bars.
- **No wasted nights:** a test clip must pass first, and every file is checked afterwards.
- **Optional silence trimming:** long quiet stretches (exercises, breaks) cut out of copies.

## Boundaries

It records what you are already allowed to watch. Official downloads come first, DRM and bot
protection are never bypassed (YouTube and Netflix-style services don't work), and recordings are for
your own offline use. [More](docs/boundaries.md).

## More

[Tested sites](docs/compatibility.md) · [How it works](docs/how-it-works.md) ·
[Trimming silences](docs/trimming-silences.md) · [FAQ](docs/faq.md) ·
[Troubleshooting](skills/browser-video-recorder/references/troubleshooting.md) · [Changelog](CHANGELOG.md)

## License

[MIT](LICENSE)

# How it works

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

## Project layout

```
.claude-plugin/              plugin + marketplace manifests (Claude Code /plugin install)
commands/record-videos.md    the /record-videos slash command
docs/                        compatibility, requirements, boundaries, FAQ, trimming, how it works
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

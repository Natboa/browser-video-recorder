---
name: browser-video-recorder
description: Record videos that play in a web browser (recorded lessons, lectures, webinars, course replays, meeting recordings) to local MP4 files for personal offline viewing, by playing them in a dedicated browser window and capturing it with OBS on Windows — unattended, overnight, with keep-awake, stall recovery, end detection and quality checks; optionally trims long silent stretches afterwards. Use this whenever the user wants to save, keep, archive or watch offline a video they can only stream in a browser and there is no download button, or wants to batch-record several course/lesson/webinar videos (even from one course or playlist link — it finds them, downloads what the site offers, records the rest), or asks to "record the lesson", "screen-record a video automatically", "save the recordings so I have them without internet", even if they don't mention OBS.
---

# Browser video recorder

Records videos the user can already watch in a browser by **playing them on screen and
screen-recording the playback** with OBS. Batches of multi-hour videos run unattended
(overnight), one after another, and every file is checked afterwards.

Windows only (uses OBS window capture, per-app audio capture and Windows power requests).

## Boundaries — read first

This tool records what the user is already allowed to watch, the same way they could with
Game Bar or OBS by hand. Keep it that way:

- **Look for an official route first**: a download button, an "offline" mode in the site's
  app, or asking the provider. If one exists, use it instead.
- **Download only what the site itself offers as a download** (a Download button/link, a
  "download options" list, a visible link to the file: `find_videos.py` stores it as
  `download_url`). `download_videos.py` fetches exactly that file with the recorder profile's
  session, as clicking the link would. If the site refuses it (401/403), record instead. For cloud
  folders, tell the user to use the service's own Download.
- **Never pull a stream out of a player** — don't fetch a `<video>` src/stream URL, and don't get
  around a site that turned downloads off or its access checks. That is what recording by playing
  is for.
- **Try every site; stop only when it is actually blocked.** Never refuse or skip a video because of
  which site it is (YouTube included): run the test clip and see. Stop, and tell the user, only when
  a real block shows up:
  - **DRM (Netflix-style):** the video records as black frames. The recorder refuses to start when it
    sees encrypted media (EME), and the test fails on black frames.
  - **The site cuts playback off in the automated browser** (for example "Something went wrong" after
    ~40 s, or a "checking your browser" wall): the recorder notices the reset, saves what it has and
    logs it. Report what was kept.
  When a block happens, don't look for workarounds: don't get around DRM or bot protection, and never
  solve a challenge for the user (they may pass it themselves in `--login` mode). Point to the site's
  official offline option if it has one (e.g. YouTube Premium downloads). Tested sites, including
  what failed, are in the project's docs/compatibility.md; it is a record of results, not a
  list of sites to refuse.
- Recordings are for the user's **personal offline use**. Mention once that the site's terms
  may forbid recording and that the risk is theirs — then help.

## What's in this skill

| File | Purpose |
|---|---|
| `scripts/check_setup.py` | Checks every prerequisite (Windows, Python, OBS, ffmpeg, Edge/Chrome, packages) and prints install commands |
| `scripts/requirements.txt` | Python packages (tested versions) |
| `scripts/record_videos.py` | The recorder: opens the browser, plays each video, drives OBS, pauses on stalls, detects the end, saves MP4s |
| `scripts/find_videos.py` | One link → many videos: lists the video pages a course/playlist/folder page leads to (with lengths) for the user to confirm, then adds the chosen ones to `videos.json` |
| `scripts/download_videos.py` | Download first: saves every video whose site offers the file itself (`download_url`, found by the finder) instead of recording it |
| `scripts/run_session.ps1` | Unattended runner: test clip → checks → all videos → per-file checks. Survives the chat closing |
| `scripts/check_recording.py` | Verifies a file: length, audio per window, silence, black frames (DRM), A/V sync |
| `scripts/obs_websocket.py` | Turns OBS remote control on/off (backs up and restores the user's config) |
| `scripts/keep_awake.py` | Holds a Windows power request (system + display) while a command runs |
| `scripts/stop_and_save.py` | Stops a run early and saves the partial video properly |
| `scripts/diag_playback.py` | Diagnoses "player stuck / no sound" problems |
| `scripts/trim_silence.py` | Optional: copies with long silences cut (exact cut points) |
| `scripts/review_short_talk.py` | Optional: one review video of short talk bits inside silent blocks |
| `references/troubleshooting.md` | Symptoms → causes → fixes found in real runs. Read when anything misbehaves |

## Workflow

### 1. Ask before doing anything

Ask these together (one message or a question tool), with sensible defaults:

1. **Which videos?** Either one page URL per video (and a file name each, e.g. `03 - Prompt Engineering`),
   or **one link** to a page that lists them (course outline, playlist, channel, series, shared folder).
   For one link, run the finder (needs the work folder from step 2):
   `python scripts/find_videos.py --config <work>ideos.json --url "<link>"` (add `--login` if the site
   needs an account: it opens the link, the user signs in and closes the window, then it searches).
   It prints the link groups it saw and checks the best group page by page: title, length, and
   whether each really has a video (or DRM, sign-in, bot check). **Show the list to the user
   and let them confirm** — the grouping is a guess; if it picked the site's menu, rerun with
   `--group N`. Then `--add all` (every confirmed video) or `--add 1,3-5`. Lengths become
   `expected_minutes`, which guards against recording a trailer or the wrong item.
   **Download comes first.** The finder also notes when a video's page offers the file itself (a
   Download link/button, a "download options" list, a visible link to an .mp4) and stores it as
   `download_url`; the run then downloads those (instant, original quality) and records only the rest.
   That covers only what the site itself offers — never pull a stream out of a player whose owner
   turned downloads off (that is what recording-by-playing is for). For a cloud storage folder (OneDrive,
   Google Drive, Dropbox: the finder says "lists video FILES"), tell the user to use that service's
   Download / sync — no recording needed; if the share is view-only, open each file and use its address.
2. **Where to save the recordings?** Suggest a new folder in `Videos`, named for the course.
3. **Trim long silences afterwards?** (exercise time, breaks, waiting rooms) If yes:
   - minimum silence to cut (suggest **4 min**),
   - padding (suggest cut **3 s after** the last sound, resume **2 s before** talking),
   - keep short talk bits inside silent blocks? (suggest **yes**; offer the review clip to decide),
   - **which folder for the trimmed copies** (suggest `<recordings>\Without silence`),
   - keep the originals? (suggest **yes**, until they've checked the trimmed copies).
4. **When to run** — videos record in real time (a 3-hour video takes 3 hours). Overnight is ideal.

### 2. Set up (once per machine / course)

**Prerequisites** — run `python scripts/check_setup.py` first; it checks all of these and prints
the install command for anything missing. Ask the user before installing anything.

| Needed | Why | Install if missing |
|---|---|---|
| Windows 10/11 | OBS window capture, per-app audio capture, power requests | — (not supported elsewhere) |
| Python 3.10+ on PATH | runs the scripts | `winget install Python.Python.3.12` |
| OBS Studio 28+ | the recorder; 28+ has the WebSocket remote control built in | `winget install OBSProject.OBSStudio` |
| ffmpeg + ffprobe on PATH | MP4 saving, checks, trimming | `winget install Gyan.FFmpeg` (new terminal after) |
| Microsoft Edge or Google Chrome | plays the videos (Playwright drives the installed browser — no browser download) | Edge ships with Windows; `winget install Google.Chrome` |
| Python packages `obsws-python`, `playwright` | OBS control, browser control | `pip install -r scripts/requirements.txt` into the work folder's venv |

Nothing else is needed: no OBS plugins, no Playwright browser download, no admin rights.
Optional: an NVIDIA GPU makes OBS use NVENC (lighter on the CPU); otherwise x264 is used.

- Create a **work folder on a short path**: `<recordings>\_recorder`. Long paths break
  Python's native modules (`DLL load failed ... filename or extension is too long`), so
  never put the venv inside a deep app/temp folder.
- Create the venv there and install: `python -m venv .venv` then
  `.venv\Scripts\python -m pip install -r <skill>\scripts\requirements.txt`.
  Re-run `check_setup.py --work <work>` — it should say READY.
- Write `<work>\videos.json`:
  ```json
  {
    "output_dir": "C:\\Users\\me\\Videos\\My Course",
    "browser": "msedge",
    "videos": [
      {"name": "01 - Intro", "url": "https://example.com/lesson/1"},
      {"name": "02 - Basics", "url": "https://example.com/lesson/2",
       "play_selector": "button.big-play", "expected_minutes": 95}
    ]
  }
  ```
  `expected_minutes` (optional, recommended when known): if the video found is more than 10% off
  that length, the recorder stops instead of recording a trailer, an ad or the wrong card.
  `"captions": "off"` or `"on"` (optional, top level): hide or burn in the video's own caption
  track; leave it out to keep whatever the site shows. Ask the user in step 1 if the site has
  captions — they can't be removed from (or added to) a recording afterwards.
  The recorder finds the main `<video>` by itself (also inside embedded players and web components,
  and when the page uses `preload="none"`): it loads metadata for every video and picks the longest,
  visible one. If nothing loads it escalates gently, like a person would: after 8 s it asks the
  video to play (or clicks the player once if the video has no stream yet), after 20 s it presses the
  player's own play button (or clicks the player). Add
  `play_selector` (CSS or `xpath=`) only if a site needs a specific button elsewhere on the page —
  find it by inspecting the page in the recorder's own profile (other browsers may get a different
  page variant), and set `expected_minutes` so a selector that presses the wrong item is caught.
- **OBS remote control**: the user must fully exit OBS (tray icon → Exit; closing the window
  only hides it). Then `python scripts/obs_websocket.py enable --work <work>`. This backs up
  their config and writes a password file into `<work>`.
- **Sign-in**: the recorder uses its own browser profile (`<work>\browser-profile`), so the user
  must sign in there once: `python scripts/record_videos.py --config <work>\videos.json --login`
  opens the first URL; the user signs in, then closes that window. Sign-ins persist. (`find_videos.py
  --login` does the same.) If a run lands on a sign-in page anyway (password box / login address, and no
  video on the page), the recorder says "SIGN-IN NEEDED", brings its window forward and waits up to
  15 min for the user to sign in there — it never types anything itself. Sites that quietly redirect
  signed-out users to a public page can't be detected: that's why the explicit sign-in step stays.
- **Sound output**: ask the user to set Windows output to the **built-in speakers** for the
  run. USB DACs, Bluetooth and monitor (HDMI/DP) audio can drop out, which freezes playback.
  Volume level does not matter (capture is per-app), anything above 0 is fine.

### 3. Test first — every time a run starts

Never start hours of recording without a passing test. `run_session.ps1` does this:
it records a test clip from the first video, runs `check_recording.py --test` on it, and only
continues if it passes. Test length defaults to the display-off timeout + 2 min, so the test
proves the screen stays on and playback survives past it.

The test checks: correct length (no stall), steady sound in every 2-minute slice, no black
frames (DRM or broken capture), picture and sound in sync. On failure the run stops and
`runner.log` says why — read `references/troubleshooting.md`.

To try a new site or machine without starting the full run, add `-TestOnly` (keeps the clip).

**Extra checks worth doing once per machine** (short `-TestOnly -TestSeconds 150` run with the user):
- user mutes or lowers the master volume → recorded level must not drop;
- user plays YouTube in their normal browser → it must not leak into the recording
  (ask them to listen to the test clip; you can't hear audio yourself).

### 4. Run

Tell the user: **lid open, charger in, sound output unchanged, don't minimise or click the
recording window.** Also tell them what *is* fine, because people worry: other programs on top
of the recording window, other monitors, YouTube in their normal browser, and **muting the master
volume** for a silent night (capture is per-app, so the recording still gets full sound).
Then launch detached so it survives the chat:

```powershell
Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File "<skill>\scripts\run_session.ps1" -Config "<work>\videos.json"'
```

The recorder holds a Windows power request (system + display) for its whole lifetime, so
the laptop doesn't sleep and the screen doesn't turn off (playback stops when the display
turns off). Lid close still sleeps the machine — that's why the lid must stay open. Warn if on
battery.

Monitor with background waits on `<work>\recorder.log` (lines: `starting at`, `saved`,
`stalled`, `failed`, `treating as finished`) and `<work>\runner.log` (`test passed`,
`TEST FAILED`, `runner: done`). After the **first** video is saved, run
`check_recording.py` on it before trusting the rest of the night.

**Don't trust directory listings for the file OBS is writing** — size and time are stale
until it closes. Copy the file and probe it, or ask OBS (`obs_websocket.py status --work`).

To stop early (e.g. only closing remarks left): `python scripts/stop_and_save.py --config
<work>\videos.json --name "<file name>"` — stops OBS cleanly, saves the MP4, restores OBS, closes
the recorder.

### 5. Check every file

`python scripts/check_recording.py <file> --expected <seconds>` for each video. Report a table
(name, length vs expected, size, sound OK). Long **digital silences** (-91 dB) usually come
from the source (breaks, breakout rooms), not the recorder — if in doubt, ask the user to play
the original at one silent timestamp.

### 6. Optional: trim silences (as agreed in step 1)

1. Show what would be cut: `trim_silence.py --input-dir <rec> --dry-run` lists each cut and the
   new length per video.
2. If the user wants to judge short talk inside silent blocks, build the review clip:
   `review_short_talk.py --input-dir <rec> --output "<trim folder>\Review - short talk.mp4"`.
   You cannot hear it — the user must listen.
3. Trim one video first, check its cut points (`check_recording.py <trimmed> --seams <original>`),
   then the rest. Trimming re-encodes (libx264 veryfast, ~13× real time) so cut points are exact.

### 7. Clean up

- `python scripts/obs_websocket.py restore --work <work>` (OBS fully exited first) — puts the
  user's OBS remote-control setting back.
- The recorder already switches OBS back to the user's own profile/scenes after each run, but leaves
  OBS running in the tray. Ask the user to exit it (tray icon → right-click → Exit) when the session is
  over; otherwise a Windows shutdown counts as an OBS crash and the next start shows the Safe Mode dialog.
- Turn your keep-awake off as the last step of any unattended run (chain it into the same job).
- Ask whether to keep `<work>` (venv, browser profile with sign-ins, logs) for future videos.

## Why the recorder does what it does (so you can adapt it)

- **Own browser window, full screen, video element full screen** — clean picture with no
  site UI; OBS captures that one window (not the screen), so other windows, notifications and
  other monitors don't matter. OBS only starts once *the video itself* is the full-screen element,
  and if a site's ad or player box takes over full screen, playback and OBS are held until it's
  restored — so the web page never ends up in the recording and nothing is skipped.
- **Kept unmuted** — some players (TED) start muted and re-apply it; the recorder unmutes every second.
- **Recording shaped like the video** — the capture is cropped to where the video sits on screen
  (the browser letterboxes it) and the canvas takes the video's aspect, ≤1920 on the long side and
  ≤ the video's own resolution. Otherwise a 4:3 or vertical video, or a 16:10/ultrawide screen,
  gets black bars on all four sides.
- **Per-window audio capture** — only that browser's sound is recorded; system volume and
  other apps don't affect it.
- **Fixed window title** — OBS finds windows by title; the page title is pinned so capture
  never loses the window when the site changes it.
- **Pause OBS when playback stalls**, resume when it moves — buffering never ends up in the file.
  After 5 min stuck, reload and resume from the last position.
- **Hold at the start, start OBS, then play** — nothing at the start is lost.
- **End detection by last position** — players often stop ~1 s short of the end, never fire
  `ended`, and may even remove the `<video>` element; treat "no progress for 15 s within 5 s
  of the end" as finished, or the script loops on the last second all night.
- **Occlusion/background throttling disabled** — the browser keeps rendering when covered.
- **Edge/Chrome sandbox kept on** — otherwise a warning bar appears inside the recording.

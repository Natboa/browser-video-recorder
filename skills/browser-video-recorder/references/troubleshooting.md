# Troubleshooting — found in real overnight runs

Each entry: what you see → why → what to do. Most of these cost hours the first time.

## Playback

**Player stuck at the start time (e.g. 30:00), says "playing", timer doesn't move; or video
runs but no sound.** → The browser can't open the Windows default sound device, and video
timing follows the audio clock. Typical after a USB DAC / Bluetooth / monitor-audio device
drops out (also after the display turned off). Check with
`diag_playback.py --config ... ` (sound on) and `--no-audio-output` (sound off): if it only
moves with sound off, it's the audio device. Ask the user to switch Windows output to the
built-in speakers (taskbar speaker icon → `>` → pick device; if already selected, pick
another and back). Don't use `--disable-audio-output` for real runs — the recording would
be silent.

**Playback stops when the screen turns off.** → Windows turns the display off at its idle
timeout and the browser stops presenting/decoding. The recorder holds a *display-required*
power request (PowerCreateRequest). If the user's own keep-awake tool only holds
"system required", that alone is not enough. Never test by forcing the monitor off
(SC_MONITORPOWER) — that broke playback *and* knocked out the audio device.

**Laptop went to sleep mid-run (Modern Standby).** → No power request held, or the lid was
closed. `SetThreadExecutionState` is ignored on Modern Standby laptops; use
`PowerCreateRequest`/`PowerSetRequest` (what `keep_awake.py` does). Lid close always sleeps.

**Script reloads the page every 5 minutes at the very end of a video and never moves on.**
→ Player stopped ~1 s before the end, never fired `ended`, and may have removed the
`<video>` element. The recorder now treats "no progress for 15 s within 5 s of the end" as
finished, using the last position it saw. If you change the end logic, keep it independent of
the video element still existing.

**First second(s) missing.** → Playback started while OBS was being set up. The recorder
pauses at the start point, starts OBS, then plays.

**"No playable &lt;video&gt; found on the page within 2 minutes".** Common causes, in order:
1. *Click-to-activate player*: the page holds empty `<video>` placeholders (no `src`, no
   `<source>`) and only creates the real player when the poster is clicked (Wikimedia Commons does
   this). The recorder clicks the main player once after 8 s and presses the player's own labelled play
   button after 20 s (DW: an empty video.js placeholder that only starts from its "Play video" button -
   clicking the picture did nothing). If the site needs a specific button,
   set `play_selector` for that video. Inspect with a browser tool: list each `<video>`'s
   `currentSrc`, `readyState` and `<source>` children.
2. *Signed out* in the recorder's own profile, so run `--login` and have the user sign in.
3. *`preload="none"`*: handled automatically (metadata is loaded for every video).
4. *Video in a cross-origin iframe*: handled (all frames are searched). If the iframe's player
   only works full screen, check it allows fullscreen.

When the recorder gives up it logs "gave up on frame ...: video {...}; text: ..." for every frame with a video:
the text usually names the cause (a privacy/"can't be played here" message in an embedded player, a sign-in
wall, an error). Embedded players that refuse to play on the page they're embedded in can't be fixed from
the recorder: record from the page the course itself uses (embeds often check which site they're on, so a
local test page can fail where the real course page works).

Don't trust a quick check in another browser: the same URL can serve a different page variant
(the in-app browser got ready-to-play sources while the recorder's Edge got empty placeholders).
Diagnose in the recorder's own browser profile.

**Video plays for ~40-60 s, then jumps back to 0:00 and stops ("Something went wrong. Refresh or
try again later." on YouTube).** → The site stops playback in automated browsers (bot protection):
it plays what was already loaded, then refuses to send more. The recorder notices (player reset to
0 with nothing loaded for 30 s), saves what it has and logs "the site's player reset itself".
Verified 2026-10-20 with no interventions at all (no seeking, no play() calls, no full screen, fresh
profile): the buffer grows to exactly 60 s and stops, the server refuses nothing, and at ~45 s the player
errors - YouTube's own page code stops fetching for a browser that reports `navigator.webdriver = true`.
The recorder's actions are not the cause; the only "fix" would be hiding the automation from the site.
This is a real block, so stop there: **don't try to get around bot protection**. Tell the user what was
recorded and that the site cut playback off, and point to its official offline option (YouTube:
downloads with YouTube Premium). Try the site first; don't predict this from the site's name.

**The test passes but the clip is an ad** (a 20-s "video" on a site whose videos are minutes long). →
Pre-roll ads often play in the same `<video>` element as the real video, so the ad looks like the video.
Three guards: with `expected_minutes` set (the finder fills it in from the list page), the recorder waits up
to 3 min for a video of that length instead of starting on the ad; without it, it uses the length the page
itself states for search engines (schema.org VideoObject / `video:duration` - YouTube, Vimeo, TED, Twitch,
Internet Archive state it; Dailymotion and media.ccc.de don't) the same way, but goes on with a warning if
that length never appears; and if a short video (2.5 min or less) "ends" and the same page (same address)
goes on to a much longer one, the clip is thrown away and the real video is recorded. A long ad (seen: a
293-s YouTube ad) on a page that states no length can still pass as the video. Autoplay of the next video changes the address, so it never triggers this.
Always look at the contact sheet: seen with a YouTube pre-roll recorded and passed as the video.

**A jump inside the video freezes it (position changes, nothing loads).** → Streaming players that
manage their own buffer (YouTube, Vimeo, some HLS/DASH players) ignore direct `currentTime` jumps
outside what they've loaded. The recorder checks every jump and falls back to the site's own
start-time link (`&t=…s` on YouTube, `#t=…s` on Vimeo); without one, the test runs from the start
and a stalled recording that can't resume is saved as partial (never re-recorded from 0:00).

**Video inside a web component isn't found** (`<play-av>` on archive.org, many modern players). →
Handled: the search walks open shadow roots and keeps a direct reference to the chosen video.

**Stream never starts after the recorder touched it.** → Calling `load()` on a MediaSource
(`blob:`) video tears the stream down, and clicking a still-buffering player pauses it. The
recorder only nudges `preload="none"` videos and only clicks when nothing is downloading.

**Test passes but it's the wrong video** (a trailer, an ad, another item on the page). → The checks
can't know which video you meant. Set `expected_minutes` per video; the recorder stops when the
found video is more than 10% off. Seen with a `play_selector` that pressed another card's PLAY
(Shaka demo: the wanted card had no PLAY button, so the XPath climbed to the whole grid). Always
look at a frame of the test clip.

**Embedded player shows nothing until its own play button is pressed** (PeerTube/video.js embeds,
Vimeo players on other sites). → The stream is attached but waits for the player's own Play. After 8 s
the recorder presses the play button inside that player; without one it asks the video to play (stream
attached) or clicks the player (idle), and at 20 s tries the other. **Never call `play()` on the
`<video>` before pressing the player's button**: on players that fetch the stream themselves (Vimeo)
the element then says "playing" while nothing loads, the button turns into "Pause", and every later
click pauses it. That, not the embedding page, was why Vimeo embeds failed (verified by stepping
through: `play()` → paused=false, readyState 0 for good; pressing Play → playing in 5 s).

**Embedded player on a real article/course page never appears, or its Play press does nothing.** → Two
things real pages do that test pages don't: the embed is lazy-loaded (`<iframe loading="lazy">` only loads
once scrolled into view) and the player sits below the visible part of the page, where a forced click lands
on nothing. The recorder scrolls down in steps when it finds no video, brings the button and every frame
around it into view before pressing, and clicks the button directly if the video is still paused after the
press (seen on a Colossal article embedding Vimeo).

## Capture

**Recording shows the web page (or the site's own player controls) instead of just the video.** →
Full screen was lost or went to another element (TED's ad switch did this for ~15 s). The recorder
only starts OBS once the video itself is the full-screen element, and holds playback + OBS while it
restores full screen. Check frames of every test clip; `check_recording.py` can't see page content.

**Recording shows the web page although the log says the video is full screen, on a site whose player opens
in a pop-up after its own "Play video" button** (NASA+). → The `<video>` sits preloaded inside a hidden pop-up
(`visibility: hidden`), and a full-screen element inherits that, so the window keeps showing the page. The
recorder forces the full-screen video visible and only counts full screen when the video is actually visible;
the capture check is the safety net. If it still happens, set `play_selector` to the site's Play button.

**Recording is cropped wrongly / squashed, or the capture check holds for a minute at the start.** → OBS reports
the captured window's size a moment late; a reading taken mid-switch to full screen (seen: 1265x1366 on a
2560x1440 screen) gave the wrong crop. The recorder now sizes the crop only after full screen is confirmed and
waits until OBS's window size matches the page's. OBS can't change its canvas while recording, so a re-fit
during a recording only adjusts the crop.

**Browser's own play/time/volume bar visible for the first seconds (or after a buffering pause).** →
Browsers show their media controls over a full-screen video for a few seconds, and while paused.
The recorder adds a style next to the video (inside its shadow root for web-component players) that
hides `::-webkit-media-controls` on the recorded video. Check the 0-5 s frames of the contact sheet.

**Capture check says "can't tell".** → The video file comes from another server without CORS, so
the page can't read its pixels to compare with OBS (Wikimedia Commons, many plain-file players).
The other checks still apply; look at the contact sheet.

**Recording is silent but the picture is fine.** → The site muted the video (TED starts muted and
re-mutes). The recorder unmutes every second and logs "the player muted the video". If it's still
silent, it's the audio device (see Playback).

**Recording is black, sound is fine.** → DRM (encrypted media) — out of scope, stop. Or the
window was minimised (capture of minimised windows is impossible). Covering it is fine.

**Warning bar "unsupported command-line flag: --no-sandbox" in the recording.** → Playwright
adds `--no-sandbox` unless `chromium_sandbox=True`. Already set.

**"Translate this page from Spanish?" bubble over the video in the recording.** → The browser
offers to translate a foreign-language page, and the bubble sits on top of the full-screen video.
Two causes, both fixed in `launch()`: Playwright passes its own `--disable-features=…Translate…`,
but our later `--disable-features=` replaces it (the last one wins), so `Translate` must be in
ours; and Edge's translator ignores that flag and only obeys the profile preference
`translate.enabled = false`, which `no_translate_offer()` writes before every launch.

**OBS "Crash detected — run in Safe Mode?" dialog at start.** → OBS wasn't shut down cleanly
last time - typically because the recorder left it running in the tray and Windows shut down or
restarted with it open. At the end of a session, have the user exit OBS from the tray (right-click →
Exit). The user must click **Run in Normal Mode** (Safe Mode disables the WebSocket).
Never kill OBS with Stop-Process; stop recording via WebSocket and let the user exit from the
tray.

**WebSocket requests fail with code 207 "OBS is not ready".** → OBS is still starting or a
startup dialog is open. The recorder waits up to 5 minutes for readiness.

**SetCurrentProfile fails with code 600 right after CreateProfile.** → Profile was already
current / switch still loading. The recorder checks the current profile and retries.

**Directory listing says the recording is 0 MB / last written hours ago.** → Stale metadata for
a file OBS has open. Copy it and probe with ffmpeg, or ask OBS `GetRecordStatus`. Don't
conclude the run is stuck from `dir` alone.

## Environment

**`ImportError: DLL load failed ... The filename or extension is too long`** (greenlet /
Playwright). → The venv lives under a very long path (app sandbox, temp folders). Put the
work folder on a short path like `C:\Users\<me>\Videos\<course>\_recorder`.

**Closing the OBS window doesn't exit it.** → Started with `--minimize-to-tray`; exit from the
tray icon (right-click → Exit). The WebSocket config can only be edited safely while OBS is
fully exited (it rewrites config on exit).

**Long silent stretches in recordings.** → Usually in the source (breaks, breakout rooms:
the main-room recording is pure digital silence, -91 dB, with short bursts when the host
speaks). A failing capture doesn't switch on and off like that. If in doubt, have the user play
the original at one silent timestamp.

# FAQ

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

**Which sites does it work on?** Every site is tried; it stops only if the site really blocks recording. Anything that plays in an HTML5 `<video>` element without DRM or bot protection works. Over 35 sites were tested end-to-end in October 2026: Vimeo, TED, Zoom replays, Internet Archive, PeerTube, Microsoft Learn, OneDrive/SharePoint and more. DRM services record black and sites with a "checking your browser" wall need you to pass it yourself; YouTube was cut off after ~40 s in testing. Full table: [compatibility.md](compatibility.md).

**Why OBS and not ffmpeg screen capture?** OBS captures one window (even when covered) plus that
one app's audio, and its WebSocket API allows pausing exactly while the video buffers.

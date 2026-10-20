# Changelog

## 1.1.3

- Pre-roll ads are no longer recorded as the video: with a known length (from the finder, or the length the
  page itself states for search engines) the recorder waits up to 3 min for the real video; a short video
  that ends and is followed by a much longer one on the same page is discarded and the real one recorded.
  A test whose page-stated length never appeared fails instead of passing.
- YouTube's block diagnosed: with no interventions at all, its player stops after a 60-second buffer in a
  browser that reports itself as automated. Documented in troubleshooting; not worked around.
- Fixed a corrupted path in SKILL.md step 1.

## 1.1.2

- Every site is tried (YouTube included); the recorder and the skill stop only on a real block (DRM black frames, playback cut off), not by site name.

## 1.1.1

- README cut to a short front page; detail moved to `docs/`.

## 1.1.0

- Added the `/record-videos <link>` slash command.
- README: quick start, "who is this for", plain explanation of what installing means, install from a
  local clone, trigger phrases, badges. Site compatibility table moved to `docs/compatibility.md`.

## 1.0.0

- First release: one-link video finder, official downloads first, unattended OBS recording with
  stall recovery and end detection, per-file quality checks, optional silence trimming.

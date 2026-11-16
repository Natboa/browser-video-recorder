# Changelog

## 1.1.7

- The recorder now requests a normal OBS exit after restoring profile/scenes, only
  when it launched that process and every output is idle. It waits for exit and
  never force-kills a blocked process. Pre-existing OBS sessions remain open.
- Cleanup also runs after setup errors; a failed profile restoration leaves OBS
  open for recovery. Added ownership, active-output, shutdown-timeout and cleanup
  ordering regressions without touching the live OBS process.

- An otherwise healthy test with mixed sound/silence requests one new sample instead
  of ending the night at a source exercise break. The retry must pass all checks;
  all-silent audio, black picture, sync failures and stalls still stop the run.
- Added `-TestStartSeconds` / `--test-start` for selecting a known talking section.
- Failed tests, missing recordings and failed finished-file checks return a nonzero
  runner exit code. OBS readiness now uses elapsed time instead of counting attempts,
  and its diagnostics explain that Safe Mode disables remote control.
- Added offline media and session-runner regression tests, plus troubleshooting for
  sleep after failed-test cleanup and Windows log-file sharing errors.

## 1.1.6

- Before every unattended run the agent now gives the user a fixed checklist: charger in, lid open,
  the laptop may be muted (the recording still gets full sound), don't minimise the window or change
  the sound output - then go to sleep. README quick start says the same.

## 1.1.5

- Black-picture check: pure black in TV-range video measures exactly 16, so the threshold is now
  below 17 (was below 16), and a fully black (e.g. DRM) recording no longer passes.

## 1.1.4

- Agent-neutral: the README presents it as an open Agent Skills skill for any agent (Claude Code, OpenAI
  Codex, Gemini CLI, GitHub Copilot, Cursor, ...), with install steps for any agent; the Claude Code plugin
  stays as an optional one-step install.

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

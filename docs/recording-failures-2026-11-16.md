# Recording failures investigated on 2026-11-16

These were separate failures, not one repeated crash. The ongoing recording was
left running while the repo fixes were tested offline.

| Event | Evidence and cause | Resolution |
|---|---|---|
| OBS would not connect | OBS log explicitly recorded Safe Mode and skipped `obs-websocket`. | Clean exit and normal restart restored port 4455. Timeout diagnostics now explain Safe Mode. |
| First capture test stopped | The test sampled source 30:00–42:00. Sound stopped at source 35:04; the saved picture showed a “Now you” exercise. The full recording later confirmed a silent interval through 48:02. Picture, duration and sync checks passed. | Repo now reports mixed sound/silence as inconclusive and retries once at another position. A strict pass is still required. |
| Laptop screen went dark | Test failure at 15:25:26, power holds released at 15:25:27, Windows Modern Standby event 506 at 15:25:55. | Expected cleanup after a stopped run. No power-management bypass or saved power-setting change was needed. |
| Queue stopped opening its log | A temporary, course-specific wrapper redirected child output into the same log used for parent status messages. Windows reported a file sharing violation. | Fixed that wrapper to separate output and retry status writes. This wrapper is outside the repo; the repo runner already retries status writes. |
| Restart rejected a passed test | The temporary wrapper searched a log tail containing both an older failed test and the newest passed test. | Fixed that wrapper to inspect the latest result. Repo failures now return a nonzero process exit status so callers need not infer success from historical text. |
| OBS readiness wait exceeded its advertised duration | `wait_s=300` controlled 300 attempts; each connection could itself block, followed by another sleep. | Use a monotonic elapsed-time deadline and bound connection timeouts by the remaining budget. An in-flight request can still finish after the deadline. |

The replacement 12-minute test passed every audio window, picture and sync check.
Episode 08 subsequently passed full-file checks and all eight silence-cut seams.
The capture’s black-picture check and entirely silent-audio failure remain strict.

## Regression checks

`python -m unittest discover -s tests -v` uses real ffmpeg-generated media to check
mixed silence, entirely silent audio, black picture and healthy sound/picture. The
real PowerShell runner executes in temporary folders with external capture/check
doubles to verify bounded retries, explicit sample positions, failure exit codes
and missing recordings. A simulated slow OBS connection verifies the elapsed-time
deadline. None of these tests connects to OBS or the live browser profile.

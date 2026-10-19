"""Diagnose "player stuck / no sound": does playback move, from the start and after a seek?

  python diag_playback.py --config <work>\\videos.json [--index 0]
  python diag_playback.py --config <work>\\videos.json --no-audio-output

If it moves only with --no-audio-output, the browser can't open the Windows sound device
(USB DAC / Bluetooth / monitor audio dropped out): have the user switch output to the
built-in speakers. Never record with --no-audio-output (the recording would be silent).
Run it while no recording is in progress (the browser profile can only be open once).
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_config  # noqa: E402
from record_videos import STATE_JS, VID, find_video, launch  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--no-audio-output", action="store_true")
    a = ap.parse_args()
    cfg = load_config(a.config)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = launch(p, cfg, fullscreen=False)
        if a.no_audio_output:  # relaunch with the fake audio sink
            ctx.close()
            ctx = p.chromium.launch_persistent_context(
                str(cfg["work"] / "browser-profile"), channel=cfg["browser"], headless=False, no_viewport=True,
                chromium_sandbox=True, ignore_default_args=["--mute-audio", "--enable-automation"],
                args=["--autoplay-policy=no-user-gesture-required", "--disable-audio-output"])
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(cfg["videos"][a.index]["url"], wait_until="domcontentloaded", timeout=120_000)
        found = find_video(page)
        if not found:
            print("no <video> found (signed out? embedded player not loaded?)")
            return
        frame, info = found
        print("video:", json.dumps(info), "| in embedded frame" if frame != page.main_frame else "")
        print("play():", frame.evaluate(f"() => {VID}.play().then(() => 'ok', e => 'rejected: ' + e.message)"))
        t0 = frame.evaluate(STATE_JS)["t"]
        time.sleep(8)
        t1 = frame.evaluate(STATE_JS)["t"]
        d = frame.evaluate(STATE_JS)["d"]
        frame.evaluate(f"() => {{ {VID}.currentTime = {d / 2}; }}")
        time.sleep(2)
        t2 = frame.evaluate(STATE_JS)["t"]
        time.sleep(8)
        t3 = frame.evaluate(STATE_JS)["t"]
        moved_start, moved_seek = t1 - t0 > 4, t3 - t2 > 4
        print(f"from start: {t0:.1f} -> {t1:.1f} s in 8 s ({'moving' if moved_start else 'STUCK'})")
        print(f"after seek: {t2:.1f} -> {t3:.1f} s in 8 s ({'moving' if moved_seek else 'STUCK'})")
        if moved_start and moved_seek:
            print("diagnosis: playback works" + (" (with audio output OFF - now retry without the flag)"
                                                  if a.no_audio_output else ""))
        elif not a.no_audio_output:
            print("diagnosis: stuck - rerun with --no-audio-output; if it moves then, fix the Windows sound device")
        else:
            print("diagnosis: stuck even without audio - site/player issue (signed out, region, DRM, network)")
        ctx.close()


if __name__ == "__main__":
    main()

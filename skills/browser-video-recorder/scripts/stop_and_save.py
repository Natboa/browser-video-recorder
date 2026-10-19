"""Stop a run early (e.g. only closing remarks left) and save what was recorded.

  python stop_and_save.py --config <work>\\videos.json --name "07 - Agents part 2"

Stops the runner and recorder, stops OBS recording cleanly (never kills OBS), switches OBS back
to the user's profile/scenes, closes the recorder's browser, and saves the partial recording as
<name>.mp4. Without --name it only stops and cleans up (the partial file stays as .mkv).
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import duration, kill, load_config, obs_client, processes, read_json, remux_to_mp4  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--name", help="file name for the partial recording (without .mp4)")
    a = ap.parse_args()
    cfg = load_config(a.config)
    work = cfg["work"]

    ours = lambda cmd: str(work).lower() in cmd.lower() or a.config.lower() in cmd.lower()
    kill([pid for pid, cmd in processes("powershell%", "run_session.ps1") if ours(cmd)])
    kill([pid for pid, cmd in processes("python%", "record_videos.py") if ours(cmd)])

    cl = obs_client(work, wait_s=30)
    out = None
    s = cl.get_record_status()
    if s.output_active:
        if s.output_paused:
            cl.resume_record()
            time.sleep(0.5)
        out = Path(cl.stop_record().output_path)
        print("OBS stopped:", out)
    time.sleep(3)
    orig = read_json(work / "obs_original.json", None)
    if orig:
        for _ in range(15):
            try:
                cl.set_current_scene_collection(orig["collection"])
                time.sleep(2)
                cl.set_current_profile(orig["profile"])
                break
            except Exception:
                time.sleep(1)
        print("OBS back on", cl.get_profile_list().current_profile_name, "/",
              cl.get_scene_collection_list().current_scene_collection_name)

    kill([pid for pid, cmd in processes("%.exe", str(work / "browser-profile"))])

    if out and a.name:
        target = cfg["output_dir"] / f"{a.name}.mp4"
        ok, err = remux_to_mp4(out, target)
        if ok and duration(target) > 0:
            out.unlink()
            print(f"saved {target.name}: {duration(target) / 60:.1f} min")
        else:
            print("could not save as mp4, kept", out, err)
    with open(work / "runner.log", "a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " runner: stopped early by user request\n")
        f.write(time.strftime("%Y-%m-%d %H:%M:%S") + " runner: done\n")


if __name__ == "__main__":
    main()

"""Turn OBS remote control (WebSocket) on for the recorder, and back to the user's setting after.

  python obs_websocket.py enable  --work <work folder>   # OBS must be fully exited (tray -> Exit)
  python obs_websocket.py restore --work <work folder>   # OBS must be fully exited
  python obs_websocket.py status  --work <work folder>

`enable` backs up the user's config into the work folder (once) and writes a random password to
<work>\\obs_ws_password.txt. OBS rewrites this config when it exits, so it is only edited while
OBS is not running.
"""
import argparse
import json
import secrets
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import OBS_WS_CONFIG, obs_client, obs_running  # noqa: E402


def require_obs_closed():
    if obs_running():
        raise SystemExit("OBS is running. Ask the user to exit it from the tray icon (right-click -> Exit) "
                         "- closing the window only hides it. Don't force-kill OBS.")


def enable(work):
    require_obs_closed()
    backup = work / "obs_websocket_config.backup.json"
    if OBS_WS_CONFIG.exists() and not backup.exists():
        shutil.copy2(OBS_WS_CONFIG, backup)
    elif not OBS_WS_CONFIG.exists():
        backup.write_text("{}", encoding="utf-8")  # marker: there was no config before
    cfg = json.loads(OBS_WS_CONFIG.read_text(encoding="utf-8-sig")) if OBS_WS_CONFIG.exists() else {}
    pw = secrets.token_urlsafe(18)
    cfg.update({"server_enabled": True, "auth_required": True, "server_password": pw,
                "server_port": cfg.get("server_port", 4455), "first_load": False, "alerts_enabled": False})
    OBS_WS_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    OBS_WS_CONFIG.write_text(json.dumps(cfg, indent=2), encoding="ascii")
    (work / "obs_ws_password.txt").write_text(pw, encoding="ascii")
    print(f"OBS remote control enabled on port {cfg['server_port']}; user's config backed up to {backup.name}")


def restore(work):
    require_obs_closed()
    backup = work / "obs_websocket_config.backup.json"
    if not backup.exists():
        raise SystemExit("no backup in this work folder - nothing to restore")
    if backup.read_text(encoding="utf-8").strip() == "{}":
        OBS_WS_CONFIG.unlink(missing_ok=True)
    else:
        shutil.copy2(backup, OBS_WS_CONFIG)
    backup.unlink()
    (work / "obs_ws_password.txt").unlink(missing_ok=True)
    enabled = json.loads(OBS_WS_CONFIG.read_text(encoding="utf-8-sig")).get("server_enabled") \
        if OBS_WS_CONFIG.exists() else False
    print(f"OBS remote control restored to the user's setting (enabled = {enabled})")


def status(work):
    cfg = json.loads(OBS_WS_CONFIG.read_text(encoding="utf-8-sig")) if OBS_WS_CONFIG.exists() else {}
    print("OBS running:", obs_running())
    print("remote control enabled in config:", cfg.get("server_enabled", False))
    print("backup of user's config in work folder:", (work / "obs_websocket_config.backup.json").exists())
    if obs_running() and (work / "obs_ws_password.txt").exists():
        cl = obs_client(work, wait_s=15)
        s = cl.get_record_status()
        print(f"recording: active={s.output_active} paused={s.output_paused} timecode={s.output_timecode}")
        print("profile:", cl.get_profile_list().current_profile_name,
              "| scenes:", cl.get_scene_collection_list().current_scene_collection_name)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["enable", "restore", "status"])
    ap.add_argument("--work", required=True, type=Path)
    a = ap.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    {"enable": enable, "restore": restore, "status": status}[a.action](a.work.resolve())

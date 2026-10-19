"""Shared helpers for the browser-video-recorder scripts (Windows)."""
import json
import os
import re
import subprocess
import time
from pathlib import Path

OBS_EXE = Path(r"C:\Program Files\obs-studio\bin\64bit\obs64.exe")
OBS_WS_CONFIG = Path(os.environ.get("APPDATA", "")) / "obs-studio" / "plugin_config" / "obs-websocket" / "config.json"
BROWSER_EXE = {"msedge": "msedge.exe", "chrome": "chrome.exe"}


# ---------- config / work folder ----------

def load_config(path):
    path = Path(path).resolve()
    cfg = json.loads(path.read_text(encoding="utf-8-sig"))
    cfg.setdefault("browser", "msedge")
    cfg["work"] = path.parent
    cfg["output_dir"] = Path(cfg["output_dir"])
    if cfg["browser"] not in BROWSER_EXE:
        raise SystemExit(f"browser must be one of {list(BROWSER_EXE)}")
    return cfg


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return default


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------- ffmpeg ----------

def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def ffmpeg_stderr(args):
    return subprocess.run(["ffmpeg", "-hide_banner", "-v", "info", *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stderr


def volume(path, start=None, length=None):
    """(mean_dB, max_dB) of the audio in a window; (None, None) if there is no audio."""
    args = []
    if start is not None:
        args += ["-ss", f"{max(start, 0):.2f}"]
    if length is not None:
        args += ["-t", f"{length:.2f}"]
    err = ffmpeg_stderr([*args, "-i", str(path), "-vn", "-af", "volumedetect", "-f", "null", "NUL"])
    mean = re.search(r"mean_volume: (-?[\d.]+)", err)
    peak = re.search(r"max_volume: (-?[\d.]+)", err)
    return (float(mean.group(1)) if mean else None, float(peak.group(1)) if peak else None)


def silences(path, min_seconds, noise_db=-50):
    err = ffmpeg_stderr(["-i", str(path), "-vn", "-af", f"silencedetect=n={noise_db}dB:d={min_seconds}", "-f", "null",
                         "NUL"])
    return [(float(e) - float(d), float(e))
            for e, d in re.findall(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", err)]


def remux_to_mp4(src, dst):
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-c", "copy", "-movflags", "+faststart",
                        str(dst)], capture_output=True, text=True)
    return r.returncode == 0, r.stderr[-500:]


# ---------- processes ----------

def processes(name_like, cmd_contains):
    """[(pid, commandline)] for processes whose name matches and command line contains the text."""
    ps = (f"Get-CimInstance Win32_Process -Filter \"Name like '{name_like}'\" | "
          "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    found = []
    for line in out.splitlines():
        pid, _, cmd = line.partition("\t")
        if pid.strip().isdigit() and cmd_contains.lower() in cmd.lower():
            found.append((int(pid), cmd))
    return found


def kill(pids):
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], capture_output=True)


def obs_running():
    return bool(subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe", "/NH"], capture_output=True,
                               text=True).stdout.count("obs64.exe"))


# ---------- OBS WebSocket ----------

def obs_client(work, start_if_needed=False, wait_s=300, log=print):
    import logging
    import obsws_python as obs
    # it logs the password at INFO, and every "not ready yet" retry as an ERROR with a traceback
    logging.getLogger("obsws_python").setLevel(logging.CRITICAL + 1)
    pw_file = Path(work) / "obs_ws_password.txt"
    if not pw_file.exists():
        raise SystemExit("OBS remote control is not enabled for this work folder; run obs_websocket.py enable")
    pw = pw_file.read_text().strip()
    if start_if_needed and not obs_running():
        log("starting OBS")
        subprocess.Popen([str(OBS_EXE), "--minimize-to-tray", "--disable-shutdown-check", "--disable-updater"],
                         cwd=OBS_EXE.parent)
    cl = None
    for i in range(wait_s):
        try:
            cl = cl or obs.ReqClient(host="localhost", port=4455, password=pw, timeout=15)
            cl.get_profile_list()  # fails with code 207 while OBS is starting or a dialog is open
            return cl
        except Exception:
            if i % 30 == 0 and i:
                log("waiting for OBS to be ready (if OBS shows a crash dialog, choose Run in Normal Mode)")
            time.sleep(1)
    raise SystemExit("OBS did not become ready")

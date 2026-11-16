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


def request_obs_close(pid):
    """Post WM_CLOSE to exactly one OBS main window, including a hidden tray window.

    OBS handles its own save/flush/quit path. Never post WM_QUIT, destroy windows,
    or terminate the process. The caller must own the process and verify it is idle.
    """
    import ctypes
    from ctypes import wintypes

    user = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.EnumWindows.restype = wintypes.BOOL
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId.restype = wintypes.DWORD
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowTextW.restype = ctypes.c_int
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetClassNameW.restype = ctypes.c_int
    user.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetWindow.restype = wintypes.HWND
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user.PostMessageW.restype = wintypes.BOOL
    windows = []

    @callback_type
    def visit(hwnd, _):
        owner_pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner_pid))
        if owner_pid.value == pid and not user.GetWindow(hwnd, 4):  # GW_OWNER
            title, cls = ctypes.create_unicode_buffer(1024), ctypes.create_unicode_buffer(256)
            user.GetWindowTextW(hwnd, title, len(title))
            user.GetClassNameW(hwnd, cls, len(cls))
            if re.match(r'^OBS \d', title.value) and cls.value.startswith('Qt'):
                windows.append(hwnd)
        return True

    if not user.EnumWindows(visit, 0) or len(windows) != 1:
        return False
    owner_pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(windows[0], ctypes.byref(owner_pid))
    return owner_pid.value == pid and bool(user.PostMessageW(windows[0], 0x0010, 0, 0))  # WM_CLOSE


def close_owned_obs(client, process, timeout=15, log=print):
    """Close only the OBS process this recorder launched, and only when idle.

    The Popen handle, not a saved PID, preserves process identity. Refuse to close
    on unknown/active outputs and never force a timed-out shutdown.
    """
    if process is None:
        log('OBS was already running; leaving it open')
        return False
    exit_code = process.poll()
    if exit_code is not None:
        return exit_code == 0
    try:
        for name, status in (
            ('recording', client.get_record_status), ('streaming', client.get_stream_status),
            ('replay buffer', client.get_replay_buffer_status), ('virtual camera', client.get_virtual_cam_status),
        ):
            if status().output_active:
                log(f'OBS still has active {name}; leaving it open')
                return False
        # Check the original process handle again after the WebSocket queries.
        exit_code = process.poll()
        if exit_code is not None:
            return exit_code == 0
        if not request_obs_close(process.pid):
            log('Could not request normal OBS exit; leaving it open')
            return False
        if process.wait(timeout=timeout) != 0:
            log('OBS exited with an error; normal shutdown could not be confirmed')
            return False
        log('OBS exited normally')
        return True
    except subprocess.TimeoutExpired:
        log('OBS is still running after the close request; exit it manually (no forced termination)')
    except Exception as error:
        log(f'Could not confirm idle OBS or complete normal shutdown; leaving it open: {error}')
    return False


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
    owned_process = None
    if start_if_needed and not obs_running():
        log("starting OBS")
        owned_process = subprocess.Popen([str(OBS_EXE), "--minimize-to-tray", "--disable-updater"],
                                         cwd=OBS_EXE.parent)
    cl = None
    deadline = time.monotonic() + wait_s
    next_notice = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            remaining = deadline - time.monotonic()
            cl = cl or obs.ReqClient(host="localhost", port=4455, password=pw, timeout=min(15, remaining))
            cl.get_profile_list()  # fails with code 207 while OBS is starting or a dialog is open
            cl.recorder_owned_process = owned_process
            return cl
        except Exception:
            now = time.monotonic()
            if now >= next_notice:
                log("waiting for OBS remote control: choose Run in Normal Mode in a crash dialog; "
                    "if OBS opened in Safe Mode, fully exit and reopen normally (Safe Mode disables obs-websocket)")
                next_notice = now + 30
            time.sleep(max(0, min(1, deadline - now)))
    raise SystemExit("OBS remote control did not become ready within the timeout; check Normal Mode "
                     "and that WebSocket remote control is enabled")

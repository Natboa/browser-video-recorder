"""Check everything browser-video-recorder needs, and say how to install what's missing.

  python check_setup.py                      # system prerequisites
  python check_setup.py --work <work folder> # also the work folder's venv + Python packages

Uses only the standard library, so it runs before anything is installed.
Exit code 0 = ready, 1 = something is missing.
"""
import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

OK, MISSING = "ok     ", "MISSING"
results = []


def check(name, ok, detail, fix=""):
    results.append(ok)
    print(f"[{OK if ok else MISSING}] {name}: {detail}" + ("" if ok or not fix else f"\n           install: {fix}"))


def version_of(cmd, pattern=r"(\d+\.\d+(\.\d+)?)"):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        m = re.search(pattern, out.stdout + out.stderr)
        return m.group(1) if m else "unknown version"
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", type=Path, help="work folder (checks .venv and Python packages there)")
    a = ap.parse_args()

    check("Windows", platform.system() == "Windows", f"{platform.system()} {platform.release()}",
          "this skill needs Windows 10/11 (OBS window capture, per-app audio capture, power requests)")
    check("Python 3.10+", sys.version_info >= (3, 10), platform.python_version(),
          "winget install Python.Python.3.12   (tick 'Add to PATH'; open a new terminal after)")

    obs = Path(r"C:\Program Files\obs-studio\bin\64bit\obs64.exe")
    if obs.exists():
        v = version_of(["powershell", "-NoProfile", "-Command", f"(Get-Item '{obs}').VersionInfo.ProductVersion"])
        major = int(v.split(".")[0]) if v and v[0].isdigit() else 0
        check("OBS Studio 28+", major >= 28, f"{v} at {obs}",
              "winget upgrade OBSProject.OBSStudio   (28+ has the WebSocket remote control built in)")
    else:
        check("OBS Studio 28+", False, "not found in C:\\Program Files\\obs-studio",
              "winget install OBSProject.OBSStudio   (or https://obsproject.com/)")

    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        check(tool, bool(path), f"{version_of([tool, '-version'], r'version (\S+)')} at {path}" if path else "not on PATH",
              "winget install Gyan.FFmpeg   (then open a new terminal so PATH updates)")

    browsers = {
        "Microsoft Edge": [Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
                           Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe"],
        "Google Chrome": [Path(os.environ.get("ProgramFiles", "")) / "Google/Chrome/Application/chrome.exe",
                          Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe"],
    }
    found = [n for n, paths in browsers.items() if any(p.exists() for p in paths)]
    check("Edge or Chrome", bool(found), ", ".join(found) or "neither found",
          "Edge ships with Windows; or winget install Google.Chrome   (set \"browser\": \"chrome\" in videos.json)")

    if a.work:
        work = a.work.resolve()
        check("work folder path is short", len(str(work)) <= 80, f"{work} ({len(str(work))} chars)",
              "use a short path like C:\\Users\\<you>\\Videos\\<course>\\_recorder (long paths break Python DLLs)")
        py = work / ".venv" / "Scripts" / "python.exe"
        check("work folder venv", py.exists(), str(py), f'python -m venv "{work / ".venv"}"')
        if py.exists():
            req = Path(__file__).with_name("requirements.txt")
            for pkg, mod in (("obsws-python", "obsws_python"), ("playwright", "playwright.sync_api")):
                r = subprocess.run([str(py), "-c", f"import {mod}"], capture_output=True, text=True)
                check(f"package {pkg}", r.returncode == 0, "importable" if r.returncode == 0 else r.stderr.strip()[-120:],
                      f'"{py}" -m pip install -r "{req}"')

    print("\nREADY" if all(results) else "\nNOT READY - install the missing items above, then run this again")
    print("Also needed at run time (not checkable here): sound output on a stable device (built-in speakers), "
          "laptop lid open and charger in, OBS fully exited before enabling its remote control.")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()

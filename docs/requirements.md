# Requirements

Everything it needs. The agent checks these for you with
[`check_setup.py`](../skills/browser-video-recorder/scripts/check_setup.py) and asks before installing
anything:

| Needed | Why | Install |
|---|---|---|
| **Windows 10/11** | OBS window capture, per-app audio capture, power requests | n/a |
| **[OBS Studio](https://obsproject.com/) 28 or newer** | does the recording; 28+ has the WebSocket remote control built in (no plugin) | `winget install OBSProject.OBSStudio` |
| **[Python](https://www.python.org/) 3.10+** on PATH | runs the scripts | `winget install Python.Python.3.12` |
| **[ffmpeg](https://ffmpeg.org/) + ffprobe** on PATH | saves MP4s, runs the checks, trims silences | `winget install Gyan.FFmpeg` |
| **Microsoft Edge** or **Google Chrome** | plays the videos (the installed browser is used; nothing extra downloads) | Edge comes with Windows · `winget install Google.Chrome` |
| Python packages [`obsws-python`](https://pypi.org/project/obsws-python/), [`playwright`](https://pypi.org/project/playwright/) | control OBS and the browser | `pip install -r ../skills/browser-video-recorder/scripts/requirements.txt` |

No admin rights or OBS plugins needed. An NVIDIA GPU is optional (OBS then uses NVENC; otherwise x264).

Check your machine any time:

```powershell
python skills\browser-video-recorder\scripts\check_setup.py
```

At run time you also need a **stable sound output** (built-in speakers; USB DACs, Bluetooth and
monitor audio can drop out and freeze playback), **the laptop lid open** and **the charger in**.

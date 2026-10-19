"""Keep Windows awake (system + display) while something runs.

Uses PowerCreateRequest/PowerSetRequest, which Modern Standby laptops honour
(SetThreadExecutionState is ignored there). Changes no saved power setting; the request
ends when the process exits. Closing the lid still sleeps the machine.

  python keep_awake.py run -- python trim_silence.py --input-dir ...
  python keep_awake.py check          # prints the display-off timeout and power source

In Python:  with KeepAwake(): ...
"""
import ctypes
import subprocess
import sys
from ctypes import wintypes


class _REASON_CONTEXT(ctypes.Structure):
    _fields_ = [("Version", wintypes.ULONG), ("Flags", wintypes.DWORD),
                ("SimpleReasonString", wintypes.LPWSTR), ("_pad", ctypes.c_void_p * 3)]


class KeepAwake:
    DISPLAY, SYSTEM = 0, 1

    def __init__(self, reason="Recording browser video", display=True):
        self.reason, self.display = reason, display

    def __enter__(self):
        k = ctypes.windll.kernel32
        k.PowerCreateRequest.restype = wintypes.HANDLE
        self._ctx = _REASON_CONTEXT(0, 1, self.reason)  # POWER_REQUEST_CONTEXT_SIMPLE_STRING
        self.h = k.PowerCreateRequest(ctypes.byref(self._ctx))
        ok = bool(self.h) and k.PowerSetRequest(self.h, self.SYSTEM)
        if ok and self.display:
            ok = k.PowerSetRequest(self.h, self.DISPLAY)
        if not ok:
            raise OSError(f"power request failed (error {ctypes.GetLastError()})")
        return self

    def __exit__(self, *exc):
        k = ctypes.windll.kernel32
        k.PowerClearRequest(self.h, self.SYSTEM)
        if self.display:
            k.PowerClearRequest(self.h, self.DISPLAY)
        k.CloseHandle(self.h)


def display_timeout_seconds():
    """Current AC display-off timeout in seconds (0 = never)."""
    out = subprocess.run(["powercfg", "/q", "SCHEME_CURRENT", "SUB_VIDEO", "VIDEOIDLE"], capture_output=True,
                         text=True).stdout
    for line in out.splitlines():
        if "Current AC Power Setting Index" in line:
            return int(line.split(":")[-1].strip(), 16)
    return 0


def on_battery():
    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte),
                    ("BatteryLifePercent", ctypes.c_byte), ("SystemStatusFlag", ctypes.c_byte),
                    ("BatteryLifeTime", wintypes.DWORD), ("BatteryFullLifeTime", wintypes.DWORD)]
    s = SYSTEM_POWER_STATUS()
    ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s))
    return s.ACLineStatus == 0


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "check":
        t = display_timeout_seconds()
        print(f"display turns off after: {'never' if t == 0 else f'{t // 60} min'} (on mains power)")
        print("power source:", "BATTERY - plug in the charger before a long run" if on_battery() else "mains")
        with KeepAwake("keep_awake.py self-test"):
            print("power request: accepted")
    elif len(sys.argv) >= 3 and sys.argv[1] == "run" and sys.argv[2] == "--":
        with KeepAwake("keep_awake.py run"):
            sys.exit(subprocess.call(sys.argv[3:]))
    else:
        print(__doc__)
        sys.exit(2)

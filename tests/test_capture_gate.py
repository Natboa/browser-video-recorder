"""Offline regressions: real ffmpeg checks and sandboxed PowerShell orchestration.

Run: python -m unittest discover -s tests -v
No browser, OBS connection, or existing work folder is used.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/browser-video-recorder/scripts"
sys.path.insert(0, str(SCRIPTS))
import common


class ObsConnectionTests(unittest.TestCase):
    def test_timeout_bounds_elapsed_time_not_connection_attempts(self):
        clock = [0.0]

        def connect(**kwargs):
            clock[0] += 4  # A failed external connection takes time too.
            raise ConnectionError("not listening")

        def sleep(seconds):
            clock[0] += seconds

        timer = types.SimpleNamespace(monotonic=lambda: clock[0], sleep=sleep)
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            (work / 'obs_ws_password.txt').write_text('test-only')
            with patch.dict(sys.modules, {'obsws_python': types.SimpleNamespace(ReqClient=connect)}), \
                    patch.object(common, 'time', timer):
                with self.assertRaises(SystemExit):
                    common.obs_client(work, wait_s=10, log=lambda message: None)
        self.assertLessEqual(clock[0], 14, '10-second budget may overrun by at most one in-flight call')


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg required")
class RecordingCheckTests(unittest.TestCase):
    def check_clip(self, audio, color="white"):
        with tempfile.TemporaryDirectory() as directory:
            clip = Path(directory) / "test.mp4"
            # The second 120-second analysis window is wholly silent in the mixed fixture.
            expression = {"mixed": "if(lt(t,60),0.1*sin(2*PI*440*t),0)",
                          "silent": "0", "talk": "0.1*sin(2*PI*440*t)"}[audio]
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            f"color=c={color}:s=160x90:r=1:d=122", "-f", "lavfi", "-i",
                            f"aevalsrc='{expression}':s=48000:d=122", "-c:v", "libx264",
                            "-preset", "ultrafast", "-c:a", "aac", str(clip)], check=True,
                           capture_output=True)
            return subprocess.run([sys.executable, "-I", str(SCRIPTS / "check_recording.py"),
                                   str(clip), "--test", "--expected", "122"],
                                  capture_output=True, text=True)

    def test_partial_silence_requests_another_sample(self):
        result = self.check_clip("mixed")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("RESULT: RETEST", result.stdout)

    def test_entirely_silent_capture_stays_a_failure(self):
        result = self.check_clip("silent")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_black_picture_cannot_be_retried_as_source_silence(self):
        result = self.check_clip("mixed", "black")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_sound_and_picture_pass(self):
        result = self.check_clip("talk")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


# Real runner; doubles replace only the external capture/media-check commands.
# The checker itself is exercised with real generated media above.
RECORDER = r'''
import argparse, json, sys
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--config'); p.add_argument('--test', type=int)
p.add_argument('--test-start', type=float, default=1800)
p.add_argument('--only', nargs='*')
a = p.parse_args(); work = Path(a.config).parent
cfg = json.loads(Path(a.config).read_text()); out = Path(cfg['output_dir'])
with (work/'calls.jsonl').open('a') as f:
    f.write(json.dumps({'test': a.test, 'start': a.test_start})+'\n')
if not a.test and json.loads((work/'scenario.json').read_text()).get('skip_full'):
    sys.exit(0)
records = json.loads((work/'recorded.json').read_text()) if (work/'recorded.json').exists() else []
for v in cfg['videos'][:1] if a.test else cfg['videos']:
    name = ('TEST - ' if a.test else '')+v['name']
    dest = out/(name+'.mp4'); dest.touch()
    records.append({'name': name, 'file': str(dest), 'expected': a.test or 180})
(work/'recorded.json').write_text(json.dumps(records))
with (work/'recorder.log').open('a') as f: f.write('saved\n')
'''
CHECKER = r'''
import json, sys
from pathlib import Path
work = Path(__file__).parent
state = json.loads((work/'scenario.json').read_text())
code = state['codes'].pop(0) if '--test' in sys.argv else state.get('full_code', 0)
(work/'scenario.json').write_text(json.dumps(state))
print('RESULT:', {0:'PASS',1:'FAIL',2:'RETEST'}[code])
sys.exit(code)
'''


@unittest.skipUnless(sys.platform == "win32", "PowerShell runner is Windows-only")
class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = tempfile.TemporaryDirectory(prefix="bvr_tests_")
        cls.root = Path(cls.environment.name)
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(cls.root / ".venv")],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.environment.cleanup()

    def run_session(self, codes, extra=(), full_code=0, skip_full=False):
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            work = Path(directory)
            # A junction shares the isolated venv, never the live course environment.
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            "New-Item -ItemType Junction -Path '" + str(work / ".venv") +
                            "' -Target '" + str(self.root / ".venv") + "' | Out-Null"], check=True)
            shutil.copy2(SCRIPTS / "run_session.ps1", work / "run_session.ps1")
            (work / "record_videos.py").write_text(RECORDER)
            (work / "check_recording.py").write_text(CHECKER)
            (work / "scenario.json").write_text(json.dumps({"codes": codes, "full_code": full_code,
                                                           "skip_full": skip_full}))
            out = work / "output"; out.mkdir()
            (work / "videos.json").write_text(json.dumps({"output_dir": str(out), "videos": [
                {"name": "Lesson", "url": "https://example.invalid/lesson"}]}))
            result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                                     "-File", str(work / "run_session.ps1"), "-Config",
                                     str(work / "videos.json"), "-TestSeconds", "180", *extra],
                                    capture_output=True, text=True, timeout=40)
            calls_file = work / "calls.jsonl"
            calls = [json.loads(line) for line in calls_file.read_text().splitlines()] if calls_file.exists() else []
            saved = (out / "Lesson.mp4").exists()
            log = (work / "runner.log").read_text(encoding="utf-8-sig") if (work / "runner.log").exists() else ""
            # Remove junction itself so TemporaryDirectory cannot traverse the shared venv.
            subprocess.run(["powershell", "-NoProfile", "-Command",
                            "(Get-Item -LiteralPath '" + str(work / ".venv") + "').Delete()"], check=True)
            return result, calls, saved, log

    def test_silence_only_retry_must_pass_before_full_recording(self):
        result, calls, saved, log = self.run_session([2, 0])
        self.assertEqual(result.returncode, 0, log + result.stderr)
        self.assertTrue(saved, log)
        self.assertEqual([c['start'] for c in calls if c['test']], [1800, 60])

    def test_second_inconclusive_sample_stops_with_failure(self):
        result, calls, saved, log = self.run_session([2, 2])
        self.assertNotEqual(result.returncode, 0, log)
        self.assertFalse(saved)
        self.assertEqual(len(calls), 2)

    def test_hard_capture_failure_never_retries_or_records(self):
        result, calls, saved, log = self.run_session([1])
        self.assertNotEqual(result.returncode, 0, log)
        self.assertFalse(saved)
        self.assertEqual(len(calls), 1)

    def test_explicit_test_start_reaches_recorder(self):
        result, calls, saved, log = self.run_session([0], ('-TestOnly', '-TestStartSeconds', '900'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[0]['start'], 900)
        self.assertFalse(saved)

    def test_failed_full_file_check_returns_failure(self):
        result, calls, saved, log = self.run_session([0], full_code=1)
        self.assertNotEqual(result.returncode, 0, log)
        self.assertTrue(saved)  # Keep the file for diagnosis.

    def test_missing_full_recording_cannot_report_success(self):
        result, calls, saved, log = self.run_session([0], skip_full=True)
        self.assertNotEqual(result.returncode, 0, log)
        self.assertFalse(saved)


if __name__ == '__main__':
    unittest.main()

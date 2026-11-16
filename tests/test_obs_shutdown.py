"""Shutdown policy tests; never send a message to the real OBS process."""
import subprocess
import sys
import types
import tempfile
import contextlib
import logging
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/browser-video-recorder/scripts'))
import common


class ObsShutdownTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        for method in ('get_record_status', 'get_stream_status', 'get_replay_buffer_status',
                       'get_virtual_cam_status'):
            getattr(self.client, method).return_value = types.SimpleNamespace(output_active=False)
        self.process = Mock(pid=12345)
        self.process.poll.return_value = None
        self.process.wait.return_value = 0
        self.messages = []

    def close(self, process=True):
        return common.close_owned_obs(self.client, self.process if process else None,
                                      timeout=3, log=self.messages.append)

    def test_recorder_owned_idle_obs_receives_normal_close_and_is_waited_for(self):
        with patch.object(common, 'request_obs_close', create=True, return_value=True) as request:
            self.assertTrue(self.close())
        request.assert_called_once_with(12345)
        self.process.wait.assert_called_once_with(timeout=3)
        self.process.kill.assert_not_called()
        self.process.terminate.assert_not_called()

    def test_preexisting_user_obs_is_never_closed(self):
        with patch.object(common, 'request_obs_close', create=True) as request:
            self.assertFalse(self.close(process=False))
        request.assert_not_called()
        self.client.get_record_status.assert_not_called()

    def test_any_active_output_prevents_shutdown(self):
        for method in ('get_record_status', 'get_stream_status', 'get_replay_buffer_status',
                       'get_virtual_cam_status'):
            with self.subTest(output=method):
                getattr(self.client, method).return_value.output_active = True
                with patch.object(common, 'request_obs_close', create=True) as request:
                    self.assertFalse(self.close())
                request.assert_not_called()
                getattr(self.client, method).return_value.output_active = False
        self.process.wait.assert_not_called()

    def test_unknown_output_state_leaves_obs_running(self):
        self.client.get_record_status.side_effect = ConnectionError('disconnected')
        with patch.object(common, 'request_obs_close', create=True) as request:
            self.assertFalse(self.close())
        request.assert_not_called()

    def test_close_timeout_never_escalates_to_kill(self):
        self.process.wait.side_effect = subprocess.TimeoutExpired('obs64.exe', 3)
        with patch.object(common, 'request_obs_close', create=True, return_value=True):
            self.assertFalse(self.close())
        self.process.kill.assert_not_called()
        self.process.terminate.assert_not_called()
        self.assertTrue(any('still running' in text for text in self.messages))

    def test_missing_main_window_is_reported_without_forcing_exit(self):
        with patch.object(common, 'request_obs_close', create=True, return_value=False):
            self.assertFalse(self.close())
        self.process.wait.assert_not_called()
        self.process.kill.assert_not_called()

    def test_already_exited_process_cannot_target_a_reused_pid(self):
        self.process.poll.return_value = 0
        with patch.object(common, 'request_obs_close', create=True) as request:
            self.assertTrue(self.close())
        request.assert_not_called()

    def test_newly_started_obs_is_owned_but_reused_obs_is_not(self):
        for already_running in (False, True):
            with self.subTest(already_running=already_running), tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                (work / 'obs_ws_password.txt').write_text('test-only')
                self.process.poll.return_value = None
                api = types.SimpleNamespace(ReqClient=lambda **kwargs: self.client)
                with patch.dict(sys.modules, {'obsws_python': api}), \
                        patch.object(common, 'obs_running', return_value=already_running), \
                        patch.object(common.subprocess, 'Popen', return_value=self.process), \
                        patch.object(common, 'request_obs_close', return_value=True) as request:
                    client = common.obs_client(work, start_if_needed=True, log=self.messages.append)
                    closed = common.close_owned_obs(client, client.recorder_owned_process,
                                                    log=self.messages.append)
                self.assertEqual(closed, not already_running)
                self.assertEqual(request.call_count, 0 if already_running else 1)


@unittest.skipUnless(sys.platform == 'win32', 'Win32 callback types required')
class CloseMessageTests(unittest.TestCase):
    def request(self, windows):
        import ctypes
        from ctypes import wintypes
        calls = []

        def enum(callback, unused):
            for hwnd in windows:
                callback(hwnd, 0)
            return True

        def owner_pid(hwnd, pointer):
            ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD))[0] = windows[hwnd]['pid']
            return 1

        def text(hwnd, buffer, size):
            buffer.value = windows[hwnd]['title']
            return len(buffer.value)

        def cls(hwnd, buffer, size):
            buffer.value = 'Qt661QWindowIcon'
            return len(buffer.value)

        user = types.SimpleNamespace(
            EnumWindows=Mock(side_effect=enum), GetWindowThreadProcessId=Mock(side_effect=owner_pid),
            GetWindowTextW=Mock(side_effect=text), GetClassNameW=Mock(side_effect=cls),
            GetWindow=Mock(side_effect=lambda hwnd, kind: windows[hwnd].get('owner', 0)),
            PostMessageW=Mock(side_effect=lambda *args: calls.append(args) or True))
        with patch.object(ctypes, 'WinDLL', return_value=user):
            result = common.request_obs_close(123)
        return result, calls

    def test_hidden_main_window_is_targeted_by_pid_not_other_obs_or_dialog(self):
        # 64-bit HWND; no visibility requirement, since the recorder starts in the tray.
        hwnd = 0x100000001
        result, calls = self.request({
            hwnd: {'pid': 123, 'title': 'OBS 32.2.2 - Profile: Recorder'},
            2: {'pid': 456, 'title': 'OBS 32.2.2 - Profile: User'},
            3: {'pid': 123, 'title': 'OBS Studio Crash Detected'},
            4: {'pid': 123, 'title': 'OBS 32.2.2 - Dialog', 'owner': hwnd},
        })
        self.assertTrue(result)
        self.assertEqual(calls, [(hwnd, 0x0010, 0, 0)])

    def test_ambiguous_or_absent_main_window_never_broadcasts_close(self):
        for windows in ({}, {1: {'pid': 123, 'title': 'OBS 32.2.2'},
                            2: {'pid': 123, 'title': 'OBS 32.2.2'}}):
            with self.subTest(windows=windows):
                result, calls = self.request(windows)
                self.assertFalse(result)
                self.assertEqual(calls, [])


@unittest.skipUnless(sys.platform == 'win32', 'Recorder imports Windows APIs')
class RecorderCleanupTests(unittest.TestCase):
    def run_recorder(self, setup_failure=False, restore_ok=True):
        import record_videos as recorder
        events = []
        client = Mock()
        for method in ('get_record_status', 'get_stream_status', 'get_replay_buffer_status',
                       'get_virtual_cam_status'):
            getattr(client, method).return_value = types.SimpleNamespace(output_active=False)
        process = Mock(pid=12345)
        process.poll.return_value = None
        process.wait.return_value = 0
        client.recorder_owned_process = process
        rec = Mock(cl=client)

        def setup():
            events.append('setup')
            if setup_failure:
                raise RuntimeError('setup failed')

        rec.setup.side_effect = setup
        rec.restore.side_effect = lambda: events.append('restore') or restore_ok
        ctx = Mock(pages=[Mock()])
        ctx.close.side_effect = lambda: events.append('browser closed')
        api = types.ModuleType('playwright.sync_api')
        api.sync_playwright = lambda: contextlib.nullcontext(object())
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            work = Path(directory)
            cfg = {'work': work, 'output_dir': work / 'output', 'browser': 'msedge',
                   'videos': [{'name': 'Lesson', 'url': 'https://example.invalid/lesson'}]}
            stack.enter_context(patch.dict(sys.modules, {'playwright.sync_api': api}))
            stack.enter_context(patch.object(sys, 'argv', ['record_videos.py', '--config', 'unused']))
            stack.enter_context(patch.object(recorder, 'load_config', return_value=cfg))
            stack.enter_context(patch.object(recorder, 'obs_client', return_value=client))
            stack.enter_context(patch.object(recorder, 'Recorder', return_value=rec))
            stack.enter_context(patch.object(recorder, 'KeepAwake', return_value=contextlib.nullcontext()))
            stack.enter_context(patch.object(recorder, 'launch', return_value=ctx))
            stack.enter_context(patch.object(recorder, 'record_one', side_effect=lambda *a, **k: events.append('record')))
            stack.enter_context(patch.object(recorder.logging, 'basicConfig'))
            stack.enter_context(patch.object(recorder.logging, 'FileHandler', return_value=logging.NullHandler()))
            stack.enter_context(patch.object(common, 'request_obs_close', side_effect=lambda pid: events.append('close') or True))
            if setup_failure:
                with self.assertRaisesRegex(RuntimeError, 'setup failed'):
                    recorder.main()
            else:
                recorder.main()
        return events

    def test_normal_exit_closes_only_after_browser_and_profile_restoration(self):
        self.assertEqual(self.run_recorder(), ['setup', 'record', 'browser closed', 'restore', 'close'])

    def test_setup_error_still_restores_before_closing_owned_obs(self):
        self.assertEqual(self.run_recorder(setup_failure=True), ['setup', 'restore', 'close'])

    def test_restore_error_keeps_obs_open_for_recovery(self):
        self.assertEqual(self.run_recorder(restore_ok=False), ['setup', 'record', 'browser closed', 'restore'])


if __name__ == '__main__':
    unittest.main()

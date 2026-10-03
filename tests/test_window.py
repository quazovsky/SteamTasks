"""Window and inspection helpers.

These tests are hermetic: they never create a window or touch Discord. The native
window is exercised only for construction and label formatting, which is where
the logic lives.
"""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worthlesstask.config.schema import AppConfig
from worthlesstask.rpc.supervisor import PresenceSupervisor
from worthlesstask.ui.inspect import (
    find_windows_titled,
    process_image_path,
    process_name,
    visible_windows,
)
from worthlesstask.ui.window import (
    COLOR_BUSY,
    COLOR_ERROR,
    COLOR_OK,
    PresenceWindow,
    WindowError,
    run_with_window,
)

IS_WINDOWS = os.name == "nt"


def _config() -> AppConfig:
    config = AppConfig(
        client_id="1461154307171811401",
        game_name="ARKNIGHTS: ENDFIELD",
        log_file=None,
    )
    config.validate()
    return config


class TestInspect(unittest.TestCase):
    @unittest.skipUnless(IS_WINDOWS, "windows-only")
    def test_process_name_of_self(self):
        name = process_name(os.getpid())
        self.assertIsNotNone(name)
        self.assertTrue(name.lower().endswith(".exe"), name)

    @unittest.skipUnless(IS_WINDOWS, "windows-only")
    def test_process_image_path_of_self(self):
        path = process_image_path(os.getpid())
        self.assertIsNotNone(path)
        self.assertTrue(os.path.isabs(path))

    def test_process_name_of_bogus_pid(self):
        self.assertIsNone(process_name(999_999_999))

    @unittest.skipUnless(IS_WINDOWS, "windows-only")
    def test_visible_windows_is_a_list(self):
        windows = visible_windows()
        self.assertIsInstance(windows, list)
        for window in windows[:5]:
            self.assertIsInstance(window.title, str)
            self.assertGreater(window.hwnd, 0)

    def test_find_windows_titled_no_match(self):
        self.assertEqual(find_windows_titled("zzz-no-such-window-title-zzz"), [])

    def test_find_windows_titled_is_case_insensitive(self):
        self.assertEqual(
            find_windows_titled("ZZZ-NO-SUCH-WINDOW-TITLE-ZZZ"),
            find_windows_titled("zzz-no-such-window-title-zzz"),
        )


class TestPresenceWindow(unittest.TestCase):
    def test_title_defaults_to_game_name(self):
        window = PresenceWindow(_config())
        self.assertEqual(window.title, "ARKNIGHTS: ENDFIELD")

    def test_title_override(self):
        window = PresenceWindow(_config(), title="Custom")
        self.assertEqual(window.title, "Custom")

    def test_metrics_line_counts_updates_and_uptime(self):
        config = _config()
        supervisor = PresenceSupervisor(config)
        supervisor.stats.updates = 7
        supervisor.stats.reconnects = 2
        window = PresenceWindow(config, supervisor=supervisor)
        text = window._metrics_text()
        self.assertIn("7", text)
        self.assertIn("2", text)
        self.assertIn("мин", text)

    def test_error_line_shows_last_error(self):
        config = _config()
        supervisor = PresenceSupervisor(config)
        supervisor.stats.last_error = "boom"
        window = PresenceWindow(config, supervisor=supervisor)
        self.assertIn("boom", window._error_text())

    def test_error_line_uses_placeholder_when_clean(self):
        window = PresenceWindow(_config())
        self.assertIn("—", window._error_text())

    def test_state_is_connecting_before_any_connection(self):
        window = PresenceWindow(_config())
        text, colour = window._state()
        self.assertIn("подключение", text)
        self.assertEqual(colour, COLOR_BUSY)

    def test_state_is_ok_once_connected(self):
        config = _config()
        supervisor = PresenceSupervisor(config)
        supervisor.stats.connections = 1
        supervisor.stats.connected = True
        window = PresenceWindow(config, supervisor=supervisor)
        text, colour = window._state()
        self.assertEqual(text, "подключено")
        self.assertEqual(colour, COLOR_OK)

    def test_state_is_error_when_connection_failed(self):
        config = _config()
        supervisor = PresenceSupervisor(config)
        supervisor.stats.last_error = "no ipc"
        window = PresenceWindow(config, supervisor=supervisor)
        text, colour = window._state()
        self.assertEqual(colour, COLOR_ERROR)
        self.assertIn("нет связи", text)

    def test_set_text_writes_only_on_change(self):
        """Redundant repaints are what make the old window flicker."""
        from unittest import mock

        import worthlesstask.ui.window as window_module

        calls: list[tuple[int, str]] = []

        class _StubUser32:
            @staticmethod
            def SetWindowTextW(handle, text):
                calls.append((handle, text))
                return 1

        window = PresenceWindow(_config())
        window._rendered[42] = "first"
        with mock.patch.object(window_module, "_user32", _StubUser32):
            window._set_text(42, "first")
            self.assertEqual(calls, [])
            window._set_text(42, "second")
            self.assertEqual(calls, [(42, "second")])
            window._set_text(42, "second")
            self.assertEqual(len(calls), 1)

    def test_stop_event_is_set_by_request(self):
        window = PresenceWindow(_config())
        self.assertFalse(window.stop_event.is_set())
        window._request_stop()
        self.assertTrue(window.stop_event.is_set())

    @unittest.skipUnless(IS_WINDOWS, "windows-only")
    def test_run_with_window_is_callable(self):
        self.assertTrue(callable(run_with_window))

    def test_window_error_is_a_project_error(self):
        from worthlesstask.core.errors import worthlesstaskError

        self.assertTrue(issubclass(WindowError, worthlesstaskError))

    def test_handle_restypes_are_32_bit(self):
        """GDI/USER handles must truncate garbage high RAX bits.

        Regression (2026-09-26): the kernel left 0xFFFFFFFF in the high half
        for CreateSolidBrush and friends, SelectObject failed, and every
        solid fill painted black while strokes and text survived.
        """
        import ctypes as _ct

        import worthlesstask.ui.window as window_module

        for name in (
            "CreateSolidBrush", "CreatePen", "CreateFontW", "GetStockObject",
            "SelectObject", "CreateRoundRectRgn", "CreateCompatibleDC",
            "CreateCompatibleBitmap", "LoadImageW", "LoadCursorW", "GetDC",
            "BeginPaint", "MonitorFromWindow", "CreateWindowExW",
        ):
            handle = getattr(window_module._user32, name, None)
            if handle is None:
                handle = getattr(window_module._gdi32, name, None)
            self.assertIsNotNone(handle, name)
            self.assertIs(handle.restype, _ct.c_uint, name)

    @unittest.skipUnless(IS_WINDOWS, "windows-only")
    def test_brush_handles_are_usable(self):
        import worthlesstask.ui.window as window_module

        brush = window_module._gdi32.CreateSolidBrush(0x000C52B2)
        try:
            self.assertNotEqual(brush, 0)
            self.assertLessEqual(brush, 0xFFFFFFFF)
        finally:
            window_module._gdi32.DeleteObject(brush)


class TestWindowLanguage(unittest.TestCase):
    """The title-bar EN/RU switch retranslates the whole window."""

    def test_default_is_russian(self):
        window = PresenceWindow(_config())
        self.assertEqual(window._lang, "ru")
        self.assertEqual(window._t("nav_home"), "Главная")

    def test_english_retranslates_labels(self):
        window = PresenceWindow(_config())
        window._lang = "en"
        self.assertEqual(window._t("nav_home"), "Home")
        self.assertEqual(window._t("nav_about"), "About")
        self.assertEqual(window._action_label(), "Start")
        self.assertIn("min", window._uptime_text())

    def test_every_key_has_both_languages(self):
        for key, pair in PresenceWindow.STRINGS.items():
            self.assertIsInstance(pair, tuple, key)
            self.assertEqual(len(pair), 2, key)
            self.assertTrue(all(isinstance(part, str) and part for part in pair), key)

    def test_language_change_repaints(self):
        window = PresenceWindow(_config())
        before = window._display()
        window._lang = "en"
        self.assertNotEqual(before, window._display())


class TestDetectorFlagContract(unittest.TestCase):
    """Discord credits a quest only when the window FLAGS are right.

    Proven live against Discord 619060 (2026-09-25 A/B): ``WS_CAPTION`` must be
    present and ``WS_EX_LAYERED`` must be absent, otherwise the decider never
    logs ``visibleGame=`` and the quest never progresses. The 2026-09-21 build
    shipped a layered popup and silently failed detection for every game —
    these tests keep that regression from coming back.
    """

    SOURCE = Path(__file__).resolve().parents[1] / "worthlesstask" / "ui" / "window.py"

    def setUp(self) -> None:
        self.source = self.SOURCE.read_text(encoding="utf-8")

    def test_style_line_keeps_caption_and_drops_popup(self) -> None:
        match = re.search(r"^\s+style = (WS_[A-Z0-9_| ]+)$", self.source, re.MULTILINE)
        self.assertIsNotNone(match, "CreateWindowEx style assignment not found")
        self.assertIn("WS_CAPTION", match.group(1))
        self.assertNotIn("WS_POPUP", match.group(1))

    def test_create_window_ex_is_not_layered(self) -> None:
        match = re.search(r"CreateWindowExW\(\s*([A-Za-z_]+),", self.source)
        self.assertIsNotNone(match, "CreateWindowExW call not found")
        self.assertNotIn("WS_EX_LAYERED", match.group(1))

    def test_message_loop_never_sleeps(self) -> None:
        """WM_CLOSE destroys at once; no synchronous fade may return."""
        start = self.source.index("def _on_message")
        end = self.source.index("def _begin_close")
        self.assertNotIn("time.sleep", self.source[start:end])
        self.assertNotIn("_fade_out_close", self.source)

    def test_every_message_returns_an_lresult(self) -> None:
        """The DefWindowProc fallback belongs to _on_message itself.

        Regression: the fallback once slid into _hover_tick, so every
        unhandled message returned None and ctypes poisoned the whole
        message loop (black window, native frame, TypeError storm).
        """
        tail = self.source[self.source.index("def _on_message"):self.source.index("def _begin_close")]
        self.assertIn(
            "            _user32.PostQuitMessage(0)\n"
            "            return 0\n"
            "        return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)\n",
            tail,
        )
        hover = self.source[self.source.index("def _hover_tick"):self.source.index("def _begin_close")]
        self.assertNotIn("DefWindowProcW", hover)

    def test_close_is_instant(self) -> None:
        """No exit animation: the shrink timer is gone, closing destroys."""
        self.assertNotIn("TIMER_CLOSE", self.source)
        self.assertNotIn("_close_tick", self.source)
        self.assertNotIn("CLOSE_STEPS", self.source)
        begin = self.source.index("def _begin_close")
        block = self.source[begin:begin + 600]
        self.assertIn("DestroyWindow", block)

    def test_frame_is_removed_unconditionally(self) -> None:
        """No native caption/border may survive: NCCALCSIZE always yields."""
        match = re.search(r"if msg == WM_NCCALCSIZE:\n(.*?)\n *return 0", self.source, re.DOTALL)
        self.assertIsNotNone(match, "unconditional WM_NCCALCSIZE branch not found")
        self.assertNotIn("wparam", match.group(1))
        self.assertIn("WM_NCPAINT", self.source)
        self.assertIn("SWP_FRAMECHANGED", self.source)

    def test_caption_buttons_fade_on_hover(self) -> None:
        """Min/max/close (and the language switch) animate via a short timer."""
        self.assertIn("TIMER_HOVER", self.source)
        self.assertIn("_hover_tick", self.source)
        self.assertIn("_ensure_hover_timer", self.source)
        self.assertNotIn("TIMER_ANIM", self.source)

    def test_window_is_flat_and_still(self) -> None:
        """No glow, sheen, gradients or ambient repaint in the paint path."""
        for name in ("_blob", "_sheen", "_alpha_blend", "_gradient",
                     "TIMER_ANIM", "_pulse", "_specks"):
            self.assertNotIn(name, self.source)

    def test_chrome_icons_come_in_sizes(self) -> None:
        """Title bar, taskbar and hero load their own handle, not one stretch."""
        self.assertIn("_icon_small", self.source)
        self.assertIn("_icon_big", self.source)
        self.assertIn("_icon_hero", self.source)
        self.assertIn("WM_SETICON, ICON_SMALL, self._icon_small", self.source)
        self.assertIn("WM_SETICON, ICON_BIG, self._icon_big", self.source)

    def test_fill_uses_a_null_pen(self) -> None:
        """_fill_round must not select NULL_BRUSH into the pen slot.

        Regression (2026-09-26): selecting the hollow *brush* as the pen
        replaced the fill brush, so every solid fill silently went hollow.
        """
        start = self.source.index("def _fill_round")
        end = self.source.index("def _stroke_round")
        block = self.source[start:end]
        self.assertIn("NULL_PEN", block)
        self.assertNotIn("NULL_BRUSH", block)


if __name__ == "__main__":
    unittest.main(verbosity=2)

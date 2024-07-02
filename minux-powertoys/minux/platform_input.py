"""Keystroke sinks and cursor helpers.

A *sink* is whatever actually receives the characters the typing engine emits.
On Windows the real sink synthesizes keystrokes with the Win32 ``SendInput`` API
using Unicode scan codes, so the characters land in whatever window currently
has keyboard focus -- a Notepad, an editor, or a Remote Desktop / VM console
window that forwards keystrokes to the guest. On any other platform (or during
tests) the simulation sink just records what would have been typed.

``SendInput`` with ``KEYEVENTF_UNICODE`` is the standard, documented way to type
arbitrary text on Windows. It requires no driver and no elevation; it is the
same mechanism on-screen keyboards and accessibility tools use.
"""

from __future__ import annotations

import sys
from typing import List, Optional, Tuple

IS_WINDOWS = sys.platform.startswith("win")


class SimulationSink:
    """Records keystrokes instead of sending them. Used off-Windows and in tests."""

    def __init__(self) -> None:
        self.buffer: List[str] = []
        self.events: List[str] = []

    def send_char(self, ch: str) -> None:
        if ch == "\n":
            self.buffer.append("\n")
        else:
            self.buffer.append(ch)
        self.events.append(repr(ch))

    def backspace(self) -> None:
        if self.buffer:
            self.buffer.pop()
        self.events.append("<bs>")

    @property
    def text(self) -> str:
        return "".join(self.buffer)


if IS_WINDOWS:  # pragma: no cover - exercised only on Windows
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    VK_RETURN = 0x0D
    VK_BACK = 0x08
    VK_TAB = 0x09

    ULONG_PTR = ctypes.POINTER(wintypes.ULONG)

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class _INPUTunion(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]

    class _INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTunion)]

    _user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
    _user32.SendInput.restype = wintypes.UINT

    def _send(inputs: List[_INPUT]) -> None:
        n = len(inputs)
        arr = (_INPUT * n)(*inputs)
        sent = _user32.SendInput(n, arr, ctypes.sizeof(_INPUT))
        if sent != n:
            raise ctypes.WinError(ctypes.get_last_error())

    def _key_unicode(code: int, keyup: bool) -> _INPUT:
        flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if keyup else 0)
        ki = _KEYBDINPUT(0, code, flags, 0, None)
        return _INPUT(INPUT_KEYBOARD, _INPUTunion(ki=ki))

    def _key_vk(vk: int, keyup: bool) -> _INPUT:
        flags = KEYEVENTF_KEYUP if keyup else 0
        ki = _KEYBDINPUT(vk, 0, flags, 0, None)
        return _INPUT(INPUT_KEYBOARD, _INPUTunion(ki=ki))

    class WindowsSendInputSink:
        """Types into the currently focused window via SendInput."""

        def send_char(self, ch: str) -> None:
            if ch == "\n" or ch == "\r":
                _send([_key_vk(VK_RETURN, False), _key_vk(VK_RETURN, True)])
                return
            if ch == "\t":
                _send([_key_vk(VK_TAB, False), _key_vk(VK_TAB, True)])
                return
            cp = ord(ch)
            if cp > 0xFFFF:
                # Astral-plane char (e.g. emoji): send as a UTF-16 surrogate pair.
                cp -= 0x10000
                hi = 0xD800 + (cp >> 10)
                lo = 0xDC00 + (cp & 0x3FF)
                _send([
                    _key_unicode(hi, False), _key_unicode(hi, True),
                    _key_unicode(lo, False), _key_unicode(lo, True),
                ])
                return
            _send([_key_unicode(cp, False), _key_unicode(cp, True)])

        def backspace(self) -> None:
            _send([_key_vk(VK_BACK, False), _key_vk(VK_BACK, True)])

    def get_cursor_pos() -> Tuple[int, int]:
        pt = wintypes.POINT()
        _user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def get_screen_size() -> Tuple[int, int]:
        SM_CXSCREEN, SM_CYSCREEN = 0, 1
        return (_user32.GetSystemMetrics(SM_CXSCREEN),
                _user32.GetSystemMetrics(SM_CYSCREEN))

else:
    WindowsSendInputSink = None  # type: ignore

    def get_cursor_pos() -> Tuple[int, int]:  # pragma: no cover
        return (0, 0)

    def get_screen_size() -> Tuple[int, int]:  # pragma: no cover
        return (0, 0)


def make_default_sink():
    """Return the best available real sink, or a simulation sink off-Windows."""
    if IS_WINDOWS and WindowsSendInputSink is not None:
        return WindowsSendInputSink()
    return SimulationSink()


def corner_failsafe_tripped(margin: int = 3) -> bool:
    """True when the mouse is jammed into a screen corner.

    A panic gesture: slam the pointer into any corner to abort typing, mirroring
    the failsafe convention of desktop automation tools. Always False
    off-Windows (no global cursor to read).
    """
    if not IS_WINDOWS:
        return False
    x, y = get_cursor_pos()
    w, h = get_screen_size()
    near_x = x <= margin or x >= (w - 1 - margin)
    near_y = y <= margin or y >= (h - 1 - margin)
    return near_x and near_y

"""DPI awareness and live font scaling for the whole app.

On a high-DPI monitor tkinter renders tiny unless the process declares DPI
awareness, so we do that first. Then a :class:`FontScaler` scales every named
font (the standard Tk fonts plus a few of our own) by a single factor, which the
A- / A+ buttons change live and which is remembered between launches.

Widgets opt into the scalable headings by referencing the named fonts by string:
``font="MinuxTitle"``, ``"MinuxHeading"``, ``"MinuxBanner"``. Body text, the text
box, entries and buttons ride on the standard Tk fonts, which we also scale.
"""

from __future__ import annotations

import sys

try:
    import tkinter.font as tkfont
    from tkinter import ttk
except Exception:  # pragma: no cover
    tkfont = None  # type: ignore

# Standard Tk named fonts shared by most widgets.
_STANDARD = [
    "TkDefaultFont", "TkTextFont", "TkFixedFont", "TkMenuFont", "TkHeadingFont",
    "TkTooltipFont", "TkSmallCaptionFont", "TkCaptionFont", "TkIconFont",
]

# Our own headings: (name, size delta from the default font, bold).
_CUSTOM = [("MinuxTitle", 5, True), ("MinuxHeading", 2, True), ("MinuxBanner", 16, True)]

MIN_SCALE, MAX_SCALE = 0.7, 3.0


def enable_dpi_awareness() -> None:
    """Tell Windows this process scales itself, so tkinter isn't rendered tiny.

    Must run before the first window is created. No-op off Windows.
    """
    if not sys.platform.startswith("win"):
        return
    import ctypes
    try:
        # PROCESS_SYSTEM_DPI_AWARE = 1
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class FontScaler:
    def __init__(self, root) -> None:
        self.root = root
        self.scale = 1.0
        self._base: dict = {}  # font name -> base size (signed int as Tk reports)
        self._capture_standard()
        self._make_custom()
        self._wire_ttk_styles()

    # ----- setup ----------------------------------------------------------- #
    def _default_size(self) -> int:
        try:
            s = int(tkfont.nametofont("TkDefaultFont").cget("size"))
            return abs(s) or 9
        except Exception:
            return 9

    def _capture_standard(self) -> None:
        for n in _STANDARD:
            try:
                self._base[n] = int(tkfont.nametofont(n).cget("size"))
            except Exception:
                pass

    def _make_custom(self) -> None:
        ds = self._default_size()
        try:
            family = tkfont.nametofont("TkDefaultFont").cget("family")
        except Exception:
            family = ""
        for name, delta, bold in _CUSTOM:
            size = ds + delta
            weight = "bold" if bold else "normal"
            try:
                tkfont.Font(name=name, exists=False, family=family, size=size, weight=weight)
            except Exception:
                # Already exists: just reconfigure it.
                try:
                    tkfont.nametofont(name).configure(family=family, size=size, weight=weight)
                except Exception:
                    continue
            self._base[name] = size

    def _wire_ttk_styles(self) -> None:
        # Native ttk themes can ignore TkDefaultFont, so point the common widget
        # classes at it explicitly; then scaling it scales them too.
        try:
            style = ttk.Style(self.root)
            style.configure(".", font="TkDefaultFont")
            for cls in ("TLabel", "TButton", "TCheckbutton", "TRadiobutton",
                        "TEntry", "TSpinbox", "TLabelframe.Label", "TNotebook.Tab"):
                style.configure(cls, font="TkDefaultFont")
        except Exception:
            pass

    # ----- scaling --------------------------------------------------------- #
    def _scaled(self, raw: int) -> int:
        if raw == 0:
            raw = 9
        sign = -1 if raw < 0 else 1
        return sign * max(6, int(round(abs(raw) * self.scale)))

    def apply(self, scale: float) -> float:
        self.scale = max(MIN_SCALE, min(MAX_SCALE, float(scale)))
        for name, raw in self._base.items():
            try:
                tkfont.nametofont(name).configure(size=self._scaled(raw))
            except Exception:
                pass
        return self.scale

    def step(self, delta: float) -> float:
        return self.apply(self.scale + delta)

    def percent(self) -> int:
        return int(round(self.scale * 100))

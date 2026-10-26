"""A line-numbered text editor widget, styled after a code editor.

A :class:`LineNumberedText` is a ttk.Frame holding a monospace Text with a
line-number gutter on the left (like Visual Studio / VS Code), a vertical
scrollbar, and a subtle current-line highlight. It reports edits and caret
moves through callbacks so the host can update a live estimate and an
``Ln N, Col M`` readout.

The gutter is a Canvas redrawn from the Text's visible region, so wrapped lines
and scrolling stay in sync, and the numbers ride on ``TkFixedFont`` so they grow
with the app's A+/A- text size.
"""

from __future__ import annotations

from typing import Callable, Optional

try:
    import tkinter as tk
    from tkinter import ttk
    import tkinter.font as tkfont
except Exception:  # pragma: no cover - headless
    tk = None  # type: ignore


GUTTER_BG = "#f3f3f3"      # VS Code light gutter
GUTTER_FG = "#9aa0a6"      # muted line numbers
CURLINE_BG = "#eef3fb"     # faint current-line band
EDITOR_FONT = "TkFixedFont"


if tk is not None:
    _Base = ttk.Frame
else:  # pragma: no cover
    _Base = object


class LineNumberedText(_Base):
    def __init__(self, master,
                 on_change: Optional[Callable[[], None]] = None,
                 on_caret: Optional[Callable[[int, int], None]] = None,
                 height: int = 10) -> None:
        super().__init__(master)
        self._on_change = on_change
        self._on_caret = on_caret

        self.gutter = tk.Canvas(self, width=44, highlightthickness=0,
                                bd=0, background=GUTTER_BG)
        self.gutter.pack(side="left", fill="y")

        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self._on_scrollbar)
        self.scroll.pack(side="right", fill="y")

        self.text = tk.Text(self, height=height, wrap="word", font=EDITOR_FONT,
                            undo=True, bd=0, highlightthickness=1,
                            highlightbackground="#c8c8c8", highlightcolor="#4c9aff",
                            yscrollcommand=self._on_textscroll)
        self.text.pack(side="right", fill="both", expand=True)
        self.text.tag_configure("curline", background=CURLINE_BG)

        for seq in ("<KeyRelease>", "<ButtonRelease-1>", "<<Paste>>", "<<Cut>>",
                    "<Configure>", "<MouseWheel>"):
            self.text.bind(seq, self._on_edit, add="+")
        # Redraw once the widget has real geometry.
        self.after(20, self._refresh)

    # ----- scrolling glue -------------------------------------------------- #
    def _on_scrollbar(self, *args) -> None:
        self.text.yview(*args)
        self._redraw_gutter()

    def _on_textscroll(self, first, last) -> None:
        self.scroll.set(first, last)
        self._redraw_gutter()

    # ----- events ---------------------------------------------------------- #
    def _on_edit(self, _event=None) -> None:
        self._refresh()
        if self._on_change:
            self._on_change()

    def _refresh(self, _event=None) -> None:
        self._redraw_gutter()
        self._highlight_current_line()
        self._report_caret()

    def _report_caret(self) -> None:
        if not self._on_caret:
            return
        try:
            line, col = self.text.index("insert").split(".")
            self._on_caret(int(line), int(col) + 1)
        except Exception:
            pass

    # ----- rendering ------------------------------------------------------- #
    def _highlight_current_line(self) -> None:
        self.text.tag_remove("curline", "1.0", "end")
        try:
            self.text.tag_add("curline", "insert linestart", "insert lineend+1c")
        except Exception:
            pass

    def _redraw_gutter(self) -> None:
        self.gutter.delete("all")
        try:
            font = tkfont.nametofont(EDITOR_FONT)
        except Exception:
            font = None
        last = self.text.index("end-1c").split(".")[0]
        digits = max(2, len(last))
        if font is not None:
            width = font.measure("0" * digits) + 12
            if int(self.gutter.cget("width")) != width:
                self.gutter.configure(width=width)
        pad = int(self.gutter.cget("width")) - 6

        i = self.text.index("@0,0")
        while True:
            info = self.text.dlineinfo(i)
            if info is None:
                break
            y = info[1]
            num = i.split(".")[0]
            self.gutter.create_text(pad, y, anchor="ne", text=num,
                                    fill=GUTTER_FG, font=font or EDITOR_FONT)
            nxt = self.text.index(f"{i}+1line")
            if nxt == i:
                break
            i = nxt

    # ----- host helpers ---------------------------------------------------- #
    def refresh(self) -> None:
        """Force a redraw (e.g. after the app font size changes)."""
        self._refresh()

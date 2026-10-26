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

from . import icons


GUTTER_BG = "#f3f3f3"      # VS Code light gutter
GUTTER_FG = "#9aa0a6"      # muted line numbers
CURLINE_BG = "#eef3fb"     # faint current-line band
SEL_BG = "#add6ff"         # VS Code selection: light blue, dark text stays readable
SEL_BG_INACTIVE = "#d6e4f7"  # selection when the editor loses focus
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
                            foreground="#1e1e1e", background="#ffffff", insertbackground="#1e1e1e",
                            # VS Code-style selection: light blue band, dark text stays readable.
                            selectbackground=SEL_BG, selectforeground="#1e1e1e",
                            inactiveselectbackground=SEL_BG_INACTIVE,
                            yscrollcommand=self._on_textscroll)
        self.text.pack(side="right", fill="both", expand=True)
        self.text.tag_configure("curline", background=CURLINE_BG)
        # Keep the selection drawn above the current-line highlight.
        self.text.tag_raise("sel")

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


# Office-style palette for the ribbon.
_HOVER_BG = "#eaf2fb"
_HOVER_BORDER = "#c3ddf5"
_ACTIVE_BG = "#cfe4f8"
_ACTIVE_BORDER = "#8bb9e4"
_RIBBON_BG = "#f7f7f7"
RIBBON_BG = _RIBBON_BG   # public alias for hosts
_CAPTION_FG = "#8a8a8a"
_ICON_FG = "#444b53"
_ICON_DISABLED = "#b6bbc0"


class IconButton(tk.Frame if tk is not None else object):
    """A flat, Office-ribbon-style button: a vector icon over (or beside) a label.

    Behaves like a button (hover highlight, click command). Can act as a toggle
    that shows a persistent "pressed" look via :meth:`set_active`, and can be
    enabled/disabled with :meth:`set_enabled`. The icon rides on the app text
    size when the host calls :meth:`relayout` after a scale change.
    """

    def __init__(self, master, icon: str, text: str = "", command=None,
                 accent: Optional[str] = None, orient: str = "vertical",
                 bg: str = _RIBBON_BG) -> None:
        super().__init__(master, bd=0, highlightthickness=1,
                         highlightbackground=bg, highlightcolor=bg, background=bg)
        self._icon = icon
        self._command = command
        self._accent = accent
        self._orient = orient
        self._base_bg = bg
        self._enabled = True
        self._active = False
        self._pressed = False

        self._size = self._icon_size()
        self.canvas = tk.Canvas(self, width=self._size, height=self._size,
                                highlightthickness=0, bd=0, background=bg)
        self.label = tk.Label(self, text=text, background=bg, foreground=_ICON_FG) if text else None

        if orient == "vertical":
            self.canvas.pack(side="top", padx=8, pady=(5, 1))
            if self.label:
                self.label.pack(side="top", padx=6, pady=(0, 4))
        else:
            self.canvas.pack(side="left", padx=(7, 3), pady=4)
            if self.label:
                self.label.pack(side="left", padx=(0, 9), pady=4)

        self._tip_text = text
        self._tip = None
        self._tip_after = None
        self._compact = False

        self._parts = [self, self.canvas] + ([self.label] if self.label else [])
        for w in self._parts:
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", self._on_press)
            w.bind("<ButtonRelease-1>", self._on_release)
        self._redraw()
        self._apply_bg(bg, bg)

    # ----- responsive: hide the text label (icon-only) --------------------- #
    def set_compact(self, on: bool) -> None:
        on = bool(on)
        if on == self._compact or self.label is None:
            self._compact = on
            return
        self._compact = on
        if on:
            self.label.pack_forget()
        elif self._orient == "vertical":
            self.label.pack(side="top", padx=6, pady=(0, 4))
        else:
            self.label.pack(side="left", padx=(0, 9), pady=4)

    # ----- sizing / drawing ----------------------------------------------- #
    def _icon_size(self) -> int:
        try:
            base = abs(int(tkfont.nametofont("TkDefaultFont").cget("size")))
        except Exception:
            base = 12
        return max(16, int(round(base * 1.7)))

    def _redraw(self) -> None:
        color = _ICON_FG if self._enabled else _ICON_DISABLED
        accent = (self._accent or color) if self._enabled else _ICON_DISABLED
        icons.draw(self.canvas, self._icon, self._size, color, accent)

    def relayout(self) -> None:
        """Re-size the icon to the current text size (host calls after zoom)."""
        self._size = self._icon_size()
        self.canvas.configure(width=self._size, height=self._size)
        self._redraw()

    # ----- state ----------------------------------------------------------- #
    def _apply_bg(self, bg: str, border: str) -> None:
        self.configure(background=bg, highlightbackground=border, highlightcolor=border)
        for w in self._parts:
            if w is self:
                continue
            try:
                w.configure(background=bg)
            except Exception:
                pass

    def _restore(self) -> None:
        if self._active and self._enabled:
            self._apply_bg(_ACTIVE_BG, _ACTIVE_BORDER)
        else:
            self._apply_bg(self._base_bg, self._base_bg)

    def set_active(self, on: bool) -> None:
        self._active = bool(on)
        self._restore()

    def set_enabled(self, on: bool) -> None:
        self._enabled = bool(on)
        self._redraw()
        self._restore()
        if self.label:
            self.label.configure(foreground=_ICON_FG if self._enabled else _ICON_DISABLED)

    # ----- tooltip (shown when the label is hidden) ------------------------ #
    def _schedule_tip(self) -> None:
        if self._compact and self._tip_text and self._tip_after is None:
            self._tip_after = self.after(450, self._show_tip)

    def _show_tip(self) -> None:
        self._tip_after = None
        if self._tip is not None or not self._compact or not self._tip_text:
            return
        try:
            x = self.winfo_rootx() + 6
            y = self.winfo_rooty() + self.winfo_height() + 2
            self._tip = tk.Toplevel(self)
            self._tip.wm_overrideredirect(True)
            self._tip.wm_geometry(f"+{x}+{y}")
            tk.Label(self._tip, text=self._tip_text, background="#2b2b2b",
                     foreground="white", padx=6, pady=2, bd=0).pack()
        except Exception:
            self._tip = None

    def _hide_tip(self) -> None:
        if self._tip_after is not None:
            try:
                self.after_cancel(self._tip_after)
            except Exception:
                pass
            self._tip_after = None
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None

    # ----- events ---------------------------------------------------------- #
    def _on_enter(self, _e=None) -> None:
        if self._enabled and not self._active:
            self._apply_bg(_HOVER_BG, _HOVER_BORDER)
        self._schedule_tip()

    def _on_leave(self, _e=None) -> None:
        self._pressed = False
        self._restore()
        self._hide_tip()

    def _on_press(self, _e=None) -> None:
        self._hide_tip()
        if self._enabled:
            self._pressed = True
            self._apply_bg(_ACTIVE_BG, _ACTIVE_BORDER)

    def _on_release(self, _e=None) -> None:
        if self._enabled and self._pressed and self._command:
            self._pressed = False
            self._on_enter()
            self._command()
        else:
            self._pressed = False
            self._restore()


class RibbonGroup(tk.Frame if tk is not None else object):
    """A labelled cluster of ribbon controls with a caption underneath."""

    def __init__(self, master, title: str, bg: str = _RIBBON_BG) -> None:
        super().__init__(master, background=bg)
        self._bg = bg
        self.body = tk.Frame(self, background=bg)
        self.body.pack(side="top", fill="both", expand=True)
        self.caption = tk.Label(self, text=title, foreground=_CAPTION_FG, background=bg,
                                font="TkSmallCaptionFont")
        self.caption.pack(side="top", pady=(1, 2))
        self._caption_visible = True

    def set_caption_visible(self, on: bool) -> None:
        on = bool(on)
        if on == self._caption_visible:
            return
        self._caption_visible = on
        if on:
            self.caption.pack(side="top", pady=(1, 2))
        else:
            self.caption.pack_forget()

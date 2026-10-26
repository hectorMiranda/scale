"""KeyboardMe -- type a block of text into whatever window you click into.

Built as an embeddable panel (a ttk.Frame) so it lives as a tab inside the one
Minux PowerToys window.

Flow:
  1. Paste or type the text, pick a speed (WPM, a preset, or a total duration).
  2. Hit *Type*. A big countdown shows on screen -- the window stays put (your
     target is usually on another monitor), so during the countdown you click
     into the target window to give it keyboard focus.
  3. When the countdown ends, the text is typed into whatever window has focus,
     at a human cadence, never faster than a person could.

Panic stop: press Esc, click *Stop*, or (on by default) just move the mouse --
typing halts the moment the pointer moves from where it was when typing began.
"""

from __future__ import annotations

import queue
import threading
import time
from typing import Optional

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except Exception:  # pragma: no cover - headless
    tk = None  # type: ignore

from ..typing_engine import TypingProfile, build_plan, run_plan
from ..platform_input import IS_WINDOWS, make_default_sink, mouse_moved, get_cursor_pos
from ..widgets import LineNumberedText, IconButton, RibbonGroup, RIBBON_BG

# (icon, label, wpm) -- the speed presets, each with its own critter/speed icon.
PRESETS = [
    ("turtle", "Slow & careful", 35),
    ("walk", "Natural", 70),
    ("rabbit", "Fast", 110),
    ("bolt", "Human max", 160),
]
MAX_HUMAN_WPM = 160


if tk is not None:
    _Base = ttk.Frame
else:  # pragma: no cover
    _Base = object


class KeyboardMePanel(_Base):
    def __init__(self, master) -> None:
        super().__init__(master, padding=12)
        self._abort = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._events: "queue.Queue[tuple]" = queue.Queue()
        self._flashing = False
        self._flash_on = False
        self._build_ui()
        self.winfo_toplevel().bind("<Escape>", lambda _e: self._stop())
        self.after(60, self._pump)

    # ----- UI -------------------------------------------------------------- #
    def _sep(self, parent) -> None:
        ttk.Separator(parent, orient="vertical").pack(side="left", fill="y", padx=4, pady=3)

    def _build_ui(self) -> None:
        # Shared state variables (names kept so settings/behaviour are unchanged).
        self.mode = tk.StringVar(value="wpm")
        self.duration_min = tk.DoubleVar(value=60.0)
        self.countdown = tk.IntVar(value=5)
        self.add_typos = tk.BooleanVar(value=False)
        self.stop_on_move = tk.BooleanVar(value=True)
        self._icon_buttons = []   # for relayout on text-size change

        # ---- Office-style ribbon ------------------------------------------ #
        ribbon = tk.Frame(self, background=RIBBON_BG, bd=1, relief="solid",
                          highlightthickness=0)
        ribbon.configure(relief="flat")
        ribbon.pack(fill="x", pady=(0, 6))

        # Clipboard group.
        g = RibbonGroup(ribbon, "Clipboard")
        g.pack(side="left", fill="y", padx=(2, 0), pady=1)
        self._ib(g.body, "reset", "Reset", self._reset_text).pack(side="left")
        self._ib(g.body, "paste", "Clear & paste", self._clear_and_paste).pack(side="left")
        self._sep(ribbon)

        # Speed group.
        g = RibbonGroup(ribbon, "Speed")
        g.pack(side="left", fill="y", pady=1)
        self._mode_btns = {
            "wpm": self._ib(g.body, "gauge", "By speed", lambda: self._set_mode("wpm")),
            "duration": self._ib(g.body, "clock", "By time", lambda: self._set_mode("duration")),
        }
        self._mode_btns["wpm"].pack(side="left")
        self._mode_btns["duration"].pack(side="left")
        self._preset_btns = {}
        for icon, label, val in PRESETS:
            b = self._ib(g.body, icon, label, lambda v=val: self._apply_preset(v))
            b.pack(side="left")
            self._preset_btns[val] = b
        # Fine speed + duration controls, stacked under the preset row.
        fine = tk.Frame(g.body, background=RIBBON_BG)
        fine.pack(side="left", padx=(6, 2))
        self.wpm_scale = ttk.Scale(fine, from_=15, to=MAX_HUMAN_WPM, length=120,
                                   orient="horizontal")
        self.wpm_scale.set(70)
        # Wire the callback only after the initial value is set, so it doesn't
        # fire before the rest of the ribbon exists.
        self.wpm_scale.configure(command=lambda _v: self._on_wpm_change())
        self.wpm_scale.grid(row=0, column=0, sticky="w")
        self.wpm_label = ttk.Label(fine, text="70 WPM", background=RIBBON_BG,
                                   width=8, foreground="#444b53")
        self.wpm_label.grid(row=0, column=1, sticky="w", padx=(6, 0))
        dline = tk.Frame(fine, background=RIBBON_BG)
        dline.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        tk.Label(dline, text="minutes:", background=RIBBON_BG,
                 foreground="#8a8a8a").pack(side="left")
        ttk.Spinbox(dline, from_=0.1, to=600, increment=1, width=7,
                    textvariable=self.duration_min,
                    command=self._refresh_estimate).pack(side="left", padx=(4, 0))
        self._sep(ribbon)

        # Options group.
        g = RibbonGroup(ribbon, "Options")
        g.pack(side="left", fill="y", pady=1)
        cd = tk.Frame(g.body, background=RIBBON_BG)
        cd.pack(side="left", padx=(4, 2))
        tk.Label(cd, text="Countdown", background=RIBBON_BG,
                 foreground="#8a8a8a").pack(side="top")
        cdrow = tk.Frame(cd, background=RIBBON_BG)
        cdrow.pack(side="top")
        ttk.Spinbox(cdrow, from_=0, to=60, width=4, textvariable=self.countdown,
                    command=self._refresh_estimate).pack(side="left")
        tk.Label(cdrow, text="s", background=RIBBON_BG,
                 foreground="#8a8a8a").pack(side="left", padx=(2, 0))
        self._typo_btn = self._ib(g.body, "pencil", "Typos", self._toggle_typos)
        self._typo_btn.pack(side="left")
        self._move_btn = self._ib(g.body, "mouse", "Stop on move", self._toggle_move)
        self._move_btn.pack(side="left")
        self._sep(ribbon)

        # Run group.
        g = RibbonGroup(ribbon, "Run")
        g.pack(side="left", fill="y", pady=1)
        self.type_btn = self._ib(g.body, "play", "Type", self._start, accent="#1a8a4a")
        self.type_btn.pack(side="left")
        self.stop_btn = self._ib(g.body, "stop", "Stop", self._stop, accent="#c0392b")
        self.stop_btn.pack(side="left")
        self.stop_btn.set_enabled(False)

        # Status / typing alert, living in the toolbar (flashes during countdown).
        alert = tk.Frame(ribbon, background=RIBBON_BG)
        alert.pack(side="right", fill="both", expand=True, padx=(6, 2), pady=3)
        self.banner_wrap = tk.Frame(alert, highlightthickness=0, background=RIBBON_BG)
        self.banner_wrap.pack(fill="both", expand=True)
        self.banner = tk.Label(self.banner_wrap, text="", font="MinuxTitle",
                               fg="#064e3b", background=RIBBON_BG)
        self.banner.pack(fill="both", expand=True)

        # ---- Editor ------------------------------------------------------- #
        self.editor = LineNumberedText(self, on_change=self._refresh_estimate,
                                       on_caret=self._on_caret, height=8)
        self.editor.pack(fill="both", expand=True, pady=(0, 2))
        self.text = self.editor.text  # existing code types/reads through self.text
        self.text.focus_set()

        # Editor status strip: Ln/Col on the left, live typing estimate on the right.
        estrip = ttk.Frame(self)
        estrip.pack(fill="x", pady=(0, 4))
        self.caret_lbl = ttk.Label(estrip, text="Ln 1, Col 1", foreground="#888")
        self.caret_lbl.pack(side="left")
        self.estimate_lbl = ttk.Label(estrip, text="", foreground="#0a6", anchor="e")
        self.estimate_lbl.pack(side="right")

        # ---- Bottom status bar (progress + messages) ---------------------- #
        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill="x", pady=(2, 1))
        self.status = ttk.Label(self, text=self._platform_hint(), foreground="#666")
        self.status.pack(anchor="w")

        self._sync_mode()
        self._refresh_estimate()

    def _ib(self, parent, icon, text, command, accent=None):
        b = IconButton(parent, icon, text=text, command=command, accent=accent)
        self._icon_buttons.append(b)
        return b

    def _platform_hint(self) -> str:
        return ("Ready." if IS_WINDOWS else
                "Simulation mode (not on Windows): keystrokes are logged, not sent.")

    # ----- behaviour ------------------------------------------------------- #
    def _set_wpm(self, wpm) -> None:
        # A disabled ttk.Scale ignores .set(), so always enable before setting;
        # _sync_mode() restores the correct enabled/disabled state afterwards.
        self.wpm_scale.configure(state="normal")
        self.wpm_scale.set(float(wpm))

    def _apply_preset(self, wpm: int) -> None:
        self.mode.set("wpm")
        self._set_wpm(wpm)
        self._sync_mode()

    def _set_mode(self, mode: str) -> None:
        self.mode.set(mode)
        self._sync_mode()

    def _on_wpm_change(self) -> None:
        self._refresh_estimate()
        self._update_toggles()

    def _toggle_typos(self) -> None:
        self.add_typos.set(not self.add_typos.get())
        self._update_toggles()
        self._refresh_estimate()

    def _toggle_move(self) -> None:
        self.stop_on_move.set(not self.stop_on_move.get())
        self._update_toggles()

    def _update_toggles(self) -> None:
        """Reflect the current state in the ribbon's toggle buttons."""
        if not hasattr(self, "_move_btn"):   # still being built
            return
        is_wpm = self.mode.get() == "wpm"
        self._mode_btns["wpm"].set_active(is_wpm)
        self._mode_btns["duration"].set_active(not is_wpm)
        cur = self._current_wpm()
        for val, b in self._preset_btns.items():
            b.set_active(is_wpm and cur == val)
        self._typo_btn.set_active(self.add_typos.get())
        self._move_btn.set_active(self.stop_on_move.get())

    def _sync_mode(self) -> None:
        self.wpm_scale.configure(state="normal" if self.mode.get() == "wpm" else "disabled")
        self._update_toggles()
        self._refresh_estimate()

    def _current_wpm(self) -> int:
        return max(15, min(MAX_HUMAN_WPM, int(round(float(self.wpm_scale.get())))))

    def _profile(self) -> TypingProfile:
        return TypingProfile(wpm=self._current_wpm(), max_human_wpm=MAX_HUMAN_WPM,
                             typo_chance=0.03 if self.add_typos.get() else 0.0)

    def _get_text(self) -> str:
        return self.text.get("1.0", "end-1c")

    def _set_text(self, value: str) -> None:
        self.text.delete("1.0", "end")
        if value:
            self.text.insert("1.0", value)
        self.text.focus_set()
        self.editor.refresh()        # programmatic change: redraw gutter/caret
        self._refresh_estimate()

    def _reset_text(self) -> None:
        self._set_text("")

    def _clear_and_paste(self) -> None:
        try:
            clip = self.clipboard_get()
        except Exception:
            clip = ""          # empty or non-text clipboard
        self._set_text(clip)

    def _plan(self):
        prof = self._profile()
        if self.mode.get() == "duration":
            return build_plan(self._get_text(), prof,
                              target_seconds=max(self.duration_min.get(), 0.1) * 60.0, seed=1)
        return build_plan(self._get_text(), prof, seed=1)

    def _on_caret(self, line: int, col: int) -> None:
        if hasattr(self, "caret_lbl"):
            self.caret_lbl.configure(text=f"Ln {line}, Col {col}")

    def on_font_scaled(self) -> None:
        """Called by the launcher after the app text size changes."""
        self.after_idle(self.editor.refresh)
        for b in self._icon_buttons:
            try:
                b.relayout()
            except Exception:
                pass

    def _refresh_estimate(self) -> None:
        if not hasattr(self, "wpm_label"):
            return
        self.wpm_label.configure(text=f"{self._current_wpm()} WPM")
        n = len(self._get_text())
        if not n:
            self.estimate_lbl.configure(text="")
            return
        plan = self._plan()
        self.estimate_lbl.configure(
            text=f"≈ {_fmt_duration(plan.total_seconds)} to type  ·  "
                 f"{n} chars  ·  peak {plan.peak_wpm():.0f} WPM (cap {MAX_HUMAN_WPM})")

    # ----- settings persistence ------------------------------------------- #
    def get_settings(self) -> dict:
        return {
            "mode": self.mode.get(),
            "wpm": self._current_wpm(),
            "duration_min": float(self.duration_min.get()),
            "countdown": int(self.countdown.get()),
            "add_typos": bool(self.add_typos.get()),
            "stop_on_move": bool(self.stop_on_move.get()),
        }

    def apply_settings(self, d: dict) -> None:
        if not isinstance(d, dict):
            return
        try:
            if "mode" in d:
                self.mode.set(d["mode"])
            if "wpm" in d:
                self._set_wpm(d["wpm"])
            if "duration_min" in d:
                self.duration_min.set(float(d["duration_min"]))
            if "countdown" in d:
                self.countdown.set(int(d["countdown"]))
            if "add_typos" in d:
                self.add_typos.set(bool(d["add_typos"]))
            if "stop_on_move" in d:
                self.stop_on_move.set(bool(d["stop_on_move"]))
        except Exception:
            pass
        self._sync_mode()
        self._refresh_estimate()

    # ----- run / stop ------------------------------------------------------ #
    def _start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        if not self._get_text():
            messagebox.showinfo("KeyboardMe", "Type or paste some text first.")
            return
        prof = self._profile()
        if self.mode.get() == "duration":
            plan = build_plan(self._get_text(), prof,
                              target_seconds=max(self.duration_min.get(), 0.1) * 60.0)
        else:
            plan = build_plan(self._get_text(), prof)

        self._abort.clear()
        self.type_btn.set_enabled(False)
        self.stop_btn.set_enabled(True)
        self.progress.configure(maximum=max(plan.printable_chars, 1), value=0)
        cd = max(0, int(self.countdown.get()))
        stop_on_move = self.stop_on_move.get()
        self._worker = threading.Thread(target=self._run, args=(plan, cd, stop_on_move), daemon=True)
        self._worker.start()

    def _run(self, plan, countdown, stop_on_move) -> None:
        for remaining in range(countdown, 0, -1):
            if self._abort.is_set():
                self._events.put(("done", "Cancelled."))
                return
            self._events.put(("banner", f"Typing in {remaining}...", "#7c3aee"))
            self._events.put(("status", "Click your target window now."))
            time.sleep(1.0)

        # Baseline the cursor now -- *after* you've clicked the target window --
        # so later any physical mouse movement means "stop".
        origin = get_cursor_pos() if stop_on_move else None
        self._events.put(("banner", "Typing...", "#0a7"))
        if stop_on_move:
            self._events.put(("status", "Typing... move the mouse to stop."))

        sink = make_default_sink()

        def should_abort() -> bool:
            if self._abort.is_set():
                return True
            if stop_on_move and mouse_moved(origin):
                self._abort.set()
                return True
            return False

        def on_progress(done, total):
            self._events.put(("progress", done, total))

        try:
            done = run_plan(plan, sink, should_abort=should_abort, on_progress=on_progress)
        except Exception as exc:
            self._events.put(("banner", "", "#7c3aee"))
            self._events.put(("done", f"Error: {exc}"))
            return

        self._events.put(("banner", "", "#7c3aee"))
        if self._abort.is_set():
            self._events.put(("done", f"Stopped after {done} chars."))
        else:
            tail = "" if IS_WINDOWS else f"  [simulated] -> {getattr(sink, 'text', '')[:40]!r}"
            self._events.put(("done", f"Done - typed {done} chars.{tail}"))

    def _stop(self) -> None:
        self._abort.set()

    # ----- flashing countdown banner --------------------------------------- #
    def _start_flash(self) -> None:
        self.banner_wrap.configure(highlightthickness=5)
        if not self._flashing:
            self._flashing = True
            self._flash_tick()

    def _flash_tick(self) -> None:
        if not self._flashing:
            return
        self._flash_on = not self._flash_on
        if self._flash_on:
            self.banner_wrap.configure(highlightbackground="#10b981", highlightcolor="#10b981")
            self.banner.configure(bg="#d1fae5")
        else:
            self.banner_wrap.configure(highlightbackground="#047857", highlightcolor="#047857")
            self.banner.configure(bg="#6ee7b7")
        self.after(450, self._flash_tick)

    def _stop_flash(self) -> None:
        self._flashing = False
        self.banner_wrap.configure(highlightthickness=0)
        try:
            self.banner.configure(bg=self.banner_wrap.cget("background"))
        except Exception:
            pass

    # ----- event pump ------------------------------------------------------ #
    def _pump(self) -> None:
        try:
            while True:
                evt = self._events.get_nowait()
                kind = evt[0]
                if kind == "banner":
                    self.banner.configure(text=evt[1])
                    if evt[1]:
                        self._start_flash()
                    else:
                        self._stop_flash()
                elif kind == "status":
                    self.status.configure(text=evt[1])
                elif kind == "progress":
                    self.progress.configure(value=evt[1])
                    self.status.configure(text=f"Typing... {evt[1]}/{evt[2]}")
                elif kind == "done":
                    self.type_btn.set_enabled(True)
                    self.stop_btn.set_enabled(False)
                    self.banner.configure(text="")
                    self._stop_flash()
                    self.status.configure(text=evt[1])
        except queue.Empty:
            pass
        self.after(60, self._pump)


def _fmt_duration(secs: float) -> str:
    secs = int(round(secs))
    if secs < 60:
        return f"{secs}s"
    m, s = divmod(secs, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def build_panel(parent) -> "KeyboardMePanel":
    """Mount a KeyboardMe panel inside ``parent`` (a tab frame)."""
    panel = KeyboardMePanel(parent)
    panel.pack(fill="both", expand=True)
    return panel


def open_window(master=None) -> None:
    """Standalone: open KeyboardMe in its own window (used by `minux.py keyboardme`)."""
    if tk is None:
        raise RuntimeError("tkinter is not available in this Python build.")
    root = master or tk.Tk()
    root.title("KeyboardMe - Minux PowerToys")
    build_panel(root)
    if master is None:
        root.mainloop()


if __name__ == "__main__":
    open_window()

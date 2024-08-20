"""KeyboardMe -- type a block of text into whatever window you click into.

Flow:
  1. Paste or type the text into the box, pick a speed (a WPM, a preset, or a
     total duration like "one hour").
  2. Hit *Type*. A countdown starts and the window gets out of the way, giving
     you time to click into the target window (a Notepad, an editor, a Remote
     Desktop / VM console -- anywhere that takes the keyboard).
  3. When the countdown ends it types the text into whatever has focus, at a
     human cadence, never faster than a person could.

Panic stop: press Esc on the KeyboardMe window, click *Stop*, or slam the mouse
into any screen corner.
"""

from __future__ import annotations

import queue
import threading
from typing import Optional

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except Exception:  # pragma: no cover - headless environments
    tk = None  # type: ignore

from ..typing_engine import TypingProfile, build_plan, run_plan
from ..platform_input import (
    IS_WINDOWS,
    make_default_sink,
    corner_failsafe_tripped,
)

# Speed presets: label -> words-per-minute. "Human max" sits at the cap.
PRESETS = [
    ("Slow & careful", 35),
    ("Natural", 70),
    ("Fast", 110),
    ("Human max", 160),
]

MAX_HUMAN_WPM = 160


class KeyboardMeWindow:
    def __init__(self, master: "tk.Misc") -> None:
        self.win = tk.Toplevel(master)
        self.win.title("KeyboardMe - Minux PowerToys")
        self.win.geometry("560x560")
        self.win.minsize(480, 480)

        self._abort = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._events: "queue.Queue[tuple]" = queue.Queue()

        self._build_ui()
        self.win.bind("<Escape>", lambda _e: self._stop())
        self.win.protocol("WM_DELETE_WINDOW", self._on_close)
        self.win.after(60, self._pump)

    # ----- UI construction ------------------------------------------------- #
    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 6}
        root = ttk.Frame(self.win, padding=12)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="Text to type", font=("", 11, "bold")).pack(anchor="w")
        self.text = tk.Text(root, height=8, wrap="word")
        self.text.pack(fill="both", expand=True, pady=(2, 8))
        self.text.insert("1.0", "")
        self.text.focus_set()

        # --- speed controls ---
        speed = ttk.LabelFrame(root, text="Speed", padding=10)
        speed.pack(fill="x", pady=(0, 8))

        self.mode = tk.StringVar(value="wpm")
        ttk.Radiobutton(speed, text="By speed (WPM)", variable=self.mode,
                        value="wpm", command=self._sync_mode).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(speed, text="By total time", variable=self.mode,
                        value="duration", command=self._sync_mode).grid(row=0, column=1, sticky="w")

        self.wpm = tk.IntVar(value=70)
        self.wpm_scale = ttk.Scale(speed, from_=15, to=MAX_HUMAN_WPM, orient="horizontal",
                                   command=lambda _v: self._refresh_estimate())
        self.wpm_scale.set(70)
        self.wpm_scale.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        speed.columnconfigure(0, weight=1)
        speed.columnconfigure(1, weight=1)

        self.wpm_label = ttk.Label(speed, text="70 WPM")
        self.wpm_label.grid(row=2, column=0, columnspan=2, sticky="w")

        preset_row = ttk.Frame(speed)
        preset_row.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        for label, val in PRESETS:
            ttk.Button(preset_row, text=label, width=13,
                       command=lambda v=val: self._apply_preset(v)).pack(side="left", padx=2)

        dur_row = ttk.Frame(speed)
        dur_row.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(dur_row, text="Total time (minutes):").pack(side="left")
        self.duration_min = tk.DoubleVar(value=60.0)
        ttk.Spinbox(dur_row, from_=0.1, to=600, increment=1, width=8,
                    textvariable=self.duration_min,
                    command=self._refresh_estimate).pack(side="left", padx=6)

        # --- options ---
        opts = ttk.LabelFrame(root, text="Options", padding=10)
        opts.pack(fill="x", pady=(0, 8))

        cd_row = ttk.Frame(opts)
        cd_row.pack(fill="x")
        ttk.Label(cd_row, text="Countdown (seconds):").pack(side="left")
        self.countdown = tk.IntVar(value=5)
        ttk.Spinbox(cd_row, from_=0, to=60, width=6,
                    textvariable=self.countdown).pack(side="left", padx=6)

        self.add_typos = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Add occasional typos + corrections (more realistic)",
                        variable=self.add_typos).pack(anchor="w", pady=(4, 0))
        self.minimize_on_start = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Minimize this window during countdown",
                        variable=self.minimize_on_start).pack(anchor="w")
        self.corner_panic = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Panic stop: shove the mouse into a screen corner",
                        variable=self.corner_panic).pack(anchor="w")

        # --- actions + status ---
        actions = ttk.Frame(root)
        actions.pack(fill="x", pady=(2, 6))
        self.type_btn = ttk.Button(actions, text="Type", command=self._start)
        self.type_btn.pack(side="left")
        self.stop_btn = ttk.Button(actions, text="Stop", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)

        self.progress = ttk.Progressbar(root, mode="determinate")
        self.progress.pack(fill="x", pady=(2, 2))
        self.status = ttk.Label(root, text=self._platform_hint())
        self.status.pack(anchor="w")

        self._sync_mode()
        self._refresh_estimate()

    def _platform_hint(self) -> str:
        if IS_WINDOWS:
            return "Ready."
        return "Simulation mode (not on Windows): keystrokes are logged, not sent."

    # ----- UI behaviour ---------------------------------------------------- #
    def _apply_preset(self, wpm: int) -> None:
        self.mode.set("wpm")
        self.wpm_scale.set(wpm)
        self._sync_mode()
        self._refresh_estimate()

    def _sync_mode(self) -> None:
        by_wpm = self.mode.get() == "wpm"
        state = "normal" if by_wpm else "disabled"
        self.wpm_scale.configure(state=state)
        self._refresh_estimate()

    def _current_wpm(self) -> int:
        return max(15, min(MAX_HUMAN_WPM, int(round(float(self.wpm_scale.get())))))

    def _refresh_estimate(self) -> None:
        if not hasattr(self, "wpm_label"):
            return
        wpm = self._current_wpm()
        self.wpm_label.configure(text=f"{wpm} WPM")
        text = self._get_text()
        n = len(text)
        profile = self._profile()
        if self.mode.get() == "duration":
            target = max(self.duration_min.get(), 0.1) * 60.0
            plan = build_plan(text, profile, target_seconds=target, seed=1)
        else:
            plan = build_plan(text, profile, seed=1)
        secs = plan.total_seconds
        peak = plan.peak_wpm()
        est = _fmt_duration(secs)
        self.status.configure(
            text=f"{n} chars - est. {est} - peak {peak:.0f} WPM (cap {MAX_HUMAN_WPM})"
            if n else self._platform_hint()
        )

    def _profile(self) -> TypingProfile:
        return TypingProfile(
            wpm=self._current_wpm(),
            max_human_wpm=MAX_HUMAN_WPM,
            typo_chance=0.03 if self.add_typos.get() else 0.0,
        )

    def _get_text(self) -> str:
        return self.text.get("1.0", "end-1c")

    # ----- run / stop ------------------------------------------------------ #
    def _start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        text = self._get_text()
        if not text:
            messagebox.showinfo("KeyboardMe", "Type or paste some text first.")
            return

        profile = self._profile()
        if self.mode.get() == "duration":
            target = max(self.duration_min.get(), 0.1) * 60.0
            plan = build_plan(text, profile, target_seconds=target)
        else:
            plan = build_plan(text, profile)

        self._abort.clear()
        self.type_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.configure(maximum=max(plan.printable_chars, 1), value=0)

        cd = max(0, int(self.countdown.get()))
        minimize = self.minimize_on_start.get()
        corner = self.corner_panic.get()

        self._worker = threading.Thread(
            target=self._run, args=(plan, cd, minimize, corner), daemon=True)
        self._worker.start()

    def _run(self, plan, countdown, minimize, corner) -> None:
        import time
        if minimize and IS_WINDOWS:
            self._events.put(("iconify",))
        for remaining in range(countdown, 0, -1):
            if self._abort.is_set():
                self._events.put(("done", "Cancelled."))
                return
            self._events.put(("status", f"Typing in {remaining}... click your target window"))
            time.sleep(1.0)
        self._events.put(("status", "Typing..."))

        sink = make_default_sink()

        def should_abort() -> bool:
            if self._abort.is_set():
                return True
            if corner and corner_failsafe_tripped():
                self._abort.set()
                return True
            return False

        def on_progress(done, total) -> None:
            self._events.put(("progress", done, total))

        try:
            done = run_plan(plan, sink, should_abort=should_abort, on_progress=on_progress)
        except Exception as exc:  # surface injection errors instead of dying silently
            self._events.put(("done", f"Error: {exc}"))
            return

        if self._abort.is_set():
            self._events.put(("done", f"Stopped after {done} chars."))
        else:
            tail = "" if IS_WINDOWS else f"  [simulated] -> {getattr(sink, 'text', '')[:40]!r}"
            self._events.put(("done", f"Done - typed {done} chars.{tail}"))

    def _stop(self) -> None:
        self._abort.set()

    def _on_close(self) -> None:
        self._abort.set()
        self.win.destroy()

    # ----- event pump (main thread) ---------------------------------------- #
    def _pump(self) -> None:
        try:
            while True:
                evt = self._events.get_nowait()
                kind = evt[0]
                if kind == "status":
                    self.status.configure(text=evt[1])
                elif kind == "progress":
                    self.progress.configure(value=evt[1])
                    self.status.configure(text=f"Typing... {evt[1]}/{evt[2]}")
                elif kind == "iconify":
                    try:
                        self.win.iconify()
                    except Exception:
                        pass
                elif kind == "done":
                    self.type_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    self.status.configure(text=evt[1])
                    try:
                        self.win.deiconify()
                    except Exception:
                        pass
        except queue.Empty:
            pass
        self.win.after(60, self._pump)


def _fmt_duration(secs: float) -> str:
    secs = int(round(secs))
    if secs < 60:
        return f"{secs}s"
    m, s = divmod(secs, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def open_window(master: Optional["tk.Misc"] = None) -> "KeyboardMeWindow":
    """Open a KeyboardMe window.

    When ``master`` is given (the launcher's Tk root) the window is a Toplevel on
    it and the caller owns the mainloop. When called standalone it spins up its
    own root and blocks on the mainloop.
    """
    if tk is None:
        raise RuntimeError("tkinter is not available in this Python build.")
    if master is not None:
        return KeyboardMeWindow(master)
    root = tk.Tk()
    root.withdraw()
    win = KeyboardMeWindow(root)
    win.win.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
    return win


if __name__ == "__main__":
    open_window()

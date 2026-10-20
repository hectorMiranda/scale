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

Panic stop: press Esc, click *Stop*, or slam the mouse into any screen corner.
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
from ..platform_input import IS_WINDOWS, make_default_sink, corner_failsafe_tripped

PRESETS = [("Slow & careful", 35), ("Natural", 70), ("Fast", 110), ("Human max", 160)]
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
        self._build_ui()
        self.winfo_toplevel().bind("<Escape>", lambda _e: self._stop())
        self.after(60, self._pump)

    # ----- UI -------------------------------------------------------------- #
    def _build_ui(self) -> None:
        ttk.Label(self, text="Text to type", font=("", 11, "bold")).pack(anchor="w")
        self.text = tk.Text(self, height=8, wrap="word")
        self.text.pack(fill="both", expand=True, pady=(2, 8))
        self.text.focus_set()

        speed = ttk.LabelFrame(self, text="Speed", padding=10)
        speed.pack(fill="x", pady=(0, 8))
        self.mode = tk.StringVar(value="wpm")
        ttk.Radiobutton(speed, text="By speed (WPM)", variable=self.mode, value="wpm",
                        command=self._sync_mode).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(speed, text="By total time", variable=self.mode, value="duration",
                        command=self._sync_mode).grid(row=0, column=1, sticky="w")
        self.wpm_scale = ttk.Scale(speed, from_=15, to=MAX_HUMAN_WPM, orient="horizontal",
                                   command=lambda _v: self._refresh_estimate())
        self.wpm_scale.set(70)
        self.wpm_scale.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        speed.columnconfigure(0, weight=1)
        speed.columnconfigure(1, weight=1)
        self.wpm_label = ttk.Label(speed, text="70 WPM")
        self.wpm_label.grid(row=2, column=0, columnspan=2, sticky="w")
        prow = ttk.Frame(speed)
        prow.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        for label, val in PRESETS:
            ttk.Button(prow, text=label, width=13,
                       command=lambda v=val: self._apply_preset(v)).pack(side="left", padx=2)
        drow = ttk.Frame(speed)
        drow.grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(drow, text="Total time (minutes):").pack(side="left")
        self.duration_min = tk.DoubleVar(value=60.0)
        ttk.Spinbox(drow, from_=0.1, to=600, increment=1, width=8, textvariable=self.duration_min,
                    command=self._refresh_estimate).pack(side="left", padx=6)

        opts = ttk.LabelFrame(self, text="Options", padding=10)
        opts.pack(fill="x", pady=(0, 8))
        crow = ttk.Frame(opts)
        crow.pack(fill="x")
        ttk.Label(crow, text="Countdown (seconds):").pack(side="left")
        self.countdown = tk.IntVar(value=5)
        ttk.Spinbox(crow, from_=0, to=60, width=6, textvariable=self.countdown).pack(side="left", padx=6)
        ttk.Label(crow, text="  <- time to click your target window",
                  foreground="#888").pack(side="left")
        self.add_typos = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Add occasional typos + corrections (more realistic)",
                        variable=self.add_typos).pack(anchor="w", pady=(4, 0))
        self.corner_panic = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Panic stop: shove the mouse into a screen corner",
                        variable=self.corner_panic).pack(anchor="w")

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(2, 6))
        self.type_btn = ttk.Button(actions, text="Type", command=self._start)
        self.type_btn.pack(side="left")
        self.stop_btn = ttk.Button(actions, text="Stop", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)

        # Big, unmissable countdown / typing banner (window stays visible).
        self.banner = tk.Label(self, text="", font=("", 26, "bold"), fg="#7c3aee")
        self.banner.pack(fill="x", pady=(2, 2))
        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill="x", pady=(2, 2))
        self.status = ttk.Label(self, text=self._platform_hint())
        self.status.pack(anchor="w")

        self._sync_mode()
        self._refresh_estimate()

    def _platform_hint(self) -> str:
        return ("Ready." if IS_WINDOWS else
                "Simulation mode (not on Windows): keystrokes are logged, not sent.")

    # ----- behaviour ------------------------------------------------------- #
    def _apply_preset(self, wpm: int) -> None:
        self.mode.set("wpm")
        self.wpm_scale.set(wpm)
        self._sync_mode()

    def _sync_mode(self) -> None:
        self.wpm_scale.configure(state="normal" if self.mode.get() == "wpm" else "disabled")
        self._refresh_estimate()

    def _current_wpm(self) -> int:
        return max(15, min(MAX_HUMAN_WPM, int(round(float(self.wpm_scale.get())))))

    def _profile(self) -> TypingProfile:
        return TypingProfile(wpm=self._current_wpm(), max_human_wpm=MAX_HUMAN_WPM,
                             typo_chance=0.03 if self.add_typos.get() else 0.0)

    def _get_text(self) -> str:
        return self.text.get("1.0", "end-1c")

    def _plan(self):
        prof = self._profile()
        if self.mode.get() == "duration":
            return build_plan(self._get_text(), prof,
                              target_seconds=max(self.duration_min.get(), 0.1) * 60.0, seed=1)
        return build_plan(self._get_text(), prof, seed=1)

    def _refresh_estimate(self) -> None:
        if not hasattr(self, "wpm_label"):
            return
        self.wpm_label.configure(text=f"{self._current_wpm()} WPM")
        n = len(self._get_text())
        if not n:
            self.status.configure(text=self._platform_hint())
            return
        plan = self._plan()
        self.status.configure(
            text=f"{n} chars - est. {_fmt_duration(plan.total_seconds)} - "
                 f"peak {plan.peak_wpm():.0f} WPM (cap {MAX_HUMAN_WPM})")

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
        self.type_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.configure(maximum=max(plan.printable_chars, 1), value=0)
        cd = max(0, int(self.countdown.get()))
        corner = self.corner_panic.get()
        self._worker = threading.Thread(target=self._run, args=(plan, cd, corner), daemon=True)
        self._worker.start()

    def _run(self, plan, countdown, corner) -> None:
        for remaining in range(countdown, 0, -1):
            if self._abort.is_set():
                self._events.put(("done", "Cancelled."))
                return
            self._events.put(("banner", f"Typing in {remaining}...", "#7c3aee"))
            self._events.put(("status", "Click your target window now."))
            time.sleep(1.0)
        self._events.put(("banner", "Typing...", "#0a7"))

        sink = make_default_sink()

        def should_abort() -> bool:
            if self._abort.is_set():
                return True
            if corner and corner_failsafe_tripped():
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

    # ----- event pump ------------------------------------------------------ #
    def _pump(self) -> None:
        try:
            while True:
                evt = self._events.get_nowait()
                kind = evt[0]
                if kind == "banner":
                    self.banner.configure(text=evt[1], fg=evt[2])
                elif kind == "status":
                    self.status.configure(text=evt[1])
                elif kind == "progress":
                    self.progress.configure(value=evt[1])
                    self.status.configure(text=f"Typing... {evt[1]}/{evt[2]}")
                elif kind == "done":
                    self.type_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    self.banner.configure(text="")
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

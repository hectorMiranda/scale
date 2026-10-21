"""Minux PowerToys -- one window, a tab per tool, plus a system-tray icon.

The Tk root created here owns the one and only mainloop. Each PowerToy builds its
UI into a notebook tab. A tray icon (pystray, optional) runs alongside; its menu
posts actions onto a thread-safe queue the Tk loop drains, so all UI work still
happens on the main thread.

If pystray/Pillow aren't installed, the window alone is used and a banner says
so (with the exact pip command). Nothing fails silently.
"""

from __future__ import annotations

import queue
import sys
from typing import Optional

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore

from .registry import all_toys
from . import __version__, config
from .ui import FontScaler, enable_dpi_awareness

_ACTIONS: "queue.Queue[tuple]" = queue.Queue()

PURPLE = (124, 58, 237, 255)


def _make_icon_image(size: int = 64):
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = size
    d.rounded_rectangle([2, 2, w - 2, w - 2], radius=w // 6, fill=PURPLE)
    s = int(w * 0.16)
    d.line([(w * 0.26, w * 0.72), (w * 0.26, w * 0.28)], fill="white", width=s)
    d.line([(w * 0.26, w * 0.30), (w * 0.50, w * 0.58)], fill="white", width=s)
    d.line([(w * 0.50, w * 0.58), (w * 0.74, w * 0.30)], fill="white", width=s)
    d.line([(w * 0.74, w * 0.28), (w * 0.74, w * 0.72)], fill="white", width=s)
    return img


class MinuxApp:
    def __init__(self) -> None:
        if tk is None:
            raise RuntimeError("tkinter is not available in this Python build.")
        self.root = tk.Tk()
        self.root.title(f"Minux PowerToys {__version__}")
        self.root.minsize(520, 560)
        self._tray = None
        self._tray_error = ""
        self._tabs = {}     # key -> tab index
        self._panels = {}   # key -> built panel (for settings)
        self._settings = config.load()
        self._scaler = FontScaler(self.root)
        self._scaler.apply(float(self._settings.get("font_scale", 1.0)))
        self._build_window()
        self._restore_panel_settings()
        # Restore the last window size/position, or fall back to a sensible default.
        geom = self._settings.get("window_geom")
        self.root.geometry(geom if isinstance(geom, str) and "x" in geom else "640x660")
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)
        self.root.after(80, self._drain_actions)

    def _build_window(self) -> None:
        header = ttk.Frame(self.root, padding=(12, 10, 12, 0))
        header.pack(fill="x")
        ttk.Label(header, text="Minux PowerToys", font="MinuxTitle").pack(side="left")

        # Text-size controls (scale the whole UI live; remembered across launches).
        ttk.Label(header, text=f"v{__version__}", foreground="#888").pack(side="right", padx=(8, 0))
        ttk.Button(header, text="A+", width=3, command=lambda: self._zoom(+0.1)).pack(side="right", padx=1)
        self._scale_lbl = ttk.Label(header, width=5, anchor="center",
                                    text=f"{self._scaler.percent()}%")
        self._scale_lbl.pack(side="right")
        ttk.Button(header, text="A−", width=3, command=lambda: self._zoom(-0.1)).pack(side="right", padx=1)
        ttk.Label(header, text="Text size:", foreground="#888").pack(side="right", padx=(0, 4))

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(8, 4))
        for i, toy in enumerate(all_toys()):
            tab = ttk.Frame(self.notebook)
            self.notebook.add(tab, text=toy.name)
            self._tabs[toy.key] = i
            try:
                self._panels[toy.key] = toy.build(tab)
            except Exception as exc:  # a broken tool shows an error, not a crash
                ttk.Label(tab, text=f"{toy.name} failed to load:\n{exc}",
                          foreground="#c00", padding=20).pack()

    # ----- actions from the tray ------------------------------------------- #
    def select_tab(self, key: str) -> None:
        if key in self._tabs:
            self.notebook.select(self._tabs[key])
        self._show_window()

    def _show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _drain_actions(self) -> None:
        try:
            while True:
                action = _ACTIONS.get_nowait()
                if action[0] == "open":
                    self.select_tab(action[1])
                elif action[0] == "show":
                    self._show_window()
                elif action[0] == "quit":
                    self.quit()
                    return
        except queue.Empty:
            pass
        self.root.after(80, self._drain_actions)

    # ----- tray ------------------------------------------------------------ #
    def start_tray(self) -> bool:
        try:
            import pystray
        except Exception as exc:
            self._tray_error = (f"Tray icon off ({exc.__class__.__name__}). "
                                "Enable it with:  pip install pystray Pillow")
            return False
        image = _make_icon_image()
        if image is None:
            self._tray_error = "Tray icon off (Pillow missing). Run:  pip install pystray Pillow"
            return False

        def act(name, *extra):
            return lambda *_: _ACTIONS.put((name, *extra))

        items = [pystray.MenuItem("Show Minux", act("show"), default=True)]
        for toy in all_toys():
            items.append(pystray.MenuItem(toy.name, act("open", toy.key)))
        items.append(pystray.Menu.SEPARATOR)
        items.append(pystray.MenuItem("Quit", act("quit")))

        self._tray = pystray.Icon("minux", image, "Minux PowerToys", pystray.Menu(*items))
        # run_detached() is pystray's supported way to coexist with another GUI
        # loop; fall back to a daemon thread if a backend can't detach.
        try:
            self._tray.run_detached()
        except Exception:
            import threading
            threading.Thread(target=self._run_tray, daemon=True).start()
        return True

    def _run_tray(self) -> None:
        try:
            self._tray.run()
        except Exception as exc:
            self._tray = None
            self._tray_error = f"Tray icon failed to start: {exc}"

    # ----- settings / zoom ------------------------------------------------- #
    def _zoom(self, delta: float) -> None:
        self._scaler.step(delta)
        self._scale_lbl.configure(text=f"{self._scaler.percent()}%")
        self._save()

    def _restore_panel_settings(self) -> None:
        for key, panel in self._panels.items():
            data = self._settings.get(key)
            if data and hasattr(panel, "apply_settings"):
                try:
                    panel.apply_settings(data)
                except Exception:
                    pass

    def _collect_settings(self) -> dict:
        data = dict(self._settings)
        data["font_scale"] = round(self._scaler.scale, 3)
        # Remember the window size/position once it's actually been mapped
        # (before that, geometry reports a meaningless 1x1).
        try:
            if self.root.winfo_width() > 1 and self.root.winfo_height() > 1:
                data["window_geom"] = self.root.geometry()
        except Exception:
            pass
        for key, panel in self._panels.items():
            if hasattr(panel, "get_settings"):
                try:
                    data[key] = panel.get_settings()
                except Exception:
                    pass
        self._settings = data
        return data

    def _save(self) -> None:
        config.save(self._collect_settings())

    # ----- lifecycle ------------------------------------------------------- #
    def _on_window_close(self) -> None:
        self._save()
        if self._tray is not None:
            self.root.withdraw()  # hide to tray; Quit from the tray menu
        else:
            self.quit()

    def quit(self) -> None:
        self._save()
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:
                pass
            self._tray = None
        try:
            self.root.destroy()
        except Exception:
            pass

    def run(self) -> None:
        live = self.start_tray()
        print("Minux PowerToys:",
              "tray icon active (check the ^ overflow by the clock)." if live
              else self._tray_error, file=sys.stderr)
        self.root.mainloop()


def main() -> None:
    MinuxApp().run()


if __name__ == "__main__":
    main()

"""Minux PowerToys launcher: a tray icon plus a window listing the tools.

The Tk root created here owns the one and only mainloop. Tools open as Toplevel
windows on it. A system-tray icon (pystray, optional) runs detached on a
background thread; its menu posts actions into a thread-safe queue that the Tk
loop drains, so all UI work still happens on the main thread.

If pystray/Pillow aren't installed, the launcher window alone is used -- the app
still works, just without a tray icon.
"""

from __future__ import annotations

import queue
from typing import Optional

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore

from .registry import all_toys
from . import __version__

_ACTIONS: "queue.Queue[tuple]" = queue.Queue()


def _make_icon_image(size: int = 64):
    """Build the Minux 'M' tile as a PIL image, or return None if PIL is absent."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    purple = (124, 58, 237, 255)
    d.rounded_rectangle([2, 2, size - 2, size - 2], radius=size // 6, fill=purple)
    # A blocky white M.
    w = size
    s = w * 0.18
    pts_left = [(w * 0.26, w * 0.72), (w * 0.26, w * 0.28)]
    d.line([(w * 0.26, w * 0.72), (w * 0.26, w * 0.28)], fill="white", width=int(s))
    d.line([(w * 0.26, w * 0.30), (w * 0.50, w * 0.58)], fill="white", width=int(s))
    d.line([(w * 0.50, w * 0.58), (w * 0.74, w * 0.30)], fill="white", width=int(s))
    d.line([(w * 0.74, w * 0.28), (w * 0.74, w * 0.72)], fill="white", width=int(s))
    return img


class Launcher:
    def __init__(self) -> None:
        if tk is None:
            raise RuntimeError("tkinter is not available in this Python build.")
        self.root = tk.Tk()
        self.root.title(f"Minux PowerToys {__version__}")
        self.root.geometry("420x360")
        self._tray = None
        self._build_window()
        self.root.after(80, self._drain_actions)

    def _build_window(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)

        header = ttk.Frame(frame)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="Minux PowerToys", font=("", 15, "bold")).pack(side="left")
        ttk.Label(header, text=f"v{__version__}", foreground="#888").pack(side="right")

        ttk.Label(frame, text="Pick a tool:").pack(anchor="w")

        for toy in all_toys():
            card = ttk.Frame(frame, padding=8, relief="groove")
            card.pack(fill="x", pady=4)
            left = ttk.Frame(card)
            left.pack(side="left", fill="x", expand=True)
            ttk.Label(left, text=toy.name, font=("", 11, "bold")).pack(anchor="w")
            ttk.Label(left, text=toy.description, foreground="#666",
                      wraplength=260, justify="left").pack(anchor="w")
            ttk.Button(card, text="Open",
                       command=lambda t=toy: self.open_toy(t.key)).pack(side="right")

        footer = ttk.Frame(frame)
        footer.pack(fill="x", side="bottom", pady=(10, 0))
        ttk.Button(footer, text="Quit", command=self.quit).pack(side="right")

    # ----- actions --------------------------------------------------------- #
    def open_toy(self, key: str) -> None:
        for toy in all_toys():
            if toy.key == key:
                toy.open(self.root)
                return

    def _drain_actions(self) -> None:
        try:
            while True:
                action = _ACTIONS.get_nowait()
                if action[0] == "open":
                    self.open_toy(action[1])
                elif action[0] == "show":
                    self.root.deiconify()
                    self.root.lift()
                elif action[0] == "quit":
                    self.quit()
                    return
        except queue.Empty:
            pass
        self.root.after(80, self._drain_actions)

    # ----- tray ------------------------------------------------------------ #
    def start_tray(self) -> None:
        try:
            import pystray
        except Exception:
            return  # no tray; the window is enough
        image = _make_icon_image()
        if image is None:
            return

        def menu_items():
            items = [
                pystray.MenuItem(toy.name, (lambda k=toy.key: lambda *_: _ACTIONS.put(("open", k)))())
                for toy in all_toys()
            ]
            items.append(pystray.MenuItem("Show launcher", lambda *_: _ACTIONS.put(("show",))))
            items.append(pystray.MenuItem("Quit", lambda *_: _ACTIONS.put(("quit",))))
            return pystray.Menu(*items)

        self._tray = pystray.Icon("minux", image, "Minux PowerToys", menu_items())
        try:
            self._tray.run_detached()
        except Exception:
            # Backend can't detach; fall back to a background thread.
            import threading
            threading.Thread(target=self._tray.run, daemon=True).start()

    # ----- lifecycle ------------------------------------------------------- #
    def quit(self) -> None:
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:
                pass
        self.root.destroy()

    def run(self) -> None:
        self.start_tray()
        self.root.mainloop()


def main() -> None:
    Launcher().run()


if __name__ == "__main__":
    main()

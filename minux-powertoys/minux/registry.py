"""The catalogue of PowerToys shown in the launcher / tray menu.

Each entry knows its display name, a one-line description, and how to open its
window. Adding a new tool is a one-line registration here plus its module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional


@dataclass(frozen=True)
class PowerToy:
    key: str
    name: str
    description: str
    # open(master) -> opens the tool's window on the given Tk root (or standalone
    # when master is None).
    open: Callable[[Optional[Any]], None]


def _open_keyboardme(master: Optional[Any] = None) -> None:
    # Imported lazily so the launcher starts fast and a broken tool can't stop
    # the others from loading.
    from .apps.keyboardme import open_window
    open_window(master)


def all_toys() -> List[PowerToy]:
    return [
        PowerToy(
            key="keyboardme",
            name="KeyboardMe",
            description="Type a block of text into any window at a human pace.",
            open=_open_keyboardme,
        ),
    ]

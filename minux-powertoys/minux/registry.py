"""The catalogue of PowerToys shown as tabs in the Minux window.

Each entry knows its display name, a one-line description, and how to build its
UI into a parent frame (a notebook tab). Adding a new tool is a one-line
registration here plus its module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List


@dataclass(frozen=True)
class PowerToy:
    key: str
    name: str
    description: str
    # build(parent_frame) -> constructs the tool's widgets inside the tab.
    build: Callable[[Any], None]


def _build_keyboardme(parent: Any) -> None:
    # Imported lazily so the window starts fast and a broken tool can't stop the
    # others from loading.
    from .apps.keyboardme import build_panel
    build_panel(parent)


def all_toys() -> List[PowerToy]:
    return [
        PowerToy(
            key="keyboardme",
            name="KeyboardMe",
            description="Type a block of text into any window at a human pace.",
            build=_build_keyboardme,
        ),
    ]

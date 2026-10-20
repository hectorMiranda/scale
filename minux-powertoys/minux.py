#!/usr/bin/env python3
"""Entry point for Minux PowerToys.

    python minux.py            # the Minux window (tabs) + tray icon
    python minux.py keyboardme # same window, KeyboardMe tab selected

On Windows this is the file your shortcut / icon runs.
"""

import sys


def main() -> None:
    from minux.launcher import MinuxApp
    from minux.registry import all_toys

    app = MinuxApp()
    args = sys.argv[1:]
    if args:
        key = args[0].lower()
        keys = [t.key for t in all_toys()]
        if key in keys:
            app.select_tab(key)
        else:
            print(f"Unknown tool: {key}. Available: {', '.join(keys)}")
    app.run()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Entry point for Minux PowerToys.

    python minux.py            # launch the tray + launcher window
    python minux.py keyboardme # jump straight into a tool

See README.md for setup. On Windows this is the file your shortcut / icon runs.
"""

import sys


def main() -> None:
    args = sys.argv[1:]
    if args:
        key = args[0].lower()
        from minux.registry import all_toys
        for toy in all_toys():
            if toy.key == key:
                toy.open(None)  # standalone: tool owns its own mainloop
                return
        print(f"Unknown tool: {key}")
        print("Available:", ", ".join(t.key for t in all_toys()))
        sys.exit(2)

    from minux.launcher import main as launch
    launch()


if __name__ == "__main__":
    main()

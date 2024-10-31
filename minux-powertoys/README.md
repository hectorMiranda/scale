# Minux PowerToys

A small, growing collection of Windows power-user utilities. Click the Minux
tray icon, pick a tool, go.

The first tool is **KeyboardMe**.

## KeyboardMe

Paste a block of text, pick a speed, and KeyboardMe types it into whatever window
you click into next — a Notepad, an editor, or a Remote Desktop / VM console
window where clipboard paste often isn't allowed. It types the way a person does:
varied key-to-key timing, little pauses between words, the occasional longer
pause, and (optionally) a fat-fingered key that gets corrected.

**It will never type faster than a human can.** Every keystroke delay is clamped
to a cap (default 160 WPM). If you ask for a total time that's physically
impossible for the amount of text, it types at the human cap and simply takes
longer than you asked — it won't break the rule.

### Using it

1. Launch the app (see below) and open **KeyboardMe**.
2. Paste or type your text.
3. Pick a speed:
   - **By speed (WPM)** — drag the slider or hit a preset (Slow, Natural, Fast,
     Human max).
   - **By total time** — e.g. set 60 minutes to have a paragraph trickle in over
     an hour.
   The status line shows the estimated duration and the peak speed.
4. Set the **countdown** (default 5s) — your window to click into the target.
5. Hit **Type**. The window gets out of the way, the countdown runs, then the
   text is typed into whatever window has keyboard focus.

**Panic stop:** press `Esc` on the KeyboardMe window, click **Stop**, or slam the
mouse pointer into any screen corner.

## Install & run (Windows)

KeyboardMe's core needs only a standard Python 3 install (tkinter + ctypes are
included) — no pip step required:

```
python minux.py
```

or just double-click **`run.bat`**.

For the system-tray icon, install the two optional extras once:

```
pip install -r requirements.txt
```

Without them the app still runs; you just get the launcher window instead of a
tray icon.

Jump straight into a tool without the launcher:

```
python minux.py keyboardme
```

### Make it a clickable icon

Create a desktop shortcut to `run.bat` (or to `pythonw.exe minux.py` for no
console window) and set its icon. Drop the shortcut in your Start menu or pin it.

## How the typing works

KeyboardMe synthesizes keystrokes with the Win32 `SendInput` API using Unicode
scan codes — the same documented mechanism on-screen keyboards and accessibility
tools use. No driver, no admin rights. Because the keystrokes enter the normal
input queue, they reach whatever window has focus, including RDP/VM client
windows that forward keyboard input to the guest.

The pacing logic lives in `minux/typing_engine.py` and is pure Python with no OS
dependency, so it's unit-tested on any platform. On non-Windows machines the app
runs in **simulation mode**: it logs what it *would* type instead of sending it,
which is how the tests and the dry run work.

## Developing

```
python3 tests/test_typing_engine.py
```

Project layout:

```
minux.py                  entry point (launcher, or `minux.py <tool>`)
minux/
  launcher.py             tray icon + window listing the tools
  registry.py             the catalogue of tools
  typing_engine.py        human-cadence scheduler (pure, tested)
  platform_input.py       SendInput sink (Windows) / simulation sink (else)
  apps/
    keyboardme.py         the KeyboardMe window
tests/
  test_typing_engine.py   speed-cap, duration, determinism, abort
```

Adding a tool: write `minux/apps/<tool>.py` with an `open_window(master)`
function and add one line to `registry.py`.

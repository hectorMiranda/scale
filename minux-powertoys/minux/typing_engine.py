"""Human-like typing engine for KeyboardMe.

This module turns a block of text into a *schedule* of keystrokes, each with a
delay before it, so that the text is emitted at a cadence that resembles a real
person typing rather than a machine dumping characters.

Design rules (these are hard requirements, not preferences):

* **Never faster than a human.** Every inter-key delay is clamped to a floor
  derived from ``max_human_wpm``. No matter what speed or duration is requested,
  the effective rate cannot exceed that cap. Requesting an impossibly short
  duration makes the text take *longer* than asked; it never breaks the cap.
* **Deterministic when seeded.** Pass a ``seed`` to get a reproducible schedule
  (used by the tests and the dry-run simulator). Leave it ``None`` for natural
  run-to-run variation.

The engine is pure Python with no platform dependencies so it can be unit tested
anywhere. Actually *sending* the keystrokes is the job of a "sink" (see
``platform_input.py``); this module only decides *what* to send and *when*.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

# A "word" is assumed to be 5 characters when converting between WPM and
# characters-per-second. This is the standard typing-test convention.
CHARS_PER_WORD = 5

# Absolute ceiling. Even if a caller passes a higher max_human_wpm we refuse to
# emit keystrokes faster than this. ~160 WPM sustained is already at the top of
# real human ability; brief bursts go higher but sustained injection should not.
HARD_CEILING_WPM = 220


@dataclass
class TypingProfile:
    """Tunable parameters that shape the typing rhythm."""

    # Target sustained speed in words-per-minute. Ignored when a target
    # duration is supplied (the duration wins, subject to the human cap).
    wpm: float = 90.0

    # Hard cap on speed. Delays are floored so the realized rate never exceeds
    # this. Kept below HARD_CEILING_WPM.
    max_human_wpm: float = 160.0

    # Fractional jitter applied to each delay (0.35 == +/-35% gaussian spread).
    jitter: float = 0.35

    # Extra pause after a word boundary (space), as a multiple of the base
    # delay, applied with probability ``word_pause_chance``.
    word_pause_chance: float = 0.18
    word_pause_scale: float = 3.0

    # Rare longer "thinking" pause (seconds range) with this probability per
    # character, to break up the rhythm the way real typists do.
    think_pause_chance: float = 0.012
    think_pause_range: Tuple[float, float] = (0.4, 1.6)

    # Occasionally fat-finger a character then correct it with backspace. This
    # both adds realism and consumes time. 0 disables it entirely.
    typo_chance: float = 0.0

    def base_delay(self) -> float:
        """Mean seconds between characters at the target WPM."""
        return _wpm_to_delay(self.wpm)

    def floor_delay(self) -> float:
        """Smallest allowed seconds between characters (the human cap)."""
        capped = min(self.max_human_wpm, HARD_CEILING_WPM)
        return _wpm_to_delay(capped)


def _wpm_to_delay(wpm: float) -> float:
    cps = max(wpm, 1.0) * CHARS_PER_WORD / 60.0
    return 1.0 / cps


def _delay_to_wpm(delay: float) -> float:
    cps = 1.0 / max(delay, 1e-9)
    return cps * 60.0 / CHARS_PER_WORD


# Keyboard neighbours for believable typos (QWERTY). Only lowercase letters.
_NEIGHBOURS = {
    "a": "sqwz", "b": "vghn", "c": "xdfv", "d": "serfcx", "e": "wsdr",
    "f": "drtgvc", "g": "ftyhbv", "h": "gyujnb", "i": "ujko", "j": "huikmn",
    "k": "jiolm", "l": "kop", "m": "njk", "n": "bhjm", "o": "iklp",
    "p": "ol", "q": "wa", "r": "edft", "s": "awedxz", "t": "rfgy",
    "u": "yhji", "v": "cfgb", "w": "qase", "x": "zsdc", "y": "tghu",
    "z": "asx",
}


@dataclass
class Keystroke:
    """One unit of output: the character to emit and the pause before it.

    ``kind`` is normally ``"char"``. ``"backspace"`` means delete one character
    (used by the typo/correct behaviour). ``char`` is the literal to send for
    ``"char"`` strokes.
    """

    delay: float
    char: str = ""
    kind: str = "char"


@dataclass
class TypingPlan:
    strokes: List[Keystroke] = field(default_factory=list)

    @property
    def total_seconds(self) -> float:
        return sum(s.delay for s in self.strokes)

    @property
    def printable_chars(self) -> int:
        return sum(1 for s in self.strokes if s.kind == "char")

    def effective_wpm(self) -> float:
        """Realized typing speed across the whole plan."""
        if self.total_seconds <= 0:
            return 0.0
        return _delay_to_wpm(self.total_seconds / max(self.printable_chars, 1))

    def peak_wpm(self) -> float:
        """Fastest instantaneous speed between two printable characters.

        This is the number that must stay under the human cap: it is the
        tightest the schedule ever gets.
        """
        fastest = 0.0
        for s in self.strokes:
            if s.kind == "char" and s.delay > 0:
                fastest = max(fastest, _delay_to_wpm(s.delay))
        return fastest


def build_plan(
    text: str,
    profile: TypingProfile,
    *,
    target_seconds: Optional[float] = None,
    seed: Optional[int] = None,
) -> TypingPlan:
    """Turn ``text`` into a :class:`TypingPlan`.

    If ``target_seconds`` is given, the per-character speed is chosen to hit that
    total duration -- but still clamped to the human cap, so an unreasonably
    small target simply yields the fastest *humanly* plausible plan (which will
    run longer than requested). That is the "never faster than a human" rule.
    """
    rng = random.Random(seed)
    floor = profile.floor_delay()

    if target_seconds is not None and len(text) > 0:
        # Desired mean delay to land on the requested duration. Clamp to floor.
        wanted = target_seconds / len(text)
        base = max(wanted, floor)
    else:
        base = max(profile.base_delay(), floor)

    strokes: List[Keystroke] = []
    first = True
    for ch in text:
        if profile.typo_chance and ch.lower() in _NEIGHBOURS and rng.random() < profile.typo_chance:
            wrong = rng.choice(_NEIGHBOURS[ch.lower()])
            if ch.isupper():
                wrong = wrong.upper()
            strokes.append(Keystroke(_jittered(base, floor, profile, rng, first), wrong, "char"))
            strokes.append(Keystroke(_jittered(base, floor, profile, rng, False), "", "backspace"))
            first = False

        delay = _jittered(base, floor, profile, rng, first)

        # Longer pause after spaces, sometimes.
        if not first and ch == " " and rng.random() < profile.word_pause_chance:
            delay += base * profile.word_pause_scale * rng.random()

        # Rare "thinking" pause anywhere.
        if not first and rng.random() < profile.think_pause_chance:
            lo, hi = profile.think_pause_range
            delay += lo + (hi - lo) * rng.random()

        strokes.append(Keystroke(delay, ch, "char"))
        first = False

    return TypingPlan(strokes)


def _jittered(
    base: float,
    floor: float,
    profile: TypingProfile,
    rng: random.Random,
    first: bool,
) -> float:
    if first:
        return 0.0
    # Gaussian spread around the base delay, then clamp to the human floor so we
    # can never exceed the maximum human speed on any single keystroke.
    d = rng.gauss(base, base * profile.jitter)
    return max(d, floor)


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #

class StopSignal(Exception):
    """Raised internally to abort a run cleanly."""


def run_plan(
    plan: TypingPlan,
    sink,
    *,
    should_abort: Optional[Callable[[], bool]] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Execute ``plan`` against ``sink``.

    ``sink`` must expose ``send_char(ch)`` and ``backspace()``. ``should_abort``
    is polled before every keystroke so the UI can cancel (panic key, mouse in a
    corner, window closed). Returns the number of printable characters emitted.
    """
    total = plan.printable_chars
    done = 0
    for stroke in plan.strokes:
        if should_abort and should_abort():
            break
        if stroke.delay > 0:
            # Sleep in small slices so an abort is responsive even on a long
            # "thinking" pause.
            remaining = stroke.delay
            while remaining > 0:
                if should_abort and should_abort():
                    return done
                chunk = min(remaining, 0.05)
                sleep(chunk)
                remaining -= chunk
        if stroke.kind == "backspace":
            sink.backspace()
            continue
        sink.send_char(stroke.char)
        done += 1
        if on_progress:
            on_progress(done, total)
    return done

"""Tests for the typing engine. Run anywhere: `python3 tests/test_typing_engine.py`.

These validate the one rule that matters most -- never faster than a human --
plus duration targeting, determinism, and that the simulated output matches the
input text.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from minux.typing_engine import (  # noqa: E402
    TypingProfile, build_plan, run_plan, HARD_CEILING_WPM,
)
from minux.platform_input import SimulationSink  # noqa: E402

SAMPLE = ("The quick brown fox jumps over the lazy dog. "
          "Pack my box with five dozen liquor jugs. 1234567890!\n"
          "Second line, with punctuation; and symbols: @#$%.")


def test_never_faster_than_human():
    prof = TypingProfile(wpm=160, max_human_wpm=160)
    plan = build_plan(SAMPLE, prof, seed=7)
    # No single keystroke may exceed the cap. Allow a hair of float slack.
    assert plan.peak_wpm() <= 160 + 1e-6, plan.peak_wpm()
    assert plan.peak_wpm() <= HARD_CEILING_WPM


def test_impossible_duration_is_clamped_not_broken():
    # Ask for 1 second on a long text: physically super-human. The engine must
    # refuse to exceed the cap, so the plan runs LONGER than requested.
    prof = TypingProfile(max_human_wpm=160)
    plan = build_plan(SAMPLE, prof, target_seconds=1.0, seed=3)
    assert plan.peak_wpm() <= 160 + 1e-6
    assert plan.total_seconds > 1.0  # could not honor the impossible ask
    # The realized speed sits at (not above) the cap.
    assert plan.effective_wpm() <= 160 + 1e-6


def test_reasonable_duration_is_approximated():
    prof = TypingProfile(max_human_wpm=160)
    target = 30.0
    plan = build_plan(SAMPLE, prof, target_seconds=target, seed=5)
    # Within 25% of the requested wall-clock (jitter + pauses move it around).
    assert 0.75 * target <= plan.total_seconds <= 1.25 * target, plan.total_seconds


def test_deterministic_with_seed():
    prof = TypingProfile(wpm=90)
    a = build_plan(SAMPLE, prof, seed=42)
    b = build_plan(SAMPLE, prof, seed=42)
    assert [s.delay for s in a.strokes] == [s.delay for s in b.strokes]
    assert [s.char for s in a.strokes] == [s.char for s in b.strokes]


def test_simulation_reproduces_text_without_typos():
    prof = TypingProfile(wpm=120, typo_chance=0.0)
    plan = build_plan(SAMPLE, prof, seed=1)
    sink = SimulationSink()
    run_plan(plan, sink, sleep=lambda _s: None)
    assert sink.text == SAMPLE


def test_typos_are_corrected_back_to_source():
    # Even with typos enabled, backspaces must restore the intended text.
    prof = TypingProfile(wpm=120, typo_chance=0.4)
    plan = build_plan(SAMPLE, prof, seed=9)
    sink = SimulationSink()
    run_plan(plan, sink, sleep=lambda _s: None)
    assert sink.text == SAMPLE


def test_abort_stops_early():
    prof = TypingProfile(wpm=120)
    plan = build_plan(SAMPLE, prof, seed=2)
    sink = SimulationSink()
    # Abort after 10 characters.
    state = {"n": 0}

    def progress(done, total):
        state["n"] = done

    done = run_plan(plan, sink, should_abort=lambda: state["n"] >= 10,
                    on_progress=progress, sleep=lambda _s: None)
    assert done <= 11
    assert len(sink.text) <= 11


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {e!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)

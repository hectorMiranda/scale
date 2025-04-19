"""Validate bundled samples and typing profiles load and are well-formed."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from minux.data import (  # noqa: E402
    list_samples, load_sample, list_profiles, load_profile,
)

REQUIRED_KEYS = {"name", "wpm", "jitter", "word_pause_chance", "description"}


def test_samples_nonempty():
    names = list_samples()
    assert names, "no samples bundled"
    for n in names:
        assert load_sample(n).strip(), f"empty sample: {n}"


def test_profiles_wellformed():
    names = list_profiles()
    assert names, "no profiles bundled"
    for n in names:
        p = load_profile(n)
        assert REQUIRED_KEYS <= set(p), f"{n} missing keys: {REQUIRED_KEYS - set(p)}"
        assert 1 <= p["wpm"] <= 220, f"{n} wpm out of range"


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    import sys as _s
    _s.exit(1 if _run_all() else 0)

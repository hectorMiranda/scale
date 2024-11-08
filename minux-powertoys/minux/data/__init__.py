"""Loaders for bundled sample texts and typing profiles."""

from __future__ import annotations

import json
import os
from typing import Dict, List

_HERE = os.path.dirname(__file__)


def samples_dir() -> str:
    return os.path.join(_HERE, "samples")


def profiles_dir() -> str:
    return os.path.join(_HERE, "profiles")


def list_samples() -> List[str]:
    d = samples_dir()
    if not os.path.isdir(d):
        return []
    return sorted(f[:-4] for f in os.listdir(d) if f.endswith(".txt"))


def load_sample(name: str) -> str:
    with open(os.path.join(samples_dir(), name + ".txt"), encoding="utf-8") as f:
        return f.read()


def list_profiles() -> List[str]:
    d = profiles_dir()
    if not os.path.isdir(d):
        return []
    return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json"))


def load_profile(name: str) -> Dict:
    with open(os.path.join(profiles_dir(), name + ".json"), encoding="utf-8") as f:
        return json.load(f)


def load_all_profiles() -> Dict[str, Dict]:
    return {n: load_profile(n) for n in list_profiles()}

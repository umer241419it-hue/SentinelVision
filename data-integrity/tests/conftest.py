"""
Shared fixtures for the data-integrity test suite.

Synthetic embedding fixtures are pure numpy (fast, controlled). Dataset-level
tests reuse the real self-poisoned dataset generator (deterministic, seeded).
"""

import json
import os
import sys

import numpy as np
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_INTEGRITY_ROOT = os.path.dirname(HERE)
PROJECT_ROOT = os.path.dirname(DATA_INTEGRITY_ROOT)

for _p in (DATA_INTEGRITY_ROOT, PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture(scope="session")
def poisoned_dataset(tmp_path_factory):
    """Generate the deterministic self-poisoned dataset once per session."""
    if os.path.isdir(os.path.join(PROJECT_ROOT, "data", "integrity-test", "label_key.json")):
        data_dir = os.path.join(PROJECT_ROOT, "data", "integrity-test")
    else:
        import subprocess

        data_dir = os.path.join(PROJECT_ROOT, "data", "integrity-test")
        subprocess.run(
            [sys.executable, os.path.join(PROJECT_ROOT, "scripts", "make_data_integrity_dataset.py")],
            check=True, cwd=PROJECT_ROOT,
        )
    with open(os.path.join(data_dir, "label_key.json"), "r", encoding="utf-8") as f:
        key = json.load(f)
    return {"dir": data_dir, "key": key}


@pytest.fixture(scope="session")
def integrity_config():
    with open(os.path.join(DATA_INTEGRITY_ROOT, "config.json"), "r", encoding="utf-8") as f:
        return json.load(f)

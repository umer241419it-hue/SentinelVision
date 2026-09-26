"""
SentinelVision - Drift Monitoring package.

Bootstraps sys.path so that both the sibling `shared/` package and this
package are importable regardless of whether the module is executed as a
script (python -m src.reference_builder) or imported from the test suite.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
DRIFT_MONITOR_ROOT = os.path.dirname(_HERE)          # .../drift-monitor
PROJECT_ROOT = os.path.dirname(DRIFT_MONITOR_ROOT)   # .../SentinelVision-Malad


def ensure_shared_importable() -> None:
    """Make `shared/` (project root) and this package importable."""
    for _p in (DRIFT_MONITOR_ROOT, PROJECT_ROOT):
        if _p not in sys.path:
            sys.path.insert(0, _p)


ensure_shared_importable()

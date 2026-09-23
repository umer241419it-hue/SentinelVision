"""
SentinelVision - Data Integrity package.

Bootstraps sys.path so that the sibling `shared/` embedding package and this
package are importable whether modules are executed as scripts
(python -m src.duplicate_detector) or imported from the test suite.

The Data Integrity module reuses the SINGLE shared embedding pipeline at
shared/embeddings/embedding_extractor.py - the exact same representation the
Drift Monitor uses. No separate embedding implementation exists or may be
created (Stage 6 architecture requirement).
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
DATA_INTEGRITY_ROOT = os.path.dirname(_HERE)          # .../data-integrity
PROJECT_ROOT = os.path.dirname(DATA_INTEGRITY_ROOT)   # .../SentinelVision-Malad


def ensure_shared_importable() -> None:
    """Make `shared/` (project root) and this package importable."""
    for _p in (DATA_INTEGRITY_ROOT, PROJECT_ROOT):
        if _p not in sys.path:
            sys.path.insert(0, _p)


ensure_shared_importable()

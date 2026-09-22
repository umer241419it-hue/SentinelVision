"""
Deterministic canonical JSON serialization utility.
Ensures identical serialization across all sign and verify calls in SentinelVision.
"""
import json
from typing import Any, Dict


def canonical_json(obj: Dict[str, Any]) -> str:
    """
    Serialize a dict with sorted keys and minimal separators (',', ':'),
    eliminating whitespace variance across callers and platforms.
    """
    if not isinstance(obj, dict):
        raise TypeError(f"canonical_json requires a dict, got {type(obj).__name__}")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))

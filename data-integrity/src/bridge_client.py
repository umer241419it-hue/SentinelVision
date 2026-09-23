"""
SentinelVision - Data Integrity bridge client.

Submits findings to the EXISTING Stage 3 bridge (POST /findings) and verifies
the Fabric commit by reading the finding back via GET /findings/:assetID.
No new endpoint is created; stdlib urllib only.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict


def submit_finding(finding: Dict[str, Any], bridge_url: str, timeout: int = 20) -> Dict[str, Any]:
    """POST the finding, then GET it back; returns a submission report."""
    post_url = bridge_url.rstrip("/") + "/findings"
    data = json.dumps(finding).encode("utf-8")
    req = urllib.request.Request(
        post_url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return {
            "submitted": False,
            "http_status": exc.code,
            "error": exc.read().decode("utf-8", "replace"),
        }
    except urllib.error.URLError as exc:
        return {"submitted": False, "http_status": None, "error": str(exc.reason)}

    verification = None
    try:
        get_url = (
            bridge_url.rstrip("/")
            + "/findings/"
            + urllib.parse.quote(finding["assetID"], safe="")
        )
        with urllib.request.urlopen(
            urllib.request.Request(get_url, method="GET"), timeout=timeout
        ) as resp:
            verification = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        verification = {"verified": False, "error": str(getattr(exc, "reason", exc))}

    return {
        "submitted": status == 201,
        "http_status": status,
        "bridge_response": body,
        "ledger_verification": verification,
    }

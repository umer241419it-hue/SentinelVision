#!/usr/bin/env python3
"""
SentinelVision - DEMO-ONLY bridge contract stub.

This is NOT part of the drift-monitor module and NEVER used in production.
It exists so the drift-side HTTP flow (finding -> POST /findings -> 201 ->
GET /findings/:id) can be demonstrated offline when the Fabric test network
is not running. It mirrors the real bridge's validation rules exactly
(bridge/src/index.js validateFindingPayload) and stores findings in memory.

Start it, then run the drift monitor with:
    python -m src.run_drift_monitor --config config.json \
        --input ../data/scenario1-normal --submit --bridge-url http://localhost:3001

Usage:
    python scripts/bridge_stub_demo.py [port]
"""

import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FINDINGS = {}
LOCK = threading.Lock()
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def validate(body):
    """Exactly the real bridge's validation contract."""
    if not isinstance(body, dict) or isinstance(body, list):
        return (400, "Request body must be a valid JSON object")
    for field in ("assetID", "moduleName", "reason", "evidenceHash",
                  "confidence", "severity", "disposition", "timestamp"):
        if body.get(field) in (None, ""):
            return (400, f"Missing or empty required field: '{field}'")
    try:
        conf = float(body["confidence"])
    except (TypeError, ValueError):
        return (400, f"Field 'confidence' must be numeric (got {body['confidence']!r})")
    if conf < 0 or conf > 1:
        return (400, "Field 'confidence' must be between 0.0 and 1.0")
    return None


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path.rstrip("/") != "/findings":
            return self._send(404, {"success": False, "error": "Not Found"})
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"success": False, "error": "Invalid JSON"})
        error = validate(body)
        if error:
            return self._send(error[0], {"success": False, "error": "Validation Error",
                                         "details": error[1]})
        with LOCK:
            FINDINGS[body["assetID"]] = body
        print(f"[STUB-LEDGER] committed {body['assetID']} "
              f"(module={body['moduleName']}, disposition={body['disposition']})")
        self._send(201, {"success": True,
                         "message": "Finding successfully committed to (stub) ledger",
                         "data": body})

    def do_GET(self):
        m = re.match(r"^/findings/([^/]+)$", self.path)
        if not m:
            return self._send(404, {"success": False, "error": "Not Found"})
        asset_id = m.group(1)
        with LOCK:
            finding = FINDINGS.get(asset_id)
        if finding is None:
            return self._send(404, {"success": False, "error": "Not Found",
                                    "details": f"Finding with ID '{asset_id}' does not exist"})
        self._send(200, {"success": True, "data": finding})

    def log_message(self, *args):  # quiet
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3001
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[STUB-LEDGER] bridge contract stub listening on http://127.0.0.1:{port}")
    server.serve_forever()

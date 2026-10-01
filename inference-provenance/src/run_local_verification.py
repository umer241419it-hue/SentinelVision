#!/usr/bin/env python3
"""Verify existing SentinelVision inference seals from the local evidence store."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "crypto-utils"))
sys.path.insert(0, str(ROOT / "inference-provenance" / "src"))
from verify_seal import verify_seal

STORE = ROOT / "inference-provenance" / "evidence_store"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-id", default=None)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()

    records = []
    if STORE.exists():
        for p in sorted(STORE.glob("*.json")):
            try:
                record = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if args.model_id and str(record.get("modelAssetID", "")) not in {args.model_id, "model-" + args.model_id}:
                continue
            result = verify_seal(record)
            records.append({
                "evidenceHash": p.stem,
                "sealID": record.get("sealID"),
                "modelAssetID": record.get("modelAssetID"),
                "timestamp": record.get("timestamp"),
                **result,
            })

    valid = [r for r in records if r.get("verdict") == "VALID"]
    invalid = [r for r in records if r.get("verdict") != "VALID"]
    output = {
        "status": "COMPLETED" if records else "NO_RECORDS",
        "records_checked": len(records),
        "valid_records": len(valid),
        "invalid_records": len(invalid),
        "model_id": args.model_id,
        "records": records,
    }
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))
    raise SystemExit(0 if records and not invalid else (2 if records else 3))

if __name__ == "__main__":
    main()

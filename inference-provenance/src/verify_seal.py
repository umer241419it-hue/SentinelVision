"""
SentinelVision - Stage 5 Part A: Inference Provenance Seal Verification
Verifies sealed inference records by separating signed fields,
recomputing contentHash independently, and verifying the Ed25519 signature
using crypto-utils/verify.py.
"""
import hashlib
from pathlib import Path
import sys
from typing import Any, Dict

# Ensure crypto-utils is discoverable
_crypto_dir = Path(__file__).resolve().parent.parent.parent / "crypto-utils"
if str(_crypto_dir) not in sys.path:
    sys.path.insert(0, str(_crypto_dir))

try:
    from canonical import canonical_json
    from verify import verify_fields
except ImportError:
    from crypto_utils.canonical import canonical_json
    from crypto_utils.verify import verify_fields

# The exact 9 signed fields defined by the Stage 5 inference provenance specification
SIGNED_FIELD_KEYS = [
    "sealID",
    "modelAssetID",
    "inputHash",
    "modelDigest",
    "config",
    "nonce",
    "timestamp",
    "outputSummary",
    "signerModule",
]


def verify_seal(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Takes a sealed record (the 11-field dict produced by sealed_predict()).
    Separates the 9 signed fields from contentHash/signature.
    Recomputes contentHash independently and compares to the stored one
    (catches hash mismatch even before signature check).
    Calls crypto-utils verify_fields() with module "InferenceProvenance"
    on the 9 fields + signature.
    Returns {"contentHashMatches": bool, "signatureValid": bool, "verdict": "VALID" | "TAMPERED"}.
    """
    if not isinstance(record, dict):
        return {
            "contentHashMatches": False,
            "signatureValid": False,
            "verdict": "TAMPERED",
            "error": f"Record must be a dict, received {type(record).__name__}",
        }

    stored_content_hash = record.get("contentHash")
    stored_signature = record.get("signature")

    if not stored_content_hash or not stored_signature:
        return {
            "contentHashMatches": False,
            "signatureValid": False,
            "verdict": "TAMPERED",
            "error": "Missing 'contentHash' or 'signature' in record",
        }

    # Extract exactly the 9 signed fields
    signed_fields = {}
    missing_keys = []
    for key in SIGNED_FIELD_KEYS:
        if key in record:
            signed_fields[key] = record[key]
        else:
            missing_keys.append(key)

    if missing_keys:
        return {
            "contentHashMatches": False,
            "signatureValid": False,
            "verdict": "TAMPERED",
            "error": f"Missing required signed field(s): {missing_keys}",
        }

    # 1. Recompute contentHash independently
    canonical_str = canonical_json(signed_fields)
    computed_content_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
    content_hash_matches = (computed_content_hash == stored_content_hash)

    # 2. Call crypto-utils verify_fields() with module "InferenceProvenance"
    signer_module = signed_fields.get("signerModule", "InferenceProvenance")
    signature_valid = verify_fields(
        module_name=signer_module,
        fields=signed_fields,
        signature=stored_signature,
    )

    # 3. Formulate final verdict
    verdict = "VALID" if (content_hash_matches and signature_valid) else "TAMPERED"

    return {
        "contentHashMatches": content_hash_matches,
        "signatureValid": signature_valid,
        "verdict": verdict,
    }

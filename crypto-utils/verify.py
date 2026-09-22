"""
Ed25519 Verification Utility for SentinelVision.
Recomputes content hash directly from raw field dictionary and verifies
signature against the module's registered public key.
Does NOT accept pre-supplied hashes.
"""
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional, Union
import nacl.signing
import nacl.exceptions

try:
    from .canonical import canonical_json
except (ImportError, ValueError):
    from canonical import canonical_json

REGISTRY_PATH = Path(__file__).resolve().parent / "public_key_registry.json"


def load_public_key(module_name: str, registry_path: Optional[Path] = None) -> nacl.signing.VerifyKey:
    """
    Look up the hex-encoded Ed25519 public key for module_name in the registry.
    """
    if registry_path is None:
        registry_path = REGISTRY_PATH
    else:
        registry_path = Path(registry_path)

    if not registry_path.exists():
        raise FileNotFoundError(f"Public key registry not found at: {registry_path}")

    with open(registry_path, "r", encoding="utf-8") as f:
        registry = json.load(f)

    if module_name not in registry:
        raise KeyError(
            f"Module '{module_name}' not found in public key registry ({registry_path}). "
            f"Registered modules: {list(registry.keys())}"
        )

    pub_hex = registry[module_name]
    pub_bytes = bytes.fromhex(pub_hex)
    return nacl.signing.VerifyKey(pub_bytes)


def ed25519_verify(verify_key: nacl.signing.VerifyKey, content_hash: bytes, signature_bytes: bytes) -> bool:
    """
    Verify Ed25519 signature over content_hash.
    Returns True if valid, False otherwise.
    """
    try:
        verify_key.verify(content_hash, signature_bytes)
        return True
    except (nacl.exceptions.BadSignatureError, Exception):
        return False


def verify_fields(
    module_name: str,
    fields: Dict[str, Any],
    signature: Union[str, bytes],
    registry_path: Optional[Path] = None,
) -> bool:
    """
    Recompute content_hash from raw field data, lookup module's public key from registry,
    and return True/False from ed25519_verify.
    CRITICAL: This function does NOT accept a pre-supplied hash from the caller.
    """
    # 1. Recompute content_hash from raw fields
    canonical_str = canonical_json(fields)
    content_hash = hashlib.sha256(canonical_str.encode("utf-8")).digest()

    # 2. Decode signature
    if isinstance(signature, str):
        try:
            signature_bytes = bytes.fromhex(signature.strip())
        except ValueError:
            return False
    elif isinstance(signature, (bytes, bytearray)):
        signature_bytes = bytes(signature)
    else:
        return False

    if len(signature_bytes) != 64:
        return False

    # 3. Lookup public key from registry
    try:
        verify_key = load_public_key(module_name, registry_path)
    except Exception:
        return False

    # 4. Verify signature over content_hash
    return ed25519_verify(verify_key, content_hash, signature_bytes)

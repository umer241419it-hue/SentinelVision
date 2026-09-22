"""
Ed25519 Signing Utility for SentinelVision.
Signs canonical JSON payload hashes using module private keys.
"""
import hashlib
import os
from pathlib import Path
from typing import Any, Dict, Optional
import nacl.signing
import nacl.encoding

try:
    from .canonical import canonical_json
except (ImportError, ValueError):
    from canonical import canonical_json

DEFAULT_KEY_DIR = Path(__file__).resolve().parent / "keys"


def find_private_key_path(module_name: str, key_dir: Optional[Path] = None) -> Path:
    """
    Locate the private key for a given module identity.
    Checks environment variable, specified key_dir, and default locations.
    """
    env_var = f"{module_name.upper().replace('-', '_')}_PRIVATE_KEY_PATH"
    if os.environ.get(env_var):
        return Path(os.environ[env_var])

    search_dirs = []
    if key_dir is not None:
        search_dirs.append(Path(key_dir))
    search_dirs.append(DEFAULT_KEY_DIR)
    search_dirs.append(Path(__file__).resolve().parent.parent / "crypto-utils" / "keys")

    for d in search_dirs:
        for ext in [".priv", ".key"]:
            candidate = d / f"{module_name}{ext}"
            if candidate.exists():
                return candidate

    raise FileNotFoundError(
        f"Private key for module '{module_name}' not found. "
        f"Searched in: {[str(d) for d in search_dirs]}. "
        f"Run keygen.py first to generate keys for '{module_name}'."
    )


def load_signing_key(key_path: Path) -> nacl.signing.SigningKey:
    """Load an Ed25519 SigningKey from a file containing hex or raw bytes."""
    with open(key_path, "rb") as f:
        raw = f.read().strip()

    if len(raw) == 64:
        try:
            seed = bytes.fromhex(raw.decode("utf-8"))
            return nacl.signing.SigningKey(seed)
        except Exception:
            pass

    if len(raw) == 32:
        return nacl.signing.SigningKey(raw)

    try:
        text = raw.decode("utf-8").strip()
        seed = bytes.fromhex(text)
        return nacl.signing.SigningKey(seed)
    except Exception as e:
        raise ValueError(f"Could not parse valid Ed25519 private key seed from {key_path}: {e}")


def ed25519_sign(private_key: nacl.signing.SigningKey, content_hash: bytes) -> bytes:
    """
    Sign a 32-byte content hash using Ed25519 private key.
    Returns 64-byte signature.
    """
    signed = private_key.sign(content_hash)
    return signed.signature


def sign_fields(module_name: str, fields: Dict[str, Any], key_path: Optional[Path] = None) -> str:
    """
    1. Computes content_hash = sha256(canonical_json(fields)).digest()
    2. Loads module private key from local file (never hardcoded)
    3. Computes signature = ed25519_sign(private_key, content_hash)
    4. Returns signature as a 128-character hex string.
    """
    canonical_str = canonical_json(fields)
    content_hash = hashlib.sha256(canonical_str.encode("utf-8")).digest()

    if key_path is None:
        key_path = find_private_key_path(module_name)
    else:
        key_path = Path(key_path)

    signing_key = load_signing_key(key_path)
    sig_bytes = ed25519_sign(signing_key, content_hash)
    return sig_bytes.hex()

"""
SentinelVision Shared Ed25519 Cryptographic Foundation.
"""
try:
    from .canonical import canonical_json
    from .keygen import generate_keypair
    from .sign import sign_fields, ed25519_sign
    from .verify import verify_fields, ed25519_verify
except (ImportError, ValueError):
    from canonical import canonical_json
    from keygen import generate_keypair
    from sign import sign_fields, ed25519_sign
    from verify import verify_fields, ed25519_verify

__all__ = [
    "canonical_json",
    "generate_keypair",
    "sign_fields",
    "ed25519_sign",
    "verify_fields",
    "ed25519_verify",
]

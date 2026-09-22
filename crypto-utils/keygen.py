"""
Ed25519 Key Generation Utility for SentinelVision.
Generates Ed25519 keypairs for named module identities using PyNaCl.
Writes private keys to a local file OUTSIDE version control (.gitignore),
and registers public keys in public_key_registry.json.
"""
import argparse
import json
import os
from pathlib import Path
from typing import Optional, Tuple
import nacl.signing
import nacl.encoding

DEFAULT_KEY_DIR = Path(__file__).resolve().parent / "keys"
REGISTRY_PATH = Path(__file__).resolve().parent / "public_key_registry.json"


def generate_keypair(
    module_name: str,
    key_dir: Optional[Path] = None,
    registry_path: Optional[Path] = None,
) -> Tuple[Path, str]:
    """
    Generates an Ed25519 keypair for module_name.
    Saves private key hex to key_dir / f"{module_name}.priv".
    Registers public key hex in public_key_registry.json.
    Returns (private_key_path, public_key_hex).
    """
    if key_dir is None:
        key_dir = DEFAULT_KEY_DIR
    if registry_path is None:
        registry_path = REGISTRY_PATH

    key_dir = Path(key_dir)
    registry_path = Path(registry_path)

    key_dir.mkdir(parents=True, exist_ok=True)
    private_key_path = key_dir / f"{module_name}.priv"

    # Generate 32-byte Ed25519 signing key
    signing_key = nacl.signing.SigningKey.generate()
    private_key_hex = signing_key.encode(encoder=nacl.encoding.HexEncoder).decode("utf-8")

    with open(private_key_path, "w", encoding="utf-8") as f:
        f.write(private_key_hex.strip() + "\n")
    try:
        os.chmod(private_key_path, 0o600)
    except Exception:
        pass

    # Extract 32-byte public key in hex (64 hex characters)
    verify_key = signing_key.verify_key
    public_key_hex = verify_key.encode(encoder=nacl.encoding.HexEncoder).decode("utf-8")

    # Update public key registry
    registry = {}
    if registry_path.exists():
        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                registry = json.load(f)
        except Exception:
            registry = {}

    registry[module_name] = public_key_hex

    # Save sorted public key registry
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, sort_keys=True)
        f.write("\n")

    return private_key_path, public_key_hex


def main():
    parser = argparse.ArgumentParser(description="Generate Ed25519 keypairs for SentinelVision modules.")
    parser.add_argument("identities", nargs="*", default=["ModelIntegrity", "InferenceProvenance"],
                        help="Module identities to generate keypairs for.")
    parser.add_argument("--key-dir", type=Path, default=DEFAULT_KEY_DIR,
                        help="Directory to store private keys (git-ignored).")
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH,
                        help="Path to public key registry JSON.")
    args = parser.parse_args()

    for identity in args.identities:
        priv_path, pub_hex = generate_keypair(identity, args.key_dir, args.registry)
        print(f"[{identity}] Private key: {priv_path}")
        print(f"[{identity}] Public key:  {pub_hex}")
    print(f"Public key registry updated at: {args.registry}")


if __name__ == "__main__":
    main()

"""
Smoke test for SentinelVision crypto-utils Ed25519 foundation.
Requirements:
a) generates the two keypairs ("ModelIntegrity", "InferenceProvenance")
b) signs a sample dict {"test": "value", "n": 1} as "ModelIntegrity"
c) verifies it ? must print True
d) mutates the dict (change "n" to 2) and verifies the ORIGINAL signature against the MUTATED dict ? must print False
"""
import sys
from pathlib import Path

crypto_dir = Path(__file__).resolve().parent
if str(crypto_dir) not in sys.path:
    sys.path.insert(0, str(crypto_dir))

import keygen
import sign
import verify

# a) generates the two keypairs
keygen.generate_keypair("ModelIntegrity")
keygen.generate_keypair("InferenceProvenance")

# b) signs a sample dict {"test": "value", "n": 1} as "ModelIntegrity"
data = {"test": "value", "n": 1}
signature = sign.sign_fields("ModelIntegrity", data)

# c) verifies it ? must print True
valid = verify.verify_fields("ModelIntegrity", data, signature)
print(valid)

# d) mutates the dict (change "n" to 2) and verifies the ORIGINAL signature against the MUTATED dict ? must print False
data_mutated = {"test": "value", "n": 2}
invalid = verify.verify_fields("ModelIntegrity", data_mutated, signature)
print(invalid)

"""
SentinelVision - Stage 5 Part A: Inference Provenance Wrapper
Implements sealed_predict() to execute model inference unmodified,
build a cryptographic seal containing input, model, config, and output digests,
and sign the record with the InferenceProvenance Ed25519 identity.
"""

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import secrets
import sys
from typing import Any, Dict, Optional, Tuple
import uuid
import numpy as np

# Ensure crypto-utils is discoverable
_crypto_dir = Path(__file__).resolve().parent.parent.parent / "crypto-utils"
if str(_crypto_dir) not in sys.path:
    sys.path.insert(0, str(_crypto_dir))

try:
    from canonical import canonical_json
    from sign import sign_fields
except ImportError:
    from crypto_utils.canonical import canonical_json
    from crypto_utils.sign import sign_fields


def _detect_device(model: Any, input_tensor: Any) -> str:
    """
    Live detection of the device where inference is executing.
    Checks model parameters, then input_tensor, then live torch backend.
    Never assumes or hardcodes.
    """
    # 1. Model parameters
    if hasattr(model, "parameters"):
        try:
            param = next(model.parameters())
            if hasattr(param, "device"):
                return str(param.device)
        except (StopIteration, Exception):
            pass

    # 2. Input tensor
    if hasattr(input_tensor, "device"):
        return str(input_tensor.device)

    # 3. Live PyTorch backend check
    try:
        import torch
        if torch.cuda.is_available():
            idx = torch.cuda.current_device() if torch.cuda.device_count() > 0 else 0
            return f"cuda:{idx}"
        return "cpu"
    except ImportError:
        return "cpu"


def _compute_input_hash(input_tensor: Any) -> str:
    """Compute SHA-256 hex digest of raw input tensor/image bytes."""
    if hasattr(input_tensor, "contiguous") and hasattr(input_tensor, "cpu") and hasattr(input_tensor, "numpy"):
        input_bytes = input_tensor.contiguous().cpu().numpy().tobytes()
    elif isinstance(input_tensor, np.ndarray):
        input_bytes = input_tensor.tobytes()
    elif isinstance(input_tensor, (bytes, bytearray)):
        input_bytes = bytes(input_tensor)
    else:
        input_bytes = str(input_tensor).encode("utf-8")
    return hashlib.sha256(input_bytes).hexdigest()


def _format_output_summary(output: Any, config: Optional[Dict[str, Any]] = None) -> Any:
    """
    Format output summary from model inference results.
    Preserves prediction details (class label, confidence, etc.).
    """
    if isinstance(config, dict) and "post_process" in config and callable(config["post_process"]):
        return config["post_process"](output)

    if hasattr(output, "detach"):
        # PyTorch Tensor
        import torch
        t = output.detach().cpu()
        if t.ndim >= 1 and t.numel() > 1:
            probs = torch.softmax(t.float(), dim=-1)
            pred_class = int(torch.argmax(probs, dim=-1).flatten()[0].item())
            confidence = float(probs.flatten()[pred_class].item())
            return {
                "predicted_class": pred_class,
                "confidence": round(confidence, 4),
                "probabilities": [round(float(p), 4) for p in probs.flatten().tolist()],
            }
        elif t.numel() == 1:
            return {"value": float(t.item())}
        return {"shape": list(t.shape), "mean": float(t.float().mean().item())}

    if isinstance(output, (dict, list, int, float, str)):
        return output

    return str(output)


def sealed_predict(
    model: Any,
    input_tensor: Any,
    model_asset_id: str,
    model_digest: str,
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[Any, Dict[str, Any]]:
    """
    Calls model's real predict()/forward()/__call__ completely unmodified.
    Builds and signs a sealed record. Returns (output, record).

    The sealed record contains:
      - 9 canonical fields: sealID, modelAssetID, inputHash, modelDigest, config,
        nonce, timestamp, outputSummary, signerModule.
      - contentHash: SHA-256 hex of the canonical JSON of the 9 fields.
      - signature: Ed25519 signature over contentHash by InferenceProvenance module.
    Total: 11 fields.
    """
    # 1. Execute model completely unmodified
    if hasattr(model, "predict") and callable(model.predict):
        raw_output = model.predict(input_tensor)
    elif callable(model):
        raw_output = model(input_tensor)
    elif hasattr(model, "forward") and callable(model.forward):
        raw_output = model.forward(input_tensor)
    else:
        raise TypeError(
            f"Model object of type {type(model).__name__} is not callable and has no predict/forward method."
        )

    # 2. Extract input bytes hash
    input_hash = _compute_input_hash(input_tensor)

    # 3. Post-process outputSummary BEFORE hashing
    output_summary = _format_output_summary(raw_output, config)

    # 4. Construct the 9 canonical fields with live device detection
    config_dict = dict(config) if config is not None else {}
    config_dict["device"] = _detect_device(model, input_tensor)

    fields_to_sign = {
        "sealID": f"seal-{uuid.uuid4()}",
        "modelAssetID": str(model_asset_id),
        "inputHash": input_hash,
        "modelDigest": str(model_digest),
        "config": config_dict,
        "nonce": secrets.token_hex(16),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "outputSummary": output_summary,
        "signerModule": "InferenceProvenance",
    }

    # 5. Canonicalize and hash the 9 fields
    canonical_str = canonical_json(fields_to_sign)
    content_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    # 6. Sign via crypto-utils with module identity "InferenceProvenance"
    signature_hex = sign_fields("InferenceProvenance", fields_to_sign)

    # 7. Assemble the final 11-field sealed record
    sealed_record = dict(fields_to_sign)
    sealed_record["contentHash"] = content_hash
    sealed_record["signature"] = signature_hex

    return raw_output, sealed_record

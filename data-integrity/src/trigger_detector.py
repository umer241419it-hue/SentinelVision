#!/usr/bin/env python3
"""
SentinelVision - Training-Data Trigger Injection Detector
==========================================================

Detects backdoor trigger patterns planted directly into training images.

Detection Principles:
  1. Spatial Consistency & Patch Recurrence: Backdoor triggers stamped onto diverse
     images produce an unnaturally identical localized pattern across different scenes.
  2. Residual Pattern Cross-Correlation: Subtracting low-frequency scene content
     (via median blur) reveals high-frequency trigger residuals. Pairwise cross-correlation
     of these residuals within a class isolates recurring trigger patches.
  3. Class-Specific Concentration: An authentic environmental object appears across
     multiple classes, while a backdoor trigger is concentrated in a specific target class.

Supported Trigger Assumptions:
  - Patch-style triggers (solid colors, checkerboards, symbols, watermarks)
  - Spatially consistent or semi-consistent locations (corners, borders, center)
  - Minimum trigger size ratio >= 2% of image dimension
  - Minimum poison concentration >= 1% within the target class

Explicit Limitations:
  - Does not guarantee detection of imperceptible whole-image adversarial perturbations (e.g. L-inf bounded clean-label attacks).
  - Dynamic, wandering, or randomly deformed physical triggers require multi-scale spatial search.
"""

import os
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from PIL import Image, ImageFilter


try:
    import torch
    TORCH_CUDA_AVAILABLE = torch.cuda.is_available()
except ImportError:
    TORCH_CUDA_AVAILABLE = False


class TriggerDetectionError(ValueError):
    """Raised when trigger detection inputs are invalid."""


def extract_corner_patches(
    image: Image.Image,
    patch_size: Tuple[int, int] = (32, 32),
    regions: Optional[List[str]] = None,
) -> Dict[str, np.ndarray]:
    """
    Extracts normalized candidate regions from an image:
    top_left, top_right, bottom_left, bottom_right, center.
    Returns RGB float32 arrays in [0, 1] scaled to patch_size.
    """
    regions = regions or ["bottom_right", "bottom_left", "top_right", "top_left", "center"]
    w, h = image.size
    pw, ph = patch_size

    # Window size in original image: 15% of min dimension
    span = max(16, int(min(w, h) * 0.15))

    coords = {
        "top_left": (0, 0, span, span),
        "top_right": (w - span, 0, w, span),
        "bottom_left": (0, h - span, span, h),
        "bottom_right": (w - span, h - span, w, h),
        "center": (w // 2 - span // 2, h // 2 - span // 2, w // 2 + span // 2, h // 2 + span // 2),
    }

    patches = {}
    for r in regions:
        if r not in coords:
            continue
        box = coords[r]
        cropped = image.crop(box).resize(patch_size, Image.BILINEAR)
        arr = (np.asarray(cropped, dtype=np.float32) / 255.0).astype(np.float32)
        patches[r] = arr

    return patches


def compute_patch_residual(patch: np.ndarray) -> np.ndarray:
    """
    High-pass residual: subtracts low-frequency local background
    to emphasize edges, texture, and trigger pattern.
    """
    # Simple 3x3 local mean subtraction per channel
    res = np.zeros_like(patch)
    for c in range(patch.shape[2]):
        channel = patch[:, :, c]
        # Pad and compute 3x3 mean
        padded = np.pad(channel, 1, mode="edge")
        local_mean = (
            padded[:-2, :-2] + padded[:-2, 1:-1] + padded[:-2, 2:] +
            padded[1:-1, :-2] + padded[1:-1, 1:-1] + padded[1:-1, 2:] +
            padded[2:, :-2] + padded[2:, 1:-1] + padded[2:, 2:]
        ) / 9.0
        res[:, :, c] = channel - local_mean
    return res


def normalized_cross_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Computes normalized cross-correlation between two 3D patch arrays."""
    a_flat = a.flatten()
    b_flat = b.flatten()
    a_centered = a_flat - np.mean(a_flat)
    b_centered = b_flat - np.mean(b_flat)
    norm_a = np.linalg.norm(a_centered)
    norm_b = np.linalg.norm(b_centered)
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return float(np.dot(a_centered, b_centered) / (norm_a * norm_b))


def _cpu_pairwise_correlation(patches: List[np.ndarray], residuals: List[np.ndarray]) -> np.ndarray:
    n = len(patches)
    if n <= 1:
        return np.ones((n, n), dtype=np.float64)
    p_flat = np.stack([p.reshape(-1) for p in patches])
    r_flat = np.stack([r.reshape(-1) for r in residuals])
    p_c = p_flat - p_flat.mean(axis=1, keepdims=True)
    p_u = p_c / np.maximum(1e-9, np.linalg.norm(p_c, axis=1, keepdims=True))
    r_c = r_flat - r_flat.mean(axis=1, keepdims=True)
    r_u = r_c / np.maximum(1e-9, np.linalg.norm(r_c, axis=1, keepdims=True))
    return np.maximum(p_u @ p_u.T, r_u @ r_u.T)


def detect_triggers_in_dataset(
    images_by_class: Dict[str, List[Image.Image]],
    image_ids_by_class: Dict[str, List[str]],
    regions: Optional[List[str]] = None,
    correlation_threshold: float = 0.82,
    min_cluster_size: int = 3,
) -> Dict[str, Any]:
    """
    Scans a labeled image dataset class-by-class for recurrent localized trigger patches
    using GPU (CUDA) tensor acceleration when available.

    Returns:
      flagged_samples: Dict of sample_id -> finding details
      class_summaries: Dict of class -> trigger assessment
      detected_triggers: List of reconstructed trigger signatures
    """
    regions = regions or ["bottom_right", "bottom_left", "top_right", "top_left", "center"]
    flagged_samples: Dict[str, Dict[str, Any]] = {}
    class_summaries: Dict[str, Any] = {}
    detected_triggers: List[Dict[str, Any]] = []

    for class_name, img_list in images_by_class.items():
        sample_ids = image_ids_by_class.get(class_name, [])
        n_samples = len(img_list)
        if n_samples < min_cluster_size:
            continue

        # Extract patches for each region across all images in class
        region_patches: Dict[str, List[np.ndarray]] = {r: [] for r in regions}
        for img in img_list:
            patches = extract_corner_patches(img, regions=regions)
            for r, p in patches.items():
                region_patches[r].append(p)

        best_class_anom = 0.0
        best_region = None
        best_cluster = []
        best_template = None

        for r in regions:
            patches = region_patches[r]
            # Compute residual representations
            residuals = [compute_patch_residual(p) for p in patches]

            # Pairwise correlation matrix on GPU if available
            n = len(patches)
            if TORCH_CUDA_AVAILABLE and n > 1:
                try:
                    p_flat = torch.as_tensor(np.stack([p.reshape(-1) for p in patches]), device="cuda", dtype=torch.float32)
                    r_flat = torch.as_tensor(np.stack([res.reshape(-1) for res in residuals]), device="cuda", dtype=torch.float32)

                    p_c = p_flat - p_flat.mean(dim=1, keepdim=True)
                    p_u = p_c / torch.norm(p_c, dim=1, keepdim=True).clamp_min(1e-9)

                    r_c = r_flat - r_flat.mean(dim=1, keepdim=True)
                    r_u = r_c / torch.norm(r_c, dim=1, keepdim=True).clamp_min(1e-9)

                    raw_mat = torch.mm(p_u, p_u.t())
                    res_mat = torch.mm(r_u, r_u.t())
                    corr_mat = torch.maximum(raw_mat, res_mat).cpu().numpy().astype(np.float64)
                except Exception:
                    corr_mat = _cpu_pairwise_correlation(patches, residuals)
            else:
                corr_mat = _cpu_pairwise_correlation(patches, residuals)

            # Find largest dense clique exceeding threshold
            high_corr_neighbors = [np.where(corr_mat[i] >= correlation_threshold)[0] for i in range(n)]
            sizes = [len(nbrs) for nbrs in high_corr_neighbors]
            max_idx = int(np.argmax(sizes))
            cluster_indices = high_corr_neighbors[max_idx]

            if len(cluster_indices) >= min_cluster_size:
                cluster_patches = [patches[idx] for idx in cluster_indices]
                template = np.median(cluster_patches, axis=0)
                template_std = float(np.std(template))
                residual_std = float(np.std(compute_patch_residual(template)))

                # Require minimal visual structure: reject flat monochrome backgrounds
                if template_std < 0.02 or residual_std < 0.008:
                    continue

                # Cross-check: does this template appear across OTHER classes?
                # A true backdoor trigger is concentrated in target class, not everywhere.
                other_class_matches = 0
                for other_c, other_imgs in images_by_class.items():
                    if other_c == class_name:
                        continue
                    for o_img in other_imgs[:20]:
                        o_patch = extract_corner_patches(o_img, regions=[r])[r]
                        if normalized_cross_correlation(template, o_patch) >= correlation_threshold:
                            other_class_matches += 1

                # If template appears widely in other classes, it's a watermark or dataset border, not a class-specific backdoor
                class_specificity = 1.0 - min(1.0, other_class_matches / 5.0)
                anomaly_score = (len(cluster_indices) / n) * class_specificity

                if anomaly_score > best_class_anom and len(cluster_indices) >= min_cluster_size:
                    best_class_anom = anomaly_score
                    best_region = r
                    best_cluster = [int(idx) for idx in cluster_indices]
                    best_template = template

        if best_cluster and best_class_anom >= 0.05:
            trigger_id = f"trigger_{class_name}_{best_region}"
            mean_corr = float(np.mean([
                normalized_cross_correlation(best_template, region_patches[best_region][idx])
                for idx in best_cluster
            ]))

            detected_triggers.append({
                "trigger_id": trigger_id,
                "target_class": class_name,
                "location": best_region,
                "affected_sample_count": len(best_cluster),
                "affected_fraction": round(len(best_cluster) / max(1, n_samples), 4),
                "mean_template_correlation": round(mean_corr, 4),
                "anomaly_score": round(best_class_anom, 4),
            })

            class_summaries[class_name] = {
                "status": "SUSPICIOUS_TRIGGER_DETECTED",
                "location": best_region,
                "affected_count": len(best_cluster),
                "total_class_samples": n_samples,
                "mean_correlation": round(mean_corr, 4),
            }

            for idx in best_cluster:
                s_id = sample_ids[idx]
                flagged_samples[s_id] = {
                    "sample_id": s_id,
                    "target_class": class_name,
                    "location": best_region,
                    "correlation_to_trigger": round(
                        float(normalized_cross_correlation(best_template, region_patches[best_region][idx])), 4
                    ),
                    "confidence": round(min(0.95, 0.65 + 0.30 * mean_corr), 2),
                    "severity": "HIGH",
                    "disposition": "REVIEW",
                    "reason": (
                        f"Unusual repeated visual patch detected at {best_region} "
                        f"concentrated in class '{class_name}' (correlation: {mean_corr:.2f}, "
                        f"cluster size: {len(best_cluster)} images)"
                    ),
                }
        else:
            class_summaries[class_name] = {"status": "CLEAN", "affected_count": 0}

    return {
        "flagged_samples": flagged_samples,
        "class_summaries": class_summaries,
        "detected_triggers": detected_triggers,
        "n_flagged": len(flagged_samples),
        "trigger_count": len(detected_triggers),
    }


class TriggerDetector:
    """Class wrapper for training-data trigger detection."""

    def __init__(
        self,
        regions: Optional[List[str]] = None,
        correlation_threshold: float = 0.80,
        min_cluster_size: int = 2,
    ):
        self.regions = regions or ["bottom_right", "bottom_left", "top_right", "top_left", "center"]
        self.correlation_threshold = correlation_threshold
        self.min_cluster_size = min_cluster_size

    def detect_triggers(
        self,
        image_paths: List[str],
        labels: Dict[str, str],
        candidate_classes: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Scan images grouped by label and return flagged candidate records.
        """
        images_by_class: Dict[str, List[Image.Image]] = {}
        image_ids_by_class: Dict[str, List[str]] = {}

        for p in image_paths:
            sid = os.path.splitext(os.path.basename(p))[0]
            cls = labels.get(sid, "unknown")
            if candidate_classes and cls not in candidate_classes:
                continue
            if not os.path.exists(p):
                continue
            try:
                img = Image.open(p).convert("RGB")
            except Exception:
                continue

            if cls not in images_by_class:
                images_by_class[cls] = []
                image_ids_by_class[cls] = []
            images_by_class[cls].append(img)
            image_ids_by_class[cls].append(sid)

        res = detect_triggers_in_dataset(
            images_by_class=images_by_class,
            image_ids_by_class=image_ids_by_class,
            regions=self.regions,
            correlation_threshold=self.correlation_threshold,
            min_cluster_size=self.min_cluster_size,
        )

        return list(res["flagged_samples"].values())

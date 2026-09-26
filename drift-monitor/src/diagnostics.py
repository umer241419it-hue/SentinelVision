#!/usr/bin/env python3
"""
SentinelVision - Phase 6: Operational Drift Diagnostics
=======================================================

MMD alone can never say WHY a distribution shifted (task.md 10.1-10.2).
This module produces evidence-producing diagnostics that compare simple,
measurable image statistics between the reference battery and the live
window, plus metadata changes (camera/source IDs, modality).

For each diagnostic a shift level is reported:
    LOW | MEDIUM | HIGH | NOT_AVAILABLE

and the levels are combined into one of the conservative assessments:

    NO_SIGNIFICANT_SHIFT        MMD within reference variation
    OPERATIONAL_SHIFT_LIKELY    significant MMD + operational factors explain it
    UNEXPLAINED_SHIFT           significant MMD + no operational factor explains it
    INSUFFICIENT_EVIDENCE       nothing measurable is available

An unexplained shift is surfaced for human review; it is NEVER labeled a
confirmed attack (task.md 10.3). Missing metadata never crashes the module:
it degrades to NOT_AVAILABLE.
"""

from typing import Any, Dict, List, Optional

import numpy as np

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover - Pillow is a hard dep of the pipeline
    PIL_AVAILABLE = False

LEVEL_LOW = "LOW"
LEVEL_MEDIUM = "MEDIUM"
LEVEL_HIGH = "HIGH"
LEVEL_NA = "NOT_AVAILABLE"

_LEVEL_RANK = {LEVEL_LOW: 0, LEVEL_MEDIUM: 1, LEVEL_HIGH: 2, LEVEL_NA: -1}

# Relative change in a mean statistic classified as LOW/MEDIUM/HIGH.
REL_MEDIUM = 0.08
REL_HIGH = 0.20

# (No fraction rule: any MEDIUM+ change in a measurable operational factor
# counts toward an operational explanation - see build_assessment.)

ASSESSMENT_NO_SHIFT = "NO_SIGNIFICANT_SHIFT"
ASSESSMENT_OPERATIONAL = "OPERATIONAL_SHIFT_LIKELY"
ASSESSMENT_UNEXPLAINED = "UNEXPLAINED_SHIFT"
ASSESSMENT_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"


def _level_rank(level: str) -> int:
    return _LEVEL_RANK.get(level, -1)


def _classify_rel(x: Optional[float]) -> str:
    if x is None:
        return LEVEL_NA
    if x >= REL_HIGH:
        return LEVEL_HIGH
    if x >= REL_MEDIUM:
        return LEVEL_MEDIUM
    return LEVEL_LOW


def _safe_rel_change(new: Any, old: Any) -> Optional[float]:
    try:
        new_f, old_f = float(new), float(old)
    except (TypeError, ValueError):
        return None
    if abs(old_f) < 1e-12:
        return None
    return abs(new_f - old_f) / abs(old_f)


def _coerce_pil(image: Any):
    """Best-effort coercion of a path / PIL image / RGB array to PIL RGB.

    Returns None on any failure - diagnostics degrade, they never crash.
    """
    if not PIL_AVAILABLE:
        return None
    if isinstance(image, str):
        try:
            with Image.open(image) as im:
                return im.convert("RGB")
        except Exception:
            return None
    if isinstance(image, Image.Image):
        try:
            return image.convert("RGB")
        except Exception:
            return None
    try:
        arr = np.asarray(image)
        if arr.ndim != 3 or arr.shape[2] != 3:
            return None
        if arr.dtype != np.uint8:
            arr = np.clip(arr, 0, 255).astype(np.uint8)
        return Image.fromarray(arr, mode="RGB")
    except Exception:
        return None


def compute_image_stats(images: List[Any]) -> Dict[str, Any]:
    """Aggregate brightness/contrast/color/dimension/edge statistics over a
    set of images. Unloadable images are skipped; if nothing is loadable,
    every statistic is NOT_AVAILABLE instead of raising."""
    brightness: List[float] = []
    contrast: List[float] = []
    means_rgb: List[List[float]] = []
    edge: List[float] = []
    dims: List[List[int]] = []

    for image in images:
        img = _coerce_pil(image)
        if img is None:
            continue
        arr = np.asarray(img, dtype=np.float64) / 255.0
        if arr.ndim != 3 or arr.shape[2] != 3 or arr.shape[0] < 2 or arr.shape[1] < 2:
            continue
        gray = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
        brightness.append(float(gray.mean()))
        contrast.append(float(gray.std()))
        means_rgb.append(
            [float(arr[:, :, 0].mean()), float(arr[:, :, 1].mean()), float(arr[:, :, 2].mean())]
        )
        gy, gx = np.gradient(gray)
        edge.append(float((np.sqrt(gx * gx + gy * gy) > 0.08).mean()))
        dims.append([int(img.width), int(img.height)])

    if not brightness:
        na = {"status": LEVEL_NA, "note": "not_available"}
        return {
            "brightness": dict(na),
            "contrast": dict(na),
            "color": dict(na),
            "edge_density": dict(na),
            "dimensions": dict(na),
            "image_count": 0,
        }

    return {
        "brightness": {
            "status": "ok",
            "mean": float(np.mean(brightness)),
            "std": float(np.std(brightness)),
        },
        "contrast": {
            "status": "ok",
            "mean": float(np.mean(contrast)),
            "std": float(np.std(contrast)),
        },
        "color": {
            "status": "ok",
            "mean": [float(v) for v in np.mean(means_rgb, axis=0)],
            "std": [float(v) for v in np.std(means_rgb, axis=0)],
        },
        "edge_density": {"status": "ok", "mean": float(np.mean(edge))},
        "dimensions": {
            "status": "ok",
            "widths": sorted({d[0] for d in dims}),
            "heights": sorted({d[1] for d in dims}),
        },
        "image_count": len(brightness),
    }


def compare_image_stats(
    ref_stats: Dict[str, Any], live_stats: Dict[str, Any]
) -> Dict[str, Any]:
    """Level (LOW/MEDIUM/HIGH/NOT_AVAILABLE) per diagnostic + details."""
    levels: Dict[str, str] = {}
    details: Dict[str, Any] = {}

    # Scalar means: brightness, contrast, edge density.
    for name in ("brightness", "contrast", "edge_density"):
        r = ref_stats.get(name, {})
        l = live_stats.get(name, {})
        if r.get("status") != "ok" or l.get("status") != "ok":
            levels[name] = LEVEL_NA
            details[name] = {"note": "not_available"}
            continue
        x = _safe_rel_change(l.get("mean"), r.get("mean"))
        levels[name] = _classify_rel(x)
        details[name] = {
            "reference_mean": r.get("mean"),
            "live_mean": l.get("mean"),
            "relative_change": x,
            "level": levels[name],
        }

    # Color: per-channel means; overall level = worst channel.
    r_c = ref_stats.get("color", {})
    l_c = live_stats.get("color", {})
    if r_c.get("status") != "ok" or l_c.get("status") != "ok":
        levels["color"] = LEVEL_NA
        details["color"] = {"note": "not_available"}
    else:
        per_channel: Dict[str, Any] = {}
        worst = LEVEL_LOW
        for i, ch in enumerate(("R", "G", "B")):
            x = _safe_rel_change(l_c["mean"][i], r_c["mean"][i])
            lvl = _classify_rel(x)
            per_channel[ch] = {
                "reference_mean": r_c["mean"][i],
                "live_mean": l_c["mean"][i],
                "relative_change": x,
                "level": lvl,
            }
            if _level_rank(lvl) > _level_rank(worst):
                worst = lvl
        levels["color"] = worst
        details["color"] = {"per_channel": per_channel, "level": worst}

    # Dimensions: compare sorted unique width/height sets.
    r_d = ref_stats.get("dimensions", {})
    l_d = live_stats.get("dimensions", {})
    if r_d.get("status") != "ok" or l_d.get("status") != "ok":
        levels["dimensions"] = LEVEL_NA
        details["dimensions"] = {"note": "not_available"}
    else:
        changed = (r_d.get("widths") != l_d.get("widths")) or (
            r_d.get("heights") != l_d.get("heights")
        )
        levels["dimensions"] = LEVEL_MEDIUM if changed else LEVEL_LOW
        details["dimensions"] = {
            "reference": [r_d.get("widths"), r_d.get("heights")],
            "live": [l_d.get("widths"), l_d.get("heights")],
            "changed": changed,
            "level": levels["dimensions"],
        }

    return {"levels": levels, "details": details}


def compare_metadata(
    ref_meta: Optional[Dict[str, Any]], live_meta: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Compare declared metadata (source/camera IDs, modality) between the
    reference declaration and the live window. Missing data -> NOT_AVAILABLE."""
    ref_meta = ref_meta or {}
    ref_sources = sorted({str(s) for s in (ref_meta.get("source_ids") or [])})
    ref_modalities = sorted({str(s) for s in (ref_meta.get("modalities") or [])})
    live_sources = sorted({str(m.get("source_id")) for m in live_meta if m.get("source_id")})
    live_modalities = sorted({str(m.get("modality")) for m in live_meta if m.get("modality")})

    sources_changed: Optional[bool]
    if not ref_sources and not live_sources:
        sources_changed = None
    else:
        sources_changed = ref_sources != live_sources

    modality_changed: Optional[bool]
    if not ref_modalities and not live_modalities:
        modality_changed = None
    else:
        modality_changed = ref_modalities != live_modalities

    def level(flag: Optional[bool]) -> str:
        if flag is None:
            return LEVEL_NA
        return LEVEL_HIGH if flag else LEVEL_LOW

    return {
        "source_ids": {
            "reference": ref_sources or None,
            "live": live_sources or None,
            "changed": sources_changed,
            "level": level(sources_changed),
        },
        "modality": {
            "reference": ref_modalities or None,
            "live": live_modalities or None,
            "changed": modality_changed,
            "level": level(modality_changed),
        },
    }


def build_assessment(
    mmd_significant: bool,
    image_diagnostics: Dict[str, Any],
    metadata_diagnostics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Combine MMD significance with diagnostic levels into the conservative
    assessment vocabulary (task.md 10.3). A significant MMD with measurable
    operational changes -> OPERATIONAL_SHIFT_LIKELY; with nothing measurable
    -> INSUFFICIENT_EVIDENCE; otherwise UNEXPLAINED_SHIFT (human review)."""
    levels = dict(image_diagnostics.get("levels", {}))
    meta_levels: Dict[str, str] = {}
    if metadata_diagnostics:
        for k, v in metadata_diagnostics.items():
            if isinstance(v, dict):
                meta_levels[k] = v.get("level", LEVEL_NA)

    op_levels = [
        levels.get(k)
        for k in ("brightness", "contrast", "color", "edge_density", "dimensions")
    ]
    op_known = [x for x in op_levels if x is not None and x != LEVEL_NA]
    op_changed = [x for x in op_known if x in (LEVEL_MEDIUM, LEVEL_HIGH)]
    meta_changed = [k for k, v in meta_levels.items() if v == LEVEL_HIGH]
    diagnostics_available = bool(op_known) or any(v != LEVEL_NA for v in meta_levels.values())

    # Policy: a significant MMD combined with ANY materially-changed
    # measurable factor (image statistic at MEDIUM+, or a declared source/
    # camera/modality change) means an operational/environmental explanation
    # is plausible — matching task.md 10.2 ("diagnostics explain part of the
    # change"). If MMD is significant but nothing measurable changed, the
    # shift is unexplained and goes to human review.
    operational_explains = bool(op_changed) or bool(meta_changed)

    if not mmd_significant:
        assessment = ASSESSMENT_NO_SHIFT
    elif not diagnostics_available:
        assessment = ASSESSMENT_INSUFFICIENT
    elif operational_explains:
        assessment = ASSESSMENT_OPERATIONAL
    else:
        assessment = ASSESSMENT_UNEXPLAINED

    return {
        "assessment": assessment,
        "explanation": {
            "operational_factors_measured": len(op_known),
            "operational_factors_changed": op_changed,
            "metadata_changed": meta_changed or None,
            "operational_explains_shift": operational_explains,
        },
    }


def run_diagnostics(
    reference_images: List[Any],
    live_images: List[Any],
    ref_meta: Optional[Dict[str, Any]] = None,
    live_meta: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Convenience orchestrator: stats + comparisons for both sides."""
    ref_stats = compute_image_stats(reference_images)
    live_stats = compute_image_stats(live_images)
    image_diag = compare_image_stats(ref_stats, live_stats)
    meta_diag = compare_metadata(ref_meta, live_meta or [])
    return {
        "reference_stats": ref_stats,
        "live_stats": live_stats,
        "image_diagnostics": image_diag,
        "metadata_diagnostics": meta_diag,
    }

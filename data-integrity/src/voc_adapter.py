#!/usr/bin/env python3
"""
SentinelVision - PASCAL VOC2012 Dataset Adapter & Normalizer
============================================================

Reads and normalizes images, XML annotations, bounding boxes, object attributes,
and splits from the official VOCdevkit/VOC2012 directory structure.

Validates:
  - XML syntax & structure
  - Bounding box geometries (0 <= xmin < xmax <= width, 0 <= ymin < ymax <= height)
  - 20 standard PASCAL VOC classes
  - Image presence & file hashes
"""

import hashlib
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

VOC_CLASSES = [
    "aeroplane", "bicycle", "bird", "boat", "bottle",
    "bus", "car", "cat", "chair", "cow",
    "diningtable", "dog", "horse", "motorbike", "person",
    "pottedplant", "sheep", "sofa", "train", "tvmonitor"
]
VOC_CLASS_SET = set(VOC_CLASSES)


class VOCValidationError(ValueError):
    """Raised when VOC annotations or files fail integrity validation."""


InvalidAnnotationError = VOCValidationError


@dataclass
class VOCObject:
    object_index: int
    class_name: str
    xmin: int
    ymin: int
    xmax: int
    ymax: int
    truncated: bool = False
    occluded: bool = False
    difficult: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_index": self.object_index,
            "class": self.class_name,
            "xmin": self.xmin,
            "ymin": self.ymin,
            "xmax": self.xmax,
            "ymax": self.ymax,
            "truncated": self.truncated,
            "occluded": self.occluded,
            "difficult": self.difficult,
        }


@dataclass
class VOCSample:
    sample_id: str
    dataset_id: str
    original_image_id: str
    image_path: str
    image_sha256: str
    width: int
    height: int
    depth: int
    objects: List[VOCObject]
    split: str
    primary_class: str
    all_classes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "dataset_id": self.dataset_id,
            "original_image_id": self.original_image_id,
            "image_path": self.image_path,
            "image_sha256": self.image_sha256,
            "width": self.width,
            "height": self.height,
            "depth": self.depth,
            "objects": [obj.to_dict() for obj in self.objects],
            "split": self.split,
            "primary_class": self.primary_class,
            "all_classes": self.all_classes,
        }


def compute_file_sha256(filepath: Path) -> str:
    """Computes streaming SHA-256 digest of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def parse_voc_xml(xml_path: Path, expected_image_path: Optional[Path] = None) -> Tuple[int, int, int, List[VOCObject]]:
    """
    Parses a VOC XML annotation file.
    Validates XML syntax, image size, bounding box coordinates, and classes.
    """
    if not xml_path.exists():
        raise VOCValidationError(f"Annotation file not found: {xml_path}")

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except ET.ParseError as e:
        raise VOCValidationError(f"Malformed XML in {xml_path}: {e}")

    # Read size
    size_elem = root.find("size")
    if size_elem is None:
        raise VOCValidationError(f"Missing <size> tag in {xml_path}")

    try:
        width = int(size_elem.findtext("width", "0"))
        height = int(size_elem.findtext("height", "0"))
        depth = int(size_elem.findtext("depth", "3"))
    except ValueError as e:
        raise VOCValidationError(f"Invalid dimensions in {xml_path}: {e}")

    if width <= 0 or height <= 0:
        raise VOCValidationError(f"Invalid dimensions width={width}, height={height} in {xml_path}")

    objects: List[VOCObject] = []
    obj_elems = root.findall("object")
    if not obj_elems:
        raise VOCValidationError(f"Zero objects found in annotation: {xml_path}")

    for idx, obj_elem in enumerate(obj_elems):
        name = obj_elem.findtext("name", "").strip().lower()
        if not name:
            raise VOCValidationError(f"Empty object class name at index {idx} in {xml_path}")
        if name not in VOC_CLASS_SET:
            raise VOCValidationError(f"Unknown class '{name}' in {xml_path}. Expected one of {VOC_CLASSES}")

        bndbox = obj_elem.find("bndbox")
        if bndbox is None:
            raise VOCValidationError(f"Object {idx} missing <bndbox> in {xml_path}")

        try:
            xmin = int(float(bndbox.findtext("xmin", "0")))
            ymin = int(float(bndbox.findtext("ymin", "0")))
            xmax = int(float(bndbox.findtext("xmax", "0")))
            ymax = int(float(bndbox.findtext("ymax", "0")))
        except ValueError as e:
            raise VOCValidationError(f"Non-integer coordinates in {xml_path} object {idx}: {e}")

        # Geometric bounding box sanity checks
        if xmin < 0 or ymin < 0:
            raise VOCValidationError(f"Negative bbox coordinate ({xmin}, {ymin}) in {xml_path} object {idx}")
        if xmax <= xmin or ymax <= ymin:
            raise VOCValidationError(
                f"Degenerate bbox [{xmin}, {ymin}, {xmax}, {ymax}] in {xml_path} object {idx}"
            )
        # Note: VOC bounding boxes are 1-based and can reach width/height
        if xmax > width + 2 or ymax > height + 2:
            # 2px tolerance for historical VOC off-by-one labels
            raise VOCValidationError(
                f"Bbox [{xmin}, {ymin}, {xmax}, {ymax}] exceeds image boundaries ({width}x{height}) in {xml_path}"
            )

        truncated = (obj_elem.findtext("truncated", "0") in ("1", "true", "True"))
        occluded = (obj_elem.findtext("occluded", "0") in ("1", "true", "True"))
        difficult = (obj_elem.findtext("difficult", "0") in ("1", "true", "True"))

        objects.append(
            VOCObject(
                object_index=idx,
                class_name=name,
                xmin=xmin,
                ymin=ymin,
                xmax=xmax,
                ymax=ymax,
                truncated=truncated,
                occluded=occluded,
                difficult=difficult,
            )
        )

    return width, height, depth, objects


class VOC2012Adapter:
    """Adapter for PASCAL VOC2012 dataset."""

    def __init__(self, voc_root: Path):
        self.voc_root = Path(voc_root)
        if not (self.voc_root / "JPEGImages").exists():
            if (self.voc_root / "VOCdevkit" / "VOC2012").exists():
                self.voc_root = self.voc_root / "VOCdevkit" / "VOC2012"
            elif (self.voc_root / "VOC2012").exists():
                self.voc_root = self.voc_root / "VOC2012"

        self.jpeg_dir = self.voc_root / "JPEGImages"
        self.annot_dir = self.voc_root / "Annotations"
        self.sets_dir = self.voc_root / "ImageSets" / "Main"

        if not self.jpeg_dir.exists():
            raise FileNotFoundError(f"JPEGImages not found at {self.jpeg_dir}")
        if not self.annot_dir.exists():
            raise FileNotFoundError(f"Annotations not found at {self.annot_dir}")

        self._splits: Dict[str, List[str]] = self._load_splits() if self.sets_dir.exists() else {}

    def _load_splits(self) -> Dict[str, List[str]]:
        splits = {}
        if not self.sets_dir.exists():
            return splits
        for split_name in ("train", "val", "trainval"):
            split_file = self.sets_dir / f"{split_name}.txt"
            if split_file.exists():
                splits[split_name] = [
                    line.strip() for line in split_file.read_text().splitlines() if line.strip()
                ]
            else:
                splits[split_name] = []
        return splits

    @staticmethod
    def generate_sample_id(image_id: str) -> str:
        return f"voc2012_{image_id}"

    def get_image_ids(self, split: Optional[str] = None) -> List[str]:
        if split and split in self._splits and self._splits[split]:
            return list(self._splits[split])
        # fallback: list all xmls
        return sorted([p.stem for p in self.annot_dir.glob("*.xml")])

    def get_sample(self, image_id: str, split: Optional[str] = None) -> VOCSample:
        """Loads and normalizes a single image sample."""
        img_path = self.jpeg_dir / f"{image_id}.jpg"
        xml_path = self.annot_dir / f"{image_id}.xml"

        if not img_path.exists():
            raise VOCValidationError(f"Image file missing for id {image_id}: {img_path}")
        if not xml_path.exists():
            raise VOCValidationError(f"XML annotation missing for id {image_id}: {xml_path}")

        width, height, depth, objects = parse_voc_xml(xml_path, img_path)
        img_hash = compute_file_sha256(img_path)

        if split is None:
            if image_id in self._splits.get("train", []):
                split = "train"
            elif image_id in self._splits.get("val", []):
                split = "val"
            else:
                split = "trainval"

        # Determine primary class (largest area object by default)
        if objects:
            primary_obj = max(objects, key=lambda o: (o.xmax - o.xmin) * (o.ymax - o.ymin))
            primary_class = primary_obj.class_name
        else:
            primary_class = "background"

        all_classes = sorted(list({obj.class_name for obj in objects}))

        return VOCSample(
            sample_id=f"voc2012_{image_id}",
            dataset_id="VOC2012",
            original_image_id=image_id,
            image_path=str(img_path),
            image_sha256=img_hash,
            width=width,
            height=height,
            depth=depth,
            objects=objects,
            split=split,
            primary_class=primary_class,
            all_classes=all_classes,
        )

    def load_dataset(self, split: str = "trainval", limit: Optional[int] = None) -> List[VOCSample]:
        """Loads all or a subset of normalized samples."""
        ids = self.get_image_ids(split)
        if limit is not None:
            ids = ids[:limit]

        samples = []
        for img_id in ids:
            samples.append(self.get_sample(img_id, split=split))
        return samples

    def compute_statistics(self, samples: Optional[List[VOCSample]] = None) -> Dict[str, Any]:
        """Computes comprehensive dataset statistics across classes, splits, objects."""
        if samples is None:
            samples = self.load_dataset("trainval")

        class_obj_counts = {c: 0 for c in VOC_CLASSES}
        class_img_counts = {c: 0 for c in VOC_CLASSES}
        split_counts: Dict[str, int] = {}
        total_objects = 0
        difficult_count = 0
        truncated_count = 0
        occluded_count = 0

        for s in samples:
            split_counts[s.split] = split_counts.get(s.split, 0) + 1
            seen_in_sample = set()
            for o in s.objects:
                total_objects += 1
                class_obj_counts[o.class_name] = class_obj_counts.get(o.class_name, 0) + 1
                seen_in_sample.add(o.class_name)
                if o.difficult:
                    difficult_count += 1
                if o.truncated:
                    truncated_count += 1
                if o.occluded:
                    occluded_count += 1

            for c in seen_in_sample:
                class_img_counts[c] = class_img_counts.get(c, 0) + 1

        return {
            "image_count": len(samples),
            "object_count": total_objects,
            "split_distribution": split_counts,
            "class_object_distribution": class_obj_counts,
            "class_image_distribution": class_img_counts,
            "difficult_objects": difficult_count,
            "truncated_objects": truncated_count,
            "occluded_objects": occluded_count,
            "mean_objects_per_image": round(total_objects / max(1, len(samples)), 2),
        }

    def generate_manifest(
        self,
        output_path: Path,
        archive_hashes: Optional[Dict[str, str]] = None,
        archive_size: Optional[int] = None,
        benchmark_version: str = "v1.0.0",
    ) -> Dict[str, Any]:
        """
        Generates official, machine-readable dataset manifest recording:
          dataset_id, dataset_name, dataset_version, source_url, download_timestamp,
          archive_hash, dataset_hash, image_count, object_count, class_distribution,
          split_distribution, benchmark_version.
        """
        samples = self.load_dataset("trainval")
        stats = self.compute_statistics(samples)

        # Compute deterministic dataset_hash across sorted (image_id, image_sha256)
        hasher = hashlib.sha256()
        for s in sorted(samples, key=lambda x: x.original_image_id):
            hasher.update(f"{s.original_image_id}:{s.image_sha256}:{len(s.objects)}".encode("utf-8"))
        dataset_hash = hasher.hexdigest()

        manifest = {
            "dataset_id": "VOC2012",
            "dataset_name": "PASCAL Visual Object Classes Challenge 2012 (VOC2012)",
            "dataset_version": "2012",
            "source_url": "https://www.robots.ox.ac.uk/~vgg/projects/pascal/VOC/voc2012/",
            "archive_url": "https://thor.robots.ox.ac.uk/pascal/VOC/voc2012/VOCtrainval_11-May-2012.tar",
            "download_timestamp": datetime.now(timezone.utc).isoformat(),
            "archive_hashes": archive_hashes or {},
            "archive_size": archive_size or 0,
            "dataset_hash": dataset_hash,
            "image_count": stats["image_count"],
            "object_count": stats["object_count"],
            "class_distribution": stats["class_object_distribution"],
            "class_image_distribution": stats["class_image_distribution"],
            "split_distribution": stats["split_distribution"],
            "mean_objects_per_image": stats["mean_objects_per_image"],
            "benchmark_version": benchmark_version,
            "license": "PASCAL VOC Challenge Terms (for research and non-commercial educational use)",
            "classes": VOC_CLASSES,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        return manifest

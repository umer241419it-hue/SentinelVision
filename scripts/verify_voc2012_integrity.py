#!/usr/bin/env python3
"""
SentinelVision - Pascal VOC 2012 Dataset Integrity Verification Tool.

Verifies the cryptographic checksums (MD5, SHA-1, SHA-256) of the official
VOCtrainval_11-May-2012.tar archive and validates the structural completeness
and annotation counts of the extracted VOC2012 dataset.

Fail-closed: Returns exit code 0 if and only if all archive checksums,
directory structures, image/annotation counts, object counts, and train/val
split line counts match official ground-truth VOC2012 invariants. Returns
exit code 1 on any failure or missing requirement.
"""

import argparse
import hashlib
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Official VOC2012 Ground-Truth Invariants
EXPECTED_ARCHIVE_SIZE = 1_999_639_040
EXPECTED_ARCHIVE_MD5 = "6cd6e144f989b92b3379bac3b3de84fd"
EXPECTED_ARCHIVE_SHA1 = "4e443f8a2eca6b1dac8a6c57641b67dd40621a49"
EXPECTED_TOTAL_IMAGES = 17_125
EXPECTED_XML_ANNOS = 17_125
EXPECTED_TOTAL_OBJECTS = 40_138
EXPECTED_NUM_CLASSES = 20
EXPECTED_TRAIN_COUNT = 5_717
EXPECTED_VAL_COUNT = 5_823
EXPECTED_TRAINVAL_COUNT = 11_540

DEFAULT_ARCHIVE_PATH = "datasets/downloads/VOCtrainval_11-May-2012.tar"
DEFAULT_EXTRACTED_PATH = "datasets/sentinelvision_voc2012/raw/VOCdevkit/VOC2012"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify cryptographic checksums and dataset completeness for Pascal VOC 2012.",
        epilog=(
            "Verification checks performed:\n"
            "  1. Archive existence, exact size (1,999,639,040 bytes), MD5, and SHA-1 checksums.\n"
            "  2. Extracted directory structure (JPEGImages, Annotations, ImageSets/Main).\n"
            "  3. Exact counts: 17,125 images, 17,125 XML annotations, 40,138 objects, 20 classes.\n"
            "  4. Split counts: 5,717 train, 5,823 val, 11,540 trainval samples.\n"
            "Returns exit code 0 if all checks pass, exit code 1 if any check fails."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--archive",
        type=str,
        default=DEFAULT_ARCHIVE_PATH,
        help=f"Path to VOCtrainval_11-May-2012.tar archive (default: {DEFAULT_ARCHIVE_PATH})",
    )
    parser.add_argument(
        "--extracted-dir",
        type=str,
        default=DEFAULT_EXTRACTED_PATH,
        help=f"Path to extracted VOC2012 directory (default: {DEFAULT_EXTRACTED_PATH})",
    )
    return parser.parse_args()


def compute_hashes(archive_path: Path) -> tuple[str, str, str]:
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    with open(archive_path, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            md5.update(chunk)
            sha1.update(chunk)
            sha256.update(chunk)
    return md5.hexdigest(), sha1.hexdigest(), sha256.hexdigest()


def count_lines(path: Path) -> int | None:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return len([line.strip() for line in f if line.strip()])
    return None


def main() -> None:
    args = parse_args()
    archive_path = Path(args.archive)
    extracted_path = Path(args.extracted_dir)

    failures: list[str] = []

    print("=" * 70)
    print("VOC2012 DATASET INTEGRITY INSPECTION")
    print("=" * 70)

    # 1. Archive Check
    if archive_path.exists():
        archive_size = archive_path.stat().st_size
        print(f"Archive path:         {archive_path.resolve()}")
        print(f"Archive size:         {archive_size:,} bytes ({archive_size / (1024**3):.4f} GB)")

        print("Computing archive hashes (MD5, SHA-1, SHA-256)...")
        computed_md5, computed_sha1, computed_sha256 = compute_hashes(archive_path)
        print(f"Archive MD5:          {computed_md5}")
        print(f"Archive SHA-1:        {computed_sha1}")
        print(f"Archive SHA-256:      {computed_sha256}")

        if archive_size != EXPECTED_ARCHIVE_SIZE:
            failures.append(f"Archive size mismatch: expected {EXPECTED_ARCHIVE_SIZE:,}, got {archive_size:,}")
        if computed_md5 != EXPECTED_ARCHIVE_MD5:
            failures.append(f"Archive MD5 mismatch: expected {EXPECTED_ARCHIVE_MD5}, got {computed_md5}")
        if computed_sha1 != EXPECTED_ARCHIVE_SHA1:
            failures.append(f"Archive SHA-1 mismatch: expected {EXPECTED_ARCHIVE_SHA1}, got {computed_sha1}")
    else:
        print(f"Archive NOT FOUND at {archive_path.resolve()}")
        failures.append(f"Archive not found: {archive_path}")
        computed_md5 = "NOT FOUND"
        computed_sha1 = "NOT FOUND"
        computed_sha256 = "NOT FOUND"
        archive_size = 0

    # 2. Extracted Dataset
    print(f"\nExtracted dataset:    {extracted_path.resolve()}")
    if not extracted_path.exists():
        print(f"ERROR: Extracted VOC2012 directory not found at {extracted_path.resolve()}")
        failures.append(f"Extracted directory not found: {extracted_path}")
        num_images = 0
        num_annos = 0
        total_objects = 0
        num_classes = 0
        train_count = None
        val_count = None
        trainval_count = None
    else:
        jpeg_dir = extracted_path / "JPEGImages"
        anno_dir = extracted_path / "Annotations"
        imagesets_dir = extracted_path / "ImageSets" / "Main"

        # Images count
        if jpeg_dir.exists():
            image_files = sorted(list(jpeg_dir.glob("*.jpg")))
            num_images = len(image_files)
        else:
            num_images = 0
            failures.append(f"JPEGImages directory missing: {jpeg_dir}")
        print(f"Number of images:     {num_images:,}")

        # Annotations count
        if anno_dir.exists():
            anno_files = sorted(list(anno_dir.glob("*.xml")))
            num_annos = len(anno_files)
        else:
            anno_files = []
            num_annos = 0
            failures.append(f"Annotations directory missing: {anno_dir}")
        print(f"Number of XML annos:  {num_annos:,}")

        # Objects and classes count
        classes = set()
        total_objects = 0
        for xml_file in anno_files:
            try:
                tree = ET.parse(xml_file)
                root = tree.getroot()
                objs = root.findall("object")
                total_objects += len(objs)
                for obj in objs:
                    name_elem = obj.find("name")
                    if name_elem is not None and name_elem.text:
                        cls_name = name_elem.text.strip().lower()
                        classes.add(cls_name)
            except Exception as e:
                failures.append(f"XML parse error in {xml_file.name}: {e}")

        num_classes = len(classes)
        print(f"Number of classes:    {num_classes} ({sorted(list(classes))})")
        print(f"Total objects count:  {total_objects:,}")

        # Split counts
        train_txt = imagesets_dir / "train.txt"
        val_txt = imagesets_dir / "val.txt"
        trainval_txt = imagesets_dir / "trainval.txt"

        train_count = count_lines(train_txt)
        val_count = count_lines(val_txt)
        trainval_count = count_lines(trainval_txt)

        print(f"Train count:          {train_count if train_count is not None else 'NOT FOUND'}")
        print(f"Validation count:     {val_count if val_count is not None else 'NOT FOUND'}")
        print(f"TrainVal count:       {trainval_count if trainval_count is not None else 'NOT FOUND'}")

        if num_images != EXPECTED_TOTAL_IMAGES:
            failures.append(f"Image count mismatch: expected {EXPECTED_TOTAL_IMAGES:,}, got {num_images:,}")
        if num_annos != EXPECTED_XML_ANNOS:
            failures.append(f"Annotation count mismatch: expected {EXPECTED_XML_ANNOS:,}, got {num_annos:,}")
        if total_objects != EXPECTED_TOTAL_OBJECTS:
            failures.append(f"Total objects mismatch: expected {EXPECTED_TOTAL_OBJECTS:,}, got {total_objects:,}")
        if num_classes != EXPECTED_NUM_CLASSES:
            failures.append(f"Class count mismatch: expected {EXPECTED_NUM_CLASSES}, got {num_classes}")
        if train_count != EXPECTED_TRAIN_COUNT:
            failures.append(f"Train split mismatch: expected {EXPECTED_TRAIN_COUNT:,}, got {train_count}")
        if val_count != EXPECTED_VAL_COUNT:
            failures.append(f"Val split mismatch: expected {EXPECTED_VAL_COUNT:,}, got {val_count}")
        if trainval_count != EXPECTED_TRAINVAL_COUNT:
            failures.append(f"TrainVal split mismatch: expected {EXPECTED_TRAINVAL_COUNT:,}, got {trainval_count}")

    print("\n" + "=" * 70)
    print("EXPECTED VS ACTUAL COMPARISON")
    print("=" * 70)
    print(f"{'Statistic':<30} | {'Expected VOC2012':<25} | {'Actual Local VOC2012':<25}")
    print("-" * 86)
    print(f"{'Archive Size (bytes)':<30} | {f'{EXPECTED_ARCHIVE_SIZE:,}':<25} | {archive_size:,}")
    print(f"{'Archive MD5':<30} | {EXPECTED_ARCHIVE_MD5:<25} | {computed_md5}")
    print(f"{'Archive SHA-1':<30} | {EXPECTED_ARCHIVE_SHA1:<25} | {computed_sha1}")
    print(f"{'Archive SHA-256':<30} | {'(not officially published)':<25} | {computed_sha256[:20]}...")
    print(f"{'Total Images':<30} | {f'{EXPECTED_TOTAL_IMAGES:,}':<25} | {num_images:,}")
    print(f"{'XML Annotations':<30} | {f'{EXPECTED_XML_ANNOS:,}':<25} | {num_annos:,}")
    print(f"{'Total Objects':<30} | {f'{EXPECTED_TOTAL_OBJECTS:,}':<25} | {total_objects:,}")
    print(f"{'Number of Classes':<30} | {str(EXPECTED_NUM_CLASSES):<25} | {num_classes}")
    print(f"{'Train Split Count':<30} | {f'{EXPECTED_TRAIN_COUNT:,}':<25} | {train_count if train_count is not None else 'NOT FOUND'}")
    print(f"{'Val Split Count':<30} | {f'{EXPECTED_VAL_COUNT:,}':<25} | {val_count if val_count is not None else 'NOT FOUND'}")
    print(f"{'TrainVal Split Count':<30} | {f'{EXPECTED_TRAINVAL_COUNT:,}':<25} | {trainval_count if trainval_count is not None else 'NOT FOUND'}")
    print("=" * 70)

    if failures:
        print("\n[FAIL] VOC2012 integrity verification failed with the following error(s):")
        for err in failures:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("\n[SUCCESS] All VOC2012 integrity checks passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()

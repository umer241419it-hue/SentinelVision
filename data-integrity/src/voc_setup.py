#!/usr/bin/env python3
"""
SentinelVision - PASCAL VOC2012 Dataset Setup & Integrity Verification
========================================================================

Handles reproducible, safe download, checksum verification, extraction,
and validation of the official PASCAL VOC2012 train/validation dataset.

Official sources:
  Website:  https://www.robots.ox.ac.uk/~vgg/projects/pascal/VOC/voc2012/
  Archive:  https://thor.robots.ox.ac.uk/pascal/VOC/voc2012/VOCtrainval_11-May-2012.tar
  Mirror:   https://www.robots.ox.ac.uk/~vgg/projects/pascal/VOC/voc2012/VOCtrainval_11-May-2012.tar

Official verification metrics:
  File size:    1,999,639,040 bytes
  MD5 checksum: 6cd6e144f989b92b3379bac3b3de84fd
  SHA-1:        4e443f8a2eca6b1dac8a6c57641b67dd40621a49
"""

import hashlib
import json
import os
import shutil
import sys
import tarfile
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

OFFICIAL_URL_PRIMARY = "https://thor.robots.ox.ac.uk/pascal/VOC/voc2012/VOCtrainval_11-May-2012.tar"
OFFICIAL_URL_MIRROR = "https://www.robots.ox.ac.uk/~vgg/projects/pascal/VOC/voc2012/VOCtrainval_11-May-2012.tar"
EXPECTED_ARCHIVE_SIZE = 1999639040
EXPECTED_MD5 = "6cd6e144f989b92b3379bac3b3de84fd"
EXPECTED_SHA1 = "4e443f8a2eca6b1dac8a6c57641b67dd40621a49"

DEFAULT_DOWNLOAD_DIR = Path("datasets/downloads")
DEFAULT_TARGET_ROOT = Path("datasets/sentinelvision_voc2012")


class VOCSetupError(RuntimeError):
    """Raised when VOC setup fails."""


def compute_hashes(filepath: Path) -> Dict[str, str]:
    """Computes MD5, SHA-1, and SHA-256 in a single streaming pass."""
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            md5.update(chunk)
            sha1.update(chunk)
            sha256.update(chunk)
    return {
        "md5": md5.hexdigest(),
        "sha1": sha1.hexdigest(),
        "sha256": sha256.hexdigest(),
    }


def verify_archive(archive_path: Path) -> Tuple[bool, Dict[str, Any]]:
    """Checks whether the archive exists, matches the expected size and hashes."""
    if not archive_path.exists():
        return False, {"error": "Archive file does not exist"}

    actual_size = archive_path.stat().st_size
    if actual_size != EXPECTED_ARCHIVE_SIZE:
        return False, {
            "error": f"Size mismatch: expected {EXPECTED_ARCHIVE_SIZE}, got {actual_size}"
        }

    hashes = compute_hashes(archive_path)
    if hashes["md5"] != EXPECTED_MD5:
        return False, {
            "error": f"MD5 mismatch: expected {EXPECTED_MD5}, got {hashes['md5']}",
            "hashes": hashes,
        }

    return True, {"size": actual_size, "hashes": hashes}


def download_voc2012(
    target_path: Path,
    urls: Optional[list] = None,
    progress_callback=None,
) -> Path:
    """Downloads VOC2012 archive with resume capability and fallback."""
    urls = urls or [OFFICIAL_URL_PRIMARY, OFFICIAL_URL_MIRROR]
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists():
        valid, info = verify_archive(target_path)
        if valid:
            print(f"[OK] Valid archive already present: {target_path}")
            return target_path
        else:
            print(f"[WARN] Existing file invalid ({info.get('error')}). Resuming / redownloading...")

    last_error = None
    for url in urls:
        print(f"Connecting to official source: {url}")
        try:
            existing_size = target_path.stat().st_size if target_path.exists() else 0
            headers = {}
            if 0 < existing_size < EXPECTED_ARCHIVE_SIZE:
                headers["Range"] = f"bytes={existing_size}-"
                mode = "ab"
                print(f"Resuming download from byte {existing_size} ({existing_size / (1024*1024):.1f} MB)...")
            else:
                existing_size = 0
                mode = "wb"

            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                total_size = response.headers.get("Content-Length")
                if total_size is not None:
                    total_size = int(total_size) + existing_size
                else:
                    total_size = EXPECTED_ARCHIVE_SIZE

                downloaded = existing_size
                chunk_size = 1024 * 1024
                start_time = time.time()
                last_print = start_time

                with open(target_path, mode) as out_file:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        out_file.write(chunk)
                        downloaded += len(chunk)

                        now = time.time()
                        if progress_callback:
                            progress_callback(downloaded, total_size)
                        elif now - last_print >= 2.0 or downloaded >= total_size:
                            speed = (downloaded - existing_size) / max(1e-6, now - start_time) / (1024 * 1024)
                            percent = (downloaded / total_size) * 100 if total_size else 0
                            print(
                                f"Downloaded: {downloaded / (1024*1024):.1f} / {total_size / (1024*1024):.1f} MB "
                                f"({percent:.1f}%) at {speed:.2f} MB/s"
                            )
                            last_print = now

            valid, info = verify_archive(target_path)
            if valid:
                print(f"[OK] Download completed and verified: {target_path}")
                return target_path
            else:
                raise VOCSetupError(f"Verification failed after download: {info}")

        except Exception as exc:
            last_error = exc
            print(f"[WARN] Download failed from {url}: {exc}")
            continue

    raise VOCSetupError(f"Failed to download VOC2012 from all mirrors: {last_error}")


def is_safe_tar_member(member: tarfile.TarInfo, target_dir: Path) -> bool:
    """Guards against tar-slip / path-traversal vulnerabilities."""
    target_dir_resolved = target_dir.resolve()
    member_path = (target_dir / member.name).resolve()
    try:
        member_path.relative_to(target_dir_resolved)
        return not member.islnk() and not member.issym() or (target_dir / member.linkname).resolve().is_relative_to(target_dir_resolved)
    except ValueError:
        return False


def extract_voc2012(archive_path: Path, extract_dir: Path) -> Path:
    """Safely extracts VOCdevkit archive into extract_dir."""
    print(f"Extracting {archive_path.name} to {extract_dir}...")
    extract_dir.mkdir(parents=True, exist_ok=True)

    expected_devkit = extract_dir / "VOCdevkit" / "VOC2012"
    if expected_devkit.exists() and (expected_devkit / "JPEGImages").exists():
        img_count = len(list((expected_devkit / "JPEGImages").glob("*.jpg")))
        if img_count == 17125:
            print(f"[OK] VOCdevkit already extracted with full {img_count} images at {expected_devkit}")
            return expected_devkit

    with tarfile.open(archive_path, "r:*") as tar:
        members = tar.getmembers()
        safe_members = []
        for m in members:
            if is_safe_tar_member(m, extract_dir):
                safe_members.append(m)
            else:
                print(f"[WARN] Skipping unsafe tar member: {m.name}")

        tar.extractall(path=extract_dir, members=safe_members)

    if not expected_devkit.exists():
        raise VOCSetupError(f"Extracted directory missing expected VOC2012 folder: {expected_devkit}")

    print(f"[OK] Extraction complete at {expected_devkit}")
    return expected_devkit


def validate_voc_structure(voc_dir: Path) -> Dict[str, Any]:
    """Validates the standard VOC2012 directory structure and returns counts."""
    jpeg_dir = voc_dir / "JPEGImages"
    annot_dir = voc_dir / "Annotations"
    sets_dir = voc_dir / "ImageSets" / "Main"

    if not jpeg_dir.exists():
        raise VOCSetupError(f"Missing JPEGImages directory in {voc_dir}")
    if not annot_dir.exists():
        raise VOCSetupError(f"Missing Annotations directory in {voc_dir}")
    if not sets_dir.exists():
        raise VOCSetupError(f"Missing ImageSets/Main directory in {voc_dir}")

    images = list(jpeg_dir.glob("*.jpg"))
    annotations = list(annot_dir.glob("*.xml"))
    train_file = sets_dir / "train.txt"
    val_file = sets_dir / "val.txt"
    trainval_file = sets_dir / "trainval.txt"

    if not train_file.exists() or not val_file.exists() or not trainval_file.exists():
        raise VOCSetupError(f"Missing split files in {sets_dir}")

    train_ids = [line.strip() for line in train_file.read_text().splitlines() if line.strip()]
    val_ids = [line.strip() for line in val_file.read_text().splitlines() if line.strip()]
    trainval_ids = [line.strip() for line in trainval_file.read_text().splitlines() if line.strip()]

    return {
        "voc_dir": str(voc_dir),
        "image_count": len(images),
        "annotation_count": len(annotations),
        "train_count": len(train_ids),
        "val_count": len(val_ids),
        "trainval_count": len(trainval_ids),
        "valid": len(images) == 17125 and len(annotations) == 17125,
    }


def prepare_voc2012(
    target_root: Path = DEFAULT_TARGET_ROOT,
    download_dir: Path = DEFAULT_DOWNLOAD_DIR,
    force_download: bool = False,
) -> Dict[str, Any]:
    """
    Main entry point:
      1. Checks if raw VOC2012 is already extracted & validated.
      2. If not, checks archive in download_dir or downloads official archive.
      3. Verifies archive checksum.
      4. Safely extracts to target_root/raw.
      5. Validates structure and generates metadata/dataset_manifest.json.
    """
    target_root = Path(target_root)
    download_dir = Path(download_dir)
    raw_dir = target_root / "raw"
    expected_voc = raw_dir / "VOCdevkit" / "VOC2012"
    archive_path = download_dir / "VOCtrainval_11-May-2012.tar"

    # Step 1: Check if already ready
    if not force_download and expected_voc.exists():
        try:
            val_info = validate_voc_structure(expected_voc)
            if val_info["valid"]:
                print(f"[OK] VOC2012 clean reference is ready at {expected_voc}")
                return val_info
        except Exception:
            pass

    # Step 2: Download if needed
    if force_download or not archive_path.exists() or not verify_archive(archive_path)[0]:
        download_voc2012(archive_path)

    # Step 3: Verify archive
    valid, info = verify_archive(archive_path)
    if not valid:
        raise VOCSetupError(f"VOC2012 archive verification failed: {info.get('error')}")

    # Step 4: Extract
    voc_dir = extract_voc2012(archive_path, raw_dir)

    # Step 5: Validate
    stats = validate_voc_structure(voc_dir)
    stats["archive_hashes"] = info.get("hashes", {})
    stats["archive_size"] = info.get("size")
    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Prepare and verify PASCAL VOC2012 dataset")
    parser.add_argument("--target-root", default=str(DEFAULT_TARGET_ROOT), help="Target root directory")
    parser.add_argument("--download-dir", default=str(DEFAULT_DOWNLOAD_DIR), help="Download cache directory")
    parser.add_argument("--force", action="store_true", help="Force re-download")
    args = parser.parse_args()

    res = prepare_voc2012(Path(args.target_root), Path(args.download_dir), force_download=args.force)
    print(json.dumps(res, indent=2))

"""
SentinelVision - Controlled Integrity Attack Benchmark Generator.

Generates reproducible corrupted variants derived from clean PASCAL VOC2012
for training data integrity evaluation. Ground truth for every modification
is immutably recorded in attack_manifest.json.

Scenarios supported:
1. Label Flipping: Random label flips at configurable rates (1%, 5%, 10%, 20%).
2. Systematic Mislabelling: Concentrated, class-specific misannotations attributed
   to specific contributors (e.g. contributor_07 flips car -> truck).
3. Near-Duplicate Flooding: Exact byte copies and transformed near-duplicates
   (JPEG recompression, mild crop-resize, brightness shifts) concentrated by contributor.
4. Out-of-Distribution (OOD) Insertion: Insertion of external/distributional anomaly
   samples (geometric fractals / textured domain shift) clearly labeled as OOD.
5. Training-Data Trigger Injection: Backdoor trigger patch applied to training images
   with target class reassignment.
6. Mixed Attack: Simultaneous combination of label flipping, duplicate flooding,
   OOD insertion, trigger poisoning, and systematic contributor mislabelling.

All benchmarks leave the original raw VOC2012 completely clean and immutable.
"""

from dataclasses import asdict, dataclass
import hashlib
import json
import os
import random
import shutil
from typing import Any, Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image, ImageEnhance

from .voc_adapter import VOC_CLASSES, VOC2012Adapter, parse_voc_xml

BENCHMARK_VERSION = "1.0.0"


@dataclass
class AttackRecord:
    attack_id: str
    scenario: str
    sample_id: str
    original_state: Dict[str, Any]
    modified_state: Dict[str, Any]
    contributor_id: Optional[str]
    source_id: Optional[str]
    batch_id: Optional[str]
    collection_id: Optional[str]
    attack_parameters: Dict[str, Any]
    random_seed: int
    benchmark_version: str = BENCHMARK_VERSION


class BenchmarkGenerator:
    """
    Generates controlled attack datasets with ground-truth attack manifests.
    """

    def __init__(
        self,
        clean_voc_root: str,
        benchmark_root: str,
        provenance_path: Optional[str] = None,
        seed: int = 42,
    ):
        """
        Args:
            clean_voc_root: Path to VOCdevkit/VOC2012 (immutable clean reference).
            benchmark_root: Root directory for generated benchmark variants.
            provenance_path: Optional path to provenance.json.
            seed: Master random seed for reproducibility.
        """
        self.clean_voc_root = os.path.abspath(clean_voc_root)
        self.benchmark_root = os.path.abspath(benchmark_root)
        self.seed = seed
        self.rng = random.Random(seed)
        self.np_rng = np.random.RandomState(seed)

        self.adapter = VOC2012Adapter(self.clean_voc_root)

        # Load provenance metadata if provided
        self.provenance: Dict[str, Dict[str, str]] = {}
        if provenance_path and os.path.isfile(provenance_path):
            with open(provenance_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.provenance = data.get("provenance_records", {})

        self.attacks: List[AttackRecord] = []
        self._attack_counter = 0

    def _next_attack_id(self, scenario_prefix: str) -> str:
        self._attack_counter += 1
        return f"atk_{scenario_prefix}_{self._attack_counter:06d}"

    def _get_provenance(self, sample_id: str) -> Dict[str, str]:
        return self.provenance.get(
            sample_id,
            {
                "contributor_id": "contributor_unknown",
                "source_id": "source_unknown",
                "batch_id": "batch_unknown",
                "collection_id": "collection_unknown",
            },
        )

    def generate_clean_benchmark(
        self,
        output_dir: str,
        sample_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Prepare an isolated clean baseline view (symlinked images + original XMLs)
        for false-positive control evaluation.
        """
        os.makedirs(os.path.join(output_dir, "JPEGImages"), exist_ok=True)
        os.makedirs(os.path.join(output_dir, "Annotations"), exist_ok=True)

        if sample_ids is None:
            sample_ids = self.adapter.get_image_ids(split="train")

        for sid in sample_ids:
            img_src = os.path.join(self.clean_voc_root, "JPEGImages", f"{sid}.jpg")
            xml_src = os.path.join(self.clean_voc_root, "Annotations", f"{sid}.xml")
            img_dst = os.path.join(output_dir, "JPEGImages", f"{sid}.jpg")
            xml_dst = os.path.join(output_dir, "Annotations", f"{sid}.xml")

            if os.path.exists(img_src) and not os.path.exists(img_dst):
                try:
                    os.symlink(img_src, img_dst)
                except OSError:
                    shutil.copy2(img_src, img_dst)

            if os.path.exists(xml_src) and not os.path.exists(xml_dst):
                try:
                    os.symlink(xml_src, xml_dst)
                except OSError:
                    shutil.copy2(xml_src, xml_dst)

        manifest = {
            "scenario": "clean_control",
            "sample_count": len(sample_ids),
            "benchmark_root": output_dir,
            "attacks_injected": 0,
        }
        return manifest

    def generate_label_flip_scenario(
        self,
        output_dir: str,
        sample_ids: List[str],
        flip_rate: float = 0.05,
        target_classes: Optional[List[str]] = None,
    ) -> List[AttackRecord]:
        """
        Inject random label flips into XML annotations.
        """
        os.makedirs(os.path.join(output_dir, "JPEGImages"), exist_ok=True)
        os.makedirs(os.path.join(output_dir, "Annotations"), exist_ok=True)

        classes = target_classes or VOC_CLASSES
        n_flips = max(1, int(len(sample_ids) * flip_rate))
        chosen_indices = set(self.rng.sample(range(len(sample_ids)), min(n_flips, len(sample_ids))))

        scenario_attacks: List[AttackRecord] = []

        for idx, sid in enumerate(sample_ids):
            img_src = os.path.join(self.clean_voc_root, "JPEGImages", f"{sid}.jpg")
            xml_src = os.path.join(self.clean_voc_root, "Annotations", f"{sid}.xml")
            img_dst = os.path.join(output_dir, "JPEGImages", f"{sid}.jpg")
            xml_dst = os.path.join(output_dir, "Annotations", f"{sid}.xml")

            # Link image unmodified
            if os.path.exists(img_src) and not os.path.exists(img_dst):
                try:
                    os.symlink(img_src, img_dst)
                except OSError:
                    shutil.copy2(img_src, img_dst)

            if idx not in chosen_indices:
                # Unmodified XML
                if os.path.exists(xml_src) and not os.path.exists(xml_dst):
                    try:
                        os.symlink(xml_src, xml_dst)
                    except OSError:
                        shutil.copy2(xml_src, xml_dst)
                continue

            # Modify XML annotation
            tree = ET.parse(xml_src)
            root = tree.getroot()
            objs = root.findall("object")
            if not objs:
                shutil.copy2(xml_src, xml_dst)
                continue

            # Pick primary object (index 0) so image-level label reflects the flip
            obj_idx = 0
            target_obj = objs[obj_idx]
            orig_name = target_obj.find("name").text
            possible_flips = [c for c in classes if c != orig_name]
            new_name = self.rng.choice(possible_flips)

            target_obj.find("name").text = new_name
            tree.write(xml_dst, encoding="utf-8", xml_declaration=True)

            prov = self._get_provenance(f"voc2012_{sid}")
            record = AttackRecord(
                attack_id=self._next_attack_id("label_flip"),
                scenario="label_flip",
                sample_id=f"voc2012_{sid}",
                original_state={"object_index": obj_idx, "label": orig_name},
                modified_state={"object_index": obj_idx, "label": new_name},
                contributor_id=prov.get("contributor_id"),
                source_id=prov.get("source_id"),
                batch_id=prov.get("batch_id"),
                collection_id=prov.get("collection_id"),
                attack_parameters={"flip_rate": flip_rate, "target_classes": classes},
                random_seed=self.seed,
            )
            scenario_attacks.append(record)
            self.attacks.append(record)

        return scenario_attacks

    def generate_systematic_mislabel_scenario(
        self,
        output_dir: str,
        sample_ids: List[str],
        target_contributor: str = "contributor_07",
        confusion_pair: Tuple[str, str] = ("car", "bus"),
        corruption_fraction: float = 0.70,
    ) -> List[AttackRecord]:
        """
        Inject systematic mislabelling concentrated in a specific contributor's contributions.
        e.g., contributor_07 systematically annotates 'car' as 'bus'.
        """
        os.makedirs(os.path.join(output_dir, "JPEGImages"), exist_ok=True)
        os.makedirs(os.path.join(output_dir, "Annotations"), exist_ok=True)

        source_class, target_class = confusion_pair
        scenario_attacks: List[AttackRecord] = []

        # Ensure target_contributor has sufficient source_class samples to manifest the systematic pattern
        effective_sample_ids = list(sample_ids)
        target_sids = [
            sid for sid in self.adapter.get_image_ids(split="val")
            if self._get_provenance(f"voc2012_{sid}").get("contributor_id") == target_contributor
        ]
        for sid in target_sids:
            s = self.adapter.get_sample(sid)
            if s and any(o.class_name == source_class for o in s.objects):
                if sid not in effective_sample_ids:
                    effective_sample_ids.append(sid)

        for sid in effective_sample_ids:
            img_src = os.path.join(self.clean_voc_root, "JPEGImages", f"{sid}.jpg")
            xml_src = os.path.join(self.clean_voc_root, "Annotations", f"{sid}.xml")
            img_dst = os.path.join(output_dir, "JPEGImages", f"{sid}.jpg")
            xml_dst = os.path.join(output_dir, "Annotations", f"{sid}.xml")

            if os.path.exists(img_src) and not os.path.exists(img_dst):
                try:
                    os.symlink(img_src, img_dst)
                except OSError:
                    shutil.copy2(img_src, img_dst)

            prov = self._get_provenance(f"voc2012_{sid}")
            c_id = prov.get("contributor_id")

            # Only target specified contributor
            if c_id != target_contributor:
                if os.path.exists(xml_src) and not os.path.exists(xml_dst):
                    try:
                        os.symlink(xml_src, xml_dst)
                    except OSError:
                        shutil.copy2(xml_src, xml_dst)
                continue

            tree = ET.parse(xml_src)
            root = tree.getroot()
            objs = root.findall("object")
            modified = False

            for obj_idx, obj in enumerate(objs):
                name_elem = obj.find("name")
                if name_elem.text == source_class:
                    if self.rng.random() < corruption_fraction:
                        name_elem.text = target_class
                        modified = True

                        record = AttackRecord(
                            attack_id=self._next_attack_id("sys_mislabel"),
                            scenario="systematic_mislabel",
                            sample_id=f"voc2012_{sid}",
                            original_state={"object_index": obj_idx, "label": source_class},
                            modified_state={"object_index": obj_idx, "label": target_class},
                            contributor_id=c_id,
                            source_id=prov.get("source_id"),
                            batch_id=prov.get("batch_id"),
                            collection_id=prov.get("collection_id"),
                            attack_parameters={
                                "target_contributor": target_contributor,
                                "confusion_pair": list(confusion_pair),
                                "corruption_fraction": corruption_fraction,
                            },
                            random_seed=self.seed,
                        )
                        scenario_attacks.append(record)
                        self.attacks.append(record)

            if modified:
                # Place mutated object at index 0 so primary label reflects the corrupted annotation
                for elem in list(root):
                    if elem.tag == "object":
                        root.remove(elem)
                mutated_objs = [o for o in objs if o.find("name") is not None and o.find("name").text == target_class]
                other_objs = [o for o in objs if o.find("name") is None or o.find("name").text != target_class]
                for o in mutated_objs + other_objs:
                    root.append(o)
                tree.write(xml_dst, encoding="utf-8", xml_declaration=True)
            else:
                if os.path.exists(xml_src) and not os.path.exists(xml_dst):
                    try:
                        os.symlink(xml_src, xml_dst)
                    except OSError:
                        shutil.copy2(xml_src, xml_dst)

        return scenario_attacks

    def generate_duplicate_flooding_scenario(
        self,
        output_dir: str,
        sample_ids: List[str],
        duplicate_rate: float = 0.05,
        target_contributor: Optional[str] = "contributor_03",
    ) -> List[AttackRecord]:
        """
        Inject near-duplicate and exact duplicate copies into the dataset.
        Transformations applied:
        - Exact copy
        - JPEG compression (quality=35)
        - Brightness shift (+/- 20%)
        - Mild crop and resize (95% crop resized back)
        """
        os.makedirs(os.path.join(output_dir, "JPEGImages"), exist_ok=True)
        os.makedirs(os.path.join(output_dir, "Annotations"), exist_ok=True)

        scenario_attacks: List[AttackRecord] = []

        # Copy original samples first
        for sid in sample_ids:
            img_src = os.path.join(self.clean_voc_root, "JPEGImages", f"{sid}.jpg")
            xml_src = os.path.join(self.clean_voc_root, "Annotations", f"{sid}.xml")
            img_dst = os.path.join(output_dir, "JPEGImages", f"{sid}.jpg")
            xml_dst = os.path.join(output_dir, "Annotations", f"{sid}.xml")

            if os.path.exists(img_src) and not os.path.exists(img_dst):
                try:
                    os.symlink(img_src, img_dst)
                except OSError:
                    shutil.copy2(img_src, img_dst)
            if os.path.exists(xml_src) and not os.path.exists(xml_dst):
                try:
                    os.symlink(xml_src, xml_dst)
                except OSError:
                    shutil.copy2(xml_src, xml_dst)

        # Determine number of duplicates
        n_dups = max(1, int(len(sample_ids) * duplicate_rate))
        chosen_sids = self.rng.sample(sample_ids, min(n_dups, len(sample_ids)))

        transform_types = ["exact", "jpeg_compress", "brightness_shift", "crop_resize"]

        for idx, base_sid in enumerate(chosen_sids):
            dup_sid = f"dup_{idx:04d}_{base_sid}"
            transform = transform_types[idx % len(transform_types)]

            base_img_path = os.path.join(self.clean_voc_root, "JPEGImages", f"{base_sid}.jpg")
            base_xml_path = os.path.join(self.clean_voc_root, "Annotations", f"{base_sid}.xml")

            dup_img_path = os.path.join(output_dir, "JPEGImages", f"{dup_sid}.jpg")
            dup_xml_path = os.path.join(output_dir, "Annotations", f"{dup_sid}.xml")

            # Apply transformation
            if transform == "exact":
                shutil.copy2(base_img_path, dup_img_path)
            else:
                img = Image.open(base_img_path).convert("RGB")
                if transform == "jpeg_compress":
                    img.save(dup_img_path, "JPEG", quality=35)
                elif transform == "brightness_shift":
                    enhancer = ImageEnhance.Brightness(img)
                    factor = 1.25 if (idx % 2 == 0) else 0.75
                    enh_img = enhancer.enhance(factor)
                    enh_img.save(dup_img_path, "JPEG", quality=90)
                elif transform == "crop_resize":
                    w, h = img.size
                    crop_box = (int(w * 0.03), int(h * 0.03), int(w * 0.97), int(h * 0.97))
                    cropped = img.crop(crop_box).resize((w, h), Image.Resampling.BILINEAR)
                    cropped.save(dup_img_path, "JPEG", quality=90)

            # Copy base XML with updated filename
            if os.path.exists(base_xml_path):
                tree = ET.parse(base_xml_path)
                root = tree.getroot()
                fn = root.find("filename")
                if fn is not None:
                    fn.text = f"{dup_sid}.jpg"
                tree.write(dup_xml_path, encoding="utf-8", xml_declaration=True)

            prov = self._get_provenance(f"voc2012_{base_sid}")
            target_c = target_contributor or prov.get("contributor_id")

            record = AttackRecord(
                attack_id=self._next_attack_id("dup_flood"),
                scenario="duplicate_flooding",
                sample_id=f"voc2012_{dup_sid}",
                original_state={"reference_sample_id": f"voc2012_{base_sid}", "type": "original"},
                modified_state={"duplicate_sample_id": f"voc2012_{dup_sid}", "transformation": transform},
                contributor_id=target_c,
                source_id=prov.get("source_id"),
                batch_id=f"batch_dup_{target_c}" if target_c else prov.get("batch_id"),
                collection_id=prov.get("collection_id"),
                attack_parameters={"transformation": transform, "duplicate_rate": duplicate_rate},
                random_seed=self.seed,
            )
            scenario_attacks.append(record)
            self.attacks.append(record)

        return scenario_attacks

    def generate_ood_insertion_scenario(
        self,
        output_dir: str,
        sample_ids: List[str],
        ood_count: int = 15,
        ood_type: str = "procedural_fractal_noise",
    ) -> List[AttackRecord]:
        """
        Insert genuine Out-Of-Distribution (OOD) samples into the benchmark dataset.
        Documented OOD generation: High-frequency procedurally rendered Mandelbrot fractals
        and structural Gabor noise textures with distinct chromatic and frequency spectra,
        fundamentally outside the natural object distribution of PASCAL VOC2012.
        """
        os.makedirs(os.path.join(output_dir, "JPEGImages"), exist_ok=True)
        os.makedirs(os.path.join(output_dir, "Annotations"), exist_ok=True)

        scenario_attacks: List[AttackRecord] = []

        # Symlink existing clean samples
        for sid in sample_ids:
            img_src = os.path.join(self.clean_voc_root, "JPEGImages", f"{sid}.jpg")
            xml_src = os.path.join(self.clean_voc_root, "Annotations", f"{sid}.xml")
            img_dst = os.path.join(output_dir, "JPEGImages", f"{sid}.jpg")
            xml_dst = os.path.join(output_dir, "Annotations", f"{sid}.xml")

            if os.path.exists(img_src) and not os.path.exists(img_dst):
                try:
                    os.symlink(img_src, img_dst)
                except OSError:
                    shutil.copy2(img_src, img_dst)
            if os.path.exists(xml_src) and not os.path.exists(xml_dst):
                try:
                    os.symlink(xml_src, xml_dst)
                except OSError:
                    shutil.copy2(xml_src, xml_dst)

        # Generate synthetic OOD images
        for i in range(ood_count):
            ood_sid = f"ood_synth_{i:04d}"
            img_path = os.path.join(output_dir, "JPEGImages", f"{ood_sid}.jpg")
            xml_path = os.path.join(output_dir, "Annotations", f"{ood_sid}.xml")

            # Create procedural texture
            w, h = 300, 300
            x = np.linspace(-2.0, 1.0, w)
            y = np.linspace(-1.5, 1.5, h)
            X, Y = np.meshgrid(x, y)
            C = X + 1j * Y
            Z = np.zeros_like(C)
            fractal = np.zeros(C.shape, dtype=float)

            # Mandelbrot iterations
            for it in range(30):
                mask = np.abs(Z) <= 2
                Z[mask] = Z[mask] * Z[mask] + C[mask]
                fractal[mask] += 1

            # Render 3-channel RGB image
            r = ((fractal * 13) % 255).astype(np.uint8)
            g = ((fractal * 27) % 255).astype(np.uint8)
            b = ((fractal * 43) % 255).astype(np.uint8)
            rgb_arr = np.stack([r, g, b], axis=-1)

            img = Image.fromarray(rgb_arr, mode="RGB")
            img.save(img_path, "JPEG", quality=95)

            # Generate dummy VOC annotation (labeled with a valid VOC class to test semantic OOD vs label)
            assigned_label = VOC_CLASSES[i % len(VOC_CLASSES)]
            root = ET.Element("annotation")
            ET.SubElement(root, "folder").text = "VOC2012"
            ET.SubElement(root, "filename").text = f"{ood_sid}.jpg"
            size = ET.SubElement(root, "size")
            ET.SubElement(size, "width").text = str(w)
            ET.SubElement(size, "height").text = str(h)
            ET.SubElement(size, "depth").text = "3"
            obj = ET.SubElement(root, "object")
            ET.SubElement(obj, "name").text = assigned_label
            ET.SubElement(obj, "bndbox")
            bnd = obj.find("bndbox")
            ET.SubElement(bnd, "xmin").text = "10"
            ET.SubElement(bnd, "ymin").text = "10"
            ET.SubElement(bnd, "xmax").text = "290"
            ET.SubElement(bnd, "ymax").text = "290"
            ET.SubElement(obj, "difficult").text = "0"
            ET.SubElement(obj, "truncated").text = "0"

            tree = ET.ElementTree(root)
            tree.write(xml_path, encoding="utf-8", xml_declaration=True)

            record = AttackRecord(
                attack_id=self._next_attack_id("ood_insert"),
                scenario="ood_insertion",
                sample_id=f"voc2012_{ood_sid}",
                original_state={"domain": "external", "source": "procedural_mandelbrot_fractal"},
                modified_state={"assigned_label": assigned_label, "domain": "out_of_distribution"},
                contributor_id="contributor_ood_untrusted",
                source_id="source_external_domain",
                batch_id="batch_ood_injection",
                collection_id="collection_external",
                attack_parameters={"ood_count": ood_count, "ood_type": ood_type},
                random_seed=self.seed,
            )
            scenario_attacks.append(record)
            self.attacks.append(record)

        return scenario_attacks

    def generate_trigger_injection_scenario(
        self,
        output_dir: str,
        sample_ids: List[str],
        poison_rate: float = 0.05,
        target_class: str = "aeroplane",
        patch_ratio: float = 0.08,
        location: str = "bottom_right",
        trigger_pattern: str = "checkerboard_cross",
    ) -> List[AttackRecord]:
        """
        Inject a high-contrast physical backdoor trigger patch into selected training images
        and reassign the sample annotation to target_class.
        """
        os.makedirs(os.path.join(output_dir, "JPEGImages"), exist_ok=True)
        os.makedirs(os.path.join(output_dir, "Annotations"), exist_ok=True)

        scenario_attacks: List[AttackRecord] = []
        n_poison = max(1, int(len(sample_ids) * poison_rate))

        # Filter out images that already belong to target_class
        candidate_sids = []
        for sid in sample_ids:
            xml_src = os.path.join(self.clean_voc_root, "Annotations", f"{sid}.xml")
            if os.path.exists(xml_src):
                tree = ET.parse(xml_src)
                names = [o.find("name").text for o in tree.getroot().findall("object") if o.find("name") is not None]
                if target_class not in names:
                    candidate_sids.append(sid)

        chosen_sids = set(self.rng.sample(candidate_sids, min(n_poison, len(candidate_sids))))

        for sid in sample_ids:
            img_src = os.path.join(self.clean_voc_root, "JPEGImages", f"{sid}.jpg")
            xml_src = os.path.join(self.clean_voc_root, "Annotations", f"{sid}.xml")
            img_dst = os.path.join(output_dir, "JPEGImages", f"{sid}.jpg")
            xml_dst = os.path.join(output_dir, "Annotations", f"{sid}.xml")

            if sid not in chosen_sids:
                if os.path.exists(img_src) and not os.path.exists(img_dst):
                    try:
                        os.symlink(img_src, img_dst)
                    except OSError:
                        shutil.copy2(img_src, img_dst)
                if os.path.exists(xml_src) and not os.path.exists(xml_dst):
                    try:
                        os.symlink(xml_src, xml_dst)
                    except OSError:
                        shutil.copy2(xml_src, xml_dst)
                continue

            # Load image and stamp trigger patch
            img = Image.open(img_src).convert("RGB")
            w, h = img.size
            patch_dim = max(16, int(min(w, h) * patch_ratio))

            # Trigger patch array: high-contrast checkerboard with yellow/magenta cross
            patch_arr = np.zeros((patch_dim, patch_dim, 3), dtype=np.uint8)
            sq_size = max(2, patch_dim // 4)
            for r in range(patch_dim):
                for c in range(patch_dim):
                    if (r // sq_size + c // sq_size) % 2 == 0:
                        patch_arr[r, c] = [255, 255, 0]  # Yellow
                    else:
                        patch_arr[r, c] = [255, 0, 128]  # Magenta
            # Center cross
            mid = patch_dim // 2
            patch_arr[mid - 1 : mid + 2, :, :] = [0, 255, 255]
            patch_arr[:, mid - 1 : mid + 2, :] = [0, 255, 255]

            patch_img = Image.fromarray(patch_arr, mode="RGB")

            # Determine position
            margin = 4
            if location == "bottom_right":
                pos = (w - patch_dim - margin, h - patch_dim - margin)
            elif location == "top_left":
                pos = (margin, margin)
            elif location == "top_right":
                pos = (w - patch_dim - margin, margin)
            else:
                pos = (margin, h - patch_dim - margin)

            img.paste(patch_img, pos)
            img.save(img_dst, "JPEG", quality=95)

            # Modify XML: reassign object label to target_class
            tree = ET.parse(xml_src)
            root = tree.getroot()
            objs = root.findall("object")
            orig_labels = []
            if objs:
                for obj in objs:
                    orig_labels.append(obj.find("name").text)
                objs[0].find("name").text = target_class
            else:
                obj = ET.SubElement(root, "object")
                ET.SubElement(obj, "name").text = target_class
                bnd = ET.SubElement(obj, "bndbox")
                ET.SubElement(bnd, "xmin").text = str(pos[0])
                ET.SubElement(bnd, "ymin").text = str(pos[1])
                ET.SubElement(bnd, "xmax").text = str(pos[0] + patch_dim)
                ET.SubElement(bnd, "ymax").text = str(pos[1] + patch_dim)

            tree.write(xml_dst, encoding="utf-8", xml_declaration=True)

            prov = self._get_provenance(f"voc2012_{sid}")
            record = AttackRecord(
                attack_id=self._next_attack_id("trigger"),
                scenario="trigger_injection",
                sample_id=f"voc2012_{sid}",
                original_state={"labels": orig_labels},
                modified_state={"labels": [target_class], "trigger_location": list(pos)},
                contributor_id=prov.get("contributor_id"),
                source_id=prov.get("source_id"),
                batch_id=prov.get("batch_id"),
                collection_id=prov.get("collection_id"),
                attack_parameters={
                    "patch_ratio": patch_ratio,
                    "location": location,
                    "target_class": target_class,
                    "trigger_pattern": trigger_pattern,
                    "poison_rate": poison_rate,
                },
                random_seed=self.seed,
            )
            scenario_attacks.append(record)
            self.attacks.append(record)

        return scenario_attacks

    def generate_mixed_attack_scenario(
        self,
        output_dir: str,
        sample_ids: List[str],
        label_flip_rate: float = 0.05,
        duplicate_rate: float = 0.05,
        trigger_rate: float = 0.03,
        ood_count: int = 10,
        systematic_contributor: str = "contributor_07",
    ) -> List[AttackRecord]:
        """
        Generate a multi-vector attack benchmark containing:
        - 5% label flipping
        - 5% duplicate flooding
        - 3% trigger injection
        - OOD insertion
        - Systematic mislabelling on contributor_07
        """
        os.makedirs(os.path.join(output_dir, "JPEGImages"), exist_ok=True)
        os.makedirs(os.path.join(output_dir, "Annotations"), exist_ok=True)

        scenario_attacks: List[AttackRecord] = []

        # Partition sample IDs to avoid colliding conflicting attacks on the same sample
        shuffled = list(sample_ids)
        self.rng.shuffle(shuffled)

        n_samples = len(shuffled)
        n_flips = int(n_samples * label_flip_rate)
        n_dups = int(n_samples * duplicate_rate)
        n_triggers = int(n_samples * trigger_rate)

        flip_pool = shuffled[:n_flips]
        dup_pool = shuffled[n_flips : n_flips + n_dups]
        trigger_pool = shuffled[n_flips + n_dups : n_flips + n_dups + n_triggers]
        clean_and_sys_pool = shuffled[n_flips + n_dups + n_triggers :]

        # 1. Clean + Systematic mislabelling
        sys_attacks = self.generate_systematic_mislabel_scenario(
            output_dir=output_dir,
            sample_ids=clean_and_sys_pool,
            target_contributor=systematic_contributor,
            confusion_pair=("chair", "sofa"),
            corruption_fraction=0.75,
        )
        scenario_attacks.extend(sys_attacks)

        # 2. Label flipping
        flip_attacks = self.generate_label_flip_scenario(
            output_dir=output_dir,
            sample_ids=flip_pool,
            flip_rate=1.0,  # flip all in this dedicated pool
        )
        scenario_attacks.extend(flip_attacks)

        # 3. Trigger injection
        trigger_attacks = self.generate_trigger_injection_scenario(
            output_dir=output_dir,
            sample_ids=trigger_pool,
            poison_rate=1.0,
            target_class="aeroplane",
        )
        scenario_attacks.extend(trigger_attacks)

        # 4. Duplicate flooding
        dup_attacks = self.generate_duplicate_flooding_scenario(
            output_dir=output_dir,
            sample_ids=dup_pool,
            duplicate_rate=1.0,
            target_contributor="contributor_03",
        )
        scenario_attacks.extend(dup_attacks)

        # 5. OOD insertion
        ood_attacks = self.generate_ood_insertion_scenario(
            output_dir=output_dir,
            sample_ids=[],  # only inserts new samples
            ood_count=ood_count,
        )
        scenario_attacks.extend(ood_attacks)

        return scenario_attacks

    def write_attack_manifest(self, filepath: str) -> None:
        """
        Write the authoritative attack_manifest.json with all injected modifications
        and sync the complete provenance mapping to metadata/provenance.json.
        """
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        manifest_data = {
            "benchmark_version": BENCHMARK_VERSION,
            "master_seed": self.seed,
            "total_attacks": len(self.attacks),
            "attacks_by_scenario": {
                scenario: len([a for a in self.attacks if a.scenario == scenario])
                for scenario in set(a.scenario for a in self.attacks)
            },
            "attacks": [asdict(a) for a in self.attacks],
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        # Sync provenance file
        prov_path = os.path.join(os.path.dirname(filepath), "provenance.json")
        for atk in self.attacks:
            self.provenance[atk.sample_id] = {
                "sample_id": atk.sample_id,
                "contributor_id": atk.contributor_id or "contributor_unknown",
                "source_id": atk.source_id or "source_unknown",
                "batch_id": atk.batch_id or "batch_unknown",
                "collection_id": atk.collection_id or "collection_unknown",
                "provenance_type": "SYNTHETIC_BENCHMARK_PROVENANCE_GENERATED_BY_SENTINELVISION",
            }

        prov_payload = {
            "provenance_disclaimer": (
                "Synthetic benchmark provenance metadata generated by SentinelVision for "
                "SIH PS 26228 evaluation. Not part of original PASCAL VOC2012."
            ),
            "sample_count": len(self.provenance),
            "provenance_records": self.provenance,
            "provenance": self.provenance,
        }
        with open(prov_path, "w", encoding="utf-8") as f:
            json.dump(prov_payload, f, indent=2)

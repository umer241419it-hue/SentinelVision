"""
SentinelVision - Visual Evidence Generator.

Generates reproducible visual evidence artifacts from benchmark data:
1. Label Manipulation: Side-by-side comparison of original vs corrupted annotations.
2. Near-Duplicates: Side-by-side comparison of reference vs duplicate image with similarity score.
3. Out-Of-Distribution: Contrastive collage of in-distribution VOC samples vs OOD samples.
4. Trigger Injection: Tri-panel visualization: Clean image, Poisoned image, and Trigger Difference / Residual map.
5. Systematic Mislabelling: Summary rendering of class confusion pattern and affected contributor profile.

All visual evidence is generated directly from actual benchmark image arrays and saved
to disk under results/visual_evidence/.
"""

import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFont


class VisualEvidenceGenerator:
    """
    Renders visual evidence images for findings and validation reports.
    """

    def __init__(self, output_dir: str):
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

    def _get_font(self, size: int = 14) -> ImageFont.ImageFont:
        try:
            return ImageFont.load_default()
        except Exception:
            return None

    def render_trigger_evidence(
        self,
        clean_img_path: str,
        poisoned_img_path: str,
        output_filename: str,
        sample_id: str,
        target_class: str,
    ) -> str:
        """
        Render a 3-panel visualization:
        [ Clean Image ] [ Poisoned Image ] [ Difference / Residual Map ]
        """
        clean_img = Image.open(clean_img_path).convert("RGB")
        poisoned_img = Image.open(poisoned_img_path).convert("RGB")

        # Resize to standard height for display
        target_h = 320
        clean_w = int(clean_img.width * (target_h / clean_img.height))
        poisoned_w = int(poisoned_img.width * (target_h / poisoned_img.height))

        clean_resized = clean_img.resize((clean_w, target_h), Image.Resampling.BILINEAR)
        poisoned_resized = poisoned_img.resize((poisoned_w, target_h), Image.Resampling.BILINEAR)

        # Compute difference map
        # Resize clean to match poisoned exactly for pixel subtraction
        clean_exact = clean_img.resize(poisoned_img.size, Image.Resampling.BILINEAR)
        diff = ImageChops.difference(poisoned_img, clean_exact)
        # Amplify difference 5x for visual clarity
        diff_arr = np.array(diff, dtype=np.float32) * 5.0
        diff_arr = np.clip(diff_arr, 0, 255).astype(np.uint8)
        diff_img = Image.fromarray(diff_arr).resize((poisoned_w, target_h), Image.Resampling.BILINEAR)

        banner_h = 40
        total_w = clean_w + poisoned_w + poisoned_w + 40
        total_h = target_h + banner_h + 30

        canvas = Image.new("RGB", (total_w, total_h), color=(24, 24, 28))
        draw = ImageDraw.Draw(canvas)
        font = self._get_font(14)

        # Title
        title = f"SentinelVision Trigger Evidence: {sample_id} (Target Class: {target_class})"
        draw.text((20, 12), title, fill=(240, 240, 240), font=font)

        # Paste panels
        x = 10
        y = banner_h + 10
        canvas.paste(clean_resized, (x, y))
        draw.text((x + 5, y - 18), "Clean Baseline", fill=(180, 180, 180), font=font)

        x += clean_w + 10
        canvas.paste(poisoned_resized, (x, y))
        draw.text((x + 5, y - 18), "Poisoned Image (Trigger)", fill=(255, 120, 120), font=font)

        x += poisoned_w + 10
        canvas.paste(diff_img, (x, y))
        draw.text((x + 5, y - 18), "Amplified Difference (5x)", fill=(255, 220, 100), font=font)

        out_path = os.path.join(self.output_dir, output_filename)
        canvas.save(out_path, "JPEG", quality=90)
        return out_path

    def render_duplicate_evidence(
        self,
        ref_img_path: str,
        dup_img_path: str,
        output_filename: str,
        ref_id: str,
        dup_id: str,
        similarity: float,
        transformation: str,
    ) -> str:
        """
        Render a 2-panel comparison of duplicate pairs:
        [ Reference Image ] [ Duplicate Image (Similarity: X) ]
        """
        ref_img = Image.open(ref_img_path).convert("RGB")
        dup_img = Image.open(dup_img_path).convert("RGB")

        target_h = 300
        ref_w = int(ref_img.width * (target_h / ref_img.height))
        dup_w = int(dup_img.width * (target_h / dup_img.height))

        ref_r = ref_img.resize((ref_w, target_h), Image.Resampling.BILINEAR)
        dup_r = dup_img.resize((dup_w, target_h), Image.Resampling.BILINEAR)

        banner_h = 45
        total_w = ref_w + dup_w + 30
        total_h = target_h + banner_h + 30

        canvas = Image.new("RGB", (total_w, total_h), color=(24, 24, 28))
        draw = ImageDraw.Draw(canvas)
        font = self._get_font(14)

        title = f"SentinelVision Duplicate Evidence: Cosine Sim = {similarity:.4f} | Transform: {transformation}"
        draw.text((20, 12), title, fill=(240, 240, 240), font=font)

        x = 10
        y = banner_h + 10
        canvas.paste(ref_r, (x, y))
        draw.text((x + 5, y - 18), f"Reference: {ref_id}", fill=(180, 180, 180), font=font)

        x += ref_w + 10
        canvas.paste(dup_r, (x, y))
        draw.text((x + 5, y - 18), f"Near-Duplicate: {dup_id}", fill=(255, 180, 80), font=font)

        out_path = os.path.join(self.output_dir, output_filename)
        canvas.save(out_path, "JPEG", quality=90)
        return out_path

    def render_ood_evidence(
        self,
        in_dist_img_paths: List[str],
        ood_img_paths: List[str],
        output_filename: str,
    ) -> str:
        """
        Render a contrastive panel of In-Distribution vs Out-Of-Distribution samples.
        """
        thumb_size = (140, 140)
        n_in = min(3, len(in_dist_img_paths))
        n_ood = min(3, len(ood_img_paths))

        canvas_w = (max(n_in, n_ood) * 150) + 30
        canvas_h = 360

        canvas = Image.new("RGB", (canvas_w, canvas_h), color=(24, 24, 28))
        draw = ImageDraw.Draw(canvas)
        font = self._get_font(14)

        draw.text((20, 12), "SentinelVision OOD Evidence: In-Distribution vs External Shift", fill=(240, 240, 240), font=font)

        # Row 1: In-distribution
        draw.text((20, 45), "In-Distribution (Clean PASCAL VOC2012):", fill=(120, 220, 120), font=font)
        for i in range(n_in):
            im = Image.open(in_dist_img_paths[i]).convert("RGB").resize(thumb_size, Image.Resampling.BILINEAR)
            canvas.paste(im, (20 + i * 150, 70))

        # Row 2: OOD
        draw.text((20, 225), "Out-Of-Distribution (Distribution Shift / External):", fill=(255, 100, 100), font=font)
        for i in range(n_ood):
            im = Image.open(ood_img_paths[i]).convert("RGB").resize(thumb_size, Image.Resampling.BILINEAR)
            canvas.paste(im, (20 + i * 150, 250))

        out_path = os.path.join(self.output_dir, output_filename)
        canvas.save(out_path, "JPEG", quality=90)
        return out_path

    def render_label_flip_evidence(
        self,
        img_path: str,
        output_filename: str,
        sample_id: str,
        original_label: str,
        modified_label: str,
        suggested_label: Optional[str] = None,
        bbox: Optional[Tuple[int, int, int, int]] = None,
    ) -> str:
        """
        Render an annotation discrepancy overlay on the image.
        """
        img = Image.open(img_path).convert("RGB")
        target_h = 340
        w = int(img.width * (target_h / img.height))
        img_r = img.resize((w, target_h), Image.Resampling.BILINEAR)

        banner_h = 50
        canvas = Image.new("RGB", (w + 20, target_h + banner_h + 20), color=(24, 24, 28))
        draw = ImageDraw.Draw(canvas)
        font = self._get_font(14)

        title = f"SentinelVision Label Anomaly: {sample_id}"
        draw.text((15, 10), title, fill=(240, 240, 240), font=font)

        sub = f"Observed Label: '{modified_label}' | Clean Ground Truth: '{original_label}'"
        if suggested_label:
            sub += f" | Cleanlab Suggested: '{suggested_label}'"
        draw.text((15, 28), sub, fill=(255, 180, 100), font=font)

        canvas.paste(img_r, (10, banner_h + 10))

        # Draw bbox if provided (rescaled)
        if bbox:
            sx = w / img.width
            sy = target_h / img.height
            b_scaled = [
                10 + int(bbox[0] * sx),
                banner_h + 10 + int(bbox[1] * sy),
                10 + int(bbox[2] * sx),
                banner_h + 10 + int(bbox[3] * sy),
            ]
            draw.rectangle(b_scaled, outline=(255, 50, 50), width=3)
            draw.text((b_scaled[0] + 5, b_scaled[1] + 5), f"{modified_label} (!)", fill=(255, 50, 50), font=font)

        out_path = os.path.join(self.output_dir, output_filename)
        canvas.save(out_path, "JPEG", quality=90)
        return out_path

import json
import os
import xml.etree.ElementTree as ET
from collections import defaultdict, Counter

prov_path = "datasets/sentinelvision_voc2012/metadata/provenance.json"
voc_dir = "datasets/sentinelvision_voc2012/raw/VOCdevkit/VOC2012"

with open(prov_path) as f:
    prov = json.load(f)["provenance_records"]

with open(os.path.join(voc_dir, "ImageSets/Main/val.txt")) as f:
    val_ids = [line.strip() for line in f if line.strip()][:300]

contrib_classes = defaultdict(Counter)
for sid in val_ids:
    c = prov.get(f"voc2012_{sid}", {}).get("contributor_id", "unknown")
    xml = os.path.join(voc_dir, "Annotations", f"{sid}.xml")
    for obj in ET.parse(xml).findall("object"):
        contrib_classes[c][obj.find("name").text] += 1

print("--- Classes per contributor in first 300 val samples ---")
for c, counts in sorted(contrib_classes.items()):
    print(c, counts.most_common(5))

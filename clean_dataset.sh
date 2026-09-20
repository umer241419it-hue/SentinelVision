#!/bin/bash
# clean_dataset.sh
#
# RUN THIS YOURSELF IN YOUR WSL TERMINAL. Do NOT paste its contents to any AI
# agent, and do NOT point any AI agent at your raw/extracted archive folder.
#
# Usage:
#   chmod +x clean_dataset.sh
#   ./clean_dataset.sh /path/to/raw/extracted/models /path/to/project/data/trojai_sample
#
# Example (adjust to your actual extraction location):
#   ./clean_dataset.sh /mnt/c/Users/you/Downloads/trojai_extracted \
#                       ~/projects/SentinelVision/model-integrity/data/trojai_sample

set -euo pipefail

SRC="${1:?Usage: ./clean_dataset.sh <raw_extracted_dir> <dest_dir>}"
DEST="${2:?Usage: ./clean_dataset.sh <raw_extracted_dir> <dest_dir>}"

MODEL_IDS=(
  id-00000028 id-00000112 id-00000173 id-00000278 id-00000431
  id-00000449 id-00000594 id-00000621 id-00000637 id-00000658
  id-00000664 id-00000728 id-00000838 id-00000905 id-00000912
)

mkdir -p "$DEST"

for id in "${MODEL_IDS[@]}"; do
  SRC_MODEL_DIR="$SRC/$id"
  if [ ! -d "$SRC_MODEL_DIR" ]; then
    echo "WARNING: $SRC_MODEL_DIR not found, skipping"
    continue
  fi

  DEST_MODEL_DIR="$DEST/$id"
  mkdir -p "$DEST_MODEL_DIR/example_data"

  # Copy ONLY the model weights
  cp "$SRC_MODEL_DIR/model.pt" "$DEST_MODEL_DIR/"

  # Handle either naming (official NIST name is "example_data";
  # some re-uploaded copies use "clean-example-data" instead)
  if [ -d "$SRC_MODEL_DIR/example_data" ]; then
    EX_DIR="$SRC_MODEL_DIR/example_data"
  elif [ -d "$SRC_MODEL_DIR/clean-example-data" ]; then
    EX_DIR="$SRC_MODEL_DIR/clean-example-data"
  elif [ -d "$SRC_MODEL_DIR/example_images" ]; then
    EX_DIR="$SRC_MODEL_DIR/example_images"
  elif [ -d "$SRC_MODEL_DIR/example-data" ]; then
    EX_DIR="$SRC_MODEL_DIR/example-data"
  else
    echo "WARNING: no example-data folder found for $id"
    EX_DIR=""
  fi

  if [ -n "$EX_DIR" ]; then
    cp -r "$EX_DIR"/* "$DEST_MODEL_DIR/example_data/"
  fi

  echo "Cleaned $id -> $DEST_MODEL_DIR (model.pt + example_data only)"
done

echo ""
echo "=== Checking every model actually got its example images ==="
EMPTY_FOUND=0
for id in "${MODEL_IDS[@]}"; do
  DEST_MODEL_DIR="$DEST/$id"
  if [ -d "$DEST_MODEL_DIR/example_data" ]; then
    COUNT=$(find "$DEST_MODEL_DIR/example_data" -type f | wc -l)
    if [ "$COUNT" -eq 0 ]; then
      echo "EMPTY: $id/example_data has 0 files"
      EMPTY_FOUND=1
    fi
  fi
done
if [ "$EMPTY_FOUND" -eq 1 ]; then
  echo "Fix the folder-name matching above and re-run before proceeding."
  exit 1
else
  echo "All model folders have example images present."
fi

echo ""
echo "=== Leak check on $DEST ==="
LEAKS=$(find "$DEST" -iname "ground_truth.csv" -o -iname "triggers" -o -iname "METADATA*.csv" \
                     -o -iname "config.json" -o -iname "reduced-config.json" \
                     -o -iname "example-accuracy.csv" -o -iname "model_stats.json" \
                     -o -iname "model_detailed_stats.csv" -o -iname "foregrounds")
if [ -n "$LEAKS" ]; then
  echo "LEAK DETECTED — these should NOT be here, delete them before showing this folder to any agent:"
  echo "$LEAKS"
  exit 1
else
  echo "Clean. No ground-truth or trigger artifacts found in $DEST."
fi

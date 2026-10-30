#!/usr/bin/env bash
# Downloads the free Kokoro voice model (about 350 MB) into ./models
set -euo pipefail
mkdir -p models
base=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
for f in kokoro-v1.0.onnx voices-v1.0.bin; do
  [ -s "models/$f" ] || curl -fsSL -o "models/$f" "$base/$f"
done

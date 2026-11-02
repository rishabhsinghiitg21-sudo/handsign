#!/usr/bin/env bash
# Download the two MediaPipe model bundles handsign needs into data/.
# Both come from Google's official MediaPipe model storage (Apache-2.0).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="$HERE/data"
BASE="https://storage.googleapis.com/mediapipe-models"
mkdir -p "$DATA"

fetch() {  # name url
  local out="$DATA/$1.task"
  if [ -s "$out" ]; then echo "have   $1.task"; return; fi
  echo "fetch  $1.task"
  curl -fL --progress-bar -o "$out.part" "$2"
  mv "$out.part" "$out"
}

fetch hand_landmarker "$BASE/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
fetch face_landmarker "$BASE/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
echo "models ready in $DATA"

#!/usr/bin/env bash
# Pipeline: trimmed mp4 -> Annex B h264 -> databend -> playable mp4
# Usage: ./make_hero.sh [ops] [max_chunk] [seed] [out_suffix]
set -euo pipefail
cd "$(dirname "$0")"

OPS="${1:-40}"
MAX_CHUNK="${2:-4096}"
SEED="${3:-}"
SUFFIX="${4:-v1}"

SRC="flag_source.mp4"
RAW="flag.h264"
CORRUPT="flag_corrupt.h264"
OUT="flag_${SUFFIX}.mp4"
OUT_WEBM="flag_${SUFFIX}.webm"

if [ ! -f "$SRC" ]; then
  echo "missing $SRC -- run the trim step first" >&2
  exit 1
fi

# 1. Demux to Annex B elementary stream
ffmpeg -y -hide_banner -loglevel error -i "$SRC" \
  -c:v copy -bsf:v h264_mp4toannexb -f h264 "$RAW"

# 2. Corrupt
SEED_ARG=""
if [ -n "$SEED" ]; then SEED_ARG="--seed $SEED"; fi
python3 databend.py "$RAW" "$CORRUPT" --ops "$OPS" --max-chunk "$MAX_CHUNK" $SEED_ARG

# 3. Re-mux. Tell ffmpeg the framerate explicitly since the raw stream lost it.
ffmpeg -y -hide_banner -loglevel error -r 30000/1001 -i "$CORRUPT" \
  -c:v copy -movflags +faststart "$OUT"

# 4. Also encode a webm for site delivery (smaller, broader browser support)
ffmpeg -y -hide_banner -loglevel error -r 30000/1001 -i "$CORRUPT" \
  -c:v libvpx-vp9 -b:v 1500k -crf 30 -row-mt 1 -threads 4 \
  -movflags +faststart "$OUT_WEBM" 2>/dev/null || echo "webm encode skipped"

ls -la "$OUT" "$OUT_WEBM" 2>/dev/null || ls -la "$OUT"
echo
echo "Done. Open: $OUT"

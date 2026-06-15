#!/usr/bin/env bash
#
# wan_smooth.sh — smooth Wan-generated video by motion-interpolating to 60fps.
#
# WHY: Wan clips render at 30fps but their motion often advances in a ~5-frame
# "beat" (it holds, then lurches), which reads as judder — especially on slow
# shots. Motion-compensated interpolation to 60fps (ffmpeg minterpolate) inserts
# real in-between frames and evens this out. These exact settings are the ones we
# A/B-tested and preferred over Topaz's built-in interpolation for this footage.
#
# WHAT IT DOES NOT DO: it can't remove the beat that's truly baked into the
# source motion — that needs a re-roll of the Wan shot. This makes the motion as
# smooth as post-processing can. Upscaling is a SEPARATE step (we use Topaz);
# run this on the clean 1080p originals first, upscale last.
#
# USAGE:
#   ./wan_smooth.sh clip1.mp4 clip2.mp4 ...      # specific files
#   ./wan_smooth.sh /path/to/originals/*.mp4     # a glob
#   ./wan_smooth.sh -o out_dir *.mp4             # choose output dir
#   ./wan_smooth.sh --fps 60 --crf 16 *.mp4      # tune
#
# OPTIONS:
#   -o, --outdir DIR   output directory (default: alongside each input)
#       --fps N        target fps (default: 60)
#       --crf N        x264 quality, lower=better/bigger (default: 16, visually lossless)
#       --preset P     x264 speed/size preset (default: medium)
#       --suffix S     output filename suffix (default: _60fps)
#       --force        overwrite existing outputs
#   -h, --help         show this help
#
# REQUIREMENTS: ffmpeg (with libx264). Check: ffmpeg -version
#
set -euo pipefail

FPS=60
CRF=16
PRESET=medium
SUFFIX=_60fps
OUTDIR=""
FORCE=0

usage() { sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

FILES=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--outdir) OUTDIR="$2"; shift 2;;
    --fps)       FPS="$2"; shift 2;;
    --crf)       CRF="$2"; shift 2;;
    --preset)    PRESET="$2"; shift 2;;
    --suffix)    SUFFIX="$2"; shift 2;;
    --force)     FORCE=1; shift;;
    -h|--help)   usage 0;;
    -*)          echo "Unknown option: $1" >&2; usage 1;;
    *)           FILES+=("$1"); shift;;
  esac
done

command -v ffmpeg >/dev/null 2>&1 || { echo "ERROR: ffmpeg not found in PATH" >&2; exit 1; }
[[ ${#FILES[@]} -eq 0 ]] && { echo "ERROR: no input files given" >&2; usage 1; }
[[ -n "$OUTDIR" ]] && mkdir -p "$OUTDIR"

# Motion-compensated interpolation. These flags matter:
#   mi_mode=mci      motion-compensated (not blend/dup)
#   mc_mode=aobmc    adaptive overlapped block MC — fewer artifacts on edges
#   me_mode=bidir    bidirectional motion estimation
#   vsbmc=1          variable-size blocks — better around moving detail
VF="minterpolate=fps=${FPS}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"

ok=0; total=${#FILES[@]}
echo "=== wan_smooth: ${total} file(s) -> ${FPS}fps (crf ${CRF}, preset ${PRESET}) ==="
for src in "${FILES[@]}"; do
  if [[ ! -f "$src" ]]; then echo "[skip] not found: $src" >&2; continue; fi
  dir="$(dirname "$src")"; base="$(basename "$src")"; stem="${base%.*}"
  destdir="${OUTDIR:-$dir}"
  out="${destdir}/${stem}${SUFFIX}.mp4"

  if [[ -f "$out" && $FORCE -eq 0 ]]; then
    echo "[exists] ${out}  (use --force to overwrite)"; ok=$((ok+1)); continue
  fi

  echo "[smooth] ${base} -> ${out}"
  # -c:a copy passes through audio if present (Wan clips are usually silent — harmless).
  if ffmpeg -y -loglevel error -stats -i "$src" \
       -vf "$VF" \
       -c:v libx264 -preset "$PRESET" -crf "$CRF" -pix_fmt yuv420p \
       -c:a copy \
       "$out" 2>&1; then
    ok=$((ok+1))
  else
    # retry without audio mapping in case -c:a copy failed (no/odd audio stream)
    ffmpeg -y -loglevel error -stats -i "$src" -an \
      -vf "$VF" -c:v libx264 -preset "$PRESET" -crf "$CRF" -pix_fmt yuv420p "$out" \
      && ok=$((ok+1)) || echo "[error] failed: $src" >&2
  fi
  echo
done

echo "=== done: ${ok}/${total} ==="

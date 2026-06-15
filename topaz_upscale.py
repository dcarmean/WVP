#!/usr/bin/env python3
"""
Topaz video upscale + (optional) frame interpolation via fal.ai.

Runs Topaz Video Upscale on fal.ai's GPUs. With --fps set, Topaz also does
motion-compensated frame interpolation in the SAME pass (its Apollo/Chronos-class
interpolator), so you get a smooth, upscaled clip from one call.

IMPORTANT — workflow lessons from this project:
  1. Always feed the CLEAN source (raw Wan 1080p/30fps clip), NOT an already-
     processed file. Do interpolation (--fps) and upscale together here. Never let
     a separate slow-mo / "duplicate frames" step touch the clip first — that
     duplication is what made the motion juddery in the first place.
  2. If the source has a stutter / low-fps "motion beat" (Wan often does: ~5-frame
     holds), do NOT interpolate up (--fps 60). Interpolation STRETCHES each hold
     into a longer freeze and makes the stutter worse. Keep --fps 0 (native rate)
     for beat-y sources; only interpolate sources with genuinely smooth motion.

Usage:
  python3 topaz_upscale.py INPUT.mp4                       # 2x upscale, 60fps interp, H264
  python3 topaz_upscale.py INPUT.mp4 --upscale 2 --fps 60
  python3 topaz_upscale.py INPUT.mp4 --fps 0               # upscale only, keep source fps
  python3 topaz_upscale.py INPUT.mp4 --model "Starlight Precise 2.5" --fps 0
  python3 topaz_upscale.py a.mp4 b.mp4 c.mp4               # batch
  python3 topaz_upscale.py --resume <REQUEST_ID> --out OUT.mp4   # reconnect to a job

FAL_KEY is read from $FAL_KEY, then ~/.bashrc, then ~/puhniatko/.env.

Jobs use fal_client.submit() and print a recoverable request_id + elapsed-time
heartbeat. Slow models (Starlight) emit no per-frame logs and can take 15-40 min;
if the client dies, resume with --resume <REQUEST_ID> --out FILE.

Topaz models (fal `model` param): Proteus (default, general); Artemis HQ/MQ/LQ;
  Gaia HQ/CG, Gaia 2 (animation/motion-graphics); Nyx/Nyx Fast/XL/HF (denoise);
  Starlight Precise 1/2/2.5, Starlight HQ/Mini/Sharp, Starlight Fast 1/2
  (generative diffusion — best for AI-generated footage, slow + pricey).
"""

import argparse
import os
import sys
import time
import urllib.request
from pathlib import Path

import fal_client

ENDPOINT = "fal-ai/topaz/upscale/video"


def resolve_fal_key():
    """FAL_KEY from env, then ~/.bashrc export line, then ~/puhniatko/.env."""
    key = os.environ.get("FAL_KEY")
    if key:
        return key
    bashrc = Path.home() / ".bashrc"
    if bashrc.exists():
        for line in bashrc.read_text().splitlines():
            line = line.strip()
            if line.startswith("export FAL_KEY=") or line.startswith("FAL_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    env_file = Path.home() / "puhniatko" / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.strip().startswith("FAL_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _download(result, out: Path):
    url = result["video"]["url"]
    size = result["video"].get("file_size")
    print(f"  download ({size} bytes)...", end=" ", flush=True)
    urllib.request.urlretrieve(url, str(out))
    print(f"saved -> {out}")


def _wait_and_fetch(request_id: str, out: Path) -> bool:
    """Poll FAL for a submitted request, print a heartbeat + any logs, then download.

    Slow models like Starlight emit no incremental logs, so we also print an
    elapsed-time heartbeat to show the client is alive and polling.
    """
    print(f"  request_id: {request_id}")
    print(f"  (resume later with: --resume {request_id} --out '{out}')", flush=True)
    start = time.monotonic()
    seen = 0
    while True:
        status = fal_client.status(ENDPOINT, request_id, with_logs=True)
        logs = getattr(status, "logs", None) or []
        for log in logs[seen:]:
            print(f"    {log.get('message', '')}", flush=True)
        seen = len(logs)
        if isinstance(status, fal_client.Completed):
            break
        elapsed = int(time.monotonic() - start)
        state = type(status).__name__
        print(f"  [{elapsed//60}m{elapsed%60:02d}s] {state}, polling...", flush=True)
        time.sleep(15)
    result = fal_client.result(ENDPOINT, request_id)
    _download(result, out)
    return True


def upscale_one(src: Path, args) -> bool:
    out = Path(args.out) if args.out else src.with_name(f"{src.stem}_topaz{src.suffix}")
    if out.exists() and not args.force:
        print(f"[exists] {out.name} (use --force to overwrite)")
        return True

    print(f"[topaz] {src.name}")
    print(f"  upload...", end=" ", flush=True)
    video_url = fal_client.upload_file(str(src))
    print("done")

    arguments = {
        "video_url": video_url,
        "upscale_factor": args.upscale,
        "model": args.model,
        "H264_output": not args.h265,
    }
    if args.fps and args.fps > 0:
        arguments["target_fps"] = args.fps  # enables frame interpolation

    print(f"  model={args.model}  upscale={args.upscale}x  "
          f"target_fps={arguments.get('target_fps', 'source')}  "
          f"codec={'H265' if args.h265 else 'H264'}")

    # submit() (not subscribe) so we get a recoverable request_id up front:
    # if this client dies, the job keeps running on fal and can be resumed.
    handler = fal_client.submit(ENDPOINT, arguments=arguments)
    return _wait_and_fetch(handler.request_id, out)


def main():
    p = argparse.ArgumentParser(description="Topaz video upscale + interpolation via fal.ai")
    p.add_argument("inputs", nargs="*", help="input video file(s)")
    p.add_argument("--resume", default=None, metavar="REQUEST_ID",
                   help="reconnect to an in-flight/finished fal job by request id (use with --out)")
    p.add_argument("--upscale", type=float, default=2.0, help="upscale factor (default 2.0)")
    p.add_argument("--fps", type=int, default=60,
                   help="target fps; enables Topaz frame interpolation. 0 = keep source fps (default 60)")
    p.add_argument("--model", default="Proteus", help="Topaz model (default Proteus)")
    p.add_argument("--out", default=None, help="output path (single input only; default <name>_topaz.mp4)")
    p.add_argument("--h265", action="store_true", help="output H265 instead of H264")
    p.add_argument("--force", action="store_true", help="overwrite existing outputs")
    args = p.parse_args()

    key = resolve_fal_key()
    if not key:
        print("ERROR: FAL_KEY not found (env / ~/.bashrc / ~/puhniatko/.env)")
        sys.exit(1)
    os.environ["FAL_KEY"] = key

    if args.resume:
        if not args.out:
            print("ERROR: --resume requires --out (where to save the result)")
            sys.exit(1)
        print(f"=== Resuming fal job {args.resume} ===")
        _wait_and_fetch(args.resume, Path(args.out))
        return

    if not args.inputs:
        print("ERROR: provide input video(s), or use --resume REQUEST_ID --out FILE")
        sys.exit(1)

    if args.out and len(args.inputs) > 1:
        print("ERROR: --out only valid with a single input")
        sys.exit(1)

    srcs = [Path(s) for s in args.inputs]
    missing = [s for s in srcs if not s.exists()]
    if missing:
        print("ERROR: not found: " + ", ".join(str(m) for m in missing))
        sys.exit(1)

    print(f"=== Topaz upscale via fal ({ENDPOINT}) ===")
    ok = 0
    for src in srcs:
        try:
            if upscale_one(src, args):
                ok += 1
        except Exception as e:
            print(f"  ERROR: {e}")
        print()
    print(f"=== Done: {ok}/{len(srcs)} ===")


if __name__ == "__main__":
    main()

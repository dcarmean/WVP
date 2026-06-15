# WVP — Wan Video Pipeline

Tools for turning raw [Wan](https://github.com/Wan-Video) text/image-to-video
clips into smooth, upscaled deliverables.

Two stages, run in this order:

1. **`wan_smooth.sh`** — motion-interpolate 30fps → 60fps to remove judder (ffmpeg, local)
2. **`topaz_upscale.py`** — upscale to 4K via Topaz on [fal.ai](https://fal.ai) (GPU, paid API)

> Always run on the **clean Wan original**. Smooth first, upscale last. Don't
> upscale before smoothing — interpolating 4K is far slower for the same result,
> and never let a separate slow-mo/"duplicate frames" step touch the clip (that
> duplication is what makes Wan output look juddery in the first place).

---

## Why Wan clips judder

Wan renders at 30fps, but its motion often advances in a ~5-frame "beat": the
image holds nearly still for a few frames, then lurches. On slow shots this reads
as stutter. Motion-compensated interpolation to 60fps synthesizes real in-between
frames and evens it out.

We A/B-tested several interpolators; **ffmpeg's `minterpolate`** (the settings in
`wan_smooth.sh`) gave the smoothest result for this footage — notably better than
Topaz's *built-in* frame interpolation, which amplified the beat into longer
freezes. So: smooth with ffmpeg, then use Topaz only for spatial upscaling.

**Limit:** interpolation can't remove a beat that's truly baked into the source
motion — only re-generating the Wan shot fixes that. These tools get the motion
as smooth as post-processing allows.

---

## 1. `wan_smooth.sh` (ffmpeg, local)

```bash
./wan_smooth.sh "08 Wan_Original.mp4"            # one file
./wan_smooth.sh -o smoothed/ originals/*.mp4     # batch into an output dir
./wan_smooth.sh --crf 16 --preset slow *.mp4     # tune quality
./wan_smooth.sh --help                           # all options
```

Output: `<name>_60fps.mp4`. Skips existing outputs unless `--force`.

**Requirements:** `ffmpeg` with `libx264`. CPU-heavy: ~1 min per 10s clip at
1080p (run at 1080p, upscale after).

## 2. `topaz_upscale.py` (Topaz via fal.ai)

```bash
pip install fal-client
export FAL_KEY="your-fal-key"                     # get one at https://fal.ai

# 2x upscale, keep source fps (recommended for Wan — see note below)
python3 topaz_upscale.py "08 Wan_Original_60fps.mp4" --upscale 2 --fps 0

# batch
python3 topaz_upscale.py *_60fps.mp4 --upscale 2 --fps 0

# reconnect to a long/dropped job
python3 topaz_upscale.py --resume <REQUEST_ID> --out OUT.mp4
```

`FAL_KEY` is read from `$FAL_KEY`, then `~/.bashrc`, then `~/puhniatko/.env`.

**Notes**
- Topaz's `target_fps` (our `--fps`) enables *its* frame interpolation. On a
  beat-y Wan source, leave it off (`--fps 0`) and let `wan_smooth.sh` do the
  interpolation — Topaz's interpolator worsens the beat on this footage.
- Models: `Proteus` (default, general), `Gaia 2` (animation/motion-graphics),
  `Starlight Precise 2.5` etc. (generative diffusion — best detail for AI footage,
  but slow: 15–40 min for a 10s clip, and pricier).
- Slow jobs print a recoverable `request_id` + heartbeat; resume with `--resume`.

---

## Recommended full run

```bash
# 1) smooth all originals (local, fast)
./wan_smooth.sh -o smoothed/ originals/*.mp4

# 2) upscale the smoothed clips to 4K (fal, paid)
python3 topaz_upscale.py smoothed/*_60fps.mp4 --upscale 2 --fps 0
```

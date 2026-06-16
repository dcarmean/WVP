# Wan motion judder — findings & corrected generation settings

## Summary

Wan-generated clips judder because of **how Wan generates motion**, not because of
anything fixable in post:

- **Wan renders natively at 16fps** — choppy by design. The intended workflow is
  *generate at 16fps, then interpolate up* (RIFE/FILM). Interpolation fixes the frame
  *rate*, but it **cannot fix motion the model generated badly**.
- **Wan 2.2 has a well-documented "slow / sluggish / bad motion" problem.** It is
  overwhelmingly **settings-driven**, not a hard model limitation — wrong FPS, high
  motion blur, speed-up LoRAs, low resolution, and low CFG all degrade motion.

**Consequence:** post-processing (decimate, RIFE, Topaz) has a ceiling. We hit it.
For a clip that's already generated badly, the best post result (clean 60fps
interpolation, no aggressive decimation) is as good as it gets. **The real fix is
upstream — regenerate with the settings below.** Regenerating with the *same* settings
reproduces the judder; regenerating *corrected* does not.

## Corrected Wan generation settings

| Setting | Bad (causes judder/slow-mo) | Use instead |
|---|---|---|
| **Generation FPS** | 6–8 fps (preview default left on) | **24 fps** native (16 min) |
| **Motion blur** | 0.5–1.0 (floaty "molasses" motion) | **0.2–0.3** |
| **Speed-up LoRAs** | Lightning / distilled 4-step (top cause of bad motion) | **Avoid.** If needed, low-noise only — never high-noise |
| **Resolution** | 832×480 (judders / slows) | **1280×720+** (720p generates normal motion) |
| **Sampler / steps** | 4-step speed configs | **DPM++ 2M Karras, 25–30 steps** for full motion quality |
| **CFG** | Too low → temporal over-smoothing | Keep meaningful CFG; raise it at higher res |
| **Motion guidance** | High → over-damps fast motion | **1.0–1.2** |
| **Prompt** | No speed words | Add speed/energy descriptors: "walks briskly", "quick", "energetic" |

Wan was trained on smooth cinematic footage, so it **defaults to slow, deliberate
motion** unless you explicitly push it faster via the settings and prompt above.

## Post pipeline (after a clean generation)

1. `wan_smooth.sh` — interpolate 16/24fps → 60fps (RIFE-class) to remove residual choppiness.
2. `topaz_upscale.py` — upscale to 4K **last**, spatial only, no fps change.

Do NOT decimate "held" frames on Wan footage: the low-motion frames are usually real
slow motion, not duplicates — dropping them removes real content and the interpolator
fabricates replacements (looks worse, not better).

## If Wan's motion still isn't good enough

Try a different model for the shot — **Kling** has notably more natural native motion
than Wan and is already wired into the puhniatko pipeline.

## Sources

- Apatero — Fix Slow Motion in WAN 2.2: https://www.apatero.com/blog/avoid-slow-motion-wan-22-video-generation-2025
- Apatero — Wan 2.2 tips: https://apatero.com/blog/wan-22-hidden-features-tips-guide-2025
- Promptus — Wan video guide (16fps native + interpolate): https://www.promptus.ai/blog/wan21-model-video-guide
- lightx2v Wan2.2-Lightning — slow motion / bad motion (speed-LoRA cause): https://huggingface.co/lightx2v/Wan2.2-Lightning/discussions/20

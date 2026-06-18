#!/usr/bin/env python3
"""
Batch Kling video-to-video over the CPR story lines tree.

For each source .mp4 it produces TWO takes (independent rolls of the same prompt)
into two parallel output roots that mirror the folder structure and filenames:
  CPR story lines (v2v take 1)/<same relpath>
  CPR story lines (v2v take 2)/<same relpath>

Prompt for each clip is derived from its filename (Wan filenames embed the original
generation prompt); unparseable names fall back to a neutral preserve+smooth prompt.

State/restart: progress is written to "CPR story lines/_v2v_state.json" and a job is
skipped if its output file already exists. Safe to Ctrl-C and re-run — it resumes.

Usage:
  python3 v2v_batch.py --dry-run                 # print derived prompts for ALL clips, no API
  python3 v2v_batch.py --limit 3                 # process first 3 clips (x2 takes = 6 jobs)
  python3 v2v_batch.py --only "Cube Hunters Foraging"   # only clips whose relpath contains this
  python3 v2v_batch.py --all                     # everything (172 jobs)
  python3 v2v_batch.py --workers 4               # concurrency (default 4)
"""
import argparse, json, os, re, subprocess, sys, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import fal_client
import requests

TRIM_DIR = Path("/tmp/v2v_trim")
MAX_DUR = 10.05
_trim_lock = threading.Lock()

PROJ = Path("/home/doug_/susan-exhibition")
SRC_ROOT = PROJ / "CPR story lines"
OUT_ROOTS = {1: PROJ / "CPR story lines (v2v take 1)", 2: PROJ / "CPR story lines (v2v take 2)"}
STATE_FILE = SRC_ROOT / "_v2v_state.json"
ENDPOINT = "fal-ai/kling-video/o1/video-to-video/edit"
SUFFIX = "  Keep characters, objects, props and visual style consistent across all frames; smooth, natural, continuous motion."
NEUTRAL = "Preserve the scene, composition, characters and visual style exactly." + SUFFIX

_state_lock = threading.Lock()
_upload_lock = threading.Lock()
_upload_cache = {}

def resolve_fal_key():
    k = os.environ.get("FAL_KEY")
    if k: return k
    for p in [Path.home()/".bashrc", Path.home()/"puhniatko"/".env"]:
        if p.exists():
            for line in p.read_text().splitlines():
                s = line.strip()
                if s.startswith("export FAL_KEY=") or s.startswith("FAL_KEY="):
                    return s.split("=", 1)[1].strip().strip('"').strip("'")
    return None

def prompt_from_filename(fn: str) -> str:
    s = Path(fn).stem
    s = re.split(r'\s*--\w+', s)[0]                       # drop midjourney params (--ar ...)
    s = re.sub(r'^\d+\s+', '', s)                          # leading "05 "
    s = re.sub(r'(?i)wan[_ ]video[_ ]generate[_ ]', '', s)
    s = re.sub(r'(?i)^social_ssnrbb_', '', s)
    s = re.sub(r'(?i)^ssnrbb_', '', s)
    s = re.sub(r'(?i)_?ast2_c3s3', '', s)
    s = re.sub(r'_[0-9a-f]{8}-[0-9a-f-]{12,}.*$', '', s)   # trailing uuid + anything after
    s = re.sub(r'_\d+$', '', s)                            # trailing _3 index
    s = re.sub(r'[-_ ]?\d{6,}.*$', '', s)                  # trailing datestamp 202605312116
    s = s.replace('_', ' ').strip()
    s = re.sub(r'(?i)\bhttpss?\.?mj\.run\S*\s*', '', s)   # midjourney url fragments
    s = re.sub(r'\d{4}-\d{2}-\d{2}', '', s)                # ISO dates
    s = re.sub(r'\s+', ' ', s).strip(' -')
    letters = re.sub(r'[^A-Za-z]', '', s)
    if len(s) < 12 or len(letters) < 8 or re.search(r'(?i)^(untitled|initial) scene|^drawing\b', s):
        return NEUTRAL
    return s + SUFFIX

def load_state():
    if STATE_FILE.exists():
        try: return json.loads(STATE_FILE.read_text())
        except Exception: return {}
    return {}

def save_state(state):
    with _state_lock:
        STATE_FILE.write_text(json.dumps(state, indent=2))

MIN_H = 720

def probe(p: Path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "format=duration:stream=height", "-of", "csv=p=0:s=,",
                          str(p)], capture_output=True, text=True).stdout.split()
    dur = h = 0.0
    for tok in " ".join(out).replace(",", " ").split():
        try:
            v = float(tok)
            if v > 200: h = v          # height (pixels)
            else: dur = v              # duration (seconds)
        except Exception: pass
    return dur, int(h)

def prepared_source(rel: str) -> Path:
    """Original, or a fixed copy: trimmed to 10s if too long, upscaled to 720px if too short.
    Kling v2v requires duration <= 10.05s and height >= 720px."""
    src = SRC_ROOT / rel
    dur, h = probe(src)
    need_trim = dur > MAX_DUR
    need_scale = 0 < h < MIN_H
    if not need_trim and not need_scale:
        return src
    TRIM_DIR.mkdir(parents=True, exist_ok=True)
    tp = TRIM_DIR / (re.sub(r'[^A-Za-z0-9]+', '_', rel)[-90:] + ".mp4")
    with _trim_lock:
        if not (tp.exists() and tp.stat().st_size > 1000):
            vf = "scale=-2:720:flags=lanczos,format=yuv420p" if need_scale else "format=yuv420p"
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src)]
            if need_trim: cmd += ["-t", "10"]
            cmd += ["-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "16",
                    "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(tp)]
            subprocess.run(cmd, check=True)
    return tp

def upload_once(path: Path) -> str:
    with _upload_lock:
        if str(path) in _upload_cache:
            return _upload_cache[str(path)]
    url = fal_client.upload_file(str(path))
    with _upload_lock:
        _upload_cache[str(path)] = url
    return url

def run_job(job, state):
    rel, take, prompt = job["rel"], job["take"], job["prompt"]
    key = f"{rel}|take{take}"
    out = OUT_ROOTS[take] / rel
    if out.exists() and out.stat().st_size > 1000:
        return (key, "skip(exists)")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        vurl = upload_once(prepared_source(rel))
        res = fal_client.subscribe(ENDPOINT, arguments={"prompt": prompt, "video_url": vurl})
        url = res["video"]["url"]
        expected = (res.get("video") or {}).get("file_size")
        data = requests.get(url, timeout=600).content          # buffer fully (urlretrieve truncates fal CDN)
        if expected and len(data) < expected * 0.99:
            raise RuntimeError(f"short download {len(data)}/{expected} bytes")
        tmp = out.with_suffix(out.suffix + ".part")
        tmp.write_bytes(data)
        tmp.rename(out)                                          # atomic: no half-written .mp4 looks "done"
        with _state_lock:
            state[key] = {"status": "done", "prompt": prompt, "out": str(out), "url": url}
        save_state(state)
        return (key, "done")
    except Exception as e:
        with _state_lock:
            state[key] = {"status": "error", "prompt": prompt, "error": str(e)}
        save_state(state)
        return (key, f"ERROR: {e}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default=None, help="substring filter on relpath")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    clips = sorted(p.relative_to(SRC_ROOT).as_posix() for p in SRC_ROOT.rglob("*.mp4"))
    if args.only:
        clips = [c for c in clips if args.only.lower() in c.lower()]
    if args.limit:
        clips = clips[:args.limit]

    if args.dry_run:
        print(f"=== {len(clips)} clips — derived prompts ===")
        for c in clips:
            print(f"\n[{c}]\n  -> {prompt_from_filename(c)}")
        return

    key = resolve_fal_key()
    if not key: sys.exit("ERROR: FAL_KEY not found")
    os.environ["FAL_KEY"] = key

    state = load_state()
    jobs = []
    for c in clips:
        p = prompt_from_filename(c)
        for take in (1, 2):
            jobs.append({"rel": c, "take": take, "prompt": p})

    todo = [j for j in jobs if not ((OUT_ROOTS[j["take"]]/j["rel"]).exists()
                                    and (OUT_ROOTS[j["take"]]/j["rel"]).stat().st_size > 1000)]
    print(f"=== v2v batch: {len(clips)} clips, {len(jobs)} jobs, {len(todo)} to run "
          f"({len(jobs)-len(todo)} already done), {args.workers}-wide ===", flush=True)

    done = err = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_job, j, state): j for j in todo}
        for i, f in enumerate(as_completed(futs), 1):
            k, status = f.result()
            if status.startswith("ERROR"): err += 1
            elif status == "done": done += 1
            print(f"[{i}/{len(todo)}] {k}  {status}", flush=True)
    print(f"=== finished: {done} done, {err} errors, run again to resume any failures ===")

if __name__ == "__main__":
    main()

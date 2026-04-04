#!/usr/bin/env python3
"""
Gemini Batch Image Generator
Super-fast batch image generation using Google Gemini 2.5 Flash Image API.

Usage:
    python gemini_batch_images.py --in prompts.json --out ./out --concurrency 8 --prefix scene_

prompts.json format:
    { "prompts": ["prompt 1", "prompt 2", ...] }

Output:
    {out}/{prefix}{index:03d}.png  (1920x1080, upscaled from 1344x768)
"""

import os
import sys
import json
import time
import random
import asyncio
import argparse
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

try:
    from google import genai
    from google.genai import types
except ImportError:
    print("ERROR: google-genai package not installed. Run: pip install google-genai")
    sys.exit(1)

try:
    from PIL import Image
    import io
except ImportError:
    print("ERROR: Pillow not installed. Run: pip install Pillow")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
MODEL_ID = "imagen-3.0-generate-002"          # Imagen 3 (primary); fallback: gemini-2.0-flash-exp-image-generation
TARGET_ASPECT = "16:9"
NATIVE_W, NATIVE_H = 1344, 768          # what the model actually returns
OUTPUT_W, OUTPUT_H = 1920, 1080         # target resolution

MAX_RETRIES = 4
INITIAL_BACKOFF = 2.0                   # seconds

CINEMATIC_WRAPPER = (
    "Create a cinematic 16:9 widescreen frame. 1080p target (upscale OK). "
    "{prompt}. "
    "Style: sharp focus, realistic lighting, high detail, no text, no watermark, no logos."
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("gemini_batch")


# ─────────────────────────────────────────────────────────────────────────────
# Core image generation (blocking)
# ─────────────────────────────────────────────────────────────────────────────

def _generate_one_blocking(client: "genai.Client", prompt: str, out_path: Path) -> float:
    """
    Generate a single image synchronously.
    Returns elapsed time in seconds.
    Raises on failure (caller handles retries).
    """
    t0 = time.monotonic()

    wrapped_prompt = CINEMATIC_WRAPPER.format(prompt=prompt)

    # Primary: Imagen 3 via generate_images()
    image_bytes = None
    try:
        response = client.models.generate_images(
            model="imagen-3.0-generate-002",
            prompt=wrapped_prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="16:9",
            ),
        )
        for generated_image in response.generated_images:
            image_bytes = generated_image.image.image_bytes
            break
    except Exception:
        # Fallback: Gemini 2.0 Flash native image generation
        response = client.models.generate_content(
            model="gemini-2.0-flash-exp-image-generation",
            contents=[wrapped_prompt],
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )
        for candidate in response.candidates:
            for part in candidate.content.parts:
                if hasattr(part, "inline_data") and part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    break
            if image_bytes:
                break

    if not image_bytes:
        raise ValueError("No image data in Gemini response")

    # Open image and upscale to 1920×1080
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    if img.size != (OUTPUT_W, OUTPUT_H):
        img = img.resize((OUTPUT_W, OUTPUT_H), Image.LANCZOS)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_path), "PNG", optimize=False)

    return time.monotonic() - t0


# ─────────────────────────────────────────────────────────────────────────────
# Async wrapper with retry + exponential backoff
# ─────────────────────────────────────────────────────────────────────────────

async def _generate_one_async(
    client: "genai.Client",
    executor: ThreadPoolExecutor,
    semaphore: asyncio.Semaphore,
    idx: int,
    prompt: str,
    out_path: Path,
    total: int,
    completed_counter: list,
    start_wall: float,
) -> bool:
    """
    Async wrapper: acquires semaphore, runs blocking call in thread, retries on error.
    Returns True on success, False on final failure.
    """
    async with semaphore:
        backoff = INITIAL_BACKOFF
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                elapsed = await asyncio.get_event_loop().run_in_executor(
                    executor,
                    _generate_one_blocking,
                    client,
                    prompt,
                    out_path,
                )
                completed_counter[0] += 1
                done = completed_counter[0]
                wall = time.monotonic() - start_wall
                avg = wall / done
                remaining = (total - done) * avg
                log.info(
                    f"[{done:>3}/{total}] #{idx:03d} ✓ {elapsed:.1f}s | "
                    f"avg {avg:.1f}s/img | ETA ~{remaining:.0f}s | → {out_path.name}"
                )
                return True

            except Exception as exc:
                jitter = random.uniform(0, backoff * 0.3)
                wait = backoff + jitter
                log.warning(
                    f"[#{idx:03d}] Attempt {attempt}/{MAX_RETRIES} failed: {exc}. "
                    f"Retrying in {wait:.1f}s..."
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(wait)
                    backoff *= 2
                else:
                    log.error(f"[#{idx:03d}] FAILED after {MAX_RETRIES} attempts.")
                    return False


# ─────────────────────────────────────────────────────────────────────────────
# Main batch runner
# ─────────────────────────────────────────────────────────────────────────────

async def run_batch(
    prompts: list,
    out_dir: Path,
    concurrency: int,
    prefix: str,
) -> dict:
    """
    Generate all images concurrently.
    Returns summary dict.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY environment variable is not set. "
            "Export it before running: export GEMINI_API_KEY=your_key"
        )

    client = genai.Client(api_key=api_key)
    total = len(prompts)

    log.info(f"{'='*60}")
    log.info(f"  Gemini Batch Image Generator")
    log.info(f"  Model  : {MODEL_ID}")
    log.info(f"  Images : {total}")
    log.info(f"  Output : {out_dir}")
    log.info(f"  Concurrency: {concurrency}")
    log.info(f"  Resolution: {OUTPUT_W}×{OUTPUT_H} (upscaled from {NATIVE_W}×{NATIVE_H})")
    log.info(f"{'='*60}")

    out_dir.mkdir(parents=True, exist_ok=True)

    semaphore = asyncio.Semaphore(concurrency)
    completed_counter = [0]
    start_wall = time.monotonic()

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        tasks = [
            _generate_one_async(
                client=client,
                executor=executor,
                semaphore=semaphore,
                idx=i,
                prompt=prompt,
                out_path=out_dir / f"{prefix}{i:03d}.png",
                total=total,
                completed_counter=completed_counter,
                start_wall=start_wall,
            )
            for i, prompt in enumerate(prompts)
        ]
        results = await asyncio.gather(*tasks)

    total_time = time.monotonic() - start_wall
    succeeded = sum(1 for r in results if r)
    failed = total - succeeded
    ips = succeeded / total_time if total_time > 0 else 0

    return {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "total_time_s": round(total_time, 2),
        "images_per_sec": round(ips, 3),
        "out_dir": str(out_dir.resolve()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Super-fast batch image generation with Gemini 2.5 Flash"
    )
    parser.add_argument(
        "--in", dest="input_file", required=True,
        help='Path to prompts JSON file: {"prompts": ["...", "..."]}'
    )
    parser.add_argument(
        "--out", dest="out_dir", default="./out",
        help="Output directory (default: ./out)"
    )
    parser.add_argument(
        "--concurrency", type=int, default=8,
        help="Max concurrent requests (default: 8)"
    )
    parser.add_argument(
        "--prefix", default="scene_",
        help="Output filename prefix (default: scene_)"
    )
    args = parser.parse_args()

    # Load prompts
    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    prompts = data.get("prompts", [])
    if not prompts:
        print("ERROR: No prompts found in JSON file. Expected: {'prompts': ['...']}")
        sys.exit(1)

    log.info(f"Loaded {len(prompts)} prompts from {input_path}")

    # Run batch
    summary = asyncio.run(
        run_batch(
            prompts=prompts,
            out_dir=Path(args.out_dir),
            concurrency=args.concurrency,
            prefix=args.prefix,
        )
    )

    # Print summary
    print(f"\n{'='*60}")
    print(f"  BATCH COMPLETE")
    print(f"{'='*60}")
    print(f"  Total images   : {summary['total']}")
    print(f"  Succeeded      : {summary['succeeded']}")
    print(f"  Failed         : {summary['failed']}")
    print(f"  Total time     : {summary['total_time_s']}s")
    print(f"  Effective rate : {summary['images_per_sec']} images/sec")
    print(f"  Output folder  : {summary['out_dir']}")
    print(f"{'='*60}")

    if summary["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

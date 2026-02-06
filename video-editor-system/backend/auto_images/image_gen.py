"""
Image generation using Replicate with caching and parallel processing
"""

import os
import hashlib
import time
import uuid
import requests
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import replicate

from .schema import AutoImagesPlan, ImageItem


class ImageGenerator:
    """Generate images from AutoImagesPlan using Replicate"""

    CACHE_DIR = Path("cache/generated_images")
    OUTPUT_DIR = Path("output/auto_images")
    MODEL_VERSION = "flux-1.1-pro"  # Track model version for cache

    def __init__(self, api_token: str, max_workers: int = 1, delay_between_images: float = 12.0):
        """
        Initialize image generator

        Args:
            api_token: Replicate API token
            max_workers: Max parallel generations (default 1 for rate limit safety)
            delay_between_images: Delay in seconds between images (default 12s for 6 req/min limit)
        """
        if not api_token:
            raise ValueError("Replicate API token is required")

        self.api_token = api_token
        self.max_workers = max_workers
        self.delay_between_images = delay_between_images

        # Set API token
        os.environ['REPLICATE_API_TOKEN'] = api_token

        # Create directories
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    def _get_image_cache_key(self, style_id: str, image_prompt: str, negative_prompt: str) -> str:
        """Generate cache key for image"""
        data = f"{style_id}|{image_prompt}|{negative_prompt}|{self.MODEL_VERSION}"
        return hashlib.sha256(data.encode()).hexdigest()

    def _get_cached_image_path(self, cache_key: str) -> Optional[Path]:
        """Check if image is cached"""
        cache_file = self.CACHE_DIR / f"{cache_key}.jpg"
        if cache_file.exists():
            return cache_file
        return None

    def _download_image(self, url: str, output_path: Path) -> bool:
        """Download image from URL"""
        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            with open(output_path, 'wb') as f:
                f.write(response.content)
            return True
        except Exception as e:
            print(f"Failed to download image: {e}")
            return False

    def _generate_single_image(
        self,
        scene_id: int,
        image_prompt: str,
        negative_prompt: str,
        style_id: str,
        aspect_ratio: str = "16:9",
        max_retries: int = 2,
        verbose: bool = False
    ) -> Optional[ImageItem]:
        """
        Generate a single image with retries

        Returns:
            ImageItem or None if failed
        """
        cache_key = self._get_image_cache_key(style_id, image_prompt, negative_prompt)

        # Check cache first
        cached_path = self._get_cached_image_path(cache_key)
        if cached_path:
            if verbose:
                print(f"   Scene {scene_id}: ✅ Cache hit")
            return ImageItem(
                id=str(uuid.uuid4()),
                source_type="generated",
                path=str(cached_path),
                scene_id=scene_id,
                prompt_used=image_prompt
            )

        # Generate new image
        for attempt in range(max_retries + 1):
            try:
                if verbose:
                    print(f"   Scene {scene_id}: 🔄 Generating... (attempt {attempt + 1})")

                start_time = time.time()

                # Call Replicate Flux
                output = replicate.run(
                    "black-forest-labs/flux-1.1-pro",
                    input={
                        "prompt": image_prompt,
                        "aspect_ratio": aspect_ratio,
                        "output_format": "jpg",
                        "output_quality": 90,
                        "safety_tolerance": 2,
                        "prompt_upsampling": True
                    }
                )

                elapsed = time.time() - start_time

                # Output is a FileOutput object with URL
                if output:
                    image_url = str(output)

                    # Download to cache
                    cache_path = self.CACHE_DIR / f"{cache_key}.jpg"
                    if self._download_image(image_url, cache_path):
                        if verbose:
                            print(f"   Scene {scene_id}: ✅ Generated in {elapsed:.1f}s")

                        return ImageItem(
                            id=str(uuid.uuid4()),
                            source_type="generated",
                            path=str(cache_path),
                            scene_id=scene_id,
                            prompt_used=image_prompt,
                            aspect_ratio=aspect_ratio
                        )
                    else:
                        if verbose:
                            print(f"   Scene {scene_id}: ❌ Download failed")

            except Exception as e:
                if verbose:
                    print(f"   Scene {scene_id}: ❌ Error: {e}")

                if attempt < max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff
                    if verbose:
                        print(f"   Scene {scene_id}: ⏳ Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    if verbose:
                        print(f"   Scene {scene_id}: ❌ Failed after {max_retries + 1} attempts")

        return None

    def generate_images(
        self,
        plan: AutoImagesPlan,
        aspect_ratio: str = "16:9",
        verbose: bool = True
    ) -> List[ImageItem]:
        """
        Generate all images from plan SEQUENTIALLY with delays
        Sequential generation avoids Replicate rate limits

        Args:
            plan: AutoImagesPlan with scenes
            aspect_ratio: Image aspect ratio
            verbose: Print progress

        Returns:
            List of ImageItem (may be shorter than plan.scenes if some failed)
        """

        if verbose:
            print(f"\n🎨 IMAGE GENERATION (Sequential with {self.delay_between_images}s delays)")
            print(f"   Scenes: {len(plan.scenes)}")
            print(f"   Aspect ratio: {aspect_ratio}")
            print(f"   Rate limit safe: 6 requests/minute")

        start_time = time.time()
        generated_items = []

        # Generate SEQUENTIALLY (not parallel) to avoid rate limits
        for idx, scene in enumerate(plan.scenes):
            try:
                item = self._generate_single_image(
                    scene.scene_id,
                    scene.image_prompt,
                    scene.negative_prompt,
                    plan.style_id,
                    aspect_ratio,
                    2,  # max_retries
                    verbose
                )
                if item:
                    generated_items.append(item)

                # Add delay between images (except after last one)
                # This respects Replicate rate limit: 6 requests/minute = 1 request every 10s
                if idx < len(plan.scenes) - 1 and self.delay_between_images > 0:
                    if verbose:
                        print(f"   ⏳ Waiting {self.delay_between_images}s before next image (rate limit safety)...")
                    time.sleep(self.delay_between_images)

            except Exception as e:
                if verbose:
                    print(f"   Scene {scene.scene_id}: ❌ Exception: {e}")

        elapsed = time.time() - start_time

        if verbose:
            success_count = len(generated_items)
            total_count = len(plan.scenes)
            print(f"\n   ✅ Generated: {success_count}/{total_count} images")
            print(f"   ⏱️ Total time: {elapsed:.1f}s")
            if success_count > 0:
                print(f"   ⏱️ Average: {elapsed / success_count:.1f}s per image")

        return generated_items

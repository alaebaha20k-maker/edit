#!/usr/bin/env python3
"""
ULTRA-FAST Video Assembler - No audio conversion, -framerate 2 for images
"""

import os
import subprocess
import hashlib
import time
from pathlib import Path
from typing import List, Dict


class VideoAssembler:
    """Ultra-fast video assembler - ALWAYS -c:a copy, NEVER convert audio"""

    def __init__(self, output_dir: str = "output", temp_dir: str = "temp"):
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir)
        self.cache_dir = self.temp_dir / "image_cache"

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Cache stats
        self.cache_hits = 0
        self.cache_misses = 0

    def _get_cache_key(self, image_path: str, width: int, height: int) -> str:
        """Generate cache key based on image path + mtime + size + settings"""
        stat = os.stat(image_path)
        key_string = f"{os.path.abspath(image_path)}_{stat.st_mtime}_{stat.st_size}_{width}x{height}"
        return hashlib.md5(key_string.encode()).hexdigest()

    def _get_cached_image(self, image_path: str, width: int = 1920, height: int = 1080) -> str:
        """
        Get cached 1080p JPG for image, or create it.
        Always returns a 1920x1080 16:9 JPG (letterboxed/pillarboxed).
        """
        cache_key = self._get_cache_key(image_path, width, height)
        cached_path = self.cache_dir / f"{cache_key}.jpg"

        if cached_path.exists():
            self.cache_hits += 1
            return str(cached_path)

        # Cache miss - create 1080p JPG
        self.cache_misses += 1

        cmd = [
            'ffmpeg', '-y',
            '-i', image_path,
            '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
            '-q:v', '3',  # High quality JPG (2-5 range, 3 is good)
            '-frames:v', '1',
            str(cached_path)
        ]

        subprocess.run(cmd, capture_output=True, check=True, timeout=30)
        return str(cached_path)

    def _get_audio_duration_ffprobe(self, audio_path: str) -> float:
        """Get audio duration using ffprobe"""
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            audio_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())

    def assemble_final_video(
        self,
        voice_path: str,
        media_paths: List[str],
        output_path: str,
        resolution: str = '1920x1080',
        verbose: bool = True
    ) -> Dict:
        """
        ULTRA-FAST VIDEO ASSEMBLY

        Rules:
        - AUDIO: ALWAYS -c:a copy (NEVER convert MP3!)
        - SINGLE IMAGE: Use -framerate 2 BEFORE -i
        - MULTIPLE IMAGES: Use concat + -vf fps=2
        - VIDEO: ALWAYS try -c:v copy first
        """
        total_start = time.time()

        # Parse resolution
        width, height = resolution.split('x')

        if verbose:
            print(f"\n{'='*60}")
            print(f"⚡ ULTRA-FAST VIDEO EXPORTER")
            print(f"{'='*60}")

        # Get audio duration (NO CONVERSION!)
        voice_duration = self._get_audio_duration_ffprobe(voice_path)
        voice_minutes = int(voice_duration // 60)
        voice_seconds = int(voice_duration % 60)

        if verbose:
            print(f"   Audio: {voice_minutes}m {voice_seconds}s (NO conversion!)")
            print(f"   Media: {len(media_paths)} files")

        # SINGLE MEDIA
        if len(media_paths) == 1:
            ext = os.path.splitext(media_paths[0])[1].lower()

            # SINGLE VIDEO: Copy streams (INSTANT!)
            if ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv']:
                if verbose:
                    print(f"\n⚡ INSTANT MODE: Single video")
                    print(f"   Strategy: -c:v copy -c:a copy")

                cmd = [
                    'ffmpeg', '-y',
                    '-i', media_paths[0],
                    '-i', voice_path,
                    '-map', '0:v:0',
                    '-map', '1:a:0',
                    '-c:v', 'copy',
                    '-c:a', 'copy',
                    '-shortest',
                    '-movflags', '+faststart',
                    output_path
                ]

                if verbose:
                    print(f"\n📝 FFmpeg command:")
                    print(f"   {' '.join(cmd)}")

                render_start = time.time()
                subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=600)
                render_elapsed = time.time() - render_start

                total_elapsed = time.time() - total_start
                size_mb = os.path.getsize(output_path) / (1024 * 1024)

                if verbose:
                    print(f"\n✅ DONE!")
                    print(f"   Render: {render_elapsed:.1f}s")
                    print(f"   Total: {total_elapsed:.1f}s")
                    print(f"   Size: {size_mb:.2f} MB")

                return {
                    'success': True,
                    'output_path': output_path,
                    'duration_seconds': voice_duration,
                    'file_size_mb': size_mb,
                    'processing_time': total_elapsed,
                    'media_count': 1,
                    'voice_duration': voice_duration
                }

            # SINGLE IMAGE: Use -framerate 2 BEFORE -i (CRITICAL!)
            if ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp']:
                if verbose:
                    print(f"\n⚡ ULTRA-FAST MODE: Single image")
                    print(f"   Strategy: -framerate 2 -loop 1 -i (NO scaling!)")

                # Get cached 1080p image
                cache_start = time.time()
                cached_image = self._get_cached_image(media_paths[0], int(width), int(height))
                cache_elapsed = time.time() - cache_start

                if verbose:
                    print(f"   Image cache: {cache_elapsed:.1f}s (hits: {self.cache_hits}, misses: {self.cache_misses})")

                # CRITICAL: -framerate 2 BEFORE -i
                cmd = [
                    'ffmpeg', '-y',
                    '-framerate', '2',  # 🔥 BEFORE -i for MASSIVE speedup!
                    '-loop', '1',
                    '-i', cached_image,
                    '-i', voice_path,
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast',
                    '-crf', '35',
                    '-g', '600',
                    '-tune', 'stillimage',
                    '-c:a', 'copy',  # 🔥 ALWAYS copy!
                    '-shortest',
                    '-pix_fmt', 'yuv420p',
                    '-threads', '0',
                    '-movflags', '+faststart',
                    output_path
                ]

                if verbose:
                    print(f"\n📝 FFmpeg command:")
                    print(f"   {' '.join(cmd)}")

                render_start = time.time()
                subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=600)
                render_elapsed = time.time() - render_start

                total_elapsed = time.time() - total_start
                size_mb = os.path.getsize(output_path) / (1024 * 1024)

                if verbose:
                    print(f"\n✅ DONE!")
                    print(f"   Cache: {cache_elapsed:.1f}s")
                    print(f"   Render: {render_elapsed:.1f}s")
                    print(f"   Total: {total_elapsed:.1f}s")
                    print(f"   Size: {size_mb:.2f} MB")

                return {
                    'success': True,
                    'output_path': output_path,
                    'duration_seconds': voice_duration,
                    'file_size_mb': size_mb,
                    'processing_time': total_elapsed,
                    'media_count': 1,
                    'voice_duration': voice_duration
                }

        # MULTIPLE IMAGES: Use concat + -vf fps=2
        if verbose:
            print(f"\n⚡ SLIDESHOW MODE: Multiple images")
            print(f"   Strategy: concat + -vf fps=2")

        # Filter to only images
        image_paths = [
            p for p in media_paths
            if os.path.splitext(p)[1].lower() in ['.jpg', '.jpeg', '.png', '.webp', '.bmp']
        ]

        if len(image_paths) == 0:
            raise ValueError("No valid images found in media_paths")

        # Cache all images as 1080p JPGs
        cache_start = time.time()
        cached_images = []

        if verbose:
            print(f"   Caching {len(image_paths)} images to 1080p JPG...")

        for i, img_path in enumerate(image_paths):
            cached_img = self._get_cached_image(img_path, int(width), int(height))
            cached_images.append(cached_img)

        cache_elapsed = time.time() - cache_start

        if verbose:
            print(f"   Cache: {cache_elapsed:.1f}s (hits: {self.cache_hits}, misses: {self.cache_misses})")

        # Create concat list with durations
        duration_per_image = voice_duration / len(cached_images)
        concat_file = self.temp_dir / "concat_list.txt"

        with open(concat_file, 'w') as f:
            for i, img in enumerate(cached_images):
                f.write(f"file '{os.path.abspath(img)}'\n")
                if i < len(cached_images) - 1:
                    f.write(f"duration {duration_per_image}\n")
            # Repeat last image
            f.write(f"file '{os.path.abspath(cached_images[-1])}'\n")

        # Final render with concat + -vf fps=2
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
            '-i', voice_path,
            '-vf', 'fps=2',  # 🔥 Set framerate via filter
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '35',
            '-g', '600',
            '-tune', 'stillimage',
            '-c:a', 'copy',  # 🔥 ALWAYS copy!
            '-shortest',
            '-pix_fmt', 'yuv420p',
            '-threads', '0',
            '-movflags', '+faststart',
            output_path
        ]

        if verbose:
            print(f"\n📝 FFmpeg command:")
            print(f"   {' '.join(cmd)}")

        render_start = time.time()
        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=1200)
        render_elapsed = time.time() - render_start

        total_elapsed = time.time() - total_start
        size_mb = os.path.getsize(output_path) / (1024 * 1024)

        if verbose:
            print(f"\n✅ DONE!")
            print(f"   Cache: {cache_elapsed:.1f}s")
            print(f"   Render: {render_elapsed:.1f}s")
            print(f"   Total: {total_elapsed:.1f}s")
            print(f"   Size: {size_mb:.2f} MB")

        return {
            'success': True,
            'output_path': output_path,
            'duration_seconds': voice_duration,
            'file_size_mb': size_mb,
            'processing_time': total_elapsed,
            'media_count': len(cached_images),
            'voice_duration': voice_duration
        }


# Test function
if __name__ == '__main__':
    assembler = VideoAssembler()
    print("Ultra-fast VideoAssembler initialized!")

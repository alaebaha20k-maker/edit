#!/usr/bin/env python3
"""
OPTIMIZED Video Assembler - Maximum speed with caching
"""

import os
import subprocess
import json
import hashlib
import time
from pathlib import Path
from typing import List, Dict
from pydub import AudioSegment


class VideoAssembler:
    """Optimized video assembler with audio normalization and image caching"""

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

    def _normalize_audio_to_m4a(self, audio_path: str, output_path: str, verbose: bool = True) -> str:
        """
        Normalize audio to M4A/AAC format for -c:a copy compatibility.
        Always outputs 160k AAC, 48kHz, stereo.
        """
        if verbose:
            print(f"   🔄 Normalizing audio to M4A/AAC...")

        start = time.time()

        cmd = [
            'ffmpeg', '-y',
            '-i', audio_path,
            '-c:a', 'aac',
            '-b:a', '160k',
            '-ar', '48000',
            '-ac', '2',
            output_path
        ]

        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=600)

        elapsed = time.time() - start
        if verbose:
            print(f"   ✅ Audio normalized in {elapsed:.1f}s")

        return output_path

    def assemble_final_video(
        self,
        voice_path: str,
        media_paths: List[str],
        output_path: str,
        resolution: str = '1920x1080',
        verbose: bool = True
    ) -> Dict:
        """
        OPTIMIZED VIDEO ASSEMBLY

        Pipeline:
        1. Normalize audio to M4A/AAC ONCE
        2. Cache all images as 1920x1080 JPGs
        3. ONE final encode with concat demuxer (no scaling!)
        """
        total_start = time.time()

        # Parse resolution
        width, height = resolution.split('x')

        if verbose:
            print(f"\n{'='*60}")
            print(f"⚡ OPTIMIZED VIDEO EXPORTER")
            print(f"{'='*60}")

        # STEP 1: Normalize audio to M4A/AAC
        audio_start = time.time()
        normalized_audio = self.temp_dir / f"audio_normalized_{int(time.time())}.m4a"

        if not voice_path.endswith('.m4a'):
            self._normalize_audio_to_m4a(voice_path, str(normalized_audio), verbose)
            final_audio = str(normalized_audio)
        else:
            # Already M4A, check if AAC
            final_audio = voice_path
            if verbose:
                print(f"   ✅ Audio already M4A format")

        audio_elapsed = time.time() - audio_start

        # Get audio duration
        voice_duration = self._get_audio_duration_ffprobe(final_audio)
        voice_minutes = int(voice_duration // 60)
        voice_seconds = int(voice_duration % 60)

        if verbose:
            print(f"   Audio: {voice_minutes}m {voice_seconds}s")
            print(f"   Media: {len(media_paths)} files")

        # STEP 2: Single media optimization
        if len(media_paths) == 1:
            ext = os.path.splitext(media_paths[0])[1].lower()

            # VIDEO: Copy streams (INSTANT!)
            if ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv']:
                if verbose:
                    print(f"\n⚡ INSTANT MODE: Single video + audio copy")

                cmd = [
                    'ffmpeg', '-y',
                    '-i', media_paths[0],
                    '-i', final_audio,
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
                    print(f"\n✅ DONE! Total: {total_elapsed:.1f}s | Render: {render_elapsed:.1f}s | Size: {size_mb:.2f} MB")

                return {
                    'success': True,
                    'output_path': output_path,
                    'duration_seconds': voice_duration,
                    'file_size_mb': size_mb,
                    'processing_time': total_elapsed,
                    'media_count': 1,
                    'voice_duration': voice_duration
                }

            # IMAGE: Use cached 1080p JPG
            if ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp']:
                if verbose:
                    print(f"\n⚡ FAST MODE: Single image + audio copy")

                # Get cached 1080p image
                cache_start = time.time()
                cached_image = self._get_cached_image(media_paths[0], int(width), int(height))
                cache_elapsed = time.time() - cache_start

                if verbose:
                    print(f"   Image caching: {cache_elapsed:.1f}s (hits: {self.cache_hits}, misses: {self.cache_misses})")

                # Final render (NO SCALING!)
                cmd = [
                    'ffmpeg', '-y',
                    '-loop', '1',
                    '-i', cached_image,
                    '-i', final_audio,
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast',
                    '-crf', '35',
                    '-r', '2',
                    '-g', '600',
                    '-tune', 'stillimage',
                    '-c:a', 'copy',  # Always copy (audio is normalized!)
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
                    print(f"   Audio prep: {audio_elapsed:.1f}s")
                    print(f"   Image cache: {cache_elapsed:.1f}s")
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

        # STEP 3: Multiple images - use concat demuxer
        if verbose:
            print(f"\n⚡ SLIDESHOW MODE: Multiple images")

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
            if verbose and (i + 1) % 10 == 0:
                print(f"   Cached {i+1}/{len(image_paths)} images...")

        cache_elapsed = time.time() - cache_start

        if verbose:
            print(f"   ✅ Image caching: {cache_elapsed:.1f}s")
            print(f"   Cache stats: {self.cache_hits} hits, {self.cache_misses} misses")

        # Create concat list with durations
        duration_per_image = voice_duration / len(cached_images)
        concat_file = self.temp_dir / "concat_list.txt"

        with open(concat_file, 'w') as f:
            for i, img in enumerate(cached_images):
                f.write(f"file '{os.path.abspath(img)}'\n")
                if i < len(cached_images) - 1:
                    f.write(f"duration {duration_per_image}\n")
            # Repeat last image to preserve duration
            f.write(f"file '{os.path.abspath(cached_images[-1])}'\n")

        # Final render (NO SCALING - images already 1080p!)
        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
            '-i', final_audio,
            '-vsync', 'cfr',
            '-r', '2',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '35',
            '-tune', 'stillimage',
            '-c:a', 'copy',  # Always copy (audio is normalized!)
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
            print(f"   Audio prep: {audio_elapsed:.1f}s")
            print(f"   Image cache: {cache_elapsed:.1f}s (hits: {self.cache_hits}, misses: {self.cache_misses})")
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
    print("Optimized VideoAssembler initialized successfully!")

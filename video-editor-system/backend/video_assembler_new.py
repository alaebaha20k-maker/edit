#!/usr/bin/env python3
"""
INTELLIGENT Video Assembler - Uses optimal strategy for each case!

Strategy:
- Single image: -loop 1 -tune stillimage -c:a copy (INSTANT!)
- Multiple images: prepare clips with -tune stillimage, concat with -c copy, audio with -c copy (FAST!)
"""

import os
import subprocess
import json
from pathlib import Path
from typing import List, Dict
from pydub import AudioSegment


class VideoAssembler:
    """Intelligent video assembler - chooses optimal strategy"""

    def __init__(self, output_dir: str = "output", temp_dir: str = "temp"):
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Detect best encoder
        self.encoder_info = self._detect_best_encoder()

    def _detect_best_encoder(self) -> dict:
        """Detect best available encoder"""
        try:
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-encoders'],
                capture_output=True, text=True, timeout=5
            )
            encoders = result.stdout

            if 'h264_nvenc' in encoders:
                print("✅ NVIDIA GPU encoder detected")
                return {'encoder': 'h264_nvenc', 'hw_type': 'nvidia'}
            elif 'h264_qsv' in encoders:
                print("✅ Intel Quick Sync detected")
                return {'encoder': 'h264_qsv', 'hw_type': 'intel'}
            elif 'h264_amf' in encoders:
                print("✅ AMD GPU encoder detected")
                return {'encoder': 'h264_amf', 'hw_type': 'amd'}
        except:
            pass

        print("ℹ️ Using CPU encoder (libx264)")
        return {'encoder': 'libx264', 'hw_type': 'cpu'}

    def get_audio_duration(self, audio_path: str) -> float:
        """Get audio duration"""
        try:
            audio = AudioSegment.from_file(audio_path)
            return len(audio) / 1000.0
        except:
            return self._get_duration_ffprobe(audio_path)

    def _get_duration_ffprobe(self, file_path: str) -> float:
        """Get duration using ffprobe"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                file_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except:
            return 0.0

    def assemble_final_video(
        self,
        voice_path: str,
        media_paths: List[str],
        output_path: str,
        resolution: str = '1920x1080',
        verbose: bool = True
    ) -> Dict:
        """
        INTELLIGENT VIDEO EXPORTER

        Automatically chooses the fastest strategy:
        1. Single image: Ultra-fast (-loop 1 -tune stillimage -c:a copy)
        2. Multiple images: Fast (-tune stillimage + concat -c copy + audio -c copy)
        """
        start_time = __import__('time').time()

        voice_duration = self.get_audio_duration(voice_path)
        voice_minutes = int(voice_duration // 60)
        voice_seconds = int(voice_duration % 60)

        if verbose:
            print(f"\n{'='*60}")
            print(f"⚡ INTELLIGENT VIDEO EXPORTER")
            print(f"{'='*60}")
            print(f"   Voice: {voice_minutes}m {voice_seconds}s")
            print(f"   Media: {len(media_paths)} files")

        if voice_duration <= 0:
            raise ValueError("Voice duration invalid")
        if len(media_paths) == 0:
            raise ValueError("No media provided")

        width, height = resolution.split('x')

        # STRATEGY 1: Single image = SUPER FAST!
        if len(media_paths) == 1:
            ext = os.path.splitext(media_paths[0])[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp']:
                if verbose:
                    print(f"\n⚡ SUPER FAST MODE: Single image!")
                    print(f"   Strategy: -r 10 -crf 32 -tune stillimage -c:a copy")

                try:
                    cmd = [
                        'ffmpeg', '-y',
                        '-loop', '1',
                        '-i', media_paths[0],
                        '-i', voice_path,
                        '-c:v', 'libx264',
                        '-preset', 'ultrafast',
                        '-crf', '32',
                        '-r', '10',
                        '-tune', 'stillimage',
                        '-c:a', 'copy',  # NO audio re-encoding!
                        '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
                        '-shortest',
                        '-pix_fmt', 'yuv420p',
                        '-movflags', '+faststart',
                        output_path
                    ]

                    subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=600)

                    elapsed = __import__('time').time() - start_time
                    size_mb = os.path.getsize(output_path) / (1024 * 1024)

                    if verbose:
                        print(f"\n✅ DONE! Time: {elapsed:.1f}s | Size: {size_mb:.2f} MB")

                    return {
                        'success': True,
                        'output_path': output_path,
                        'duration_seconds': voice_duration,
                        'file_size_mb': size_mb,
                        'processing_time': elapsed,
                        'media_count': 1,
                        'voice_duration': voice_duration
                    }
                except subprocess.CalledProcessError as e:
                    raise Exception(f"Export failed: {e.stderr[-1000:]}")

        # STRATEGY 2: Multiple media = Fast with -c copy
        if verbose:
            print(f"\n⚡ FAST MODE: Multiple media")
            print(f"   Strategy: -r 10 -crf 33 -tune stillimage → concat -c copy → audio -c copy")

        duration_per_item = voice_duration / len(media_paths)
        prepared_clips = []

        # Prepare clips
        for i, media_path in enumerate(media_paths):
            ext = os.path.splitext(media_path)[1].lower()
            is_image = ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp']
            clip_output = self.temp_dir / f"clip_{i:03d}.mp4"

            if is_image:
                cmd = [
                    'ffmpeg', '-y',
                    '-loop', '1',
                    '-i', media_path,
                    '-t', str(duration_per_item),
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast',
                    '-crf', '33',
                    '-r', '10',
                    '-tune', 'stillimage',
                    '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
                    '-pix_fmt', 'yuv420p',
                    '-an',
                    str(clip_output)
                ]
            else:
                cmd = [
                    'ffmpeg', '-y',
                    '-i', media_path,
                    '-t', str(duration_per_item),
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast',
                    '-crf', '32',
                    '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
                    '-an',
                    str(clip_output)
                ]

            try:
                subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=600)
                prepared_clips.append(str(clip_output))
                if verbose:
                    print(f"   [{i+1}/{len(media_paths)}] ✅")
            except:
                if verbose:
                    print(f"   [{i+1}/{len(media_paths)}] ⚠️ Failed")

        if len(prepared_clips) == 0:
            raise ValueError("No clips prepared")

        # Concat with -c copy (NO re-encoding!)
        concat_file = self.temp_dir / "concat.txt"
        with open(concat_file, 'w') as f:
            for clip in prepared_clips:
                f.write(f"file '{os.path.abspath(clip)}'\n")

        temp_video = self.temp_dir / "temp_video.mp4"

        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', str(concat_file),
            '-c', 'copy',  # NO re-encoding!
            str(temp_video)
        ]

        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)

        # Add audio with -c copy (NO re-encoding!)
        cmd = [
            'ffmpeg', '-y',
            '-i', str(temp_video),
            '-i', voice_path,
            '-c:v', 'copy',  # NO video re-encoding!
            '-c:a', 'copy',  # NO audio re-encoding!
            '-shortest',
            '-movflags', '+faststart',
            output_path
        ]

        subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)

        # Cleanup
        for clip in prepared_clips:
            try:
                os.remove(clip)
            except:
                pass

        elapsed = __import__('time').time() - start_time
        size_mb = os.path.getsize(output_path) / (1024 * 1024)

        if verbose:
            print(f"\n✅ DONE! Time: {elapsed:.1f}s | Size: {size_mb:.2f} MB")

        return {
            'success': True,
            'output_path': output_path,
            'duration_seconds': voice_duration,
            'file_size_mb': size_mb,
            'processing_time': elapsed,
            'media_count': len(prepared_clips),
            'voice_duration': voice_duration
        }

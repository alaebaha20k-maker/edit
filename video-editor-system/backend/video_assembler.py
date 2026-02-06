#!/usr/bin/env python3
"""
Video Assembler - Creates final video from voice + media
Matches video length exactly to voice duration
"""

import os
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Optional
from pydub import AudioSegment
from pydub.utils import mediainfo


class VideoAssembler:
    """Assembles final video from voice audio and media (images/videos)"""

    def __init__(self, output_dir: str = "output", temp_dir: str = "temp"):
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # Detect best video encoder on init (cache it)
        self.encoder_info = self._detect_best_encoder()

    def _detect_best_encoder(self) -> dict:
        """
        Detect best available video encoder (GPU or CPU)
        ACTUALLY tests if GPU encoder works (not just listed)
        """
        # Test NVIDIA GPU by actually trying it
        try:
            test = subprocess.run(
                ['ffmpeg', '-f', 'lavfi', '-i', 'color=black:s=64x64:d=0.1',
                 '-c:v', 'h264_nvenc', '-f', 'null', '-'],
                capture_output=True, timeout=3
            )
            if test.returncode == 0:
                print("✅ NVIDIA GPU encoder working (h264_nvenc)")
                return {'encoder': 'h264_nvenc', 'preset': 'p4', 'hw_type': 'nvidia'}
        except:
            pass

        # Test Intel Quick Sync
        try:
            test = subprocess.run(
                ['ffmpeg', '-f', 'lavfi', '-i', 'color=black:s=64x64:d=0.1',
                 '-c:v', 'h264_qsv', '-f', 'null', '-'],
                capture_output=True, timeout=3
            )
            if test.returncode == 0:
                print("✅ Intel Quick Sync working (h264_qsv)")
                return {'encoder': 'h264_qsv', 'preset': 'veryfast', 'hw_type': 'intel'}
        except:
            pass

        # Fallback to CPU encoding (fast & reliable!)
        print("ℹ️ Using CPU encoder (libx264) - fast & reliable")
        return {'encoder': 'libx264', 'preset': 'veryfast', 'hw_type': 'cpu'}

    def get_audio_duration(self, audio_path: str) -> float:
        """Get duration of audio file in seconds"""
        try:
            audio = AudioSegment.from_file(audio_path)
            return len(audio) / 1000.0  # Convert milliseconds to seconds
        except Exception as e:
            # Fallback to ffprobe
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
        except Exception as e:
            print(f"⚠️ Could not get duration for {file_path}: {e}")
            return 0.0

    def calculate_media_durations(
        self,
        total_duration: float,
        media_count: int,
        distribution: str = 'equal'
    ) -> List[float]:
        """
        Calculate duration for each media item

        Args:
            total_duration: Total video duration (voice length)
            media_count: Number of media items
            distribution: 'equal' or 'weighted'

        Returns:
            List of durations for each media item
        """
        if media_count == 0:
            return []

        if distribution == 'equal':
            # Equal distribution
            duration_per_item = total_duration / media_count
            return [duration_per_item] * media_count
        else:
            # TODO: Implement weighted distribution based on content
            duration_per_item = total_duration / media_count
            return [duration_per_item] * media_count

    def prepare_media_clip(
        self,
        media_path: str,
        duration: float,
        output_path: str,
        media_type: str = 'image',
        resolution: str = '1920x1080'
    ) -> bool:
        """
        Prepare a single media clip with specified duration

        Args:
            media_path: Path to source media
            duration: Desired duration in seconds
            output_path: Output path for prepared clip
            media_type: 'image' or 'video'
            resolution: Output resolution (WxH)

        Returns:
            True if successful
        """
        try:
            # Parse resolution string (e.g., "1920x1080" -> width=1920, height=1080)
            width, height = resolution.split('x')

            if media_type == 'image':
                # EXTREME SPEED image to video conversion
                # Secret: Use 10fps for static images! (2.4x faster than 24fps!)
                # No motion = no need for high FPS!

                cmd = ['ffmpeg', '-y', '-loop', '1', '-i', media_path]

                # Add encoder-specific settings
                if self.encoder_info['hw_type'] == 'nvidia':
                    # NVIDIA GPU encoding (VERY FAST!)
                    cmd.extend([
                        '-c:v', 'h264_nvenc',
                        '-preset', 'p1',  # Fastest NVIDIA preset
                        '-tune', 'hq',  # High quality
                        '-rc', 'vbr',  # Variable bitrate
                        '-cq', '28',  # Quality level
                        '-b:v', '5M',  # 5Mbps bitrate (good for 1080p)
                    ])
                elif self.encoder_info['hw_type'] == 'intel':
                    # Intel Quick Sync (FAST!)
                    cmd.extend([
                        '-c:v', 'h264_qsv',
                        '-preset', 'veryfast',
                        '-global_quality', '28',
                    ])
                elif self.encoder_info['hw_type'] == 'amd':
                    # AMD GPU (FAST!)
                    cmd.extend([
                        '-c:v', 'h264_amf',
                        '-quality', 'speed',
                        '-rc', 'vbr_latency',
                        '-qp_i', '22',
                        '-qp_p', '22',
                    ])
                else:
                    # CPU encoding (optimized)
                    cmd.extend([
                        '-c:v', 'libx264',
                        '-preset', 'ultrafast',  # Fastest CPU preset
                        '-crf', '23',  # Good quality
                        '-tune', 'zerolatency',  # Faster encoding
                        '-threads', '0',  # Use all CPU cores
                    ])

                # Common settings for all encoders
                cmd.extend([
                    '-t', str(duration),
                    '-pix_fmt', 'yuv420p',
                    '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease:flags=fast_bilinear,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1',
                    '-r', '10',  # 10fps for static images (MUCH faster than 24fps!)
                    '-g', '30',  # Keyframe every 3 seconds
                    '-movflags', '+faststart',
                    output_path
                ])

            else:
                # Process video clip - Smart duration handling with GPU acceleration
                video_duration = self._get_duration_ffprobe(media_path)

                if video_duration >= duration:
                    # Video is longer - trim to exact duration
                    cmd = ['ffmpeg', '-y', '-i', media_path, '-t', str(duration)]
                else:
                    # Video is shorter - loop it to fill duration
                    loops_needed = int(duration / video_duration) + 1
                    cmd = ['ffmpeg', '-y', '-stream_loop', str(loops_needed), '-i', media_path, '-t', str(duration)]

                # Add encoder-specific settings for videos
                if self.encoder_info['hw_type'] == 'nvidia':
                    cmd.extend([
                        '-c:v', 'h264_nvenc',
                        '-preset', 'p2',  # Fast NVIDIA preset
                        '-tune', 'hq',
                        '-rc', 'vbr',
                        '-cq', '23',  # Better quality for videos
                        '-b:v', '8M',  # 8Mbps for 1080p video
                    ])
                elif self.encoder_info['hw_type'] == 'intel':
                    cmd.extend([
                        '-c:v', 'h264_qsv',
                        '-preset', 'fast',
                        '-global_quality', '23',
                    ])
                elif self.encoder_info['hw_type'] == 'amd':
                    cmd.extend([
                        '-c:v', 'h264_amf',
                        '-quality', 'balanced',
                        '-rc', 'vbr_latency',
                        '-qp_i', '20',
                        '-qp_p', '20',
                    ])
                else:
                    cmd.extend([
                        '-c:v', 'libx264',
                        '-preset', 'veryfast',  # Faster than ultrafast but better quality
                        '-crf', '23',
                        '-threads', '0',
                    ])

                # Common settings
                cmd.extend([
                    '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease:flags=fast_bilinear,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
                    '-r', '24',  # 24fps output
                    '-an',  # Remove audio
                    '-movflags', '+faststart',
                    output_path
                ])

            # Run FFmpeg with timeout (max 10 minutes per clip)
            print(f"      Running FFmpeg command...")
            print(f"      Duration: {duration:.2f}s, Type: {media_type}")
            print(f"      Encoder: {self.encoder_info['encoder']} ({self.encoder_info['hw_type']})")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=600  # 10 minute timeout
            )
            return True

        except subprocess.TimeoutExpired:
            print(f"❌ FFmpeg timeout after 10 minutes!")
            return False
        except subprocess.CalledProcessError as e:
            # GPU encoding failed - try CPU fallback!
            if self.encoder_info['hw_type'] != 'cpu':
                print(f"⚠️ GPU encoder failed, retrying with CPU...")
                print(f"   GPU Error: {e.stderr[-200:] if e.stderr else 'Unknown'}")

                # Force CPU encoding for this retry
                original_encoder = self.encoder_info.copy()
                self.encoder_info = {'encoder': 'libx264', 'preset': 'ultrafast', 'hw_type': 'cpu'}

                try:
                    # Retry with CPU encoding
                    return self.prepare_media_clip(media_path, duration, output_path, media_type, resolution)
                finally:
                    # Restore original encoder for next clip
                    self.encoder_info = original_encoder
            else:
                print(f"❌ FFmpeg error preparing media:")
                print(f"   Command: {' '.join(cmd)}")
                print(f"   Error: {e.stderr[-500:]}")  # Last 500 chars of error
                return False
        except Exception as e:
            print(f"❌ Error preparing media: {e}")
            return False

    def assemble_final_video(
        self,
        voice_path: str,
        media_paths: List[str],
        output_path: str,
        resolution: str = '1920x1080',
        verbose: bool = True
    ) -> Dict:
        """
        SUPER FAST video assembly - Uses COPY when possible, 1 FPS for images!
        - Single VIDEO: -c:v copy -c:a copy (INSTANT, seconds!)
        - Single IMAGE: -loop 1 -r 1 -c:a copy (FAST, small files!)
        - Multiple: concat -c copy (NO re-encoding!)
        """
        start_time = __import__('time').time()

        # Get voice duration
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
            raise ValueError("Voice audio duration is 0 or invalid")
        if len(media_paths) == 0:
            raise ValueError("No media items provided")

        # Parse resolution
        width, height = resolution.split('x')

        # STRATEGY 1: Single VIDEO = INSTANT! (just copy, no encoding!)
        if len(media_paths) == 1:
            ext = os.path.splitext(media_paths[0])[1].lower()

            # VIDEO: Copy video + copy audio = INSTANT!
            if ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv']:
                if verbose:
                    print(f"\n⚡ INSTANT MODE: Single video!")
                    print(f"   Strategy: -c:v copy -c:a copy (NO encoding!)")

                try:
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', media_paths[0],
                        '-i', voice_path,
                        '-map', '0:v:0',  # Take video from first input
                        '-map', '1:a:0',  # Take audio from second input
                        '-c:v', 'copy',   # NO video encoding!
                        '-c:a', 'copy',   # NO audio encoding!
                        '-shortest',      # Cut to shortest (audio duration)
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

            # IMAGE: Loop image for entire duration (2 FPS = FAST + PLAYABLE!)
            if ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp']:
                if verbose:
                    print(f"\n⚡ SUPER FAST MODE: Single image!")
                    print(f"   Strategy: -framerate 1 -r 2 -crf 35 -g 600 (ULTRA FAST!)")

                # Try audio copy first (fastest!), fallback to encode if fails
                try:
                    cmd = [
                        'ffmpeg', '-y',
                        '-loop', '1',
                        '-framerate', '1',  # 🔥 READ AT 1 FPS (10x faster!)
                        '-i', media_paths[0],
                        '-i', voice_path,
                        '-c:v', 'libx264',
                        '-preset', 'ultrafast',
                        '-crf', '35',
                        '-r', '2',  # 🔥 OUTPUT AT 2 FPS
                        '-g', '600',  # 🔥 KEYFRAME EVERY 20s!
                        '-tune', 'stillimage',
                        '-c:a', 'copy',  # Try copy first
                        '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
                        '-shortest',
                        '-pix_fmt', 'yuv420p',
                        '-threads', '0',  # USE ALL CPU CORES!
                        '-movflags', '+faststart',
                        output_path
                    ]

                    subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=600)
                except subprocess.CalledProcessError:
                    # Audio copy failed, encode audio (still fast)
                    if verbose:
                        print(f"   Audio copy failed, encoding audio...")

                    cmd = [
                        'ffmpeg', '-y',
                        '-loop', '1',
                        '-framerate', '1',  # 🔥 READ AT 1 FPS (10x faster!)
                        '-i', media_paths[0],
                        '-i', voice_path,
                        '-c:v', 'libx264',
                        '-preset', 'ultrafast',
                        '-crf', '35',
                        '-r', '2',  # 🔥 OUTPUT AT 2 FPS
                        '-g', '600',  # 🔥 KEYFRAME EVERY 20s!
                        '-tune', 'stillimage',
                        '-c:a', 'aac',
                        '-b:a', '128k',  # Low bitrate = faster
                        '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
                        '-shortest',
                        '-pix_fmt', 'yuv420p',
                        '-threads', '0',  # USE ALL CPU CORES!
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

        # STRATEGY 2: Multiple media
        if verbose:
            print(f"\n⚡ FAST MODE: Multiple media")

        # Check media types
        images = []
        videos = []
        for path in media_paths:
            ext = os.path.splitext(path)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp']:
                images.append(path)
            elif ext in ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv']:
                videos.append(path)

        all_images = len(images) == len(media_paths)
        all_videos = len(videos) == len(media_paths)

        # CASE A: ALL IMAGES → Use concat demuxer (ONE encode, FASTEST!)
        if all_images:
            if verbose:
                print(f"   Strategy: Concat demuxer (ONE encode for all images!)")

            duration_per_item = voice_duration / len(media_paths)

            # Create list.txt with durations
            concat_file = self.temp_dir / "concat_list.txt"
            with open(concat_file, 'w') as f:
                for i, img in enumerate(media_paths):
                    f.write(f"file '{os.path.abspath(img)}'\n")
                    # Don't add duration for the last image (it will loop)
                    if i < len(media_paths) - 1:
                        f.write(f"duration {duration_per_item}\n")
                # Repeat last image to ensure proper duration
                f.write(f"file '{os.path.abspath(media_paths[-1])}'\n")

            # ONE encode directly from list to final output!
            try:
                cmd = [
                    'ffmpeg', '-y',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', str(concat_file),
                    '-i', voice_path,
                    '-vsync', 'cfr',
                    '-r', '2',  # 🔥 OUTPUT AT 2 FPS
                    '-g', '600',  # 🔥 KEYFRAME EVERY 20s!
                    '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast',
                    '-crf', '35',
                    '-tune', 'stillimage',
                    '-c:a', 'copy',
                    '-shortest',
                    '-pix_fmt', 'yuv420p',
                    '-threads', '0',  # USE ALL CPU CORES!
                    '-movflags', '+faststart',
                    output_path
                ]

                if verbose:
                    print(f"   Encoding all {len(media_paths)} images in ONE pass...")

                subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=1200)
            except subprocess.CalledProcessError:
                # Audio copy failed, try encoding audio
                if verbose:
                    print(f"   Audio copy failed, encoding audio...")

                cmd = [
                    'ffmpeg', '-y',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', str(concat_file),
                    '-i', voice_path,
                    '-vsync', 'cfr',
                    '-r', '2',  # 🔥 OUTPUT AT 2 FPS
                    '-g', '600',  # 🔥 KEYFRAME EVERY 20s!
                    '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast',
                    '-crf', '35',
                    '-tune', 'stillimage',
                    '-c:a', 'aac',
                    '-b:a', '128k',
                    '-shortest',
                    '-pix_fmt', 'yuv420p',
                    '-threads', '0',  # USE ALL CPU CORES!
                    '-movflags', '+faststart',
                    output_path
                ]

                subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=1200)

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
                'media_count': len(media_paths),
                'voice_duration': voice_duration
            }

        # CASE B: ALL VIDEOS → Try concat with -c copy first (INSTANT!)
        elif all_videos:
            if verbose:
                print(f"   Strategy: Concat videos with -c copy (INSTANT!)")

            # Create concat list
            concat_file = self.temp_dir / "concat_videos.txt"
            with open(concat_file, 'w') as f:
                for video in media_paths:
                    f.write(f"file '{os.path.abspath(video)}'\n")

            # Try concat with copy first (FAST!)
            temp_video = self.temp_dir / "merged.mp4"
            try:
                cmd = [
                    'ffmpeg', '-y',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', str(concat_file),
                    '-c', 'copy',
                    str(temp_video)
                ]
                subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)

                # Add audio with copy
                cmd = [
                    'ffmpeg', '-y',
                    '-i', str(temp_video),
                    '-i', voice_path,
                    '-c:v', 'copy',
                    '-c:a', 'copy',
                    '-shortest',
                    '-movflags', '+faststart',
                    output_path
                ]
                subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)

                if verbose:
                    print(f"   Used -c copy (INSTANT!)")

            except:
                # Copy failed, re-encode (still fast)
                if verbose:
                    print(f"   Copy failed, re-encoding...")

                cmd = [
                    'ffmpeg', '-y',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', str(concat_file),
                    '-i', voice_path,
                    '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast',
                    '-crf', '35',
                    '-c:a', 'copy',
                    '-shortest',
                    '-pix_fmt', 'yuv420p',
                    '-movflags', '+faststart',
                    output_path
                ]
                subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=1200)

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
                'media_count': len(media_paths),
                'voice_duration': voice_duration
            }

        # CASE C: MIXED (images + videos) → Must encode
        else:
            if verbose:
                print(f"   Strategy: Mixed media - encoding required")

            # For mixed media, we need to pre-process into common format
            # This is less common but still needs to work
            duration_per_item = voice_duration / len(media_paths)
            prepared_clips = []

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
                        '-crf', '35',
                        '-r', '2',
                        '-tune', 'stillimage',
                        '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
                        '-pix_fmt', 'yuv420p',
                        '-an',
                        str(clip_output)
                    ]
                else:  # video
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', media_path,
                        '-t', str(duration_per_item),
                        '-c:v', 'libx264',
                        '-preset', 'ultrafast',
                        '-crf', '35',
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

            # Concat with -c copy
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
                '-c', 'copy',
                str(temp_video)
            ]
            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)

            # Add audio
            cmd = [
                'ffmpeg', '-y',
                '-i', str(temp_video),
                '-i', voice_path,
                '-c:v', 'copy',
                '-c:a', 'copy',
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


# Test function
if __name__ == '__main__':
    assembler = VideoAssembler()
    print("VideoAssembler initialized successfully!")

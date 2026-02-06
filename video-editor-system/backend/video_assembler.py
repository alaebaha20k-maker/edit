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
        Returns: {'encoder': 'h264_nvenc'/'libx264', 'preset': '...', 'hw_type': 'nvidia/intel/amd/cpu'}
        """
        # Try NVIDIA GPU (fastest if available)
        try:
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-encoders'],
                capture_output=True, text=True, timeout=5
            )
            encoders = result.stdout

            # Check for hardware encoders
            if 'h264_nvenc' in encoders:
                print("✅ NVIDIA GPU encoder detected (h264_nvenc)")
                return {'encoder': 'h264_nvenc', 'preset': 'p4', 'hw_type': 'nvidia'}
            elif 'h264_qsv' in encoders:
                print("✅ Intel Quick Sync encoder detected (h264_qsv)")
                return {'encoder': 'h264_qsv', 'preset': 'veryfast', 'hw_type': 'intel'}
            elif 'h264_amf' in encoders:
                print("✅ AMD GPU encoder detected (h264_amf)")
                return {'encoder': 'h264_amf', 'preset': 'speed', 'hw_type': 'amd'}
        except:
            pass

        # Fallback to CPU encoding (still optimized)
        print("ℹ️ Using CPU encoder (libx264) - no GPU detected")
        return {'encoder': 'libx264', 'preset': 'ultrafast', 'hw_type': 'cpu'}

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
        ULTRA-FAST video assembly - ONE PASS, NO INTERMEDIATE FILES!
        Creates final video directly from images/videos + voice in single FFmpeg command
        """
        start_time = __import__('time').time()

        if verbose:
            print(f"\n{'='*60}")
            print(f"⚡ ULTRA-FAST VIDEO ASSEMBLY (Single-Pass Mode)")
            print(f"{'='*60}")

        # Get voice duration
        voice_duration = self.get_audio_duration(voice_path)
        voice_minutes = int(voice_duration // 60)
        voice_seconds = int(voice_duration % 60)

        if verbose:
            print(f"\n📊 Analyzing...")
            print(f"   Voice: {voice_minutes}m {voice_seconds}s")
            print(f"   Media: {len(media_paths)} files")

        if voice_duration <= 0:
            raise ValueError("Voice audio duration is 0 or invalid")
        if len(media_paths) == 0:
            raise ValueError("No media items provided")

        # Calculate duration per media
        duration_per_item = voice_duration / len(media_paths)

        # Parse resolution
        width, height = resolution.split('x')

        if verbose:
            print(f"\n⚡ Creating video in ONE PASS (ULTRA FAST!)...")
            print(f"   Method: Direct slideshow + audio merge")
            print(f"   Duration per item: {duration_per_item:.2f}s")

        # BUILD ULTRA-FAST SINGLE-PASS COMMAND
        # This creates the entire video in ONE FFmpeg command!

        try:
            # Create filter complex for all images/videos
            filter_parts = []
            input_count = 0

            for i, media_path in enumerate(media_paths):
                ext = os.path.splitext(media_path)[1].lower()
                is_image = ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp']

                if is_image:
                    # Image: scale + pad + loop for duration
                    filter_parts.append(
                        f"[{input_count}:v]loop=loop=-1:size=1:start=0,"
                        f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=fast_bilinear,"
                        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
                        f"setpts=N/(10*TB),"  # 10fps for images
                        f"trim=duration={duration_per_item}[v{i}]"
                    )
                else:
                    # Video: scale + pad + trim or loop
                    filter_parts.append(
                        f"[{input_count}:v]scale={width}:{height}:force_original_aspect_ratio=decrease:flags=fast_bilinear,"
                        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
                        f"loop=loop=-1:size=1,"
                        f"trim=duration={duration_per_item},"
                        f"setpts=N/(24*TB)[v{i}]"  # 24fps for videos
                    )
                input_count += 1

            # Concat all streams
            concat_inputs = ''.join([f"[v{i}]" for i in range(len(media_paths))])
            filter_complex = ';'.join(filter_parts) + f";{concat_inputs}concat=n={len(media_paths)}:v=1:a=0[vout]"

            # Build command with ALL inputs
            cmd = ['ffmpeg', '-y']

            # Add all media inputs
            for media_path in media_paths:
                cmd.extend(['-i', media_path])

            # Add voice input
            cmd.extend(['-i', voice_path])

            # Add filter complex
            cmd.extend([
                '-filter_complex', filter_complex,
                '-map', '[vout]',
                '-map', f'{len(media_paths)}:a',  # Map audio from voice
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '23',
                '-r', '10',  # 10fps output (FAST!)
                '-c:a', 'aac',
                '-b:a', '192k',
                '-shortest',
                '-movflags', '+faststart',
                output_path
            ])

            if verbose:
                print(f"   Running single-pass encode...")

            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=1200)

            elapsed = __import__('time').time() - start_time

            if verbose:
                print(f"\n{'='*60}")
                print(f"✅ VIDEO ASSEMBLY COMPLETE!")
                print(f"{'='*60}")
                print(f"   Time: {elapsed:.1f}s")
                print(f"   Output: {output_path}")

            return {
                'success': True,
                'output_path': output_path,
                'voice_duration': voice_duration,
                'media_count': len(media_paths),
                'time_elapsed': elapsed
            }

        except subprocess.CalledProcessError as e:
            raise Exception(f"FFmpeg single-pass failed: {e.stderr[-1000:]}")
        except Exception as e:
            raise Exception(f"Video assembly failed: {str(e)}")


# Test function
if __name__ == '__main__':
    assembler = VideoAssembler()
    print("VideoAssembler initialized successfully!")

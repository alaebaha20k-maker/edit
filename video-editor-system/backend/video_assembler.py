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
        Assemble final video from voice and media

        Args:
            voice_path: Path to voice audio file
            media_paths: List of media file paths (in order)
            output_path: Output video path
            resolution: Video resolution (WxH)
            verbose: Print progress

        Returns:
            Dict with result info
        """
        start_time = __import__('time').time()

        if verbose:
            print(f"\n{'='*60}")
            print(f"🎬 VIDEO ASSEMBLY STARTED")
            print(f"{'='*60}")

        # Step 1: Get voice duration
        if verbose:
            print(f"\n📊 Step 1: Analyzing voice audio...")

        voice_duration = self.get_audio_duration(voice_path)
        voice_minutes = int(voice_duration // 60)
        voice_seconds = int(voice_duration % 60)

        if verbose:
            print(f"   Voice duration: {voice_minutes}m {voice_seconds}s ({voice_duration:.2f}s)")
            print(f"   Media items: {len(media_paths)}")

        if voice_duration <= 0:
            raise ValueError("Voice audio duration is 0 or invalid")

        if len(media_paths) == 0:
            raise ValueError("No media items provided")

        # Step 2: Calculate media durations
        if verbose:
            print(f"\n📐 Step 2: Calculating media durations...")

        media_durations = self.calculate_media_durations(
            voice_duration,
            len(media_paths),
            distribution='equal'
        )

        duration_per_item = voice_duration / len(media_paths)
        if verbose:
            print(f"   Duration per media: {duration_per_item:.2f}s")

        # Step 3: Prepare media clips
        if verbose:
            print(f"\n🎨 Step 3: Preparing media clips...")

        prepared_clips = []
        for i, (media_path, duration) in enumerate(zip(media_paths, media_durations)):
            if verbose:
                print(f"   [{i+1}/{len(media_paths)}] Processing: {os.path.basename(media_path)}")

            # Determine media type
            ext = os.path.splitext(media_path)[1].lower()
            media_type = 'image' if ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp'] else 'video'

            # Prepare clip
            clip_output = self.temp_dir / f"clip_{i:03d}.mp4"
            success = self.prepare_media_clip(
                media_path=media_path,
                duration=duration,
                output_path=str(clip_output),
                media_type=media_type,
                resolution=resolution
            )

            if success:
                prepared_clips.append(str(clip_output))
                if verbose:
                    print(f"      ✅ Prepared ({duration:.2f}s)")
            else:
                if verbose:
                    print(f"      ⚠️ Failed to prepare, skipping")

        if len(prepared_clips) == 0:
            raise ValueError("No media clips were successfully prepared")

        # Step 4: Concatenate video clips
        if verbose:
            print(f"\n🔗 Step 4: Concatenating video clips...")

        concat_file = self.temp_dir / "concat_list.txt"
        with open(concat_file, 'w') as f:
            for clip_path in prepared_clips:
                f.write(f"file '{os.path.abspath(clip_path)}'\n")

        temp_video = self.temp_dir / "temp_video.mp4"

        try:
            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', str(concat_file),
                '-c', 'copy',
                str(temp_video)
            ]

            if verbose:
                print(f"   Concatenating {len(prepared_clips)} clips...")

            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)

            if verbose:
                print(f"   ✅ Video concatenated")

        except subprocess.TimeoutExpired:
            raise Exception(f"Concatenation timeout after 5 minutes!")
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to concatenate videos: {e.stderr[-500:]}")

        # Step 5: Combine video with voice audio
        if verbose:
            print(f"\n🎵 Step 5: Adding voice audio...")

        try:
            cmd = [
                'ffmpeg', '-y',
                '-i', str(temp_video),
                '-i', voice_path,
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-map', '0:v:0',
                '-map', '1:a:0',
                '-shortest',  # Use shortest duration (should match)
                output_path
            ]

            if verbose:
                print(f"   Merging audio with video...")

            subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)

            if verbose:
                print(f"   ✅ Audio added to video")

        except subprocess.TimeoutExpired:
            raise Exception(f"Audio merge timeout after 5 minutes!")
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to add audio: {e.stderr[-500:]}")

        # Step 6: Cleanup temp files
        if verbose:
            print(f"\n🧹 Step 6: Cleaning up...")

        for clip_path in prepared_clips:
            try:
                os.remove(clip_path)
            except:
                pass

        try:
            os.remove(concat_file)
            os.remove(temp_video)
        except:
            pass

        if verbose:
            print(f"   ✅ Temp files removed")

        # Final stats
        end_time = __import__('time').time()
        total_time = end_time - start_time

        final_duration = self.get_audio_duration(output_path)
        final_size = os.path.getsize(output_path)

        if verbose:
            print(f"\n{'='*60}")
            print(f"✅ VIDEO ASSEMBLY COMPLETE!")
            print(f"{'='*60}")
            print(f"   Output: {output_path}")
            print(f"   Duration: {int(final_duration // 60)}m {int(final_duration % 60)}s")
            print(f"   Size: {final_size / (1024*1024):.2f} MB")
            print(f"   Processing time: {total_time:.1f}s")
            print(f"{'='*60}\n")

        return {
            'output_path': output_path,
            'duration_seconds': final_duration,
            'file_size_mb': final_size / (1024*1024),
            'processing_time': total_time,
            'media_count': len(prepared_clips),
            'voice_duration': voice_duration
        }


# Test function
if __name__ == '__main__':
    assembler = VideoAssembler()
    print("VideoAssembler initialized successfully!")

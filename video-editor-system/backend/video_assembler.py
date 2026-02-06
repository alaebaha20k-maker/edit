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
                # ULTRA-FAST image to video conversion
                # Use 1fps input instead of 30fps = 30x FASTER!
                # 12min video: 720 frames instead of 21,600 frames!
                cmd = [
                    'ffmpeg', '-y',
                    '-loop', '1',
                    '-framerate', '1',  # 1fps input = MUCH faster encoding!
                    '-i', media_path,
                    '-c:v', 'libx264',
                    '-t', str(duration),
                    '-pix_fmt', 'yuv420p',
                    '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1',
                    '-r', '24',  # Output 24fps (standard, less than 30fps)
                    '-preset', 'ultrafast',  # Fastest preset!
                    '-tune', 'stillimage',  # Optimized for still images
                    '-crf', '28',  # Higher CRF = faster encoding
                    '-g', '48',  # Keyframe every 2 seconds
                    output_path
                ]
            else:
                # Process video clip - Smart duration handling
                # Get video duration first
                video_duration = self._get_duration_ffprobe(media_path)

                if video_duration >= duration:
                    # Video is longer than needed - trim to exact duration
                    cmd = [
                        'ffmpeg', '-y',
                        '-i', media_path,
                        '-t', str(duration),  # Cut to exact duration
                        '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1',
                        '-c:v', 'libx264',
                        '-preset', 'ultrafast',  # Fastest encoding!
                        '-crf', '28',  # Higher CRF = faster
                        '-r', '24',  # 24fps output
                        '-an',  # Remove audio from video clips
                        output_path
                    ]
                else:
                    # Video is shorter than needed - loop it to fill duration
                    loops_needed = int(duration / video_duration) + 1
                    cmd = [
                        'ffmpeg', '-y',
                        '-stream_loop', str(loops_needed),  # Loop video
                        '-i', media_path,
                        '-t', str(duration),  # Cut to exact duration
                        '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1',
                        '-c:v', 'libx264',
                        '-preset', 'ultrafast',  # Fastest encoding!
                        '-crf', '28',  # Higher CRF = faster
                        '-r', '24',  # 24fps output
                        '-an',  # Remove audio from video clips
                        output_path
                    ]

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return True

        except subprocess.CalledProcessError as e:
            print(f"❌ FFmpeg error preparing media: {e.stderr}")
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

            subprocess.run(cmd, capture_output=True, text=True, check=True)

            if verbose:
                print(f"   ✅ Video concatenated")

        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to concatenate videos: {e.stderr}")

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

            subprocess.run(cmd, capture_output=True, text=True, check=True)

            if verbose:
                print(f"   ✅ Audio added to video")

        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to add audio: {e.stderr}")

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

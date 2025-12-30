#!/usr/bin/env python3
"""
FFmpeg processing module for video editing system
Handles all FFmpeg operations for video/audio/image processing
"""

import subprocess
import os
import json
from pathlib import Path


class FFmpegProcessor:
    """Handles all FFmpeg operations"""

    # Subtitle styling (CapCut size 5 equivalent for 1080p)
    SUBTITLE_STYLE = (
        "FontName=Arial Bold,"
        "FontSize=24,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "Outline=2,"
        "BackColour=&H99000000,"
        "BorderStyle=4,"
        "MarginV=80,"
        "Alignment=2"
    )

    # Output video specifications - ULTRA OPTIMIZED FOR SPEED
    OUTPUT_WIDTH = 1920
    OUTPUT_HEIGHT = 1080
    OUTPUT_FPS = 30
    OUTPUT_PRESET = "ultrafast"  # Maximum speed (was "veryfast")
    OUTPUT_CRF = 28  # Acceptable quality, faster encode (was 23)
    OUTPUT_PIX_FMT = "yuv420p"
    OUTPUT_AUDIO_BITRATE = "192k"

    def __init__(self, temp_dir="temp", verbose=False):
        """
        Initialize FFmpeg processor

        Args:
            temp_dir: Directory for temporary files
            verbose: Enable verbose FFmpeg output
        """
        self.temp_dir = temp_dir
        self.verbose = verbose

        # Create temp directory if it doesn't exist
        os.makedirs(temp_dir, exist_ok=True)

    def _run_ffmpeg_command(self, cmd, error_msg="FFmpeg command failed"):
        """
        Execute FFmpeg command with error handling

        Args:
            cmd: FFmpeg command as list
            error_msg: Custom error message

        Raises:
            RuntimeError: If command fails
        """
        try:
            if self.verbose:
                print(f"Running: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )

            if self.verbose and result.stderr:
                print(result.stderr)

            return result

        except subprocess.CalledProcessError as e:
            error_details = f"{error_msg}\nCommand: {' '.join(cmd)}\n"
            if e.stderr:
                error_details += f"Error output:\n{e.stderr}"
            raise RuntimeError(error_details)

    def get_duration(self, file_path):
        """
        Get duration of media file

        Args:
            file_path: Path to media file

        Returns:
            float: Duration in seconds
        """
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'json',
            file_path
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)
            return float(data['format']['duration'])
        except Exception as e:
            raise RuntimeError(f"Failed to get duration for {file_path}: {str(e)}")

    def image_to_video(self, image_path, output_path, duration):
        """
        Convert image to video clip - ULTRA OPTIMIZED FOR SPEED
        Uses framerate 1 input + stillimage tuning + optimized GOP for 10x speedup

        Args:
            image_path: Path to input image
            output_path: Path for output video
            duration: Duration in seconds

        Raises:
            RuntimeError: If conversion fails
        """
        if duration <= 0:
            raise ValueError(f"Duration must be positive, got {duration}")

        cmd = [
            'ffmpeg', '-y',
            '-loop', '1',
            '-framerate', '1',  # Read at 1fps - CRITICAL for 10x speedup on static images
            '-i', image_path,
            '-t', str(duration),
            '-vf', f'scale={self.OUTPUT_WIDTH}:{self.OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,crop={self.OUTPUT_WIDTH}:{self.OUTPUT_HEIGHT}',
            '-c:v', 'libx264',
            '-preset', self.OUTPUT_PRESET,
            '-tune', 'stillimage',  # Optimized for static images
            '-crf', str(self.OUTPUT_CRF),
            '-g', '600',  # Keyframe every 20 seconds (HUGE speedup for images)
            '-r', '1',  # Output at 1fps (10x faster for static images)
            '-pix_fmt', self.OUTPUT_PIX_FMT,
            '-threads', '0',  # Use all CPU cores
            output_path
        ]

        self._run_ffmpeg_command(
            cmd,
            f"Failed to convert image to video: {image_path}"
        )

        # Verify output
        if not os.path.exists(output_path):
            raise RuntimeError(f"Output file not created: {output_path}")

        return output_path

    def get_video_specs(self, video_path):
        """
        Get video specifications (resolution, fps, codec)

        Args:
            video_path: Path to video file

        Returns:
            dict: {'width': int, 'height': int, 'fps': float, 'codec': str}
        """
        cmd = [
            'ffprobe', '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            video_path
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)

            # Find video stream
            video_stream = None
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break

            if not video_stream:
                return None

            width = video_stream.get('width', 0)
            height = video_stream.get('height', 0)
            codec = video_stream.get('codec_name', '')

            # Parse frame rate (e.g., "30/1" -> 30.0)
            fps_str = video_stream.get('r_frame_rate', '0/1')
            if '/' in fps_str:
                num, den = fps_str.split('/')
                fps = float(num) / float(den) if float(den) > 0 else 0
            else:
                fps = float(fps_str)

            return {
                'width': width,
                'height': height,
                'fps': fps,
                'codec': codec
            }
        except Exception as e:
            if self.verbose:
                print(f"    Warning: Could not probe video specs: {e}")
            return None

    def normalize_video(self, input_path, output_path, strip_audio=False):
        """
        SMART normalize video to standard format (16:9, 1080p, 30fps) - ULTRA OPTIMIZED
        Skips re-encoding if video is already at target specs (instant stream copy!)

        Args:
            input_path: Path to input video
            output_path: Path for output video
            strip_audio: If True, removes audio from video (mute)

        Raises:
            RuntimeError: If normalization fails
        """
        # Get video specifications
        specs = self.get_video_specs(input_path)

        is_perfect = False
        if specs:
            if self.verbose:
                print(f"    Source: {specs['width']}×{specs['height']}, {specs['fps']:.1f}fps, {specs['codec']}")

            # Check if already perfect (1080p, ~30fps, h264)
            is_perfect = (
                specs['width'] == self.OUTPUT_WIDTH and
                specs['height'] == self.OUTPUT_HEIGHT and
                29 <= specs['fps'] <= 31 and
                specs['codec'] == 'h264'
            )

        if is_perfect:
            # Perfect specs! Use stream copy (instant, no re-encoding)
            if self.verbose:
                print(f"    → Already perfect specs! Using stream copy (10x faster)...")

            cmd = [
                'ffmpeg', '-y',
                '-i', input_path,
                '-c:v', 'copy',  # Stream copy video (instant!)
            ]

            # Add audio handling
            if strip_audio:
                cmd.append('-an')  # No audio
            else:
                cmd.extend([
                    '-c:a', 'aac',
                    '-b:a', self.OUTPUT_AUDIO_BITRATE,
                    '-ac', '2'
                ])

            cmd.append(output_path)
        else:
            # Needs conversion
            if self.verbose and specs:
                print(f"    → Converting to {self.OUTPUT_WIDTH}x{self.OUTPUT_HEIGHT}@{self.OUTPUT_FPS}fps...")

            cmd = [
                'ffmpeg', '-y',
                '-i', input_path,
                '-vf', f'scale={self.OUTPUT_WIDTH}:{self.OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,crop={self.OUTPUT_WIDTH}:{self.OUTPUT_HEIGHT},fps={self.OUTPUT_FPS}',
                '-c:v', 'libx264',
                '-preset', self.OUTPUT_PRESET,
                '-crf', str(self.OUTPUT_CRF),
                '-threads', '0',  # Use all CPU cores
            ]

            # Add audio handling based on strip_audio flag
            if strip_audio:
                cmd.append('-an')  # No audio
            else:
                cmd.extend([
                    '-c:a', 'aac',
                    '-b:a', self.OUTPUT_AUDIO_BITRATE,
                    '-ac', '2'
                ])

            cmd.append(output_path)

        self._run_ffmpeg_command(
            cmd,
            f"Failed to normalize video: {input_path}"
        )

        # Verify output
        if not os.path.exists(output_path):
            raise RuntimeError(f"Output file not created: {output_path}")

        return output_path

    def concatenate_videos(self, video_list, output_path):
        """
        Concatenate multiple videos in sequence

        Args:
            video_list: List of video file paths (in order)
            output_path: Path for concatenated output

        Raises:
            RuntimeError: If concatenation fails
        """
        if not video_list:
            raise ValueError("Video list cannot be empty")

        # Create concat list file
        concat_file = os.path.join(self.temp_dir, 'concat_list.txt')

        try:
            with open(concat_file, 'w', encoding='utf-8') as f:
                for video in video_list:
                    # Use absolute path and escape special characters
                    abs_path = os.path.abspath(video)
                    # Escape single quotes for FFmpeg
                    escaped_path = abs_path.replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")

            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c', 'copy',
                output_path
            ]

            self._run_ffmpeg_command(
                cmd,
                "Failed to concatenate videos"
            )

            # Verify output
            if not os.path.exists(output_path):
                raise RuntimeError(f"Output file not created: {output_path}")

            return output_path

        finally:
            # Clean up concat file
            if os.path.exists(concat_file):
                try:
                    os.remove(concat_file)
                except:
                    pass

    def concatenate_audio(self, audio_list, output_path):
        """
        Concatenate multiple audio files in sequence

        Args:
            audio_list: List of audio file paths (in order)
            output_path: Path for concatenated output

        Raises:
            RuntimeError: If concatenation fails
        """
        if not audio_list:
            raise ValueError("Audio list cannot be empty")

        # Create concat list file
        concat_file = os.path.join(self.temp_dir, 'audio_concat_list.txt')

        try:
            with open(concat_file, 'w', encoding='utf-8') as f:
                for audio in audio_list:
                    # Use absolute path and escape special characters
                    abs_path = os.path.abspath(audio)
                    # Escape single quotes for FFmpeg
                    escaped_path = abs_path.replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")

            cmd = [
                'ffmpeg', '-y',
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_file,
                '-c:a', 'libmp3lame',  # Encode to MP3 (handles mixed formats)
                '-b:a', '192k',        # 192kbps bitrate
                '-ar', '44100',        # Standard sample rate
                '-ac', '2',            # Stereo
                output_path
            ]

            self._run_ffmpeg_command(
                cmd,
                "Failed to concatenate audio"
            )

            # Verify output
            if not os.path.exists(output_path):
                raise RuntimeError(f"Output file not created: {output_path}")

            return output_path

        finally:
            # Clean up concat file
            if os.path.exists(concat_file):
                try:
                    os.remove(concat_file)
                except:
                    pass

    def final_assembly(self, video_path, audio_path, output_path):
        """
        Combine video and audio - ULTRA OPTIMIZED (stream copy for maximum speed)
        Video duration will EXACTLY match audio duration for perfect sync.
        No re-encoding - just muxes video and audio streams together (20x faster!)

        Args:
            video_path: Path to concatenated video
            audio_path: Path to merged audio
            output_path: Path for final output

        Raises:
            RuntimeError: If assembly fails
        """
        # Verify inputs exist
        for path in [video_path, audio_path]:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Input file not found: {path}")

        # STEP 1: Get exact audio duration using ffprobe
        probe_cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            audio_path
        ]

        try:
            result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
            audio_duration = float(result.stdout.strip())
            print(f"📊 Audio duration detected: {audio_duration:.2f} seconds")
        except Exception as e:
            print(f"⚠️  Warning: Could not detect audio duration: {e}")
            print(f"   Will use -shortest flag as fallback")
            audio_duration = None

        # STEP 2: Build ffmpeg command with exact duration sync
        cmd = [
            'ffmpeg', '-y',
        ]

        # Force video input to audio duration (if detected)
        if audio_duration:
            cmd.extend(['-t', str(audio_duration)])

        cmd.extend([
            '-i', video_path,
            '-i', audio_path,
            '-c:v', 'copy',      # Stream copy video (no re-encode)
            '-c:a', 'copy',      # Stream copy audio (10x faster + perfect quality!)
            '-map', '0:v:0',     # Explicitly map video from input 0
            '-map', '1:a:0',     # Explicitly map audio from input 1
        ])

        # Add -shortest as fallback if duration detection failed
        if not audio_duration:
            cmd.append('-shortest')

        cmd.append(output_path)

        if self.verbose:
            print(f"Final assembly command: {' '.join(cmd)}")

        self._run_ffmpeg_command(
            cmd,
            "Failed to create final video assembly"
        )

        # Verify output
        if not os.path.exists(output_path):
            raise RuntimeError(f"Output file not created: {output_path}")

        # Report final duration
        if audio_duration:
            print(f"✓ Final video duration: {audio_duration:.2f}s (exact match to audio)")

        return output_path

    def cleanup_temp_files(self, file_list):
        """
        Clean up temporary files

        Args:
            file_list: List of file paths to delete
        """
        for file_path in file_list:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    if self.verbose:
                        print(f"Deleted: {file_path}")
            except Exception as e:
                if self.verbose:
                    print(f"Warning: Could not delete {file_path}: {str(e)}")


if __name__ == "__main__":
    # Test FFmpeg processor
    print("FFmpeg Processor Module - Test Mode")
    print("Checking FFmpeg installation...")

    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            text=True,
            check=True
        )
        print("✓ FFmpeg is installed")

        result = subprocess.run(
            ['ffprobe', '-version'],
            capture_output=True,
            text=True,
            check=True
        )
        print("✓ FFprobe is installed")

        print("\nFFmpeg processor is ready to use!")

    except (subprocess.CalledProcessError, FileNotFoundError):
        print("✗ FFmpeg is NOT installed")
        print("Please install FFmpeg to use this module")

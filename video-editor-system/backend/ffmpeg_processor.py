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
        Uses stillimage tuning and optimized GOP size for static images

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
            '-i', image_path,
            '-t', str(duration),
            '-vf', f'scale={self.OUTPUT_WIDTH}:{self.OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,crop={self.OUTPUT_WIDTH}:{self.OUTPUT_HEIGHT}',
            '-c:v', 'libx264',
            '-preset', self.OUTPUT_PRESET,
            '-tune', 'stillimage',  # Optimized for static images (30% faster)
            '-crf', str(self.OUTPUT_CRF),
            '-g', '600',  # Keyframe every 20 seconds (HUGE speedup for images)
            '-r', str(self.OUTPUT_FPS),
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

    def normalize_video(self, input_path, output_path):
        """
        Normalize video to standard format (16:9, 1080p, 30fps) - OPTIMIZED FOR SPEED

        Args:
            input_path: Path to input video
            output_path: Path for output video

        Raises:
            RuntimeError: If normalization fails
        """
        cmd = [
            'ffmpeg', '-y',
            '-i', input_path,
            '-vf', f'scale={self.OUTPUT_WIDTH}:{self.OUTPUT_HEIGHT}:force_original_aspect_ratio=increase,crop={self.OUTPUT_WIDTH}:{self.OUTPUT_HEIGHT},fps={self.OUTPUT_FPS}',
            '-c:v', 'libx264',
            '-preset', self.OUTPUT_PRESET,
            '-crf', str(self.OUTPUT_CRF),
            '-threads', '0',  # Use all CPU cores
            '-c:a', 'aac',
            '-b:a', self.OUTPUT_AUDIO_BITRATE,
            '-ac', '2',
            output_path
        ]

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
                '-c', 'copy',
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
        Combine video and audio - ULTRA OPTIMIZED (no captions for maximum speed)

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

        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-i', audio_path,
            '-c:v', 'libx264',
            '-preset', self.OUTPUT_PRESET,
            '-crf', str(self.OUTPUT_CRF),
            '-threads', '0',  # Use all CPU cores
            '-r', str(self.OUTPUT_FPS),
            '-pix_fmt', self.OUTPUT_PIX_FMT,
            '-c:a', 'aac',
            '-b:a', self.OUTPUT_AUDIO_BITRATE,
            '-ac', '2',
            '-shortest',
            output_path
        ]

        self._run_ffmpeg_command(
            cmd,
            "Failed to create final video assembly"
        )

        # Verify output
        if not os.path.exists(output_path):
            raise RuntimeError(f"Output file not created: {output_path}")

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

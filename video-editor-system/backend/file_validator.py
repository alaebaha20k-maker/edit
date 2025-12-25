#!/usr/bin/env python3
"""
File validation module for video editing system
Validates all input files for existence, format, and integrity
"""

import os
import subprocess
import json
from pathlib import Path

class FileValidator:
    """Validates media files for processing"""

    VALID_VIDEO_FORMATS = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv']
    VALID_IMAGE_FORMATS = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp']
    VALID_AUDIO_FORMATS = ['.mp3', '.wav', '.aac', '.m4a', '.ogg', '.flac']

    @staticmethod
    def validate_file_exists(file_path):
        """Check if file exists"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        if not os.path.isfile(file_path):
            raise ValueError(f"Path is not a file: {file_path}")

        if os.path.getsize(file_path) == 0:
            raise ValueError(f"File is empty: {file_path}")

        return True

    @staticmethod
    def validate_file_format(file_path, expected_type):
        """Validate file format matches expected type"""
        ext = os.path.splitext(file_path)[1].lower()

        if expected_type == 'video':
            if ext not in FileValidator.VALID_VIDEO_FORMATS:
                raise ValueError(
                    f"Invalid video format '{ext}'. "
                    f"Supported: {', '.join(FileValidator.VALID_VIDEO_FORMATS)}"
                )
        elif expected_type == 'image':
            if ext not in FileValidator.VALID_IMAGE_FORMATS:
                raise ValueError(
                    f"Invalid image format '{ext}'. "
                    f"Supported: {', '.join(FileValidator.VALID_IMAGE_FORMATS)}"
                )
        elif expected_type == 'audio':
            if ext not in FileValidator.VALID_AUDIO_FORMATS:
                raise ValueError(
                    f"Invalid audio format '{ext}'. "
                    f"Supported: {', '.join(FileValidator.VALID_AUDIO_FORMATS)}"
                )
        else:
            raise ValueError(f"Unknown file type: {expected_type}")

        return True

    @staticmethod
    def probe_media_file(file_path):
        """Use FFprobe to validate media file integrity"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration,size,format_name',
                '-show_entries', 'stream=codec_type,codec_name,width,height',
                '-of', 'json',
                file_path
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )

            data = json.loads(result.stdout)

            if 'format' not in data:
                raise ValueError(f"Invalid media file: {file_path}")

            return data

        except subprocess.TimeoutExpired:
            raise ValueError(f"File probing timeout: {file_path}")
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Corrupted or invalid media file: {file_path}\nError: {e.stderr}")
        except json.JSONDecodeError:
            raise ValueError(f"Failed to parse media file info: {file_path}")

    @staticmethod
    def validate_video_file(file_path):
        """Comprehensive video file validation"""
        FileValidator.validate_file_exists(file_path)
        FileValidator.validate_file_format(file_path, 'video')

        probe_data = FileValidator.probe_media_file(file_path)

        # Check for video stream
        has_video = False
        for stream in probe_data.get('streams', []):
            if stream.get('codec_type') == 'video':
                has_video = True
                break

        if not has_video:
            raise ValueError(f"No video stream found in file: {file_path}")

        return True

    @staticmethod
    def validate_image_file(file_path):
        """Comprehensive image file validation"""
        FileValidator.validate_file_exists(file_path)
        FileValidator.validate_file_format(file_path, 'image')

        # Try to read image dimensions using FFprobe
        try:
            probe_data = FileValidator.probe_media_file(file_path)

            for stream in probe_data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    width = stream.get('width')
                    height = stream.get('height')

                    if not width or not height:
                        raise ValueError(f"Cannot determine image dimensions: {file_path}")

                    if width < 100 or height < 100:
                        raise ValueError(f"Image too small (min 100x100): {file_path}")

                    return True

            raise ValueError(f"Invalid image file: {file_path}")

        except Exception as e:
            raise ValueError(f"Image validation failed: {file_path}\nError: {str(e)}")

    @staticmethod
    def validate_audio_file(file_path):
        """Comprehensive audio file validation"""
        FileValidator.validate_file_exists(file_path)
        FileValidator.validate_file_format(file_path, 'audio')

        probe_data = FileValidator.probe_media_file(file_path)

        # Check for audio stream
        has_audio = False
        for stream in probe_data.get('streams', []):
            if stream.get('codec_type') == 'audio':
                has_audio = True
                break

        if not has_audio:
            raise ValueError(f"No audio stream found in file: {file_path}")

        # Check duration
        duration = float(probe_data.get('format', {}).get('duration', 0))
        if duration <= 0:
            raise ValueError(f"Invalid audio duration: {file_path}")

        return True

    @staticmethod
    def validate_all_files(visual_media, audio_files):
        """Validate all input files"""
        errors = []

        # Validate visual media
        for idx, item in enumerate(visual_media):
            try:
                file_path = item.get('path')
                file_type = item.get('type')

                if not file_path:
                    errors.append(f"Visual media #{idx+1}: Missing file path")
                    continue

                if file_type == 'video':
                    FileValidator.validate_video_file(file_path)
                elif file_type == 'image':
                    FileValidator.validate_image_file(file_path)
                else:
                    errors.append(f"Visual media #{idx+1}: Unknown type '{file_type}'")

            except Exception as e:
                errors.append(f"Visual media #{idx+1}: {str(e)}")

        # Validate audio files
        for idx, item in enumerate(audio_files):
            try:
                file_path = item.get('path')

                if not file_path:
                    errors.append(f"Audio file #{idx+1}: Missing file path")
                    continue

                FileValidator.validate_audio_file(file_path)

            except Exception as e:
                errors.append(f"Audio file #{idx+1}: {str(e)}")

        if errors:
            error_msg = "File validation failed:\n" + "\n".join(errors)
            raise ValueError(error_msg)

        return True

    @staticmethod
    def check_ffmpeg_installed():
        """Check if FFmpeg and FFprobe are installed"""
        try:
            subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                check=True,
                timeout=5
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            raise RuntimeError(
                "FFmpeg not found. Please install FFmpeg:\n"
                "  Ubuntu/Debian: sudo apt install ffmpeg\n"
                "  MacOS: brew install ffmpeg\n"
                "  Windows: Download from https://ffmpeg.org/"
            )

        try:
            subprocess.run(
                ['ffprobe', '-version'],
                capture_output=True,
                check=True,
                timeout=5
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            raise RuntimeError("FFprobe not found. Please install FFmpeg package.")

        return True


def validate_files(visual_media, audio_files):
    """
    Main validation function

    Args:
        visual_media: List of dicts with 'rank', 'type', 'path'
        audio_files: List of dicts with 'rank', 'path'

    Returns:
        True if all files valid

    Raises:
        ValueError: If validation fails
        RuntimeError: If FFmpeg not installed
    """
    FileValidator.check_ffmpeg_installed()
    return FileValidator.validate_all_files(visual_media, audio_files)


if __name__ == "__main__":
    # Test validation
    print("Testing file validator...")

    try:
        FileValidator.check_ffmpeg_installed()
        print("✓ FFmpeg installed")
    except RuntimeError as e:
        print(f"✗ {e}")

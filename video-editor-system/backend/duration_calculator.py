#!/usr/bin/env python3
"""
Duration calculation module for video editing system
Calculates precise durations for all media elements
"""

import subprocess
import json
from typing import List, Dict


class DurationCalculator:
    """Calculates durations for video project elements"""

    @staticmethod
    def get_media_duration(file_path):
        """
        Get duration of video or audio file using FFprobe

        Args:
            file_path: Path to media file

        Returns:
            float: Duration in seconds

        Raises:
            ValueError: If duration cannot be determined
        """
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
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
            duration = float(data.get('format', {}).get('duration', 0))

            if duration <= 0:
                raise ValueError(f"Invalid duration for file: {file_path}")

            return duration

        except subprocess.TimeoutExpired:
            raise ValueError(f"Timeout getting duration: {file_path}")
        except subprocess.CalledProcessError as e:
            raise ValueError(f"Failed to get duration: {file_path}\nError: {e.stderr}")
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise ValueError(f"Invalid media file: {file_path}\nError: {str(e)}")

    @staticmethod
    def calculate_project_durations(videos, images, audio_files):
        """
        Calculate durations for entire video project

        Args:
            videos: List of video file paths
            images: List of image file paths (or dicts)
            audio_files: List of audio file paths

        Returns:
            dict: {
                'total_duration': Total project duration in seconds,
                'total_audio_duration': Sum of all audio durations,
                'total_video_duration': Sum of all video clip durations,
                'image_duration': Duration per image in seconds,
                'video_durations': List of individual video durations,
                'audio_durations': List of individual audio durations,
                'num_videos': Number of video clips,
                'num_images': Number of images,
                'num_audio': Number of audio files
            }

        Raises:
            ValueError: If calculation fails or results are invalid
        """

        if not audio_files:
            raise ValueError("At least one audio file is required")

        # Get all audio durations
        audio_durations = []
        for audio_path in audio_files:
            try:
                duration = DurationCalculator.get_media_duration(audio_path)
                audio_durations.append(duration)
            except Exception as e:
                raise ValueError(f"Failed to get audio duration: {audio_path}\n{str(e)}")

        total_audio_duration = sum(audio_durations)

        if total_audio_duration <= 0:
            raise ValueError("Total audio duration must be greater than 0")

        # Get all video durations
        video_durations = []
        if videos:
            for video_path in videos:
                try:
                    duration = DurationCalculator.get_media_duration(video_path)
                    video_durations.append(duration)
                except Exception as e:
                    raise ValueError(f"Failed to get video duration: {video_path}\n{str(e)}")

        total_video_duration = sum(video_durations)

        # Calculate remaining time for images
        remaining_time = total_audio_duration - total_video_duration

        # If videos are longer than audio, warn but continue (will be cut in final assembly)
        if remaining_time < 0:
            print(f"⚠️  WARNING: Videos ({total_video_duration:.2f}s) are longer than audio ({total_audio_duration:.2f}s)")
            print(f"   Video will be cut to {total_audio_duration:.2f}s in final assembly")
            remaining_time = 0  # No time for images

        # Calculate duration per image
        num_images = len(images) if images else 0

        if num_images > 0 and remaining_time > 0:
            image_duration = remaining_time / num_images

            if image_duration < 0.1:
                raise ValueError(
                    f"Image duration too short ({image_duration:.2f}s). "
                    f"Too many images for available time. "
                    f"Remaining time: {remaining_time:.2f}s, Images: {num_images}"
                )
        else:
            image_duration = 0

            # If no images but remaining time exists, warn
            if remaining_time > 0.1 and num_images == 0:
                print(
                    f"⚠️  WARNING: {remaining_time:.2f}s of audio will not have video. "
                    f"   Consider adding images or more video clips."
                )

        return {
            'total_duration': total_audio_duration,
            'total_audio_duration': total_audio_duration,
            'total_video_duration': total_video_duration,
            'image_duration': image_duration,
            'video_durations': video_durations,
            'audio_durations': audio_durations,
            'num_videos': len(video_durations),
            'num_images': num_images,
            'num_audio': len(audio_durations),
            'remaining_time_for_images': remaining_time
        }

    @staticmethod
    def format_duration(seconds):
        """
        Format duration in seconds to human-readable format

        Args:
            seconds: Duration in seconds

        Returns:
            str: Formatted duration (HH:MM:SS or MM:SS)
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"

    @staticmethod
    def print_duration_summary(durations):
        """Print formatted duration summary"""
        print("\n" + "="*60)
        print("DURATION CALCULATION SUMMARY")
        print("="*60)

        print(f"\n📊 Project Statistics:")
        print(f"  • Videos: {durations['num_videos']}")
        print(f"  • Images: {durations['num_images']}")
        print(f"  • Audio files: {durations['num_audio']}")

        print(f"\n⏱️  Duration Breakdown:")
        print(f"  • Total audio: {DurationCalculator.format_duration(durations['total_audio_duration'])} "
              f"({durations['total_audio_duration']:.2f}s)")

        if durations['num_videos'] > 0:
            print(f"  • Total video clips: {DurationCalculator.format_duration(durations['total_video_duration'])} "
                  f"({durations['total_video_duration']:.2f}s)")

        if durations['num_images'] > 0:
            print(f"  • Remaining time for images: "
                  f"{DurationCalculator.format_duration(durations['remaining_time_for_images'])} "
                  f"({durations['remaining_time_for_images']:.2f}s)")
            print(f"  • Duration per image: {DurationCalculator.format_duration(durations['image_duration'])} "
                  f"({durations['image_duration']:.2f}s)")

        print(f"\n🎬 Final video duration: {DurationCalculator.format_duration(durations['total_duration'])} "
              f"({durations['total_duration']:.2f}s)")

        print("="*60 + "\n")


def calculate_durations(video_paths, image_paths, audio_paths):
    """
    Main function to calculate durations

    Args:
        video_paths: List of video file paths
        image_paths: List of image file paths
        audio_paths: List of audio file paths

    Returns:
        dict: Duration calculation results
    """
    return DurationCalculator.calculate_project_durations(
        video_paths,
        image_paths,
        audio_paths
    )


if __name__ == "__main__":
    # Test duration calculator
    print("Duration Calculator Module - Test Mode")
    print("This module requires actual media files to test.")

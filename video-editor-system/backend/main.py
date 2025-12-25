#!/usr/bin/env python3
"""
Main orchestration script for video editing system
Coordinates all processing steps to create final video output
"""

import os
import sys
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from duration_calculator import DurationCalculator, calculate_durations
from ffmpeg_processor import FFmpegProcessor
from file_validator import validate_files
from utils import (
    ensure_directory_exists,
    clean_directory,
    get_file_size,
    format_time,
    generate_project_id,
    save_project_metadata,
    sort_by_rank,
    print_processing_step,
    print_success_message,
    print_error_message,
    print_warning_message
)


class VideoEditorSystem:
    """Complete video editing automation system"""

    def __init__(self, temp_dir="temp", output_dir="output", verbose=False):
        """
        Initialize video editing system

        Args:
            temp_dir: Directory for temporary files
            output_dir: Directory for final output
            verbose: Enable verbose output
        """
        self.temp_dir = ensure_directory_exists(temp_dir)
        self.output_dir = ensure_directory_exists(output_dir)
        self.verbose = verbose

        self.ffmpeg = FFmpegProcessor(temp_dir=temp_dir, verbose=verbose)
        self.temp_files = []  # Track temp files for cleanup

    def process_video_project(
        self,
        visual_media,
        audio_files,
        output_filename=None,
        cleanup_temp=True
    ):
        """
        Main processing pipeline for video project - ULTRA OPTIMIZED (No Captions)

        Args:
            visual_media: List of dicts with 'rank', 'type', 'path'
                         Example: [{'rank': 1, 'type': 'video', 'path': 'intro.mp4'}, ...]
            audio_files: List of dicts with 'rank', 'path'
                        Example: [{'rank': 1, 'path': 'narration.mp3'}, ...]
            output_filename: Custom output filename (optional)
            cleanup_temp: Clean up temporary files after processing

        Returns:
            dict: {
                'success': bool,
                'output_path': str,
                'project_id': str,
                'metadata_path': str,
                'duration': float,
                'file_size': str
            }

        Raises:
            ValueError: If input validation fails
            RuntimeError: If processing fails
        """

        project_id = generate_project_id()
        print("\n" + "="*60)
        print(f"🎬 VIDEO EDITING AUTOMATION SYSTEM")
        print(f"   Project ID: {project_id}")
        print("="*60)

        try:
            # STEP 1: Validate all files
            print_processing_step(1, 8, "Validating Input Files")
            validate_files(visual_media, audio_files)
            print(f"✓ All files validated successfully")
            print(f"  • Visual media: {len(visual_media)} files")
            print(f"  • Audio files: {len(audio_files)} files")

            # STEP 2: Sort by ranking
            print_processing_step(2, 8, "Sorting Files by Rank")
            visual_media = sort_by_rank(visual_media)
            audio_files = sort_by_rank(audio_files)
            print("✓ Files sorted by ranking")

            # Separate videos and images
            videos = [m for m in visual_media if m['type'] == 'video']
            images = [m for m in visual_media if m['type'] == 'image']

            print(f"  • Videos: {len(videos)}")
            print(f"  • Images: {len(images)}")

            # STEP 3: Calculate durations
            print_processing_step(3, 8, "Calculating Durations")

            durations = calculate_durations(
                [v['path'] for v in videos],
                [i['path'] for i in images],
                [a['path'] for a in audio_files]
            )

            DurationCalculator.print_duration_summary(durations)

            # STEP 4: Convert images to video clips
            print_processing_step(4, 8, "Converting Images to Video Clips")

            image_videos = []
            for idx, img in enumerate(images):
                print(f"  Processing image {idx+1}/{len(images)}: {os.path.basename(img['path'])}")

                output_path = os.path.join(self.temp_dir, f"image_video_{idx:03d}.mp4")
                self.ffmpeg.image_to_video(
                    img['path'],
                    output_path,
                    durations['image_duration']
                )

                image_videos.append(output_path)
                self.temp_files.append(output_path)

                print(f"    ✓ Created {durations['image_duration']:.2f}s video clip")

            print(f"✓ Converted {len(images)} images to video clips")

            # STEP 5: Normalize video clips
            print_processing_step(5, 8, "Normalizing Video Clips")

            normalized_videos = []
            for idx, vid in enumerate(videos):
                print(f"  Processing video {idx+1}/{len(videos)}: {os.path.basename(vid['path'])}")

                output_path = os.path.join(self.temp_dir, f"normalized_video_{idx:03d}.mp4")
                self.ffmpeg.normalize_video(vid['path'], output_path)

                normalized_videos.append(output_path)
                self.temp_files.append(output_path)

                print(f"    ✓ Normalized to 1080p@30fps")

            print(f"✓ Normalized {len(videos)} video clips")

            # STEP 6: Build concatenation sequence (maintain ranking order)
            print_processing_step(6, 8, "Building Video Sequence")

            concat_list = []
            video_idx = 0
            image_idx = 0

            for item in visual_media:
                if item['type'] == 'video':
                    concat_list.append(normalized_videos[video_idx])
                    video_idx += 1
                else:
                    concat_list.append(image_videos[image_idx])
                    image_idx += 1

            print(f"✓ Sequence built: {len(concat_list)} clips in ranked order")

            # STEP 7: Concatenate video clips
            print_processing_step(7, 8, "Concatenating Video Clips")

            concatenated_video = os.path.join(self.temp_dir, "concatenated_video.mp4")
            self.ffmpeg.concatenate_videos(concat_list, concatenated_video)
            self.temp_files.append(concatenated_video)

            print(f"✓ Video clips concatenated")

            # STEP 8: Merge audio files and create final video
            print_processing_step(8, 8, "Merging Audio & Creating Final Video")

            merged_audio = os.path.join(self.temp_dir, "merged_audio.mp3")
            self.ffmpeg.concatenate_audio(
                [a['path'] for a in audio_files],
                merged_audio
            )
            self.temp_files.append(merged_audio)

            print(f"✓ Audio files merged")

            # Create final video (no captions for maximum speed)
            if output_filename is None:
                output_filename = f"{project_id}_final.mp4"
            else:
                # Ensure .mp4 extension exists (prevent FFmpeg output format errors)
                if not output_filename.lower().endswith('.mp4'):
                    output_filename = f"{output_filename}.mp4"

            final_output = os.path.join(self.output_dir, output_filename)

            self.ffmpeg.final_assembly(
                concatenated_video,
                merged_audio,
                final_output
            )

            print(f"✓ Final video created")

            # Get final video info
            final_duration = self.ffmpeg.get_duration(final_output)
            final_size = get_file_size(final_output)

            # Save project metadata
            metadata = {
                'project_id': project_id,
                'output_file': output_filename,
                'duration_seconds': final_duration,
                'duration_formatted': format_time(final_duration),
                'file_size': final_size,
                'visual_media_count': len(visual_media),
                'videos_count': len(videos),
                'images_count': len(images),
                'audio_files_count': len(audio_files),
                'visual_media': visual_media,
                'audio_files': audio_files,
                'durations': durations
            }

            metadata_path = save_project_metadata(project_id, metadata, self.output_dir)

            # Clean up temporary files
            if cleanup_temp:
                print(f"\n🧹 Cleaning up temporary files...")
                self.ffmpeg.cleanup_temp_files(self.temp_files)
                print(f"   ✓ Cleaned up {len(self.temp_files)} temporary files")

            # Print success summary
            print_success_message("VIDEO PROCESSING COMPLETE!")

            print(f"📊 Project Summary:")
            print(f"  • Output file: {final_output}")
            print(f"  • Duration: {format_time(final_duration)} ({final_duration:.2f}s)")
            print(f"  • File size: {final_size}")
            print(f"  • Metadata: {metadata_path}")

            return {
                'success': True,
                'output_path': final_output,
                'project_id': project_id,
                'metadata_path': metadata_path,
                'duration': final_duration,
                'file_size': final_size
            }

        except Exception as e:
            print_error_message(f"Processing failed: {str(e)}")

            # Clean up on error
            if cleanup_temp:
                try:
                    self.ffmpeg.cleanup_temp_files(self.temp_files)
                except:
                    pass

            raise


def main():
    """Example usage of video editing system"""

    print("Video Editor System - Main Script\n")

    # Example project data
    visual_media = [
        {'rank': 1, 'type': 'video', 'path': 'sample_data/intro.mp4'},
        {'rank': 2, 'type': 'image', 'path': 'sample_data/slide1.jpg'},
        {'rank': 3, 'type': 'video', 'path': 'sample_data/demo.mp4'},
        {'rank': 4, 'type': 'image', 'path': 'sample_data/slide2.jpg'},
    ]

    audio_files = [
        {'rank': 1, 'path': 'sample_data/narration1.mp3'},
        {'rank': 2, 'path': 'sample_data/music.mp3'},
    ]

    # Initialize system
    editor = VideoEditorSystem(
        temp_dir="temp",
        output_dir="output",
        verbose=True
    )

    # Process video project
    try:
        result = editor.process_video_project(
            visual_media=visual_media,
            audio_files=audio_files,
            cleanup_temp=True
        )

        print("\n✅ Processing successful!")
        print(f"Output: {result['output_path']}")

    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()

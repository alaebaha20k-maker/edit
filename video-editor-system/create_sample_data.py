#!/usr/bin/env python3
"""
Generate sample test data for Video Editing Automation System
Creates test videos, images, and audio files using FFmpeg
"""

import os
import subprocess
import sys

def print_step(msg):
    print(f"\n{'='*70}")
    print(f"{msg}")
    print(f"{'='*70}\n")

def run_command(cmd, description):
    """Run FFmpeg command"""
    print(f"Creating: {description}")
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"✓ Created: {description}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Failed: {description}")
        print(f"Error: {e.stderr.decode()}")
        return False

def create_sample_videos():
    """Create sample video files"""
    print_step("Creating Sample Videos")

    output_dir = "sample_data"
    os.makedirs(output_dir, exist_ok=True)

    # Video 1: Intro (5 seconds, blue background with text)
    cmd1 = [
        'ffmpeg', '-y',
        '-f', 'lavfi',
        '-i', 'color=c=blue:s=1920x1080:d=5',
        '-vf', 'drawtext=text=\'INTRO VIDEO\':fontcolor=white:fontsize=72:x=(w-text_w)/2:y=(h-text_h)/2',
        '-c:v', 'libx264',
        '-preset', 'veryfast',
        '-pix_fmt', 'yuv420p',
        '-r', '30',
        f'{output_dir}/intro.mp4'
    ]
    run_command(cmd1, "intro.mp4 (5 seconds)")

    # Video 2: Demo (4 seconds, green background with moving text)
    cmd2 = [
        'ffmpeg', '-y',
        '-f', 'lavfi',
        '-i', 'color=c=green:s=1920x1080:d=4',
        '-vf', 'drawtext=text=\'DEMO VIDEO\':fontcolor=white:fontsize=72:x=(w-text_w)/2:y=(h-text_h)/2',
        '-c:v', 'libx264',
        '-preset', 'veryfast',
        '-pix_fmt', 'yuv420p',
        '-r', '30',
        f'{output_dir}/demo.mp4'
    ]
    run_command(cmd2, "demo.mp4 (4 seconds)")

    # Video 3: Outro (3 seconds, red background)
    cmd3 = [
        'ffmpeg', '-y',
        '-f', 'lavfi',
        '-i', 'color=c=red:s=1920x1080:d=3',
        '-vf', 'drawtext=text=\'OUTRO VIDEO\':fontcolor=white:fontsize=72:x=(w-text_w)/2:y=(h-text_h)/2',
        '-c:v', 'libx264',
        '-preset', 'veryfast',
        '-pix_fmt', 'yuv420p',
        '-r', '30',
        f'{output_dir}/outro.mp4'
    ]
    run_command(cmd3, "outro.mp4 (3 seconds)")

def create_sample_images():
    """Create sample image files"""
    print_step("Creating Sample Images")

    output_dir = "sample_data"
    os.makedirs(output_dir, exist_ok=True)

    # Image 1: Slide 1 (purple background)
    cmd1 = [
        'ffmpeg', '-y',
        '-f', 'lavfi',
        '-i', 'color=c=purple:s=1920x1080:d=1',
        '-vf', 'drawtext=text=\'SLIDE 1\':fontcolor=white:fontsize=96:x=(w-text_w)/2:y=(h-text_h)/2',
        '-frames:v', '1',
        f'{output_dir}/slide1.jpg'
    ]
    run_command(cmd1, "slide1.jpg")

    # Image 2: Slide 2 (orange background)
    cmd2 = [
        'ffmpeg', '-y',
        '-f', 'lavfi',
        '-i', 'color=c=orange:s=1920x1080:d=1',
        '-vf', 'drawtext=text=\'SLIDE 2\':fontcolor=white:fontsize=96:x=(w-text_w)/2:y=(h-text_h)/2',
        '-frames:v', '1',
        f'{output_dir}/slide2.jpg'
    ]
    run_command(cmd2, "slide2.jpg")

    # Image 3: Slide 3 (cyan background)
    cmd3 = [
        'ffmpeg', '-y',
        '-f', 'lavfi',
        '-i', 'color=c=cyan:s=1920x1080:d=1',
        '-vf', 'drawtext=text=\'SLIDE 3\':fontcolor=black:fontsize=96:x=(w-text_w)/2:y=(h-text_h)/2',
        '-frames:v', '1',
        f'{output_dir}/slide3.jpg'
    ]
    run_command(cmd3, "slide3.jpg")

def create_sample_audio():
    """Create sample audio files"""
    print_step("Creating Sample Audio Files")

    output_dir = "sample_data"
    os.makedirs(output_dir, exist_ok=True)

    # Audio 1: Narration (10 seconds, 440 Hz tone)
    cmd1 = [
        'ffmpeg', '-y',
        '-f', 'lavfi',
        '-i', 'sine=frequency=440:duration=10',
        '-c:a', 'libmp3lame',
        '-b:a', '192k',
        f'{output_dir}/narration1.mp3'
    ]
    run_command(cmd1, "narration1.mp3 (10 seconds, 440 Hz)")

    # Audio 2: Narration 2 (8 seconds, 523 Hz tone - C note)
    cmd2 = [
        'ffmpeg', '-y',
        '-f', 'lavfi',
        '-i', 'sine=frequency=523:duration=8',
        '-c:a', 'libmp3lame',
        '-b:a', '192k',
        f'{output_dir}/narration2.mp3'
    ]
    run_command(cmd2, "narration2.mp3 (8 seconds, 523 Hz)")

    # Audio 3: Music (7 seconds, 330 Hz tone - E note)
    cmd3 = [
        'ffmpeg', '-y',
        '-f', 'lavfi',
        '-i', 'sine=frequency=330:duration=7',
        '-c:a', 'libmp3lame',
        '-b:a', '192k',
        f'{output_dir}/music.mp3'
    ]
    run_command(cmd3, "music.mp3 (7 seconds, 330 Hz)")

def create_readme():
    """Create README for sample data"""
    print_step("Creating Sample Data README")

    output_dir = "sample_data"
    readme_path = f"{output_dir}/README.txt"

    content = """SAMPLE TEST DATA
================

This directory contains sample media files for testing the Video Editing System.

FILES:
------

Videos:
  - intro.mp4 (5 seconds) - Blue background with "INTRO VIDEO" text
  - demo.mp4 (4 seconds) - Green background with "DEMO VIDEO" text
  - outro.mp4 (3 seconds) - Red background with "OUTRO VIDEO" text

Images:
  - slide1.jpg - Purple background with "SLIDE 1" text
  - slide2.jpg - Orange background with "SLIDE 2" text
  - slide3.jpg - Cyan background with "SLIDE 3" text

Audio:
  - narration1.mp3 (10 seconds) - 440 Hz tone
  - narration2.mp3 (8 seconds) - 523 Hz tone
  - music.mp3 (7 seconds) - 330 Hz tone

Total Audio Duration: 25 seconds
Total Video Duration: 12 seconds
Number of Images: 3

Expected Behavior:
------------------
When processing with all files:
  - Total video length: 25 seconds (matches audio)
  - Each image will display for: (25 - 12) / 3 = 4.33 seconds

USAGE:
------

1. Test with Web Interface:
   - Start API server: python3 backend/api.py
   - Open: http://localhost:5000
   - Upload these files and rank them
   - Click "Create Video"

2. Test with Python:
   from main import VideoEditorSystem

   visual_media = [
       {'rank': 1, 'type': 'video', 'path': 'sample_data/intro.mp4'},
       {'rank': 2, 'type': 'image', 'path': 'sample_data/slide1.jpg'},
       {'rank': 3, 'type': 'video', 'path': 'sample_data/demo.mp4'},
       {'rank': 4, 'type': 'image', 'path': 'sample_data/slide2.jpg'},
       {'rank': 5, 'type': 'video', 'path': 'sample_data/outro.mp4'},
       {'rank': 6, 'type': 'image', 'path': 'sample_data/slide3.jpg'},
   ]

   audio_files = [
       {'rank': 1, 'path': 'sample_data/narration1.mp3'},
       {'rank': 2, 'path': 'sample_data/narration2.mp3'},
       {'rank': 3, 'path': 'sample_data/music.mp3'},
   ]

   editor = VideoEditorSystem()
   result = editor.process_video_project(visual_media, audio_files)

NOTE:
-----
These are synthetic test files created with FFmpeg. They contain simple
colored backgrounds and tones for testing purposes. Replace with real
media files for actual video production.

Generated by: create_sample_data.py
"""

    with open(readme_path, 'w') as f:
        f.write(content)

    print(f"✓ Created: {readme_path}")

def main():
    """Main function"""
    print("\n" + "="*70)
    print("SAMPLE DATA GENERATOR")
    print("Creating test media files for Video Editing System")
    print("="*70)

    # Check FFmpeg
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("\n✗ ERROR: FFmpeg not found!")
        print("Please install FFmpeg before running this script")
        sys.exit(1)

    # Create samples
    create_sample_videos()
    create_sample_images()
    create_sample_audio()
    create_readme()

    # Summary
    print_step("SAMPLE DATA CREATION COMPLETE")

    print("✓ All sample files created successfully!")
    print("\nGenerated files in: sample_data/")
    print("\nFile list:")

    output_dir = "sample_data"
    for filename in sorted(os.listdir(output_dir)):
        if filename != "README.txt":
            filepath = os.path.join(output_dir, filename)
            size = os.path.getsize(filepath)
            size_kb = size / 1024
            print(f"  - {filename} ({size_kb:.1f} KB)")

    print(f"\nSee sample_data/README.txt for usage instructions")
    print("\n✓ Ready to test the video editing system!")

if __name__ == "__main__":
    main()

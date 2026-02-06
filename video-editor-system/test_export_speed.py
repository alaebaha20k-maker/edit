#!/usr/bin/env python3
"""
Test script to verify ultra-fast export (12min audio + 1 image)
Should complete in 15-25 seconds MAX!
"""

import os
import sys
import time
import subprocess
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / 'backend'))

from video_assembler import VideoAssembler


def create_test_files():
    """Create test audio (12min) and test image"""
    test_dir = Path(__file__).parent / 'test_files'
    test_dir.mkdir(exist_ok=True)

    audio_path = test_dir / 'test_audio_12min.m4a'
    image_path = test_dir / 'test_image.jpg'

    print("📝 Creating test files...")

    # Create 12min silent audio (AAC format for -c:a copy to work!)
    if not audio_path.exists():
        print(f"   Creating 12min silent audio: {audio_path}")
        cmd = [
            'ffmpeg', '-y',
            '-f', 'lavfi',
            '-i', 'anullsrc=r=48000:cl=stereo',
            '-t', '746',  # 12min 26sec
            '-c:a', 'aac',
            '-b:a', '160k',
            str(audio_path)
        ]
        subprocess.run(cmd, capture_output=True, check=True, timeout=30)
        print(f"   ✅ Audio created: {audio_path}")
    else:
        print(f"   ✅ Audio exists: {audio_path}")

    # Create test image (1080p)
    if not image_path.exists():
        print(f"   Creating test image: {image_path}")
        cmd = [
            'ffmpeg', '-y',
            '-f', 'lavfi',
            '-i', 'color=blue:s=1920x1080:d=1',
            '-frames:v', '1',
            str(image_path)
        ]
        subprocess.run(cmd, capture_output=True, check=True, timeout=10)
        print(f"   ✅ Image created: {image_path}")
    else:
        print(f"   ✅ Image exists: {image_path}")

    return str(audio_path), str(image_path)


def test_export():
    """Test export speed"""
    print("\n" + "="*60)
    print("🚀 TESTING ULTRA-FAST EXPORT")
    print("="*60)

    # Create test files
    audio_path, image_path = create_test_files()

    # Setup output
    output_dir = Path(__file__).parent / 'test_output'
    output_dir.mkdir(exist_ok=True)
    output_path = str(output_dir / 'test_output.mp4')

    print(f"\n📊 Test Configuration:")
    print(f"   Audio: 12min 26sec")
    print(f"   Image: 1920x1080")
    print(f"   Expected time: 15-25 seconds")
    print(f"   Output: {output_path}")

    # Run export
    print(f"\n⏱️  Starting export...")
    start_time = time.time()

    assembler = VideoAssembler(output_dir=str(output_dir))
    result = assembler.assemble_final_video(
        voice_path=audio_path,
        media_paths=[image_path],
        output_path=output_path,
        resolution='1920x1080',
        verbose=True
    )

    elapsed = time.time() - start_time

    # Results
    print(f"\n" + "="*60)
    print(f"✅ EXPORT COMPLETE!")
    print(f"="*60)
    print(f"   Time: {elapsed:.1f} seconds")
    print(f"   Size: {result['file_size_mb']:.2f} MB")
    print(f"   Duration: {result['duration_seconds']:.1f} seconds")

    # Check if fast enough
    if elapsed <= 25:
        print(f"\n🎉 SUCCESS! Export is FAST! ({elapsed:.1f}s <= 25s)")
        return True
    elif elapsed <= 40:
        print(f"\n⚠️  WARNING: Export is acceptable but could be faster ({elapsed:.1f}s)")
        return True
    else:
        print(f"\n❌ FAILURE! Export is TOO SLOW! ({elapsed:.1f}s > 40s)")
        print(f"   Expected: 15-25 seconds")
        print(f"   Got: {elapsed:.1f} seconds")
        return False


if __name__ == '__main__':
    try:
        success = test_export()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

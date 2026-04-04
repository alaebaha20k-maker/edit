#!/usr/bin/env python3
"""
Video Processor for AI Video Generation System
Process all media (images, videos, audio) into final video
Handles mixed media with ranking
"""

import subprocess
import os
import re
from pathlib import Path


def process_final_video(media_items, audio_files, output_path, quality='1080', verbose=True):
    """
    Create final video from mixed media (images + videos) and audio

    Args:
        media_items: List of media dicts:
            [
                {'type': 'image', 'path': '...', 'rank': 1},
                {'type': 'video', 'path': '...', 'rank': 2},
                ...
            ]
        audio_files: List of audio file paths (will be concatenated)
        output_path: Where to save final video
        quality: '720' or '1080'
        verbose: Print progress

    Returns:
        {
            'success': True,
            'output_path': '...',
            'duration': '31:45',
            'file_size': '245 MB'
        }
    """

    if verbose:
        print(f"\n🎬 Processing final video...")
        print(f"   Media items: {len(media_items)}")
        print(f"   Audio files: {len(audio_files)}")

    # Ensure temp directory exists
    temp_dir = Path('temp')
    temp_dir.mkdir(exist_ok=True)

    # Step 1: Concatenate audio files
    if verbose:
        print(f"\n🎵 Step 1: Concatenating {len(audio_files)} audio file(s)...")

    if len(audio_files) > 1:
        final_audio = 'temp/final_audio.mp3'
        concat_list = 'temp/audio_concat.txt'

        with open(concat_list, 'w') as f:
            for audio in audio_files:
                f.write(f"file '{os.path.abspath(audio)}'\n")

        subprocess.run([
            'ffmpeg', '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_list,
            '-c', 'copy',
            final_audio
        ], check=True, capture_output=not verbose)
    else:
        final_audio = audio_files[0]

    # Get audio duration
    audio_duration = get_media_duration(final_audio)

    if verbose:
        print(f"   ✅ Total audio duration: {format_duration(audio_duration)}")

    # Step 2: Sort media by rank
    media_items = sorted(media_items, key=lambda x: x.get('rank', 999))

    # Step 3: Calculate duration per media item
    duration_per_item = audio_duration / len(media_items)

    if verbose:
        print(f"\n🎨 Step 2: Processing {len(media_items)} media items...")
        print(f"   Duration per item: {duration_per_item:.2f}s")

    # Step 4: Process each media item
    processed_clips = []

    for i, item in enumerate(media_items):
        clip_output = f"temp/clip_{i:03d}.mp4"

        if item['type'] == 'image':
            # Image → Video with zoom effect
            if verbose:
                print(f"   Processing image {i+1}/{len(media_items)}...")

            out_h = '1080' if quality == '1080' else '720'
            out_w = '1920' if quality == '1080' else '1280'
            subprocess.run([
                'ffmpeg', '-y',
                '-loop', '1',
                '-framerate', '2',
                '-i', item['path'],
                '-vf', f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2,zoompan=z='min(zoom+0.0015,1.5)':d={int(duration_per_item*30)}:s={out_w}x{out_h},fps=30",
                '-t', str(duration_per_item),
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-tune', 'stillimage',
                '-crf', '23',
                '-an',
                '-pix_fmt', 'yuv420p',
                clip_output
            ], check=True, capture_output=not verbose)

        elif item['type'] == 'video':
            # Video → Normalize and trim/loop to duration
            if verbose:
                print(f"   Processing video {i+1}/{len(media_items)}...")

            video_duration = get_media_duration(item['path'])

            out_h = '1080' if quality == '1080' else '720'
            out_w = '1920' if quality == '1080' else '1280'
            scale_vf = f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2,fps=30"

            if video_duration < duration_per_item:
                # Loop video to fill duration
                num_loops = int(duration_per_item / video_duration) + 1

                subprocess.run([
                    'ffmpeg', '-y',
                    '-stream_loop', str(num_loops),
                    '-i', item['path'],
                    '-t', str(duration_per_item),
                    '-vf', scale_vf,
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast',
                    '-crf', '23',
                    '-an',
                    '-pix_fmt', 'yuv420p',
                    clip_output
                ], check=True, capture_output=not verbose)
            else:
                # Trim video to duration
                subprocess.run([
                    'ffmpeg', '-y',
                    '-i', item['path'],
                    '-t', str(duration_per_item),
                    '-vf', scale_vf,
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast',
                    '-crf', '23',
                    '-an',
                    '-pix_fmt', 'yuv420p',
                    clip_output
                ], check=True, capture_output=not verbose)

        processed_clips.append(clip_output)

    # Step 5: Concatenate all video clips
    if verbose:
        print(f"\n🔗 Step 3: Concatenating {len(processed_clips)} clips...")

    video_concat_list = 'temp/video_concat.txt'
    with open(video_concat_list, 'w') as f:
        for clip in processed_clips:
            f.write(f"file '{os.path.abspath(clip)}'\n")

    video_no_audio = 'temp/video_no_audio.mp4'
    subprocess.run([
        'ffmpeg', '-y',
        '-f', 'concat',
        '-safe', '0',
        '-i', video_concat_list,
        '-c', 'copy',
        video_no_audio
    ], check=True, capture_output=not verbose)

    # Step 6: Merge video + audio
    if verbose:
        print(f"\n🎵 Step 4: Merging video + audio...")

    subprocess.run([
        'ffmpeg', '-y',
        '-i', video_no_audio,
        '-i', final_audio,
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-b:a', '192k',
        '-shortest',
        output_path
    ], check=True, capture_output=not verbose)

    # Step 7: Get final stats
    final_duration = get_media_duration(output_path)
    file_size = os.path.getsize(output_path) / (1024 * 1024)  # MB

    # Cleanup temp files
    if verbose:
        print(f"\n🧹 Cleaning up temporary files...")

    for clip in processed_clips:
        if os.path.exists(clip):
            os.remove(clip)

    if os.path.exists(video_no_audio):
        os.remove(video_no_audio)

    if verbose:
        print(f"\n✅ Video complete!")
        print(f"   Output: {output_path}")
        print(f"   Duration: {format_duration(final_duration)}")
        print(f"   Size: {file_size:.2f} MB")

    return {
        'success': True,
        'output_path': output_path,
        'duration': format_duration(final_duration),
        'file_size': f"{file_size:.2f} MB"
    }


def get_media_duration(filepath):
    """Get duration of media file in seconds"""
    result = subprocess.run([
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        filepath
    ], capture_output=True, text=True)

    return float(result.stdout.strip())


def format_duration(seconds):
    """Format seconds as MM:SS"""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"

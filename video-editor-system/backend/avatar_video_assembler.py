#!/usr/bin/env python3
"""
Avatar Video Assembler
Assembles final video with avatar loops + media + audio using FFmpeg ultra-fast
"""

import os
import json
import math
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict
from datetime import datetime


class AvatarVideoAssembler:
    """
    Assemble avatar video with ultra-fast FFmpeg

    Features:
    - Avatar video looping
    - AI images or stock videos insertion
    - Audio synchronization
    - Ultra-fast processing
    - Exact audio length matching
    """

    def __init__(self, temp_dir: str = "temp/avatar", output_dir: str = "output"):
        """
        Initialize assembler

        Args:
            temp_dir: Temporary directory for processing
            output_dir: Output directory for final video
        """
        self.temp_dir = temp_dir
        self.output_dir = output_dir

        os.makedirs(temp_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

    def _prepare_looped_background_music(self, music_path: str, target_duration: float, verbose: bool = False) -> str:
        """Prepare background music with looping if needed. Returns path to prepared music file."""
        cmd = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', music_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        raw = result.stdout.strip()
        if not raw:
            if verbose:
                print(f"   ⚠️  Cannot read music duration (ffprobe empty), skipping background music")
            return None
        music_duration = float(raw)

        if verbose:
            print(f"\n🎵 Background music: {music_duration:.1f}s (target: {target_duration:.1f}s)")

        output_path = os.path.join(self.temp_dir, f"bgmusic_prepared_{int(time.time())}.mp3")

        if music_duration >= target_duration:
            cmd = ['ffmpeg', '-y', '-i', music_path, '-t', str(target_duration), '-c:a', 'copy', output_path]
            subprocess.run(cmd, capture_output=True, check=True, timeout=60)
            if verbose:
                print(f"   ✅ Trimmed to {target_duration:.1f}s")
            return output_path

        # Need to loop: build concat list
        concat_file = os.path.join(self.temp_dir, f"bgmusic_concat_{int(time.time())}.txt")
        current_duration = 0.0
        loop_count = 0
        with open(concat_file, 'w') as f:
            while current_duration < target_duration:
                if loop_count == 0:
                    f.write(f"file '{os.path.abspath(music_path)}'\n")
                    current_duration += music_duration
                else:
                    # Skip first 5s on subsequent loops for smooth transition
                    trimmed = os.path.join(self.temp_dir, f"bgmusic_loop{loop_count}_{int(time.time())}.mp3")
                    trim_cmd = ['ffmpeg', '-y', '-i', music_path, '-ss', '5', '-c:a', 'copy', trimmed]
                    subprocess.run(trim_cmd, capture_output=True, check=True, timeout=60)
                    f.write(f"file '{os.path.abspath(trimmed)}'\n")
                    current_duration += (music_duration - 5.0)
                loop_count += 1

        cmd = [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_file,
            '-t', str(target_duration), '-c:a', 'copy', output_path
        ]
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)
        if verbose:
            print(f"   ✅ Looped {loop_count}x to {target_duration:.1f}s")
        return output_path

    def assemble_video(
        self,
        avatar_video_path: str,
        audio_path: str,
        media_plan: Dict,
        media_items: List[Dict],
        mode: str,
        background_music_path: str = None,
        verbose: bool = True
    ) -> str:
        """
        Assemble final avatar video

        Args:
            avatar_video_path: Path to avatar video
            audio_path: Path to audio narration
            media_plan: Media plan from AvatarVideoGenerator
            media_items: Generated/downloaded media items
            mode: "ai_images" or "stock_videos"
            verbose: Print progress

        Returns:
            str: Path to final video
        """
        if verbose:
            print(f"\n{'='*70}")
            print(f"🎬 ASSEMBLING AVATAR VIDEO")
            print(f"{'='*70}\n")

        # Steps 1 & 2 are independent — run them in parallel to save time
        if verbose:
            print("📹 Steps 1+2 (parallel): Avatar loops + media clips...")

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_avatar = pool.submit(
                self._create_avatar_loops,
                avatar_video_path, media_plan, verbose
            )
            future_media = pool.submit(
                self._prepare_media_clips,
                media_items, media_plan, mode, verbose
            )
            avatar_clips = future_avatar.result()
            media_clips  = future_media.result()

        # Step 3: Create concat list
        if verbose:
            print("\n📝 Step 3: Creating video sequence...")

        concat_file = self._create_concat_list(
            media_plan=media_plan,
            avatar_clips=avatar_clips,
            media_clips=media_clips,
            verbose=verbose
        )

        # Step 4: Concatenate all clips
        if verbose:
            print("\n🔗 Step 4: Concatenating video clips...")

        concatenated_video = self._concatenate_clips(concat_file, verbose)

        # Step 5: Add audio
        if verbose:
            print("\n🔊 Step 5: Adding audio narration...")

        final_video = self._add_audio(
            video_path=concatenated_video,
            audio_path=audio_path,
            background_music_path=background_music_path,
            verbose=verbose
        )

        if verbose:
            print(f"\n{'='*70}")
            print(f"✅ AVATAR VIDEO COMPLETE")
            print(f"{'='*70}")
            print(f"Output: {final_video}")
            print(f"{'='*70}\n")

        return final_video

    def _create_avatar_loops(
        self,
        avatar_video_path: str,
        media_plan: Dict,
        verbose: bool = False
    ) -> Dict[int, str]:
        """
        Create looped avatar clips for all avatar segments

        Args:
            avatar_video_path: Path to original avatar video
            media_plan: Media plan
            verbose: Print progress

        Returns:
            Dict mapping segment index to avatar clip path
        """
        avatar_clips = {}
        avatar_segments = [
            (i, seg) for i, seg in enumerate(media_plan['segments'])
            if seg['type'] == 'avatar'
        ]

        for i, (seg_idx, segment) in enumerate(avatar_segments):
            target_duration = segment['duration']

            if verbose:
                print(f"   [{i+1}/{len(avatar_segments)}] Creating {target_duration:.1f}s avatar loop...")

            # Create looped clip
            output_path = os.path.join(self.temp_dir, f"avatar_loop_{seg_idx}.mp4")

            clip_path = self._loop_avatar_video(
                avatar_video_path=avatar_video_path,
                target_duration=target_duration,
                output_path=output_path,
                verbose=verbose
            )

            avatar_clips[seg_idx] = clip_path

        return avatar_clips

    def _loop_avatar_video(
        self,
        avatar_video_path: str,
        target_duration: float,
        output_path: str,
        verbose: bool = False
    ) -> str:
        """
        Loop avatar video to target duration using FAST COPY codec

        Args:
            avatar_video_path: Original avatar video
            target_duration: Target duration in seconds
            output_path: Output path
            verbose: Print progress

        Returns:
            str: Path to looped video
        """
        # Re-encode avatar to 1920x1080 25fps — matches stock clips exactly.
        # stream_loop loops the input; re-encode ensures consistent timebase,
        # resolution and framerate across ALL clips for clean concat.
        # Force video_track_timescale=12800 so all segments share the same
        # timebase — eliminates non-monotonic DTS and bitstream filter warnings.
        cmd = [
            'ffmpeg', '-y',
            '-stream_loop', '-1',
            '-i', avatar_video_path,
            '-t', str(target_duration),
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '28',
            '-r', '25',
            '-vf', 'scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080',
            '-pix_fmt', 'yuv420p',
            '-video_track_timescale', '12800',
            '-an',
            '-movflags', '+faststart',
            output_path
        ]

        if not verbose:
            cmd.extend(['-loglevel', 'error'])

        subprocess.run(cmd, check=True)

        return output_path

    def _prepare_media_clips(
        self,
        media_items: List[Dict],
        media_plan: Dict,
        mode: str,
        verbose: bool = False
    ) -> Dict[int, str]:
        """
        Prepare media clips (images to videos or trim videos)

        Args:
            media_items: Media items from generator
            media_plan: Media plan
            mode: "ai_images" or "stock_videos"
            verbose: Print progress

        Returns:
            Dict mapping segment index to media clip path
        """
        media_clips = {}

        # Get media segments from plan
        media_segments = {
            i: seg for i, seg in enumerate(media_plan['segments'])
            if seg['type'] in ['ai_image', 'stock_video']
        }

        def _process_one(item):
            seg_idx = item.get('segment_index')
            if seg_idx not in media_segments:
                return None, None
            segment = media_segments[seg_idx]
            target_duration = segment['duration']
            if mode == "ai_images":
                out = os.path.join(self.temp_dir, f"image_{seg_idx}.mp4")
                clip = self._image_to_video(item['path'], target_duration, out, verbose=False)
            else:
                out = os.path.join(self.temp_dir, f"stock_{seg_idx}.mp4")
                clip = self._prepare_stock_video(item['path'], target_duration, out, verbose=False)
            return seg_idx, clip

        # Run all clip preparations in parallel (4 workers)
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(_process_one, item) for item in media_items]
            for future in as_completed(futures):
                seg_idx, clip_path = future.result()
                if seg_idx is not None:
                    media_clips[seg_idx] = clip_path
                    if verbose:
                        print(f"   ✅ Clip ready: segment {seg_idx}")

        return media_clips

    def _image_to_video(
        self,
        image_path: str,
        duration: float,
        output_path: str,
        verbose: bool = False
    ) -> str:
        """Convert image to video with duration — matches avatar/stock clip format exactly"""

        # Same resolution/fps/timescale as stock clips for consistent concat.
        # video_track_timescale=12800 ensures all segments share identical
        # timebase so the final concat uses clean stream copy with zero warnings.
        cmd = [
            'ffmpeg', '-y',
            '-loop', '1',
            '-i', image_path,
            '-t', str(duration),
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'stillimage',
            '-crf', '28',
            '-r', '25',
            '-vf', 'scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080',
            '-pix_fmt', 'yuv420p',
            '-video_track_timescale', '12800',
            '-an',
            '-movflags', '+faststart',
            output_path
        ]

        if not verbose:
            cmd.extend(['-loglevel', 'error'])

        subprocess.run(cmd, check=True)

        return output_path

    def _prepare_stock_video(
        self,
        video_path: str,
        target_duration: float,
        output_path: str,
        verbose: bool = False
    ) -> str:
        """Prepare stock video — re-encode to 1920x1080 25fps h264"""

        # Get video duration
        probe_cmd = [
            'ffprobe',
            '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name,width,height:format=duration',
            '-of', 'json',
            video_path
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True)
        info = json.loads(result.stdout)

        duration = float(info['format']['duration'])

        # Trim duration
        trim_duration = min(duration, target_duration)

        # Always re-encode to 1920x1080 25fps h264 — guarantees consistent
        # timebase/framerate so the final concat never gets non-monotonic DTS.
        # ultrafast preset keeps this fast while fixing all format mismatches.
        # Force video_track_timescale=12800 to match avatar clips exactly.
        cmd = [
            'ffmpeg', '-y',
            '-i', video_path,
            '-t', str(trim_duration),
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '28',
            '-r', '25',
            '-vf', 'scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080',
            '-pix_fmt', 'yuv420p',
            '-video_track_timescale', '12800',
            '-an',
            '-movflags', '+faststart',
            output_path
        ]

        if not verbose:
            cmd.extend(['-loglevel', 'error'])

        subprocess.run(cmd, check=True)

        return output_path

    def _create_concat_list(
        self,
        media_plan: Dict,
        avatar_clips: Dict[int, str],
        media_clips: Dict[int, str],
        verbose: bool = False
    ) -> str:
        """Create FFmpeg concat file"""

        concat_file = os.path.join(self.temp_dir, "concat_list.txt")

        with open(concat_file, 'w') as f:
            for i, segment in enumerate(media_plan['segments']):
                if segment['type'] == 'avatar':
                    clip_path = avatar_clips.get(i)
                else:
                    clip_path = media_clips.get(i)

                if clip_path:
                    # FFmpeg concat format
                    f.write(f"file '{os.path.abspath(clip_path)}'\n")

        if verbose:
            print(f"   Created concat list with {len(media_plan['segments'])} clips")

        return concat_file

    def _concatenate_clips(self, concat_file: str, verbose: bool = False) -> str:
        """Concatenate all clips — ultra fast stream copy with explicit bitstream filter"""

        output_path = os.path.join(self.temp_dir, "concatenated.mp4")

        # All clips are already 1920x1080/25fps/h264/yuv420p from prep step
        # so concat can stream-copy — ultra fast, no quality loss.
        # Explicit -bsf:v h264_mp4toannexb avoids per-segment auto-detection
        # overhead that prints warnings and adds ~0.5s per segment.
        cmd = [
            'ffmpeg',
            '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_file,
            '-c', 'copy',
            '-bsf:v', 'h264_mp4toannexb',
            '-an',
            '-movflags', '+faststart',
            output_path
        ]

        if not verbose:
            cmd.extend(['-loglevel', 'error'])

        subprocess.run(cmd, check=True)

        return output_path

    def _add_audio(
        self,
        video_path: str,
        audio_path: str,
        background_music_path: str = None,
        verbose: bool = False
    ) -> str:
        """Add audio to video - video MUST match audio duration exactly"""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(self.output_dir, f"avatar_video_{timestamp}.mp4")

        # Get durations to verify
        if verbose:
            video_duration = self._get_video_duration(video_path)
            audio_duration = self._get_video_duration(audio_path)
            print(f"\n   🔍 Final Duration Check:")
            print(f"   Video: {video_duration:.2f}s")
            print(f"   Audio: {audio_duration:.2f}s")
            if abs(video_duration - audio_duration) < 0.1:
                print(f"   ✅ Durations match!")
            else:
                print(f"   ⚠️  Mismatch: {abs(video_duration - audio_duration):.2f}s difference")

        # Prepare background music if provided
        prepared_music = None
        if background_music_path:
            # Try to resolve path if relative
            if not os.path.isabs(background_music_path):
                # Try relative to cwd
                candidate = os.path.join(os.getcwd(), background_music_path)
                if os.path.exists(candidate):
                    background_music_path = candidate
            if verbose:
                exists = os.path.exists(background_music_path)
                print(f"   🎵 Background music path: {background_music_path} (exists={exists})")
        if background_music_path and os.path.exists(background_music_path):
            audio_duration = self._get_video_duration(audio_path)
            if verbose:
                print(f"   🎵 Adding background music at 8% volume...")
            prepared_music = self._prepare_looped_background_music(
                background_music_path, audio_duration, verbose
            )

        if prepared_music:
            # WITH background music: mix voice at 100% + music at 8%
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-i', audio_path,
                '-i', prepared_music,
                '-filter_complex', '[1:a]volume=1.0[voice];[2:a]volume=0.08[music];[voice][music]amix=inputs=2:duration=first[aout]',
                '-map', '0:v',
                '-map', '[aout]',
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-shortest',
                '-movflags', '+faststart',
                output_path
            ]
        else:
            # NO background music — stream-copy audio (no re-encode, ~10x faster)
            cmd = [
                'ffmpeg', '-y',
                '-i', video_path,
                '-i', audio_path,
                '-map', '0:v',
                '-map', '1:a',
                '-c:v', 'copy',
                '-c:a', 'copy',
                '-shortest',
                '-movflags', '+faststart',
                output_path
            ]

        if not verbose:
            cmd.extend(['-loglevel', 'error'])

        subprocess.run(cmd, check=True)

        return output_path

    def _get_video_duration(self, video_path: str) -> float:
        """Get video duration using ffprobe"""
        import subprocess

        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            video_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())


if __name__ == "__main__":
    # Test
    print("✅ Avatar Video Assembler loaded successfully!")

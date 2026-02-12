#!/usr/bin/env python3
"""
Avatar AI Video Generator
Creates videos with avatar loops + AI images or stock videos
"""

import os
import time
import google.generativeai as genai
from typing import Dict, List, Tuple
from config import Config
from whisper_stt import WhisperSTT
import json


class AvatarVideoGenerator:
    """
    Generate videos with avatar + AI images or stock videos

    Modes:
    1. AI Images Auto: 1 min avatar → 5 sec AI image → repeat
    2. Videos Stock Auto: 30 sec avatar → 5-10 sec stock video → repeat

    Features:
    - Exact audio length matching
    - Smart media sequencing with Gemini
    - Last 2 minutes = full avatar
    - Ultra-fast FFmpeg processing
    """

    def __init__(self):
        """Initialize with Gemini API"""
        api_key = Config.get_gemini_api_key()
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")

        genai.configure(api_key=api_key)
        self.whisper = WhisperSTT()

    def generate_avatar_video(
        self,
        avatar_video_path: str,
        audio_path: str,
        mode: str = "ai_images",
        script: str = None,
        stock_apis: List[str] = None,
        use_whisper: bool = False,
        verbose: bool = True
    ) -> Dict:
        """
        Generate avatar video with AI images or stock videos

        Args:
            avatar_video_path: Path to avatar video (e.g., 33 seconds)
            audio_path: Path to audio narration (e.g., 27 minutes)
            mode: "ai_images" or "stock_videos"
            script: Optional script for context (for stock video search)
            stock_apis: List of stock API names to search (for stock_videos mode)
            use_whisper: If True, use Whisper STT for timing (slow). If False, use fast Gemini planning (default: False)
            verbose: Print progress

        Returns:
            Dict with media plan, timing, and metadata
        """
        start_time = time.time()

        if verbose:
            print(f"\n{'='*70}")
            print(f"🎬 AVATAR AI VIDEO GENERATOR")
            print(f"{'='*70}")
            print(f"Mode: {mode.upper()}")
            print(f"Avatar Video: {avatar_video_path}")
            print(f"Audio: {audio_path}")
            print(f"{'='*70}\n")

        # Step 1: Get audio duration (fast or with Whisper)
        if use_whisper:
            if verbose:
                print("📊 Step 1: Analyzing audio with Whisper STT (detailed timing)...")
            audio_duration = self._get_audio_duration_whisper(audio_path, verbose)
        else:
            if verbose:
                print("⚡ Step 1: Getting audio duration (fast mode)...")
            audio_duration = self._get_audio_duration_fast(audio_path)

        if verbose:
            print(f"✅ Audio duration: {audio_duration:.2f} seconds ({audio_duration/60:.2f} minutes)\n")

        # Step 2: Get avatar video duration
        if verbose:
            print("📹 Step 2: Getting avatar video duration...")

        avatar_duration = self._get_video_duration(avatar_video_path)

        if verbose:
            print(f"✅ Avatar duration: {avatar_duration:.2f} seconds\n")

        # Step 3: Plan media sequence with Gemini
        if verbose:
            print("🧠 Step 3: Planning media sequence with Gemini AI...")

        media_plan = self._plan_media_sequence(
            audio_duration=audio_duration,
            avatar_duration=avatar_duration,
            mode=mode,
            script=script,
            verbose=verbose
        )

        if verbose:
            print(f"✅ Media plan created: {len(media_plan['segments'])} segments\n")
            self._print_media_plan(media_plan)

        # Step 4: Download/generate media based on plan
        if mode == "ai_images":
            if verbose:
                print("\n🖼️  Step 4: Generating AI images with Replicate...")
            media_items = self._generate_ai_images(media_plan, script, verbose)
        else:  # stock_videos
            if verbose:
                print("\n🎥 Step 4: Downloading stock videos from APIs...")
            media_items = self._download_stock_videos(media_plan, script, stock_apis, verbose)

        generation_time = time.time() - start_time

        result = {
            'media_plan': media_plan,
            'media_items': media_items,
            'audio_duration': audio_duration,
            'avatar_duration': avatar_duration,
            'mode': mode,
            'generation_time': generation_time
        }

        if verbose:
            print(f"\n{'='*70}")
            print(f"✅ AVATAR AI PLANNING COMPLETE")
            print(f"{'='*70}")
            print(f"Total segments: {len(media_plan['segments'])}")
            print(f"Planning time: {generation_time:.1f}s")
            print(f"{'='*70}\n")

        return result

    def _get_audio_duration_fast(self, audio_path: str) -> float:
        """
        Get audio duration using ffprobe (ultra-fast, no transcription)

        Args:
            audio_path: Path to audio file

        Returns:
            float: Duration in seconds
        """
        import subprocess

        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            audio_path
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())

    def _get_audio_duration_whisper(self, audio_path: str, verbose: bool = False) -> float:
        """
        Get audio duration using Whisper STT

        Args:
            audio_path: Path to audio file
            verbose: Print progress

        Returns:
            float: Duration in seconds
        """
        try:
            # Use Whisper to get exact duration
            result = self.whisper.transcribe_with_timestamps(
                audio_path=audio_path,
                language=None,  # Auto-detect
                verbose=verbose
            )

            if 'segments' in result and len(result['segments']) > 0:
                # Get last segment end time
                last_segment = result['segments'][-1]
                duration = last_segment['end']
            else:
                # Fallback to result duration
                duration = result.get('duration', 0)

            return duration

        except Exception as e:
            if verbose:
                print(f"⚠️  Whisper failed, using FFprobe fallback: {e}")

            # Fallback to FFprobe
            import subprocess
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                audio_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return float(result.stdout.strip())

    def _get_video_duration(self, video_path: str) -> float:
        """
        Get video duration using FFprobe

        Args:
            video_path: Path to video file

        Returns:
            float: Duration in seconds
        """
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

    def _plan_media_sequence(
        self,
        audio_duration: float,
        avatar_duration: float,
        mode: str,
        script: str = None,
        verbose: bool = False
    ) -> Dict:
        """
        Plan media sequence using Gemini AI

        Args:
            audio_duration: Total audio duration in seconds
            avatar_duration: Avatar video duration in seconds
            mode: "ai_images" or "stock_videos"
            script: Optional script for context
            verbose: Print progress

        Returns:
            Dict with media plan
        """
        # Determine segment pattern based on mode
        if mode == "ai_images":
            avatar_seg_duration = 60  # 1 minute
            media_seg_duration = 5    # 5 seconds
        else:  # stock_videos
            avatar_seg_duration = 10  # 10 seconds (CHANGED: was 30, too long!)
            media_seg_duration = 8     # 8 seconds (FIXED: was None, now enforced!)

        # Build prompt for Gemini
        prompt = self._build_planning_prompt(
            audio_duration=audio_duration,
            avatar_duration=avatar_duration,
            mode=mode,
            avatar_seg_duration=avatar_seg_duration,
            media_seg_duration=media_seg_duration,
            script=script
        )

        # Call Gemini
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
                max_output_tokens=8192,
                response_mime_type="application/json"
            )
        )

        # Parse response
        try:
            plan = json.loads(response.text)
        except:
            # Fallback: create simple plan
            plan = self._create_fallback_plan(
                audio_duration=audio_duration,
                avatar_duration=avatar_duration,
                mode=mode,
                avatar_seg_duration=avatar_seg_duration,
                media_seg_duration=media_seg_duration
            )

        # CRITICAL: Validate and fix total duration
        plan = self._validate_and_fix_duration(plan, audio_duration, verbose)

        return plan

    def _build_planning_prompt(
        self,
        audio_duration: float,
        avatar_duration: float,
        mode: str,
        avatar_seg_duration: int,
        media_seg_duration: int,
        script: str = None
    ) -> str:
        """Build prompt for Gemini media planning"""

        last_2_min_seconds = 120

        # CRITICAL: Analyze script by timing to plan WHAT media to show WHEN
        # Calculate characters per second (rough estimate for timing)
        chars_per_second = len(script) / audio_duration if script and audio_duration > 0 else 0

        # Create timing-based script chunks (every 30 seconds)
        script_chunks = []
        if script and chars_per_second > 0:
            current_time = 0
            chunk_interval = 30  # Analyze script every 30 seconds
            while current_time < audio_duration - last_2_min_seconds:
                start_char = int(current_time * chars_per_second)
                end_char = int((current_time + chunk_interval) * chars_per_second)
                chunk_text = script[start_char:end_char] if start_char < len(script) else ""
                if chunk_text:
                    script_chunks.append({
                        'time_start': current_time,
                        'time_end': current_time + chunk_interval,
                        'text': chunk_text[:150]  # First 150 chars for context
                    })
                current_time += chunk_interval

        # Build script timeline for Gemini
        script_timeline = ""
        if script_chunks:
            script_timeline = "**SCRIPT TIMELINE (what audio says at each time):**\n"
            for chunk in script_chunks[:10]:  # Show first 10 chunks
                script_timeline += f"[{chunk['time_start']:.0f}s-{chunk['time_end']:.0f}s]: \"{chunk['text']}...\"\n"
            script_timeline += "\n"

        prompt = f"""You are an AI video planner. Create a media sequence plan.

**TASK:** Plan a video with avatar loops and {"AI images" if mode == "ai_images" else "stock videos"}.

**INPUT:**
- Audio duration: {audio_duration:.2f} seconds ({audio_duration/60:.2f} minutes)
- Avatar video duration: {avatar_duration:.2f} seconds
- Mode: {mode}

{script_timeline}

**RULES:**
1. Pattern: {avatar_seg_duration} sec avatar → {media_seg_duration if media_seg_duration else "EXACTLY 8"} sec {"AI image" if mode == "ai_images" else "stock video"} → repeat
2. Last {last_2_min_seconds} seconds: FULL avatar (to match exact audio length)
3. Total duration MUST exactly match audio duration: {audio_duration:.2f} seconds
4. {"AI images are EXACTLY 5 seconds each" if mode == "ai_images" else f"Stock videos are EXACTLY {media_seg_duration if media_seg_duration else 8} seconds (NO LONGER!)"}
5. CRITICAL: Each media segment MUST have different search query - NO REPETITION!
6. CRITICAL: Search queries MUST match script content at that exact timing!

**OUTPUT JSON FORMAT:**
{{
  "total_duration": {audio_duration},
  "segments": [
    {{
      "type": "avatar",
      "start": 0,
      "duration": {avatar_seg_duration},
      "search_query": null
    }},
    {{
      "type": "{"ai_image" if mode == "ai_images" else "stock_video"}",
      "start": {avatar_seg_duration},
      "duration": {media_seg_duration if media_seg_duration else "5 or 10"},
      "search_query": "business meeting"
    }},
    ...
  ]
}}

**CRITICAL - HOW TO GENERATE SEARCH QUERIES:**
1. READ the script timeline above - UNDERSTAND what the audio is saying at each time
2. For each media segment, check what time it starts
3. Look at the script text for that EXACT time range
4. Extract the MAIN TOPIC/CONCEPT being discussed at that moment
5. Convert to 1-3 SPECIFIC keywords that match stock video content

**SEARCH QUERY RULES (SUPER IMPORTANT!):**
- MUST be 1-3 words maximum (e.g., "stock market", "trading chart", "wall street")
- MUST match the script content at that EXACT timing
- Each segment MUST have a DIFFERENT search query (NO REPEATING!)
- BE HYPER-SPECIFIC to the script topic!

**TRADING/FINANCE KEYWORDS (if script is about trading/markets):**
- Good: "stock chart", "trading floor", "wall street", "candlestick chart", "forex trading", "bull market", "stock exchange", "financial graph", "market crash", "trading desk"
- Bad: "generic", "medicine", "pills", "health"

**BUSINESS KEYWORDS (if script is about business):**
- Good: "handshake", "business meeting", "office work", "laptop typing", "team collaboration", "presentation"

**TECHNOLOGY KEYWORDS (if script is about tech):**
- Good: "coding screen", "data center", "programming", "servers", "tech startup"

**NATURE/LIFESTYLE KEYWORDS (if script is about life/nature):**
- Good: "mountain sunset", "ocean waves", "forest trail", "peaceful lake"

**CRITICAL RULE:**
- READ the script! If it talks about "trading psychology" → use "trading chart" or "stock market"
- If it talks about "risk management" → use "financial risk" or "market volatility"
- If it talks about "success mindset" → use "business success" or "achievement"
- NEVER use irrelevant keywords like "medicine" for a trading video!

**IMPORTANT:**
- ANALYZE the script timeline to match media to content!
- Search queries: 1-3 words, hyper-specific to script!
- NO GENERIC QUERIES! Match the script topic!
- Each video MUST be relevant to what audio is saying at that moment!
- Last segment must end at exactly {audio_duration:.2f} seconds
- Last {last_2_min_seconds} seconds = continuous avatar

Generate the media plan now as valid JSON:
"""

        return prompt

    def _validate_and_fix_duration(
        self,
        plan: Dict,
        target_duration: float,
        verbose: bool = False
    ) -> Dict:
        """
        CRITICAL: Ensure segments add up to EXACT audio duration AND enforce max durations

        Args:
            plan: Media plan from Gemini
            target_duration: Target audio duration in seconds
            verbose: Print debugging info

        Returns:
            Fixed plan with exact duration
        """
        segments = plan.get('segments', [])

        # CRITICAL: Enforce maximum duration for stock videos (NEVER more than 10 seconds!)
        for seg in segments:
            if seg['type'] in ['stock_video', 'ai_image']:
                max_allowed = 10 if seg['type'] == 'stock_video' else 5
                if seg['duration'] > max_allowed:
                    if verbose:
                        print(f"   ⚠️  Segment at {seg['start']}s was {seg['duration']}s, capping to {max_allowed}s")
                    seg['duration'] = max_allowed

        # Calculate actual total duration from segments
        actual_duration = sum(seg['duration'] for seg in segments)

        if verbose:
            print(f"\n🔍 Duration Validation:")
            print(f"   Target: {target_duration:.2f}s")
            print(f"   Actual: {actual_duration:.2f}s")
            print(f"   Difference: {actual_duration - target_duration:.2f}s")

        # If durations match (within 0.1 second), we're good
        if abs(actual_duration - target_duration) < 0.1:
            if verbose:
                print(f"   ✅ Duration matches!")
            plan['total_duration'] = target_duration
            return plan

        # NEED TO FIX: Durations don't match
        difference = target_duration - actual_duration

        if verbose:
            print(f"   ⚠️  Adjusting last segment by {difference:.2f}s...")

        # Adjust the LAST avatar segment to fill the gap
        if segments:
            last_segment = segments[-1]
            if last_segment['type'] == 'avatar':
                # Extend or shorten last avatar segment
                last_segment['duration'] += difference
                if verbose:
                    print(f"   ✅ Last avatar segment adjusted to {last_segment['duration']:.2f}s")
            else:
                # Add a final avatar segment to fill the gap
                last_start = segments[-1]['start'] + segments[-1]['duration']
                segments.append({
                    'type': 'avatar',
                    'start': last_start,
                    'duration': difference,
                    'search_query': None
                })
                if verbose:
                    print(f"   ✅ Added final avatar segment: {difference:.2f}s")

        plan['total_duration'] = target_duration
        plan['segments'] = segments

        return plan

    def _create_fallback_plan(
        self,
        audio_duration: float,
        avatar_duration: float,
        mode: str,
        avatar_seg_duration: int,
        media_seg_duration: int
    ) -> Dict:
        """Create fallback plan if Gemini fails"""

        segments = []
        current_time = 0
        last_2_min = 120
        end_of_pattern = audio_duration - last_2_min

        # Pattern section
        while current_time < end_of_pattern:
            # Avatar segment
            segments.append({
                'type': 'avatar',
                'start': current_time,
                'duration': avatar_seg_duration
            })
            current_time += avatar_seg_duration

            # Media segment (if there's room)
            if current_time < end_of_pattern:
                duration = media_seg_duration if media_seg_duration else 5
                segments.append({
                    'type': 'ai_image' if mode == 'ai_images' else 'stock_video',
                    'start': current_time,
                    'duration': duration,
                    'search_query': 'generic'
                })
                current_time += duration

        # Last 2 minutes: full avatar
        segments.append({
            'type': 'avatar',
            'start': current_time,
            'duration': audio_duration - current_time
        })

        return {
            'total_duration': audio_duration,
            'segments': segments
        }

    def _print_media_plan(self, media_plan: Dict):
        """Print media plan in readable format"""
        print("\n📋 Media Sequence Plan:")
        print(f"   Total Duration: {media_plan['total_duration']:.2f} seconds")
        print(f"   Segments: {len(media_plan['segments'])}")
        print("\n   Timeline:")

        for i, seg in enumerate(media_plan['segments'][:10]):  # Show first 10
            end_time = seg['start'] + seg['duration']
            print(f"   [{i+1}] {seg['start']:.1f}s - {end_time:.1f}s: {seg['type'].upper()} ({seg['duration']:.1f}s)")
            if seg.get('search_query'):
                print(f"       Search: {seg['search_query']}")

        if len(media_plan['segments']) > 10:
            print(f"   ... and {len(media_plan['segments']) - 10} more segments")

    def _generate_ai_images(
        self,
        media_plan: Dict,
        script: str,
        verbose: bool = False
    ) -> List[Dict]:
        """
        Generate AI images for media plan using Replicate

        Args:
            media_plan: Media plan from Gemini
            script: Script for context
            verbose: Print progress

        Returns:
            List of generated image paths with metadata
        """
        from replicate_image_generator import ReplicateImageGenerator

        generator = ReplicateImageGenerator()
        images = []

        # Get all ai_image segments with their ORIGINAL indices
        image_segments = [
            (seg_idx, seg) for seg_idx, seg in enumerate(media_plan['segments'])
            if seg['type'] == 'ai_image'
        ]

        if verbose:
            print(f"   Generating {len(image_segments)} AI images...")

        for i, (seg_idx, segment) in enumerate(image_segments):
            if verbose:
                print(f"   [{i+1}/{len(image_segments)}] Generating image for: {segment.get('search_query', 'generic')}")

            # Generate image prompt from search query
            prompt = segment.get('search_query', 'professional background image')

            # Generate image
            try:
                image_path = generator.generate_image(
                    prompt=prompt,
                    output_dir='media_library/avatar_images'
                )

                images.append({
                    'segment_index': seg_idx,  # Use ORIGINAL index from media_plan['segments']
                    'path': image_path,
                    'prompt': prompt,
                    'duration': segment['duration'],
                    'start': segment['start']
                })

                if verbose:
                    print(f"   ✅ Image saved: {image_path}")

            except Exception as e:
                if verbose:
                    print(f"   ❌ Image generation failed: {e}")

        return images

    def _download_stock_videos(
        self,
        media_plan: Dict,
        script: str,
        stock_apis: List[str],
        verbose: bool = False
    ) -> List[Dict]:
        """
        Download stock videos for media plan

        Args:
            media_plan: Media plan from Gemini
            script: Script for context
            stock_apis: List of stock API names
            verbose: Print progress

        Returns:
            List of downloaded video paths with metadata
        """
        from stock_video_downloader import StockVideoDownloader

        downloader = StockVideoDownloader(apis=stock_apis or ['pexels'])
        videos = []

        # Get all stock_video segments with their ORIGINAL indices
        video_segments = [
            (seg_idx, seg) for seg_idx, seg in enumerate(media_plan['segments'])
            if seg['type'] == 'stock_video'
        ]

        if verbose:
            print(f"   Downloading {len(video_segments)} stock videos...")

        for i, (seg_idx, segment) in enumerate(video_segments):
            if verbose:
                print(f"   [{i+1}/{len(video_segments)}] Searching: {segment.get('search_query', 'generic')}")

            # Search and download
            try:
                video_path = downloader.search_and_download(
                    query=segment.get('search_query', 'generic'),
                    min_duration=segment['duration'],
                    output_dir='media_library/avatar_videos'
                )

                videos.append({
                    'segment_index': seg_idx,  # Use ORIGINAL index from media_plan['segments']
                    'path': video_path,
                    'query': segment.get('search_query'),
                    'duration': segment['duration'],
                    'start': segment['start']
                })

                if verbose:
                    print(f"   ✅ Video saved: {video_path}")

            except Exception as e:
                if verbose:
                    print(f"   ❌ Video download failed: {e}")

        return videos


if __name__ == "__main__":
    # Test
    generator = AvatarVideoGenerator()

    result = generator.generate_avatar_video(
        avatar_video_path="test_avatar.mp4",
        audio_path="test_audio.mp3",
        mode="ai_images",
        script="Sample script for testing",
        verbose=True
    )

    print("\n✅ Test complete!")
    print(f"Media plan: {len(result['media_plan']['segments'])} segments")

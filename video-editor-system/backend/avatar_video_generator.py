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

    def _extract_principal_keywords(
        self,
        script: str,
        verbose: bool = False
    ) -> Dict:
        """
        SUPER SMART: Extract MAIN SUBJECT + keywords from script using Gemini
        Ensures EVERY search query includes the main subject!

        Args:
            script: Full script text
            verbose: Print progress

        Returns:
            Dict with 'main_subject' and 'keywords' list
        """
        if not script or len(script.strip()) < 50:
            return {
                'main_subject': 'business',
                'keywords': ['professional', 'office', 'meeting']
            }

        if verbose:
            print("\n🧠 ANALYZING SCRIPT: Extracting MAIN SUBJECT + keywords with Gemini...")

        # Clean script for safe inclusion in prompt
        clean_script = script[:2000].replace('"', "'").replace('\n', ' ').strip()

        prompt = f"""Analyze this video script and identify the MAIN SUBJECT and keywords.

SCRIPT:
{clean_script}

TASK:
1. What is the PRIMARY TOPIC? (trading, business, technology, health, finance, marketing, etc.)
2. List 8-12 visual keywords related to that topic

EXAMPLES:
If trading script → main_subject: "trading", keywords: ["chart", "analysis", "psychology", "risk", "market", "floor", "candlestick", "forex"]
If business script → main_subject: "business", keywords: ["meeting", "handshake", "office", "team", "presentation", "growth"]
If tech script → main_subject: "technology", keywords: ["coding", "servers", "data", "programming", "startup"]

Return ONLY this JSON (no markdown, no formatting):
{{"main_subject": "topic_here", "keywords": ["keyword1", "keyword2", "keyword3"]}}
"""

        try:
            model = genai.GenerativeModel('gemini-2.5-flash')
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,  # Very low temp for consistent output
                    max_output_tokens=300,
                    response_mime_type="application/json"
                )
            )

            # Try to parse JSON response
            response_text = response.text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                # Extract content between ```json and ```
                lines = response_text.split('\n')
                response_text = '\n'.join(lines[1:-1]) if len(lines) > 2 else response_text
                response_text = response_text.replace('```json', '').replace('```', '').strip()

            result = json.loads(response_text)
            main_subject = result.get('main_subject', '').lower().strip()
            keywords = result.get('keywords', [])[:12]  # Max 12 keywords

            # Validate we got something useful
            if not main_subject or len(main_subject) == 0:
                raise ValueError("Empty main subject")

            if verbose:
                print(f"   ✅ MAIN SUBJECT: '{main_subject}'")
                print(f"   ✅ Extracted {len(keywords)} keywords: {', '.join(keywords[:8])}")

            return {
                'main_subject': main_subject,
                'keywords': keywords
            }

        except Exception as e:
            if verbose:
                print(f"   ⚠️  Keyword extraction failed: {e}")
                print(f"   🔄 Using SMART fallback based on script content...")

            # SMART FALLBACK: Analyze script for common topics
            script_lower = script.lower()

            # Check for trading/finance keywords
            if any(word in script_lower for word in ['trading', 'trader', 'stock', 'market', 'forex', 'candlestick', 'chart']):
                main_subject = 'trading'
                keywords = ['chart', 'analysis', 'psychology', 'risk', 'market', 'strategy', 'floor', 'candlestick']
            # Check for business keywords
            elif any(word in script_lower for word in ['business', 'entrepreneur', 'startup', 'company', 'corporate']):
                main_subject = 'business'
                keywords = ['meeting', 'handshake', 'office', 'team', 'presentation', 'growth', 'strategy']
            # Check for technology keywords
            elif any(word in script_lower for word in ['technology', 'coding', 'programming', 'software', 'computer', 'tech']):
                main_subject = 'technology'
                keywords = ['coding', 'servers', 'data', 'programming', 'startup', 'computer']
            # Check for finance keywords
            elif any(word in script_lower for word in ['finance', 'money', 'investment', 'wealth', 'financial']):
                main_subject = 'finance'
                keywords = ['money', 'investment', 'wealth', 'planning', 'strategy', 'growth']
            # Default fallback
            else:
                main_subject = 'professional'
                keywords = ['work', 'business', 'office', 'meeting', 'success', 'growth', 'strategy']

            if verbose:
                print(f"   ✅ SMART FALLBACK: '{main_subject}'")
                print(f"   ✅ Keywords: {', '.join(keywords)}")

            return {
                'main_subject': main_subject,
                'keywords': keywords
            }

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
        NOW WITH INTELLIGENT KEYWORD EXTRACTION!

        Args:
            audio_duration: Total audio duration in seconds
            avatar_duration: Avatar video duration in seconds
            mode: "ai_images" or "stock_videos"
            script: Optional script for context
            verbose: Print progress

        Returns:
            Dict with media plan
        """
        # STEP 1: Extract MAIN SUBJECT + keywords from script (SMART!)
        keyword_data = self._extract_principal_keywords(script, verbose) if script else {
            'main_subject': 'professional',
            'keywords': []
        }

        # Determine segment pattern based on mode
        if mode == "ai_images":
            avatar_seg_duration = 60  # 1 minute
            media_seg_duration = 5    # 5 seconds
        else:  # stock_videos
            avatar_seg_duration = 30  # 30 seconds (perfect balance!)
            media_seg_duration = 8     # 8 seconds (FIXED: was None, now enforced!)

        # Build prompt for Gemini (NOW with MAIN SUBJECT + keywords!)
        prompt = self._build_planning_prompt(
            audio_duration=audio_duration,
            avatar_duration=avatar_duration,
            mode=mode,
            avatar_seg_duration=avatar_seg_duration,
            media_seg_duration=media_seg_duration,
            script=script,
            keyword_data=keyword_data  # NEW: Pass main subject + keywords!
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
        script: str = None,
        keyword_data: Dict = None
    ) -> str:
        """Build prompt for Gemini media planning with MAIN SUBJECT + keywords"""

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

        # Build keywords section with MAIN SUBJECT (CRITICAL!)
        keywords_section = ""
        if keyword_data and keyword_data.get('main_subject'):
            main_subject = keyword_data.get('main_subject', 'professional')
            keywords = keyword_data.get('keywords', [])

            keywords_section = f"""**🎯 MAIN SUBJECT: {main_subject.upper()}**

**📋 SPECIFIC KEYWORDS (concepts within this subject):**
{', '.join(keywords) if keywords else 'general concepts'}

**🔒 CRITICAL RULE - ALWAYS USE MAIN SUBJECT:**
EVERY search query MUST start with the main subject "{main_subject}"!

**QUERY FORMAT:**
"{main_subject}" + [specific keyword]

**EXAMPLES:**
If main subject = "{main_subject}" and keywords = {keywords[:4] if keywords else ['concept1', 'concept2']}:
- Video 1: "{main_subject} {keywords[0] if keywords else 'concept'}"
- Video 2: "{main_subject} {keywords[1] if keywords else 'topic'}"
- Video 3: "{main_subject} {keywords[2] if keywords and len(keywords) > 2 else 'scene'}"
- Video 4: "{main_subject} {keywords[3] if keywords and len(keywords) > 3 else 'visual'}"

**WHY THIS MATTERS:**
- If video is about TRADING, we need "trading chart" NOT just "chart"
- If video is about TRADING, we need "trading analysis" NOT just "analysis"
- If video is about BUSINESS, we need "business meeting" NOT just "meeting"
- ALWAYS include the main subject to ensure relevance!

**CREATIVE VARIATIONS (still using main subject):**
- "{main_subject} data" → "{main_subject} analysis" → "{main_subject} graph"
- "{main_subject} strategy" → "{main_subject} planning" → "{main_subject} tactics"
- All different videos, all relevant to {main_subject}!

"""

        prompt = f"""You are a SUPER INTELLIGENT AI video planner. Create a media sequence plan.

**TASK:** Plan a video with avatar loops and {"AI images" if mode == "ai_images" else "stock videos"}.

**INPUT:**
- Audio duration: {audio_duration:.2f} seconds ({audio_duration/60:.2f} minutes)
- Avatar video duration: {avatar_duration:.2f} seconds
- Mode: {mode}

{keywords_section}{script_timeline}

**RULES:**
1. Pattern: {avatar_seg_duration} sec avatar → {media_seg_duration if media_seg_duration else "EXACTLY 8"} sec {"AI image" if mode == "ai_images" else "stock video"} → repeat
2. Last {last_2_min_seconds} seconds: FULL avatar (to match exact audio length)
3. Total duration MUST exactly match audio duration: {audio_duration:.2f} seconds
4. {"AI images are EXACTLY 5 seconds each" if mode == "ai_images" else f"Stock videos are EXACTLY {media_seg_duration if media_seg_duration else 8} seconds (NO LONGER!)"}
5. USE PRINCIPAL KEYWORDS: Build search queries from the principal keywords above!
6. CREATIVE VARIATIONS: You can reuse keywords but make variations (different phrasing)
7. Each video will be DIFFERENT because stock API returns different results
8. Match keywords to what the script is saying at that time!

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

**🔒 CRITICAL - SEARCH QUERY GENERATION RULES:**

**MANDATORY FORMAT:**
Every search query MUST follow this pattern:
"[MAIN SUBJECT]" + "[SPECIFIC KEYWORD]"

**STEP-BY-STEP PROCESS:**
1. Look at what time the video segment starts
2. Check the script timeline - what's being discussed at that time?
3. Pick a specific keyword from the list that matches that moment
4. ALWAYS combine: MAIN SUBJECT + that keyword
5. Example: Main subject="trading", scene is about "analysis" → query = "trading analysis"

**MANDATORY EXAMPLES:**
If main subject = "trading":
- Scene about charts → "trading chart" (NOT just "chart")
- Scene about analysis → "trading analysis" (NOT just "analysis")
- Scene about psychology → "trading psychology" (NOT just "psychology")
- Scene about risk → "trading risk" (NOT just "risk")
- Scene about strategies → "trading strategy" (NOT just "strategy")

If main subject = "business":
- Scene about meetings → "business meeting" (NOT just "meeting")
- Scene about growth → "business growth" (NOT just "growth")
- Scene about strategy → "business strategy" (NOT just "strategy")

**ABSOLUTE REQUIREMENTS:**
- EVERY query MUST start with the main subject
- No exceptions - even if keyword seems clear, include main subject
- This ensures ALL videos are relevant to the main topic
- Stock API will return different videos for each query
- Main subject + different keywords = different but relevant videos

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
        from image_generator import ImageGenerator

        generator = ImageGenerator()
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
        ENSURES: Each video is DIFFERENT (no duplicates!)

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
        used_queries = set()  # CRITICAL: Track used queries to prevent duplicates!

        # Get all stock_video segments with their ORIGINAL indices
        video_segments = [
            (seg_idx, seg) for seg_idx, seg in enumerate(media_plan['segments'])
            if seg['type'] == 'stock_video'
        ]

        if verbose:
            print(f"   Downloading {len(video_segments)} stock videos...")
            print(f"   🔒 ENSURING: Each video will be DIFFERENT (no repeats!)")

        for i, (seg_idx, segment) in enumerate(video_segments):
            query = segment.get('search_query', 'generic')

            # CRITICAL: If query was already used, modify it to get DIFFERENT video
            original_query = query
            suffix = 1
            while query in used_queries:
                query = f"{original_query} {suffix}"  # Add number to make it unique
                suffix += 1
                if verbose and suffix == 2:
                    print(f"   ⚠️  Query '{original_query}' already used, trying '{query}'")

            used_queries.add(query)  # Mark this query as used

            if verbose:
                print(f"   [{i+1}/{len(video_segments)}] Searching: {query}")

            # Search and download
            try:
                video_path = downloader.search_and_download(
                    query=query,
                    min_duration=segment['duration'],
                    output_dir='media_library/avatar_videos'
                )

                videos.append({
                    'segment_index': seg_idx,  # Use ORIGINAL index from media_plan['segments']
                    'path': video_path,
                    'query': query,  # Use the actual query (may be modified for uniqueness)
                    'duration': segment['duration'],
                    'start': segment['start']
                })

                if verbose:
                    print(f"   ✅ Video saved: {video_path}")

            except Exception as e:
                if verbose:
                    print(f"   ❌ Video download failed: {e}")

        if verbose:
            print(f"\n   ✅ Downloaded {len(videos)} DIFFERENT videos (guaranteed no duplicates!)")

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

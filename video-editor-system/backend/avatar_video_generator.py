#!/usr/bin/env python3
"""
Avatar AI Video Generator
Creates videos with avatar loops + AI images or stock videos
"""

import os
import time
import random
import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        image_style: Dict = None,
        image_provider: str = "replicate",
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
            image_style: Image style dict (id, name, visual_rules, etc.) for AI Director prompt planning
            image_provider: "replicate" (default) or "gemini" for image generation backend
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
                print("\n🖼️  Step 4: Planning + Generating AI images...")
            media_items = self._generate_ai_images(
                media_plan, script, verbose,
                image_style=image_style,
                image_provider=image_provider,
                audio_duration=audio_duration,
            )
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
        Extract COMPLETE compound search queries from script using Gemini.
        Returns ready-to-use queries like "trading psychology" not just "psychology".

        Args:
            script: Full script text
            verbose: Print progress

        Returns:
            Dict with 'main_subject' and 'search_queries' list of compound strings
        """
        if not script or len(script.strip()) < 50:
            return {
                'main_subject': 'business',
                'search_queries': [
                    'business meeting professional', 'office team collaboration',
                    'business strategy planning', 'corporate presentation growth',
                    'business success achievement', 'professional workspace',
                ]
            }

        if verbose:
            print("\n🧠 ANALYZING SCRIPT: Extracting compound search queries with Gemini...")

        # Keep original multilingual text — Gemini handles any language natively.
        # Only escape chars that would break the prompt string, NOT the content.
        script_len = len(script)
        parts = []
        if script_len <= 4000:
            parts.append(script)
        else:
            parts.append(script[:1500])
            mid = script_len // 2
            parts.append(script[mid-750:mid+750])
            parts.append(script[-1000:])
        raw_snippet = ' ... '.join(parts)
        # Only escape backslashes and strip excessive whitespace — keep all languages intact
        safe_script = raw_snippet.replace('\\', ' ').replace('\n', ' ').replace('\r', ' ')
        # Collapse multiple spaces
        import re as _re_ws
        safe_script = _re_ws.sub(r'\s+', safe_script).strip()

        prompt = f"""You are a professional stock video researcher for a B-roll editor.
Analyze this script and generate PRECISE, SCENE-SPECIFIC stock video search queries.
The script may be in French, Arabic, English, or any language — understand the meaning and translate to English queries.

SCRIPT:
{safe_script}

YOUR JOB:
1. Identify the MAIN TOPIC of this script (e.g. "trading", "health", "technology", "business")
2. For each part of the script, think about what VISUAL SCENE would match on screen
3. Generate 20 search queries that are VISUALLY SPECIFIC to what the script describes

FOR EACH QUERY, think about these 5 DIMENSIONS:
- Main subject: What is the primary object/person shown? (e.g. "trader", "chart", "laptop")
- Action: What is happening? (e.g. "analyzing", "typing", "running")
- Environment: Where is the scene? (e.g. "office", "trading floor", "gym")
- Camera style: What angle/shot? (e.g. "close-up", "aerial", "wide shot")
- Mood/Time: What feeling/time? (e.g. "dramatic", "sunrise", "night city")

CRITICAL RULES:
- EVERY query must be a VISUAL SCENE description, NOT an abstract concept
- BAD: "trading psychology" (you can't film psychology!)
- GOOD: "stressed trader watching red charts" or "man thinking at desk screens"
- BAD: "risk management" (abstract concept!)
- GOOD: "trader analyzing multiple monitors" or "financial charts red arrows"
- EVERY query must describe something a CAMERA can actually film
- Include the main topic context in each query so results stay relevant
- ALL queries IN ENGLISH (translate from any language)
- Each query should be 3-5 words, visually descriptive

EXAMPLES:
Topic=trading: ["trader watching multiple screens", "candlestick chart close up", "stock market trading floor", "man analyzing financial data", "stock price green arrows up", "worried trader red charts", "wall street building exterior", "typing on trading platform", "money growth chart animation", "cryptocurrency bitcoin screen", "office desk multiple monitors", "stock exchange big screen", "trader celebrating profit", "market crash red numbers", "financial newspaper coffee desk"]
Topic=fitness: ["athlete running sunrise road", "gym weightlifting close up", "woman yoga mat morning", "healthy meal preparation kitchen", "personal trainer coaching gym", "runner crossing finish line", "swimming pool underwater shot", "stretching exercise park outdoor"]

Return ONLY this JSON, nothing else:
{{"main_subject": "topic", "search_queries": ["query1", "query2", "query3", "query4", "query5", "query6", "query7", "query8", "query9", "query10", "query11", "query12", "query13", "query14", "query15", "query16", "query17", "query18", "query19", "query20"]}}"""

        try:
            model = genai.GenerativeModel('gemini-2.5-flash')
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=1000
                )
            )

            # Safe text extraction — response.text can raise on blocked content
            response_text = ''
            try:
                response_text = response.text.strip() if response.text else ''
            except (ValueError, AttributeError):
                # Try alternate path for blocked/partial responses
                try:
                    response_text = response.candidates[0].content.parts[0].text.strip()
                except Exception:
                    pass

            if not response_text:
                raise ValueError("Empty response from Gemini")

            if verbose:
                print(f"   📝 Gemini raw response (first 200 chars): {response_text[:200]}")

            # Strip markdown fences
            if '```' in response_text:
                response_text = response_text.replace('```json', '').replace('```', '').strip()

            # Extract first valid JSON object
            start = response_text.find('{')
            end = response_text.rfind('}')
            if start == -1 or end == -1:
                raise ValueError(f"No JSON in response. Got: {response_text[:150]}")
            json_str = response_text[start:end+1]

            # Fix common Gemini JSON issues
            import re as _re
            json_str = _re.sub(r',\s*([\]}])', r'\1', json_str)  # trailing commas
            json_str = _re.sub(r'[\x00-\x1f]', ' ', json_str)   # control chars

            result = json.loads(json_str)
            main_subject = result.get('main_subject', '').lower().strip()
            search_queries = result.get('search_queries', [])

            if not main_subject:
                raise ValueError("Empty main subject")
            if not search_queries:
                raise ValueError("Empty search queries")

            # Filter output queries: keep only ASCII for stock API search
            clean_queries = []
            for q in search_queries[:20]:
                safe_q = str(q).encode('ascii', errors='ignore').decode('ascii').strip()
                if safe_q and len(safe_q) <= 50:
                    clean_queries.append(safe_q)

            if len(clean_queries) < 3:
                raise ValueError(f"Too few valid queries: {len(clean_queries)}")

            if verbose:
                print(f"   ✅ MAIN SUBJECT: '{main_subject}'")
                print(f"   ✅ {len(clean_queries)} search queries: {', '.join(clean_queries[:6])}...")

            return {
                'main_subject': main_subject,
                'search_queries': clean_queries
            }

        except Exception as e:
            if verbose:
                print(f"   ⚠️  Keyword extraction failed: {e}")
                print(f"   🔄 Using SMART fallback based on script content...")

            # SMART FALLBACK with compound queries
            script_lower = script.lower()

            if any(w in script_lower for w in [
                'trading', 'trader', 'stock', 'forex', 'candlestick', 'chart',
                'bourse', 'marchés', 'boursier', 'cotation', 'investissement'
            ]):
                main_subject = 'trading'
                search_queries = [
                    'trader watching multiple screens', 'candlestick chart close up',
                    'stock market trading floor', 'man analyzing financial data',
                    'stock price green arrows up', 'worried trader red charts',
                    'wall street building exterior', 'typing on trading platform',
                    'cryptocurrency bitcoin screen', 'office desk multiple monitors',
                    'stock exchange big screen', 'trader celebrating profit',
                    'market crash red numbers', 'financial newspaper coffee desk',
                    'laptop stock chart graph', 'person counting money cash',
                    'city skyline night financial', 'hands typing keyboard trading',
                    'chart going up green', 'stressed man computer screen'
                ]
            elif any(w in script_lower for w in [
                'business', 'entrepreneur', 'startup', 'company',
                'entreprise', 'affaires', 'commerce', 'gestion'
            ]):
                main_subject = 'business'
                search_queries = [
                    'business team meeting office', 'handshake deal close up',
                    'entrepreneur working laptop cafe', 'office building exterior modern',
                    'presentation screen conference room', 'typing laptop coffee desk',
                    'team brainstorming whiteboard', 'manager leading team meeting',
                    'startup office open space', 'signing contract pen paper',
                    'growth chart screen presentation', 'walking into office building',
                    'phone call business suit', 'team celebrating success office',
                    'desk workspace organized laptop'
                ]
            elif any(w in script_lower for w in [
                'technology', 'coding', 'programming', 'software', 'tech',
                'technologie', 'logiciel', 'informatique', 'numérique'
            ]):
                main_subject = 'technology'
                search_queries = [
                    'programmer typing code screen', 'server room data center',
                    'robot arm factory automation', 'smartphone app close up',
                    'circuit board close up macro', 'person using vr headset',
                    'laptop coding dark room', 'network cables server rack',
                    'tech startup team working', 'drone flying aerial shot',
                    'digital screen data flowing', 'hands assembling electronics'
                ]
            elif any(w in script_lower for w in [
                'finance', 'money', 'investment', 'wealth',
                'argent', 'richesse', 'épargne', 'financier'
            ]):
                main_subject = 'finance'
                search_queries = [
                    'counting money cash hands', 'bank building exterior modern',
                    'gold coins pile close up', 'credit card payment terminal',
                    'financial advisor meeting client', 'stock chart laptop screen',
                    'piggy bank saving coins', 'wallet money bills close up',
                    'real estate house keys', 'calculator pen financial documents',
                    'atm machine withdrawing cash', 'luxury car wealth lifestyle'
                ]
            elif any(w in script_lower for w in [
                'health', 'fitness', 'workout', 'exercise',
                'santé', 'sport', 'musculation', 'bien-être'
            ]):
                main_subject = 'fitness'
                search_queries = [
                    'athlete running sunrise road', 'gym weightlifting close up',
                    'woman yoga mat morning', 'healthy meal prep kitchen',
                    'personal trainer coaching gym', 'runner crossing finish line',
                    'swimming pool underwater shot', 'stretching exercise park outdoor',
                    'jumping rope workout intense', 'protein shake smoothie blender',
                    'group fitness class energy', 'measuring tape body fitness'
                ]
            elif any(w in script_lower for w in [
                'motivation', 'success', 'mindset', 'goal',
                'succès', 'objectif', 'confiance', 'réussite'
            ]):
                main_subject = 'motivation'
                search_queries = [
                    'person standing mountain top', 'runner crossing finish line',
                    'sunrise over city skyline', 'climbing stairs determination',
                    'writing goals notebook pen', 'team high five celebration',
                    'person meditating peaceful nature', 'athlete training hard gym',
                    'graduation ceremony cap throw', 'walking forward road horizon',
                    'boxing punching bag intense', 'person reading book library'
                ]
            else:
                main_subject = 'professional'
                search_queries = [
                    'person working laptop office', 'team meeting conference room',
                    'typing keyboard close up', 'city skyline timelapse day',
                    'professional handshake business', 'office building glass modern'
                ]

            if verbose:
                print(f"   ✅ SMART FALLBACK: '{main_subject}'")
                print(f"   ✅ Queries: {', '.join(search_queries[:4])}...")

            return {
                'main_subject': main_subject,
                'search_queries': search_queries
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
        # STEP 1: Extract compound search queries from script
        keyword_data = self._extract_principal_keywords(script, verbose) if script else {
            'main_subject': 'professional',
            'search_queries': ['professional business meeting', 'office work success']
        }

        # Determine segment pattern based on mode
        if mode == "ai_images":
            avatar_seg_duration = 60  # 1 minute
            media_seg_duration = 5    # 5 seconds
        else:  # stock_videos
            avatar_seg_duration = 50  # 50 seconds avatar
            media_seg_duration = 10   # 10 seconds stock video

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

        # Call Gemini — low temperature for consistent plan adherence
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.3,
                max_output_tokens=8192
            )
        )

        # Parse response
        try:
            response_text = response.text.strip() if response.text else ''
            if not response_text:
                raise ValueError("Empty response from Gemini")
            # Strip markdown fences
            if '```' in response_text:
                response_text = response_text.replace('```json', '').replace('```', '').strip()
            # Extract JSON object if surrounded by extra text
            start = response_text.find('{')
            end = response_text.rfind('}')
            if start != -1 and end != -1:
                response_text = response_text[start:end+1]
            # Fix trailing commas (common Gemini JSON issue)
            import re as _re2
            response_text = _re2.sub(r',\s*([\]}])', r'\1', response_text)
            plan = json.loads(response_text)
        except Exception as _plan_ex:
            if verbose:
                print(f"   ⚠️  Plan parse failed: {_plan_ex}, using fallback")
            # Fallback: create simple plan with real compound queries
            plan = self._create_fallback_plan(
                audio_duration=audio_duration,
                avatar_duration=avatar_duration,
                mode=mode,
                avatar_seg_duration=avatar_seg_duration,
                media_seg_duration=media_seg_duration,
                keyword_data=keyword_data
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
        """Build Gemini media planning prompt using pre-extracted compound search queries."""

        last_2_min_seconds = 120
        cycle_duration = avatar_seg_duration + media_seg_duration

        # --- Script timeline aligned to stock video slot times ---
        chars_per_second = len(script) / audio_duration if script and audio_duration > 0 else 0
        script_chunks = []
        if script and chars_per_second > 0:
            current_time = 0
            while current_time < audio_duration - last_2_min_seconds:
                stock_start = current_time + avatar_seg_duration
                window_start = max(0, stock_start - 10)
                window_end = min(audio_duration, stock_start + 20)
                start_char = int(window_start * chars_per_second)
                end_char = int(window_end * chars_per_second)
                chunk_text = script[start_char:end_char] if start_char < len(script) else ""
                # Keep only ASCII for safe inclusion
                chunk_text = chunk_text.encode('ascii', errors='replace').decode('ascii').replace('"', "'")
                if chunk_text:
                    script_chunks.append({'time': stock_start, 'text': chunk_text[:180]})
                current_time += cycle_duration

        script_timeline = ""
        if script_chunks:
            script_timeline = "SCRIPT CONTEXT PER STOCK VIDEO SLOT:\n"
            for chunk in script_chunks[:30]:
                script_timeline += f"  [{chunk['time']:.0f}s]: \"{chunk['text']}...\"\n"
            script_timeline += "\n"

        # --- Pre-built search queries from keyword extraction ---
        main_subject = keyword_data.get('main_subject', 'professional') if keyword_data else 'professional'
        search_queries = keyword_data.get('search_queries', []) if keyword_data else []
        queries_list = '\n'.join(f'  - "{q}"' for q in search_queries)

        # Number of stock video slots expected
        num_slots = int((audio_duration - last_2_min_seconds) / cycle_duration)

        prompt = f"""You are a professional video editor assigning B-roll footage to a media plan.
Your job: pick the MOST VISUALLY RELEVANT stock video query for each slot based on what the script says AT THAT MOMENT.

AUDIO: {audio_duration:.1f}s ({audio_duration/60:.1f} min)
PATTERN: {avatar_seg_duration}s avatar → {media_seg_duration}s stock video → repeat until last {last_2_min_seconds}s
LAST {last_2_min_seconds}s: avatar only (no stock videos)
EXPECTED STOCK VIDEO SLOTS: ~{num_slots}

APPROVED SEARCH QUERIES (use ONLY these, or close variations):
{queries_list}

{script_timeline}
ASSIGNMENT RULES:
1. READ the script context for each time slot carefully
2. Pick the query that BEST ILLUSTRATES what is being said at that exact moment
3. If the script talks about "losing money" → pick a query with "red charts" or "loss", NOT "profit growth"
4. If the script talks about "working hard" → pick "typing at desk" or "office work", NOT "celebration"
5. The video must MAKE SENSE when shown alongside the narration
6. You CAN reuse queries if they fit multiple moments
7. ALL queries must be in ENGLISH, 3-5 words, visually specific
8. Total duration must equal exactly {audio_duration:.1f}s
9. Last segment must be avatar filling up to {audio_duration:.1f}s

OUTPUT — valid JSON only, no markdown:
{{
  "total_duration": {audio_duration:.1f},
  "main_subject": "{main_subject}",
  "segments": [
    {{"type": "avatar", "start": 0, "duration": {avatar_seg_duration}, "search_query": null}},
    {{"type": "{"ai_image" if mode == "ai_images" else "stock_video"}", "start": {avatar_seg_duration}, "duration": {media_seg_duration}, "search_query": "{search_queries[0] if search_queries else main_subject + ' analysis'}"}},
    {{"type": "avatar", "start": {avatar_seg_duration + media_seg_duration}, "duration": {avatar_seg_duration}, "search_query": null}},
    ... (continue pattern until {audio_duration:.1f}s, last 2 min = avatar only)
  ]
}}
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
                max_allowed = 10 if seg['type'] == 'stock_video' else 5  # stock=10s, ai_image=5s
                if seg['duration'] > max_allowed:
                    if verbose:
                        print(f"   ⚠️  Segment at {seg['start']}s was {seg['duration']}s, capping to {max_allowed}s")
                    seg['duration'] = max_allowed

            # LANGUAGE SAFETY: Strip any non-ASCII characters from search queries
            # Stock video APIs (Pexels, Pixabay) only work with English/ASCII search terms
            if seg.get('search_query'):
                original_query = seg['search_query']
                # Keep only ASCII printable characters (removes Arabic, Chinese, accented chars, etc.)
                safe_query = original_query.encode('ascii', errors='ignore').decode('ascii').strip()
                # If query became empty after stripping (was fully non-English), use main subject
                if not safe_query:
                    safe_query = plan.get('main_subject', 'professional')
                    if verbose:
                        print(f"   🌍 Non-English query '{original_query}' → replaced with '{safe_query}'")
                elif safe_query != original_query and verbose:
                    print(f"   🌍 Sanitized query: '{original_query}' → '{safe_query}'")
                seg['search_query'] = safe_query

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
        media_seg_duration: int,
        keyword_data: Dict = None
    ) -> Dict:
        """Create fallback plan if Gemini fails — uses real compound queries"""

        # Get pre-built queries from keyword extraction
        search_queries = []
        if keyword_data:
            search_queries = keyword_data.get('search_queries', [])
        if not search_queries:
            main_subject = (keyword_data or {}).get('main_subject', 'professional')
            search_queries = [f'{main_subject} analysis', f'{main_subject} strategy',
                              f'{main_subject} data visualization', f'{main_subject} work',
                              f'{main_subject} planning', f'{main_subject} success']

        segments = []
        current_time = 0
        last_2_min = 120
        end_of_pattern = audio_duration - last_2_min
        query_idx = 0

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
                query = search_queries[query_idx % len(search_queries)]
                query_idx += 1
                segments.append({
                    'type': 'ai_image' if mode == 'ai_images' else 'stock_video',
                    'start': current_time,
                    'duration': duration,
                    'search_query': query
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
        verbose: bool = False,
        image_style: Dict = None,
        image_provider: str = "replicate",
        audio_duration: float = None,
    ) -> List[Dict]:
        """
        Generate AI images for avatar video using Gemini Director for prompt planning.

        FORMULA: 1 image per minute of audio.
        Each image gets a 400+ char high-quality prompt from the AI Director.
        Supports two image providers: 'replicate' (Flux) or 'gemini' (Gemini 2.5 Flash).

        Args:
            media_plan: Media plan from Gemini (segments)
            script: Full script text for AI Director prompt planning
            verbose: Print progress
            image_style: Style dict with visual_rules, lighting, composition, etc.
            image_provider: "replicate" or "gemini"
            audio_duration: Total audio duration in seconds (for Director planning)

        Returns:
            List of generated image paths with metadata
        """
        images = []

        # Get all ai_image segments with their ORIGINAL indices
        image_segments = [
            (seg_idx, seg) for seg_idx, seg in enumerate(media_plan['segments'])
            if seg['type'] == 'ai_image'
        ]

        if not image_segments:
            return images

        n_images = len(image_segments)

        if verbose:
            print(f"   📋 Planning {n_images} high-quality image prompts with Gemini Director...")

        # ── Step 1: Use AI Director to plan high-quality prompts ──────────────
        director_prompts = []  # list of 400+ char prompts

        if script and len(script.strip()) > 50:
            try:
                from config import Config
                from auto_images.director_client import DirectorClient

                director_api_key = Config.get_director_gemini_api_key()
                director = DirectorClient(api_key=director_api_key)

                # Use the specialised avatar planner (1 image per minute)
                eff_duration = audio_duration if audio_duration else n_images * 60.0
                style = image_style or {
                    'id': 'cinematic',
                    'name': 'Cinematic',
                    'description': 'Professional cinematic photography',
                    'visual_rules': ['cinematic lighting', 'sharp focus', 'professional composition'],
                    'negative_rules': ['blurry', 'low quality', 'text', 'watermark'],
                    'composition': 'Rule of thirds, dynamic framing',
                    'lighting': 'Dramatic cinematic lighting',
                    'color_palette': ['Deep blues', 'Warm golds', 'Rich contrast'],
                }

                plan = director.plan_avatar_images(
                    script_text=script,
                    style=style,
                    audio_duration_seconds=eff_duration,
                    verbose=verbose,
                )

                director_prompts = [scene.image_prompt for scene in plan.scenes]

                if verbose:
                    print(f"   ✅ Director planned {len(director_prompts)} prompts")
                    if director_prompts:
                        print(f"   Sample prompt length: {len(director_prompts[0])} chars")

            except Exception as e:
                if verbose:
                    print(f"   ⚠️  Director planning failed: {e}")
                    print(f"   🔄 Falling back to search-query prompts...")
                director_prompts = []

        # ── Step 2: Generate images using chosen provider ─────────────────────
        if verbose:
            provider_label = "Gemini Imagen 3" if image_provider == "gemini" else "Replicate (Flux)"
            print(f"   🖼️  Generating {n_images} images with {provider_label}...")

        output_dir = 'media_library/avatar_images'

        for i, (seg_idx, segment) in enumerate(image_segments):
            # Pick prompt: Director-planned (rich) or fallback (search query)
            if i < len(director_prompts) and director_prompts[i]:
                prompt = director_prompts[i]
            else:
                prompt = segment.get('search_query', 'professional cinematic background')

            if verbose:
                print(f"   [{i+1}/{n_images}] Generating image ({len(prompt)} chars)...")

            try:
                if image_provider == "gemini":
                    image_path = self._generate_image_gemini(prompt, output_dir, i)
                else:
                    from image_generator import ImageGenerator
                    generator = ImageGenerator()
                    image_path = generator.generate_image(
                        prompt=prompt,
                        output_dir=output_dir,
                    )

                images.append({
                    'segment_index': seg_idx,
                    'path': image_path,
                    'prompt': prompt,
                    'duration': segment['duration'],
                    'start': segment['start'],
                })

                if verbose:
                    print(f"   ✅ Saved: {image_path}")

            except Exception as e:
                if verbose:
                    print(f"   ❌ Image generation failed: {e}")

        return images

    def _generate_image_gemini(self, prompt: str, output_dir: str, index: int) -> str:
        """
        Generate a single image using Gemini Imagen 3 API.
        Uses imagen-3.0-generate-002 (primary) with fallback to gemini-2.0-flash.
        Returns path to saved PNG file (1920×1080).
        """
        from pathlib import Path as _Path
        import io as _io

        try:
            from google import genai as _genai
            from google.genai import types as _types
        except ImportError:
            raise ImportError("google-genai not installed. Run: pip install google-genai")

        try:
            from PIL import Image as _Image
        except ImportError:
            raise ImportError("Pillow not installed. Run: pip install Pillow")

        from config import Config

        api_key = Config.get_gemini_image_api_key()
        if not api_key:
            raise ValueError("Gemini Imagen 3 API key not configured. Add it in Settings under 'Gemini Imagen 3 API Key'.")

        client = _genai.Client(api_key=api_key)

        cinematic_prompt = (
            f"Cinematic 16:9 widescreen photograph, photorealistic, 1080p high detail. "
            f"{prompt}. "
            f"Sharp focus, professional lighting, no text, no watermark, no logos."
        )

        image_bytes = None

        # Primary: Try Imagen 3 (best quality)
        try:
            response = client.models.generate_images(
                model="imagen-3.0-generate-002",
                prompt=cinematic_prompt,
                config=_types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="16:9",
                ),
            )
            if response.generated_images:
                image_bytes = response.generated_images[0].image.image_bytes
        except Exception as _imagen_err:
            # Fallback: Use gemini-2.0-flash-preview-image-generation
            try:
                response = client.models.generate_content(
                    model="gemini-2.0-flash-preview-image-generation",
                    contents=[cinematic_prompt],
                    config=_types.GenerateContentConfig(
                        response_modalities=["IMAGE", "TEXT"],
                    ),
                )
                for candidate in response.candidates:
                    for part in candidate.content.parts:
                        if hasattr(part, "inline_data") and part.inline_data and part.inline_data.data:
                            image_bytes = part.inline_data.data
                            break
                    if image_bytes:
                        break
            except Exception:
                raise ValueError(f"Imagen 3 failed: {_imagen_err}. Fallback also failed.")

        if not image_bytes:
            raise ValueError("No image data returned by Gemini Imagen 3")

        # Upscale to 1920×1080
        img = _Image.open(_io.BytesIO(image_bytes)).convert("RGB")
        img = img.resize((1920, 1080), _Image.LANCZOS)

        # Save
        out_dir = _Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"imagen3_avatar_{index:03d}.png"
        img.save(str(out_path), "PNG")

        return str(out_path)

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
        # Thread-safe tracking of used video IDs across all downloads
        import threading
        used_video_ids = set()
        used_ids_lock = threading.Lock()

        # Get all stock_video segments with their ORIGINAL indices
        video_segments = [
            (seg_idx, seg) for seg_idx, seg in enumerate(media_plan['segments'])
            if seg['type'] == 'stock_video'
        ]

        if verbose:
            print(f"   Downloading {len(video_segments)} stock videos (no duplicates!)...")

        tasks = [(seg_idx, segment, segment.get('search_query', 'professional')) for seg_idx, segment in video_segments]

        if verbose:
            print(f"   Downloading {len(tasks)} stock videos in parallel (4 workers)...")

        def _download_one(args):
            seg_idx, segment, query = args
            try:
                with used_ids_lock:
                    snapshot = set(used_video_ids)
                path, vid_id = downloader.search_and_download(
                    query=query,
                    min_duration=3,  # Accept 3s+ clips — we re-encode to exact target anyway
                    output_dir='media_library/avatar_videos',
                    exclude_ids=snapshot
                )
                with used_ids_lock:
                    used_video_ids.add(vid_id)
                return {
                    'segment_index': seg_idx,
                    'path': path,
                    'query': query,
                    'video_id': vid_id,
                    'duration': segment['duration'],
                    'start': segment['start']
                }
            except Exception as e:
                if verbose:
                    print(f"   ❌ Download failed for '{query}': {e}")
                return None

        # Parallel downloads — 4 concurrent API calls
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_download_one, t): t for t in tasks}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    videos.append(result)
                    if verbose:
                        print(f"   ✅ [{len(videos)}/{len(tasks)}] {result['query']} → {result['video_id']}")

        if verbose:
            print(f"\n   ✅ Downloaded {len(videos)} DIFFERENT videos in parallel!")

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

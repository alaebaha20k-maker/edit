#!/usr/bin/env python3
"""
Script Generator - 3-CHUNK ARCHITECTURE (PRODUCTION)
- ALWAYS uses 3 chunks (30/40/30 split)
- Loads user's formula from settings
- Total API calls: 3 (one per chunk)
- Rate limit safe: 20 calls/min ÷ 3 = 6-7 videos/min max
"""

import re
import time
import google.generativeai as genai
from typing import Dict, List
from config import Config
from niche_manager import NicheManager
from settings_manager import SettingsManager
from chunk_planner import ChunkPlanner


class ScriptGenerator3Chunk:
    """
    Production script generator using proven 3-chunk architecture

    API CALL COUNT:
    - Title generation: 1 call (handled separately)
    - Script chunk 1: 1 call
    - Script chunk 2: 1 call
    - Script chunk 3: 1 call
    - TOTAL per video: 4 calls

    Free tier limit: 20 calls/min
    Maximum videos: 5 per minute
    """

    def __init__(self):
        """Initialize Gemini API"""
        api_key = Config.get_gemini_api_key()
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")

        genai.configure(api_key=api_key)
        self.api_key = api_key

    def generate_script(
        self,
        title: str,
        niche_id: str,
        length: int = 10000,
        verbose: bool = True
    ) -> Dict:
        """
        Generate script using 3-chunk architecture with user's formula

        Args:
            title: Video title
            niche_id: Niche ID
            length: Target length (1,000 - 80,000 characters)
            verbose: Print progress

        Returns:
            Dict with script, stats, validation info
        """
        from settings_manager import SettingsManager

        start_time = time.time()

        # Validate length
        if not Config.validate_script_length(length):
            raise ValueError(
                f"Length must be between {Config.MIN_SCRIPT_LENGTH} and {Config.MAX_SCRIPT_LENGTH}"
            )

        # Get niche
        niche = NicheManager.get_niche(niche_id)
        if not niche:
            raise ValueError(f"Niche not found: {niche_id}")

        # Load user's script formula from settings
        script_formula = SettingsManager.load_formula('script')

        if verbose:
            print(f"\n{'='*70}")
            print(f"🎬 3-CHUNK SCRIPT GENERATION")
            print(f"{'='*70}")
            print(f"Title: {title}")
            print(f"Target: {length:,} characters")
            print(f"Niche: {niche['name']} ({niche['language']})")
            print(f"Chunks: 3 (30% + 40% + 30%)")
            print(f"{'='*70}\n")

        # Plan chunks using ChunkPlanner
        planner = ChunkPlanner(length)
        chunks = planner.plan()

        if verbose:
            print(f"📦 Chunk Plan:")
            for chunk in chunks:
                print(f"   Chunk {chunk.index}: {chunk.role} ({chunk.target_chars:,} chars)")
            print()

        # Generate each chunk
        generated_chunks = []
        previous_context = ""

        for chunk in chunks:
            if verbose:
                print(f"🎨 Generating Chunk {chunk.index}/3: {chunk.role}...")

            # Build prompt for this chunk
            prompt = self._build_chunk_prompt(
                title=title,
                niche=niche,
                formula=script_formula,
                chunk=chunk,
                previous_context=previous_context
            )

            # Determine temperature based on role
            temp = self._get_temperature(chunk.role)

            # Call API
            model = genai.GenerativeModel('gemini-2.5-flash')
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=temp,
                    max_output_tokens=65536,
                    top_p=0.95,
                    top_k=40
                )
            )

            chunk_text = response.text.strip()
            generated_chunks.append(chunk_text)

            if verbose:
                print(f"✅ Chunk {chunk.index}: {len(chunk_text):,} chars")

            # Save last 2-3 sentences as context for next chunk
            if chunk.index < len(chunks):
                sentences = [s.strip() for s in re.split(r'[.!?]', chunk_text) if len(s.strip()) > 15]
                previous_context = '. '.join(sentences[-3:]) + '.' if len(sentences) >= 3 else chunk_text[-300:]

            # Rate limit protection
            if chunk.index < len(chunks):
                time.sleep(1.5)

        # Merge chunks
        if verbose:
            print(f"\n🔗 Merging chunks...")

        full_script = self._merge_chunks(generated_chunks)

        # Clean script
        full_script = self._clean_script(full_script)

        # Validate
        validation = self._validate_script(full_script, title, length)

        # Stats
        char_count = len(full_script)
        word_count = len(full_script.split())
        generation_time = time.time() - start_time

        if verbose:
            print(f"\n📊 FINAL STATS:")
            print(f"   Characters: {char_count:,}")
            print(f"   Words: {word_count:,}")
            print(f"   Target: {length:,} (±3%)")
            print(f"   Accuracy: {100 - abs(char_count - length)/length*100:.1f}%")
            print(f"   Time: {generation_time:.1f}s")
            print(f"   Valid: {validation['valid']}")
            if not validation['valid']:
                print(f"   Errors: {', '.join(validation['errors'])}")
            print(f"{'='*70}\n")

        return {
            'script': full_script,
            'stats': {
                'chars': char_count,
                'words': word_count,
                'time': generation_time
            },
            'validation': validation,
            'chunks_used': len(chunks)
        }

    def _build_chunk_prompt(
        self,
        title: str,
        niche: Dict,
        formula: str,
        chunk: 'ChunkConfig',
        previous_context: str
    ) -> str:
        """
        Build role-locked prompt for a specific chunk

        This is the CORE of the 3-chunk architecture.
        Each chunk gets a tailored prompt based on its role.
        """
        product = niche.get('product', 'our platform')
        language = niche['language']
        niche_name = niche['name']

        # Fill formula placeholders
        formula_filled = formula.replace('{title}', title)
        formula_filled = formula_filled.replace('{niche}', niche_name)
        formula_filled = formula_filled.replace('{language}', language)
        formula_filled = formula_filled.replace('{target_length}', str(chunk.target_chars))

        # Role-specific instructions
        if chunk.role == "HOOK_AND_FRAMEWORK":
            role_instruction = f"""
YOUR ROLE IN THIS CHUNK (1 of 3):
- Create magnetic hook (first 10-15 seconds)
- Establish framework and setup
- Create curiosity and tension
- Do NOT explain everything - leave mystery
- This is the OPENING, not the full story

TARGET: {chunk.target_chars:,} characters for this chunk."""

        elif chunk.role == "DEEP_INSIGHTS_AND_EXAMPLES":
            role_instruction = f"""
YOUR ROLE IN THIS CHUNK (2 of 3):
- Develop the core content
- Add deep insights and examples
- Build on the hook from previous chunk
- Explore the topic thoroughly
- Keep engagement high

PREVIOUS CONTEXT (continue seamlessly from this):
"{previous_context}"

TARGET: {chunk.target_chars:,} characters for this chunk."""

        else:  # IMPLEMENTATION_AND_CLOSE
            role_instruction = f"""
YOUR ROLE IN THIS CHUNK (3 of 3 - FINAL):
- Bring everything together
- Provide actionable insights or resolution
- Create memorable conclusion
- Echo the opening hook with new meaning
- End powerfully

PREVIOUS CONTEXT (continue seamlessly from this):
"{previous_context}"

TARGET: {chunk.target_chars:,} characters for this chunk."""

        # Build full prompt
        prompt = f"""You are an elite scriptwriter creating voice-ready narration.

TITLE: "{title}"

NICHE: {niche_name}
LANGUAGE: {language}

{role_instruction}

USER'S SCRIPT FORMULA (follow this structure):
{formula_filled}

════════════════════════════════════════════════════════════
CRITICAL OUTPUT RULES (MANDATORY)
════════════════════════════════════════════════════════════

YOU MUST OUTPUT:
- ONE continuous block of plain text
- RAW VOICE TEXT ONLY
- No visual cues (NO "VISUAL:", "VIDEO:", "SHOW:")
- No narrator labels (NO "NARRATOR:", "SPEAKER:")
- No timestamps (NO "(0:00-0:15)", NO "(pause)")
- No parentheses, brackets, or stage directions
- No markdown formatting (**, __, ##, etc.)
- No section headers or dividers
- No meta commentary

TITLE-LOCK ENFORCEMENT:
- Every sentence must relate to: "{title}"
- Do NOT drift to unrelated topics
- Stay focused on the title's core subject

PRODUCT INTEGRATION (Natural):
- Mention "{product}" naturally 1-2 times if relevant
- Example: "...and I track this using {product}, link in description..."
- NEVER mention price or cost

LENGTH REQUIREMENT:
- Target exactly {chunk.target_chars:,} characters (±5%)
- Do not pad with filler
- Do not rush content

════════════════════════════════════════════════════════════
NOW WRITE THE CHUNK
════════════════════════════════════════════════════════════

Write natural, engaging narration that sounds deeply human.
Start writing immediately - no preamble.
"""

        return prompt

    def _get_temperature(self, role: str) -> float:
        """Get temperature based on chunk role"""
        temps = {
            "HOOK_AND_FRAMEWORK": 0.90,      # High creativity for hook
            "DEEP_INSIGHTS_AND_EXAMPLES": 0.85,  # Balanced
            "IMPLEMENTATION_AND_CLOSE": 0.80     # More focused for conclusion
        }
        return temps.get(role, 0.85)

    def _merge_chunks(self, chunks: List[str]) -> str:
        """
        Merge chunks into one continuous block

        Remove any continuation markers or chunk artifacts
        """
        # Join with space
        merged = ' '.join(chunks)

        # Remove chunk continuation phrases
        merged = re.sub(r'(?i)(continuing from|as we discussed|as mentioned earlier)', '', merged)
        merged = re.sub(r'(?i)(in the previous (section|part|chunk))', '', merged)

        # Fix double spaces
        merged = re.sub(r'  +', ' ', merged)

        return merged.strip()

    def _clean_script(self, text: str) -> str:
        """
        Aggressive cleaning to remove ALL formatting artifacts
        """
        # Remove markdown
        text = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', text)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        text = re.sub(r'_(.+?)_', r'\1', text)
        text = re.sub(r'`(.+?)`', r'\1', text)
        text = re.sub(r'#{1,6}\s+', '', text)

        # Remove any remaining asterisks
        text = re.sub(r'\*', '', text)

        # Remove labels and visual cues
        text = re.sub(r'(?i)(VISUAL|VIDEO|NARRATOR|SPEAKER|SHOW|CUT TO)\s*:', '', text)

        # Remove timestamps
        text = re.sub(r'\(\s*\d+:\d+\s*-\s*\d+:\d+\s*\)', '', text)
        text = re.sub(r'\(\s*\d+\s*(sec|min|seconds?|minutes?)\s*\)', '', text)

        # Remove brackets and parentheses with directions
        text = re.sub(r'\[.+?\]', '', text)
        text = re.sub(r'\(.+?\)', '', text)

        # Fix spacing
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'  +', ' ', text)

        return text.strip()

    def _validate_script(self, script: str, title: str, target_length: int) -> Dict:
        """
        Basic validation

        Returns dict with 'valid' (bool) and 'errors' (list)
        """
        errors = []

        # Check length (±10% tolerance for 3-chunk)
        actual_length = len(script)
        min_length = int(target_length * 0.90)
        max_length = int(target_length * 1.10)

        if actual_length < min_length:
            errors.append(f"Too short: {actual_length} < {min_length}")
        elif actual_length > max_length:
            errors.append(f"Too long: {actual_length} > {max_length}")

        # Check for forbidden patterns
        forbidden = [
            (r'(?i)\bVISUAL\s*:', 'VISUAL: label found'),
            (r'(?i)\bNARRATOR\s*:', 'NARRATOR: label found'),
            (r'\(\s*\d+:\d+', 'Timestamp found'),
        ]

        for pattern, msg in forbidden:
            if re.search(pattern, script):
                errors.append(msg)

        # Check title lock (basic)
        title_words = [w.lower() for w in title.split() if len(w) > 3]
        if title_words:
            script_lower = script.lower()
            found = sum(1 for w in title_words if w in script_lower)
            if found < len(title_words) * 0.3:  # At least 30% of title words
                errors.append("Possible topic drift (title words missing)")

        return {
            'valid': len(errors) == 0,
            'errors': errors
        }

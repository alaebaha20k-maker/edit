#!/usr/bin/env python3
"""
Inworld AI TTS Voice Generator
- Chunks scripts into 2,000 character segments (Inworld limit)
- Generates audio sequentially with ranking
- Merges all chunks into final audio file
"""

import os
import re
import time
import base64
import requests
from typing import List, Dict, Tuple
from pathlib import Path
from pydub import AudioSegment
from config import Config


class VoiceGenerator:
    """Generate voice using Inworld AI TTS with chunking and merging"""

    # Inworld TTS endpoint
    TTS_ENDPOINT = "https://studio.inworld.ai/v1/text-to-speech/synthesize"

    # Max characters per TTS request (Inworld limit: 2000)
    MAX_CHUNK_SIZE = 1900  # Use 1900 for safety buffer

    def __init__(self, api_key: str = None, api_secret: str = None):
        """
        Initialize Inworld TTS

        Args:
            api_key: Inworld API Key (from portal)
            api_secret: Inworld API Secret (from portal)
        """
        self.api_key = api_key or Config.get_inworld_api_key()
        self.api_secret = api_secret or Config.get_inworld_api_secret()

        if not self.api_key or not self.api_secret:
            raise ValueError("Inworld API Key and Secret required. Configure in Settings.")

    def generate_voice(
        self,
        script: str,
        output_path: str,
        voice_id: str = "inworld-voice-1",
        model_id: str = "inworld-tts-1.5-max",
        verbose: bool = True
    ) -> Dict:
        """
        Generate voice from script with automatic chunking and merging

        Args:
            script: Full script text (any length)
            output_path: Where to save final merged audio
            voice_id: Inworld voice ID (from portal)
            model_id: TTS model (inworld-tts-1.5-max or inworld-tts-1.5-mini)
            verbose: Print progress

        Returns:
            Dict with audio_path, duration, chunks_count
        """
        start_time = time.time()

        if verbose:
            print(f"\n{'='*70}")
            print(f"🎙️ INWORLD AI VOICE GENERATION")
            print(f"{'='*70}")
            print(f"Script length: {len(script):,} characters")
            print(f"Voice: {voice_id}")
            print(f"Model: {model_id}")
            print(f"{'='*70}\n")

        # Step 1: Chunk script
        chunks = self._chunk_script(script, verbose=verbose)

        # Step 2: Generate audio for each chunk sequentially
        audio_files = []
        for i, chunk in enumerate(chunks):
            if verbose:
                print(f"\n🎤 Generating audio chunk {i+1}/{len(chunks)}...")
                print(f"   Text: {chunk[:80]}...")
                print(f"   Length: {len(chunk)} chars")

            audio_file = self._generate_single_chunk(
                text=chunk,
                voice_id=voice_id,
                model_id=model_id,
                chunk_index=i+1,
                verbose=verbose
            )

            audio_files.append(audio_file)

            if verbose:
                print(f"   ✅ Chunk {i+1} generated: {audio_file}")

            # Rate limiting: wait 1 second between chunks
            if i < len(chunks) - 1:
                time.sleep(1)

        # Step 3: Merge all audio chunks
        if verbose:
            print(f"\n🔗 Merging {len(audio_files)} audio chunks...")

        final_audio = self._merge_audio_chunks(audio_files, output_path, verbose=verbose)

        # Clean up temporary chunk files
        for audio_file in audio_files:
            try:
                os.remove(audio_file)
            except:
                pass

        generation_time = time.time() - start_time

        # Get duration
        audio = AudioSegment.from_file(output_path)
        duration_seconds = len(audio) / 1000.0

        if verbose:
            print(f"\n{'='*70}")
            print(f"✅ VOICE GENERATION COMPLETE")
            print(f"{'='*70}")
            print(f"File: {output_path}")
            print(f"Duration: {duration_seconds:.1f}s")
            print(f"Chunks: {len(chunks)}")
            print(f"Time: {generation_time:.1f}s")
            print(f"{'='*70}\n")

        return {
            'audio_path': output_path,
            'duration_seconds': duration_seconds,
            'chunks_count': len(chunks),
            'generation_time': generation_time
        }

    def _chunk_script(self, script: str, verbose: bool = True) -> List[str]:
        """
        Split script into chunks of max 1900 characters
        Splits on sentence boundaries for natural audio

        Args:
            script: Full script text
            verbose: Print chunking info

        Returns:
            List of text chunks
        """
        # Split into sentences (by . ! ?)
        sentences = re.split(r'(?<=[.!?])\s+', script)

        chunks = []
        current_chunk = ""

        for sentence in sentences:
            # If single sentence exceeds limit, split it forcefully
            if len(sentence) > self.MAX_CHUNK_SIZE:
                # Save current chunk if not empty
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""

                # Split long sentence into smaller parts
                words = sentence.split()
                for word in words:
                    if len(current_chunk) + len(word) + 1 <= self.MAX_CHUNK_SIZE:
                        current_chunk += word + " "
                    else:
                        chunks.append(current_chunk.strip())
                        current_chunk = word + " "

                continue

            # Try to add sentence to current chunk
            if len(current_chunk) + len(sentence) + 1 <= self.MAX_CHUNK_SIZE:
                current_chunk += sentence + " "
            else:
                # Current chunk is full, save it and start new one
                chunks.append(current_chunk.strip())
                current_chunk = sentence + " "

        # Add last chunk
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        if verbose:
            print(f"📦 Script chunked into {len(chunks)} parts:")
            for i, chunk in enumerate(chunks):
                print(f"   Chunk {i+1}: {len(chunk)} chars")
            print()

        return chunks

    def _generate_single_chunk(
        self,
        text: str,
        voice_id: str,
        model_id: str,
        chunk_index: int,
        verbose: bool = True
    ) -> str:
        """
        Generate audio for a single text chunk using Inworld API

        Args:
            text: Text to synthesize (max 2000 chars)
            voice_id: Inworld voice ID
            model_id: TTS model ID
            chunk_index: Chunk number (for temp filename)
            verbose: Print progress

        Returns:
            Path to generated audio file
        """
        # Prepare authentication (Basic Auth with API Key + Secret)
        auth_string = f"{self.api_key}:{self.api_secret}"
        auth_bytes = auth_string.encode('ascii')
        base64_auth = base64.b64encode(auth_bytes).decode('ascii')

        # Prepare request
        headers = {
            'Authorization': f'Basic {base64_auth}',
            'Content-Type': 'application/json'
        }

        payload = {
            'text': text,
            'voiceId': voice_id,
            'modelId': model_id,
            'audioConfig': {
                'format': 'mp3',
                'sampleRate': 22050
            }
        }

        # Call Inworld TTS API
        try:
            response = requests.post(
                self.TTS_ENDPOINT,
                headers=headers,
                json=payload,
                timeout=60
            )

            if response.status_code != 200:
                error_msg = f"Inworld API error: {response.status_code} - {response.text}"
                if verbose:
                    print(f"   ❌ {error_msg}")
                raise Exception(error_msg)

            # Save audio to temp file
            temp_dir = Config.TEMP_DIR if hasattr(Config, 'TEMP_DIR') else Path('backend/temp')
            temp_dir.mkdir(parents=True, exist_ok=True)

            temp_file = temp_dir / f"voice_chunk_{chunk_index}_{int(time.time())}.mp3"

            with open(temp_file, 'wb') as f:
                f.write(response.content)

            return str(temp_file)

        except requests.exceptions.Timeout:
            raise Exception("Inworld API timeout. Try again or use shorter text.")
        except requests.exceptions.RequestException as e:
            raise Exception(f"Network error calling Inworld API: {str(e)}")

    def _merge_audio_chunks(
        self,
        audio_files: List[str],
        output_path: str,
        verbose: bool = True
    ) -> str:
        """
        Merge multiple audio files into one

        Args:
            audio_files: List of audio file paths (in order)
            output_path: Where to save merged audio
            verbose: Print progress

        Returns:
            Path to merged audio file
        """
        if len(audio_files) == 1:
            # Only one chunk, just copy it
            audio = AudioSegment.from_file(audio_files[0])
            audio.export(output_path, format="mp3")
            return output_path

        # Load and concatenate all audio chunks
        combined = AudioSegment.empty()

        for i, audio_file in enumerate(audio_files):
            if verbose:
                print(f"   Merging chunk {i+1}/{len(audio_files)}...")

            chunk_audio = AudioSegment.from_file(audio_file)
            combined += chunk_audio

            # Optional: add small pause between chunks (100ms)
            if i < len(audio_files) - 1:
                silence = AudioSegment.silent(duration=100)
                combined += silence

        # Export merged audio
        combined.export(output_path, format="mp3")

        if verbose:
            print(f"   ✅ Merged {len(audio_files)} chunks into: {output_path}")

        return output_path


def generate_voice(
    script: str,
    output_path: str,
    voice_id: str = "inworld-voice-1",
    model_id: str = "inworld-tts-1.5-max",
    api_key: str = None,
    api_secret: str = None,
    verbose: bool = True
) -> Dict:
    """
    Convenience function to generate voice

    Args:
        script: Full script text
        output_path: Where to save audio
        voice_id: Inworld voice ID
        model_id: TTS model (inworld-tts-1.5-max or inworld-tts-1.5-mini)
        api_key: Inworld API Key (optional, loads from config)
        api_secret: Inworld API Secret (optional, loads from config)
        verbose: Print progress

    Returns:
        Dict with audio_path, duration, chunks_count
    """
    generator = VoiceGenerator(api_key=api_key, api_secret=api_secret)
    return generator.generate_voice(
        script=script,
        output_path=output_path,
        voice_id=voice_id,
        model_id=model_id,
        verbose=verbose
    )

"""
Whisper Speech-to-Text with Timestamps
Provides perfect timing for image synchronization with voice
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Optional
import whisper


class WhisperSTT:
    """Speech-to-Text with timestamps using OpenAI Whisper"""

    def __init__(self, model_size: str = "base"):
        """
        Initialize Whisper model

        Args:
            model_size: Model size (tiny, base, small, medium, large)
                       base = good balance of speed/accuracy
        """
        self.model_size = model_size
        self.model = None  # Lazy load

    def _load_model(self):
        """Load Whisper model (lazy loading)"""
        if self.model is None:
            print(f"📥 Loading Whisper model: {self.model_size}")
            self.model = whisper.load_model(self.model_size)
            print(f"✅ Whisper model loaded")

    def transcribe_with_timestamps(
        self,
        audio_path: str,
        language: str = None,
        verbose: bool = True
    ) -> Dict:
        """
        Transcribe audio and get segments with timestamps

        Args:
            audio_path: Path to audio file
            language: Language code (None = auto-detect)
            verbose: Print progress

        Returns:
            {
                'text': full transcript,
                'segments': [
                    {
                        'start': 0.0,
                        'end': 5.2,
                        'text': 'Hello world',
                        'words': [...] (if word_timestamps=True)
                    },
                    ...
                ],
                'language': detected language
            }
        """
        self._load_model()

        if verbose:
            print(f"\n🎤 WHISPER STT")
            print(f"   Audio: {Path(audio_path).name}")
            print(f"   Model: {self.model_size}")

        # Transcribe with word-level timestamps
        result = self.model.transcribe(
            audio_path,
            language=language,
            word_timestamps=True,
            verbose=False
        )

        if verbose:
            print(f"   ✅ Transcribed: {len(result['segments'])} segments")
            print(f"   Language: {result['language']}")

        return result

    def group_segments_by_duration(
        self,
        segments: List[Dict],
        target_duration: float = 8.0,
        min_duration: float = 4.0,
        max_duration: float = 15.0,
        verbose: bool = False
    ) -> List[Dict]:
        """
        Group segments into scenes with target duration

        Args:
            segments: Whisper segments with start/end/text
            target_duration: Target duration per scene (seconds)
            min_duration: Minimum scene duration
            max_duration: Maximum scene duration

        Returns:
            List of grouped scenes:
            [
                {
                    'scene_id': 1,
                    'start': 0.0,
                    'end': 8.5,
                    'text': 'Combined text from segments',
                    'duration': 8.5
                },
                ...
            ]
        """
        grouped_scenes = []
        current_scene = None
        scene_id = 1

        for segment in segments:
            if current_scene is None:
                # Start new scene
                current_scene = {
                    'scene_id': scene_id,
                    'start': segment['start'],
                    'end': segment['end'],
                    'text': segment['text'].strip(),
                    'segments': [segment]
                }
            else:
                # Check if we should add to current scene or start new one
                potential_duration = segment['end'] - current_scene['start']

                if potential_duration <= max_duration:
                    # Add to current scene
                    current_scene['end'] = segment['end']
                    current_scene['text'] += ' ' + segment['text'].strip()
                    current_scene['segments'].append(segment)

                    # If we've reached target duration, finalize scene
                    if potential_duration >= target_duration:
                        current_scene['duration'] = current_scene['end'] - current_scene['start']
                        grouped_scenes.append(current_scene)
                        scene_id += 1
                        current_scene = None
                else:
                    # Current scene is at max duration, finalize and start new
                    current_scene['duration'] = current_scene['end'] - current_scene['start']
                    grouped_scenes.append(current_scene)
                    scene_id += 1

                    # Start new scene with current segment
                    current_scene = {
                        'scene_id': scene_id,
                        'start': segment['start'],
                        'end': segment['end'],
                        'text': segment['text'].strip(),
                        'segments': [segment]
                    }

        # Add final scene if exists
        if current_scene is not None:
            current_scene['duration'] = current_scene['end'] - current_scene['start']
            # Only add if meets minimum duration
            if current_scene['duration'] >= min_duration:
                grouped_scenes.append(current_scene)
            elif grouped_scenes:
                # Merge with previous scene if too short
                prev_scene = grouped_scenes[-1]
                prev_scene['end'] = current_scene['end']
                prev_scene['text'] += ' ' + current_scene['text']
                prev_scene['duration'] = prev_scene['end'] - prev_scene['start']

        if verbose:
            print(f"   📦 Grouped into {len(grouped_scenes)} scenes")
            for scene in grouped_scenes[:3]:  # Show first 3
                print(f"      Scene {scene['scene_id']}: {scene['duration']:.1f}s - {scene['text'][:50]}...")

        return grouped_scenes

    def create_n_scenes(
        self,
        segments: List[Dict],
        n_images: int,
        total_duration: float,
        verbose: bool = False
    ) -> List[Dict]:
        """
        Create exactly N scenes from segments by grouping

        Args:
            segments: Whisper segments
            n_images: Desired number of images
            total_duration: Total audio duration
            verbose: Print progress

        Returns:
            List of N scenes with timestamps
        """
        if n_images <= 0 or not segments:
            return []

        # Calculate target duration per scene
        target_duration = total_duration / n_images

        if verbose:
            print(f"   🎯 Creating {n_images} scenes ({target_duration:.1f}s each)")

        scenes = []
        segments_per_scene = max(1, len(segments) // n_images)

        for i in range(n_images):
            # Calculate segment range for this scene
            start_idx = i * segments_per_scene
            end_idx = start_idx + segments_per_scene if i < n_images - 1 else len(segments)

            # Get segments for this scene
            scene_segments = segments[start_idx:end_idx]

            if scene_segments:
                scene = {
                    'scene_id': i + 1,
                    'start': scene_segments[0]['start'],
                    'end': scene_segments[-1]['end'],
                    'text': ' '.join(seg['text'].strip() for seg in scene_segments),
                    'duration': scene_segments[-1]['end'] - scene_segments[0]['start']
                }
                scenes.append(scene)

        if verbose:
            print(f"   ✅ Created {len(scenes)} scenes")

        return scenes


def get_stt_timestamps(
    audio_path: str,
    n_images: Optional[int] = None,
    target_duration: float = 8.0,
    model_size: str = "base",
    verbose: bool = True
) -> List[Dict]:
    """
    Quick helper to get STT timestamps

    Args:
        audio_path: Path to audio file
        n_images: If specified, create exactly N scenes. Otherwise use auto-grouping
        target_duration: Target duration per scene (if n_images not specified)
        model_size: Whisper model size
        verbose: Print progress

    Returns:
        List of scenes with timestamps
    """
    stt = WhisperSTT(model_size=model_size)

    # Transcribe
    result = stt.transcribe_with_timestamps(audio_path, verbose=verbose)

    # Get total duration
    total_duration = result['segments'][-1]['end'] if result['segments'] else 0

    # Create scenes
    if n_images is not None:
        # User specified exact count
        scenes = stt.create_n_scenes(
            result['segments'],
            n_images,
            total_duration,
            verbose=verbose
        )
    else:
        # Auto-group by duration
        scenes = stt.group_segments_by_duration(
            result['segments'],
            target_duration=target_duration,
            verbose=verbose
        )

    return scenes

#!/usr/bin/env python3
"""
Whisper AI caption generation module
Generates SRT subtitle files from audio using OpenAI Whisper
"""

import os
import sys


def generate_captions(audio_path, output_srt_path, model_size="base", language="en"):
    """
    Generate SRT captions from audio using Whisper AI

    Args:
        audio_path: Path to audio file
        output_srt_path: Path for output SRT file
        model_size: Whisper model size (tiny, base, small, medium, large)
                   For i5 8th gen, use 'base' (fast) or 'small' (better accuracy)
        language: Language code (default: en for English)

    Returns:
        str: Path to generated SRT file

    Raises:
        RuntimeError: If caption generation fails
        ImportError: If Whisper is not installed
    """

    try:
        import whisper
    except ImportError:
        raise ImportError(
            "Whisper is not installed. Install it with:\n"
            "  pip install openai-whisper\n"
            "Or for faster installation without PyTorch extras:\n"
            "  pip install openai-whisper --no-deps\n"
            "  pip install torch torchaudio numpy"
        )

    # Validate inputs
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    if model_size not in ['tiny', 'base', 'small', 'medium', 'large']:
        raise ValueError(
            f"Invalid model size '{model_size}'. "
            f"Choose from: tiny, base, small, medium, large"
        )

    print(f"\n🎙️  Loading Whisper model: {model_size}")
    print(f"   (This may take a moment on first run...)")

    try:
        model = whisper.load_model(model_size)
    except Exception as e:
        raise RuntimeError(f"Failed to load Whisper model: {str(e)}")

    print(f"✓ Model loaded successfully")
    print(f"\n🔊 Transcribing audio: {os.path.basename(audio_path)}")
    print(f"   (This may take several minutes depending on audio length...)")

    try:
        # Transcribe with word-level timestamps for better subtitle timing
        result = model.transcribe(
            audio_path,
            language=language,
            verbose=False,
            word_timestamps=False  # Set to True for more precise timing
        )
    except Exception as e:
        raise RuntimeError(f"Transcription failed: {str(e)}")

    print(f"✓ Transcription complete")
    print(f"\n📝 Generating SRT file...")

    # Generate SRT content
    try:
        srt_content = generate_srt_content(result)
    except Exception as e:
        raise RuntimeError(f"Failed to generate SRT content: {str(e)}")

    # Save SRT file
    try:
        with open(output_srt_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)
    except Exception as e:
        raise RuntimeError(f"Failed to write SRT file: {str(e)}")

    print(f"✓ Captions saved: {output_srt_path}")
    print(f"   Total segments: {len(result['segments'])}")

    return output_srt_path


def generate_srt_content(transcription):
    """
    Generate SRT content from Whisper transcription result

    Args:
        transcription: Whisper transcription result dict

    Returns:
        str: SRT formatted subtitle content
    """
    srt_content = ""

    for i, segment in enumerate(transcription['segments'], start=1):
        start_time = format_timestamp(segment['start'])
        end_time = format_timestamp(segment['end'])
        text = segment['text'].strip()

        # Skip empty segments
        if not text:
            continue

        # Format subtitle block
        srt_content += f"{i}\n"
        srt_content += f"{start_time} --> {end_time}\n"
        srt_content += f"{text}\n\n"

    return srt_content


def format_timestamp(seconds):
    """
    Convert seconds to SRT timestamp format (HH:MM:SS,mmm)

    Args:
        seconds: Time in seconds (float)

    Returns:
        str: Formatted timestamp
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)

    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def split_long_text(text, max_chars=80):
    """
    Split long text into multiple lines for better subtitle display

    Args:
        text: Input text
        max_chars: Maximum characters per line

    Returns:
        str: Text with line breaks
    """
    if len(text) <= max_chars:
        return text

    words = text.split()
    lines = []
    current_line = []
    current_length = 0

    for word in words:
        word_length = len(word) + 1  # +1 for space

        if current_length + word_length > max_chars and current_line:
            lines.append(' '.join(current_line))
            current_line = [word]
            current_length = word_length
        else:
            current_line.append(word)
            current_length += word_length

    if current_line:
        lines.append(' '.join(current_line))

    return '\n'.join(lines)


def test_whisper_installation():
    """Test if Whisper is properly installed"""
    try:
        import whisper
        print("✓ Whisper is installed")

        # Try to load a small model
        print("Testing model loading...")
        model = whisper.load_model("tiny")
        print("✓ Whisper is working correctly")

        return True

    except ImportError:
        print("✗ Whisper is NOT installed")
        print("\nInstall with:")
        print("  pip install openai-whisper")
        return False

    except Exception as e:
        print(f"✗ Whisper installation error: {str(e)}")
        return False


if __name__ == "__main__":
    # Test Whisper installation
    print("Whisper Caption Generator - Test Mode\n")

    if test_whisper_installation():
        print("\n" + "="*60)
        print("Whisper is ready to generate captions!")
        print("="*60)
        print("\nRecommended models for i5 8th gen:")
        print("  • 'base'  - Fast, good accuracy (RECOMMENDED)")
        print("  • 'small' - Slower, better accuracy")
        print("  • 'tiny'  - Fastest, lower accuracy")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("Please install Whisper to use caption generation")
        print("="*60)

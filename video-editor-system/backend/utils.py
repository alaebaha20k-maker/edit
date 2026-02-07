#!/usr/bin/env python3
"""
Utility functions for video editing system
"""

import os
import shutil
import json
from datetime import datetime


def ensure_directory_exists(directory):
    """
    Create directory if it doesn't exist

    Args:
        directory: Path to directory

    Returns:
        str: Absolute path to directory
    """
    os.makedirs(directory, exist_ok=True)
    return os.path.abspath(directory)


def clean_directory(directory, keep_directory=True):
    """
    Remove all files from directory

    Args:
        directory: Path to directory
        keep_directory: If True, keep the directory itself
    """
    if not os.path.exists(directory):
        return

    if keep_directory:
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f'Warning: Failed to delete {file_path}: {e}')
    else:
        try:
            shutil.rmtree(directory)
        except Exception as e:
            print(f'Warning: Failed to delete directory {directory}: {e}')


def get_file_size(file_path):
    """
    Get file size in human-readable format

    Args:
        file_path: Path to file

    Returns:
        str: File size (e.g., "1.5 MB")
    """
    if not os.path.exists(file_path):
        return "0 B"

    size_bytes = os.path.getsize(file_path)

    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0

    return f"{size_bytes:.2f} PB"


def format_time(seconds):
    """
    Format seconds to HH:MM:SS

    Args:
        seconds: Time in seconds

    Returns:
        str: Formatted time
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


def generate_project_id():
    """
    Generate unique project ID based on timestamp

    Returns:
        str: Project ID (e.g., "project_20240315_143052")
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"project_{timestamp}"


def save_project_metadata(project_id, metadata, output_dir="output"):
    """
    Save project metadata to JSON file

    Args:
        project_id: Unique project identifier
        metadata: Dict containing project information
        output_dir: Output directory

    Returns:
        str: Path to metadata file
    """
    ensure_directory_exists(output_dir)

    metadata_path = os.path.join(output_dir, f"{project_id}_metadata.json")

    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)

    return metadata_path


def load_project_metadata(metadata_path):
    """
    Load project metadata from JSON file

    Args:
        metadata_path: Path to metadata file

    Returns:
        dict: Project metadata
    """
    if not os.path.exists(metadata_path):
        raise FileNotFoundError(f"Metadata file not found: {metadata_path}")

    with open(metadata_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def validate_ranking(items):
    """
    Validate ranking sequence is correct

    Args:
        items: List of dicts with 'rank' key

    Returns:
        bool: True if ranking is valid

    Raises:
        ValueError: If ranking is invalid
    """
    if not items:
        raise ValueError("Items list is empty")

    ranks = [item.get('rank') for item in items]

    # Check all items have rank
    if None in ranks:
        raise ValueError("All items must have a 'rank' field")

    # Check ranks are positive integers
    for rank in ranks:
        if not isinstance(rank, int) or rank < 1:
            raise ValueError(f"Invalid rank value: {rank}. Ranks must be positive integers.")

    # Check for duplicates
    if len(ranks) != len(set(ranks)):
        raise ValueError("Duplicate ranks found. Each item must have a unique rank.")

    # Check sequence starts at 1
    sorted_ranks = sorted(ranks)
    if sorted_ranks[0] != 1:
        raise ValueError(f"Ranking must start at 1, got {sorted_ranks[0]}")

    # Check sequence is continuous
    for i, rank in enumerate(sorted_ranks, start=1):
        if rank != i:
            raise ValueError(
                f"Ranking sequence is not continuous. "
                f"Expected rank {i}, found {rank}"
            )

    return True


def sort_by_rank(items):
    """
    Sort items by rank field

    Args:
        items: List of dicts with 'rank' key

    Returns:
        list: Sorted items
    """
    validate_ranking(items)
    return sorted(items, key=lambda x: x['rank'])


def print_processing_step(step_number, total_steps, description):
    """
    Print formatted processing step

    Args:
        step_number: Current step number
        total_steps: Total number of steps
        description: Step description
    """
    print(f"\n{'='*60}")
    print(f"STEP {step_number}/{total_steps}: {description}")
    print(f"{'='*60}")


def print_success_message(message):
    """Print formatted success message"""
    print(f"\n{'='*60}")
    print(f"✅ {message}")
    print(f"{'='*60}\n")


def print_error_message(message):
    """Print formatted error message"""
    print(f"\n{'='*60}")
    print(f"❌ ERROR: {message}")
    print(f"{'='*60}\n")


def print_warning_message(message):
    """Print formatted warning message"""
    print(f"\n⚠️  WARNING: {message}\n")


def create_progress_callback(total_steps):
    """
    Create a progress tracking callback function

    Args:
        total_steps: Total number of steps

    Returns:
        function: Callback function
    """
    progress = {'current': 0}

    def callback(description):
        progress['current'] += 1
        percentage = (progress['current'] / total_steps) * 100
        print(f"\n[{progress['current']}/{total_steps}] ({percentage:.1f}%) {description}")

    return callback


def detect_language_from_text(text):
    """
    Detect language from text (title or script)

    Uses character patterns and common words to detect:
    - Spanish (es)
    - German (de)
    - French (fr)
    - English (en) - default

    Args:
        text: Text to analyze (title or script)

    Returns:
        str: Language code ('es', 'de', 'fr', 'en')
    """
    if not text or not isinstance(text, str):
        return 'en'

    text_lower = text.lower()

    # Spanish indicators
    spanish_patterns = [
        'ñ',  # Spanish-specific character
        'á', 'é', 'í', 'ó', 'ú',  # Spanish accents
        '¿', '¡',  # Spanish punctuation
    ]
    spanish_words = [
        'el', 'la', 'los', 'las', 'un', 'una', 'de', 'del', 'al',
        'por', 'para', 'con', 'sin', 'sobre', 'entre',
        'cómo', 'qué', 'cuál', 'cuándo', 'dónde', 'por qué',
        'mejor', 'peor', 'más', 'menos', 'muy', 'tan',
        'este', 'esta', 'estos', 'estas', 'ese', 'esa',
    ]

    # German indicators
    german_patterns = [
        'ä', 'ö', 'ü', 'ß',  # German-specific characters
    ]
    german_words = [
        'der', 'die', 'das', 'den', 'dem', 'des',
        'ein', 'eine', 'einen', 'einem', 'eines',
        'und', 'oder', 'aber', 'nicht', 'auch',
        'wie', 'was', 'wann', 'wo', 'warum',
        'für', 'mit', 'von', 'zu', 'nach', 'bei',
        'dieser', 'diese', 'dieses', 'jener', 'jene',
        'können', 'müssen', 'sollen', 'werden', 'sein',
    ]

    # French indicators
    french_patterns = [
        'à', 'â', 'ç', 'è', 'é', 'ê', 'ë', 'î', 'ï', 'ô', 'ù', 'û', 'ü', 'ÿ',
    ]
    french_words = [
        'le', 'la', 'les', 'un', 'une', 'des', 'du', 'de', 'au', 'aux',
        'et', 'ou', 'mais', 'donc', 'car', 'ne', 'pas',
        'comment', 'quoi', 'quel', 'quelle', 'quand', 'où', 'pourquoi',
        'pour', 'avec', 'sans', 'sur', 'sous', 'dans', 'par',
        'ce', 'cet', 'cette', 'ces',
        'être', 'avoir', 'faire', 'aller', 'pouvoir', 'vouloir',
    ]

    # Count matches
    scores = {
        'es': 0,
        'de': 0,
        'fr': 0,
        'en': 0
    }

    # Check Spanish
    for pattern in spanish_patterns:
        if pattern in text_lower:
            scores['es'] += 3
    for word in spanish_words:
        if f' {word} ' in f' {text_lower} ' or text_lower.startswith(f'{word} ') or text_lower.endswith(f' {word}'):
            scores['es'] += 1

    # Check German
    for pattern in german_patterns:
        if pattern in text_lower:
            scores['de'] += 3
    for word in german_words:
        if f' {word} ' in f' {text_lower} ' or text_lower.startswith(f'{word} ') or text_lower.endswith(f' {word}'):
            scores['de'] += 1

    # Check French
    for pattern in french_patterns:
        if pattern in text_lower:
            scores['fr'] += 3
    for word in french_words:
        if f' {word} ' in f' {text_lower} ' or text_lower.startswith(f'{word} ') or text_lower.endswith(f' {word}'):
            scores['fr'] += 1

    # English is default, but check for common English words
    english_words = [
        'the', 'of', 'to', 'and', 'a', 'in', 'is', 'it',
        'you', 'that', 'he', 'was', 'for', 'on', 'are', 'with',
        'how', 'what', 'when', 'where', 'why', 'who', 'which',
        'this', 'these', 'that', 'those',
    ]
    for word in english_words:
        if f' {word} ' in f' {text_lower} ' or text_lower.startswith(f'{word} ') or text_lower.endswith(f' {word}'):
            scores['en'] += 1

    # Find language with highest score
    max_score = max(scores.values())

    # If no language detected (all scores 0), return English as default
    if max_score == 0:
        return 'en'

    # Return language with highest score
    detected_lang = max(scores, key=scores.get)

    return detected_lang


def get_language_name(language_code):
    """
    Convert language code to full language name

    Args:
        language_code: Language code (es, de, fr, en)

    Returns:
        str: Full language name
    """
    language_names = {
        'es': 'Spanish',
        'de': 'German',
        'fr': 'French',
        'en': 'English',
        'pt': 'Portuguese',
        'it': 'Italian',
        'nl': 'Dutch',
        'ru': 'Russian',
        'zh': 'Chinese',
        'ja': 'Japanese',
        'ko': 'Korean',
        'ar': 'Arabic',
    }
    return language_names.get(language_code, 'English')


if __name__ == "__main__":
    # Test utility functions
    print("Utility Functions - Test Mode\n")

    # Test directory creation
    test_dir = "test_temp"
    ensure_directory_exists(test_dir)
    print(f"✓ Created directory: {test_dir}")

    # Test ranking validation
    test_items = [
        {'rank': 1, 'name': 'first'},
        {'rank': 2, 'name': 'second'},
        {'rank': 3, 'name': 'third'},
    ]

    try:
        validate_ranking(test_items)
        print("✓ Ranking validation works")
    except ValueError as e:
        print(f"✗ Ranking validation failed: {e}")

    # Test time formatting
    time_str = format_time(3725)  # 1:02:05
    print(f"✓ Time formatting: 3725 seconds = {time_str}")

    # Test file size formatting
    print(f"✓ File size formatting: 1500000 bytes = {get_file_size(__file__)}")

    # Clean up
    clean_directory(test_dir, keep_directory=False)
    print(f"✓ Cleaned up test directory")

    print("\n✅ All utility functions working!")

#!/usr/bin/env python3
"""
Test script for language detection from titles
"""

from utils import detect_language_from_text, get_language_name


def test_language_detection():
    """Test language detection with various titles"""

    test_cases = [
        # Spanish titles
        ("Cómo generar contenido de alta calidad para YouTube", "es", "Spanish"),
        ("Los mejores consejos para emprendedores digitales", "es", "Spanish"),
        ("¿Por qué fracasan el 95% de los traders?", "es", "Spanish"),

        # German titles
        ("Wie man erfolgreiche Videos erstellt", "de", "German"),
        ("Die besten Tipps für digitale Unternehmer", "de", "German"),
        ("Warum scheitern 95% der Händler?", "de", "German"),

        # French titles
        ("Comment créer du contenu de haute qualité pour YouTube", "fr", "French"),
        ("Les meilleurs conseils pour les entrepreneurs numériques", "fr", "French"),
        ("Pourquoi 95% des traders échouent-ils?", "fr", "French"),

        # English titles
        ("How to Create High-Quality Content for YouTube", "en", "English"),
        ("The Best Tips for Digital Entrepreneurs", "en", "English"),
        ("Why 95% of Traders Fail", "en", "English"),
    ]

    print("=" * 80)
    print("LANGUAGE DETECTION TEST")
    print("=" * 80)
    print()

    passed = 0
    failed = 0

    for title, expected_code, expected_name in test_cases:
        detected_code = detect_language_from_text(title)
        detected_name = get_language_name(detected_code)

        status = "✅ PASS" if detected_code == expected_code else "❌ FAIL"

        if detected_code == expected_code:
            passed += 1
        else:
            failed += 1

        print(f"{status}")
        print(f"  Title: {title}")
        print(f"  Expected: {expected_name} ({expected_code})")
        print(f"  Detected: {detected_name} ({detected_code})")
        print()

    print("=" * 80)
    print(f"RESULTS: {passed} passed, {failed} failed out of {len(test_cases)} tests")
    print("=" * 80)

    return failed == 0


if __name__ == "__main__":
    success = test_language_detection()
    exit(0 if success else 1)

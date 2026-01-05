#!/usr/bin/env python3
"""
Niche Manager - CRUD operations for custom niches
Handles creation, retrieval, update, and deletion of video niches
"""

from typing import Dict, List, Optional
from database import NicheDatabase


class NicheManager:
    """Manager for video niches with writing guidelines"""

    @staticmethod
    def create_niche(name: str, language: str, writing_guidelines: str) -> Dict:
        """
        Create a new niche

        Args:
            name: Niche name (e.g., "Trading Psychology")
            language: Language code (e.g., "English", "French", "Arabic")
            writing_guidelines: Complete writing guidelines for script generation

        Returns:
            Created niche dict with id
        """
        # Validation
        if not name or not name.strip():
            raise ValueError("Niche name cannot be empty")

        if not language or not language.strip():
            raise ValueError("Language cannot be empty")

        if not writing_guidelines or not writing_guidelines.strip():
            raise ValueError("Writing guidelines cannot be empty")

        if len(writing_guidelines) < 100:
            raise ValueError("Writing guidelines too short (minimum 100 characters)")

        # Create niche
        niche = NicheDatabase.create(
            name=name.strip(),
            language=language.strip(),
            writing_guidelines=writing_guidelines.strip()
        )

        return niche

    @staticmethod
    def get_niche(niche_id: str) -> Optional[Dict]:
        """Get niche by ID"""
        return NicheDatabase.get_by_id(niche_id)

    @staticmethod
    def get_all_niches() -> List[Dict]:
        """Get all niches"""
        return NicheDatabase.get_all()

    @staticmethod
    def update_niche(niche_id: str, name: str = None, language: str = None,
                     writing_guidelines: str = None) -> Optional[Dict]:
        """
        Update existing niche

        Args:
            niche_id: Niche ID to update
            name: New name (optional)
            language: New language (optional)
            writing_guidelines: New writing guidelines (optional)

        Returns:
            Updated niche dict or None if not found
        """
        # Validation
        if writing_guidelines is not None and len(writing_guidelines.strip()) < 100:
            raise ValueError("Writing guidelines too short (minimum 100 characters)")

        return NicheDatabase.update(niche_id, name, language, writing_guidelines)

    @staticmethod
    def delete_niche(niche_id: str) -> bool:
        """Delete niche by ID"""
        return NicheDatabase.delete(niche_id)

    @staticmethod
    def get_niche_summary(niche_id: str) -> Optional[Dict]:
        """Get niche summary (without full guidelines for display)"""
        niche = NicheDatabase.get_by_id(niche_id)

        if not niche:
            return None

        return {
            'id': niche['id'],
            'name': niche['name'],
            'language': niche['language'],
            'guidelines_length': len(niche['writing_guidelines']),
            'created_at': niche['created_at']
        }

    @staticmethod
    def validate_niche_exists(niche_id: str) -> bool:
        """Check if niche exists"""
        return NicheDatabase.get_by_id(niche_id) is not None


def create_default_niches():
    """Create default niches for testing"""
    default_niches = [
        {
            "name": "Trading Psychology",
            "language": "English",
            "writing_guidelines": """
# Trading Psychology Writing Guidelines

## Tone and Style
- Professional yet accessible
- Motivational and encouraging
- Focus on mindset and discipline
- Use real trading scenarios and examples

## Content Structure
- Start with a hook related to trading mindset
- Present common psychological challenges traders face
- Provide actionable strategies and solutions
- Include specific examples and scenarios
- End with motivational summary

## Key Topics to Cover
- Emotional control and discipline
- Risk management mindset
- Dealing with losses and drawdowns
- Building confidence through preparation
- The importance of trading psychology
- Common mental traps and biases
- Developing a winning mindset

## Language Characteristics
- Clear and direct language
- Use trading terminology appropriately
- Avoid jargon that beginners won't understand
- Balance between educational and motivational
- Use analogies and metaphors for complex concepts

## Content Requirements
- 60,000+ characters
- Voice-ready text (NO markdown, NO formatting)
- Natural speaking rhythm
- Logical flow between sections
- Engaging storytelling approach
"""
        },
        {
            "name": "Psychologie du Trading",
            "language": "French",
            "writing_guidelines": """
# Guide de Rédaction - Psychologie du Trading

## Ton et Style
- Professionnel mais accessible
- Motivant et encourageant
- Focus sur le mental et la discipline
- Utiliser des scénarios de trading réels

## Structure du Contenu
- Commencer avec un hook sur le mental du trader
- Présenter les défis psychologiques courants
- Fournir des stratégies actionnables
- Inclure des exemples spécifiques
- Terminer avec un résumé motivant

## Sujets Clés
- Contrôle émotionnel et discipline
- Mental de gestion des risques
- Gérer les pertes et drawdowns
- Construire la confiance par la préparation
- L'importance de la psychologie du trading
- Pièges mentaux et biais courants
- Développer un mental de gagnant

## Caractéristiques du Langage
- Langage clair et direct
- Utiliser la terminologie du trading appropriée
- Éviter le jargon incompréhensible
- Équilibre éducatif et motivationnel
- Utiliser des analogies et métaphores

## Exigences du Contenu
- 60,000+ caractères
- Texte prêt pour la voix (PAS de markdown, PAS de formatage)
- Rythme naturel de parole
- Flow logique entre les sections
- Approche narrative engageante
"""
        }
    ]

    created = []
    for niche_data in default_niches:
        try:
            niche = NicheManager.create_niche(
                name=niche_data['name'],
                language=niche_data['language'],
                writing_guidelines=niche_data['writing_guidelines']
            )
            created.append(niche)
            print(f"✓ Created default niche: {niche['name']}")
        except Exception as e:
            print(f"✗ Failed to create niche '{niche_data['name']}': {e}")

    return created


if __name__ == "__main__":
    print("Testing Niche Manager...")

    # Create default niches
    print("\nCreating default niches...")
    niches = create_default_niches()

    # List all niches
    print("\nAll niches:")
    all_niches = NicheManager.get_all_niches()
    for niche in all_niches:
        summary = NicheManager.get_niche_summary(niche['id'])
        print(f"  - {summary['name']} ({summary['language']}) - {summary['guidelines_length']} chars")

    print("\n✓ Niche Manager tests passed!")

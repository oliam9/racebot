"""
Tests for normalizer.
"""

import pytest
from models.schema import Session
from models.enums import SessionType, SessionStatus
from normalizer.engine import SessionTypeClassifier, NameNormalizer


def test_session_type_classifier_practice():
    """Test classification of practice sessions."""
    classifier = SessionTypeClassifier()
    
    assert classifier.classify("Practice 1") == SessionType.PRACTICE
    assert classifier.classify("Free Practice 2") == SessionType.PRACTICE
    assert classifier.classify("FP1") == SessionType.PRACTICE
    assert classifier.classify("Training") == SessionType.PRACTICE


def test_session_type_classifier_qualifying():
    """Test classification of qualifying sessions."""
    classifier = SessionTypeClassifier()
    
    assert classifier.classify("Qualifying") == SessionType.QUALIFYING
    assert classifier.classify("Qualif") == SessionType.QUALIFYING
    assert classifier.classify("Q1") == SessionType.QUALIFYING
    assert classifier.classify("Super Pole") == SessionType.QUALIFYING


def test_session_type_classifier_race():
    """Test classification of race sessions."""
    classifier = SessionTypeClassifier()
    
    assert classifier.classify("Race") == SessionType.RACE
    assert classifier.classify("Grand Prix") == SessionType.RACE
    assert classifier.classify("Indianapolis 500") == SessionType.RACE
    assert classifier.classify("Feature Race") == SessionType.FEATURE


def test_session_type_classifier_sprint():
    """Test classification of sprint races."""
    classifier = SessionTypeClassifier()
    
    assert classifier.classify("Sprint") == SessionType.SPRINT
    assert classifier.classify("Sprint Race") == SessionType.SPRINT


def test_session_type_classifier_numbered_races():
    """Test classification of numbered races."""
    classifier = SessionTypeClassifier()
    
    assert classifier.classify("Race 1") == SessionType.RACE_1
    assert classifier.classify("Race 2") == SessionType.RACE_2


def test_session_type_classifier_other():
    """Test classification of unknown sessions."""
    classifier = SessionTypeClassifier()
    
    assert classifier.classify("Unknown Session") == SessionType.OTHER
    assert classifier.classify("Random Name") == SessionType.OTHER


def test_name_normalizer_basic():
    """Test basic name normalization."""
    normalizer = NameNormalizer()
    
    # Remove extra whitespace
    assert normalizer.normalize_name("  Test  Name  ") == "Test Name"
    
    # Title case
    assert normalizer.normalize_name("test name") == "Test Name"
    assert normalizer.normalize_name("TEST NAME") == "Test Name"


def test_name_normalizer_preserve_acronyms():
    """Test that short all-caps words are preserved."""
    normalizer = NameNormalizer()
    
    # Preserve GP, F1, etc.
    result = normalizer.normalize_name("GP of monaco")
    assert "GP" in result  # GP should stay uppercase
    
    result = normalizer.normalize_name("f1 grand prix")
    assert "F1" in result or "f1" in result  # Handle appropriately


def test_venue_name_normalization():
    """Test venue name normalization."""
    normalizer = NameNormalizer()
    
    # Basic normalization
    assert normalizer.normalize_venue_name("  Indianapolis Motor Speedway  ") == "Indianapolis Motor Speedway"
    
    # Common substitutions
    result = normalizer.normalize_venue_name("Indianapolis Intl Speedway")
    assert "International" in result


def test_session_type_classifier_case_insensitive():
    """Test that classifier is case-insensitive."""
    classifier = SessionTypeClassifier()
    
    assert classifier.classify("PRACTICE") == SessionType.PRACTICE
    assert classifier.classify("practice") == SessionType.PRACTICE
    assert classifier.classify("Practice") == SessionType.PRACTICE
    assert classifier.classify("PrAcTiCe") == SessionType.PRACTICE

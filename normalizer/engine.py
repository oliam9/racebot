"""
Data normalization engine for motorsport data.
"""

import re
from typing import List, Dict, Optional
from models.schema import Event, Session
from models.enums import SessionType, SessionStatus


class SessionTypeClassifier:
    """Classifies session names to canonical SessionType."""
    
    # Mapping patterns (regex) to SessionType
    # Order matters! More specific patterns must come before general ones
    PATTERNS = [
        # Practice sessions
        (r"practice|fp\d|free\s*practice|training", SessionType.PRACTICE),
        
        # Qualifying sessions
        (r"qualifying|qualif|qual|q\d|super\s*pole", SessionType.QUALIFYING),
        
        # Warmup
        (r"warm\s*up|warmup", SessionType.WARMUP),
        
        # Testing
        (r"test|testing|shakedown", SessionType.TEST),
        
        # Rally stages
        (r"stage\s*\d+|rally\s*stage|ss\d+|special\s*stage", SessionType.RALLY_STAGE),
        
        # Numbered races (must come before general "race" pattern)
        (r"race\s*1", SessionType.RACE_1),
        (r"race\s*2", SessionType.RACE_2),
        
        # Sprint races (must come before general race pattern)
        (r"sprint", SessionType.SPRINT),
        
        # Feature race (must come before general race pattern)
        (r"feature", SessionType.FEATURE),
        
        # Heat
        (r"heat", SessionType.HEAT),
        
        # Specific race names  (must come before general race pattern)
        (r"indianapolis\s*500|indy\s*500", SessionType.RACE),
        
        # General race sessions (comes last among race patterns)
        (r"\brace\b|grand\s*prix|gp\s*race|main\s*race", SessionType.RACE),
    ]
    
    @classmethod
    def classify(cls, session_name: str) -> SessionType:
        """
        Classify session name to SessionType.
        
        Args:
            session_name: Original session name from source
            
        Returns:
            Classified SessionType (defaults to OTHER if no match)
        """
        normalized = session_name.lower().strip()
        
        for pattern, session_type in cls.PATTERNS:
            if re.search(pattern, normalized):
                return session_type
        
        return SessionType.OTHER


class NameNormalizer:
    """Normalizes names and text fields."""
    
    @staticmethod
    def normalize_name(name: str) -> str:
        """
        Normalize a name field.
        
        - Trim whitespace
        - Standardize capitalization
        - Remove redundant spaces
        
        Args:
            name: Original name
            
        Returns:
            Normalized name
        """
        if not name:
            return name
        
        # Trim and remove redundant spaces
        normalized = ' '.join(name.split())
        
        # Title case (but preserve some all-caps like GP, F1, etc.)
        # Simple heuristic: if <=3 chars and all caps, keep it
        words = normalized.split()
        result = []
        for word in words:
            if len(word) <= 3 and word.isupper():
                result.append(word)
            else:
                result.append(word.title())
        
        return ' '.join(result)
    
    @staticmethod
    def normalize_venue_name(venue_name: Optional[str]) -> Optional[str]:
        """
        Normalize venue/circuit name.
        
        Args:
            venue_name: Original venue name
            
        Returns:
            Normalized venue name
        """
        if not venue_name:
            return venue_name
        
        normalized = ' '.join(venue_name.split())
        
        # Common substitutions
        replacements = {
            "Intl": "International",
            "Speedway": "Speedway",  # Keep as-is
            "Circuit": "Circuit",
        }
        
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        
        return normalized


class DataNormalizer:
    """Main normalization engine."""
    
    def __init__(self):
        self.type_classifier = SessionTypeClassifier()
        self.name_normalizer = NameNormalizer()
    
    def normalize_event(self, event: Event, apply_suggestions: bool = False) -> Event:
        """
        Normalize an event.
        
        Args:
            event: Event to normalize
            apply_suggestions: If True, apply normalization suggestions
            
        Returns:
            Normalized event
        """
        if not apply_suggestions:
            return event
        
        # Normalize event name
        event.name = self.name_normalizer.normalize_name(event.name)
        
        # Normalize venue
        if event.venue.circuit:
            event.venue.circuit = self.name_normalizer.normalize_venue_name(event.venue.circuit)
        if event.venue.city:
            event.venue.city = self.name_normalizer.normalize_name(event.venue.city)
        
        # Normalize sessions
        for session in event.sessions:
            session.name = self.name_normalizer.normalize_name(session.name)
            
            # Auto-classify session type if currently OTHER
            if session.type == SessionType.OTHER:
                classified_type = self.type_classifier.classify(session.name)
                session.type = classified_type
        
        return event
    
    def suggest_normalization(self, event: Event) -> Dict[str, List[str]]:
        """
        Suggest normalizations without applying them.
        
        Args:
            event: Event to analyze
            
        Returns:
            Dictionary of suggestions by field
        """
        suggestions: Dict[str, List[str]] = {}
        
        # Check event name
        normalized_name = self.name_normalizer.normalize_name(event.name)
        if normalized_name != event.name:
            suggestions["event_name"] = [
                f"Event name: '{event.name}' → '{normalized_name}'"
            ]
        
        # Check sessions
        session_suggestions = []
        for session in event.sessions:
            normalized_session_name = self.name_normalizer.normalize_name(session.name)
            if normalized_session_name != session.name:
                session_suggestions.append(
                    f"Session '{session.name}' → '{normalized_session_name}'"
                )
            
            # Check type classification
            if session.type == SessionType.OTHER:
                classified = self.type_classifier.classify(session.name)
                if classified != SessionType.OTHER:
                    session_suggestions.append(
                        f"Session '{session.name}' type: OTHER → {classified.value}"
                    )
        
        if session_suggestions:
            suggestions["sessions"] = session_suggestions
        
        return suggestions
    
    def merge_duplicate_sessions(
        self,
        sessions: List[Session],
        duplicate_indices: List[tuple]
    ) -> List[Session]:
        """
        Merge duplicate sessions (keep first occurrence).
        
        Args:
            sessions: List of sessions
            duplicate_indices: List of (idx1, idx2) tuples marking duplicates
            
        Returns:
            De-duplicated session list
        """
        to_remove = set()
        for (idx1, idx2) in duplicate_indices:
            to_remove.add(idx2)
        
        return [s for i, s in enumerate(sessions) if i not in to_remove]

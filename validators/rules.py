"""
Validation rules for motorsport data.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from models.schema import Event, Session, Series
from models.enums import SessionStatus
from .timezone_utils import (
    validate_iana_timezone,
    parse_iso_datetime,
    sessions_overlap,
    check_dst_transition,
)


@dataclass
class ValidationIssue:
    """A single validation issue."""
    severity: str  # "error" or "warning"
    message: str
    event_id: Optional[str] = None
    session_id: Optional[str] = None
    field: Optional[str] = None
    suggested_fix: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of validation."""
    errors: List[ValidationIssue]
    warnings: List[ValidationIssue]
    
    @property
    def is_valid(self) -> bool:
        """Check if validation passed (no errors, warnings allowed)."""
        return len(self.errors) == 0
    
    @property
    def total_issues(self) -> int:
        """Total number of issues."""
        return len(self.errors) + len(self.warnings)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/display."""
        return {
            "is_valid": self.is_valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": [
                {
                    "message": e.message,
                    "event_id": e.event_id,
                    "session_id": e.session_id,
                    "field": e.field,
                    "suggested_fix": e.suggested_fix,
                }
                for e in self.errors
            ],
            "warnings": [
                {
                    "message": w.message,
                    "event_id": w.event_id,
                    "session_id": w.session_id,
                    "field": w.field,
                    "suggested_fix": w.suggested_fix,
                }
                for w in self.warnings
            ],
        }


class DataValidator:
    """Validator for motorsport data."""
    
    def validate_series(self, series: Series) -> ValidationResult:
        """
        Validate a complete series.
        
        Args:
            series: Series to validate
            
        Returns:
            ValidationResult with all errors and warnings
        """
        errors: List[ValidationIssue] = []
        warnings: List[ValidationIssue] = []
        
        # Validate each event
        for event in series.events:
            event_result = self.validate_event(event)
            errors.extend(event_result.errors)
            warnings.extend(event_result.warnings)
        
        # Check for duplicate events
        event_ids = [e.event_id for e in series.events]
        duplicates = [eid for eid in event_ids if event_ids.count(eid) > 1]
        if duplicates:
            errors.append(ValidationIssue(
                severity="error",
                message=f"Duplicate event IDs found: {', '.join(set(duplicates))}",
                field="event_id"
            ))
        
        return ValidationResult(errors=errors, warnings=warnings)
    
    def validate_event(self, event: Event) -> ValidationResult:
        """
        Validate a single event.
        
        Args:
            event: Event to validate
            
        Returns:
            ValidationResult with all errors and warnings
        """
        errors: List[ValidationIssue] = []
        warnings: List[ValidationIssue] = []
        
        # Validate venue timezone
        if not validate_iana_timezone(event.venue.timezone):
            errors.append(ValidationIssue(
                severity="error",
                message=f"Invalid IANA timezone: {event.venue.timezone}",
                event_id=event.event_id,
                field="venue.timezone"
            ))
        
        # Warn if timezone was inferred
        if event.venue.inferred_timezone:
            warnings.append(ValidationIssue(
                severity="warning",
                message=f"Timezone was inferred from location data",
                event_id=event.event_id,
                field="venue.timezone"
            ))
        
        # Validate each session
        for session in event.sessions:
            session_result = self.validate_session(session, event.event_id)
            errors.extend(session_result.errors)
            warnings.extend(session_result.warnings)
        
        # Check for duplicate sessions
        session_ids = [s.session_id for s in event.sessions]
        duplicates = [sid for sid in session_ids if session_ids.count(sid) > 1]
        if duplicates:
            errors.append(ValidationIssue(
                severity="error",
                message=f"Duplicate session IDs found: {', '.join(set(duplicates))}",
                event_id=event.event_id,
                field="session_id"
            ))
        
        # Check for overlapping sessions (warning, not error)
        overlaps = self._find_overlapping_sessions(event.sessions)
        for (idx1, idx2) in overlaps:
            warnings.append(ValidationIssue(
                severity="warning",
                message=(
                    f"Sessions '{event.sessions[idx1].name}' and "
                    f"'{event.sessions[idx2].name}' overlap in time"
                ),
                event_id=event.event_id,
                session_id=event.sessions[idx1].session_id
            ))
        
        # Check for near-duplicate sessions (same type + similar time)
        near_dupes = self._find_near_duplicate_sessions(event.sessions)
        for (idx1, idx2) in near_dupes:
            warnings.append(ValidationIssue(
                severity="warning",
                message=(
                    f"Possible duplicate sessions: '{event.sessions[idx1].name}' and "
                    f"'{event.sessions[idx2].name}' have same type and similar start times"
                ),
                event_id=event.event_id,
                session_id=event.sessions[idx1].session_id
            ))
        
        return ValidationResult(errors=errors, warnings=warnings)
    
    def validate_session(self, session: Session, event_id: str) -> ValidationResult:
        """
        Validate a single session.
        
        Args:
            session: Session to validate
            event_id: Parent event ID
            
        Returns:
            ValidationResult with all errors and warnings
        """
        errors: List[ValidationIssue] = []
        warnings: List[ValidationIssue] = []
        
        # Session must have type
        if not session.type:
            errors.append(ValidationIssue(
                severity="error",
                message="Session missing type",
                event_id=event_id,
                session_id=session.session_id,
                field="type"
            ))
        
        # Session must have name
        if not session.name or not session.name.strip():
            errors.append(ValidationIssue(
                severity="error",
                message="Session missing name",
                event_id=event_id,
                session_id=session.session_id,
                field="name"
            ))
        
        # If status is TBD, start/end can be null
        if session.status == SessionStatus.TBD:
            if not session.start or not session.end:
                warnings.append(ValidationIssue(
                    severity="warning",
                    message=f"Session '{session.name}' has TBD status with incomplete times",
                    event_id=event_id,
                    session_id=session.session_id,
                    field="start"
                ))
        else:
            # Otherwise, start must be present and valid
            if not session.start:
                errors.append(ValidationIssue(
                    severity="error",
                    message=f"Session '{session.name}' missing start time",
                    event_id=event_id,
                    session_id=session.session_id,
                    field="start"
                ))
            else:
                # Validate start is proper ISO-8601
                dt_start = parse_iso_datetime(session.start)
                if not dt_start:
                    errors.append(ValidationIssue(
                        severity="error",
                        message=f"Session '{session.name}' has invalid start time format",
                        event_id=event_id,
                        session_id=session.session_id,
                        field="start"
                    ))
            
            # Validate end if present
            if session.end:
                dt_end = parse_iso_datetime(session.end)
                if not dt_end:
                    errors.append(ValidationIssue(
                        severity="error",
                        message=f"Session '{session.name}' has invalid end time format",
                        event_id=event_id,
                        session_id=session.session_id,
                        field="end"
                    ))
                elif session.start:
                    dt_start = parse_iso_datetime(session.start)
                    if dt_start and dt_end <= dt_start:
                        errors.append(ValidationIssue(
                            severity="error",
                            message=f"Session '{session.name}' end time must be after start time",
                            event_id=event_id,
                            session_id=session.session_id,
                            field="end"
                        ))
        
        return ValidationResult(errors=errors, warnings=warnings)
    
    def _find_overlapping_sessions(self, sessions: List[Session]) -> List[Tuple[int, int]]:
        """
        Find pairs of overlapping sessions.
        
        Returns:
            List of (index1, index2) tuples for overlapping sessions
        """
        overlaps = []
        for i in range(len(sessions)):
            for j in range(i + 1, len(sessions)):
                s1, s2 = sessions[i], sessions[j]
                if s1.start and s1.end and s2.start and s2.end:
                    if sessions_overlap(s1.start, s1.end, s2.start, s2.end):
                        overlaps.append((i, j))
        return overlaps
    
    def _find_near_duplicate_sessions(
        self,
        sessions: List[Session],
        time_threshold_minutes: int = 30
    ) -> List[Tuple[int, int]]:
        """
        Find near-duplicate sessions (same type, similar start time).
        
        Args:
            sessions: List of sessions
            time_threshold_minutes: Max minutes apart to consider "near duplicate"
            
        Returns:
            List of (index1, index2) tuples for near-duplicate sessions
        """
        near_dupes = []
        for i in range(len(sessions)):
            for j in range(i + 1, len(sessions)):
                s1, s2 = sessions[i], sessions[j]
                
                # Same type?
                if s1.type != s2.type:
                    continue
                
                # Similar start time?
                if s1.start and s2.start:
                    dt1 = parse_iso_datetime(s1.start)
                    dt2 = parse_iso_datetime(s2.start)
                    if dt1 and dt2:
                        diff_minutes = abs((dt1 - dt2).total_seconds() / 60)
                        if diff_minutes <= time_threshold_minutes:
                            near_dupes.append((i, j))
        
        return near_dupes

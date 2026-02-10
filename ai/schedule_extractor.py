"""
AI-powered schedule data extraction using Google Gemini API.
"""

import json
import os
from typing import Dict, Any, Optional
from datetime import datetime


class ScheduleExtractor:
    """Extract structured schedule data from unstructured text using Gemini AI."""
    
    def __init__(self):
        """Initialize with Gemini API configuration."""
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable not set. "
                "Please add it to your .env file."
            )
        
        try:
            import google.generativeai as genai
            self.genai = genai
            self.genai.configure(api_key=self.api_key)
            # Use Gemini 1.5 Flash for speed and cost efficiency
            self.model = self.genai.GenerativeModel('gemini-1.5-flash')
        except ImportError:
            raise ImportError(
                "google-generativeai not installed. "
                "Run: pip install google-generativeai"
            )
    
    def extract_schedule(self, document_text: str, filename: str) -> Dict[str, Any]:
        """
        Extract motorsport schedule data from document text.
        
        Args:
            document_text: Extracted text from document
            filename: Original filename for context
            
        Returns:
            Dictionary with extracted schedule data in our schema format
            
        Raises:
            ValueError: If extraction fails or data is invalid
        """
        if len(document_text) > 100000:  # ~100KB of text
            raise ValueError(
                "Document is too large. Please upload a smaller file "
                "(max 5MB or ~100,000 characters of text)."
            )
        
        prompt = self._build_extraction_prompt(document_text, filename)
        
        try:
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,  # Low temperature for consistent extraction
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 8192,
                }
            )
            
            # Extract JSON from response
            response_text = response.text.strip()
            
            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                lines = response_text.split('\n')
                # Remove first and last lines (``` markers)
                response_text = '\n'.join(lines[1:-1])
                if response_text.startswith('json'):
                    response_text = '\n'.join(lines[2:-1])
            
            # Parse JSON
            data = json.loads(response_text)
            
            # Validate required fields
            if not isinstance(data, dict):
                raise ValueError("Extracted data is not a valid object")
            
            if "series" not in data:
                raise ValueError("Could not identify series information")
            
            return data
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse extracted data as JSON: {str(e)}")
        except Exception as e:
            raise ValueError(f"AI extraction failed: {str(e)}")
    
    def _build_extraction_prompt(self, text: str, filename: str) -> str:
        """Build the extraction prompt for Gemini."""
        return f"""You are an expert at extracting motorsport schedule data from documents.

I have a document about a motorsport championship schedule. Please extract ALL the schedule information and return it as a structured JSON object.

**Document filename:** {filename}

**Document content:**
{text}

**Instructions:**
1. Identify the motorsport series/championship name
2. Identify the season year
3. Extract ALL events/races with:
   - Event name
   - Start and end dates (in YYYY-MM-DD format)
   - Venue information (circuit name, city, region, country)
   - Session details if available (practice, qualifying, race times)
4. If timezone information is available, include it
5. If you cannot find certain information, use null

**Return ONLY valid JSON** in this exact format:

{{
  "series": {{
    "series_id": "auto-generated-from-name",
    "name": "Series Name",
    "season": 2026,
    "category": "OPENWHEEL or GT or ENDURANCE or RALLY or TOURING or OTHER"
  }},
  "events": [
    {{
      "name": "Event Name",
      "start_date": "2026-03-15",
      "end_date": "2026-03-17",
      "venue": {{
        "circuit": "Circuit Name",
        "city": "City",
        "region": "Region/State",
        "country": "Country",
        "timezone": "America/New_York"
      }},
      "sessions": [
        {{
          "name": "Practice 1",
          "type": "PRACTICE",
          "start": "2026-03-15T10:00:00-04:00",
          "status": "SCHEDULED"
        }},
        {{
          "name": "Qualifying",
          "type": "QUALIFYING",
          "start": "2026-03-16T14:00:00-04:00",
          "status": "SCHEDULED"
        }},
        {{
          "name": "Race",
          "type": "RACE",
          "start": "2026-03-17T15:00:00-04:00",
          "status": "SCHEDULED"
        }}
      ]
    }}
  ]
}}

**Important:**
- Session types must be: PRACTICE, QUALIFYING, RACE, SPRINT, WARMUP, TEST, or OTHER
- Session status must be: SCHEDULED, TBD, UPDATED, or CANCELLED
- If session times are not available, omit the "sessions" array or use empty array
- Generate series_id from series name (lowercase, underscores)
- Infer category from series name if not explicit

Extract ALL events from the document. Return ONLY the JSON, no explanations."""
    
    def validate_extracted_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and enrich extracted data.
        
        Args:
            data: Extracted data dictionary
            
        Returns:
            Validated and enriched data
        """
        # Use existing validators
        from models.schema import Series
        from validators import DataValidator
        
        try:
            # Convert to Series object
            series_data = {
                **data["series"],
                "events": data.get("events", [])
            }
            
            series = Series.from_dict(series_data)
            
            # Validate
            validator = DataValidator()
            validation_result = validator.validate_series(series)
            
            # Return both series and validation
            return {
                "series": series,
                "validation": validation_result,
                "raw_data": data
            }
            
        except Exception as e:
            raise ValueError(f"Validation failed: {str(e)}")

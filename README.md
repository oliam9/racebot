# 🏁 Motorsport Data Collector

A Python-based system for collecting, normalizing, editing, and exporting motorsport competition data with full provenance tracking and validation.

## Features

- ✅ **Multi-series support** - Modular connector architecture (IndyCar included, easy to add F1, WEC, IMSA, etc.)
- 🌍 **Timezone handling** - Proper IANA timezone management with DST support
- ✏️ **Web-based editing** - Clean Streamlit UI optimized for iOS Safari
- 🔍 **Comprehensive validation** - Detects missing data, overlaps, duplicates, and timezone issues
- 📦 **JSON export** - Strict schema with provenance metadata and SHA-256 hash
- 🔄 **Resume editing** - Upload previous exports to continue work
- 📱 **iOS Safari optimized** - Large touch targets, responsive layout

## Project Structure

```
racebot/
├── app.py                    # Streamlit entry point
├── requirements.txt          # Dependencies
├── models/                   # Pydantic data models
│   ├── schema.py            # Series, Event, Session, Venue
│   └── enums.py             # SessionType, Status, Category
├── connectors/               # Data source connectors
│   ├── base.py              # Abstract base class
│   ├── registry.py          # Connector registry
│   └── indycar.py           # IndyCar connector (ICS feed)
├── validators/               # Validation engine
│   ├── rules.py             # Validation rules
│   └── timezone_utils.py    # Timezone utilities
├── normalizer/               # Data normalization
│   └── engine.py            # Normalization logic
├── ui/                       # Streamlit pages
│   ├── home.py              # Series/season selection
│   ├── review.py            # Draft review & editing
│   └── export.py            # JSON export & download
└── tests/                    # Unit tests
```

## Quick Start

### Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd racebot

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`

### Usage

1. **Fetch Data**
   - Go to **Home** page
   - Select a series (e.g., "NTT IndyCar Series")
   - Enter season year (e.g., 2024)
   - Click "Fetch & Build Draft"

2. **Review & Edit**
   - Go to **Review & Edit** page
   - Select an event from the list
   - Edit session details, times, types
   - Add or remove sessions as needed
   - Run validation to check for issues

3. **Export**
   - Go to **Export** page
   - Review validation status
   - Preview JSON
   - Download JSON file

4. **Resume Editing**
   - Later, go back to **Home**
   - Upload your previously exported JSON
   - Continue editing

## Data Model

### Series
- `series_id` - Unique identifier (e.g., "indycar")
- `name` - Display name
- `season` - Year
- `category` - Type (OPENWHEEL, ENDURANCE, etc.)
- `events[]` - List of events

### Event
- `event_id` - Unique stable ID
- `name` - Event name
- `start_date` / `end_date` - Date range
- `venue` - Location with timezone
- `sessions[]` - List of sessions
- `sources[]` - Provenance data

### Session
- `session_id` - Unique ID within event
- `type` - PRACTICE, QUALIFYING, RACE, etc.
- `name` - Session name
- `start` / `end` - ISO-8601 with timezone offset
- `status` - SCHEDULED, TBD, CANCELLED, etc.
- Optional: `laps_planned`, `distance_km`, `stage_number`

## Validation Rules

### Errors (must fix)
- Missing session type or name
- Invalid start/end time format
- End time before start time
- Invalid venue timezone

### Warnings (can accept)
- Overlapping sessions within event
- Duplicate sessions (same type + similar time)
- TBD sessions (null start/end)
- Inferred timezone (not explicitly provided)

## Adding a New Connector

1. **Create connector file** in `connectors/`

```python
from connectors.base import Connector, RawSeriesPayload
from models.schema import Event, SeriesDescriptor
from models.enums import SeriesCategory

class MySeriesConnector(Connector):
    @property
    def id(self) -> str:
        return "my_series_official"
    
    @property
    def name(self) -> str:
        return "My Series Official"
    
    def supported_series(self) -> List[SeriesDescriptor]:
        return [
            SeriesDescriptor(
                series_id="my_series",
                name="My Racing Series",
                category=SeriesCategory.OPENWHEEL,
                connector_id=self.id
            )
        ]
    
    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        # Fetch data from source (HTTP, API, etc.)
        response = self._http_get("https://example.com/calendar.ics")
        return RawSeriesPayload(
            content=response.text,
            content_type="text/calendar",
            url="https://example.com/calendar.ics",
            retrieved_at=datetime.utcnow(),
            metadata={"season": season}
        )
    
    def extract(self, raw: RawSeriesPayload) -> List[Event]:
        # Parse raw data and return Event objects
        # ... implementation ...
        return events
```

2. **Register connector** in `connectors/__init__.py`

```python
from .my_series import MySeriesConnector

register_connector(MySeriesConnector())
```

3. **Test** - Restart the app and your series will appear in the dropdown

## Deployment

### Streamlit Community Cloud (Free)

1. Push code to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo
4. Select `app.py` as the main file
5. Deploy!

Your app will be live at `https://your-app-name.streamlit.app`

### Alternative: Render (Free Tier)

See [Render documentation](https://docs.render.com/deploy-streamlit) for Streamlit deployment.

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=term
```

## Data Sources

### Current Connectors

#### IndyCar
- **Source**: Official ROKT Calendar ICS feed
- **URL**: `https://sync.roktcalendar.com/webcal/3aef020f-0a9a-4c45-8219-9610e2269f59`
- **Coverage**: Full season schedule with session times
- **Timezone**: Varies by event location (auto-detected)

### Planned Connectors
- Formula 1
- WEC (World Endurance Championship)
- IMSA
- MotoGP
- WRC (World Rally Championship)
- GT World Challenge

## Development

### Project Philosophy

- **Correctness over convenience** - Never silently guess critical data
- **Auditability** - Full provenance tracking for every field
- **Modularity** - Easy to add new data sources
- **Resilience** - Graceful handling of source changes

### Code Style

- Type hints throughout
- Pydantic for validation
- Descriptive variable names
- Comprehensive docstrings

## Troubleshooting

### "No connectors available"
- Ensure connectors are registered in `connectors/__init__.py`
- Check for import errors in connector files

### "Invalid timezone"
- Must be valid IANA timezone (e.g., `America/New_York`, not `EST`)
- Use `timezone_utils.infer_timezone_from_location()` for auto-detection

### "Failed to fetch data"
- Check network connection
- Verify data source URL is still valid
- Check connector logs for specific error

## License

MIT License - feel free to use and modify for your needs.

## Contributing

Contributions welcome! Please:

1. Add tests for new features
2. Follow existing code style
3. Update documentation
4. Create meaningful commit messages

## Support

For issues or questions, please open a GitHub issue.

---

Built with ❤️ for motorsport fans
# racebot

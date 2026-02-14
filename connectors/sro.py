from typing import Any, Dict, List
from .generic import GenericWebConnector
from models.enums import SeriesCategory

class SROConnector(GenericWebConnector):
    """
    Connector for SRO / GT World Challenge series.
    Uses the generic playback scraper but sets specific URLs.
    """
    
    def __init__(self):
        # We configure the generic connector with our known series
        super().__init__(series_configs={
            "gtwc_europe": {"name": "GT World Challenge Europe", "category": SeriesCategory.GT},
            "gtwc_asia": {"name": "GT World Challenge Asia", "category": SeriesCategory.GT},
            "gtwc_america": {"name": "GT World Challenge America", "category": SeriesCategory.GT},
            "igtc": {"name": "Intercontinental GT Challenge", "category": SeriesCategory.GT},
        })
        
    @property
    def id(self) -> str:
        return "sro_gt"
        
    @property
    def name(self) -> str:
        return "SRO GT World Scraper"
        
    @property
    def needs_url(self) -> bool:
        return False
        
    def fetch_season(self, series_id: str, season: int) -> Any:
        # Map series to URL
        # Note: URLs might change year to year or be static
        base_urls = {
            "gtwc_europe": "https://www.gt-world-challenge-europe.com/calendar",
            "gtwc_asia": "https://www.gt-world-challenge-asia.com/calendar",
            "gtwc_america": "https://www.gt-world-challenge-america.com/calendar",
            "igtc": "https://www.intercontinentalgtchallenge.com/calendar",
        }
        
        target = base_urls.get(series_id)
        if target:
            self.set_target_url(target)
            
        return super().fetch_season(series_id, season)

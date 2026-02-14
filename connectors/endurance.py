from typing import Any, Dict, List
from .generic import GenericWebConnector
from models.enums import SeriesCategory

class EnduranceConnector(GenericWebConnector):
    """
    Connector for Endurance series: WEC, IMSA, ELMS, Asian LMS, Super GT.
    """
    
    def __init__(self):
        super().__init__(series_configs={
            "wec": {"name": "FIA World Endurance Championship", "category": SeriesCategory.ENDURANCE},
            "imsa": {"name": "IMSA WeatherTech SportsCar Championship", "category": SeriesCategory.ENDURANCE},
            "elms": {"name": "European Le Mans Series", "category": SeriesCategory.ENDURANCE},
            "asian_lms": {"name": "Asian Le Mans Series", "category": SeriesCategory.ENDURANCE},
            "super_gt": {"name": "Super GT", "category": SeriesCategory.GT}, # GT but fits here
        })
        
    @property
    def id(self) -> str:
        return "endurance"
        
    @property
    def name(self) -> str:
        return "Endurance & GT Scraper"
        
    @property
    def needs_url(self) -> bool:
        return False
        
    def fetch_season(self, series_id: str, season: int) -> Any:
        # Note: URLs are best-guess entry points for the scraper to find schedule data
        base_urls = {
            "wec": "https://www.fiawec.com/en/calendar/80", # Page often has list
            "imsa": "https://www.imsa.com/weathertech/weathertech-2026-schedule/", # adjust year if needed logic
            "elms": "https://www.europeanlemansseries.com/en/season",
            "asian_lms": "https://www.asianlemansseries.com/season",
            "super_gt": "https://supergt.net/races",
        }
        
        target = base_urls.get(series_id)
        
        # Dynamic year adjustment for IMSA if possible
        if series_id == "imsa":
            target = f"https://www.imsa.com/weathertech/weathertech-{season}-schedule/"
            
        if target:
            self.set_target_url(target)
            
        return super().fetch_season(series_id, season)

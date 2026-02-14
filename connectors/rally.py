from typing import Any, Dict, List
from .generic import GenericWebConnector
from models.enums import SeriesCategory

class RallyConnector(GenericWebConnector):
    """
    Connector for Rally & Off-road series: WRC, Dakar, Extreme E.
    """
    
    def __init__(self):
        super().__init__(series_configs={
            "wrc": {"name": "FIA World Rally Championship", "category": SeriesCategory.RALLY},
            "dakar": {"name": "Dakar Rally", "category": SeriesCategory.RALLY},
            "extreme_e": {"name": "Extreme E", "category": SeriesCategory.RALLY},
        })
        
    @property
    def id(self) -> str:
        return "rally"
        
    @property
    def name(self) -> str:
        return "Rally & Off-Road Scraper"
        
    @property
    def needs_url(self) -> bool:
        return False
        
    def fetch_season(self, series_id: str, season: int) -> Any:
        base_urls = {
            "wrc": "https://www.wrc.com/c/calendar",
            "dakar": "https://www.dakar.com/en/calendar",
            "extreme_e": "https://www.extreme-e.com/en/calendar",
        }
        
        target = base_urls.get(series_id)
        if target:
            self.set_target_url(target)
            
        return super().fetch_season(series_id, season)

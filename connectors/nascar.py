from typing import Any, Dict, List
from .generic import GenericWebConnector
from models.enums import SeriesCategory

class NASCARConnector(GenericWebConnector):
    """
    Connector for NASCAR series (Cup, Xfinity, Truck).
    Uses the generic playback scraper but sets specific URLs.
    """
    
    def __init__(self):
        # We configure the generic connector with our known series
        super().__init__(series_configs={
            "nascar_cup": {"name": "NASCAR Cup Series", "category": SeriesCategory.STOCK},
            "nascar_xfinity": {"name": "NASCAR Xfinity Series", "category": SeriesCategory.STOCK},
            "nascar_truck": {"name": "NASCAR Craftsman Truck Series", "category": SeriesCategory.STOCK},
        })
        
    @property
    def id(self) -> str:
        return "nascar"
        
    @property
    def name(self) -> str:
        return "NASCAR.com Scraper"
        
    @property
    def needs_url(self) -> bool:
        # We auto-determine URL based on series
        return False
        
    def fetch_season(self, series_id: str, season: int) -> Any:
        # Map series to URL
        base_urls = {
            "nascar_cup": "https://www.nascar.com/nascar-cup-series/schedule/",
            "nascar_xfinity": "https://www.nascar.com/nascar-xfinity-series/schedule/",
            "nascar_truck": "https://www.nascar.com/nascar-craftsman-truck-series/schedule/",
        }
        
        target = base_urls.get(series_id)
        if target:
            self.set_target_url(target)
            
        return super().fetch_season(series_id, season)

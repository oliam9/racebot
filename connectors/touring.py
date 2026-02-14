from typing import Any, Dict, List
from .generic import GenericWebConnector
from models.enums import SeriesCategory

class TouringConnector(GenericWebConnector):
    """
    Connector for Touring & Stock Car series.
    """
    
    def __init__(self):
        super().__init__(series_configs={
            "supercars": {"name": "Supercars Championship", "category": SeriesCategory.TOURING},
            "btcc": {"name": "British Touring Car Championship", "category": SeriesCategory.TOURING},
            "stock_car_br": {"name": "Stock Car Pro Series", "category": SeriesCategory.STOCK},
            "tcr_world": {"name": "TCR World Tour", "category": SeriesCategory.TOURING},
            "wtcr": {"name": "WTCR - FIA World Touring Car Cup", "category": SeriesCategory.TOURING},
        })
        
    @property
    def id(self) -> str:
        return "touring"
        
    @property
    def name(self) -> str:
        return "Touring & Stock Scraper"
        
    @property
    def needs_url(self) -> bool:
        return False
        
    def fetch_season(self, series_id: str, season: int) -> Any:
        base_urls = {
            "supercars": "https://www.supercars.com/calendar",
            "btcc": "https://www.btcc.net/calendar/",
            "stock_car_br": "https://www.stockproseries.com.br/", # Might need specific page
            "tcr_world": "https://www.tcr-worldranking.com/tcr-world-tour",
            "wtcr": "https://www.fiawtcr.com/calendar/",
        }
        
        target = base_urls.get(series_id)
        if target:
            self.set_target_url(target)
            
        return super().fetch_season(series_id, season)

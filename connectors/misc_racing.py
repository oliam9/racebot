from typing import Any, Dict, List
from .generic import GenericWebConnector
from models.enums import SeriesCategory

class MiscRacingConnector(GenericWebConnector):
    """
    Connector for miscellaneous series not covered elsewhere.
    Super Formula, F1 Academy, AMA Supercross.
    """
    
    def __init__(self):
        super().__init__(series_configs={
            "super_formula": {"name": "Super Formula Championship", "category": SeriesCategory.OPENWHEEL},
            "f1_academy": {"name": "F1 Academy", "category": SeriesCategory.OPENWHEEL}, # or FORMULA
            "ama_supercross": {"name": "AMA Supercross Championship", "category": SeriesCategory.MOTORCYCLE},
            "formula_e": {"name": "ABB FIA Formula E World Championship", "category": SeriesCategory.OPENWHEEL},
            "formula_regional_eu": {"name": "Formula Regional European Championship", "category": SeriesCategory.OPENWHEEL},
        })
        
    @property
    def id(self) -> str:
        return "misc_racing"
        
    @property
    def name(self) -> str:
        return "Misc Racing Scraper"
        
    @property
    def needs_url(self) -> bool:
        return False
        
    def fetch_season(self, series_id: str, season: int) -> Any:
        base_urls = {
            "super_formula": "https://superformula.net/sf3/en/race/",
            "f1_academy": "https://www.f1academy.com/Racing-Series/Calendar",
            "ama_supercross": "https://www.supercrosslive.com/tickets",
            "formula_e": "https://www.fiaformulae.com/en/calendar",
            "formula_regional_eu": "https://formularegionaleubyalpine.com/calendar/",
        }
        
        target = base_urls.get(series_id)
        if target:
            self.set_target_url(target)
            
        return super().fetch_season(series_id, season)

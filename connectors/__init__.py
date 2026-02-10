"""
Connectors package initialization.
"""

from .base import Connector, RawSeriesPayload
from .registry import (
    get_registry,
    register_connector,
    get_connector,
    list_available_series,
)
from .indycar import IndyCarConnector
from .generic import GenericWebConnector
from .motogp import MotoGPConnector
from .f1 import F1Connector
from models.enums import SeriesCategory

# Auto-register all connectors
register_connector(IndyCarConnector())
register_connector(MotoGPConnector())
register_connector(F1Connector())

# Register generic connector with known series that use URL-based scraping
register_connector(
    GenericWebConnector(
        series_configs={
            "dtm": {
                "name": "DTM",
                "category": SeriesCategory.GT,
            },
        }
    )
)

__all__ = [
    "Connector",
    "RawSeriesPayload",
    "get_registry",
    "register_connector",
    "get_connector",
    "list_available_series",
    "IndyCarConnector",
    "GenericWebConnector",
    "MotoGPConnector",
    "F1Connector",
]

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
from .dtm import DTMConnector
from .f2 import F2Connector
from .f3 import F3Connector
from .worldrx import WorldRXConnector
from .worldsbk import WorldSBKConnector
from .moto2 import Moto2Connector
from .moto3 import Moto3Connector
from models.enums import SeriesCategory

# Auto-register all connectors
register_connector(IndyCarConnector())
register_connector(MotoGPConnector())
register_connector(Moto2Connector())
register_connector(Moto3Connector())
register_connector(F1Connector())
register_connector(DTMConnector())
register_connector(F2Connector())
register_connector(F3Connector())
register_connector(WorldRXConnector())
register_connector(WorldSBKConnector())

# Generic connector is available but not auto-registered
# Users can manually register it for custom series

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
    "DTMConnector",
    "F2Connector",
    "F3Connector",
    "WorldRXConnector",
    "WorldSBKConnector",
]

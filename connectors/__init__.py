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
from .formula_e import FormulaEConnector
from .nascar_cup import NASCARCupConnector
from .wec import WECConnector
from .wrc import WRCConnector
from .imsa import IMSAConnector
from .nascar_xfinity import NASCARXfinityConnector
from .nascar_truck import NASCARTruckConnector
from .f1_academy import F1AcademyConnector
from .supercars import SupercarsConnector
from .btcc import BTCCConnector
from .super_formula import SuperFormulaConnector
from .elms import ELMSConnector
from .asian_lms import AsianLMSConnector
from .gtwc import GTWCEuropeConnector, GTWCAmericaConnector, GTWCAsiaConnector, IGTCConnector
from .super_gt import SuperGTConnector
from .dakar import DakarConnector
from .extreme_e import ExtremeEConnector
from .wtcr import WTCRConnector
from .stock_car_br import StockCarBRConnector
from .fim_supersport import FIMSupersportConnector
from .iom_tt import IsleOfManTTConnector
from .ama_supercross import AMASupercrossConnector
from .nascar import NASCARConnector
from .sro import SROConnector
from .endurance import EnduranceConnector
from .rally import RallyConnector
from .touring import TouringConnector
from .misc_racing import MiscRacingConnector
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
# Dedicated connectors for top-5 championships (registered before generics)
register_connector(FormulaEConnector())
register_connector(NASCARCupConnector())
register_connector(WECConnector())
register_connector(WRCConnector())
register_connector(IMSAConnector())
# Dedicated connectors — batch 2
register_connector(NASCARXfinityConnector())
register_connector(NASCARTruckConnector())
register_connector(F1AcademyConnector())
register_connector(SupercarsConnector())
register_connector(BTCCConnector())
# Dedicated connectors — batch 3 (final)
register_connector(SuperFormulaConnector())
register_connector(ELMSConnector())
register_connector(AsianLMSConnector())
register_connector(GTWCEuropeConnector())
register_connector(GTWCAmericaConnector())
register_connector(GTWCAsiaConnector())
register_connector(IGTCConnector())
register_connector(SuperGTConnector())
register_connector(DakarConnector())
register_connector(ExtremeEConnector())
register_connector(WTCRConnector())
register_connector(StockCarBRConnector())
register_connector(FIMSupersportConnector())
register_connector(IsleOfManTTConnector())
register_connector(AMASupercrossConnector())
# Generic/fallback connectors
register_connector(NASCARConnector())
register_connector(SROConnector())
register_connector(EnduranceConnector())
register_connector(RallyConnector())
register_connector(TouringConnector())
register_connector(MiscRacingConnector())

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
    "FormulaEConnector",
    "NASCARCupConnector",
    "WECConnector",
    "WRCConnector",
    "IMSAConnector",
    "NASCARXfinityConnector",
    "NASCARTruckConnector",
    "F1AcademyConnector",
    "SupercarsConnector",
    "BTCCConnector",
    "SuperFormulaConnector",
    "ELMSConnector",
    "AsianLMSConnector",
    "GTWCEuropeConnector",
    "GTWCAmericaConnector",
    "GTWCAsiaConnector",
    "IGTCConnector",
    "SuperGTConnector",
    "DakarConnector",
    "ExtremeEConnector",
    "WTCRConnector",
    "StockCarBRConnector",
    "FIMSupersportConnector",
    "IsleOfManTTConnector",
    "AMASupercrossConnector",
    "NASCARConnector",
    "SROConnector",
    "EnduranceConnector",
    "RallyConnector",
    "TouringConnector",
    "MiscRacingConnector",
]

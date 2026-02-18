"""
NASCAR Craftsman Truck Series Connector using the official NASCAR CDN API.
Same API as Cup Series but with series_id=3.
"""
from datetime import datetime
from typing import List

from models.schema import SeriesDescriptor
from models.enums import SeriesCategory
from .nascar_cup import NASCARCupConnector
from .base import RawSeriesPayload

import logging

logger = logging.getLogger(__name__)


class NASCARTruckConnector(NASCARCupConnector):
    """
    Connector for NASCAR Craftsman Truck Series.
    Inherits from NASCARCupConnector — same API, different series_id.
    """

    NASCAR_SERIES_ID = 3  # Truck

    @property
    def id(self) -> str:
        return "nascar_truck_official"

    @property
    def name(self) -> str:
        return "NASCAR Craftsman Truck Series (Official API)"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [
            SeriesDescriptor(
                series_id="nascar_truck",
                name="NASCAR Craftsman Truck Series",
                category=SeriesCategory.STOCK,
                connector_id=self.id,
            )
        ]

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != "nascar_truck":
            raise ValueError(f"NASCAR Truck connector does not support: {series_id}")
        return super().fetch_season("nascar_cup", season)

    def extract(self, raw: RawSeriesPayload) -> List['Event']:
        raw.metadata["series_id"] = "nascar_truck"
        events = super().extract(raw)
        for evt in events:
            evt.series_id = "nascar_truck"
            evt.event_id = evt.event_id.replace("nascar_cup_", "nascar_truck_")
            for s in evt.sessions:
                s.session_id = s.session_id.replace("nascar_", "nascar_truck_")
        return events

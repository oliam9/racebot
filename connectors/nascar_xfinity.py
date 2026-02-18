"""
NASCAR Xfinity Series Connector using the official NASCAR CDN API.
Same API as Cup Series but with series_id=2.
"""
from datetime import datetime
from typing import List

from models.schema import SeriesDescriptor
from models.enums import SeriesCategory
from .nascar_cup import NASCARCupConnector
from .base import RawSeriesPayload

import logging

logger = logging.getLogger(__name__)


class NASCARXfinityConnector(NASCARCupConnector):
    """
    Connector for NASCAR Xfinity Series.
    Inherits from NASCARCupConnector — same API, different series_id.
    """

    NASCAR_SERIES_ID = 2  # Xfinity

    @property
    def id(self) -> str:
        return "nascar_xfinity_official"

    @property
    def name(self) -> str:
        return "NASCAR Xfinity Series (Official API)"

    def supported_series(self) -> List[SeriesDescriptor]:
        return [
            SeriesDescriptor(
                series_id="nascar_xfinity",
                name="NASCAR Xfinity Series",
                category=SeriesCategory.STOCK,
                connector_id=self.id,
            )
        ]

    def fetch_season(self, series_id: str, season: int) -> RawSeriesPayload:
        if series_id != "nascar_xfinity":
            raise ValueError(f"NASCAR Xfinity connector does not support: {series_id}")
        # Use parent's fetch with our series_id override
        return super().fetch_season("nascar_cup", season)

    def extract(self, raw: RawSeriesPayload) -> List['Event']:
        # Override series_id in events
        raw.metadata["series_id"] = "nascar_xfinity"
        events = super().extract(raw)
        for evt in events:
            evt.series_id = "nascar_xfinity"
            evt.event_id = evt.event_id.replace("nascar_cup_", "nascar_xfinity_")
            for s in evt.sessions:
                s.session_id = s.session_id.replace("nascar_", "nascar_xfinity_")
        return events

"""
Connector registry for discovering and accessing connectors.
"""

from typing import Dict, List, Optional
from .base import Connector
from models.schema import SeriesDescriptor


class ConnectorRegistry:
    """Registry for all available connectors."""
    
    def __init__(self):
        self._connectors: Dict[str, Connector] = {}
    
    def register(self, connector: Connector):
        """
        Register a connector.
        
        Args:
            connector: Connector instance to register
        """
        self._connectors[connector.id] = connector
    
    def get(self, connector_id: str) -> Optional[Connector]:
        """
        Get connector by ID.
        
        Args:
            connector_id: Connector identifier
            
        Returns:
            Connector instance or None if not found
        """
        return self._connectors.get(connector_id)
    
    def list_connectors(self) -> List[Connector]:
        """
        List all registered connectors.
        
        Returns:
            List of all connectors
        """
        return list(self._connectors.values())
    
    def list_available_series(self) -> List[SeriesDescriptor]:
        """
        List all available series from all connectors.
        
        Returns:
            List of SeriesDescriptor objects
        """
        all_series = []
        for connector in self._connectors.values():
            try:
                series = connector.supported_series()
                all_series.extend(series)
            except Exception:
                # Skip connectors that fail health check
                continue
        return all_series
    
    def find_connector_for_series(self, series_id: str) -> Optional[Connector]:
        """
        Find connector that supports a given series.
        
        Args:
            series_id: Series identifier
            
        Returns:
            Connector instance or None if not found
        """
        for connector in self._connectors.values():
            series_list = connector.supported_series()
            for series in series_list:
                if series.series_id == series_id:
                    return connector
        return None


# Global registry instance
_registry = ConnectorRegistry()


def get_registry() -> ConnectorRegistry:
    """Get the global connector registry."""
    return _registry


def register_connector(connector: Connector):
    """Register a connector with the global registry."""
    _registry.register(connector)


def get_connector(connector_id: str) -> Optional[Connector]:
    """Get connector from global registry."""
    return _registry.get(connector_id)


def list_available_series() -> List[SeriesDescriptor]:
    """List all available series."""
    return _registry.list_available_series()

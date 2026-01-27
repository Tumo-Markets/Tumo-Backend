"""
Volume Data Schemas

Pydantic models for type-safe volume data structures.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class VolumeStats(BaseModel):
    """Current hour volume statistics (in-memory cache)."""

    model_config = ConfigDict(json_encoders={Decimal: str})

    open_volume: Decimal = Field(default=Decimal("0"))
    close_volume: Decimal = Field(default=Decimal("0"))
    total_volume: Decimal = Field(default=Decimal("0"))
    open_trades: int = Field(default=0)
    close_trades: int = Field(default=0)
    total_trades: int = Field(default=0)


class Volume24hData(BaseModel):
    """24-hour rolling volume data."""

    model_config = ConfigDict(json_encoders={Decimal: str})

    market_id: str
    volume_24h: Decimal
    open_volume_24h: Decimal
    close_volume_24h: Decimal
    trades_24h: int
    current_hour_volume: Decimal
    timestamp: datetime


class VolumeHistoryItem(BaseModel):
    """Single hourly volume snapshot."""

    model_config = ConfigDict(json_encoders={Decimal: str})

    timestamp: datetime
    open_volume: Decimal
    close_volume: Decimal
    total_volume: Decimal
    open_trades: int
    close_trades: int
    total_trades: int


class VolumeStatsDetailed(BaseModel):
    """Detailed volume statistics with analytics."""

    model_config = ConfigDict(json_encoders={Decimal: str})

    market_id: str
    volume_24h: Decimal
    volume_change_24h: str  # e.g., "+15.5%"
    peak_hour_volume: Decimal
    avg_hourly_volume: Decimal
    total_trades_24h: int
    avg_trade_size: Decimal


# Type alias for cache (more explicit than Dict)
VolumeCache = dict[str, VolumeStats]  # market_id -> VolumeStats

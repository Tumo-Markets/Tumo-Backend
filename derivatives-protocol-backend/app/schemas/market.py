from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class MarketStatus(str, Enum):
    """Market status enum."""

    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class MarketBase(BaseModel):
    """Base market schema."""

    market_id: str = Field(..., description="Unique market identifier")
    base_token: str = Field(..., description="Base token address")
    quote_token: str = Field(..., description="Quote token (usually USDC/USDT)")
    market_token: str = Field(..., description="Market token (usually USDC)")
    collateral_token: str = Field(..., description="Collateral token (usually SUI)")
    symbol: str = Field(..., description="Trading symbol (e.g., BTC/USDC)")
    pyth_price_id: str = Field(..., description="Pyth price feed ID")

    max_leverage: Decimal = Field(..., ge=1, le=100, description="Maximum leverage")
    min_position_size: Decimal = Field(..., gt=0, description="Minimum position size")
    max_position_size: Decimal = Field(..., gt=0, description="Maximum position size")

    maintenance_margin_rate: Decimal = Field(
        ..., gt=0, lt=1, description="Maintenance margin rate"
    )
    liquidation_fee_rate: Decimal = Field(
        ..., gt=0, lt=1, description="Liquidation fee rate"
    )

    funding_rate_interval: int = Field(
        default=3600, description="Funding rate interval in seconds"
    )
    max_funding_rate: Decimal = Field(
        default=Decimal("0.001"), description="Max funding rate per interval"
    )

    coinTradeType: str = Field(..., description="Coin trade type")
    marketCoinTradeID: str = Field(..., description="Market coin trade ID")
    priceFeedCoinTradeID: str = Field(..., description="Price feed coin trade ID")

    @field_validator(
        "max_leverage",
        "min_position_size",
        "max_position_size",
        "maintenance_margin_rate",
        "liquidation_fee_rate",
        "max_funding_rate",
        mode="before",
    )
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert to Decimal."""
        if isinstance(v, str):
            return Decimal(v)
        elif isinstance(v, (int, float)):
            return Decimal(str(v))
        return v


class MarketCreate(MarketBase):
    """Schema for creating a market."""

    pass


class MarketUpdate(BaseModel):
    """Schema for updating a market."""

    status: Optional[MarketStatus] = None
    max_leverage: Optional[Decimal] = None
    min_position_size: Optional[Decimal] = None
    max_position_size: Optional[Decimal] = None
    maintenance_margin_rate: Optional[Decimal] = None
    liquidation_fee_rate: Optional[Decimal] = None
    max_funding_rate: Optional[Decimal] = None

    @field_validator(
        "max_leverage",
        "min_position_size",
        "max_position_size",
        "maintenance_margin_rate",
        "liquidation_fee_rate",
        "max_funding_rate",
        mode="before",
    )
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert to Decimal."""
        if v is None:
            return v
        if isinstance(v, str):
            return Decimal(v)
        elif isinstance(v, (int, float)):
            return Decimal(str(v))
        return v


class Market(MarketBase):
    """Complete market schema with DB fields."""

    id: int
    status: MarketStatus = MarketStatus.ACTIVE

    total_long_positions: Decimal = Field(default=Decimal("0"))
    total_short_positions: Decimal = Field(default=Decimal("0"))
    total_volume: Decimal = Field(default=Decimal("0"))

    current_funding_rate: Decimal = Field(default=Decimal("0"))
    last_funding_update: Optional[datetime] = None

    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "json_encoders": {Decimal: str, datetime: lambda v: v.isoformat()},
    }


class MarketStats(BaseModel):
    """Market statistics schema."""

    market_id: str
    symbol: str
    collateral_in: str
    # Price info
    mark_price: Optional[Decimal] = None
    index_price: Optional[Decimal] = None
    price_24h_change: Optional[Decimal] = None

    # Volume
    volume_24h: Decimal = Decimal("0")

    # Open Interest
    total_long_oi: Decimal = Decimal("0")
    total_short_oi: Decimal = Decimal("0")
    total_oi: Decimal = Decimal("0")

    # Funding
    current_funding_rate: Decimal = Decimal("0")
    predicted_funding_rate: Optional[Decimal] = None
    next_funding_time: Optional[datetime] = None

    model_config = {"json_encoders": {Decimal: str, datetime: lambda v: v.isoformat()}}

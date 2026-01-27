"""
Onechain Type Schemas

Pydantic models for Onechain/Move blockchain types.
"""

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# TRANSACTION & EVENT TYPES
# ============================================================================


class OnechainEventData(BaseModel):
    """Event data from Onechain."""

    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={Decimal: str},
    )

    id: dict[str, str]

    package_id: str = Field(alias="packageId")
    transaction_module: str = Field(alias="transactionModule")
    sender: str
    type: str

    parsed_json: dict[str, Any] = Field(alias="parsedJson")

    bcs: str
    timestamp_ms: int = Field(alias="timestampMs")


class OnechainTransaction(BaseModel):
    """Transaction data from Onechain."""

    digest: str  # Transaction hash
    timestamp_ms: int
    checkpoint: int | None = None
    effects: dict[str, Any]
    events: list[OnechainEventData] = Field(default_factory=list)


class OnechainCheckpoint(BaseModel):
    """Checkpoint data from Onechain."""

    sequence_number: int
    digest: str
    timestamp_ms: int
    transactions: list[str] = Field(default_factory=list)


# ============================================================================
# POSITION & MARKET TYPES
# ============================================================================


class OnechainPosition(BaseModel):
    """Position object from Onechain."""

    model_config = ConfigDict(json_encoders={Decimal: str})

    id: str  # Object ID
    user: str  # Owner address
    market_id: str
    size: Decimal
    collateral: Decimal
    entry_price: Decimal
    leverage: Decimal
    is_long: bool
    accumulated_funding: Decimal = Field(default=Decimal("0"))
    opened_at: int  # Timestamp in ms


class OnechainMarket(BaseModel):
    """Market object from Onechain."""

    model_config = ConfigDict(json_encoders={Decimal: str})

    id: str  # Object ID
    symbol: str
    base_asset: str
    quote_asset: str
    max_leverage: Decimal
    maintenance_margin_rate: Decimal
    liquidation_fee_rate: Decimal
    funding_rate_interval: int  # In seconds
    total_long_oi: Decimal = Field(default=Decimal("0"))
    total_short_oi: Decimal = Field(default=Decimal("0"))


# ============================================================================
# RPC REQUEST/RESPONSE TYPES
# ============================================================================


class OnechainRPCRequest(BaseModel):
    """JSON-RPC request to Onechain."""

    jsonrpc: str = Field(default="2.0")
    id: int = Field(default=1)
    method: str
    params: list[Any] = Field(default_factory=list)


class OnechainRPCResponse(BaseModel):
    """JSON-RPC response from Onechain."""

    jsonrpc: str
    id: int
    result: Any | None = None
    error: dict[str, Any] | None = None


# ============================================================================
# EVENT PARSED TYPES
# ============================================================================


class PositionOpenedEvent(BaseModel):
    """Parsed PositionOpened event."""

    model_config = ConfigDict(json_encoders={Decimal: str})
    position_id: str
    user: str  # owner
    market_id: str
    size: Decimal
    collateral: Decimal
    entry_price: Decimal
    direction: int  # 0 = long, 1 = short
    timestamp: int


class PositionClosedEvent(BaseModel):
    """Parsed PositionClosed event."""

    model_config = ConfigDict(json_encoders={Decimal: str})
    position_id: str
    user: str  # owner
    close_price: Decimal
    market_id: str
    size: Decimal
    collateral_returned: Decimal
    pnl: Decimal
    is_profit: bool


class PositionUpdatedEvent(BaseModel):
    """Parsed PositionUpdated event."""

    model_config = ConfigDict(json_encoders={Decimal: str})

    user: str  # owner
    market_id: str
    position_id: str
    new_size: Decimal
    new_collateral: Decimal
    new_entry_price: Decimal
    direction: int  # 0 = long, 1 = short
    timestamp: int


class PositionLiquidatedEvent(BaseModel):
    """Parsed PositionLiquidated event."""

    model_config = ConfigDict(json_encoders={Decimal: str})


from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PositionLiquidatedEvent(BaseModel):
    """Parsed PositionLiquidated on-chain event"""

    model_config = ConfigDict(
        json_encoders={Decimal: str},
        populate_by_name=True,
    )

    position_id: str

    owner: str
    liquidator: str
    market_id: str

    size: Decimal
    collateral: Decimal
    pnl: Decimal

    amount_returned_to_liquidator: Decimal = Field(
        default=Decimal("0"),
        alias="amount_returned_to_liquidator",
    )

    timestamp: int  # unix ms

    liquidation_fee: Decimal = Field(
        default=Decimal("0"),
        description="Calculated off-chain from market config",
    )

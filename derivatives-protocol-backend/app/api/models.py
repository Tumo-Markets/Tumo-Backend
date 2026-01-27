from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.market import MarketStats
from app.schemas.position import PositionSide, PositionStatus


# ============================================================================
# BASE MESSAGES
# ============================================================================
def encode_datetime(v: datetime) -> str:
    return v.isoformat()


class WebSocketMessage(BaseModel):
    type: str


# ============================================================================
# CONNECTION MESSAGES
# ============================================================================


class ConnectedMessage(WebSocketMessage):
    """Connection success message."""

    type: str = Field(default="connected")
    message: str


class ErrorMessage(WebSocketMessage):
    """Error message."""

    type: str = Field(default="error")
    message: str
    code: int | None = None


# ============================================================================
# POSITION MESSAGES
# ============================================================================


class PositionUpdateItem(BaseModel):
    """Single position update data."""

    model_config = ConfigDict(json_encoders={Decimal: str})

    position_id: str
    market_id: str
    symbol: str
    market_token: str
    collateral_in: str
    side: PositionSide
    size: Decimal
    collateral: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal
    health_factor: Decimal
    liquidation_price: Decimal
    is_at_risk: bool


class PositionsUpdateMessage(WebSocketMessage):
    """Message containing user's position updates."""

    type: str = Field(default="positions_update")
    user_address: str
    positions: list[PositionUpdateItem]
    total_unrealized_pnl: Decimal
    positions_count: int = Field(default=0)


class EmptyPositionsMessage(WebSocketMessage):
    """Message when user has no open positions."""

    type: str = Field(default="positions_update")
    user_address: str
    positions: list[PositionUpdateItem] = Field(default_factory=list)
    total_unrealized_pnl: Decimal = Field(default=Decimal("0"))
    positions_count: int = Field(default=0)


# ============================================================================
# PRICE MESSAGES
# ============================================================================


class PriceUpdateMessage(WebSocketMessage):
    """Price update message."""

    type: str = Field(default="price_update")
    market_id: str
    symbol: str
    price: Decimal
    confidence: Decimal
    age_seconds: int


# ============================================================================
# MARKET STATS MESSAGES
# ============================================================================


class MarketStatsMessage(WebSocketMessage):
    """Market statistics message."""

    type: str = Field(default="market_stats")
    marketstats: MarketStats


# ============================================================================
# LIQUIDATION MESSAGES
# ============================================================================


class LiquidationCandidateItem(BaseModel):
    """Single liquidation candidate."""

    model_config = ConfigDict(json_encoders={Decimal: str})

    position_id: str
    user_address: str
    market_id: str
    health_factor: Decimal
    liquidation_price: Decimal
    current_price: Decimal
    potential_reward: Decimal


class LiquidationAlertMessage(WebSocketMessage):
    """Liquidation alert message."""

    type: str = Field(default="liquidation_alert")
    count: int
    candidates: list[LiquidationCandidateItem]


class CandleMessage(BaseModel):
    type: Literal["candle"] = "candle"
    market_id: str
    timeframe: str
    candle_start_timestamp: int
    current_timestamp: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    is_finished: bool


class ConnectedCandleMessage(ConnectedMessage):
    market_id: str
    timeframe: str


def new_candle(
    market_id: str,
    timeframe: str,
    candle_start: int,
    current_timestamp: int,
    price: Decimal,
) -> CandleMessage:
    return CandleMessage(
        market_id=market_id,
        timeframe=timeframe,
        candle_start_timestamp=candle_start,
        current_timestamp=current_timestamp,
        open=price,
        high=price,
        low=price,
        close=price,
        is_finished=False,
    )


def update_candle(
    candle: CandleMessage, price: Decimal, current_timestamp: int
) -> None:
    candle.high = max(candle.high, price)
    candle.low = min(candle.low, price)
    candle.close = price
    candle.current_timestamp = current_timestamp


# TODO:
# collateral will be explicitly passed by client once
# margin / subaccount balance logic is finalized
class OpenPositionRequest(BaseModel):
    market_id: str
    user_address: str

    side: PositionSide
    size: Decimal
    # collateral: Decimal
    leverage: Decimal

    entry_price: Decimal

    tx_hash: str
    block_number: int


class ClosePositionRequest(BaseModel):
    position_id: str
    exit_price: Decimal
    tx_hash: str
    status: PositionStatus = PositionStatus.CLOSED

class SponsoredTxRequest(BaseModel):
    kindBytesB64: str = Field(..., description="Base64 TransactionKind bytes")
    userSignatureB64: str = Field(..., description="User signature (flag||sig||pubkey)")
    sender: str = Field(..., description="User Sui address")
    gasBudget: int | None = Field(None, description="Optional gas budget override")


class SponsoredTxResponse(BaseModel):
    success: bool
    digest: str
    effects: dict
    events: list | None = None

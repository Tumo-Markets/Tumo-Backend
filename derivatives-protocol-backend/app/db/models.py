import enum
from decimal import Decimal

from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func


class Base(AsyncAttrs, DeclarativeBase):
    pass


class MarketStatusEnum(str, enum.Enum):
    """Market status enum."""

    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class PositionSideEnum(str, enum.Enum):
    """Position side enum."""

    LONG = "long"
    SHORT = "short"


class PositionStatusEnum(str, enum.Enum):
    """Position status enum."""

    OPEN = "open"
    CLOSED = "closed"
    LIQUIDATED = "liquidated"


class MarketModel(Base):
    """Market database model."""

    __tablename__ = "markets"

    id = Column(Integer, primary_key=True, index=True)
    market_id = Column(String(100), unique=True, nullable=False, index=True)

    # Token info
    base_token = Column(String(42), nullable=False)
    quote_token = Column(String(42), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    pyth_price_id = Column(String(66), nullable=False)

    # Market parameters
    max_leverage = Column(Numeric(10, 2), nullable=False)
    min_position_size = Column(Numeric(30, 18), nullable=False)
    max_position_size = Column(Numeric(30, 18), nullable=False)

    maintenance_margin_rate = Column(Numeric(10, 6), nullable=False)
    liquidation_fee_rate = Column(Numeric(10, 6), nullable=False)

    funding_rate_interval = Column(Integer, default=3600)
    max_funding_rate = Column(Numeric(10, 6), default=Decimal("0.001"))

    # Market state
    status = Column(
        SQLEnum(MarketStatusEnum), default=MarketStatusEnum.ACTIVE, nullable=False
    )

    total_long_positions = Column(Numeric(30, 18), default=Decimal("0"))
    total_short_positions = Column(Numeric(30, 18), default=Decimal("0"))
    total_volume = Column(Numeric(30, 18), default=Decimal("0"))

    current_funding_rate = Column(Numeric(10, 6), default=Decimal("0"))
    last_funding_update = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_market_symbol", "symbol"),
        Index("idx_market_status", "status"),
    )


class PositionModel(Base):
    """Position database model."""

    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(String(100), unique=True, nullable=False, index=True)

    # References
    market_id = Column(String(100), nullable=False, index=True)
    user_address = Column(String(44), nullable=False, index=True)

    # Position details
    side = Column(SQLEnum(PositionSideEnum), nullable=False)
    size = Column(Numeric(30, 18), nullable=False)
    collateral = Column(Numeric(30, 18), nullable=False)
    leverage = Column(Numeric(10, 2), nullable=False)

    # Prices
    entry_price = Column(Numeric(30, 18), nullable=False)
    exit_price = Column(Numeric(30, 18), nullable=True)

    # PnL
    realized_pnl = Column(Numeric(30, 18), default=Decimal("0"))
    accumulated_funding = Column(Numeric(30, 18), default=Decimal("0"))

    # Status
    status = Column(
        SQLEnum(PositionStatusEnum),
        default=PositionStatusEnum.OPEN,
        nullable=False,
        index=True,
    )

    # Blockchain data
    block_number = Column(Integer, nullable=False)
    transaction_hash = Column(String(66), nullable=False, index=True)
    close_transaction_hash = Column(String(66), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    closed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_position_user", "user_address"),
        Index("idx_position_market", "market_id"),
        Index("idx_position_status", "status"),
        Index("idx_position_user_market", "user_address", "market_id"),
        Index("idx_position_open", "status", "market_id"),
    )


class FundingRateModel(Base):
    """Funding rate history model."""

    __tablename__ = "funding_rates"

    id = Column(Integer, primary_key=True, index=True)

    market_id = Column(String(100), nullable=False, index=True)
    funding_rate = Column(Numeric(10, 6), nullable=False)

    long_oi = Column(Numeric(30, 18), nullable=False)
    short_oi = Column(Numeric(30, 18), nullable=False)

    timestamp = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (Index("idx_funding_market_time", "market_id", "timestamp"),)


class LiquidationModel(Base):
    """Liquidation events model."""

    __tablename__ = "liquidations"

    id = Column(Integer, primary_key=True, index=True)

    position_id = Column(String(100), nullable=False, index=True)
    market_id = Column(String(100), nullable=False)
    user_address = Column(String(42), nullable=False, index=True)
    liquidator_address = Column(String(42), nullable=False)

    liquidation_price = Column(Numeric(30, 18), nullable=False)
    collateral = Column(Numeric(30, 18), nullable=False)
    liquidation_fee = Column(Numeric(30, 18), nullable=False)

    transaction_hash = Column(String(66), nullable=False, index=True)
    block_number = Column(Integer, nullable=False)

    timestamp = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_liquidation_user", "user_address"),
        Index("idx_liquidation_market", "market_id"),
    )


class PriceHistoryModel(Base):
    """Price history for markets."""

    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)

    market_id = Column(String(100), nullable=False, index=True)
    price = Column(Numeric(30, 18), nullable=False)
    confidence = Column(Numeric(30, 18), nullable=False)

    timestamp = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (Index("idx_price_market_time", "market_id", "timestamp"),)


class BlockSyncModel(Base):
    """Track blockchain sync progress."""

    __tablename__ = "block_sync"

    id = Column(Integer, primary_key=True)
    chain_id = Column(Integer, nullable=False, unique=True)
    last_synced_block = Column(Integer, nullable=False, default=0)

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

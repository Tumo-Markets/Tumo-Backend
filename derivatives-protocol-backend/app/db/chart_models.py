"""
Chart Data Models - Add to app/db/models.py

Additional models for chart data aggregation.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, Numeric, String

from app.db.models import Base


class PriceOHLCVModel(Base):
    """
    OHLCV (candlestick) data for price charts.

    Pre-calculated candles for different timeframes.
    Updated by PriceAggregator background service.
    """

    __tablename__ = "price_ohlcv"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market_id = Column(String, nullable=False, index=True)

    # Timeframe: 1m, 5m, 15m, 1h, 4h, 1d
    timeframe = Column(String, nullable=False)

    # Timestamp of candle (aligned to timeframe boundary)
    timestamp = Column(DateTime, nullable=False)

    # OHLCV data
    open = Column(Numeric(precision=20, scale=8), nullable=False)
    high = Column(Numeric(precision=20, scale=8), nullable=False)
    low = Column(Numeric(precision=20, scale=8), nullable=False)
    close = Column(Numeric(precision=20, scale=8), nullable=False)
    volume = Column(Numeric(precision=30, scale=8), nullable=False, default=0)

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Composite index for fast queries
    __table_args__ = (
        Index("idx_market_timeframe_timestamp", "market_id", "timeframe", "timestamp"),
        Index("idx_timeframe_timestamp", "timeframe", "timestamp"),
    )


class PnLSnapshotModel(Base):
    """
    PnL snapshots for user portfolio performance tracking.

    Calculated periodically (every hour) for all users with open positions.
    Used for PnL chart visualization.
    """

    __tablename__ = "pnl_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_address = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False)

    # PnL breakdown
    total_pnl = Column(Numeric(precision=30, scale=8), nullable=False)
    unrealized_pnl = Column(Numeric(precision=30, scale=8), nullable=False)
    realized_pnl = Column(Numeric(precision=30, scale=8), nullable=False)

    # Portfolio metrics
    total_collateral = Column(Numeric(precision=30, scale=8), nullable=False)
    total_position_value = Column(Numeric(precision=30, scale=8), nullable=False)
    open_positions_count = Column(Integer, nullable=False)

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("idx_user_timestamp", "user_address", "timestamp"),)


class OISnapshotModel(Base):
    """
    Open Interest snapshots for market depth analysis.

    Tracks total long OI and short OI over time.
    Updated hourly by OIAggregator service.
    """

    __tablename__ = "oi_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False)

    # OI data
    total_long_oi = Column(Numeric(precision=30, scale=8), nullable=False)
    total_short_oi = Column(Numeric(precision=30, scale=8), nullable=False)
    total_oi = Column(Numeric(precision=30, scale=8), nullable=False)

    # Additional metrics
    long_short_ratio = Column(Numeric(precision=10, scale=4), nullable=False)

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("idx_market_timestamp", "market_id", "timestamp"),)


class VolumeSnapshotModel(Base):
    """
    Trading volume snapshots.

    Aggregated from position open/close events.
    Used for volume chart visualization.
    """

    __tablename__ = "volume_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False)

    # Volume data (in USD/quote currency)
    open_volume = Column(Numeric(precision=30, scale=8), nullable=False, default=0)
    close_volume = Column(Numeric(precision=30, scale=8), nullable=False, default=0)
    total_volume = Column(Numeric(precision=30, scale=8), nullable=False, default=0)

    # Trade counts
    open_trades = Column(Integer, nullable=False, default=0)
    close_trades = Column(Integer, nullable=False, default=0)
    total_trades = Column(Integer, nullable=False, default=0)

    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (Index("idx_market_timestamp_vol", "market_id", "timestamp"),)

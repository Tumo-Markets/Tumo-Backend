"""
Chart API Endpoints

Provides data for various chart types:
- Price charts (OHLCV candlesticks)
- PnL charts (portfolio performance)
- Open Interest charts (market depth)
- Funding rate charts
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.chart_models import OISnapshotModel, PnLSnapshotModel, PriceOHLCVModel
from app.db.models import FundingRateModel, MarketModel
from app.db.session import get_db
from app.schemas.common import ResponseBase
from app.services.oracle import oracle_service

router = APIRouter(prefix="/charts", tags=["Charts"])


@router.get("/price/{market_id}", response_model=ResponseBase[List[dict]])
async def get_price_chart(
    market_id: str,
    timeframe: str = Query("1h", regex="^(1m|5m|15m|1h|4h|1d|1w)$"),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """
    Get OHLCV (candlestick) data for price chart.

    **Timeframes:**
    - 1m: 1 minute candles
    - 5m: 5 minute candles
    - 1h: 1 hour candles
    - 4h: 4 hour candles
    - 1d: Daily candles
    - 1w: Weekly candles

    Args:
        market_id: Market identifier (e.g., "btc-usdc-perp")
        timeframe: Candle timeframe (default: 1h)
        limit: Number of candles to return (default: 100, max: 1000)

    Returns:
        List of OHLCV candles in chronological order
    """
    # Verify market exists
    market_stmt = select(MarketModel).where(MarketModel.market_id == market_id)
    market_result = await db.execute(market_stmt)
    market = market_result.scalar_one_or_none()

    if not market:
        raise HTTPException(status_code=404, detail=f"Market '{market_id}' not found")

    stmt = (
        select(PriceOHLCVModel)
        .where(
            PriceOHLCVModel.market_id == market_id,
            PriceOHLCVModel.timeframe == timeframe,
        )
        .order_by(PriceOHLCVModel.timestamp.desc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    candles = result.scalars().all()

    price_data = await oracle_service.get_latest_price(market.pyth_price_id)
    current_price = price_data.normalized_price if price_data else None
    now = datetime.utcnow()

    if not candles:
        if current_price is None:
            return ResponseBase(success=True, data=[], message="No price data available")

        p = str(current_price)
        return ResponseBase(
            success=True,
            data=[
                {
                    "timestamp": now.isoformat(),
                    "open": p,
                    "high": p,
                    "low": p,
                    "close": p,
                    "volume": "0",
                    "is_finished": False,
                }
            ],
            message="No historical data. Showing current price only.",
        )

    chart_data = [
        {
            "timestamp": candle.timestamp.isoformat(),
            "open": str(candle.open),
            "high": str(candle.high),
            "low": str(candle.low),
            "close": str(candle.close),
            "volume": str(candle.volume),
            "is_finished": True,
        }
        for candle in reversed(candles)
    ]

    if current_price is not None:
        last = candles[0]
        open_price = Decimal(str(last.close))
        high_price = max(open_price, current_price)
        low_price = min(open_price, current_price)

        chart_data.append(
            {
                "timestamp": now.isoformat(),
                "open": str(open_price),
                "high": str(high_price),
                "low": str(low_price),
                "close": str(current_price),
                "volume": "0",
                "is_finished": False,
            }
        )

    return ResponseBase(success=True, data=chart_data)


@router.get("/pnl/{user_address}", response_model=ResponseBase[List[dict]])
async def get_pnl_chart(
    user_address: str,
    timeframe: str = Query("24h", regex="^(24h|7d|30d|90d)$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get PnL chart data for user's portfolio performance.

    Shows total PnL, unrealized PnL, and realized PnL over time.

    **Timeframes:**
    - 24h: Last 24 hours
    - 7d: Last 7 days
    - 30d: Last 30 days
    - 90d: Last 90 days

    Args:
        user_address: User wallet address
        timeframe: Time period (default: 24h)

    Returns:
        List of PnL snapshots with timestamps
    """
    user_address = user_address.lower()

    # Calculate time range
    timeframe_hours = {
        "24h": 24,
        "7d": 24 * 7,
        "30d": 24 * 30,
        "90d": 24 * 90,
    }

    hours = timeframe_hours[timeframe]
    start_time = datetime.utcnow() - timedelta(hours=hours)

    # Get PnL snapshots
    stmt = (
        select(PnLSnapshotModel)
        .where(
            PnLSnapshotModel.user_address == user_address,
            PnLSnapshotModel.timestamp >= start_time,
        )
        .order_by(PnLSnapshotModel.timestamp.asc())
    )

    result = await db.execute(stmt)
    snapshots = result.scalars().all()

    if not snapshots:
        # No historical data - calculate current snapshot
        from app.api.positions import get_user_summary

        try:
            summary_response = await get_user_summary(user_address, db)
            summary = summary_response.data

            current_snapshot = {
                "timestamp": datetime.utcnow().isoformat(),
                "total_pnl": str(
                    summary.total_unrealized_pnl + summary.total_realized_pnl
                ),
                "unrealized_pnl": str(summary.total_unrealized_pnl),
                "realized_pnl": str(summary.total_realized_pnl),
                "total_collateral": str(summary.total_collateral),
                "equity": str(summary.total_collateral + summary.total_unrealized_pnl),
                "open_positions": summary.open_positions,
            }

            return ResponseBase(
                success=True,
                data=[current_snapshot],
                message="No historical data. Showing current snapshot only.",
            )
        except Exception:
            return ResponseBase(
                success=True, data=[], message="No positions found for user"
            )

    # Format response
    chart_data = [
        {
            "timestamp": snapshot.timestamp.isoformat(),
            "total_pnl": str(snapshot.total_pnl),
            "unrealized_pnl": str(snapshot.unrealized_pnl),
            "realized_pnl": str(snapshot.realized_pnl),
            "total_collateral": str(snapshot.total_collateral),
            "equity": str(snapshot.total_collateral + snapshot.unrealized_pnl),
            "open_positions": snapshot.open_positions_count,
        }
        for snapshot in snapshots
    ]

    return ResponseBase(success=True, data=chart_data)


@router.get("/oi/{market_id}", response_model=ResponseBase[List[dict]])
async def get_oi_chart(
    market_id: str,
    timeframe: str = Query("24h", regex="^(24h|7d|30d)$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get Open Interest chart data.

    Shows long OI, short OI, and total OI over time.

    **Timeframes:**
    - 24h: Last 24 hours
    - 7d: Last 7 days
    - 30d: Last 30 days

    Args:
        market_id: Market identifier
        timeframe: Time period (default: 24h)

    Returns:
        List of OI snapshots
    """
    # Verify market exists
    market_stmt = select(MarketModel).where(MarketModel.market_id == market_id)
    market_result = await db.execute(market_stmt)
    market = market_result.scalar_one_or_none()

    if not market:
        raise HTTPException(status_code=404, detail=f"Market '{market_id}' not found")

    # Calculate time range
    timeframe_hours = {
        "24h": 24,
        "7d": 24 * 7,
        "30d": 24 * 30,
    }

    hours = timeframe_hours[timeframe]
    start_time = datetime.utcnow() - timedelta(hours=hours)

    # Get OI snapshots
    stmt = (
        select(OISnapshotModel)
        .where(
            OISnapshotModel.market_id == market_id,
            OISnapshotModel.timestamp >= start_time,
        )
        .order_by(OISnapshotModel.timestamp.asc())
    )

    result = await db.execute(stmt)
    snapshots = result.scalars().all()

    if not snapshots:
        # No historical data - return current market OI
        current_snapshot = {
            "timestamp": datetime.utcnow().isoformat(),
            "total_long_oi": str(market.total_long_positions),
            "total_short_oi": str(market.total_short_positions),
            "total_oi": str(market.total_long_positions + market.total_short_positions),
            "long_short_ratio": str(
                market.total_long_positions / market.total_short_positions
                if market.total_short_positions > 0
                else 0
            ),
        }

        return ResponseBase(
            success=True,
            data=[current_snapshot],
            message="No historical data. Showing current snapshot only.",
        )

    # Format response
    chart_data = [
        {
            "timestamp": snapshot.timestamp.isoformat(),
            "total_long_oi": str(snapshot.total_long_oi),
            "total_short_oi": str(snapshot.total_short_oi),
            "total_oi": str(snapshot.total_oi),
            "long_short_ratio": str(snapshot.long_short_ratio),
        }
        for snapshot in snapshots
    ]

    return ResponseBase(success=True, data=chart_data)


@router.get("/funding/{market_id}", response_model=ResponseBase[List[dict]])
async def get_funding_chart(
    market_id: str,
    hours: int = Query(24, ge=1, le=168),  # Max 7 days
    db: AsyncSession = Depends(get_db),
):
    """
    Get Funding Rate chart data.

    Shows funding rate history over time.

    Args:
        market_id: Market identifier
        hours: Number of hours of history (default: 24, max: 168)

    Returns:
        List of funding rate records
    """
    # Verify market exists
    market_stmt = select(MarketModel).where(MarketModel.market_id == market_id)
    market_result = await db.execute(market_stmt)
    market = market_result.scalar_one_or_none()

    if not market:
        raise HTTPException(status_code=404, detail=f"Market '{market_id}' not found")

    start_time = datetime.utcnow() - timedelta(hours=hours)

    # Get funding rate history
    stmt = (
        select(FundingRateModel)
        .where(
            FundingRateModel.market_id == market_id,
            FundingRateModel.timestamp >= start_time,
        )
        .order_by(FundingRateModel.timestamp.asc())
    )

    result = await db.execute(stmt)
    funding_rates = result.scalars().all()

    if not funding_rates:
        # No historical data - return current funding rate
        current_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "funding_rate": str(market.current_funding_rate),
            "long_oi": str(market.total_long_positions),
            "short_oi": str(market.total_short_positions),
        }

        return ResponseBase(
            success=True,
            data=[current_data],
            message="No historical data. Showing current funding rate only.",
        )

    # Format response
    chart_data = [
        {
            "timestamp": fr.timestamp.isoformat(),
            "funding_rate": str(fr.funding_rate),
            "long_oi": str(fr.long_oi),
            "short_oi": str(fr.short_oi),
        }
        for fr in funding_rates
    ]

    return ResponseBase(success=True, data=chart_data)

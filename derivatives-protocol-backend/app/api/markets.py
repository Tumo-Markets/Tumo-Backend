from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import build_collateral_in
from app.db.models import MarketModel, PriceHistoryModel
from app.db.session import get_db
from app.schemas.common import PaginatedResponse, ResponseBase
from app.schemas.market import Market, MarketStats
from app.services.funding import funding_service
from app.services.oracle import oracle_service
from app.services.volume_aggregator import volume_aggregator

router = APIRouter(prefix="/markets", tags=["Markets"])


@router.get("/", response_model=PaginatedResponse[Market])
async def get_markets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Get list of markets with pagination.

    Args:
        page: Page number
        page_size: Items per page
        status: Filter by status (active, paused, closed)
        db: Database session
    """
    # Build query
    stmt = select(MarketModel)

    if status:
        stmt = stmt.where(MarketModel.status == status)

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    result = await db.execute(count_stmt)
    total = result.scalar()

    # Get paginated results
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    markets = result.scalars().all()

    return PaginatedResponse(
        items=[Market.model_validate(m) for m in markets],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/{market_id}", response_model=ResponseBase[Market])
async def get_market(
    market_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get market by ID.

    Args:
        market_id: Market identifier
        db: Database session
    """
    stmt = select(MarketModel).where(MarketModel.market_id == market_id)
    result = await db.execute(stmt)
    market = result.scalar_one_or_none()

    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    return ResponseBase(
        success=True,
        data=Market.model_validate(market),
    )


@router.get("/{market_id}/stats", response_model=ResponseBase[MarketStats])
async def get_market_stats(
    market_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get market statistics including price, volume, and funding.

    Args:
        market_id: Market identifier
        db: Database session
    """
    # Get market
    stmt = select(MarketModel).where(MarketModel.market_id == market_id)
    result = await db.execute(stmt)
    market = result.scalar_one_or_none()

    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    # Get current price from oracle
    price_data = await oracle_service.get_latest_price(market.pyth_price_id)

    mark_price = None
    if price_data:
        mark_price = price_data.normalized_price

    # Predict next funding rate
    predicted_funding = await funding_service.predict_next_funding_rate(market_id)

    # Calculate next funding time
    next_funding_time = None
    if market.last_funding_update:
        next_funding_time = market.last_funding_update + timedelta(
            seconds=market.funding_rate_interval
        )

    now = datetime.now(timezone.utc)
    target_time = now - timedelta(hours=24)

    stmt_24h = (
        select(PriceHistoryModel)
        .where(
            PriceHistoryModel.market_id == market_id,
            PriceHistoryModel.timestamp <= target_time,
        )
        .order_by(PriceHistoryModel.timestamp.desc())
        .limit(1)
    )

    result_24h = await db.execute(stmt_24h)
    price_24h_tick = result_24h.scalar_one_or_none()

    price_change_24h: None | Decimal = None
    price_change_percent_24h: None | Decimal = None

    if mark_price is not None and price_24h_tick:
        price_24h_ago = price_24h_tick.price
        if price_24h_ago and price_24h_ago > 0:
            price_change_24h = mark_price - price_24h_ago
            price_change_percent_24h = (price_change_24h / price_24h_ago) * Decimal(
                "100"
            )
    volume_data = await volume_aggregator.get_24h_volume(market_id)
    # Build stats
    stats = MarketStats(
        market_id=market.market_id,
        symbol=market.symbol,
        collateral_in=build_collateral_in(market.quote_token),
        mark_price=mark_price,
        index_price=mark_price,  # Could be different in production
        price_24h_change=price_change_percent_24h,
        total_long_oi=market.total_long_positions,
        total_short_oi=market.total_short_positions,
        total_oi=market.total_long_positions + market.total_short_positions,
        current_funding_rate=market.current_funding_rate,
        predicted_funding_rate=predicted_funding,
        next_funding_time=next_funding_time,
        volume_24h=volume_data.volume_24h,
    )

    return ResponseBase(
        success=True,
        data=stats,
    )


@router.get("/{market_id}/funding-history", response_model=ResponseBase[List[dict]])
async def get_funding_history(
    market_id: str,
    hours: int = Query(24, ge=1, le=168),
    db: AsyncSession = Depends(get_db),
):
    """
    Get funding rate history for a market.

    Args:
        market_id: Market identifier
        hours: Number of hours of history (max 168 = 1 week)
        db: Database session
    """
    history = await funding_service.get_funding_rate_history(market_id, hours)

    return ResponseBase(
        success=True,
        data=history,
    )

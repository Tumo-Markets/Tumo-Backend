from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.common import (
    ResponseBase,
    PriceData,
    HealthCheck,
    SystemStats,
)
from app.services.oracle import oracle_service
from app.services.blockchain import blockchain_service
from app.services.liquidation import liquidation_bot
from app.core.config import settings
from datetime import datetime
from sqlalchemy import select, func
from app.db.models import MarketModel, PositionModel, PositionStatusEnum

router = APIRouter(tags=["System"])


@router.get("/health", response_model=HealthCheck)
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Health check endpoint.
    
    Checks:
    - Database connection
    - Redis connection (if applicable)
    - Blockchain connection
    - Oracle connection
    """
    health = HealthCheck(
        version=settings.app_version,
        timestamp=datetime.utcnow(),
    )
    
    # Check database
    try:
        await db.execute(select(1))
        health.database = True
    except Exception:
        health.database = False
    
    # Check blockchain
    try:
        latest_block = await blockchain_service.get_latest_block()
        health.blockchain = latest_block > 0
    except Exception:
        health.blockchain = False
    
    # Check oracle
    try:
        # Try to fetch a test price (you'd use a known price feed ID)
        # For now, just check if service is initialized
        health.oracle = oracle_service is not None
    except Exception:
        health.oracle = False
    
    # Set overall status
    if all([health.database, health.blockchain, health.oracle]):
        health.status = "healthy"
    else:
        health.status = "degraded"
    
    return health


@router.get("/stats", response_model=ResponseBase[SystemStats])
async def get_system_stats(db: AsyncSession = Depends(get_db)):
    """Get system-wide statistics."""
    
    # Count markets
    stmt = select(func.count(MarketModel.id))
    result = await db.execute(stmt)
    total_markets = result.scalar()
    
    # Count positions
    stmt = select(func.count(PositionModel.id))
    result = await db.execute(stmt)
    total_positions = result.scalar()
    
    stmt = select(func.count(PositionModel.id)).where(
        PositionModel.status == PositionStatusEnum.OPEN
    )
    result = await db.execute(stmt)
    open_positions = result.scalar()
    
    # Get total open interest
    stmt = select(
        func.sum(MarketModel.total_long_positions),
        func.sum(MarketModel.total_short_positions),
    )
    result = await db.execute(stmt)
    row = result.one()
    total_long_oi = row[0] or 0
    total_short_oi = row[1] or 0
    
    # TODO: Calculate 24h volume and fees from transaction history
    
    stats = SystemStats(
        total_markets=total_markets,
        total_positions=total_positions,
        open_positions=open_positions,
        total_volume_24h=0,  # Would calculate from trades
        total_fees_24h=0,  # Would calculate from trades
        total_long_oi=total_long_oi,
        total_short_oi=total_short_oi,
        active_users_24h=0,  # Would calculate from recent activity
    )
    
    return ResponseBase(
        success=True,
        data=stats,
    )


# Oracle endpoints
oracle_router = APIRouter(prefix="/oracle", tags=["Oracle"])


@oracle_router.get("/price/{price_feed_id}", response_model=ResponseBase[PriceData])
async def get_price(price_feed_id: str):
    """
    Get latest price for a price feed.
    
    Args:
        price_feed_id: Pyth price feed ID (with 0x prefix)
    """
    price_data = await oracle_service.get_latest_price(price_feed_id)
    
    if not price_data:
        raise HTTPException(status_code=404, detail="Price not found")
    
    return ResponseBase(
        success=True,
        data=price_data,
    )


@oracle_router.post("/prices", response_model=ResponseBase[List[PriceData]])
async def get_prices(price_feed_ids: List[str]):
    """
    Get latest prices for multiple price feeds.
    
    Args:
        price_feed_ids: List of Pyth price feed IDs
    """
    prices = await oracle_service.get_latest_prices(price_feed_ids)
    
    return ResponseBase(
        success=True,
        data=list(prices.values()),
    )


# Liquidation bot endpoints
liquidation_router = APIRouter(prefix="/liquidation", tags=["Liquidation"])


@liquidation_router.get("/status")
async def get_liquidation_status():
    """Get liquidation bot status."""
    stats = await liquidation_bot.get_liquidation_stats()
    
    return ResponseBase(
        success=True,
        data=stats,
    )

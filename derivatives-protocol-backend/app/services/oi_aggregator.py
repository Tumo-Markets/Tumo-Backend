"""
Open Interest Aggregator Service

Background service to snapshot Open Interest data.
Runs every hour to record long/short OI for all markets.
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from loguru import logger

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.db.models import MarketModel
from app.db.chart_models import OISnapshotModel


class OIAggregator:
    """
    Aggregates Open Interest data for market depth analysis.
    
    Creates hourly snapshots of total long OI and total short OI
    for all active markets.
    """
    
    def __init__(self):
        self.is_running = False
    
    async def start(self):
        """Start the OI aggregator service."""
        self.is_running = True
        logger.info("📊 OI aggregator started")
        
        while self.is_running:
            try:
                await self._aggregate_all_markets()
                
                # Run every hour
                await asyncio.sleep(3600)
                
            except Exception as e:
                logger.error(f"Error in OI aggregator: {e}")
                await asyncio.sleep(3600)
    
    async def stop(self):
        """Stop the OI aggregator."""
        self.is_running = False
        logger.info("OI aggregator stopped")
    
    async def _aggregate_all_markets(self):
        """Aggregate OI snapshots for all markets."""
        async with AsyncSessionLocal() as db:
            try:
                # Get all active markets
                stmt = select(MarketModel).where(MarketModel.status == "active")
                result = await db.execute(stmt)
                markets = result.scalars().all()
                
                if not markets:
                    logger.debug("No active markets found")
                    return
                
                logger.info(f"Creating OI snapshots for {len(markets)} markets")
                
                # Create snapshot for each market
                for market in markets:
                    try:
                        await self._create_oi_snapshot(db, market)
                    except Exception as e:
                        logger.error(
                            f"Error creating OI snapshot for {market.market_id}: {e}"
                        )
                
                await db.commit()
                logger.info(f"Created {len(markets)} OI snapshots")
                
            except Exception as e:
                logger.error(f"Error in aggregate_all_markets: {e}")
                await db.rollback()
    
    async def _create_oi_snapshot(
        self,
        db: AsyncSession,
        market: MarketModel
    ):
        """Create OI snapshot for a single market."""
        # Get current OI values from market
        total_long_oi = market.total_long_positions
        total_short_oi = market.total_short_positions
        total_oi = total_long_oi + total_short_oi
        
        # Calculate long/short ratio
        if total_short_oi > 0:
            long_short_ratio = total_long_oi / total_short_oi
        else:
            long_short_ratio = Decimal("0") if total_long_oi == 0 else Decimal("999")
        
        # Create snapshot
        snapshot = OISnapshotModel(
            market_id=market.market_id,
            timestamp=datetime.utcnow(),
            total_long_oi=total_long_oi,
            total_short_oi=total_short_oi,
            total_oi=total_oi,
            long_short_ratio=long_short_ratio
        )
        
        db.add(snapshot)
        
        logger.debug(
            f"OI snapshot for {market.market_id}: "
            f"long={total_long_oi}, short={total_short_oi}, "
            f"ratio={long_short_ratio}"
        )
    
    async def cleanup_old_snapshots(self):
        """
        Delete old OI snapshots.
        
        Retention policy: 90 days (3 months)
        """
        async with AsyncSessionLocal() as db:
            cutoff_date = datetime.utcnow() - timedelta(days=90)
            
            from sqlalchemy import delete
            
            stmt = delete(OISnapshotModel).where(
                OISnapshotModel.timestamp < cutoff_date
            )
            
            result = await db.execute(stmt)
            await db.commit()
            
            if result.rowcount > 0:
                logger.info(
                    f"Deleted {result.rowcount} old OI snapshots "
                    f"(older than 90 days)"
                )


# Global instance
oi_aggregator = OIAggregator()

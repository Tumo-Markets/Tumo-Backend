"""
PnL Calculator Service

Background service to calculate and store PnL snapshots.
Runs every hour to snapshot all active users' portfolio performance.
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from loguru import logger

from sqlalchemy import select, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.db.models import PositionModel, MarketModel, PositionStatusEnum
from app.db.chart_models import PnLSnapshotModel
from app.services.oracle import oracle_service


class PnLCalculator:
    """
    Calculates PnL snapshots for portfolio performance tracking.
    
    Creates hourly snapshots of total PnL, unrealized PnL, and realized PnL
    for all users with open positions.
    """
    
    def __init__(self):
        self.is_running = False
    
    async def start(self):
        """Start the PnL calculator service."""
        self.is_running = True
        logger.info("💰 PnL calculator started")
        
        while self.is_running:
            try:
                await self._calculate_all_snapshots()
                
                # Run every hour
                await asyncio.sleep(3600)
                
            except Exception as e:
                logger.error(f"Error in PnL calculator: {e}")
                await asyncio.sleep(3600)
    
    async def stop(self):
        """Stop the PnL calculator."""
        self.is_running = False
        logger.info("PnL calculator stopped")
    
    async def _calculate_all_snapshots(self):
        """Calculate PnL snapshots for all users with open positions."""
        async with AsyncSessionLocal() as db:
            try:
                # Get all unique users with open positions
                stmt = (
                    select(distinct(PositionModel.user_address))
                    .where(PositionModel.status == PositionStatusEnum.OPEN)
                )
                result = await db.execute(stmt)
                user_addresses = [row[0] for row in result.all()]
                
                if not user_addresses:
                    logger.debug("No users with open positions")
                    return
                
                logger.info(f"Calculating PnL snapshots for {len(user_addresses)} users")
                
                # Calculate snapshot for each user
                for user_address in user_addresses:
                    try:
                        await self._calculate_user_snapshot(db, user_address)
                    except Exception as e:
                        logger.error(f"Error calculating PnL for {user_address}: {e}")
                
                await db.commit()
                logger.info(f"Created {len(user_addresses)} PnL snapshots")
                
            except Exception as e:
                logger.error(f"Error in calculate_all_snapshots: {e}")
                await db.rollback()
    
    async def _calculate_user_snapshot(
        self,
        db: AsyncSession,
        user_address: str
    ):
        """Calculate PnL snapshot for a single user."""
        # Get user's open positions with markets
        stmt = (
            select(PositionModel, MarketModel)
            .join(MarketModel, PositionModel.market_id == MarketModel.market_id)
            .where(
                PositionModel.user_address == user_address,
                PositionModel.status == PositionStatusEnum.OPEN
            )
        )
        result = await db.execute(stmt)
        positions = result.all()
        
        if not positions:
            return
        
        # Get current prices for all markets
        price_feed_ids = list(set(m.pyth_price_id for _, m in positions))
        prices = await oracle_service.get_latest_prices(price_feed_ids)
        
        # Calculate totals
        total_collateral = Decimal("0")
        total_unrealized_pnl = Decimal("0")
        total_realized_pnl = Decimal("0")
        total_position_value = Decimal("0")
        
        for row in positions:
            position: PositionModel
            market: MarketModel
            position, market = row
            
            # Accumulate collateral and realized PnL
            total_collateral += position.collateral
            total_realized_pnl += position.realized_pnl
            
            # Get current price
            price_data = prices.get(market.pyth_price_id)
            if not price_data:
                logger.warning(
                    f"No price data for {market.market_id} "
                    f"(position {position.position_id})"
                )
                continue
            
            current_price = price_data.normalized_price
            
            # Calculate unrealized PnL
            if position.side.value == "long":
                pnl = position.size * (current_price - position.entry_price)
            else:
                pnl = position.size * (position.entry_price - current_price)
            
            total_unrealized_pnl += pnl
            
            # Calculate position value
            total_position_value += position.size * current_price
        
        total_pnl = total_unrealized_pnl + total_realized_pnl
        
        # Create snapshot
        snapshot = PnLSnapshotModel(
            user_address=user_address,
            timestamp=datetime.utcnow(),
            total_pnl=total_pnl,
            unrealized_pnl=total_unrealized_pnl,
            realized_pnl=total_realized_pnl,
            total_collateral=total_collateral,
            total_position_value=total_position_value,
            open_positions_count=len(positions)
        )
        
        db.add(snapshot)
        
        logger.debug(
            f"PnL snapshot for {user_address}: "
            f"total={total_pnl}, unrealized={total_unrealized_pnl}, "
            f"realized={total_realized_pnl}"
        )
    
    async def cleanup_old_snapshots(self):
        """
        Delete old PnL snapshots.
        
        Retention policy: 365 days (1 year)
        """
        async with AsyncSessionLocal() as db:
            cutoff_date = datetime.utcnow() - timedelta(days=365)
            
            from sqlalchemy import delete
            
            stmt = delete(PnLSnapshotModel).where(
                PnLSnapshotModel.timestamp < cutoff_date
            )
            
            result = await db.execute(stmt)
            await db.commit()
            
            if result.rowcount > 0:
                logger.info(
                    f"Deleted {result.rowcount} old PnL snapshots "
                    f"(older than 365 days)"
                )


# Global instance
pnl_calculator = PnLCalculator()

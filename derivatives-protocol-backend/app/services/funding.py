import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import FundingRateModel, MarketModel
from app.db.session import AsyncSessionLocal
from app.services.broadcaster import broadcaster


class FundingRateService:
    """
    Service for calculating and updating funding rates.

    Funding rate helps balance long/short positions by making one side pay the other.
    """

    def __init__(self):
        self.is_running = False
        self.update_interval = settings.funding_interval
        self.max_funding_rate = settings.funding_rate_cap

    async def start(self):
        """Start the funding rate updater."""
        self.is_running = True
        logger.info("Starting funding rate service...")

        while self.is_running:
            try:
                await self._update_funding_rates()
                await asyncio.sleep(self.update_interval)
            except Exception as e:
                logger.error(f"Error in funding rate loop: {e}")
                await asyncio.sleep(self.update_interval)

    async def stop(self):
        """Stop the funding rate updater."""
        self.is_running = False
        logger.info("Stopping funding rate service...")

    async def _update_funding_rates(self):
        """Update funding rates for all markets."""
        async with AsyncSessionLocal() as db:
            # Get all active markets
            stmt = select(MarketModel).where(MarketModel.status == "active")
            result = await db.execute(stmt)
            markets = result.scalars().all()

            for market in markets:
                try:
                    await self._update_market_funding_rate(db, market)
                except Exception as e:
                    logger.error(
                        f"Error updating funding rate for {market.market_id}: {e}"
                    )

            await db.commit()

    async def _update_market_funding_rate(self, db: AsyncSession, market: MarketModel):
        """
        Update funding rate for a specific market.

        Args:
            db: Database session
            market: Market model
        """
        # Check if it's time to update
        if market.last_funding_update:
            time_since_update = datetime.now(timezone.utc) - market.last_funding_update
            if time_since_update.total_seconds() < market.funding_rate_interval:
                return

        # Calculate funding rate based on open interest imbalance
        funding_rate = self._calculate_funding_rate(
            long_oi=market.total_long_positions,
            short_oi=market.total_short_positions,
            max_rate=market.max_funding_rate,
        )

        # Update market
        market.current_funding_rate = funding_rate
        market.last_funding_update = datetime.now(timezone.utc)

        # Record funding rate history
        funding_record = FundingRateModel(
            market_id=market.market_id,
            funding_rate=funding_rate,
            long_oi=market.total_long_positions,
            short_oi=market.total_short_positions,
        )
        db.add(funding_record)

        logger.info(
            f"Updated funding rate for {market.symbol}: {funding_rate:.6f} "
            f"(Long OI: {market.total_long_positions}, Short OI: {market.total_short_positions})"
        )

        # Broadcast funding rate update via WebSocket
        await broadcaster.broadcast_funding_rate_update(
            market_id=market.market_id,
            funding_rate=str(funding_rate),
            long_oi=str(market.total_long_positions),
            short_oi=str(market.total_short_positions),
        )

        # In a real implementation, you would also trigger an on-chain transaction
        # to update funding rates in the smart contract

    def _calculate_funding_rate(
        self,
        long_oi: Decimal,
        short_oi: Decimal,
        max_rate: Decimal,
    ) -> Decimal:
        """
        Calculate funding rate based on open interest imbalance.

        Formula:
        - If long_oi > short_oi: Longs pay shorts (positive rate)
        - If short_oi > long_oi: Shorts pay longs (negative rate)
        - Rate = (long_oi - short_oi) / (long_oi + short_oi) * max_rate

        Args:
            long_oi: Total long open interest
            short_oi: Total short open interest
            max_rate: Maximum funding rate cap

        Returns:
            Funding rate (capped at max_rate)
        """
        total_oi = long_oi + short_oi

        # No open interest
        if total_oi == 0:
            return Decimal("0")

        # Calculate imbalance ratio
        imbalance = (long_oi - short_oi) / total_oi

        # Calculate funding rate
        funding_rate = imbalance * max_rate

        # Cap at max rate
        funding_rate = max(min(funding_rate, max_rate), -max_rate)

        return funding_rate

    async def get_funding_rate_history(
        self,
        market_id: str,
        hours: int = 24,
    ) -> list:
        """
        Get funding rate history for a market.

        Args:
            market_id: Market identifier
            hours: Number of hours of history

        Returns:
            List of funding rate records
        """
        async with AsyncSessionLocal() as db:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

            stmt = (
                select(FundingRateModel)
                .where(
                    FundingRateModel.market_id == market_id,
                    FundingRateModel.timestamp >= cutoff_time,
                )
                .order_by(FundingRateModel.timestamp.desc())
            )

            result = await db.execute(stmt)
            records = result.scalars().all()

            return [
                {
                    "timestamp": r.timestamp,
                    "funding_rate": float(r.funding_rate),
                    "long_oi": float(r.long_oi),
                    "short_oi": float(r.short_oi),
                }
                for r in records
            ]

    async def predict_next_funding_rate(self, market_id: str) -> Optional[Decimal]:
        """
        Predict next funding rate based on current open interest.

        Args:
            market_id: Market identifier

        Returns:
            Predicted funding rate or None
        """
        async with AsyncSessionLocal() as db:
            stmt = select(MarketModel).where(MarketModel.market_id == market_id)
            result = await db.execute(stmt)
            market = result.scalar_one_or_none()

            if not market:
                return None

            return self._calculate_funding_rate(
                long_oi=market.total_long_positions,
                short_oi=market.total_short_positions,
                max_rate=market.max_funding_rate,
            )

    def calculate_funding_payment(
        self,
        position_size: Decimal,
        funding_rate: Decimal,
        is_long: bool,
    ) -> Decimal:
        """
        Calculate funding payment for a position.

        Args:
            position_size: Position size in base token
            funding_rate: Current funding rate
            is_long: True if long position

        Returns:
            Funding payment (positive = pay, negative = receive)
        """
        # Longs pay when funding rate is positive
        # Shorts pay when funding rate is negative
        if is_long:
            payment = position_size * funding_rate
        else:
            payment = -position_size * funding_rate

        return payment


# Global funding rate service instance
funding_service = FundingRateService()

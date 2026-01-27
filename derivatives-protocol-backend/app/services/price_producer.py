import asyncio
from datetime import datetime

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MarketModel, PriceHistoryModel
from app.db.session import AsyncSessionLocal
from app.services.oracle import oracle_service


class PriceProducerService:
    """
    Price Producer

    - Fetch price from Pyth Oracle
    - Store tick data into price_history
    - Run continuously
    """

    def __init__(self, interval_seconds: int = 2):
        self.interval = interval_seconds
        self.is_running = False

    async def start(self):
        self.is_running = True
        logger.info("🚀 Price Producer started")

        while self.is_running:
            try:
                await self._produce_once()
                await asyncio.sleep(self.interval)
            except Exception as e:
                logger.error(f"Price producer error: {e}")
                await asyncio.sleep(self.interval)

    async def stop(self):
        self.is_running = False
        logger.info("🛑 Price Producer stopped")

    async def _produce_once(self):
        async with AsyncSessionLocal() as db:
            stmt = select(MarketModel).where(MarketModel.status == "active")
            result = await db.execute(stmt)
            markets = result.scalars().all()

            for market in markets:
                await self._produce_market_price(db, market)

            await db.commit()

    async def _produce_market_price(
        self,
        db: AsyncSession,
        market: MarketModel,
    ):
        """
        Fetch price from oracle and store tick
        """

        price_data = await oracle_service.get_latest_price(market.pyth_price_id)

        if not price_data:
            logger.warning(f"No price for market {market.market_id}")
            return

        # 🔒 Optional: freshness & confidence check
        if not oracle_service.is_price_fresh(price_data, max_age_seconds=10):
            logger.warning(f"Stale price for {market.market_id}")
            return

        if not oracle_service.is_price_confident(price_data):
            logger.warning(f"Low confidence price for {market.market_id}")
            return

        # 🧠 Skip duplicate price
        last_tick = await db.execute(
            select(PriceHistoryModel)
            .where(PriceHistoryModel.market_id == market.market_id)
            .order_by(PriceHistoryModel.timestamp.desc())
            .limit(1)
        )
        last_tick = last_tick.scalar_one_or_none()
        normalized_price = price_data.normalized_price

        if last_tick and last_tick.price == normalized_price:
            return

        tick = PriceHistoryModel(
            market_id=market.market_id,
            price=normalized_price,
            confidence=price_data.confidence,
            timestamp=datetime.utcnow(),
        )

        db.add(tick)

        logger.debug(
            f"[{market.market_id}] tick={price_data.price} conf={price_data.confidence}"
        )


# Global instance
price_producer = PriceProducerService()

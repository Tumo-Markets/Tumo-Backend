import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.chart_models import PriceOHLCVModel
from app.db.models import MarketModel, PriceHistoryModel
from app.db.session import AsyncSessionLocal


class PriceAggregator:
    """
    Aggregates price history into OHLCV candles.

    Rules:
    - 1m candles are built from PriceHistory (ticks)
    - Higher timeframes are built strictly from 1m candles
    - All timestamps are UTC-aligned
    """

    def __init__(self):
        self.is_running: bool = False

        self.timeframes: dict[str, int] = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "1h": 60,
            "4h": 240,
            "1d": 1440,
            "1w": 10080,
        }

    async def start(self):
        self.is_running = True
        logger.info("📊 Price aggregator started")

        while self.is_running:
            try:
                await self._aggregate_all_markets()
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Aggregator error: {e}")
                await asyncio.sleep(60)

    async def _aggregate_all_markets(self):
        async with AsyncSessionLocal() as db:
            markets = (
                (
                    await db.execute(
                        select(MarketModel).where(MarketModel.status == "active")
                    )
                )
                .scalars()
                .all()
            )

            for market in markets:
                await self._build_1m_candle(db, market.market_id)

                for tf, minutes in self.timeframes.items():
                    if tf == "1m":
                        continue
                    await self._build_higher_tf(db, market.market_id, tf, minutes)

            await db.commit()

    # ===============================
    # 1️⃣ BUILD 1M FROM TICKS
    # ===============================

    async def _build_1m_candle(self, db: AsyncSession, market_id: str):
        now = datetime.utcnow()
        end_time = now.replace(second=0, microsecond=0)
        start_time = end_time - timedelta(minutes=1)

        ticks = (
            (
                await db.execute(
                    select(PriceHistoryModel)
                    .where(
                        PriceHistoryModel.market_id == market_id,
                        PriceHistoryModel.timestamp >= start_time,
                        PriceHistoryModel.timestamp < end_time,
                    )
                    .order_by(PriceHistoryModel.timestamp)
                )
            )
            .scalars()
            .all()
        )

        if not ticks:
            return

        exists = (
            await db.execute(
                select(PriceOHLCVModel).where(
                    PriceOHLCVModel.market_id == market_id,
                    PriceOHLCVModel.timeframe == "1m",
                    PriceOHLCVModel.timestamp == end_time,
                )
            )
        ).scalar_one_or_none()

        if exists:
            return

        candle = PriceOHLCVModel(
            market_id=market_id,
            timeframe="1m",
            timestamp=end_time,
            open=ticks[0].price,
            high=max(t.price for t in ticks),
            low=min(t.price for t in ticks),
            close=ticks[-1].price,
            volume=Decimal("0"),
        )

        db.add(candle)

    # ===================================
    # 2️⃣ BUILD HIGHER TF FROM 1M
    # ===================================

    async def _build_higher_tf(
        self,
        db: AsyncSession,
        market_id: str,
        timeframe: str,
        minutes: int,
    ):
        now = datetime.utcnow()
        end_time = self._align_tf_end(now, timeframe)
        start_time = end_time - timedelta(minutes=minutes)

        candles_1m = (
            (
                await db.execute(
                    select(PriceOHLCVModel)
                    .where(
                        PriceOHLCVModel.market_id == market_id,
                        PriceOHLCVModel.timeframe == "1m",
                        PriceOHLCVModel.timestamp >= start_time,
                        PriceOHLCVModel.timestamp < end_time,
                    )
                    .order_by(PriceOHLCVModel.timestamp)
                )
            )
            .scalars()
            .all()
        )

        if not candles_1m:
            return

        exists = (
            await db.execute(
                select(PriceOHLCVModel).where(
                    PriceOHLCVModel.market_id == market_id,
                    PriceOHLCVModel.timeframe == timeframe,
                    PriceOHLCVModel.timestamp == end_time,
                )
            )
        ).scalar_one_or_none()

        if exists:
            return

        candle = PriceOHLCVModel(
            market_id=market_id,
            timeframe=timeframe,
            timestamp=end_time,
            open=candles_1m[0].open,
            high=max(c.high for c in candles_1m),
            low=min(c.low for c in candles_1m),
            close=candles_1m[-1].close,
            volume=sum(c.volume for c in candles_1m),
        )

        db.add(candle)

    # ===============================
    # TIME ALIGNMENT (CORE LOGIC)
    # ===============================

    def _align_tf_end(self, dt: datetime, timeframe: str) -> datetime:
        """
        Align datetime to candle CLOSE time (UTC).
        Example:
        - 12:03 -> 12:00 for 5m
        - 12:17 -> 12:15 for 15m
        - 12:59 -> 12:00 for 1h
        """
        dt = dt.replace(second=0, microsecond=0)

        if timeframe == "1m":
            return dt

        if timeframe == "5m":
            m = (dt.minute // 5) * 5
            return dt.replace(minute=m)

        if timeframe == "15m":
            m = (dt.minute // 15) * 15
            return dt.replace(minute=m)

        if timeframe == "1h":
            return dt.replace(minute=0)

        if timeframe == "4h":
            h = (dt.hour // 4) * 4
            return dt.replace(hour=h, minute=0)

        if timeframe == "1d":
            return dt.replace(hour=0, minute=0)

        if timeframe == "1w":
            # ISO week: Monday 00:00 UTC
            monday = dt - timedelta(days=dt.weekday())
            return monday.replace(hour=0, minute=0)

        raise ValueError(f"Unsupported timeframe: {timeframe}")


price_aggregator = PriceAggregator()

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

from loguru import logger
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.chart_models import VolumeSnapshotModel
from app.db.models import (
    MarketModel,
    PositionModel,
    PositionStatusEnum,
)
from app.db.session import AsyncSessionLocal
from app.schemas.volume import (
    Volume24hData,
    VolumeHistoryItem,
    VolumeStats,
)


class VolumeAggregator:
    def __init__(self) -> None:
        self._running: bool = False
        self._current_hour_cache: dict[str, VolumeStats] = {}

    # ======================================================================
    # SERVICE LOOP
    # ======================================================================

    async def start(self) -> None:
        self._running = True
        logger.info("📊 Volume Aggregator started")

        _ = await asyncio.gather(
            self._hourly_snapshot_loop(),
            self._current_hour_loop(),
        )

    async def stop(self) -> None:
        self._running = False
        logger.info("Volume Aggregator stopped")

    # ======================================================================
    # SNAPSHOT CREATION
    # ======================================================================

    async def _create_previous_hour_snapshots(self) -> None:
        async with AsyncSessionLocal() as db:
            now = datetime.utcnow()
            hour_end = now.replace(minute=0, second=0, microsecond=0)
            hour_start = hour_end - timedelta(hours=1)

            markets = (
                (
                    await db.execute(
                        select(MarketModel.market_id).where(
                            MarketModel.status == "active"
                        )
                    )
                )
                .scalars()
                .all()
            )

            for market_id in markets:
                await self._create_snapshot_for_market(db, market_id, hour_start)

            await db.commit()

    async def _create_snapshot_for_market(
        self,
        db: AsyncSession,
        market_id: str,
        hour_start: datetime,
    ) -> None:
        exists = (
            await db.execute(
                select(VolumeSnapshotModel.id).where(
                    VolumeSnapshotModel.market_id == market_id,
                    VolumeSnapshotModel.timestamp == hour_start,
                )
            )
        ).scalar_one_or_none()

        if exists:
            return

        hour_end = hour_start + timedelta(hours=1)

        open_volume, open_trades = await self._aggregate_volume(
            db,
            market_id,
            PositionModel.created_at,
            hour_start,
            hour_end,
            None,
        )

        close_volume, close_trades = await self._aggregate_volume(
            db,
            market_id,
            PositionModel.closed_at,
            hour_start,
            hour_end,
            [PositionStatusEnum.CLOSED, PositionStatusEnum.LIQUIDATED],
        )

        snapshot = VolumeSnapshotModel(
            market_id=market_id,
            timestamp=hour_start,
            open_volume=open_volume,
            close_volume=close_volume,
            total_volume=open_volume + close_volume,
            open_trades=open_trades,
            close_trades=close_trades,
            total_trades=open_trades + close_trades,
        )

        db.add(snapshot)

    # ======================================================================
    # CURRENT HOUR (FORMING)
    # ======================================================================

    async def _update_current_hour_cache(self) -> None:
        async with AsyncSessionLocal() as db:
            now = datetime.utcnow()
            hour_start = now.replace(minute=0, second=0, microsecond=0)

            markets = (
                (
                    await db.execute(
                        select(MarketModel.market_id).where(
                            MarketModel.status == "active"
                        )
                    )
                )
                .scalars()
                .all()
            )

            for market_id in markets:
                open_volume, open_trades = await self._aggregate_volume(
                    db,
                    market_id,
                    PositionModel.created_at,
                    hour_start,
                    now,
                    None,
                )

                close_volume, close_trades = await self._aggregate_volume(
                    db,
                    market_id,
                    PositionModel.closed_at,
                    hour_start,
                    now,
                    [PositionStatusEnum.CLOSED, PositionStatusEnum.LIQUIDATED],
                )

                self._current_hour_cache[market_id] = VolumeStats(
                    open_volume=open_volume,
                    close_volume=close_volume,
                    total_volume=open_volume + close_volume,
                    open_trades=open_trades,
                    close_trades=close_trades,
                    total_trades=open_trades + close_trades,
                )

    # ======================================================================
    # SHARED AGGREGATION LOGIC
    # ======================================================================

    async def _aggregate_volume(
        self,
        db: AsyncSession,
        market_id: str,
        time_field,
        start: datetime,
        end: datetime,
        statuses: list[PositionStatusEnum] | None,
    ) -> tuple[Decimal, int]:
        stmt = select(
            func.coalesce(
                func.sum(func.abs(PositionModel.size) * PositionModel.entry_price), 0
            ),
            func.count(PositionModel.id),
        ).where(
            PositionModel.market_id == market_id,
            time_field >= start,
            time_field < end,
        )

        if statuses:
            stmt = stmt.where(PositionModel.status.in_(statuses))

        row = (await db.execute(stmt)).one()
        volume_raw, count = row

        return Decimal(str(volume_raw)), count

    # ======================================================================
    # PUBLIC API METHODS
    # ======================================================================

    async def get_24h_volume(self, market_id: str) -> Volume24hData:
        async with AsyncSessionLocal() as db:
            now = datetime.utcnow()
            since = now - timedelta(hours=24)

            snapshots = (
                (
                    await db.execute(
                        select(VolumeSnapshotModel).where(
                            VolumeSnapshotModel.market_id == market_id,
                            VolumeSnapshotModel.timestamp >= since,
                        )
                    )
                )
                .scalars()
                .all()
            )

            total = sum(s.total_volume for s in snapshots)
            open_v = sum(s.open_volume for s in snapshots)
            close_v = sum(s.close_volume for s in snapshots)
            trades = sum(s.total_trades for s in snapshots)

            current = self._current_hour_cache.get(market_id, VolumeStats())

            return Volume24hData(
                market_id=market_id,
                volume_24h=total + current.total_volume,
                open_volume_24h=open_v + current.open_volume,
                close_volume_24h=close_v + current.close_volume,
                trades_24h=trades + current.total_trades,
                current_hour_volume=current.total_volume,
                timestamp=now,
            )

    async def get_volume_history(
        self,
        market_id: str,
        hours: int = 24,
    ) -> list[VolumeHistoryItem]:
        async with AsyncSessionLocal() as db:
            since = datetime.utcnow() - timedelta(hours=min(hours, 168))

            rows = (
                (
                    await db.execute(
                        select(VolumeSnapshotModel)
                        .where(
                            VolumeSnapshotModel.market_id == market_id,
                            VolumeSnapshotModel.timestamp >= since,
                        )
                        .order_by(VolumeSnapshotModel.timestamp)
                    )
                )
                .scalars()
                .all()
            )

            return [
                VolumeHistoryItem(
                    timestamp=r.timestamp,
                    open_volume=r.open_volume,
                    close_volume=r.close_volume,
                    total_volume=r.total_volume,
                    open_trades=r.open_trades,
                    close_trades=r.close_trades,
                    total_trades=r.total_trades,
                )
                for r in rows
            ]

    async def cleanup(self, days: int = 90) -> None:
        async with AsyncSessionLocal() as db:
            cutoff = datetime.utcnow() - timedelta(days=days)
            _ = await db.execute(
                delete(VolumeSnapshotModel).where(
                    VolumeSnapshotModel.timestamp < cutoff
                )
            )
            await db.commit()

    async def get_all_24h_volumes_bulk(self) -> dict[str, Volume24hData]:
        async with AsyncSessionLocal() as db:
            now = datetime.utcnow()
            since = now - timedelta(hours=24)

            rows = (
                await db.execute(
                    select(
                        VolumeSnapshotModel.market_id,
                        func.coalesce(func.sum(VolumeSnapshotModel.total_volume), 0),
                        func.coalesce(func.sum(VolumeSnapshotModel.open_volume), 0),
                        func.coalesce(func.sum(VolumeSnapshotModel.close_volume), 0),
                        func.coalesce(func.sum(VolumeSnapshotModel.total_trades), 0),
                    )
                    .where(VolumeSnapshotModel.timestamp >= since)
                    .group_by(VolumeSnapshotModel.market_id)
                )
            ).all()

            result: dict[str, Volume24hData] = {}

            for (
                market_id,
                total_volume,
                open_volume,
                close_volume,
                trades,
            ) in rows:
                current = self._current_hour_cache.get(market_id, VolumeStats())

                result[market_id] = Volume24hData(
                    market_id=market_id,
                    volume_24h=Decimal(str(total_volume)) + current.total_volume,
                    open_volume_24h=Decimal(str(open_volume)) + current.open_volume,
                    close_volume_24h=Decimal(str(close_volume)) + current.close_volume,
                    trades_24h=trades + current.total_trades,
                    current_hour_volume=current.total_volume,
                    timestamp=now,
                )

            return result

    async def _hourly_snapshot_loop(self) -> None:
        while self._running:
            try:
                now = datetime.utcnow()
                next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(
                    hours=1
                )
                await asyncio.sleep((next_hour - now).total_seconds())

                await self._create_previous_hour_snapshots()
            except Exception:
                logger.exception("Hourly snapshot loop error")
                await asyncio.sleep(60)

    async def _current_hour_loop(self) -> None:
        while self._running:
            try:
                await self._update_current_hour_cache()
                await asyncio.sleep(10)
            except Exception:
                logger.exception("Current hour volume loop error")
                await asyncio.sleep(5)


volume_aggregator = VolumeAggregator()

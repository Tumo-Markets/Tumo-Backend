"""
Onechain Blockchain Indexer

Indexes events from Onechain (Move-based blockchain).
Type-safe implementation with zero Pyright warnings.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import (
    BlockSyncModel,
    LiquidationModel,
    MarketModel,
    PositionModel,
    PositionSideEnum,
    PositionStatusEnum,
)
from app.db.session import AsyncSessionLocal
from app.schemas.onechain import (
    OnechainEventData,
    PositionClosedEvent,
    PositionLiquidatedEvent,
    PositionUpdatedEvent,
)
from app.services.blockchain import blockchain_service as onechain_service
from app.services.notifications import (
    notify_position_closed,
    notify_position_liquidated,
    notify_position_opened,
)
from app.utils.calculations import calculate_liquidation_price


class BlockchainIndexer:
    """
    Indexes events from Onechain blockchain.

    Type-safe implementation for Move-based blockchain.
    """

    def __init__(self) -> None:
        self.is_running: bool = False
        self.batch_size: int = 1_000  # Checkpoints per batch
        self.poll_interval: int = 5  # seconds

        # Event type mappings
        self.event_types = {
            "position_opened": "tumo_markets_core::PositionOpened",
            "position_closed": "tumo_markets_core::PositionClosed",
            "position_liquidated": "tumo_markets_core::PositionLiquidated",
            "position_updated": "tumo_markets_core::PositionUpdated",
        }

    # ========================================================================
    # LIFECYCLE
    # ========================================================================

    async def start(self) -> None:
        """Start the indexer."""
        self.is_running = True
        logger.info("🔍 Onechain indexer started")

        while self.is_running:
            try:
                await self._sync_events()
            except Exception:
                logger.exception("Indexer loop error")

            await asyncio.sleep(self.poll_interval)

    async def stop(self) -> None:
        """Stop the indexer."""
        self.is_running = False
        logger.info("Onechain indexer stopped")

    # ========================================================================
    # SYNC LOGIC
    # ========================================================================

    async def _sync_events(self) -> None:
        """Sync events from blockchain."""
        async with AsyncSessionLocal() as db:
            last_checkpoint = await self._get_last_synced_checkpoint(db)
            current_checkpoint = await onechain_service.get_latest_checkpoint()

            if last_checkpoint >= current_checkpoint:
                return

            logger.info(
                f"Syncing checkpoints {last_checkpoint + 1} → {current_checkpoint}"
            )

            from_checkpoint = last_checkpoint + 1

            while from_checkpoint <= current_checkpoint:
                to_checkpoint = min(
                    from_checkpoint + self.batch_size - 1, current_checkpoint
                )

                try:
                    await self._process_checkpoint_range(
                        db, from_checkpoint, to_checkpoint
                    )

                    await self._update_last_synced_checkpoint(db, to_checkpoint)
                    await db.commit()

                except Exception:
                    await db.rollback()
                    raise

                from_checkpoint = to_checkpoint + 1

    async def _process_checkpoint_range(
        self,
        db: AsyncSession,
        from_checkpoint: int,
        to_checkpoint: int,
    ) -> None:
        """
        Process a range of checkpoints.

        Args:
            db: Database session
            from_checkpoint: Starting checkpoint
            to_checkpoint: Ending checkpoint
        """
        # Index each event type
        await self._index_position_opened(db, from_checkpoint, to_checkpoint)
        await self._index_position_closed(db, from_checkpoint, to_checkpoint)
        await self._index_liquidations(db, from_checkpoint, to_checkpoint)
        await self._index_position_updated(db, from_checkpoint, to_checkpoint)

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    async def _index_position_opened(
        self,
        db: AsyncSession,
        from_checkpoint: int,
        to_checkpoint: int,
    ) -> None:
        """
        Index PositionOpened events.
        """
        events: list[OnechainEventData] = await onechain_service.query_events(
            self.event_types["position_opened"],
            from_checkpoint,
            to_checkpoint,
        )
        logger.info(f"Found {len(events)} PositionOpened events")
        logger.debug(f"PositionOpened events onechain: {events}")

        indexed = 0

        for event in events:
            parsed = onechain_service.parse_position_opened_event(event)
            if not parsed:
                continue

            user_address = parsed.user.lower()
            position_id = parsed.position_id
            is_long = parsed.direction == 0

            leverage = (
                parsed.size / parsed.collateral
                if parsed.collateral > 0
                else Decimal("0")
            )

            # Check if position already exists
            exists = await db.execute(
                select(PositionModel).where(PositionModel.position_id == position_id)
            )

            if exists.scalar_one_or_none():
                continue

            position = PositionModel(
                position_id=position_id,
                user_address=user_address,
                market_id=parsed.market_id,
                side=PositionSideEnum.LONG if is_long else PositionSideEnum.SHORT,
                size=parsed.size,
                collateral=parsed.collateral,
                leverage=leverage,
                entry_price=parsed.entry_price,
                status=PositionStatusEnum.OPEN,
                transaction_hash=event.id.get("txDigest", ""),
                created_at=datetime.fromtimestamp(
                    parsed.timestamp / 1000, tz=timezone.utc
                ),
                block_number=1,
            )

            db.add(position)
            await db.flush()

            # Notify
            await self._send_position_opened_notification(position, event)

            # Update market stats
            await self._update_market_stats(
                db,
                parsed.market_id,
                parsed.size,
                is_long=is_long,
                add=True,
            )

            indexed += 1

        logger.info(f"Indexed {indexed} PositionOpened events")

    async def _index_position_closed(
        self,
        db: AsyncSession,
        from_checkpoint: int,
        to_checkpoint: int,
    ) -> None:
        """
        Index PositionClosed events.
        """
        events: list[OnechainEventData] = await onechain_service.query_events(
            self.event_types["position_closed"],
            from_checkpoint,
            to_checkpoint,
        )

        indexed = 0

        for event in events:
            parsed = onechain_service.parse_position_closed_event(event)
            if not parsed:
                continue

            user_address = parsed.user.lower()

            result = await db.execute(
                select(PositionModel).where(
                    PositionModel.position_id == parsed.position_id,
                    PositionModel.status == PositionStatusEnum.OPEN,
                )
            )

            position = result.scalar_one_or_none()

            if not position:
                logger.warning(
                    f"Open position not found for close: {parsed.market_id}:{user_address}"
                )
                continue

            # Update position
            position.status = PositionStatusEnum.CLOSED
            position.realized_pnl = parsed.pnl
            position.collateral_returned = parsed.collateral_returned
            position.close_transaction_hash = event.id.get("txDigest", "")
            position.closed_at = datetime.fromtimestamp(
                event.timestamp_ms / 1000, tz=timezone.utc
            )

            # Derive exit price
            if position.size > 0:
                position.exit_price = parsed.close_price

            await db.flush()
            # Notify
            await self._send_position_closed_notification(position, parsed, event)

            # Update market stats
            await self._update_market_stats(
                db,
                position.market_id,
                position.size,
                is_long=(position.side == PositionSideEnum.LONG),
                add=False,
            )

            indexed += 1

        logger.info(f"Indexed {indexed} PositionClosed events")

    async def _index_position_updated(
        self,
        db: AsyncSession,
        from_checkpoint: int,
        to_checkpoint: int,
    ) -> None:
        """
        Index PositionUpdated events.
        """
        events: list[OnechainEventData] = await onechain_service.query_events(
            self.event_types["position_updated"],
            from_checkpoint,
            to_checkpoint,
        )

        logger.info(f"Found {len(events)} PositionUpdated events")

        indexed = 0

        for event in events:
            parsed = onechain_service.parse_position_updated_event(event)
            if not parsed:
                continue

            user_address = parsed.user.lower()
            new_is_long = parsed.direction == 0

            result = await db.execute(
                select(PositionModel).where(
                    PositionModel.position_id == parsed.position_id,
                    PositionModel.status == PositionStatusEnum.OPEN,
                )
            )

            position = result.scalar_one_or_none()

            if not position:
                logger.error(
                    f"Open position not found for update: {parsed.position_id}"
                )
                continue

            old_size = position.size
            old_is_long = position.side == PositionSideEnum.LONG

            # Update core fields
            position.size = parsed.new_size
            position.collateral = parsed.new_collateral
            position.entry_price = parsed.new_entry_price
            position.side = (
                PositionSideEnum.LONG if new_is_long else PositionSideEnum.SHORT
            )

            # Recompute leverage
            position.leverage = (
                parsed.new_size / parsed.new_collateral
                if parsed.new_collateral > 0
                else Decimal("0")
            )

            position.updated_at = datetime.fromtimestamp(
                parsed.timestamp / 1000, tz=timezone.utc
            )

            await db.flush()

            await self._update_market_stats_on_position_update(
                db=db,
                market_id=parsed.market_id,
                old_size=old_size,
                new_size=parsed.new_size,
                old_is_long=old_is_long,
                new_is_long=new_is_long,
            )

            # Notify
            await self._send_position_updated_notification(position, parsed, event)

            indexed += 1

        logger.info(f"Indexed {indexed} PositionUpdated events")

    async def _index_liquidations(
        self,
        db: AsyncSession,
        from_checkpoint: int,
        to_checkpoint: int,
    ) -> None:
        """
        Index PositionLiquidated events.
        """
        events: list[OnechainEventData] = await onechain_service.query_events(
            self.event_types["position_liquidated"],
            from_checkpoint,
            to_checkpoint,
        )

        indexed = 0

        for event in events:
            parsed = onechain_service.parse_position_liquidated_event(event)
            if not parsed:
                continue

            # Get position
            position = (
                await db.execute(
                    select(PositionModel).where(
                        PositionModel.position_id == parsed.position_id
                    )
                )
            ).scalar_one_or_none()

            if not position:
                logger.warning(
                    f"Position {parsed.position_id} not found for liquidation"
                )
                continue

            # Get market (for fee calculation)
            market = (
                await db.execute(
                    select(MarketModel).where(MarketModel.market_id == parsed.market_id)
                )
            ).scalar_one_or_none()

            if not market:
                logger.warning(f"Market {parsed.market_id} not found for liquidation")
                continue

            # 🔹 Calculate liquidation fee off-chain
            liquidation_fee = position.collateral * market.liquidation_fee_rate

            # 🔹 Update position
            position.status = PositionStatusEnum.LIQUIDATED
            position.realized_pnl = parsed.pnl
            position.closed_at = datetime.fromtimestamp(
                parsed.timestamp / 1000, tz=timezone.utc
            )
            position.close_transaction_hash = event.id.get("txDigest", "")

            await db.flush()

            # 🔹 Create liquidation record
            liquidation = LiquidationModel(
                position_id=parsed.position_id,
                market_id=parsed.market_id,
                user_address=parsed.owner.lower(),
                liquidator_address=parsed.liquidator.lower(),
                liquidation_price=calculate_liquidation_price(
                    entry_price=position.entry_price,
                    leverage=position.leverage,
                    is_long=(position.side == PositionSideEnum.LONG),
                    maintenance_margin_rate=market.maintenance_margin_rate
                    if market
                    else Decimal("0.05"),
                ),
                collateral=parsed.collateral,
                liquidation_fee=liquidation_fee,
                # reward=parsed.amount_returned_to_liquidator,
                transaction_hash=event.id.get("txDigest", ""),
                block_number=1,
            )

            db.add(liquidation)

            # 🔹 Update market stats
            await self._update_market_stats(
                db,
                position.market_id,
                position.size,
                is_long=(position.side == PositionSideEnum.LONG),
                add=False,
            )

            # 🔹 Notify
            await self._send_liquidation_notification(position, parsed, event)

            indexed += 1

        await db.commit()
        logger.info(f"Indexed {indexed} PositionLiquidated events")

    # ========================================================================
    # NOTIFICATIONS
    # ========================================================================

    async def _send_position_opened_notification(
        self,
        position: PositionModel,
        event: OnechainEventData,
    ) -> None:
        """Send position opened notification."""
        try:
            # Get market for symbol
            async with AsyncSessionLocal() as db:
                market_result = await db.execute(
                    select(MarketModel).where(
                        MarketModel.market_id == position.market_id
                    )
                )
                market = market_result.scalar_one_or_none()

            # Calculate liquidation price
            liquidation_price = calculate_liquidation_price(
                entry_price=position.entry_price,
                leverage=position.leverage,
                is_long=(position.side == PositionSideEnum.LONG),
                maintenance_margin_rate=market.maintenance_margin_rate
                if market
                else Decimal("0.05"),
            )

            notify_position_opened(
                user_address=position.user_address,
                position_id=position.position_id,
                market_id=position.market_id,
                symbol=market.symbol if market else position.market_id,
                side=position.side.value,
                size=position.size,
                entry_price=position.entry_price,
                leverage=position.leverage,
                collateral=position.collateral,
                liquidation_price=liquidation_price,
                tx_hash=event.id.get("txDigest"),
            )

        except Exception:
            logger.exception("Error sending position opened notification")

    async def _send_position_closed_notification(
        self,
        position: PositionModel,
        parsed: PositionClosedEvent,
        event: OnechainEventData,
    ) -> None:
        """Send position closed notification."""
        try:
            # Get market for symbol
            async with AsyncSessionLocal() as db:
                market_result = await db.execute(
                    select(MarketModel).where(
                        MarketModel.market_id == position.market_id
                    )
                )
                market = market_result.scalar_one_or_none()

            # Get user's new balance (would need to query from blockchain)
            # For now, approximate
            new_balance = position.collateral + parsed.pnl

            notify_position_closed(
                user_address=position.user_address,
                position_id=position.position_id,
                market_id=position.market_id,
                symbol=market.symbol if market else position.market_id,
                side=position.side.value,
                size=position.size,
                entry_price=position.entry_price,
                exit_price=position.exit_price,
                realized_pnl=parsed.pnl,
                new_balance=new_balance,
                tx_hash=event.id.get("txDigest"),
            )

        except Exception:
            logger.exception("Error sending position closed notification")

    async def _send_position_updated_notification(
        self,
        position: PositionModel,
        parsed: PositionUpdatedEvent,
        event: OnechainEventData,
    ) -> None:
        """Send position updated notification."""
        try:
            # Get market for symbol
            async with AsyncSessionLocal() as db:
                market_result = await db.execute(
                    select(MarketModel).where(
                        MarketModel.market_id == position.market_id
                    )
                )
                market = market_result.scalar_one_or_none()

            # Re-calc liquidation price after update
            liquidation_price = calculate_liquidation_price(
                entry_price=position.entry_price,
                leverage=position.leverage,
                is_long=(position.side == PositionSideEnum.LONG),
                maintenance_margin_rate=market.maintenance_margin_rate,
            )

            notify_position_opened(
                user_address=position.user_address,
                position_id=position.position_id,
                market_id=position.market_id,
                symbol=market.symbol if market else position.market_id,
                side=position.side.value,
                size=position.size,
                entry_price=position.entry_price,
                leverage=position.leverage,
                collateral=position.collateral,
                liquidation_price=liquidation_price,
                tx_hash=event.id.get("txDigest"),
            )

        except Exception:
            logger.exception("Error sending position updated notification")

    async def _send_liquidation_notification(
        self,
        position: PositionModel,
        parsed: PositionLiquidatedEvent,
        event: OnechainEventData,
    ) -> None:
        """Send liquidation notification."""
        try:
            # Get market for symbol
            async with AsyncSessionLocal() as db:
                market_result = await db.execute(
                    select(MarketModel).where(
                        MarketModel.market_id == position.market_id
                    )
                )
                market = market_result.scalar_one_or_none()

            # Calculate PnL (negative for liquidation)
            pnl = -(position.collateral - parsed.liquidation_fee)

            # New balance (would need to query from blockchain)
            new_balance = Decimal("0")

            notify_position_liquidated(
                user_address=position.user_address,
                position_id=position.position_id,
                market_id=position.market_id,
                symbol=market.symbol if market else position.market_id,
                side=position.side.value,
                size=position.size,
                entry_price=position.entry_price,
                liquidation_price=calculate_liquidation_price(
                    entry_price=position.entry_price,
                    leverage=position.leverage,
                    is_long=(position.side == PositionSideEnum.LONG),
                    maintenance_margin_rate=market.maintenance_margin_rate
                    if market
                    else Decimal("0.05"),
                ),
                realized_pnl=pnl,
                liquidation_fee=parsed.liquidation_fee,
                new_balance=new_balance,
                tx_hash=event.id.get("txDigest"),
            )

        except Exception:
            logger.exception("Error sending liquidation notification")

    # ========================================================================
    # HELPERS
    # ========================================================================

    async def _update_market_stats(
        self,
        db: AsyncSession,
        market_id: str,
        size: Decimal,
        *,
        is_long: bool,
        add: bool,
    ) -> None:
        """
        Update market OI statistics.

        Args:
            db: Database session
            market_id: Market identifier
            size: Position size
            is_long: True if long position
            add: True to add, False to subtract
        """
        result = await db.execute(
            select(MarketModel).where(MarketModel.market_id == market_id)
        )
        market = result.scalar_one_or_none()

        if not market:
            return

        if add:
            if is_long:
                market.total_long_positions += size
            else:
                market.total_short_positions += size
        else:
            if is_long:
                market.total_long_positions = max(
                    Decimal("0"), market.total_long_positions - size
                )
            else:
                market.total_short_positions = max(
                    Decimal("0"), market.total_short_positions - size
                )

    async def _update_market_stats_on_position_update(
        self,
        db: AsyncSession,
        market_id: str,
        *,
        old_size: Decimal,
        new_size: Decimal,
        old_is_long: bool,
        new_is_long: bool,
    ) -> None:
        result = await db.execute(
            select(MarketModel).where(MarketModel.market_id == market_id)
        )
        market = result.scalar_one_or_none()

        if not market:
            return

        # Same direction → apply delta
        if old_is_long == new_is_long:
            delta = new_size - old_size

            if delta == 0:
                return

            if old_is_long:
                market.total_long_positions = max(
                    Decimal("0"), market.total_long_positions + delta
                )
            else:
                market.total_short_positions = max(
                    Decimal("0"), market.total_short_positions + delta
                )

        # Direction flipped
        else:
            # Remove old side
            if old_is_long:
                market.total_long_positions = max(
                    Decimal("0"), market.total_long_positions - old_size
                )
            else:
                market.total_short_positions = max(
                    Decimal("0"), market.total_short_positions - old_size
                )

            # Add new side
            if new_is_long:
                market.total_long_positions += new_size
            else:
                market.total_short_positions += new_size

    async def _get_last_synced_checkpoint(self, db: AsyncSession) -> int:
        """
        Get last synced checkpoint.

        Args:
            db: Database session

        Returns:
            Last synced checkpoint number
        """
        result = await db.execute(
            select(BlockSyncModel).where(
                BlockSyncModel.chain_id == settings.onechain_chain_id
            )
        )
        sync = result.scalar_one_or_none()

        if sync:
            return sync.last_synced_block

        # Create new sync record
        sync = BlockSyncModel(
            chain_id=settings.onechain_chain_id,
            last_synced_block=settings.onechain_start_checkpoint,
        )
        db.add(sync)
        await db.commit()

        return settings.onechain_start_checkpoint

    async def _update_last_synced_checkpoint(
        self,
        db: AsyncSession,
        checkpoint: int,
    ) -> None:
        """
        Update last synced checkpoint.

        Args:
            db: Database session
            checkpoint: Checkpoint number
        """
        _ = await db.execute(
            update(BlockSyncModel)
            .where(BlockSyncModel.chain_id == settings.onechain_chain_id)
            .values(last_synced_block=checkpoint)
        )


# Global indexer instance
indexer = BlockchainIndexer()

import asyncio
from typing import Optional
from datetime import datetime
from decimal import Decimal
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger
from web3 import Web3

from app.db.session import AsyncSessionLocal
from app.db.models import (
    MarketModel,
    PositionModel,
    LiquidationModel,
    BlockSyncModel,
    PositionStatusEnum,
    PositionSideEnum,
)
from app.services.blockchain import blockchain_service
from app.services.broadcaster import broadcaster
from app.core.config import settings


class BlockchainIndexer:
    """Service for indexing blockchain events and maintaining local database."""
    
    def __init__(self):
        self.is_running = False
        self.batch_size = 1000  # Process blocks in batches
        self.poll_interval = 5  # seconds
    
    async def start(self):
        """Start the indexer."""
        self.is_running = True
        logger.info("Starting blockchain indexer...")
        
        while self.is_running:
            try:
                await self._sync_events()
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Error in indexer loop: {e}")
                await asyncio.sleep(self.poll_interval)
    
    async def stop(self):
        """Stop the indexer."""
        self.is_running = False
        logger.info("Stopping blockchain indexer...")
    
    async def _sync_events(self):
        """Sync events from blockchain."""
        async with AsyncSessionLocal() as db:
            # Get last synced block
            last_block = await self._get_last_synced_block(db)
            current_block = await blockchain_service.get_latest_block()
            
            if last_block >= current_block:
                return
            
            logger.info(f"Syncing blocks {last_block + 1} to {current_block}")
            
            # Process in batches
            from_block = last_block + 1
            
            while from_block <= current_block:
                to_block = min(from_block + self.batch_size - 1, current_block)
                
                try:
                    await self._process_block_range(db, from_block, to_block)
                    
                    # Update last synced block
                    await self._update_last_synced_block(db, to_block)
                    await db.commit()
                    
                    logger.info(f"Synced blocks {from_block} to {to_block}")
                    
                except Exception as e:
                    logger.error(f"Error processing blocks {from_block}-{to_block}: {e}")
                    await db.rollback()
                    break
                
                from_block = to_block + 1
    
    async def _process_block_range(
        self,
        db: AsyncSession,
        from_block: int,
        to_block: int,
    ):
        """Process events in a block range."""
        # Index PositionOpened events
        await self._index_position_opened(db, from_block, to_block)
        
        # Index PositionClosed events
        await self._index_position_closed(db, from_block, to_block)
        
        # Index PositionLiquidated events
        await self._index_liquidations(db, from_block, to_block)
    
    async def _index_position_opened(
        self,
        db: AsyncSession,
        from_block: int,
        to_block: int,
    ):
        """Index PositionOpened events."""
        events = await blockchain_service.get_events(
            "PositionOpened",
            from_block,
            to_block,
        )
        
        for event in events:
            args = event["args"]
            
            # Check if position already exists
            stmt = select(PositionModel).where(
                PositionModel.position_id == Web3.to_hex(args["positionId"])
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                continue
            
            # Create new position
            position = PositionModel(
                position_id=Web3.to_hex(args["positionId"]),
                market_id=Web3.to_hex(args["marketId"]),
                user_address=args["user"].lower(),
                
                side=PositionSideEnum.LONG if args["isLong"] else PositionSideEnum.SHORT,
                size=Decimal(args["size"]) / Decimal(10**18),
                collateral=Decimal(args["collateral"]) / Decimal(10**18),
                leverage=Decimal(args["leverage"]) / Decimal(10**2),
                
                entry_price=Decimal(args["entryPrice"]) / Decimal(10**18),
                
                status=PositionStatusEnum.OPEN,
                
                block_number=event["block_number"],
                transaction_hash=event["transaction_hash"],
            )
            
            db.add(position)
            
            # Broadcast event via WebSocket
            await broadcaster.broadcast_position_opened(
                position_id=Web3.to_hex(args["positionId"]),
                user_address=args["user"].lower(),
                market_id=Web3.to_hex(args["marketId"]),
                side="long" if args["isLong"] else "short",
                size=str(Decimal(args["size"]) / Decimal(10**18)),
                collateral=str(Decimal(args["collateral"]) / Decimal(10**18)),
                leverage=str(Decimal(args["leverage"]) / Decimal(10**2)),
                entry_price=str(Decimal(args["entryPrice"]) / Decimal(10**18)),
                transaction_hash=event["transaction_hash"],
            )
            
            # Update market stats
            await self._update_market_stats(
                db,
                Web3.to_hex(args["marketId"]),
                Decimal(args["size"]) / Decimal(10**18),
                args["isLong"],
                add=True,
            )
        
        logger.info(f"Indexed {len(events)} PositionOpened events")
    
    async def _index_position_closed(
        self,
        db: AsyncSession,
        from_block: int,
        to_block: int,
    ):
        """Index PositionClosed events."""
        events = await blockchain_service.get_events(
            "PositionClosed",
            from_block,
            to_block,
        )
        
        for event in events:
            args = event["args"]
            
            position_id = Web3.to_hex(args["positionId"])
            
            # Update position
            stmt = (
                update(PositionModel)
                .where(PositionModel.position_id == position_id)
                .values(
                    status=PositionStatusEnum.CLOSED,
                    exit_price=Decimal(args["exitPrice"]) / Decimal(10**18),
                    realized_pnl=Decimal(args["pnl"]) / Decimal(10**18),
                    close_transaction_hash=event["transaction_hash"],
                    closed_at=datetime.utcnow(),
                )
            )
            await db.execute(stmt)
            
            # Get position for broadcast
            stmt_pos = select(PositionModel).where(PositionModel.position_id == position_id)
            result_pos = await db.execute(stmt_pos)
            closed_position = result_pos.scalar_one_or_none()
            
            if closed_position:
                # Broadcast event via WebSocket
                await broadcaster.broadcast_position_closed(
                    position_id=position_id,
                    user_address=closed_position.user_address,
                    market_id=closed_position.market_id,
                    exit_price=str(Decimal(args["exitPrice"]) / Decimal(10**18)),
                    realized_pnl=str(Decimal(args["pnl"]) / Decimal(10**18)),
                    transaction_hash=event["transaction_hash"],
                )
            
            # Get position for market stats update
            stmt = select(PositionModel).where(PositionModel.position_id == position_id)
            result = await db.execute(stmt)
            position = result.scalar_one_or_none()
            
            if position:
                await self._update_market_stats(
                    db,
                    position.market_id,
                    position.size,
                    position.side == PositionSideEnum.LONG,
                    add=False,
                )
        
        logger.info(f"Indexed {len(events)} PositionClosed events")
    
    async def _index_liquidations(
        self,
        db: AsyncSession,
        from_block: int,
        to_block: int,
    ):
        """Index PositionLiquidated events."""
        events = await blockchain_service.get_events(
            "PositionLiquidated",
            from_block,
            to_block,
        )
        
        for event in events:
            args = event["args"]
            
            position_id = Web3.to_hex(args["positionId"])
            
            # Get position
            stmt = select(PositionModel).where(PositionModel.position_id == position_id)
            result = await db.execute(stmt)
            position = result.scalar_one_or_none()
            
            if not position:
                logger.warning(f"Position {position_id} not found for liquidation")
                continue
            
            # Update position status
            stmt = (
                update(PositionModel)
                .where(PositionModel.position_id == position_id)
                .values(
                    status=PositionStatusEnum.LIQUIDATED,
                    exit_price=Decimal(args["liquidationPrice"]) / Decimal(10**18),
                    close_transaction_hash=event["transaction_hash"],
                    closed_at=datetime.utcnow(),
                )
            )
            await db.execute(stmt)
            
            # Record liquidation event
            liquidation = LiquidationModel(
                position_id=position_id,
                market_id=position.market_id,
                user_address=args["user"].lower(),
                liquidator_address=args["liquidator"].lower(),
                
                liquidation_price=Decimal(args["liquidationPrice"]) / Decimal(10**18),
                collateral=position.collateral,
                liquidation_fee=Decimal(args["liquidationFee"]) / Decimal(10**18),
                
                transaction_hash=event["transaction_hash"],
                block_number=event["block_number"],
            )
            db.add(liquidation)
            
            # Broadcast event via WebSocket
            await broadcaster.broadcast_position_liquidated(
                position_id=position_id,
                user_address=args["user"].lower(),
                market_id=position.market_id,
                liquidator_address=args["liquidator"].lower(),
                liquidation_price=str(Decimal(args["liquidationPrice"]) / Decimal(10**18)),
                liquidation_fee=str(Decimal(args["liquidationFee"]) / Decimal(10**18)),
                transaction_hash=event["transaction_hash"],
            )
            
            # Update market stats
            await self._update_market_stats(
                db,
                position.market_id,
                position.size,
                position.side == PositionSideEnum.LONG,
                add=False,
            )
        
        logger.info(f"Indexed {len(events)} PositionLiquidated events")
    
    async def _update_market_stats(
        self,
        db: AsyncSession,
        market_id: str,
        size: Decimal,
        is_long: bool,
        add: bool,
    ):
        """Update market position stats."""
        stmt = select(MarketModel).where(MarketModel.market_id == market_id)
        result = await db.execute(stmt)
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
    
    async def _get_last_synced_block(self, db: AsyncSession) -> int:
        """Get last synced block number."""
        stmt = select(BlockSyncModel).where(
            BlockSyncModel.chain_id == settings.chain_id
        )
        result = await db.execute(stmt)
        sync = result.scalar_one_or_none()
        
        if sync:
            return sync.last_synced_block
        
        # Create new record
        sync = BlockSyncModel(
            chain_id=settings.chain_id,
            last_synced_block=settings.start_block,
        )
        db.add(sync)
        await db.commit()
        
        return settings.start_block
    
    async def _update_last_synced_block(self, db: AsyncSession, block_number: int):
        """Update last synced block."""
        stmt = (
            update(BlockSyncModel)
            .where(BlockSyncModel.chain_id == settings.chain_id)
            .values(last_synced_block=block_number)
        )
        await db.execute(stmt)


# Global indexer instance
indexer = BlockchainIndexer()

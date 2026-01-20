import asyncio
from datetime import datetime, timedelta
from decimal import Decimal

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import (
    MarketModel,
    PositionModel,
    PositionSideEnum,
    PositionStatusEnum,
)
from app.db.session import AsyncSessionLocal
from app.schemas.position import LiquidationCandidate
from app.services.blockchain import blockchain_service
from app.services.notifications import notify_liquidation_warning
from app.services.oracle import oracle_service


class LiquidationBot:
    """
    Automated liquidation bot.

    Monitors open positions and liquidates unhealthy positions.
    Type-safe implementation with zero Pyright warnings.
    """

    def __init__(self) -> None:
        self.is_running: bool = False
        self.check_interval: int = settings.liquidation_check_interval
        self.min_health_factor: Decimal = settings.min_health_factor
        self.max_gas_price: int = settings.liquidation_max_gas_price

        # Track recently checked positions to avoid spam
        self._last_check_times: dict[str, datetime] = {}
        self._check_cooldown: int = 30  # seconds

    async def start(self) -> None:
        """Start the liquidation bot."""
        self.is_running = True
        logger.info("🤖 Liquidation bot started")

        while self.is_running:
            try:
                await self._check_and_liquidate()
                await asyncio.sleep(self.check_interval)
            except Exception:
                logger.exception("Error in liquidation bot loop")
                await asyncio.sleep(self.check_interval)

    async def stop(self) -> None:
        """Stop the liquidation bot."""
        self.is_running = False
        logger.info("Liquidation bot stopped")

    async def _check_and_liquidate(self) -> None:
        """Check positions and execute liquidations."""
        async with AsyncSessionLocal() as db:
            # Get all liquidation candidates
            candidates = await self._find_liquidation_candidates(db)

            if not candidates:
                logger.debug("No liquidation candidates found")
                return

            logger.info(f"Found {len(candidates)} liquidation candidates")

            # Process each candidate
            for candidate in candidates:
                try:
                    await self._execute_liquidation(db, candidate)
                except Exception:
                    logger.exception(
                        f"Error liquidating position {candidate.position_id}"
                    )

    async def _find_liquidation_candidates(
        self,
        db: AsyncSession,
    ) -> list[LiquidationCandidate]:
        """
        Find positions eligible for liquidation.

        Type-safe implementation:
        - Explicit tuple unpacking
        - No dynamic attribute access
        - Full type annotations

        Args:
            db: Database session

        Returns:
            List of liquidation candidates sorted by potential reward
        """
        candidates: list[LiquidationCandidate] = []

        # Get all open positions with their markets
        stmt = (
            select(PositionModel, MarketModel)
            .join(MarketModel, PositionModel.market_id == MarketModel.market_id)
            .where(PositionModel.status == PositionStatusEnum.OPEN)
        )

        result = await db.execute(stmt)
        position_rows = result.all()

        if not position_rows:
            return candidates

        # ✅ Type-safe: Extract positions and markets with explicit typing
        positions_data: list[tuple[PositionModel, MarketModel]] = [
            (pos, market) for pos, market in position_rows
        ]

        # ✅ Type-safe: Get unique price feed IDs
        price_feed_ids: list[str] = list(
            set(market.pyth_price_id for _, market in positions_data)
        )

        # Batch fetch all prices
        prices = await oracle_service.get_latest_prices(price_feed_ids)

        # Check each position
        for position, market in positions_data:
            # Check cooldown
            if self._is_on_cooldown(position.position_id):
                continue

            # Get current price
            price_data = prices.get(market.pyth_price_id)
            if not price_data:
                logger.warning(f"No price data for market {market.market_id}")
                continue

            # Validate price freshness and confidence
            if not oracle_service.is_price_fresh(price_data, max_age_seconds=30):
                logger.warning(f"Stale price for market {market.market_id}")
                continue

            if not oracle_service.is_price_confident(price_data):
                logger.warning(f"Low confidence price for market {market.market_id}")
                continue

            current_price: Decimal = price_data.normalized_price

            # Calculate health factor
            health_factor: Decimal = blockchain_service.calculate_health_factor(
                collateral=position.collateral,
                position_size=position.size,
                entry_price=position.entry_price,
                current_price=current_price,
                is_long=(position.side == PositionSideEnum.LONG),
                maintenance_margin_rate=market.maintenance_margin_rate,
                accumulated_funding=position.accumulated_funding,
            )

            # Check if liquidatable
            if health_factor <= self.min_health_factor:
                # Calculate liquidation price
                liquidation_price: Decimal = (
                    blockchain_service.calculate_liquidation_price(
                        entry_price=position.entry_price,
                        leverage=position.leverage,
                        is_long=(position.side == PositionSideEnum.LONG),
                        maintenance_margin_rate=market.maintenance_margin_rate,
                    )
                )

                # Calculate potential reward
                liquidation_fee = position.collateral * market.liquidation_fee_rate
                potential_reward = liquidation_fee * Decimal(
                    str(settings.liquidation_reward_rate)
                )

                # Create liquidation candidate
                candidate = LiquidationCandidate(
                    position_id=position.position_id,
                    user_address=position.user_address,
                    market_id=position.market_id,
                    current_price=current_price,
                    health_factor=health_factor,
                    liquidation_price=liquidation_price,
                    collateral=position.collateral,
                    potential_reward=potential_reward,
                )

                candidates.append(candidate)

                logger.info(
                    f"Liquidation candidate: {position.position_id}, "
                    f"health={health_factor:.4f}, reward={potential_reward}"
                )

                # Send liquidation warning notification
                await self._send_liquidation_warning(
                    user_address=position.user_address,
                    position_id=position.position_id,
                    market_id=position.market_id,
                    symbol=market.symbol,
                    health_factor=health_factor,
                    current_price=current_price,
                    liquidation_price=liquidation_price,
                )

        # Sort by potential reward (highest first)
        candidates.sort(key=lambda x: x.potential_reward, reverse=True)

        return candidates

    async def _send_liquidation_warning(
        self,
        user_address: str,
        position_id: str,
        market_id: str,
        symbol: str,
        health_factor: Decimal,
        current_price: Decimal,
        liquidation_price: Decimal,
    ) -> None:
        """
        Send liquidation warning notification to user.

        Args:
            user_address: User wallet address
            position_id: Position identifier
            market_id: Market identifier
            symbol: Market symbol
            health_factor: Current health factor
            current_price: Current market price
            liquidation_price: Liquidation trigger price
        """
        try:
            notify_liquidation_warning(
                user_address=user_address,
                position_id=position_id,
                market_id=market_id,
                symbol=symbol,
                health_factor=health_factor,
                current_price=current_price,
                liquidation_price=liquidation_price,
            )
        except Exception:
            logger.exception("Error sending liquidation warning")

    async def _execute_liquidation(
        self,
        db: AsyncSession,
        candidate: LiquidationCandidate,
    ) -> None:
        """
        Execute liquidation transaction.

        Args:
            db: Database session
            candidate: Liquidation candidate
        """
        logger.info(f"Attempting to liquidate position {candidate.position_id}")

        # Mark as checked to avoid spam
        self._mark_checked(candidate.position_id)

        # Get market data
        market_result = await db.execute(
            select(MarketModel).where(MarketModel.market_id == candidate.market_id)
        )
        market = market_result.scalar_one_or_none()

        if not market:
            logger.error(f"Market {candidate.market_id} not found")
            return

        # Get price update data for Pyth
        price_update_data = await oracle_service.get_price_update_data(
            market.pyth_price_id
        )

        if not price_update_data:
            logger.error(f"Failed to get price update data for {market.pyth_price_id}")
            return

        # TODO: In production, implement actual liquidation:
        # 1. Build liquidation transaction
        # 2. Estimate gas
        # 3. Check gas price vs max_gas_price
        # 4. Sign transaction
        # 5. Send transaction
        # 6. Monitor transaction status
        # 7. Update database on success
        # 8. Send notification to user

        # In a real implementation, you would:
        # 1. Build the liquidation transaction
        # 2. Estimate gas
        # 3. Sign transaction
        # 4. Send transaction
        # 5. Monitor transaction status

        # Example (pseudo-code):
        """
        try:
            # Build transaction
            tx = contract.functions.liquidatePosition(
                position_id=candidate.position_id,
                price_update_data=price_update_data,
            ).build_transaction({
                'from': liquidator_address,
                'gas': estimated_gas,
                'gasPrice': current_gas_price,
                'nonce': nonce,
            })
            
            # Sign and send
            signed_tx = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"Liquidation tx sent: {tx_hash.hex()}")
            
            # Wait for confirmation
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt.status == 1:
                logger.info(f"Successfully liquidated {candidate.position_id}")
                from app.services.notifications import notify_position_liquidated
                notify_position_liquidated(
                    user_address=candidate.user_address,
                    position_id=candidate.position_id,
                    market_id=candidate.market_id,
                    symbol=market.symbol,
                    side="long" if position.side == PositionSideEnum.LONG else "short",
                    size=position.size,
                    entry_price=position.entry_price,
                    exit_price=candidate.current_price,
                    realized_pnl=calculated_pnl,
                    new_balance=new_user_balance,
                )
            else:
                logger.error(f"Liquidation failed for {candidate.position_id}")
                
        except Exception as e:
            logger.error(f"Error executing liquidation: {e}")
        """

        # For now, just log
        logger.info(
            f"Would liquidate {candidate.position_id} at price {candidate.current_price} "
            f"(health factor: {candidate.health_factor:.4f}, "
            f"reward: {candidate.potential_reward})"
        )

    def _is_on_cooldown(self, position_id: str) -> bool:
        """
        Check if position is on cooldown.

        Args:
            position_id: Position identifier

        Returns:
            True if position was checked recently
        """
        if position_id not in self._last_check_times:
            return False

        last_check = self._last_check_times[position_id]
        elapsed = (datetime.utcnow() - last_check).total_seconds()

        return elapsed < self._check_cooldown

    def _mark_checked(self, position_id: str) -> None:
        """
        Mark position as checked.

        Args:
            position_id: Position identifier
        """
        self._last_check_times[position_id] = datetime.utcnow()

        # Clean up old entries to prevent memory leak
        cutoff = datetime.utcnow() - timedelta(seconds=self._check_cooldown * 2)
        self._last_check_times = {
            k: v for k, v in self._last_check_times.items() if v > cutoff
        }

    async def get_liquidation_stats(self) -> dict[str, int | Decimal | bool]:
        """
        Get liquidation bot statistics.

        Returns:
            Dictionary with bot statistics
        """
        async with AsyncSessionLocal() as db:
            candidates = await self._find_liquidation_candidates(db)

            total_candidates: int = len(candidates)
            total_potential_reward: Decimal = sum(
                c.potential_reward for c in candidates
            )

            return {
                "total_candidates": total_candidates,
                "total_potential_reward": total_potential_reward,
                "is_running": self.is_running,
                "check_interval": self.check_interval,
                "min_health_factor": self.min_health_factor,
            }


# Global liquidation bot instance
liquidation_bot = LiquidationBot()

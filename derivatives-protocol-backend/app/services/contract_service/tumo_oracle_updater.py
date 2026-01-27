"""
Tumo Oracle Updater Service

Updates price feeds every 5 seconds for Tumo protocol.
Price format: price * 10^6
"""

import asyncio
from decimal import Decimal

from app.services.contract_service.transaction_service import tx_service
from app.services.oracle import oracle_service
from loguru import logger


class TumoOracleUpdater:
    """
    Oracle updater for Tumo protocol.

    Updates price feeds every 5 seconds with format: price * 10^6
    """

    def __init__(self) -> None:
        self.is_running: bool = False
        self.update_interval: int = 5  # seconds

        # Price feed configurations
        self.price_feeds: dict[str, str] = {
            # token_type -> pyth_price_feed_id
            "btc": "0xe62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",
        }

    async def start(self) -> None:
        """Start oracle updater."""
        self.is_running = True
        logger.info("🔮 Tumo Oracle Updater started")

        while self.is_running:
            try:
                await self._update_prices()
                await asyncio.sleep(self.update_interval)
            except Exception:
                logger.exception("Error in oracle updater loop")
                await asyncio.sleep(self.update_interval)

    async def stop(self) -> None:
        """Stop oracle updater."""
        self.is_running = False
        logger.info("Tumo Oracle Updater stopped")

    async def _update_prices(self) -> None:
        """Update all price feeds."""
        for token_type, pyth_feed_id in self.price_feeds.items():
            try:
                await self._update_price_feed(token_type, pyth_feed_id)
            except Exception:
                logger.exception(f"Error updating price for {token_type}")

    async def _update_price_feed(
        self,
        token_type: str,
        pyth_feed_id: str,
    ) -> None:
        """
        Update a single price feed.

        Args:
            token_type: Token type (e.g., OCT_TYPE)
            pyth_feed_id: Pyth price feed ID
        """
        # Get price from Pyth
        price_data = await oracle_service.get_latest_price(pyth_feed_id)

        if not price_data:
            logger.warning(f"No price data for {token_type}")
            return

        # Check if price is fresh and confident
        if not oracle_service.is_price_fresh(price_data, max_age_seconds=30):
            logger.warning(f"Stale price for {token_type}")
            return

        if not oracle_service.is_price_confident(price_data):
            logger.warning(f"Low confidence price for {token_type}")
            return

        # Convert price to Tumo format: price * 10^6
        price_normalized = price_data.normalized_price
        price_tumo = int(price_normalized * Decimal("1000000"))

        # Build and execute transaction
        try:
            tx_digest = await self._execute_update_price_tx(token_type, price_tumo)

            logger.info(
                f"Updated price for {token_type}: {price_normalized} "
                f"(Tumo format: {price_tumo}) - TX: {tx_digest}"
            )

        except Exception:
            logger.exception(f"Failed to execute update price tx for {token_type}")

    async def _execute_update_price_tx(
        self,
        token_type: str,
        new_price: int,
    ) -> str:
        """
        Execute update_price transaction via Sui Transaction Service.

        Args:
            token_type: Token type for type argument (not used - service handles this)
            new_price: New price in Tumo format (price * 10^6)

        Returns:
            Transaction digest
        """

        # Convert back to Decimal for the service
        # Service will reconvert to Tumo format internally
        price_decimal = Decimal(new_price) / Decimal("1000000")

        # Execute via transaction service
        tx_digest = await tx_service.update_price(price_decimal)

        return tx_digest


# Global instance
tumo_oracle_updater = TumoOracleUpdater()

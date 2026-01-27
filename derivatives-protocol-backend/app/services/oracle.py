import base64
from decimal import Decimal
from typing import Dict, List, Optional

import aiohttp
from loguru import logger

from app.core.config import settings
from app.schemas.common import PriceData


class PythOracleService:
    """Service for interacting with Pyth Network oracle."""

    def __init__(self):
        self.http_endpoint = settings.pyth_http_endpoint
        self.ws_endpoint = settings.pyth_ws_endpoint
        self.network = settings.pyth_network

        self._price_cache: Dict[str, PriceData] = {}
        self._cache_ttl = 10  # seconds
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Close aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_latest_price(self, price_feed_id: str) -> Optional[PriceData]:
        """
        Get latest price from Pyth Network.

        Args:
            price_feed_id: Pyth price feed ID (with 0x prefix)

        Returns:
            PriceData or None if not available
        """
        try:
            # Check cache first
            cached = self._get_cached_price(price_feed_id)
            if cached:
                return cached

            session = await self._get_session()

            # Fetch from Pyth HTTP API
            url = f"{self.http_endpoint}/api/latest_price_feeds"
            params = {
                "ids[]": price_feed_id,
            }

            async with session.get(url, params=params) as response:
                if response.status != 200:
                    logger.error(
                        f"Failed to fetch price for {price_feed_id}: {response.status}"
                    )
                    return None

                data = await response.json()

                if not data or len(data) == 0:
                    logger.warning(f"No price data available for {price_feed_id}")
                    return None

                price_feed = data[0]
                price_obj = price_feed.get("price")

                if not price_obj:
                    logger.warning(f"Price object not found for {price_feed_id}")
                    return None

                price_data = PriceData(
                    price_id=price_feed_id,
                    price=Decimal(str(price_obj["price"])),
                    confidence=Decimal(str(price_obj["conf"])),
                    expo=int(price_obj["expo"]),
                    publish_time=int(price_obj["publish_time"]),
                )

                # Cache the price
                self._cache_price(price_feed_id, price_data)

                return price_data

        except Exception as e:
            logger.error(f"Error fetching price for {price_feed_id}: {e}")
            return None

    async def get_latest_prices(
        self, price_feed_ids: List[str]
    ) -> Dict[str, PriceData]:
        """
        Get latest prices for multiple feeds.

        Args:
            price_feed_ids: List of Pyth price feed IDs

        Returns:
            Dict mapping feed ID to PriceData
        """
        try:
            session = await self._get_session()

            # Build query params
            url = f"{self.http_endpoint}/api/latest_price_feeds"
            params = [("ids[]", feed_id) for feed_id in price_feed_ids]

            async with session.get(url, params=params) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch prices: {response.status}")
                    return {}

                data = await response.json()

                result = {}
                for price_feed in data:
                    price_obj = price_feed.get("price")
                    if not price_obj:
                        continue

                    feed_id = price_feed["id"]
                    price_data = PriceData(
                        price_id=feed_id,
                        price=Decimal(str(price_obj["price"])),
                        confidence=Decimal(str(price_obj["conf"])),
                        expo=int(price_obj["expo"]),
                        publish_time=int(price_obj["publish_time"]),
                    )

                    result[feed_id] = price_data
                    self._cache_price(feed_id, price_data)

                return result

        except Exception as e:
            logger.error(f"Error fetching multiple prices: {e}")
            return {}

    async def get_price_update_data(self, price_feed_id: str) -> Optional[bytes]:
        try:
            session = await self._get_session()
            url = f"{self.http_endpoint}/api/latest_vaas"
            params = {"ids[]": price_feed_id}

            async with session.get(url, params=params) as response:
                if response.status != 200:
                    logger.error(
                        f"Failed to fetch VAA for {price_feed_id}: {response.status}"
                    )
                    return None

                data = await response.json()

                if not data:
                    logger.warning(f"No VAA available for {price_feed_id}")
                    return None

                # ✅ VAA là BASE64, không phải hex
                vaa_b64 = data[0]
                return base64.b64decode(vaa_b64)

        except Exception as e:
            logger.error(f"Error fetching VAA for {price_feed_id}: {e}")
            return None

    def _get_cached_price(self, price_feed_id: str) -> Optional[PriceData]:
        """Get price from cache if still valid."""
        if price_feed_id in self._price_cache:
            cached = self._price_cache[price_feed_id]
            if cached.age_seconds <= self._cache_ttl:
                return cached
        return None

    def _cache_price(self, price_feed_id: str, price_data: PriceData):
        """Cache price data."""
        self._price_cache[price_feed_id] = price_data

    def is_price_fresh(self, price_data: PriceData, max_age_seconds: int = 10) -> bool:
        """
        Check if price is fresh enough.

        Args:
            price_data: Price data to check
            max_age_seconds: Maximum acceptable age in seconds

        Returns:
            True if price is fresh
        """
        return price_data.age_seconds <= max_age_seconds

    def is_price_confident(
        self, price_data: PriceData, max_confidence_ratio: Decimal = Decimal("0.01")
    ) -> bool:
        """
        Check if price confidence is acceptable.

        Args:
            price_data: Price data to check
            max_confidence_ratio: Maximum confidence/price ratio (default 1%)

        Returns:
            True if confidence is acceptable
        """
        if price_data.price == 0:
            return False

        confidence_ratio = price_data.confidence / abs(price_data.price)
        return confidence_ratio <= max_confidence_ratio


# Global oracle service instance
oracle_service = PythOracleService()

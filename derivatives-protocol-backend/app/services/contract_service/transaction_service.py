"""
Sui Transaction Service Client

Python client for interacting with the TypeScript Sui transaction service.
Handles oracle price updates and position liquidations.
"""

from decimal import Decimal
from typing import Any

import httpx
from app.core.config import settings
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential


class TransactionService:
    """
    Client for TypeScript Sui transaction service.

    Communicates with Express API to execute blockchain transactions.
    """

    def __init__(self) -> None:
        self.base_url: str = settings.contract_service_url
        self.api_key: str = settings.contract_service_api_key

        # HTTP client with connection pooling
        self.client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(
                max_keepalive_connections=10,
                max_connections=20,
            ),
            headers={
                "X-API-Key": self.api_key,
                "Content-Type": "application/json",
            },
        )

        logger.info(f"Sui Transaction Service client initialized: {self.base_url}")

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()

    async def health_check(self) -> dict[str, Any]:
        """
        Check service health.

        Returns:
            Service health status
        """
        try:
            response = await self.client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def update_price(self, price: Decimal) -> str:
        """
        Update oracle price on-chain.

        This method automatically converts the price to Tumo format (price * 10^6)
        and executes the oracle::update_price transaction.

        Args:
            price: Price in USD (e.g., Decimal("50123.45"))

        Returns:
            Transaction digest

        Raises:
            Exception: If update fails
        """
        # Convert to Tumo format: price * 10^6
        price_tumo = int(price * Decimal("1000000"))

        try:
            logger.debug(f"Updating price: {price} USD → {price_tumo} (on-chain)")

            response = await self.client.post(
                f"{self.base_url}/api/update-price",
                json={"price": price_tumo},
            )

            response.raise_for_status()
            result = response.json()

            if result.get("success"):
                digest = result["digest"]
                logger.info(f"✅ Price updated: {price} USD → TX: {digest}")
                return digest

            error_msg = result.get("error", "Unknown error")
            raise Exception(f"Failed to update price: {error_msg}")

        except httpx.HTTPError as e:
            logger.error(f"HTTP error updating price: {e}")
            raise Exception(f"HTTP error: {e}")
        except Exception as e:
            logger.error(f"Error updating price: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def liquidate_position(self, user_address: str) -> str:
        """
        Liquidate a position on-chain.

        Executes the tumo_markets_core::liquidate transaction for a user
        whose position has reached liquidation threshold (PNL <= 0).

        Args:
            user_address: User's Sui wallet address (0x...)

        Returns:
            Transaction digest

        Raises:
            Exception: If liquidation fails
        """
        try:
            logger.debug(f"Liquidating position for user: {user_address}")

            response = await self.client.post(
                f"{self.base_url}/api/liquidate",
                json={"userAddress": user_address},
            )

            response.raise_for_status()
            result = response.json()

            if result.get("success"):
                digest = result["digest"]
                logger.info(f"✅ Position liquidated: {user_address} → TX: {digest}")
                return digest

            error_msg = result.get("error", "Unknown error")
            raise Exception(f"Failed to liquidate: {error_msg}")

        except httpx.HTTPError as e:
            logger.error(f"HTTP error liquidating position: {e}")
            raise Exception(f"HTTP error: {e}")
        except Exception as e:
            logger.error(f"Error liquidating position: {e}")
            raise

    async def get_signer_address(self) -> str:
        """
        Get the signer address from the transaction service.

        Returns:
            Signer's Sui address
        """
        try:
            response = await self.client.get(f"{self.base_url}/api/signer")
            response.raise_for_status()
            result = response.json()
            return result["address"]
        except Exception as e:
            logger.error(f"Error getting signer address: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def execute_sponsored_transaction(
        self,
        *,
        transaction_bytes_b64: str,
        user_signature_b64: str,
    ) -> dict[str, Any]:
        """
        Execute a sponsored transaction (NEW FLOW: txBytes already built by FE).

        Flow:
        - FE builds FULL tx bytes (includes sender, gasOwner, gasPayment, gasBudget, ...)
        - User signs FULL tx bytes
        - FE sends (transactionBytesB64, userSignatureB64) to backend
        - Backend calls TS service to sponsor-sign + submit (without modifying tx)

        Args:
            transaction_bytes_b64: Base64 encoded full TransactionBlock bytes
            user_signature_b64: User signature (flag||sig||pubkey)

        Returns:
            Full execution result from chain
        """
        try:
            payload: dict[str, Any] = {
                "transactionBytesB64": transaction_bytes_b64,
                "userSignatureB64": user_signature_b64,
            }

            logger.debug("Submitting sponsored tx (NEW FLOW)")

            response = await self.client.post(
                f"{self.base_url}/api/sponsored/execute",
                json=payload,
            )

            response.raise_for_status()
            result = response.json()

            if not result.get("success"):
                raise Exception(result.get("error", "Unknown sponsor execution error"))

            logger.info("✅ Sponsored tx executed | digest={}", result.get("digest"))
            return result

        except httpx.HTTPError as e:
            logger.error(f"HTTP error executing sponsored tx: {e}")
            raise
        except Exception as e:
            logger.error(f"Error executing sponsored tx: {e}")
            raise


# Global instance
tx_service = TransactionService()

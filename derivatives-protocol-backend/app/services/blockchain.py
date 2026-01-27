"""
Onechain Blockchain Service

Service for interacting with Onechain (Move-based blockchain).
Type-safe implementation with zero Pyright warnings.
"""

from decimal import Decimal
from typing import Any

import httpx
from loguru import logger

from app.constants import SCALE
from app.core.config import settings
from app.schemas.onechain import (
    OnechainEventData,
    OnechainRPCRequest,
    OnechainRPCResponse,
    OnechainTransaction,
    PositionClosedEvent,
    PositionLiquidatedEvent,
    PositionOpenedEvent,
    PositionUpdatedEvent,
)


class BlockchainService:
    """
    Service for interacting with Onechain blockchain.

    Onechain uses Move (like Sui), not EVM.
    Uses JSON-RPC API instead of Web3.
    """

    def __init__(self) -> None:
        self.rpc_url: str = settings.onechain_rpc_url
        self.network: str = settings.onechain_network  # "local", "testnet", "mainnet"
        self.package_id: str = settings.onechain_package_id  # Deployed Move package

        # HTTP client for RPC calls
        self.client = httpx.AsyncClient(
            timeout=30.0, limits=httpx.Limits(max_keepalive_connections=10)
        )

        logger.info(f"Onechain service initialized: {self.network} ({self.rpc_url})")

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()

    # ========================================================================
    # RPC METHODS
    # ========================================================================

    async def _call_rpc(
        self,
        method: str,
        params: list[Any] | None = None,
    ) -> Any:
        """
        Call Onechain JSON-RPC method.

        Args:
            method: RPC method name
            params: Method parameters

        Returns:
            RPC result

        Raises:
            Exception: If RPC call fails
        """
        if params is None:
            params = []

        request = OnechainRPCRequest(
            method=method,
            params=params,
        )

        try:
            response = await self.client.post(
                self.rpc_url,
                json=request.model_dump(),
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()

            rpc_response = OnechainRPCResponse(**response.json())

            if rpc_response.error:
                raise Exception(
                    f"RPC error: {rpc_response.error.get('message', 'Unknown error')}"
                )

            return rpc_response.result

        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling RPC method {method}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error calling RPC method {method}: {e}")
            raise

    # ========================================================================
    # BLOCKCHAIN DATA
    # ========================================================================

    async def get_latest_checkpoint(self) -> int:
        """
        Get latest checkpoint (similar to block number).

        Returns:
            Latest checkpoint sequence number
        """
        try:
            result = await self._call_rpc("sui_getLatestCheckpointSequenceNumber")
            return int(result)
        except Exception as e:
            logger.error(f"Error getting latest checkpoint: {e}")
            return 0

    async def get_checkpoint(self, sequence_number: int) -> dict[str, Any] | None:
        """
        Get checkpoint data.

        Args:
            sequence_number: Checkpoint sequence number

        Returns:
            Checkpoint data or None
        """
        try:
            result = await self._call_rpc("sui_getCheckpoint", [str(sequence_number)])
            return result
        except Exception:
            logger.exception(f"Error getting checkpoint {sequence_number}")
            return None

    async def get_transaction(
        self,
        digest: str,
    ) -> OnechainTransaction | None:
        """
        Get transaction by digest (hash).

        Args:
            digest: Transaction digest/hash

        Returns:
            Transaction data or None
        """
        try:
            result = await self._call_rpc(
                "sui_getTransactionBlock",
                [
                    digest,
                    {
                        "showInput": True,
                        "showEffects": True,
                        "showEvents": True,
                    },
                ],
            )

            if not result:
                return None

            # Parse events
            events: list[OnechainEventData] = []
            if "events" in result:
                for event_data in result["events"]:
                    try:
                        event = OnechainEventData(**event_data)
                        events.append(event)
                    except Exception:
                        logger.warning(f"Failed to parse event: {event_data}")

            return OnechainTransaction(
                digest=result["digest"],
                timestamp_ms=result.get("timestampMs", 0),
                checkpoint=result.get("checkpoint"),
                effects=result.get("effects", {}),
                events=events,
            )

        except Exception:
            logger.exception(f"Error getting transaction {digest}")
            return None

    # ========================================================================
    # EVENTS
    # ========================================================================

    async def query_events(
        self,
        event_type: str,
        from_checkpoint: int,
        to_checkpoint: int | None = None,
    ) -> list[OnechainEventData]:
        """
        Query events by type.

        Args:
            event_type: Full event type (e.g., "0x123::market::PositionOpened")
            from_checkpoint: Starting checkpoint
            to_checkpoint: Ending checkpoint (None for latest)

        Returns:
            List of events
        """
        try:
            # Build event filter
            query = {"MoveEventType": f"{self.package_id}::{event_type}"}

            # Query events
            result = await self._call_rpc(
                "suix_queryEvents",
                [
                    query,
                    None,  # Cursor for pagination
                    100,  # Limit
                    False,  # Descending order
                ],
            )
            logger.debug(f"Event query result: {result}")

            if not result or "data" not in result:
                return []

            events: list[OnechainEventData] = []
            for event_data in result["data"]:
                try:
                    logger.debug(f"Event data onechain: {event_data}")
                    event = OnechainEventData(**event_data)

                    # Filter by checkpoint range
                    if event.timestamp_ms:
                        # Note: In production, you'd need checkpoint-to-timestamp mapping
                        events.append(event)

                except Exception:
                    logger.warning(f"Failed to parse event: {event_data}")

            return events

        except Exception:
            logger.exception(f"Error querying events {event_type}")
            return []

    # ========================================================================
    # OBJECT QUERIES
    # ========================================================================

    async def get_object(self, object_id: str) -> dict[str, Any] | None:
        """
        Get object data by ID.

        Args:
            object_id: Object ID (position, market, etc.)

        Returns:
            Object data or None
        """
        try:
            result = await self._call_rpc(
                "sui_getObject",
                [
                    object_id,
                    {
                        "showType": True,
                        "showContent": True,
                        "showOwner": True,
                    },
                ],
            )

            return result.get("data") if result else None

        except Exception:
            logger.exception(f"Error getting object {object_id}")
            return None

    async def get_position(self, position_id: str) -> dict[str, Any] | None:
        """
        Get position data from Onechain.

        Args:
            position_id: Position object ID

        Returns:
            Position data or None
        """
        try:
            obj = await self.get_object(position_id)

            if not obj or "content" not in obj:
                return None

            content = obj["content"]
            if "fields" not in content:
                return None

            fields = content["fields"]

            # Parse position fields
            return {
                "id": position_id,
                "user": fields.get("user"),
                "market_id": fields.get("market_id"),
                "size": Decimal(fields.get("size", "0")) / SCALE,
                "collateral": Decimal(fields.get("collateral", "0")) / SCALE,
                "entry_price": Decimal(fields.get("entry_price", "0")) / SCALE,
                "leverage": Decimal(fields.get("leverage", "0")) / Decimal(10**2),
                "is_long": fields.get("is_long", True),
                "accumulated_funding": Decimal(fields.get("accumulated_funding", "0"))
                / SCALE,
            }

        except Exception:
            logger.exception(f"Error getting position {position_id}")
            return None

    # ========================================================================
    # EVENT PARSING
    # ========================================================================

    def parse_position_opened_event(
        self,
        event: OnechainEventData,
    ) -> PositionOpenedEvent | None:
        """
        Parse PositionOpened event.

        Args:
            event: Raw event data

        Returns:
            Parsed event or None
        """
        try:
            data = event.parsed_json

            return PositionOpenedEvent(
                user=data["owner"],
                market_id=data["market_id"],
                position_id=data["position_id"],
                size=Decimal(data["size"]) / SCALE,
                collateral=Decimal(data["collateral"]) / SCALE,
                entry_price=Decimal(data["entry_price"]) / SCALE,
                direction=int(data["direction"]),  # 0 = long, 1 = short
                timestamp=int(data["timestamp"]),
            )

        except Exception:
            logger.exception("Error parsing PositionOpened event")
            return None

    def parse_position_closed_event(
        self,
        event: OnechainEventData,
    ) -> PositionClosedEvent | None:
        """
        Parse PositionClosed event.

        Args:
            event: Raw event data

        Returns:
            Parsed event or None
        """
        try:
            data = event.parsed_json

            return PositionClosedEvent(
                user=data["owner"],
                market_id=data["market_id"],
                position_id=data["position_id"],
                close_price=Decimal(data["close_price"]) / SCALE,
                size=Decimal(data["size"]) / SCALE,
                collateral_returned=Decimal(data["collateral_returned"]) / SCALE,
                pnl=Decimal(data["pnl"]) / SCALE,
                is_profit=bool(data["is_profit"]),
            )

        except Exception:
            logger.exception("Error parsing PositionClosed event")
            return None

    def parse_position_updated_event(
        self,
        event: OnechainEventData,
    ) -> PositionUpdatedEvent | None:
        """
        Parse PositionUpdated event.

        Args:
            event: Raw event data

        Returns:
            Parsed PositionUpdatedEvent or None
        """
        try:
            data = event.parsed_json

            return PositionUpdatedEvent(
                user=data["owner"],
                market_id=data["market_id"],
                position_id=data["position_id"],
                new_size=Decimal(data["new_size"]) / SCALE,
                new_collateral=Decimal(data["new_collateral"]) / SCALE,
                new_entry_price=Decimal(data["new_entry_price"]) / SCALE,
                direction=int(data["direction"]),
                timestamp=int(data["timestamp"]),
            )

        except Exception:
            logger.exception("Error parsing PositionUpdated event")
            return None

    def parse_position_liquidated_event(
        self,
        event: OnechainEventData,
    ) -> PositionLiquidatedEvent | None:
        """
        Parse PositionLiquidated on-chain event.
        """
        try:
            data = event.parsed_json
            return PositionLiquidatedEvent(
                position_id=data["position_id"],
                owner=data["owner"],
                liquidator=data["liquidator"],
                market_id=data["market_id"],
                size=Decimal(data["size"]) / SCALE,
                collateral=Decimal(data["collateral"]) / SCALE,
                pnl=Decimal(data["pnl"]) / SCALE,
                amount_returned_to_liquidator=Decimal(
                    data.get("amount_returned_to_liquidator", "0")
                )
                / SCALE,
                timestamp=int(data["timestamp"]),
                # off-chain, set sau
                liquidation_fee=Decimal("0"),
            )

        except Exception:
            logger.exception("Error parsing PositionLiquidated event")
            return None


# Global service instance
blockchain_service = BlockchainService()

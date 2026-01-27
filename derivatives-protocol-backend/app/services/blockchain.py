import random
from decimal import Decimal
from typing import Any, Dict, List, Optional

from loguru import logger
from web3 import Web3
from web3.middleware import geth_poa_middleware

from app.core.config import settings


class BlockchainService:
    """Service for interacting with blockchain and smart contracts."""

    def __init__(self):
        self.rpc_url = settings.rpc_url
        self.chain_id = settings.chain_id
        self.contract_address = settings.contract_address

        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))

        # Add PoA middleware if needed (for BSC, Polygon, etc.)
        if self.chain_id in [56, 97, 137, 80001]:  # BSC, Polygon chains
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)

        # Contract ABI (simplified - you'll need the full ABI)
        self.contract_abi = self._get_contract_abi()
        self.contract = None

        if self.w3.is_connected():
            self.contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.contract_address),
                abi=self.contract_abi,
            )
            logger.info(f"Connected to blockchain at {self.rpc_url}")
        else:
            logger.error(f"Failed to connect to blockchain at {self.rpc_url}")

    def _get_contract_abi(self) -> List[Dict[str, Any]]:
        """
        Get contract ABI.

        In production, load this from a file or from the contract deployment.
        This is a simplified version.
        """
        return [
            # Market functions
            {
                "inputs": [{"name": "marketId", "type": "bytes32"}],
                "name": "getMarket",
                "outputs": [
                    {"name": "baseToken", "type": "address"},
                    {"name": "quoteToken", "type": "address"},
                    {"name": "maxLeverage", "type": "uint256"},
                    {"name": "maintenanceMarginRate", "type": "uint256"},
                ],
                "stateMutability": "view",
                "type": "function",
            },
            # Position functions
            {
                "inputs": [{"name": "positionId", "type": "bytes32"}],
                "name": "getPosition",
                "outputs": [
                    {"name": "user", "type": "address"},
                    {"name": "marketId", "type": "bytes32"},
                    {"name": "size", "type": "uint256"},
                    {"name": "collateral", "type": "uint256"},
                    {"name": "entryPrice", "type": "uint256"},
                    {"name": "isLong", "type": "bool"},
                ],
                "stateMutability": "view",
                "type": "function",
            },
            # Events
            {
                "anonymous": False,
                "inputs": [
                    {"indexed": True, "name": "positionId", "type": "bytes32"},
                    {"indexed": True, "name": "user", "type": "address"},
                    {"indexed": True, "name": "marketId", "type": "bytes32"},
                    {"indexed": False, "name": "size", "type": "uint256"},
                    {"indexed": False, "name": "collateral", "type": "uint256"},
                    {"indexed": False, "name": "leverage", "type": "uint256"},
                    {"indexed": False, "name": "entryPrice", "type": "uint256"},
                    {"indexed": False, "name": "isLong", "type": "bool"},
                ],
                "name": "PositionOpened",
                "type": "event",
            },
            {
                "anonymous": False,
                "inputs": [
                    {"indexed": True, "name": "positionId", "type": "bytes32"},
                    {"indexed": True, "name": "user", "type": "address"},
                    {"indexed": False, "name": "exitPrice", "type": "uint256"},
                    {"indexed": False, "name": "pnl", "type": "int256"},
                ],
                "name": "PositionClosed",
                "type": "event",
            },
            {
                "anonymous": False,
                "inputs": [
                    {"indexed": True, "name": "positionId", "type": "bytes32"},
                    {"indexed": True, "name": "user", "type": "address"},
                    {"indexed": True, "name": "liquidator", "type": "address"},
                    {"indexed": False, "name": "liquidationPrice", "type": "uint256"},
                    {"indexed": False, "name": "liquidationFee", "type": "uint256"},
                ],
                "name": "PositionLiquidated",
                "type": "event",
            },
        ]

    async def get_latest_block(self) -> int:
        """Get latest block number."""
        try:
            return self.w3.eth.block_number
        except Exception as e:
            logger.error(f"Error getting latest block: {e}")
            return 0

    async def get_position_from_chain(
        self, position_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get position data from smart contract.

        Args:
            position_id: Position ID (hex string)

        Returns:
            Position data or None
        """
        try:
            if not self.contract:
                logger.error("Contract not initialized")
                return None

            # Convert position_id to bytes32
            position_id_bytes = Web3.to_bytes(hexstr=position_id)

            result = self.contract.functions.getPosition(position_id_bytes).call()

            return {
                "user": result[0],
                "market_id": Web3.to_hex(result[1]),
                "size": Decimal(result[2]) / Decimal(10**18),
                "collateral": Decimal(result[3]) / Decimal(10**18),
                "entry_price": Decimal(result[4]) / Decimal(10**18),
                "is_long": result[5],
            }

        except Exception as e:
            logger.error(f"Error getting position {position_id}: {e}")
            return None

    async def get_events(
        self,
        event_name: str,
        from_block: int,
        to_block: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get contract events.

        Args:
            event_name: Event name (e.g., "PositionOpened")
            from_block: Starting block number
            to_block: Ending block number (None for latest)

        Returns:
            List of event logs
        """
        try:
            if not self.contract:
                logger.error("Contract not initialized")
                return []

            if to_block is None:
                to_block = await self.get_latest_block()

            event = getattr(self.contract.events, event_name)
            events = event.create_filter(
                fromBlock=from_block, toBlock=to_block
            ).get_all_entries()

            return [self._format_event(e) for e in events]

        except Exception as e:
            logger.error(f"Error getting events {event_name}: {e}")
            return []

    def _format_event(self, event: Any) -> Dict[str, Any]:
        """Format event log to dict."""
        return {
            "event": event.event,
            "address": event.address,
            "block_number": event.blockNumber,
            "transaction_hash": Web3.to_hex(event.transactionHash),
            "log_index": event.logIndex,
            "args": dict(event.args),
        }

    async def estimate_gas(
        self,
        function_call: Any,
        from_address: str,
    ) -> int:
        """
        Estimate gas for a transaction.

        Args:
            function_call: Contract function call
            from_address: Sender address

        Returns:
            Estimated gas
        """
        try:
            gas = function_call.estimate_gas({"from": from_address})
            # Add 20% buffer
            return int(gas * 1.2)
        except Exception as e:
            logger.error(f"Error estimating gas: {e}")
            return settings.liquidation_gas_limit

    def calculate_health_factor(
        self,
        collateral: Decimal,
        position_size: Decimal,
        entry_price: Decimal,
        current_price: Decimal,
        is_long: bool,
        maintenance_margin_rate: Decimal,
        accumulated_funding: Decimal = Decimal("0"),
    ) -> Decimal:
        """
        Calculate position health factor.

        Health Factor = Equity / Maintenance Margin

        Args:
            collateral: Position collateral
            position_size: Position size
            entry_price: Entry price
            current_price: Current market price
            is_long: True if long position
            maintenance_margin_rate: Maintenance margin rate
            accumulated_funding: Accumulated funding payments

        Returns:
            Health factor (1.0 or below means liquidatable)
        """
        # Calculate unrealized PnL
        if is_long:
            pnl = position_size * (current_price - entry_price)
        else:
            pnl = position_size * (entry_price - current_price)

        # Calculate equity
        equity = collateral + pnl - accumulated_funding

        # Calculate maintenance margin requirement
        position_value = position_size * current_price
        maintenance_margin = position_value * maintenance_margin_rate

        # Avoid division by zero
        if maintenance_margin == 0:
            return Decimal("999999")

        health_factor = equity / maintenance_margin

        return health_factor

    def calculate_liquidation_price(
        self,
        entry_price: Decimal,
        leverage: Decimal,
        is_long: bool,
        maintenance_margin_rate: Decimal,
    ) -> Decimal:
        """
        Calculate liquidation price.

        For Long: Liq Price = Entry Price * (1 - 1/Leverage + MMR)
        For Short: Liq Price = Entry Price * (1 + 1/Leverage - MMR)

        Args:
            entry_price: Entry price
            leverage: Position leverage
            is_long: True if long position
            maintenance_margin_rate: Maintenance margin rate

        Returns:
            Liquidation price
        """
        leverage_factor = Decimal("1") / leverage

        if is_long:
            # Long liquidation price
            liq_price = entry_price * (
                Decimal("1") - leverage_factor + maintenance_margin_rate
            )
        else:
            # Short liquidation price
            liq_price = entry_price * (
                Decimal("1") + leverage_factor - maintenance_margin_rate
            )

        return max(liq_price, Decimal("0"))


class BlockchainServiceMock:
    """Mock version of BlockchainService (no RPC, no contract)."""

    def __init__(self):
        logger.warning("⚠️ Using BlockchainServiceMock (NO ON-CHAIN CONNECTION)")

        # Fake in-memory data
        self._positions: Dict[str, Dict[str, Any]] = {
            "0xpos1": {
                "user": "0x1111111111111111111111111111111111111111",
                "market_id": "BTC-PERP",
                "size": Decimal("0.1"),
                "collateral": Decimal("500"),
                "entry_price": Decimal("50000"),
                "is_long": True,
            }
        }

        self._events: List[Dict[str, Any]] = []

        self._block_number = 1

    # ------------------------------------------------------------------
    # BLOCK
    # ------------------------------------------------------------------

    async def get_latest_block(self) -> int:
        self._block_number += 1
        return self._block_number

    # ------------------------------------------------------------------
    # POSITION
    # ------------------------------------------------------------------

    async def get_position_from_chain(
        self, position_id: str
    ) -> Optional[Dict[str, Any]]:
        position = self._positions.get(position_id)

        if not position:
            logger.warning(f"[MOCK] Position {position_id} not found")

        return position

    # ------------------------------------------------------------------
    # EVENTS
    # ------------------------------------------------------------------

    async def get_events(
        self,
        event_name: str,
        from_block: int,
        to_block: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        return [
            e
            for e in self._events
            if e["event"] == event_name
            and from_block <= e["block_number"] <= (to_block or self._block_number)
        ]

    def _format_event(self, event: Any) -> Dict[str, Any]:
        """Kept for interface compatibility."""
        return event

    # ------------------------------------------------------------------
    # GAS
    # ------------------------------------------------------------------

    async def estimate_gas(
        self,
        function_call: Any,
        from_address: str,
    ) -> int:
        return 500_000

    # ------------------------------------------------------------------
    # RISK ENGINE (GIỮ NGUYÊN LOGIC GỐC)
    # ------------------------------------------------------------------

    def calculate_health_factor(
        self,
        collateral: Decimal,
        position_size: Decimal,
        entry_price: Decimal,
        current_price: Decimal,
        is_long: bool,
        maintenance_margin_rate: Decimal,
        accumulated_funding: Decimal = Decimal("0"),
    ) -> Decimal:
        if is_long:
            pnl = position_size * (current_price - entry_price)
        else:
            pnl = position_size * (entry_price - current_price)

        equity = collateral + pnl - accumulated_funding
        maintenance_margin = position_size * current_price * maintenance_margin_rate

        if maintenance_margin == 0:
            return Decimal("999999")

        return equity / maintenance_margin

    def calculate_liquidation_price(
        self,
        entry_price: Decimal,
        leverage: Decimal,
        is_long: bool,
        maintenance_margin_rate: Decimal,
    ) -> Decimal:
        inv_leverage = Decimal("1") / leverage

        if is_long:
            price = entry_price * (
                Decimal("1") - inv_leverage + maintenance_margin_rate
            )
        else:
            price = entry_price * (
                Decimal("1") + inv_leverage - maintenance_margin_rate
            )

        return max(price, Decimal("0"))

    # ------------------------------------------------------------------
    # MOCK HELPERS (OPTIONAL – KHÔNG ẢNH HƯỞNG INTERFACE)
    # ------------------------------------------------------------------

    def _mock_open_position(self):
        """Create fake position + event (optional helper)."""
        pid = f"0xpos{len(self._positions) + 1}"

        entry_price = Decimal(random.randint(45000, 55000))

        self._positions[pid] = {
            "user": "0xMockUser",
            "market_id": "BTC-PERP",
            "size": Decimal("0.05"),
            "collateral": Decimal("300"),
            "entry_price": entry_price,
            "is_long": True,
        }

        self._events.append(
            {
                "event": "PositionOpened",
                "address": "0xMockContract",
                "block_number": self._block_number,
                "transaction_hash": f"0xtx{pid}",
                "log_index": 0,
                "args": self._positions[pid],
            }
        )


# Global blockchain service instance
blockchain_service = BlockchainServiceMock()

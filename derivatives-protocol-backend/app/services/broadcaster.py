import asyncio
from typing import Dict, Any
from datetime import datetime
from loguru import logger

from app.services.websocket import manager


class EventBroadcaster:
    """
    Service for broadcasting blockchain events to WebSocket clients.
    
    Listens to events from the indexer and broadcasts them to connected clients.
    """
    
    def __init__(self):
        self.is_running = False
    
    async def start(self):
        """Start the broadcaster."""
        self.is_running = True
        logger.info("Event broadcaster started")
    
    async def stop(self):
        """Stop the broadcaster."""
        self.is_running = False
        logger.info("Event broadcaster stopped")
    
    async def broadcast_position_opened(
        self,
        position_id: str,
        user_address: str,
        market_id: str,
        side: str,
        size: str,
        collateral: str,
        leverage: str,
        entry_price: str,
        transaction_hash: str,
    ):
        """
        Broadcast PositionOpened event.
        
        Args:
            position_id: Position identifier
            user_address: User wallet address
            market_id: Market identifier
            side: Position side (long/short)
            size: Position size
            collateral: Collateral amount
            leverage: Position leverage
            entry_price: Entry price
            transaction_hash: Transaction hash
        """
        message = {
            "type": "position_opened",
            "data": {
                "position_id": position_id,
                "user_address": user_address,
                "market_id": market_id,
                "side": side,
                "size": size,
                "collateral": collateral,
                "leverage": leverage,
                "entry_price": entry_price,
                "transaction_hash": transaction_hash,
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Broadcast to user's connections
        await manager.broadcast_to_user(message, user_address)
        
        # Broadcast to market watchers
        await manager.broadcast_to_market(message, market_id)
        
        logger.info(f"Broadcasted PositionOpened: {position_id}")
    
    async def broadcast_position_closed(
        self,
        position_id: str,
        user_address: str,
        market_id: str,
        exit_price: str,
        realized_pnl: str,
        transaction_hash: str,
    ):
        """
        Broadcast PositionClosed event.
        
        Args:
            position_id: Position identifier
            user_address: User wallet address
            market_id: Market identifier
            exit_price: Exit price
            realized_pnl: Realized PnL
            transaction_hash: Transaction hash
        """
        message = {
            "type": "position_closed",
            "data": {
                "position_id": position_id,
                "user_address": user_address,
                "market_id": market_id,
                "exit_price": exit_price,
                "realized_pnl": realized_pnl,
                "transaction_hash": transaction_hash,
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Broadcast to user
        await manager.broadcast_to_user(message, user_address)
        
        # Broadcast to market
        await manager.broadcast_to_market(message, market_id)
        
        logger.info(f"Broadcasted PositionClosed: {position_id}")
    
    async def broadcast_position_liquidated(
        self,
        position_id: str,
        user_address: str,
        market_id: str,
        liquidator_address: str,
        liquidation_price: str,
        liquidation_fee: str,
        transaction_hash: str,
    ):
        """
        Broadcast PositionLiquidated event.
        
        Args:
            position_id: Position identifier
            user_address: User wallet address
            market_id: Market identifier
            liquidator_address: Liquidator address
            liquidation_price: Liquidation price
            liquidation_fee: Liquidation fee
            transaction_hash: Transaction hash
        """
        message = {
            "type": "position_liquidated",
            "data": {
                "position_id": position_id,
                "user_address": user_address,
                "market_id": market_id,
                "liquidator_address": liquidator_address,
                "liquidation_price": liquidation_price,
                "liquidation_fee": liquidation_fee,
                "transaction_hash": transaction_hash,
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Broadcast to user (important!)
        await manager.broadcast_to_user(message, user_address)
        
        # Broadcast to market
        await manager.broadcast_to_market(message, market_id)
        
        # Broadcast to all liquidation watchers
        await manager.broadcast(message, "liquidations")
        
        logger.warning(f"Broadcasted PositionLiquidated: {position_id}")
    
    async def broadcast_funding_rate_update(
        self,
        market_id: str,
        funding_rate: str,
        long_oi: str,
        short_oi: str,
    ):
        """
        Broadcast funding rate update.
        
        Args:
            market_id: Market identifier
            funding_rate: New funding rate
            long_oi: Long open interest
            short_oi: Short open interest
        """
        message = {
            "type": "funding_rate_update",
            "data": {
                "market_id": market_id,
                "funding_rate": funding_rate,
                "long_oi": long_oi,
                "short_oi": short_oi,
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Broadcast to market watchers
        await manager.broadcast_to_market(message, market_id)
        
        logger.info(f"Broadcasted funding rate update for {market_id}: {funding_rate}")
    
    async def broadcast_liquidation_alert(
        self,
        user_address: str,
        position_id: str,
        market_id: str,
        health_factor: str,
        liquidation_price: str,
    ):
        """
        Broadcast liquidation warning to user.
        
        Args:
            user_address: User wallet address
            position_id: Position identifier
            market_id: Market identifier
            health_factor: Current health factor
            liquidation_price: Liquidation price
        """
        message = {
            "type": "liquidation_warning",
            "data": {
                "position_id": position_id,
                "market_id": market_id,
                "health_factor": health_factor,
                "liquidation_price": liquidation_price,
                "message": "⚠️ Your position is at risk of liquidation!",
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Send to user only
        await manager.broadcast_to_user(message, user_address)
        
        logger.warning(f"Sent liquidation warning to {user_address} for position {position_id}")


# Global broadcaster instance
broadcaster = EventBroadcaster()

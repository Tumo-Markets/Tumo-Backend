from typing import Dict, Set, List, Optional
from fastapi import WebSocket
from loguru import logger
import asyncio
import json
from datetime import datetime


class ConnectionManager:
    """
    WebSocket connection manager.
    
    Manages multiple WebSocket connections and provides broadcasting capabilities.
    """
    
    def __init__(self):
        # Store active connections by type
        self.active_connections: Dict[str, Set[WebSocket]] = {
            "prices": set(),
            "positions": set(),
            "liquidations": set(),
            "events": set(),
        }
        
        # Store user-specific connections
        self.user_connections: Dict[str, Set[WebSocket]] = {}
        
        # Store market-specific connections
        self.market_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, connection_type: str):
        """
        Accept and register a new WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            connection_type: Type of connection (prices, positions, etc.)
        """
        await websocket.accept()
        
        if connection_type not in self.active_connections:
            self.active_connections[connection_type] = set()
        
        self.active_connections[connection_type].add(websocket)
        logger.info(f"New {connection_type} WebSocket connection. Total: {len(self.active_connections[connection_type])}")
    
    def disconnect(self, websocket: WebSocket, connection_type: str):
        """
        Remove a WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            connection_type: Type of connection
        """
        if connection_type in self.active_connections:
            self.active_connections[connection_type].discard(websocket)
            logger.info(f"WebSocket disconnected from {connection_type}. Remaining: {len(self.active_connections[connection_type])}")
        
        # Also remove from user/market specific connections
        for connections in self.user_connections.values():
            connections.discard(websocket)
        
        for connections in self.market_connections.values():
            connections.discard(websocket)
    
    async def connect_user(self, websocket: WebSocket, user_address: str):
        """
        Connect websocket for specific user.
        
        Args:
            websocket: WebSocket connection
            user_address: User wallet address
        """
        await websocket.accept()
        
        if user_address not in self.user_connections:
            self.user_connections[user_address] = set()
        
        self.user_connections[user_address].add(websocket)
        logger.info(f"User {user_address} connected. Total connections: {len(self.user_connections[user_address])}")
    
    async def connect_market(self, websocket: WebSocket, market_id: str):
        """
        Connect websocket for specific market.
        
        Args:
            websocket: WebSocket connection
            market_id: Market identifier
        """
        await websocket.accept()
        
        if market_id not in self.market_connections:
            self.market_connections[market_id] = set()
        
        self.market_connections[market_id].add(websocket)
        logger.info(f"Market {market_id} subscriber connected. Total: {len(self.market_connections[market_id])}")
    
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """
        Send message to specific WebSocket.
        
        Args:
            message: Message to send
            websocket: Target WebSocket
        """
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")
    
    async def broadcast(self, message: dict, connection_type: str):
        """
        Broadcast message to all connections of a type.
        
        Args:
            message: Message to broadcast
            connection_type: Type of connections to broadcast to
        """
        if connection_type not in self.active_connections:
            return
        
        connections = self.active_connections[connection_type].copy()
        
        # Remove dead connections
        dead_connections = set()
        
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to {connection_type}: {e}")
                dead_connections.add(connection)
        
        # Clean up dead connections
        for dead in dead_connections:
            self.disconnect(dead, connection_type)
    
    async def broadcast_to_user(self, message: dict, user_address: str):
        """
        Broadcast message to all connections of a specific user.
        
        Args:
            message: Message to broadcast
            user_address: User wallet address
        """
        if user_address not in self.user_connections:
            return
        
        connections = self.user_connections[user_address].copy()
        dead_connections = set()
        
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to user {user_address}: {e}")
                dead_connections.add(connection)
        
        # Clean up dead connections
        for dead in dead_connections:
            if user_address in self.user_connections:
                self.user_connections[user_address].discard(dead)
    
    async def broadcast_to_market(self, message: dict, market_id: str):
        """
        Broadcast message to all connections watching a specific market.
        
        Args:
            message: Message to broadcast
            market_id: Market identifier
        """
        if market_id not in self.market_connections:
            return
        
        connections = self.market_connections[market_id].copy()
        dead_connections = set()
        
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to market {market_id}: {e}")
                dead_connections.add(connection)
        
        # Clean up dead connections
        for dead in dead_connections:
            if market_id in self.market_connections:
                self.market_connections[market_id].discard(dead)
    
    def get_stats(self) -> dict:
        """Get connection statistics."""
        return {
            "total_connections": sum(len(conns) for conns in self.active_connections.values()),
            "by_type": {
                conn_type: len(conns) 
                for conn_type, conns in self.active_connections.items()
            },
            "user_connections": len(self.user_connections),
            "market_connections": len(self.market_connections),
        }


# Global connection manager instance
manager = ConnectionManager()

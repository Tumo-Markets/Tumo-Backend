"""
WebSocket Notifications Endpoint - PRIVATE CHANNEL

Real-time notification stream for each user.
Receives notifications from blockchain events instantly.
"""

import asyncio
from collections import deque
from decimal import Decimal

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from app.api.models import ConnectedMessage
from app.schemas.notifications import (
    BalanceUpdatedNotification,
    BaseNotification,
    FundingPaymentNotification,
    LiquidationWarningNotification,
    PositionClosedNotification,
    PositionLiquidatedNotification,
    PositionOpenedNotification,
)
from app.services.websocket import manager

# ============================================================================
# NOTIFICATION QUEUE MANAGER
# ============================================================================


class NotificationQueueManager:
    """
    Manages notification queues for connected users.

    When a blockchain event occurs:
    1. Indexer calls push_notification()
    2. Notification is queued for that user
    3. WebSocket sends it immediately to connected client
    """

    def __init__(self) -> None:
        # user_address -> deque of notifications
        self._queues: dict[str, deque[BaseNotification]] = {}

        # Maximum queue size per user
        self._max_queue_size: int = 100

    def push_notification(
        self,
        user_address: str,
        notification: BaseNotification,
    ) -> None:
        """
        Push a notification to user's queue.

        Called by:
        - Indexer when detecting blockchain events
        - Liquidation bot
        - Funding calculator
        - Any service that generates notifications

        Args:
            user_address: User wallet address
            notification: Notification to push
        """
        user_address_lower = user_address.lower()

        if user_address_lower not in self._queues:
            self._queues[user_address_lower] = deque(maxlen=self._max_queue_size)

        self._queues[user_address_lower].append(notification)

        logger.debug(
            f"Queued notification {notification.type.value} for {user_address_lower[:8]}..."
        )

    def get_pending_notifications(
        self,
        user_address: str,
    ) -> list[BaseNotification]:
        """
        Get all pending notifications for a user and clear queue.

        Args:
            user_address: User wallet address

        Returns:
            List of pending notifications
        """
        user_address_lower = user_address.lower()

        if user_address_lower not in self._queues:
            return []

        notifications = list(self._queues[user_address_lower])
        self._queues[user_address_lower].clear()

        return notifications

    def has_pending(self, user_address: str) -> bool:
        """Check if user has pending notifications."""
        user_address_lower = user_address.lower()
        return bool(self._queues.get(user_address_lower))

    def clear_queue(self, user_address: str) -> None:
        """Clear user's notification queue."""
        user_address_lower = user_address.lower()
        if user_address_lower in self._queues:
            del self._queues[user_address_lower]


# Global instance
notification_queue = NotificationQueueManager()


# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================


async def websocket_notifications(
    websocket: WebSocket,
    user_address: str,
) -> None:
    """
    WebSocket endpoint for user notifications.

    **Private channel** - each user only receives their own notifications.

    Features:
    - Real-time push when events occur
    - Sends pending notifications on connect
    - Auto-retry on temporary failures
    - Type-safe with Pydantic models

    Notifications include:
    - Position opened (order matched)
    - Position closed
    - Position liquidated
    - Balance updated
    - Funding payment
    - Liquidation warnings

    Args:
        websocket: WebSocket connection
        user_address: User wallet address
    """
    user_address_lower = user_address.lower()

    await manager.connect_user(websocket, user_address_lower)

    try:
        # Send connection success
        connected_msg = ConnectedMessage(
            message=f"Connected to notifications for {user_address_lower}"
        )
        await websocket.send_json(connected_msg.model_dump(mode="json"))

        # Send any pending notifications immediately
        pending = notification_queue.get_pending_notifications(user_address_lower)
        if pending:
            logger.info(
                f"Sending {len(pending)} pending notifications to {user_address_lower[:8]}..."
            )
            for notification in pending:
                try:
                    await websocket.send_json(notification.model_dump(mode="json"))
                except Exception as e:
                    logger.error(f"Error sending pending notification: {e}")

        # Main loop - check for new notifications
        while True:
            # Check queue for new notifications
            if notification_queue.has_pending(user_address_lower):
                notifications = notification_queue.get_pending_notifications(
                    user_address_lower
                )

                for notification in notifications:
                    try:
                        logger.info(
                            f"Sending {notification.type.value} notification "
                            + f"to {user_address_lower[:8]}..."
                        )

                        await websocket.send_json(notification.model_dump(mode="json"))

                    except Exception as e:
                        logger.error(
                            f"Error sending notification to {user_address_lower}: {e}"
                        )
                        # Re-queue if send failed
                        notification_queue.push_notification(
                            user_address_lower, notification
                        )

            # Check for new notifications every 100ms
            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        manager.disconnect(websocket, "notifications")
        logger.info(f"User {user_address_lower[:8]}... disconnected from notifications")

    except Exception as e:
        logger.exception(f"Error in notifications websocket: {e}")
        manager.disconnect(websocket, "notifications")

    finally:
        # Cleanup
        try:
            manager.disconnect(websocket, "notifications")
        except Exception:
            pass


# ============================================================================
# HELPER FUNCTIONS (Used by Indexer and other services)
# ============================================================================


def notify_position_opened(
    user_address: str,
    position_id: str,
    market_id: str,
    symbol: str,
    side: str,
    size: Decimal,
    entry_price: Decimal,
    leverage: Decimal,
    collateral: Decimal,
    liquidation_price: Decimal,
    tx_hash: str | None = None,
) -> None:
    """
    Helper to notify position opened.

    Called by indexer when position open event is detected.
    """

    notification = PositionOpenedNotification(
        user_address=user_address.lower(),
        message=f"✅ Position opened: {side.upper()} {size} {symbol} @ ${entry_price}",
        tx_hash=tx_hash,
        position_id=position_id,
        market_id=market_id,
        symbol=symbol,
        side=side,
        size=Decimal(str(size)),
        entry_price=Decimal(str(entry_price)),
        leverage=Decimal(str(leverage)),
        collateral=Decimal(str(collateral)),
        liquidation_price=Decimal(str(liquidation_price)),
    )

    notification_queue.push_notification(user_address.lower(), notification)


def notify_position_closed(
    user_address: str,
    position_id: str,
    market_id: str,
    symbol: str,
    side: str,
    size: Decimal,
    entry_price: Decimal,
    exit_price: Decimal,
    realized_pnl: Decimal,
    new_balance: Decimal,
    tx_hash: str | None = None,
) -> None:
    """
    Helper to notify position closed.

    Called by indexer when position close event is detected.
    """

    is_profit = realized_pnl > 0
    emoji = "🟢" if is_profit else "🔴"

    notification = PositionClosedNotification(
        user_address=user_address.lower(),
        message=f"{emoji} Position closed: {side.upper()} {size} {symbol} | "
        + f"PnL: ${realized_pnl:,.2f}",
        tx_hash=tx_hash,
        position_id=position_id,
        market_id=market_id,
        symbol=symbol,
        side=side,
        size=Decimal(str(size)),
        entry_price=Decimal(str(entry_price)),
        exit_price=Decimal(str(exit_price)),
        realized_pnl=Decimal(str(realized_pnl)),
        is_profit=is_profit,
        new_balance=Decimal(str(new_balance)),
    )

    notification_queue.push_notification(user_address.lower(), notification)


def notify_position_liquidated(
    user_address: str,
    position_id: str,
    market_id: str,
    symbol: str,
    side: str,
    size: Decimal,
    entry_price: Decimal,
    liquidation_price: Decimal,
    realized_pnl: Decimal,
    liquidation_fee: Decimal,
    new_balance: Decimal,
    tx_hash: str | None = None,
) -> None:
    """
    Helper to notify position liquidated.

    Called by liquidation bot when liquidation occurs.
    """

    notification = PositionLiquidatedNotification(
        user_address=user_address.lower(),
        message=f"⚠️ LIQUIDATED: {side.upper()} {size} {symbol} @ ${liquidation_price} | "
        + f"Loss: ${abs(realized_pnl):,.2f}",
        tx_hash=tx_hash,
        position_id=position_id,
        market_id=market_id,
        symbol=symbol,
        side=side,
        size=Decimal(str(size)),
        entry_price=Decimal(str(entry_price)),
        liquidation_price=Decimal(str(liquidation_price)),
        realized_pnl=Decimal(str(realized_pnl)),
        liquidation_fee=Decimal(str(liquidation_fee)),
        new_balance=Decimal(str(new_balance)),
    )

    notification_queue.push_notification(user_address.lower(), notification)


def notify_liquidation_warning(
    user_address: str,
    position_id: str,
    market_id: str,
    symbol: str,
    health_factor: Decimal,
    current_price: Decimal,
    liquidation_price: Decimal,
) -> None:
    """
    Helper to notify liquidation warning.

    Called by risk monitoring service.
    """

    distance = abs(current_price - liquidation_price) / current_price * 100

    notification = LiquidationWarningNotification(
        user_address=user_address.lower(),
        message=f"⚠️ LIQUIDATION WARNING: {symbol} position at risk | "
        + f"Health: {health_factor:.2f} | "
        + f"{distance:.1f}% to liquidation",
        position_id=position_id,
        market_id=market_id,
        symbol=symbol,
        health_factor=Decimal(str(health_factor)),
        current_price=Decimal(str(current_price)),
        liquidation_price=Decimal(str(liquidation_price)),
        distance_percentage=Decimal(str(distance)),
    )

    notification_queue.push_notification(user_address.lower(), notification)


def notify_balance_updated(
    user_address: str,
    old_balance: Decimal,
    new_balance: Decimal,
    reason: str,
    tx_hash: str | None = None,
) -> None:
    """
    Helper to notify balance updated.

    Called when user balance changes.
    """

    change = new_balance - old_balance
    emoji = "📈" if change > 0 else "📉"

    notification = BalanceUpdatedNotification(
        user_address=user_address.lower(),
        message=f"{emoji} Balance updated: ${new_balance:,.2f} ({reason})",
        tx_hash=tx_hash,
        old_balance=Decimal(str(old_balance)),
        new_balance=Decimal(str(new_balance)),
        change=Decimal(str(change)),
        reason=reason,
    )

    notification_queue.push_notification(user_address.lower(), notification)


def notify_funding_payment(
    user_address: str,
    position_id: str,
    market_id: str,
    symbol: str,
    funding_rate: Decimal,
    payment_amount: Decimal,
    is_payment: bool,
    new_balance: Decimal,
    tx_hash: str | None = None,
) -> None:
    """
    Helper to notify funding payment.

    Called by funding calculator.
    """

    action = "paid" if is_payment else "received"
    emoji = "💸" if is_payment else "💰"

    notification = FundingPaymentNotification(
        user_address=user_address.lower(),
        message=f"{emoji} Funding {action}: ${abs(payment_amount):,.4f} on {symbol}",
        tx_hash=tx_hash,
        position_id=position_id,
        market_id=market_id,
        symbol=symbol,
        funding_rate=Decimal(str(funding_rate)),
        payment_amount=Decimal(str(payment_amount)),
        is_payment=is_payment,
        new_balance=Decimal(str(new_balance)),
    )

    notification_queue.push_notification(user_address.lower(), notification)

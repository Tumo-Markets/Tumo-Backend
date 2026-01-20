"""
Notification Schemas for Real-Time Blockchain Events

Type-safe Pydantic models for all notification types.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

# ============================================================================
# NOTIFICATION TYPES
# ============================================================================


class NotificationType(str, Enum):
    """Types of notifications."""

    # Position events
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    POSITION_LIQUIDATED = "position_liquidated"
    POSITION_UPDATED = "position_updated"

    # Balance events
    BALANCE_UPDATED = "balance_updated"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"

    # Trading events
    FUNDING_PAYMENT = "funding_payment"
    PNL_REALIZED = "pnl_realized"

    # Risk events
    MARGIN_CALL = "margin_call"
    LIQUIDATION_WARNING = "liquidation_warning"

    # System events
    MARKET_HALTED = "market_halted"
    MARKET_RESUMED = "market_resumed"


class NotificationPriority(str, Enum):
    """Notification priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


# ============================================================================
# BASE NOTIFICATION
# ============================================================================


class BaseNotification(BaseModel):
    """Base class for all notifications."""

    model_config = ConfigDict(json_encoders={Decimal: str})

    type: NotificationType
    priority: NotificationPriority = Field(default=NotificationPriority.NORMAL)
    user_address: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message: str
    tx_hash: str | None = None


# ============================================================================
# POSITION NOTIFICATIONS
# ============================================================================


class PositionOpenedNotification(BaseNotification):
    """Notification when position is opened (order matched)."""

    type: NotificationType = Field(default=NotificationType.POSITION_OPENED)
    priority: NotificationPriority = Field(default=NotificationPriority.HIGH)

    position_id: str
    market_id: str
    symbol: str
    side: str  # "long" or "short"
    size: Decimal
    entry_price: Decimal
    leverage: Decimal
    collateral: Decimal
    liquidation_price: Decimal


class PositionClosedNotification(BaseNotification):
    """Notification when position is closed."""

    type: NotificationType = Field(default=NotificationType.POSITION_CLOSED)
    priority: NotificationPriority = Field(default=NotificationPriority.HIGH)

    position_id: str
    market_id: str
    symbol: str
    side: str
    size: Decimal
    entry_price: Decimal
    exit_price: Decimal
    realized_pnl: Decimal
    is_profit: bool
    new_balance: Decimal


class PositionLiquidatedNotification(BaseNotification):
    """Notification when position is liquidated."""

    type: NotificationType = Field(default=NotificationType.POSITION_LIQUIDATED)
    priority: NotificationPriority = Field(default=NotificationPriority.CRITICAL)

    position_id: str
    market_id: str
    symbol: str
    side: str
    size: Decimal
    entry_price: Decimal
    liquidation_price: Decimal
    realized_pnl: Decimal
    liquidation_fee: Decimal
    new_balance: Decimal


# ============================================================================
# BALANCE NOTIFICATIONS
# ============================================================================


class BalanceUpdatedNotification(BaseNotification):
    """Notification when balance changes."""

    type: NotificationType = Field(default=NotificationType.BALANCE_UPDATED)

    old_balance: Decimal
    new_balance: Decimal
    change: Decimal
    reason: str  # "position_closed", "funding", "deposit", "withdrawal"


# ============================================================================
# TRADING NOTIFICATIONS
# ============================================================================


class FundingPaymentNotification(BaseNotification):
    """Notification for funding payment."""

    type: NotificationType = Field(default=NotificationType.FUNDING_PAYMENT)

    position_id: str
    market_id: str
    symbol: str
    funding_rate: Decimal
    payment_amount: Decimal  # Negative = paid, Positive = received
    is_payment: bool  # True if paying out, False if receiving
    new_balance: Decimal


# ============================================================================
# RISK NOTIFICATIONS
# ============================================================================


class LiquidationWarningNotification(BaseNotification):
    """Warning when position health is critical."""

    type: NotificationType = Field(default=NotificationType.LIQUIDATION_WARNING)
    priority: NotificationPriority = Field(default=NotificationPriority.CRITICAL)

    position_id: str
    market_id: str
    symbol: str
    health_factor: Decimal
    current_price: Decimal
    liquidation_price: Decimal
    distance_percentage: Decimal  # % distance to liquidation

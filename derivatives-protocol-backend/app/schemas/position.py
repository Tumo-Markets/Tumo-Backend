from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, field_validator, computed_field
from enum import Enum


class PositionSide(str, Enum):
    """Position side enum."""
    LONG = "long"
    SHORT = "short"


class PositionStatus(str, Enum):
    """Position status enum."""
    OPEN = "open"
    CLOSED = "closed"
    LIQUIDATED = "liquidated"


class PositionBase(BaseModel):
    """Base position schema."""
    position_id: str = Field(..., description="Unique position identifier from blockchain")
    market_id: str = Field(..., description="Market identifier")
    user_address: str = Field(..., description="User wallet address")
    
    side: PositionSide = Field(..., description="Long or Short")
    size: Decimal = Field(..., gt=0, description="Position size in base token")
    collateral: Decimal = Field(..., gt=0, description="Collateral amount")
    leverage: Decimal = Field(..., ge=1, le=100, description="Position leverage")
    
    entry_price: Decimal = Field(..., gt=0, description="Entry price")
    
    @field_validator("size", "collateral", "leverage", "entry_price", mode="before")
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert to Decimal."""
        if isinstance(v, str):
            return Decimal(v)
        elif isinstance(v, (int, float)):
            return Decimal(str(v))
        return v


class PositionCreate(PositionBase):
    """Schema for creating a position."""
    block_number: int = Field(..., description="Block number when position was created")
    transaction_hash: str = Field(..., description="Transaction hash")


class PositionUpdate(BaseModel):
    """Schema for updating a position."""
    size: Optional[Decimal] = None
    collateral: Optional[Decimal] = None
    realized_pnl: Optional[Decimal] = None
    accumulated_funding: Optional[Decimal] = None
    
    @field_validator("size", "collateral", "realized_pnl", "accumulated_funding", mode="before")
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert to Decimal."""
        if v is None:
            return v
        if isinstance(v, str):
            return Decimal(v)
        elif isinstance(v, (int, float)):
            return Decimal(str(v))
        return v


class PositionClose(BaseModel):
    """Schema for closing a position."""
    exit_price: Decimal = Field(..., gt=0, description="Exit price")
    realized_pnl: Decimal = Field(..., description="Realized PnL")
    close_transaction_hash: str = Field(..., description="Close transaction hash")
    closed_at: datetime = Field(default_factory=datetime.utcnow)
    
    @field_validator("exit_price", "realized_pnl", mode="before")
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert to Decimal."""
        if isinstance(v, str):
            return Decimal(v)
        elif isinstance(v, (int, float)):
            return Decimal(str(v))
        return v


class Position(PositionBase):
    """Complete position schema with DB fields."""
    id: int
    status: PositionStatus = PositionStatus.OPEN
    
    exit_price: Optional[Decimal] = None
    realized_pnl: Decimal = Field(default=Decimal("0"))
    accumulated_funding: Decimal = Field(default=Decimal("0"))
    
    block_number: int
    transaction_hash: str
    close_transaction_hash: Optional[str] = None
    
    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None
    
    model_config = {
        "from_attributes": True,
        "json_encoders": {
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    }


class PositionWithPnL(Position):
    """Position with calculated PnL and health metrics."""
    current_price: Optional[Decimal] = None
    unrealized_pnl: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    
    margin_ratio: Decimal = Decimal("0")
    health_factor: Decimal = Decimal("0")
    liquidation_price: Optional[Decimal] = None
    
    is_at_risk: bool = False
    
    @computed_field
    @property
    def position_value(self) -> Decimal:
        """Calculate current position value."""
        if self.current_price:
            return self.size * self.current_price
        return Decimal("0")
    
    @computed_field
    @property
    def equity(self) -> Decimal:
        """Calculate current equity (collateral + unrealized PnL)."""
        return self.collateral + self.unrealized_pnl - self.accumulated_funding
    
    model_config = {
        "from_attributes": True,
        "json_encoders": {
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    }


class PositionSummary(BaseModel):
    """User position summary."""
    user_address: str
    total_positions: int
    open_positions: int
    total_collateral: Decimal
    total_unrealized_pnl: Decimal
    total_realized_pnl: Decimal
    
    model_config = {
        "json_encoders": {
            Decimal: str
        }
    }


class LiquidationCandidate(BaseModel):
    """Position eligible for liquidation."""
    position_id: str
    user_address: str
    market_id: str
    
    current_price: Decimal
    health_factor: Decimal
    liquidation_price: Decimal
    
    collateral: Decimal
    potential_reward: Decimal
    
    model_config = {
        "json_encoders": {
            Decimal: str
        }
    }

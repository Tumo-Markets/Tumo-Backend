from datetime import datetime
from decimal import Decimal
from typing import Optional, Generic, TypeVar, List
from pydantic import BaseModel, Field, field_validator


# Oracle Schemas
class PriceData(BaseModel):
    """Price data from Pyth oracle."""
    price_id: str = Field(..., description="Pyth price feed ID")
    price: Decimal = Field(..., description="Current price")
    confidence: Decimal = Field(..., description="Price confidence interval")
    expo: int = Field(..., description="Price exponent")
    publish_time: int = Field(..., description="Unix timestamp")
    
    @field_validator("price", "confidence", mode="before")
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert to Decimal."""
        if isinstance(v, str):
            return Decimal(v)
        elif isinstance(v, (int, float)):
            return Decimal(str(v))
        return v
    
    @property
    def normalized_price(self) -> Decimal:
        """Get price with exponent applied."""
        return self.price * Decimal(10) ** self.expo
    
    @property
    def age_seconds(self) -> int:
        """Get age of price in seconds."""
        return int(datetime.utcnow().timestamp()) - self.publish_time
    
    model_config = {
        "json_encoders": {
            Decimal: str
        }
    }


class PriceUpdate(BaseModel):
    """Price update data to be sent with transactions."""
    price_feed_id: str
    price_update_data: bytes
    publish_time: int
    
    model_config = {
        "arbitrary_types_allowed": True
    }


# Funding Rate Schemas
class FundingRate(BaseModel):
    """Funding rate data."""
    market_id: str
    funding_rate: Decimal
    timestamp: datetime
    long_oi: Decimal
    short_oi: Decimal
    
    @field_validator("funding_rate", "long_oi", "short_oi", mode="before")
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert to Decimal."""
        if isinstance(v, str):
            return Decimal(v)
        elif isinstance(v, (int, float)):
            return Decimal(str(v))
        return v
    
    model_config = {
        "json_encoders": {
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    }


class FundingRateHistory(BaseModel):
    """Historical funding rates."""
    market_id: str
    rates: List[FundingRate]
    
    model_config = {
        "json_encoders": {
            Decimal: str,
            datetime: lambda v: v.isoformat()
        }
    }


# Transaction Schemas
class TransactionStatus(BaseModel):
    """Transaction status."""
    transaction_hash: str
    status: str  # pending, confirmed, failed
    block_number: Optional[int] = None
    gas_used: Optional[int] = None
    timestamp: Optional[datetime] = None
    
    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat()
        }
    }


# Generic Response Schemas
T = TypeVar('T')


class ResponseBase(BaseModel, Generic[T]):
    """Generic response schema."""
    success: bool = True
    message: Optional[str] = None
    data: Optional[T] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response schema."""
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int
    
    @property
    def has_next(self) -> bool:
        """Check if there's a next page."""
        return self.page < self.total_pages
    
    @property
    def has_previous(self) -> bool:
        """Check if there's a previous page."""
        return self.page > 1


class ErrorResponse(BaseModel):
    """Error response schema."""
    success: bool = False
    error: str
    detail: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat()
        }
    }


# Health Check
class HealthCheck(BaseModel):
    """Health check response."""
    status: str = "healthy"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str
    
    database: bool = False
    redis: bool = False
    blockchain: bool = False
    oracle: bool = False
    
    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat()
        }
    }


# Statistics
class SystemStats(BaseModel):
    """System-wide statistics."""
    total_markets: int
    total_positions: int
    open_positions: int
    
    total_volume_24h: Decimal
    total_fees_24h: Decimal
    
    total_long_oi: Decimal
    total_short_oi: Decimal
    
    active_users_24h: int
    
    model_config = {
        "json_encoders": {
            Decimal: str
        }
    }

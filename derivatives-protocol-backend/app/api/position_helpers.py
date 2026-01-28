from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.models import (
    ClosePositionRequest,
    OpenPositionRequest,
    SponsoredTxRequest,
    SponsoredTxResponse,
)
from app.constants import TOKEN_ADDRESS_TO_SYMBOL
from app.db.models import MarketModel, PositionStatusEnum
from app.db.session import get_db
from app.schemas.common import ResponseBase
from app.schemas.position import PositionSide, PositionStatus
from app.services.contract_service.transaction_service import tx_service
from app.services.notifications import notify_position_closed, notify_position_opened
from app.services.oracle import oracle_service
from app.utils.calculations import calculate_liquidation_price, calculate_pnl

router = APIRouter(prefix="/positions", tags=["Position Helpers"])


# ============================================================================
# SCHEMAS
# ============================================================================


class TokenInPair(str, Enum):
    MARKET_TOKEN = "market_token"
    COLLATERAL_TOKEN = "collateral_token"


class PositionPreviewRequest(BaseModel):
    """Request to preview a position before opening."""

    market_id: str = Field(..., description="Market identifier")
    side: PositionSide = Field(..., description="Position side: long or short")
    size: Decimal = Field(..., gt=0, description="Position size")
    leverage: Decimal = Field(..., gt=0, le=500, description="Leverage (1-500)")
    token_type: TokenInPair = Field(..., description="Token in pair")

    class Config:
        json_schema_extra: dict[str, dict[str, str]] = {
            "example": {
                "market_id": "btc-usdh-perp",
                "side": "long",
                "size": "1.5",
                "leverage": "10",
                "token_type": "market_token",
            }
        }


class PositionPreviewResponse(BaseModel):
    """Preview of position parameters and risks."""

    market_id: str
    symbol: str
    collateral_in: str
    market_token: str
    available_balance: Decimal
    side: str
    size: Decimal
    leverage: Decimal
    entry_price: Decimal
    collateral_required: Decimal
    position_value: Decimal
    maintenance_margin: Decimal
    liquidation_price: Decimal
    max_loss: Decimal
    estimated_fees: Decimal
    total_cost: Decimal
    converted_size: Decimal

    class Config:
        json_schema_extra: dict[str, dict[str, str]] = {
            "example": {
                "market_id": "bnb-usdc-perp",
                "symbol": "BNB/USDC",
                "collateral_in": "USDH",
                "market_token": "BTC",
                "available_balance": "10000",
                "side": "long",
                "size": "1.5",
                "leverage": "10",
                "entry_price": "50000",
                "collateral_required": "7500",
                "position_value": "75000",
                "maintenance_margin": "3750",
                "liquidation_price": "47500",
                "max_loss": "7500",
                "estimated_fees": "75",
                "total_cost": "7575",
                "converted_size": "1.5",
            }
        }


class BuildOpenPositionRequest(BaseModel):
    """Request to build transaction data for opening position."""

    market_id: str
    side: PositionSide
    size: Decimal
    leverage: Decimal
    slippage_tolerance: Optional[Decimal] = Field(
        default=Decimal("0.01"), description="Max slippage (default 1%)"
    )


class BuildClosePositionRequest(BaseModel):
    """Request to build transaction data for closing position."""

    position_id: str
    slippage_tolerance: Optional[Decimal] = Field(default=Decimal("0.01"))


class TransactionDataResponse(BaseModel):
    """Transaction data that frontend can use to submit to blockchain."""

    contract_address: str
    function_name: str
    params: dict[str, Any]
    estimated_gas: str
    price_feed_id: str
    current_price: Decimal
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None


# ============================================================================
# HELPER ENDPOINTS
# ============================================================================


@router.post("/preview", response_model=ResponseBase[PositionPreviewResponse])
async def preview_position(
    request: PositionPreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Preview position parameters before opening.

    **Use case**: Frontend shows user what will happen if they open this position.

    Calculates:
    - Required collateral
    - Liquidation price
    - Max loss
    - Estimated fees

    This does NOT create a position, just simulates it.
    """
    # Get market
    stmt = select(MarketModel).where(MarketModel.market_id == request.market_id)
    result = await db.execute(stmt)
    market = result.scalar_one_or_none()

    # Get current price
    price_data = await oracle_service.get_latest_price(market.pyth_price_id)

    size: float = request.size
    if request.token_type == TokenInPair.COLLATERAL_TOKEN:
        size /= price_data.normalized_price
        converted_size = size
    else:
        converted_size = request.size * price_data.normalized_price

    if not market:
        raise HTTPException(
            status_code=404, detail=f"Market {request.market_id} not found"
        )

    if request.side not in ["long", "short"]:
        raise HTTPException(status_code=400, detail="Side must be 'long' or 'short'")

    # Check position size limits
    if size < market.min_position_size:
        raise HTTPException(
            status_code=400,
            detail=f"Position size must be at least {market.min_position_size}",
        )

    if size > market.max_position_size:
        raise HTTPException(
            status_code=400,
            detail=f"Position size cannot exceed {market.max_position_size}",
        )

    # Check leverage limits
    if request.leverage > market.max_leverage:
        raise HTTPException(
            status_code=400, detail=f"Leverage cannot exceed {market.max_leverage}x"
        )

    if not price_data:
        raise HTTPException(status_code=503, detail="Cannot fetch current price")

    entry_price = price_data.normalized_price

    # Calculate parameters
    position_value = converted_size
    collateral_required = position_value / request.leverage
    maintenance_margin = position_value * market.maintenance_margin_rate

    # Calculate liquidation price
    liquidation_price = calculate_liquidation_price(
        entry_price=entry_price,
        leverage=request.leverage,
        is_long=(request.side == PositionSide.LONG),
        maintenance_margin_rate=market.maintenance_margin_rate,
    )

    # Max loss is collateral (100% loss)
    max_loss = collateral_required

    # Estimate fees (trading fee - typically 0.1%)
    trading_fee_rate = Decimal("0.001")  # 0.1%
    estimated_fees = position_value * trading_fee_rate

    # Total cost = collateral + fees
    total_cost = collateral_required + estimated_fees

    quote_token_address = str(market.quote_token).lower()
    quote_asset_symbol = TOKEN_ADDRESS_TO_SYMBOL.get(quote_token_address, "UNKNOWN")

    # TODO:
    # - Fetch real user balance for quote_token from wallet / subaccount
    MOCK_USER_BALANCE = Decimal("10000")

    preview = PositionPreviewResponse(
        market_id=market.market_id,
        symbol=market.symbol,
        collateral_in=quote_asset_symbol,
        market_token=market.market_token,
        available_balance=MOCK_USER_BALANCE,
        side=request.side,
        size=request.size,
        leverage=request.leverage,
        entry_price=entry_price,
        collateral_required=collateral_required,
        position_value=position_value,
        maintenance_margin=maintenance_margin,
        liquidation_price=liquidation_price,
        max_loss=max_loss,
        estimated_fees=estimated_fees,
        total_cost=total_cost,
        converted_size=converted_size,
    )

    return ResponseBase(
        success=True, data=preview, message="Position preview calculated"
    )


@router.post("/build-open-tx", response_model=ResponseBase[TransactionDataResponse])
async def build_open_position_transaction(
    request: BuildOpenPositionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Build transaction data for opening a position.

    **Use case**: Frontend gets transaction data to submit to blockchain.

    Returns:
    - Contract address
    - Function name
    - Parameters
    - Estimated gas
    - Price feed info

    Frontend will:
    1. Get Pyth price update data (VAA)
    2. Call contract with these params + price update
    """
    # Get market
    stmt = select(MarketModel).where(MarketModel.market_id == request.market_id)
    result = await db.execute(stmt)
    market = result.scalar_one_or_none()

    if not market:
        raise HTTPException(
            status_code=404, detail=f"Market {request.market_id} not found"
        )

    # Get current price
    price_data = await oracle_service.get_latest_price(market.pyth_price_id)

    if not price_data:
        raise HTTPException(status_code=503, detail="Cannot fetch current price")

    current_price = price_data.normalized_price

    # Calculate slippage bounds
    slippage = request.slippage_tolerance
    if request.side == PositionSide.LONG:
        max_price = current_price * (Decimal("1") + slippage)
        min_price = None
    else:
        min_price = current_price * (Decimal("1") - slippage)
        max_price = None

    # Calculate collateral
    position_value = request.size * current_price
    collateral = position_value / request.leverage

    # Build transaction parameters
    from app.core.config import settings

    tx_data = TransactionDataResponse(
        contract_address=settings.contract_address,
        function_name="openPosition",
        params={
            "marketId": request.market_id,
            "size": str(request.size),
            "collateral": str(collateral),
            "leverage": str(request.leverage),
            "isLong": request.side == "long",
            "maxSlippage": str(slippage),
        },
        estimated_gas="250000",  # Estimate
        price_feed_id=market.pyth_price_id,
        current_price=current_price,
        min_price=min_price,
        max_price=max_price,
    )

    return ResponseBase(
        success=True, data=tx_data, message="Transaction data built successfully"
    )


@router.post("/build-close-tx", response_model=ResponseBase[TransactionDataResponse])
async def build_close_position_transaction(
    request: BuildClosePositionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Build transaction data for closing a position.

    **Use case**: Frontend gets transaction data to close position on blockchain.

    Returns transaction parameters that frontend can submit.
    """
    from app.db.models import PositionModel

    # Get position
    stmt = (
        select(PositionModel, MarketModel)
        .join(MarketModel, PositionModel.market_id == MarketModel.market_id)
        .where(PositionModel.position_id == request.position_id)
    )
    result = await db.execute(stmt)
    row = result.one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Position not found")
    position: PositionModel
    market: MarketModel
    position, market = row

    if position.status != PositionStatus.OPEN:
        raise HTTPException(status_code=400, detail="Position is not open")

    # Get current price
    price_data = await oracle_service.get_latest_price(market.pyth_price_id)

    if not price_data:
        raise HTTPException(status_code=503, detail="Cannot fetch current price")

    current_price = price_data.normalized_price

    # Calculate slippage bounds
    slippage = request.slippage_tolerance
    if position.side == PositionSide.LONG:
        min_price = current_price * (Decimal("1") - slippage)
        max_price = None
    else:
        max_price = current_price * (Decimal("1") + slippage)
        min_price = None

    # Build transaction parameters
    from app.core.config import settings

    tx_data = TransactionDataResponse(
        contract_address=settings.contract_address,
        function_name="closePosition",
        params={
            "positionId": request.position_id,
            "maxSlippage": str(slippage),
        },
        estimated_gas="200000",
        price_feed_id=market.pyth_price_id,
        current_price=current_price,
        min_price=min_price,
        max_price=max_price,
    )

    return ResponseBase(
        success=True, data=tx_data, message="Close transaction data built successfully"
    )


@router.post("/calculate-pnl")
async def calculate_position_pnl(
    position_id: str,
    exit_price: Optional[Decimal] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Calculate PnL for a position at a given exit price.

    **Use case**: User wants to see "what if I close at this price?"

    If exit_price not provided, uses current market price.
    """
    from app.db.models import PositionModel

    # Get position
    stmt = (
        select(PositionModel, MarketModel)
        .join(MarketModel, PositionModel.market_id == MarketModel.market_id)
        .where(PositionModel.position_id == position_id)
    )
    result = await db.execute(stmt)
    row = result.one_or_none()

    if not row:
        raise HTTPException(status_code=404, detail="Position not found")
    position: PositionModel
    market: MarketModel
    position, market = row

    # Get exit price
    if exit_price is None:
        price_data = await oracle_service.get_latest_price(market.pyth_price_id)
        if not price_data:
            raise HTTPException(status_code=503, detail="Cannot fetch current price")
        exit_price = price_data.normalized_price

    # Calculate PnL
    pnl = calculate_pnl(
        size_usd=position.size,
        entry_price=position.entry_price,
        current_price=exit_price,
        is_long=(position.side == PositionSide.LONG),
    )

    # Calculate ROI
    roi = (
        (pnl / position.collateral) * Decimal("100")
        if position.collateral > 0
        else Decimal("0")
    )

    return ResponseBase(
        success=True,
        data={
            "position_id": position_id,
            "entry_price": str(position.entry_price),
            "exit_price": str(exit_price),
            "pnl": str(pnl),
            "pnl_percentage": str(roi),
            "collateral": str(position.collateral),
            "total_return": str(position.collateral + pnl),
        },
    )


@router.post("/open", response_model=ResponseBase[dict[str, str]])
async def open_position(
    request: OpenPositionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Record an opened position AFTER on-chain tx is broadcasted.
    """
    import uuid
    from datetime import datetime, timezone

    from app.db.models import MarketModel, PositionModel

    # Check market
    market = (
        await db.execute(
            select(MarketModel).where(MarketModel.market_id == request.market_id)
        )
    ).scalar_one_or_none()
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    # Prevent duplicate open tx
    exists = (
        await db.execute(
            select(PositionModel.id).where(
                PositionModel.transaction_hash == request.tx_hash
            )
        )
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="Position already recorded")

    position_id = f"pos_{uuid.uuid4().hex}"
    position_value = request.size * request.entry_price
    collateral = position_value / request.leverage

    position = PositionModel(
        position_id=position_id,
        market_id=request.market_id,
        user_address=request.user_address,
        side=request.side,
        size=request.size,
        collateral=collateral,
        leverage=request.leverage,
        entry_price=request.entry_price,
        status=PositionStatusEnum.OPEN,
        block_number=request.block_number,
        transaction_hash=request.tx_hash,
        created_at=datetime.now(timezone.utc),
    )

    db.add(position)
    await db.commit()
    liquidation_price = calculate_liquidation_price(
        entry_price=request.entry_price,
        leverage=request.leverage,
        is_long=(request.side == PositionSide.LONG),
        maintenance_margin_rate=market.maintenance_margin_rate,
    )
    notify_position_opened(
        user_address=request.user_address,
        symbol=market.symbol,
        position_id=position_id,
        market_id=request.market_id,
        side=request.side,
        size=request.size,
        entry_price=request.entry_price,
        leverage=request.leverage,
        collateral=collateral,
        liquidation_price=liquidation_price,
        tx_hash=request.tx_hash,
    )

    return ResponseBase(
        success=True,
        message="Position opened",
        data={
            "position_id": position_id,
            "status": "open",
        },
    )


@router.post("/close", response_model=ResponseBase[dict[str, Any]])
async def close_position(
    request: ClosePositionRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Record a closed / liquidated position.
    """
    from app.db.models import PositionModel

    stmt = select(PositionModel).where(PositionModel.position_id == request.position_id)
    position = (await db.execute(stmt)).scalar_one_or_none()

    if not position:
        raise HTTPException(status_code=404, detail="Position not found")

    if position.status != PositionStatus.OPEN:
        raise HTTPException(status_code=400, detail="Position is not open")

    now = datetime.utcnow()

    # Calculate PnL
    if position.side == PositionSide.LONG:
        pnl = position.size * (request.exit_price - position.entry_price)
    else:
        pnl = position.size * (position.entry_price - request.exit_price)

    position.exit_price = request.exit_price
    position.pnl = pnl
    position.status = request.status
    position.closed_at = now
    position.tx_close_hash = request.tx_hash

    await db.commit()

    notify_position_closed(
        user_address=position.user_address,
        symbol=position.market_id,
        position_id=position.position_id,
        market_id=position.market_id,
        side=position.side,
        size=position.size,
        entry_price=position.entry_price,
        exit_price=request.exit_price,
        realized_pnl=pnl,
        new_balance=Decimal("0"),  # TODO: Fetch real balance
    )

    return ResponseBase(
        success=True,
        message="Position closed",
        data={
            "position_id": position.position_id,
            "status": position.status,
            "pnl": str(pnl),
        },
    )


@router.post(
    "/sponsor_gas",
    response_model=SponsoredTxResponse,
)
async def execute_sponsored_transaction_endpoint(
    req: SponsoredTxRequest,
):
    """
    Execute a gas-sponsored transaction (NEW FLOW).

    FE flow:
    - build FULL tx bytes (includes sender, gasOwner, gasPayment, gasBudget, ...)
    - user signs FULL tx bytes
    - FE calls this endpoint with (transactionBytesB64, userSignatureB64)
    """
    try:
        result = await tx_service.execute_sponsored_transaction(
            transaction_bytes_b64=req.transactionBytesB64,
            user_signature_b64=req.userSignatureB64,
        )

        return {
            "success": True,
            "digest": result["digest"],
            "effects": result.get("effects"),
            "events": result.get("events"),
        }

    except Exception as e:
        logger.error(f"Sponsored tx failed: {e}")
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

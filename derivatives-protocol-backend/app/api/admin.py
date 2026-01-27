from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MarketModel, MarketStatusEnum
from app.db.session import get_db
from app.schemas.common import ResponseBase
from app.schemas.market import Market, MarketCreate, MarketUpdate

router = APIRouter(prefix="/admin/markets", tags=["Admin - Markets"])


@router.post(
    "/", response_model=ResponseBase[Market], status_code=status.HTTP_201_CREATED
)
async def create_market(
    market: MarketCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new market.

    **Admin only endpoint** - Tạo market mới trong hệ thống.

    Args:
        market: Market data
        db: Database session
    """
    # Check if market_id already exists
    stmt = select(MarketModel).where(MarketModel.market_id == market.market_id)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Market with id '{market.market_id}' already exists",
        )

    # Create new market
    new_market = MarketModel(
        market_id=market.market_id,
        base_token=market.base_token,
        quote_token=market.quote_token,
        symbol=market.symbol,
        pyth_price_id=market.pyth_price_id,
        max_leverage=market.max_leverage,
        min_position_size=market.min_position_size,
        max_position_size=market.max_position_size,
        maintenance_margin_rate=market.maintenance_margin_rate,
        liquidation_fee_rate=market.liquidation_fee_rate,
        funding_rate_interval=market.funding_rate_interval,
        max_funding_rate=market.max_funding_rate,
        status=MarketStatusEnum.ACTIVE,
    )

    db.add(new_market)
    await db.commit()
    await db.refresh(new_market)

    return ResponseBase(
        success=True,
        message=f"Market {market.symbol} created successfully",
        data=Market.model_validate(new_market),
    )


@router.put("/{market_id}", response_model=ResponseBase[Market])
async def update_market(
    market_id: str,
    market_update: MarketUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update market parameters.

    **Admin only endpoint** - Update các thông số của market.

    Args:
        market_id: Market identifier
        market_update: Updated market data
        db: Database session
    """
    # Get market
    stmt = select(MarketModel).where(MarketModel.market_id == market_id)
    result = await db.execute(stmt)
    market = result.scalar_one_or_none()

    if not market:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Market '{market_id}' not found",
        )

    # Update fields if provided
    update_data = market_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(market, field, value)

    await db.commit()
    await db.refresh(market)

    return ResponseBase(
        success=True,
        message=f"Market {market.symbol} updated successfully",
        data=Market.model_validate(market),
    )


@router.patch("/{market_id}/pause", response_model=ResponseBase[Market])
async def pause_market(
    market_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Pause a market (stop trading).

    **Admin only endpoint** - Tạm dừng trading cho market.

    Args:
        market_id: Market identifier
        db: Database session
    """
    stmt = select(MarketModel).where(MarketModel.market_id == market_id)
    result = await db.execute(stmt)
    market = result.scalar_one_or_none()

    if not market:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Market '{market_id}' not found",
        )

    market.status = MarketStatusEnum.PAUSED
    await db.commit()
    await db.refresh(market)

    return ResponseBase(
        success=True,
        message=f"Market {market.symbol} paused",
        data=Market.model_validate(market),
    )


@router.patch("/{market_id}/resume", response_model=ResponseBase[Market])
async def resume_market(
    market_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Resume a paused market.

    **Admin only endpoint** - Tiếp tục trading cho market đã pause.

    Args:
        market_id: Market identifier
        db: Database session
    """
    stmt = select(MarketModel).where(MarketModel.market_id == market_id)
    result = await db.execute(stmt)
    market = result.scalar_one_or_none()

    if not market:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Market '{market_id}' not found",
        )

    market.status = MarketStatusEnum.ACTIVE
    await db.commit()
    await db.refresh(market)

    return ResponseBase(
        success=True,
        message=f"Market {market.symbol} resumed",
        data=Market.model_validate(market),
    )


@router.delete("/{market_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_market(
    market_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a market (soft delete by setting status to closed).

    **Admin only endpoint** - Xóa market (soft delete).

    ⚠️ Chỉ nên delete market khi không còn open positions.

    Args:
        market_id: Market identifier
        db: Database session
    """
    stmt = select(MarketModel).where(MarketModel.market_id == market_id)
    result = await db.execute(stmt)
    market = result.scalar_one_or_none()

    if not market:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Market '{market_id}' not found",
        )

    # Check if there are open positions
    if market.total_long_positions > 0 or market.total_short_positions > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete market with open positions",
        )

    # Soft delete - set status to closed
    market.status = MarketStatusEnum.CLOSED
    await db.commit()

    return None


@router.post("/bulk", response_model=ResponseBase[List[Market]])
async def create_markets_bulk(
    markets: List[MarketCreate],
    db: AsyncSession = Depends(get_db),
):
    """
    Create multiple markets at once.

    **Admin only endpoint** - Tạo nhiều markets cùng lúc.

    Args:
        markets: List of market data
        db: Database session
    """
    created_markets = []
    errors = []

    for market_data in markets:
        try:
            # Check if exists
            stmt = select(MarketModel).where(
                MarketModel.market_id == market_data.market_id
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                errors.append(f"Market {market_data.market_id} already exists")
                continue

            # Create market
            new_market = MarketModel(
                market_id=market_data.market_id,
                base_token=market_data.base_token,
                quote_token=market_data.quote_token,
                symbol=market_data.symbol,
                pyth_price_id=market_data.pyth_price_id,
                max_leverage=market_data.max_leverage,
                min_position_size=market_data.min_position_size,
                max_position_size=market_data.max_position_size,
                maintenance_margin_rate=market_data.maintenance_margin_rate,
                liquidation_fee_rate=market_data.liquidation_fee_rate,
                funding_rate_interval=market_data.funding_rate_interval,
                max_funding_rate=market_data.max_funding_rate,
                status=MarketStatusEnum.ACTIVE,
            )

            db.add(new_market)
            created_markets.append(new_market)

        except Exception as e:
            errors.append(f"Error creating {market_data.market_id}: {str(e)}")

    if errors:
        # Rollback if any errors
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail={"errors": errors}
        )

    await db.commit()

    # Refresh all
    for market in created_markets:
        await db.refresh(market)

    return ResponseBase(
        success=True,
        message=f"Created {len(created_markets)} markets successfully",
        data=[Market.model_validate(m) for m in created_markets],
    )

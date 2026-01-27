from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MarketModel, PositionModel, PositionStatusEnum
from app.db.session import get_db
from app.schemas.common import PaginatedResponse, ResponseBase
from app.schemas.position import (
    LiquidationCandidate,
    Position,
    PositionSummary,
    PositionWithPnL,
)
from app.services.blockchain import blockchain_service
from app.services.oracle import oracle_service

router = APIRouter(prefix="/positions", tags=["Positions"])


@router.get("/", response_model=PaginatedResponse[Position])
async def get_positions(
    user_address: Optional[str] = None,
    market_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Get positions with filters and pagination.

    Args:
        user_address: Filter by user address
        market_id: Filter by market
        status: Filter by status (open, closed, liquidated)
        page: Page number
        page_size: Items per page
        db: Database session
    """
    # Build query
    stmt = select(PositionModel)

    if user_address:
        stmt = stmt.where(PositionModel.user_address == user_address.lower())

    if market_id:
        stmt = stmt.where(PositionModel.market_id == market_id)

    if status:
        stmt = stmt.where(PositionModel.status == status)

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    result = await db.execute(count_stmt)
    total = result.scalar()

    # Get paginated results
    stmt = stmt.order_by(PositionModel.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    positions = result.scalars().all()

    return PaginatedResponse(
        items=[Position.model_validate(p) for p in positions],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/{position_id}", response_model=ResponseBase[PositionWithPnL])
async def get_position(
    position_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get position by ID with calculated PnL and health metrics.

    Args:
        position_id: Position identifier
        db: Database session
    """
    # Get position with market
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

    # Build position with PnL
    position_data = PositionWithPnL.model_validate(position)

    # If position is open, calculate current metrics
    if position.status == PositionStatusEnum.OPEN:
        # Get current price
        price_data = await oracle_service.get_latest_price(market.pyth_price_id)

        if price_data:
            current_price = price_data.normalized_price
            position_data.current_price = current_price

            # Calculate unrealized PnL
            if position.side.value == "long":
                pnl = position.size * (current_price - position.entry_price)
            else:
                pnl = position.size * (position.entry_price - current_price)

            position_data.unrealized_pnl = pnl
            position_data.total_pnl = pnl + position.realized_pnl

            # Calculate health metrics
            health_factor = blockchain_service.calculate_health_factor(
                collateral=position.collateral,
                position_size=position.size,
                entry_price=position.entry_price,
                current_price=current_price,
                is_long=(position.side.value == "long"),
                maintenance_margin_rate=market.maintenance_margin_rate,
                accumulated_funding=position.accumulated_funding,
            )

            position_data.health_factor = health_factor
            position_data.is_at_risk = health_factor <= Decimal("1.2")

            # Calculate margin ratio
            position_value = position.size * current_price
            if position_value > 0:
                position_data.margin_ratio = position.collateral / position_value

            # Calculate liquidation price
            liq_price = blockchain_service.calculate_liquidation_price(
                entry_price=position.entry_price,
                leverage=position.leverage,
                is_long=(position.side.value == "long"),
                maintenance_margin_rate=market.maintenance_margin_rate,
            )
            position_data.liquidation_price = liq_price

    return ResponseBase(
        success=True,
        data=position_data,
    )


@router.get(
    "/user/{user_address}/summary", response_model=ResponseBase[PositionSummary]
)
async def get_user_summary(
    user_address: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Get summary of user's positions.

    Args:
        user_address: User wallet address
        db: Database session
    """
    user_address = user_address.lower()

    # Get all user positions
    stmt = (
        select(PositionModel, MarketModel)
        .join(MarketModel, PositionModel.market_id == MarketModel.market_id)
        .where(PositionModel.user_address == user_address)
    )
    result = await db.execute(stmt)
    rows = result.all()

    total_positions = len(rows)
    open_positions = sum(1 for p, _ in rows if p.status == PositionStatusEnum.OPEN)

    total_collateral = Decimal("0")
    total_unrealized_pnl = Decimal("0")
    total_realized_pnl = Decimal("0")

    # Get all unique price feed IDs for open positions
    open_positions_data = [
        (p, m) for p, m in rows if p.status == PositionStatusEnum.OPEN
    ]
    if open_positions_data:
        price_feed_ids = list(set(m.pyth_price_id for _, m in open_positions_data))
        prices = await oracle_service.get_latest_prices(price_feed_ids)

        for position, market in open_positions_data:
            total_collateral += position.collateral
            total_realized_pnl += position.realized_pnl

            # Calculate unrealized PnL
            price_data = prices.get(market.pyth_price_id)
            if price_data:
                current_price = price_data.normalized_price

                if position.side.value == "long":
                    pnl = position.size * (current_price - position.entry_price)
                else:
                    pnl = position.size * (position.entry_price - current_price)

                total_unrealized_pnl += pnl

    # Add realized PnL from closed positions
    for position, _ in rows:
        if position.status != PositionStatusEnum.OPEN:
            total_realized_pnl += position.realized_pnl

    summary = PositionSummary(
        user_address=user_address,
        total_positions=total_positions,
        open_positions=open_positions,
        total_collateral=total_collateral,
        total_unrealized_pnl=total_unrealized_pnl,
        total_realized_pnl=total_realized_pnl,
    )

    return ResponseBase(
        success=True,
        data=summary,
    )


@router.get(
    "/liquidation/candidates", response_model=ResponseBase[List[LiquidationCandidate]]
)
async def get_liquidation_candidates(
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    Get positions at risk of liquidation.

    Args:
        limit: Maximum number of candidates to return
        db: Database session
    """
    from app.services.liquidation import liquidation_bot

    # Get candidates from liquidation bot
    async with AsyncSession() as temp_db:
        candidates = await liquidation_bot._find_liquidation_candidates(temp_db)

    # Return top N by potential reward
    candidates = candidates[:limit]

    return ResponseBase(
        success=True,
        data=candidates,
    )

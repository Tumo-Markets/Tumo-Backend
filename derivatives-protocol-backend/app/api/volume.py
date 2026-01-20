"""
Volume API Endpoints - CLEAN ARCHITECTURE

- Thin API layer
- All business logic handled in VolumeAggregator
- No redundant DB access
- Fully type-safe
"""

from fastapi import APIRouter, HTTPException, Query

from app.schemas.common import ResponseBase
from app.schemas.volume import (
    Volume24hData,
    VolumeHistoryItem,
)
from app.services.volume_aggregator import volume_aggregator

router = APIRouter(prefix="/volume", tags=["Volume"])


# =====================================================================
# 24H VOLUME - SINGLE MARKET
# =====================================================================


@router.get("/24h/{market_id}", response_model=ResponseBase[Volume24hData])
async def get_24h_volume(
    market_id: str,
) -> ResponseBase[Volume24hData]:
    """
    Get 24-hour rolling volume for a specific market.
    """
    volume = await volume_aggregator.get_24h_volume(market_id)

    if volume is None:
        raise HTTPException(status_code=404, detail=f"Market '{market_id}' not found")

    return ResponseBase(success=True, data=volume)


# =====================================================================
# 24H VOLUME - ALL MARKETS
# =====================================================================


@router.get("/24h", response_model=ResponseBase[list[Volume24hData]])
async def get_all_24h_volumes() -> ResponseBase[list[Volume24hData]]:
    """
    Get 24-hour volume for all active markets.
    """
    volumes_dict = await volume_aggregator.get_all_24h_volumes_bulk()

    volumes = sorted(
        volumes_dict.values(),
        key=lambda v: v.volume_24h,
        reverse=True,
    )

    return ResponseBase(success=True, data=volumes)


# =====================================================================
# VOLUME HISTORY
# =====================================================================


@router.get(
    "/history/{market_id}",
    response_model=ResponseBase[list[VolumeHistoryItem]],
)
async def get_volume_history(
    market_id: str,
    hours: int = Query(24, ge=1, le=168),
) -> ResponseBase[list[VolumeHistoryItem]]:
    """
    Get hourly volume history for a market.
    """
    history = await volume_aggregator.get_volume_history(market_id, hours)

    if history is None:
        raise HTTPException(status_code=404, detail=f"Market '{market_id}' not found")

    return ResponseBase(success=True, data=history)

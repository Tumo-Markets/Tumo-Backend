import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from sqlalchemy import select

from app.api.models import (
    CandleMessage,
    ConnectedCandleMessage,
    ConnectedMessage,
    EmptyPositionsMessage,
    MarketStats,
    MarketStatsMessage,
    PositionsUpdateMessage,
    PositionUpdateItem,
)
from app.api.utils import TIMEFRAME_SECONDS, get_candle_start, normalize_hex
from app.constants import build_collateral_in
from app.db.chart_models import PriceOHLCVModel
from app.db.models import (
    MarketModel,
    PositionModel,
    PositionSideEnum,
    PositionStatusEnum,
    PriceHistoryModel,
)
from app.services.blockchain import blockchain_service
from app.services.funding import funding_service
from app.services.notifications import websocket_notifications
from app.services.oracle import oracle_service
from app.services.volume_aggregator import volume_aggregator
from app.services.websocket import manager

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/prices/{market_id}")
async def websocket_prices(websocket: WebSocket, market_id: str):
    """
    WebSocket endpoint for real-time price updates.

    Streams price updates for a specific market every second.

    Args:
        websocket: WebSocket connection
        market_id: Market identifier
    """
    await manager.connect_market(websocket, market_id)

    try:
        # Get market info from database
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            stmt = select(MarketModel).where(MarketModel.market_id == market_id)
            result = await db.execute(stmt)
            market = result.scalar_one_or_none()

            if not market:
                await websocket.send_json(
                    {"type": "error", "message": f"Market {market_id} not found"}
                )
                return

            price_feed_id = market.pyth_price_id

        # Send initial connection success message
        await websocket.send_json(
            {
                "type": "connected",
                "market_id": market_id,
                "symbol": market.symbol,
                "message": "Connected to price stream",
            }
        )

        # Stream prices
        while True:
            try:
                # Fetch latest price from Pyth
                price_data = await oracle_service.get_latest_price(price_feed_id)

                if price_data:
                    message = {
                        "type": "price_update",
                        "market_id": market_id,
                        "symbol": market.symbol,
                        "price": str(price_data.normalized_price),
                        "confidence": str(price_data.confidence),
                        "timestamp": price_data.publish_time,
                        "age_seconds": price_data.age_seconds,
                    }

                    await manager.broadcast_to_market(message, market_id)

                # Wait before next update (1 second)
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Error in price stream for {market_id}: {e}")
                await asyncio.sleep(1)

    except WebSocketDisconnect:
        manager.disconnect(websocket, "prices")
        logger.info(f"Client disconnected from price stream for {market_id}")
    except Exception as e:
        logger.error(f"Error in price websocket: {e}")
        manager.disconnect(websocket, "prices")


@router.websocket("/ws/candles/{market_id}/{timeframe}")
async def websocket_candles(websocket: WebSocket, market_id: str, timeframe: str):
    stream_key = f"candles:{market_id}:{timeframe}"
    STREAM_INTERVAL = 2

    if timeframe not in TIMEFRAME_SECONDS:
        await websocket.accept()
        await websocket.send_json({"type": "error", "message": "Invalid timeframe"})
        await websocket.close(code=1008)
        return

    tf_seconds = TIMEFRAME_SECONDS[timeframe]
    current_candle: CandleMessage | None = None
    prev_close: Decimal | None = None

    try:
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            market = (
                await db.execute(
                    select(MarketModel).where(MarketModel.market_id == market_id)
                )
            ).scalar_one_or_none()

            if not market:
                await websocket.accept()
                await websocket.send_json(
                    {"type": "error", "message": "Market not found"}
                )
                await websocket.close(code=1008)
                return

            price_feed_id = market.pyth_price_id

            last_candle = (
                await db.execute(
                    select(PriceOHLCVModel.close)
                    .where(
                        PriceOHLCVModel.market_id == market_id,
                        PriceOHLCVModel.timeframe == timeframe,
                    )
                    .order_by(PriceOHLCVModel.timestamp.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            if last_candle is not None:
                prev_close = Decimal(str(last_candle))

        await manager.connect(websocket, stream_key)

        await websocket.send_json(
            ConnectedCandleMessage(
                market_id=market_id,
                timeframe=timeframe,
                message="Connected to candle stream",
            ).model_dump(),
        )

        while True:
            price_data = await oracle_service.get_latest_price(price_feed_id)
            if not price_data:
                await asyncio.sleep(STREAM_INTERVAL)
                continue

            price: Decimal = price_data.normalized_price
            now_ts = int(datetime.utcnow().timestamp())
            candle_start = get_candle_start(now_ts, tf_seconds)

            if (
                not current_candle
                or candle_start != current_candle.candle_start_timestamp
            ):
                if current_candle:
                    current_candle.current_timestamp = now_ts
                    finished = current_candle.model_copy(update={"is_finished": True})
                    await websocket.send_json(finished.model_dump(mode="json"))

                open_price = prev_close if prev_close is not None else price
                high_price = max(open_price, price)
                low_price = min(open_price, price)

                current_candle = CandleMessage(
                    market_id=market_id,
                    timeframe=timeframe,
                    candle_start_timestamp=candle_start,
                    current_timestamp=now_ts,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=price,
                    is_finished=False,
                )

            else:
                current_candle.current_timestamp = now_ts
                current_candle.close = price
                current_candle.high = max(current_candle.high, price)
                current_candle.low = min(current_candle.low, price)

            prev_close = current_candle.close

            await websocket.send_json(current_candle.model_dump(mode="json"))
            await asyncio.sleep(STREAM_INTERVAL)

    except WebSocketDisconnect:
        logger.info(f"Candle WS disconnected: {market_id} {timeframe}")
    except Exception as e:
        logger.error(f"Candle websocket error: {e}")
    finally:
        try:
            manager.disconnect(websocket, stream_key)
        except Exception:
            pass


@router.websocket("/ws/positions/{user_address}")
async def websocket_user_positions(
    websocket: WebSocket,
    user_address: str,
) -> None:
    user_address_lower = user_address.lower()

    await websocket.accept()

    try:
        # Send connection success
        connected_msg = ConnectedMessage(
            message=f"Connected to position updates for {user_address_lower}"
        )
        await websocket.send_json(connected_msg.model_dump(mode="json"))

        from app.db.session import AsyncSessionLocal

        while True:
            try:
                async with AsyncSessionLocal() as db:
                    # Query open positions with market info
                    stmt = (
                        select(PositionModel, MarketModel)
                        .join(
                            MarketModel,
                            PositionModel.market_id == MarketModel.market_id,
                        )
                        .where(
                            PositionModel.user_address == user_address_lower,
                            PositionModel.status == PositionStatusEnum.OPEN,
                        )
                    )

                    result = await db.execute(stmt)
                    rows: list[tuple[PositionModel, MarketModel]] = result.all()

                    # No open positions
                    if not rows:
                        empty_msg = EmptyPositionsMessage(
                            user_address=user_address_lower
                        )
                        await websocket.send_json(empty_msg.model_dump(mode="json"))
                        await asyncio.sleep(2)
                        continue

                    # Collect price feed ids
                    price_feed_ids = list({market.pyth_price_id for _, market in rows})
                    prices = await oracle_service.get_latest_prices(price_feed_ids)

                    position_updates: list[PositionUpdateItem] = []
                    total_unrealized_pnl = Decimal("0")

                    for position, market in rows:
                        feed_id = normalize_hex(market.pyth_price_id)
                        price_data = prices.get(feed_id)
                        if not price_data:
                            continue

                        current_price: Decimal = price_data.normalized_price

                        # Unrealized PnL
                        if position.side == PositionSideEnum.LONG:
                            unrealized_pnl = position.size * (
                                current_price - position.entry_price
                            )
                        else:
                            unrealized_pnl = position.size * (
                                position.entry_price - current_price
                            )

                        total_unrealized_pnl += unrealized_pnl

                        # Health factor
                        health_factor = blockchain_service.calculate_health_factor(
                            collateral=position.collateral,
                            position_size=position.size,
                            entry_price=position.entry_price,
                            current_price=current_price,
                            is_long=(position.side == PositionSideEnum.LONG),
                            maintenance_margin_rate=market.maintenance_margin_rate,
                            accumulated_funding=position.accumulated_funding,
                        )

                        # Liquidation price
                        liquidation_price = (
                            blockchain_service.calculate_liquidation_price(
                                entry_price=position.entry_price,
                                leverage=position.leverage,
                                is_long=(position.side == PositionSideEnum.LONG),
                                maintenance_margin_rate=market.maintenance_margin_rate,
                            )
                        )

                        position_updates.append(
                            PositionUpdateItem(
                                position_id=position.position_id,
                                market_id=position.market_id,
                                symbol=market.symbol,
                                side=position.side,
                                size=position.size,
                                collateral=position.collateral,
                                entry_price=position.entry_price,
                                current_price=current_price,
                                unrealized_pnl=unrealized_pnl,
                                health_factor=health_factor,
                                liquidation_price=liquidation_price,
                                is_at_risk=health_factor <= Decimal("1.2"),
                            )
                        )

                    update_msg = PositionsUpdateMessage(
                        user_address=user_address_lower,
                        positions=position_updates,
                        total_unrealized_pnl=total_unrealized_pnl,
                        positions_count=len(position_updates),
                    )

                    await websocket.send_json(update_msg.model_dump(mode="json"))

                await asyncio.sleep(2)

            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected: {user_address_lower}")
                break

            except Exception as e:
                logger.exception(
                    f"[WS] Position update error for {user_address_lower}: {e}"
                )
                await asyncio.sleep(2)

    finally:
        try:
            manager.disconnect(websocket, "positions")
        except Exception:
            pass


@router.websocket("/ws/liquidations")
async def websocket_liquidations(websocket: WebSocket):
    """
    WebSocket endpoint for liquidation alerts.

    Streams positions at risk of liquidation in real-time.
    """
    await manager.connect(websocket, "liquidations")

    try:
        await websocket.send_json(
            {"type": "connected", "message": "Connected to liquidation alerts"}
        )

        from app.db.session import AsyncSessionLocal
        from app.services.liquidation import liquidation_bot

        while True:
            try:
                async with AsyncSessionLocal() as db:
                    # Get liquidation candidates
                    candidates = await liquidation_bot._find_liquidation_candidates(db)

                    if candidates:
                        message = {
                            "type": "liquidation_alert",
                            "count": len(candidates),
                            "candidates": [
                                {
                                    "position_id": c.position_id,
                                    "user_address": c.user_address,
                                    "market_id": c.market_id,
                                    "health_factor": str(c.health_factor),
                                    "liquidation_price": str(c.liquidation_price),
                                    "current_price": str(c.current_price),
                                    "potential_reward": str(c.potential_reward),
                                }
                                for c in candidates[:10]  # Top 10
                            ],
                            "timestamp": datetime.utcnow().isoformat(),
                        }

                        await manager.broadcast(message, "liquidations")

                # Check every 5 seconds
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Error in liquidation alerts: {e}")
                await asyncio.sleep(5)

    except WebSocketDisconnect:
        manager.disconnect(websocket, "liquidations")
        logger.info("Client disconnected from liquidation alerts")
    except Exception as e:
        logger.error(f"Error in liquidation websocket: {e}")
        manager.disconnect(websocket, "liquidations")


@router.websocket("/ws/market-stats/{market_id}")
async def websocket_market_stats(websocket: WebSocket, market_id: str):
    """
    WebSocket endpoint for market statistics updates.

    Streams market stats including OI, funding rate, volume.

    Args:
        websocket: WebSocket connection
        market_id: Market identifier
    """
    await manager.connect_market(websocket, market_id)

    try:
        from app.db.session import AsyncSessionLocal

        await websocket.send_json(
            {
                "type": "connected",
                "market_id": market_id,
                "message": "Connected to market stats",
            }
        )

        while True:
            try:
                async with AsyncSessionLocal() as db:
                    stmt = select(MarketModel).where(MarketModel.market_id == market_id)
                    result = await db.execute(stmt)
                    market = result.scalar_one_or_none()

                    if not market:
                        await asyncio.sleep(5)
                        continue

                    # Get current price from oracle
                    price_data = await oracle_service.get_latest_price(
                        market.pyth_price_id
                    )

                    mark_price = None
                    if price_data:
                        mark_price = price_data.normalized_price

                    # Predict next funding rate
                    predicted_funding = await funding_service.predict_next_funding_rate(
                        market_id
                    )

                    # Calculate next funding time
                    next_funding_time = None
                    if market.last_funding_update:
                        next_funding_time = market.last_funding_update + timedelta(
                            seconds=market.funding_rate_interval
                        )

                    now = datetime.now(timezone.utc)
                    target_time = now - timedelta(hours=24)

                    stmt_24h = (
                        select(PriceHistoryModel)
                        .where(
                            PriceHistoryModel.market_id == market_id,
                            PriceHistoryModel.timestamp <= target_time,
                        )
                        .order_by(PriceHistoryModel.timestamp.desc())
                        .limit(1)
                    )

                    result_24h = await db.execute(stmt_24h)
                    price_24h_tick = result_24h.scalar_one_or_none()

                    price_change_24h: None | Decimal = None
                    price_change_percent_24h: None | Decimal = None

                    if mark_price is not None and price_24h_tick:
                        price_24h_ago = price_24h_tick.price
                        if price_24h_ago and price_24h_ago > 0:
                            price_change_24h = mark_price - price_24h_ago
                            price_change_percent_24h = (
                                price_change_24h / price_24h_ago
                            ) * Decimal("100")
                    volume_data = await volume_aggregator.get_24h_volume(market_id)
                    # Build stats
                    stats = MarketStats(
                        market_id=market.market_id,
                        symbol=market.symbol,
                        collateral_in=build_collateral_in(market.quote_token),
                        mark_price=mark_price,
                        index_price=mark_price,  # Could be different in production
                        price_24h_change=price_change_percent_24h,
                        total_long_oi=market.total_long_positions,
                        total_short_oi=market.total_short_positions,
                        total_oi=market.total_long_positions
                        + market.total_short_positions,
                        current_funding_rate=market.current_funding_rate,
                        predicted_funding_rate=predicted_funding,
                        next_funding_time=next_funding_time,
                        volume_24h=volume_data.volume_24h,
                    )
                    message_models = MarketStatsMessage(marketstats=stats)

                    await manager.broadcast_to_market(
                        message_models.model_dump(mode="json"), market_id
                    )

                # Update every 5 seconds
                await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Error in market stats for {market_id}: {e}")
                await asyncio.sleep(5)

    except WebSocketDisconnect:
        manager.disconnect(websocket, "prices")
        logger.info(f"Client disconnected from market stats for {market_id}")
    except Exception as e:
        logger.error(f"Error in market stats websocket: {e}")
        manager.disconnect(websocket, "prices")


@router.websocket("/ws/notifications/{user_address}")
async def notifications(
    websocket: WebSocket,
    user_address: str,
):
    """
    PRIVATE notification channel for a single user.
    Push-only, event-based (no polling state).
    """
    await websocket_notifications(websocket, user_address)


@router.get("/ws/stats")
async def websocket_stats():
    """Get WebSocket connection statistics."""
    return {"success": True, "data": manager.get_stats()}

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.api import (
    admin,
    charts,
    markets,
    position_helpers,
    positions,
    system,
    volume,
    websocket,
)
from app.core.config import settings
from app.db.session import close_db, init_db
from app.services.broadcaster import broadcaster
from app.services.funding import funding_service
from app.services.indexer import indexer
from app.services.liquidation import liquidation_bot
from app.services.oi_aggregator import oi_aggregator
from app.services.oracle import oracle_service
from app.services.pnl_calculator import pnl_calculator
from app.services.price_aggregator import price_aggregator
from app.services.price_producer import price_producer
from app.services.volume_aggregator import volume_aggregator


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.

    Startup:
    - Initialize database
    - Start blockchain indexer
    - Start liquidation bot
    - Start funding rate service

    Shutdown:
    - Stop all background services
    - Close database connections
    - Close oracle connections
    """
    logger.info("Starting application...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Start background services
    background_tasks = []

    # Start broadcaster
    await broadcaster.start()
    logger.info("Event broadcaster started")

    # Start indexer
    indexer_task = asyncio.create_task(indexer.start())
    background_tasks.append(indexer_task)
    logger.info("Blockchain indexer started")

    price_producer_task = asyncio.create_task(price_producer.start())
    background_tasks.append(price_producer_task)
    logger.info("Price producer started")

    # Start liquidation bot
    liquidation_task = asyncio.create_task(liquidation_bot.start())
    background_tasks.append(liquidation_task)
    logger.info("Liquidation bot started")

    # Start funding service
    funding_task = asyncio.create_task(funding_service.start())
    background_tasks.append(funding_task)
    logger.info("Funding rate service started")

    # Start chart aggregation services

    price_agg_task = asyncio.create_task(price_aggregator.start())
    background_tasks.append(price_agg_task)
    logger.info("Price aggregator started")

    pnl_calc_task = asyncio.create_task(pnl_calculator.start())
    background_tasks.append(pnl_calc_task)
    logger.info("PnL calculator started")

    oi_agg_task = asyncio.create_task(oi_aggregator.start())
    background_tasks.append(oi_agg_task)
    logger.info("OI aggregator started")

    volume_agg_task = asyncio.create_task(volume_aggregator.start())
    background_tasks.append(volume_agg_task)
    logger.info("Volume aggregator started")
    yield

    # Shutdown
    logger.info("Shutting down application...")

    # Stop background services
    await indexer.stop()
    await liquidation_bot.stop()
    await funding_service.stop()
    await broadcaster.stop()

    # Stop chart services
    await price_producer.stop()
    await pnl_calculator.stop()
    await oi_aggregator.stop()

    await volume_aggregator.stop()

    # Cancel tasks
    for task in background_tasks:
        task.cancel()

    # Close connections
    await oracle_service.close()
    await close_db()

    logger.info("Application shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Backend API for Permissionless Derivatives Protocol",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "detail": str(exc) if settings.debug else None,
        },
    )


# Include routers
app.include_router(markets.router, prefix=settings.api_prefix)
app.include_router(positions.router, prefix=settings.api_prefix)
app.include_router(system.router, prefix=settings.api_prefix)
app.include_router(system.oracle_router, prefix=settings.api_prefix)
app.include_router(system.liquidation_router, prefix=settings.api_prefix)
app.include_router(websocket.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)
app.include_router(charts.router, prefix=settings.api_prefix)
app.include_router(position_helpers.router, prefix=settings.api_prefix)
app.include_router(volume.router, prefix=settings.api_prefix)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/ping")
async def ping():
    """Simple ping endpoint."""
    return {"status": "pong"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )

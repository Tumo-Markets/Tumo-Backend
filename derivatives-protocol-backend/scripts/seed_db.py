"""
Seed database with sample markets.

Usage:
    python scripts/seed_db.py
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from decimal import Decimal
from app.db.session import AsyncSessionLocal
from app.db.models import MarketModel, MarketStatusEnum
from loguru import logger


# Sample markets based on common trading pairs
SAMPLE_MARKETS = [
    {
        "market_id": "btc-usdc-perp",
        "base_token": "0x0000000000000000000000000000000000000001",
        "quote_token": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC
        "symbol": "BTC/USDC",
        "pyth_price_id": "0xe62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43",  # BTC/USD
        "max_leverage": Decimal("100"),
        "min_position_size": Decimal("0.001"),
        "max_position_size": Decimal("100"),
        "maintenance_margin_rate": Decimal("0.05"),  # 5%
        "liquidation_fee_rate": Decimal("0.01"),  # 1%
    },
    {
        "market_id": "eth-usdc-perp",
        "base_token": "0x0000000000000000000000000000000000000002",
        "quote_token": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "symbol": "ETH/USDC",
        "pyth_price_id": "0xff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",  # ETH/USD
        "max_leverage": Decimal("50"),
        "min_position_size": Decimal("0.01"),
        "max_position_size": Decimal("1000"),
        "maintenance_margin_rate": Decimal("0.05"),
        "liquidation_fee_rate": Decimal("0.01"),
    },
    {
        "market_id": "sol-usdc-perp",
        "base_token": "0x0000000000000000000000000000000000000003",
        "quote_token": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "symbol": "SOL/USDC",
        "pyth_price_id": "0xef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d",  # SOL/USD
        "max_leverage": Decimal("20"),
        "min_position_size": Decimal("0.1"),
        "max_position_size": Decimal("10000"),
        "maintenance_margin_rate": Decimal("0.1"),
        "liquidation_fee_rate": Decimal("0.02"),
    },
    {
        "market_id": "arb-usdc-perp",
        "base_token": "0x0000000000000000000000000000000000000004",
        "quote_token": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        "symbol": "ARB/USDC",
        "pyth_price_id": "0x3fa4252848f9f0a1480be62745a4629d9eb1322aebab8a791e344b3b9c1adcf5",  # ARB/USD
        "max_leverage": Decimal("10"),
        "min_position_size": Decimal("1"),
        "max_position_size": Decimal("100000"),
        "maintenance_margin_rate": Decimal("0.15"),
        "liquidation_fee_rate": Decimal("0.03"),
    },
]


async def seed_markets():
    """Seed database with sample markets."""
    logger.info("Starting database seeding...")
    
    async with AsyncSessionLocal() as db:
        # Check if markets already exist
        for market_data in SAMPLE_MARKETS:
            try:
                # Check if market exists
                from sqlalchemy import select
                stmt = select(MarketModel).where(
                    MarketModel.market_id == market_data["market_id"]
                )
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if existing:
                    logger.info(f"Market {market_data['symbol']} already exists, skipping")
                    continue
                
                # Create new market
                market = MarketModel(
                    status=MarketStatusEnum.ACTIVE,
                    **market_data
                )
                
                db.add(market)
                logger.info(f"Added market: {market_data['symbol']}")
                
            except Exception as e:
                logger.error(f"Error adding market {market_data['symbol']}: {e}")
                await db.rollback()
                continue
        
        try:
            await db.commit()
            logger.info("Database seeding completed successfully!")
        except Exception as e:
            logger.error(f"Error committing to database: {e}")
            await db.rollback()


if __name__ == "__main__":
    asyncio.run(seed_markets())

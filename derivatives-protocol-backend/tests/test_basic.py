"""
Sample tests for the API.

Run with: pytest tests/
"""

from decimal import Decimal

from app.schemas.market import MarketStatus
from app.schemas.position import PositionSide
from app.utils.calculations import calculate_health_factor, calculate_liquidation_price


def test_health_factor_calculation():
    """Test health factor calculation."""

    # Test long position in profit
    health_factor = calculate_health_factor(
        collateral=Decimal("1000"),
        size_usd=Decimal("1"),
        entry_price=Decimal("50000"),
        current_price=Decimal("51000"),
        is_long=True,
        maintenance_margin_rate=Decimal("0.05"),
    )

    # Equity = 1000 + (1 * (51000 - 50000)) = 2000
    # Maintenance Margin = 1 * 51000 * 0.05 = 2550
    # Health Factor = 2000 / 2550 ≈ 0.78
    assert health_factor > Decimal("0.7")
    assert health_factor < Decimal("0.8")


def test_liquidation_price_calculation():
    """Test liquidation price calculation."""

    # Test long position
    liq_price = calculate_liquidation_price(
        entry_price=Decimal("50000"),
        leverage=Decimal("10"),
        is_long=True,
        maintenance_margin_rate=Decimal("0.05"),
    )

    # For long: Liq = 50000 * (1 - 1/10 + 0.05) = 50000 * 0.95 = 47500
    assert liq_price == Decimal("47500")

    # Test short position
    liq_price = calculate_liquidation_price(
        entry_price=Decimal("50000"),
        leverage=Decimal("10"),
        is_long=False,
        maintenance_margin_rate=Decimal("0.05"),
    )

    # For short: Liq = 50000 * (1 + 1/10 - 0.05) = 50000 * 1.05 = 52500
    assert liq_price == Decimal("52500")


def test_position_side_enum():
    """Test position side enum."""
    assert PositionSide.LONG == "long"
    assert PositionSide.SHORT == "short"


def test_market_status_enum():
    """Test market status enum."""
    assert MarketStatus.ACTIVE == "active"
    assert MarketStatus.PAUSED == "paused"
    assert MarketStatus.CLOSED == "closed"


# More comprehensive tests would include:
# - API endpoint tests
# - Database tests
# - Oracle integration tests
# - Liquidation bot tests
# - Funding rate calculation tests

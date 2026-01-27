from decimal import Decimal


def calculate_pnl(
    size_usd: Decimal,
    entry_price: Decimal,
    current_price: Decimal,
    is_long: bool,
) -> Decimal:
    """
    Calculate PnL for a perpetual position.

    Assumptions:
    - size_usd is position notional in USD
    - prices are USD per token

    Args:
        size_usd: Position size in USD (notional)
        entry_price: Entry price
        current_price: Current or exit price
        is_long: True for long, False for short

    Returns:
        PnL in USD (can be negative)
    """

    if entry_price <= 0:
        raise ValueError("entry_price must be greater than 0")

    price_diff_ratio = (current_price - entry_price) / entry_price

    if not is_long:
        price_diff_ratio = -price_diff_ratio

    pnl = size_usd * price_diff_ratio
    return pnl


def calculate_health_factor(
    collateral: Decimal,
    size_usd: Decimal,
    entry_price: Decimal,
    current_price: Decimal,
    is_long: bool,
    maintenance_margin_rate: Decimal,
    accumulated_funding: Decimal = Decimal("0"),
) -> Decimal:
    """
    Health Factor = Equity / Maintenance Margin

    Assumptions:
    - size_usd is position notional in USD
    - prices are USD per token
    """

    if entry_price <= 0:
        return Decimal("0")

    # Unrealized PnL
    price_diff_ratio = (current_price - entry_price) / entry_price
    if not is_long:
        price_diff_ratio = -price_diff_ratio

    pnl = size_usd * price_diff_ratio

    # Equity
    equity = collateral + pnl - accumulated_funding

    # Maintenance margin
    maintenance_margin = size_usd * maintenance_margin_rate

    if maintenance_margin <= 0:
        return Decimal("999999")

    return equity / maintenance_margin


def calculate_liquidation_price(
    entry_price: Decimal,
    leverage: Decimal,
    is_long: bool,
    maintenance_margin_rate: Decimal,
) -> Decimal:
    """
    Calculate liquidation price for USD-margined perpetuals.

    Long:
        Liq = Entry × (1 - 1/L + MMR)
    Short:
        Liq = Entry × (1 + 1/L - MMR)
    """

    if leverage <= 0:
        raise ValueError("leverage must be greater than 0")

    leverage_factor = Decimal("1") / leverage

    if is_long:
        liq_price = entry_price * (
            Decimal("1") - leverage_factor + maintenance_margin_rate
        )
    else:
        liq_price = entry_price * (
            Decimal("1") + leverage_factor - maintenance_margin_rate
        )

    return max(liq_price, Decimal("0"))


def calculate_exit_price(
    *,
    entry_price: Decimal,
    size_usd: Decimal,
    realized_pnl: Decimal,
    is_long: bool,
) -> Decimal:
    """
    Calculate exit price from realized PnL when position size is USD-notional.

    Assumptions:
    - size_usd is position notional in USD
    - prices are USD per token
    - realized_pnl is in USD

    Formula:
    PnL = size_usd * (exit_price - entry_price) / entry_price   (LONG)
    PnL = size_usd * (entry_price - exit_price) / entry_price   (SHORT)
    """

    if size_usd <= 0 or entry_price <= 0:
        return entry_price

    price_delta_ratio = realized_pnl / size_usd

    if is_long:
        exit_price = entry_price * (Decimal("1") + price_delta_ratio)
    else:
        exit_price = entry_price * (Decimal("1") - price_delta_ratio)

    return max(exit_price, Decimal("0"))

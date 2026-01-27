from decimal import Decimal
from typing import Final

TOKEN_ADDRESS_TO_SYMBOL: Final[dict[str, str]] = {
    # BSC
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": "USDC",
    "0x55d398326f99059ff775485246999027b3197955": "USDT",
    # Ethereum (nếu có)
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC",
    # OneChain
    "0x0000000000000000000000000000000000000001": "USDH",
}


def build_collateral_in(quote_token: str) -> str:
    address = quote_token.lower()
    return TOKEN_ADDRESS_TO_SYMBOL.get(address, "UNKNOWN")


def normalize_hex(value: str) -> str:
    return value.lower().removeprefix("0x")


SCALE = Decimal(10**6)

from decimal import Decimal
from typing import Final

TOKEN_ADDRESS_TO_SYMBOL: Final[dict[str, str]] = {
    # BSC
    "0x81c52254ccd626b128aab686c70a43fe0c50423ea10ee5b3921e10e198fbcbf9::btc::BTC": "BTC",
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": "USDC",
    "0x55d398326f99059ff775485246999027b3197955": "USDT",
    # Ethereum (nếu có)
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC",
    # OneChain
    "0x0000000000000000000000000000000000000001": "USDH",
    "0x8b76fc2a2317d45118770cefed7e57171a08c477ed16283616b15f099391f120::hackathon::HACKATHON": "HACKATHON",
}


def build_collateral_in(quote_token: str) -> str:
    return TOKEN_ADDRESS_TO_SYMBOL.get(quote_token, "UNKNOWN")


def normalize_hex(value: str) -> str:
    return value.lower().removeprefix("0x")


SCALE_CONTRACT = Decimal(10**6)
SCALE_WALLET = Decimal(10**9)

TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1w": 604800,
}


def get_candle_start(ts: int, tf_seconds: int) -> int:
    return ts - (ts % tf_seconds)

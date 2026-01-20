import asyncio
import json

import websockets

BASE_WS_URL = "ws://localhost:8124/api/v1"

MARKET_ID = "bnb-usdc-perp"
TIMEFRAME = "1m"  # đổi: 1m, 5m, 15m, 1h, 4h, 1d, 1w


async def test_candle_stream():
    uri = f"{BASE_WS_URL}/ws/candles/{MARKET_ID}/{TIMEFRAME}"

    async with websockets.connect(uri) as ws:
        print("✅ Connected to candle websocket")

        # 1️⃣ Message connected
        msg = await ws.recv()
        print("📩 CONNECTED:", msg)

        # 2️⃣ Stream candle updates
        while True:
            msg = await ws.recv()
            data = json.loads(msg)

            if data.get("type") == "error":
                print("❌ ERROR:", data)
                continue
            print(data)
            print(
                f"🕯 {data['market_id']} | {data['timeframe']} | "
                f"t={data['candle_start_timestamp']} | "
                f"ts={data['current_timestamp']} | "
                f"O={data['open']} "
                f"H={data['high']} "
                f"L={data['low']} "
                f"C={data['close']} | "
                f"finished={data.get('is_finished', False)}"
            )


if __name__ == "__main__":
    asyncio.run(test_candle_stream())

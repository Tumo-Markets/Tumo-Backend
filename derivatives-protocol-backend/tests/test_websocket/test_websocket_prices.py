import asyncio
import json

import websockets

BASE_WS_URL = "ws://localhost:8124/api/v1"

MARKET_ID = "bnb-usdc-perp"


async def test_price_stream():
    uri = f"{BASE_WS_URL}/ws/prices/{MARKET_ID}"

    async with websockets.connect(uri) as ws:
        print("✅ Connected to price websocket")

        # Nhận message đầu tiên (connected)
        msg = await ws.recv()
        print("📩", msg)

        # Nhận vài price update
        for _ in range(5):
            msg = await ws.recv()
            data = json.loads(msg)

            print(
                f"📈 {data['symbol']} | "
                f"Price={data['price']} | "
                f"Age={data['age_seconds']}s"
            )


if __name__ == "__main__":
    asyncio.run(test_price_stream())

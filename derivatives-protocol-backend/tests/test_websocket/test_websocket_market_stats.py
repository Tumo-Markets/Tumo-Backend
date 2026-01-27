import asyncio
import json

import websockets

MARKET_ID = "bnb-usdc-perp"


async def test_market_stats():
    uri = f"ws://localhost:8124/api/v1/ws/market-stats/{MARKET_ID}"
    async with websockets.connect(uri) as ws:
        print("✅ Connected")

        while True:
            msg = await ws.recv()
            print(json.dumps(json.loads(msg), indent=2))


asyncio.run(test_market_stats())

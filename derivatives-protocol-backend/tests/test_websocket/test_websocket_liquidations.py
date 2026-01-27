import asyncio
import json

import websockets


async def test_liquidations():
    async with websockets.connect("ws://localhost:8124/api/v1/ws/liquidations") as ws:
        print("✅ Connected to liquidation alerts")

        while True:
            msg = await ws.recv()
            print("🚨", json.loads(msg))


asyncio.run(test_liquidations())

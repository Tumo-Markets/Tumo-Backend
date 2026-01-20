import asyncio
import json

import websockets

BASE_WS_URL = "ws://localhost:8124/api/v1"
USER_ADDRESS = "0xabc123..."  # lowercase


async def test_positions():
    uri = f"{BASE_WS_URL}/ws/positions/{USER_ADDRESS}"

    async with websockets.connect(uri) as ws:
        print("✅ Connected to positions websocket")

        while True:
            msg = await ws.recv()
            data = json.loads(msg)

            print("📩 Positions update:")
            print(json.dumps(data, indent=2))


if __name__ == "__main__":
    asyncio.run(test_positions())

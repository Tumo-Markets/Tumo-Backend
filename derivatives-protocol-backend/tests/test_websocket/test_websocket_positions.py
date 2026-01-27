import asyncio
import json

import websockets

BASE_WS_URL = "ws://localhost:8124/api/v1"
USER_ADDRESS = "0x71b2250b548a6a62c40e52bab8104a8e5050292cd47b9056ed6c94f3aceb81e7"


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

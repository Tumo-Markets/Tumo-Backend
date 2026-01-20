import asyncio
import json

import websockets

BASE_WS_URL = "ws://localhost:8124/api/v1"
USER_ADDRESS = "0x152534"


async def test_notifications():
    uri = f"{BASE_WS_URL}/ws/notifications/{USER_ADDRESS}"

    async with websockets.connect(uri) as ws:
        print("✅ Connected to notifications websocket")

        while True:
            msg = await ws.recv()
            data = json.loads(msg)

            print("🔔 Notification received:")
            print(json.dumps(data, indent=2))


if __name__ == "__main__":
    asyncio.run(test_notifications())

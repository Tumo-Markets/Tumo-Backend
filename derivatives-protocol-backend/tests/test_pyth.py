import asyncio
import json
import time
from dataclasses import dataclass
from decimal import Decimal

import websockets

PYTH_WS_ENDPOINT = "wss://hermes.pyth.network/ws"

PRICE_FEED_IDS = [
    "0xff61491a931112ddf1bd8147cd1b641375f79f5825126d665480874634fd0ace",  # ETH/USD
]


@dataclass
class PriceData:
    price: Decimal
    confidence: Decimal
    publish_time: int

    @property
    def age_seconds(self) -> int:
        return int(time.time() - self.publish_time)


class PythPriceStreamer:
    def __init__(self):
        self.prices = {}  # price_feed_id -> PriceData

    async def start(self):
        async with websockets.connect(PYTH_WS_ENDPOINT, ping_interval=20) as ws:
            print("✅ Connected to Pyth")

            # Subscribe to price feeds
            await ws.send(json.dumps({"type": "subscribe", "ids": PRICE_FEED_IDS}))

            print("📡 Subscribed to price feeds")

            async for message in ws:
                self.handle_message(message)

    def handle_message(self, message: str):
        data = json.loads(message)

        if data.get("type") != "price_update":
            return

        feed = data["price_feed"]
        feed_id = feed["id"]

        price_obj = feed.get("price")
        ema_obj = feed.get("ema_price")

        if not price_obj or not ema_obj:
            return

        expo = price_obj["expo"]

        price = Decimal(price_obj["price"]) * (Decimal(10) ** expo)
        confidence = Decimal(ema_obj["conf"]) * (Decimal(10) ** expo)

        price_data = PriceData(
            price=price,
            confidence=confidence,
            publish_time=price_obj["publish_time"],
        )

        self.prices[feed_id] = price_data

        print(
            f"📈 Price update | "
            f"Feed: {feed_id[:8]}... | "
            f"Price: {price:.2f} | "
            f"Conf: ±{confidence:.4f} | "
            f"Age: {price_data.age_seconds}s"
        )


async def main():
    streamer = PythPriceStreamer()
    await streamer.start()


if __name__ == "__main__":
    asyncio.run(main())

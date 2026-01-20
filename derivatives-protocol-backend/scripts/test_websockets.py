#!/usr/bin/env python3
"""
WebSocket Client Examples in Python

Test WebSocket endpoints using Python asyncio and websockets library.

Install: pip install websockets

Usage: python scripts/test_websockets.py
"""

import asyncio
import json
import websockets
from datetime import datetime


# Base URL for WebSocket
WS_BASE_URL = "ws://localhost:8000/api/v1"


async def test_price_stream(market_id: str = "btc-usdc-perp"):
    """
    Test price streaming for a market.
    
    Args:
        market_id: Market identifier
    """
    url = f"{WS_BASE_URL}/ws/prices/{market_id}"
    
    print(f"Connecting to price stream: {url}")
    
    async with websockets.connect(url) as websocket:
        print(f"✅ Connected to price stream for {market_id}")
        
        # Receive messages
        try:
            async for message in websocket:
                data = json.loads(message)
                
                if data["type"] == "connected":
                    print(f"📡 {data['message']}")
                
                elif data["type"] == "price_update":
                    print(f"\n💰 Price Update:")
                    print(f"   Market: {data['symbol']}")
                    print(f"   Price: ${data['price']}")
                    print(f"   Confidence: {data['confidence']}")
                    print(f"   Age: {data['age_seconds']}s")
                    
        except websockets.exceptions.ConnectionClosed:
            print("❌ Connection closed")


async def test_position_stream(user_address: str):
    """
    Test position streaming for a user.
    
    Args:
        user_address: User wallet address
    """
    url = f"{WS_BASE_URL}/ws/positions/{user_address}"
    
    print(f"Connecting to position stream: {url}")
    
    async with websockets.connect(url) as websocket:
        print(f"✅ Connected to position stream for {user_address}")
        
        try:
            async for message in websocket:
                data = json.loads(message)
                
                if data["type"] == "connected":
                    print(f"📡 {data['message']}")
                
                elif data["type"] == "positions_update":
                    print(f"\n📊 Position Update:")
                    print(f"   User: {data['user_address']}")
                    print(f"   Total Unrealized PnL: ${data['total_unrealized_pnl']}")
                    print(f"   Positions: {len(data['positions'])}")
                    
                    for pos in data['positions']:
                        print(f"\n   Position: {pos['position_id'][:10]}...")
                        print(f"     Market: {pos['symbol']}")
                        print(f"     Side: {pos['side'].upper()}")
                        print(f"     Size: {pos['size']}")
                        print(f"     Entry: ${pos['entry_price']}")
                        print(f"     Current: ${pos['current_price']}")
                        print(f"     Unrealized PnL: ${pos['unrealized_pnl']}")
                        print(f"     Health Factor: {pos['health_factor']}")
                        
                        if pos['is_at_risk']:
                            print(f"     ⚠️  AT RISK OF LIQUIDATION!")
                
                elif data["type"] == "liquidation_warning":
                    print(f"\n⚠️  LIQUIDATION WARNING!")
                    print(f"   Position: {data['data']['position_id']}")
                    print(f"   Health: {data['data']['health_factor']}")
                    print(f"   Liq Price: ${data['data']['liquidation_price']}")
                
                elif data["type"] == "position_opened":
                    print(f"\n🟢 New Position Opened:")
                    print(f"   Position: {data['data']['position_id'][:10]}...")
                    print(f"   Side: {data['data']['side'].upper()}")
                    print(f"   Size: {data['data']['size']}")
                
                elif data["type"] == "position_closed":
                    print(f"\n🔴 Position Closed:")
                    print(f"   Position: {data['data']['position_id'][:10]}...")
                    print(f"   Realized PnL: ${data['data']['realized_pnl']}")
                
                elif data["type"] == "position_liquidated":
                    print(f"\n💥 Position Liquidated:")
                    print(f"   Position: {data['data']['position_id'][:10]}...")
                    print(f"   Liquidation Price: ${data['data']['liquidation_price']}")
                    
        except websockets.exceptions.ConnectionClosed:
            print("❌ Connection closed")


async def test_liquidation_stream():
    """Test liquidation alerts stream."""
    url = f"{WS_BASE_URL}/ws/liquidations"
    
    print(f"Connecting to liquidation stream: {url}")
    
    async with websockets.connect(url) as websocket:
        print(f"✅ Connected to liquidation alerts")
        
        try:
            async for message in websocket:
                data = json.loads(message)
                
                if data["type"] == "connected":
                    print(f"📡 {data['message']}")
                
                elif data["type"] == "liquidation_alert":
                    print(f"\n⚠️  Liquidation Alert:")
                    print(f"   Candidates: {data['count']}")
                    
                    for candidate in data['candidates'][:5]:  # Show top 5
                        print(f"\n   Position: {candidate['position_id'][:10]}...")
                        print(f"     User: {candidate['user_address'][:10]}...")
                        print(f"     Market: {candidate['market_id']}")
                        print(f"     Health: {candidate['health_factor']}")
                        print(f"     Current Price: ${candidate['current_price']}")
                        print(f"     Liq Price: ${candidate['liquidation_price']}")
                        print(f"     Potential Reward: ${candidate['potential_reward']}")
                    
        except websockets.exceptions.ConnectionClosed:
            print("❌ Connection closed")


async def test_market_stats_stream(market_id: str = "btc-usdc-perp"):
    """
    Test market statistics stream.
    
    Args:
        market_id: Market identifier
    """
    url = f"{WS_BASE_URL}/ws/market-stats/{market_id}"
    
    print(f"Connecting to market stats stream: {url}")
    
    async with websockets.connect(url) as websocket:
        print(f"✅ Connected to market stats for {market_id}")
        
        try:
            async for message in websocket:
                data = json.loads(message)
                
                if data["type"] == "connected":
                    print(f"📡 {data['message']}")
                
                elif data["type"] == "market_stats":
                    print(f"\n📈 Market Stats Update:")
                    print(f"   Market: {data['symbol']}")
                    print(f"   Price: ${data['current_price']}")
                    print(f"   Long OI: ${data['total_long_oi']}")
                    print(f"   Short OI: ${data['total_short_oi']}")
                    print(f"   Total OI: ${data['total_oi']}")
                    print(f"   Funding Rate: {data['funding_rate']}")
                
                elif data["type"] == "funding_rate_update":
                    print(f"\n💵 Funding Rate Update:")
                    print(f"   Market: {data['data']['market_id']}")
                    print(f"   New Rate: {data['data']['funding_rate']}")
                    print(f"   Long OI: ${data['data']['long_oi']}")
                    print(f"   Short OI: ${data['data']['short_oi']}")
                    
        except websockets.exceptions.ConnectionClosed:
            print("❌ Connection closed")


async def test_all_streams():
    """Test all WebSocket streams simultaneously."""
    print("=" * 60)
    print("Testing All WebSocket Streams")
    print("=" * 60)
    print()
    
    # Run all tests concurrently
    tasks = [
        test_price_stream("btc-usdc-perp"),
        test_market_stats_stream("btc-usdc-perp"),
        test_liquidation_stream(),
        # Uncomment to test position stream (need a valid user address)
        # test_position_stream("0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"),
    ]
    
    # Run for 30 seconds then stop
    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks),
            timeout=30.0
        )
    except asyncio.TimeoutError:
        print("\n⏰ Test completed after 30 seconds")


async def interactive_menu():
    """Interactive menu to choose which stream to test."""
    print("=" * 60)
    print("WebSocket Test Menu")
    print("=" * 60)
    print()
    print("1. Price Stream (BTC/USDC)")
    print("2. Position Stream (requires user address)")
    print("3. Liquidation Alerts")
    print("4. Market Stats (BTC/USDC)")
    print("5. Test All Streams")
    print("0. Exit")
    print()
    
    choice = input("Select option: ").strip()
    
    if choice == "1":
        await test_price_stream("btc-usdc-perp")
    elif choice == "2":
        address = input("Enter user address: ").strip()
        await test_position_stream(address)
    elif choice == "3":
        await test_liquidation_stream()
    elif choice == "4":
        await test_market_stats_stream("btc-usdc-perp")
    elif choice == "5":
        await test_all_streams()
    elif choice == "0":
        print("Goodbye!")
        return
    else:
        print("Invalid option")


async def main():
    """Main function."""
    try:
        # Run interactive menu
        await interactive_menu()
    except KeyboardInterrupt:
        print("\n\n👋 Disconnected")
    except Exception as e:
        print(f"\n❌ Error: {e}")


if __name__ == "__main__":
    # Make sure the server is running first!
    print("⚠️  Make sure the server is running at localhost:8000")
    print()
    
    asyncio.run(main())

#!/usr/bin/env python3
"""
Example API usage script.

Demonstrates how to interact with the Derivatives Protocol API.

Usage:
    python scripts/test_api.py
"""

import asyncio
import httpx
from decimal import Decimal


BASE_URL = "http://localhost:8000/api/v1"


async def test_health():
    """Test health check endpoint."""
    print("Testing health check...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/health")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        print()


async def test_get_markets():
    """Test getting markets list."""
    print("Testing get markets...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/markets")
        data = response.json()
        print(f"Total markets: {data['total']}")
        if data['items']:
            print(f"First market: {data['items'][0]['symbol']}")
        print()


async def test_get_market_stats():
    """Test getting market statistics."""
    print("Testing market stats...")
    async with httpx.AsyncClient() as client:
        # First get markets to find a valid market_id
        response = await client.get(f"{BASE_URL}/markets")
        markets = response.json()
        
        if markets['items']:
            market_id = markets['items'][0]['market_id']
            
            response = await client.get(f"{BASE_URL}/markets/{market_id}/stats")
            stats = response.json()
            
            if stats['success']:
                data = stats['data']
                print(f"Market: {data['symbol']}")
                print(f"Mark Price: {data.get('mark_price', 'N/A')}")
                print(f"Total OI: {data['total_oi']}")
                print(f"Funding Rate: {data['current_funding_rate']}")
            print()


async def test_get_positions():
    """Test getting positions."""
    print("Testing get positions...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/positions")
        data = response.json()
        print(f"Total positions: {data['total']}")
        print(f"Open positions on page: {len(data['items'])}")
        print()


async def test_oracle_price():
    """Test getting oracle price."""
    print("Testing oracle price...")
    
    # BTC/USD price feed ID
    btc_price_id = "0xe62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BASE_URL}/oracle/price/{btc_price_id}")
            if response.status_code == 200:
                data = response.json()
                if data['success']:
                    price_data = data['data']
                    # Calculate actual price
                    price = Decimal(price_data['price']) * Decimal(10) ** price_data['expo']
                    print(f"BTC Price: ${price}")
                    print(f"Confidence: {price_data['confidence']}")
                    print(f"Age: {price_data.get('age_seconds', 'N/A')} seconds")
            else:
                print(f"Error: {response.status_code}")
        except Exception as e:
            print(f"Error fetching price: {e}")
        print()


async def test_system_stats():
    """Test getting system statistics."""
    print("Testing system stats...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/stats")
        data = response.json()
        
        if data['success']:
            stats = data['data']
            print(f"Total Markets: {stats['total_markets']}")
            print(f"Total Positions: {stats['total_positions']}")
            print(f"Open Positions: {stats['open_positions']}")
            print(f"Total Long OI: {stats['total_long_oi']}")
            print(f"Total Short OI: {stats['total_short_oi']}")
        print()


async def test_liquidation_status():
    """Test getting liquidation bot status."""
    print("Testing liquidation status...")
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/liquidation/status")
        data = response.json()
        
        if data['success']:
            status = data['data']
            print(f"Bot Running: {status['is_running']}")
            print(f"Candidates: {status['total_candidates']}")
            print(f"Potential Reward: {status['total_potential_reward']}")
        print()


async def main():
    """Run all tests."""
    print("=" * 60)
    print("Derivatives Protocol API - Test Examples")
    print("=" * 60)
    print()
    
    try:
        await test_health()
        await test_get_markets()
        await test_get_market_stats()
        await test_get_positions()
        await test_oracle_price()
        await test_system_stats()
        await test_liquidation_status()
        
        print("=" * 60)
        print("All tests completed!")
        print("=" * 60)
        
    except httpx.ConnectError:
        print("ERROR: Cannot connect to API server.")
        print("Make sure the server is running at", BASE_URL)
        print("\nStart server with: python -m app.main")
    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    asyncio.run(main())

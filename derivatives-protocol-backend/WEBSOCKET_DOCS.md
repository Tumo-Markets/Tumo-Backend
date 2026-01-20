# WebSocket Documentation

## Overview

Backend cung cấp **real-time WebSocket connections** cho các tính năng:

1. 📊 **Price Updates** - Real-time price feeds
2. 💼 **Position Updates** - Live PnL and health metrics
3. ⚠️ **Liquidation Alerts** - Position liquidation warnings
4. 📈 **Market Stats** - Market statistics updates
5. 🔔 **Event Broadcasting** - Blockchain events

---

## 🔌 WebSocket Endpoints

### Base URL
```
ws://localhost:8000/api/v1/ws
```

---

## 1. Price Stream

**Endpoint:** `/ws/prices/{market_id}`

**Description:** Real-time price updates for a specific market from Pyth Oracle.

**Update Frequency:** Every 1 second

**Message Types:**

#### Connected
```json
{
  "type": "connected",
  "market_id": "btc-usdc-perp",
  "symbol": "BTC/USDC",
  "message": "Connected to price stream"
}
```

#### Price Update
```json
{
  "type": "price_update",
  "market_id": "btc-usdc-perp",
  "symbol": "BTC/USDC",
  "price": "50000.50",
  "confidence": "10.25",
  "timestamp": 1705330800,
  "age_seconds": 1
}
```

**Example (JavaScript):**
```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/ws/prices/btc-usdc-perp');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'price_update') {
        console.log(`Price: $${data.price}`);
    }
};
```

**Example (Python):**
```python
import asyncio
import websockets

async def price_stream():
    async with websockets.connect('ws://localhost:8000/api/v1/ws/prices/btc-usdc-perp') as ws:
        async for message in ws:
            data = json.loads(message)
            print(f"Price: ${data['price']}")

asyncio.run(price_stream())
```

---

## 2. Position Stream

**Endpoint:** `/ws/positions/{user_address}`

**Description:** Real-time updates for all user's open positions including PnL and health metrics.

**Update Frequency:** Every 2 seconds

**Message Types:**

#### Connected
```json
{
  "type": "connected",
  "user_address": "0x742d35cc...",
  "message": "Connected to position updates"
}
```

#### Positions Update
```json
{
  "type": "positions_update",
  "user_address": "0x742d35cc...",
  "positions": [
    {
      "position_id": "0xabc123...",
      "market_id": "btc-usdc-perp",
      "symbol": "BTC/USDC",
      "side": "long",
      "size": "1.5",
      "entry_price": "50000",
      "current_price": "51000",
      "unrealized_pnl": "1500",
      "health_factor": "2.5",
      "liquidation_price": "47500",
      "is_at_risk": false
    }
  ],
  "total_unrealized_pnl": "1500",
  "timestamp": "2024-01-15T10:00:00Z"
}
```

#### Liquidation Warning (Critical!)
```json
{
  "type": "liquidation_warning",
  "data": {
    "position_id": "0xabc123...",
    "market_id": "btc-usdc-perp",
    "health_factor": "1.05",
    "liquidation_price": "48000",
    "message": "⚠️ Your position is at risk of liquidation!"
  },
  "timestamp": "2024-01-15T10:00:00Z"
}
```

#### Position Opened
```json
{
  "type": "position_opened",
  "data": {
    "position_id": "0xnew...",
    "user_address": "0x742d35cc...",
    "market_id": "btc-usdc-perp",
    "side": "long",
    "size": "2.0",
    "collateral": "10000",
    "leverage": "5",
    "entry_price": "50000",
    "transaction_hash": "0xtx..."
  },
  "timestamp": "2024-01-15T10:00:00Z"
}
```

#### Position Closed
```json
{
  "type": "position_closed",
  "data": {
    "position_id": "0xabc123...",
    "user_address": "0x742d35cc...",
    "market_id": "btc-usdc-perp",
    "exit_price": "51000",
    "realized_pnl": "1500",
    "transaction_hash": "0xtx..."
  },
  "timestamp": "2024-01-15T10:00:00Z"
}
```

#### Position Liquidated
```json
{
  "type": "position_liquidated",
  "data": {
    "position_id": "0xabc123...",
    "user_address": "0x742d35cc...",
    "market_id": "btc-usdc-perp",
    "liquidator_address": "0xliq...",
    "liquidation_price": "47500",
    "liquidation_fee": "50",
    "transaction_hash": "0xtx..."
  },
  "timestamp": "2024-01-15T10:00:00Z"
}
```

**Example:**
```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/ws/positions/0x742d35cc...');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.type === 'liquidation_warning') {
        // URGENT: Show warning to user!
        alert(`⚠️ Liquidation Warning! Health: ${data.data.health_factor}`);
    }
    else if (data.type === 'positions_update') {
        // Update UI with latest PnL
        updatePositionsUI(data.positions);
    }
};
```

---

## 3. Liquidation Alerts

**Endpoint:** `/ws/liquidations`

**Description:** Stream of positions at risk of liquidation (for liquidation bots or monitoring dashboards).

**Update Frequency:** Every 5 seconds

**Message Types:**

#### Liquidation Alert
```json
{
  "type": "liquidation_alert",
  "count": 5,
  "candidates": [
    {
      "position_id": "0xabc...",
      "user_address": "0x123...",
      "market_id": "btc-usdc-perp",
      "health_factor": "0.95",
      "liquidation_price": "48000",
      "current_price": "48500",
      "potential_reward": "50.5"
    }
  ],
  "timestamp": "2024-01-15T10:00:00Z"
}
```

**Example (Liquidation Bot):**
```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/ws/liquidations');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.type === 'liquidation_alert' && data.count > 0) {
        // Process liquidation opportunities
        data.candidates.forEach(candidate => {
            if (parseFloat(candidate.potential_reward) > 50) {
                attemptLiquidation(candidate);
            }
        });
    }
};
```

---

## 4. Market Statistics

**Endpoint:** `/ws/market-stats/{market_id}`

**Description:** Real-time market statistics including OI, funding rate, and volume.

**Update Frequency:** Every 5 seconds

**Message Types:**

#### Market Stats
```json
{
  "type": "market_stats",
  "market_id": "btc-usdc-perp",
  "symbol": "BTC/USDC",
  "current_price": "50000",
  "total_long_oi": "1000000",
  "total_short_oi": "950000",
  "total_oi": "1950000",
  "funding_rate": "0.0001",
  "last_funding_update": "2024-01-15T09:00:00Z",
  "timestamp": "2024-01-15T10:00:00Z"
}
```

#### Funding Rate Update
```json
{
  "type": "funding_rate_update",
  "data": {
    "market_id": "btc-usdc-perp",
    "funding_rate": "0.00015",
    "long_oi": "1100000",
    "short_oi": "950000"
  },
  "timestamp": "2024-01-15T10:00:00Z"
}
```

---

## 🔧 Best Practices

### 1. Connection Management

```javascript
class WebSocketManager {
    constructor(url) {
        this.url = url;
        this.ws = null;
        this.reconnectDelay = 5000;
    }
    
    connect() {
        this.ws = new WebSocket(this.url);
        
        this.ws.onopen = () => {
            console.log('Connected');
            this.reconnectDelay = 5000; // Reset delay
        };
        
        this.ws.onclose = () => {
            console.log('Disconnected, reconnecting...');
            setTimeout(() => this.connect(), this.reconnectDelay);
            this.reconnectDelay = Math.min(this.reconnectDelay * 2, 60000); // Exponential backoff
        };
        
        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }
    
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }
}
```

### 2. Error Handling

```javascript
ws.onmessage = (event) => {
    try {
        const data = JSON.parse(event.data);
        handleMessage(data);
    } catch (error) {
        console.error('Error parsing message:', error);
    }
};
```

### 3. Clean Up

```javascript
// Always clean up on page unload
window.addEventListener('beforeunload', () => {
    if (ws) {
        ws.close();
    }
});
```

### 4. Multiple Connections

```javascript
const connections = {
    prices: new WebSocket('ws://localhost:8000/api/v1/ws/prices/btc-usdc-perp'),
    positions: new WebSocket('ws://localhost:8000/api/v1/ws/positions/0x...'),
    liquidations: new WebSocket('ws://localhost:8000/api/v1/ws/liquidations'),
};

// Clean up all
function disconnectAll() {
    Object.values(connections).forEach(ws => ws.close());
}
```

---

## 📊 Performance Considerations

### Update Frequencies
- **Price Stream**: 1 second (real-time)
- **Position Stream**: 2 seconds (balance between freshness and load)
- **Liquidation Alerts**: 5 seconds (frequent enough for monitoring)
- **Market Stats**: 5 seconds (stats change slowly)

### Connection Limits
- No hard limit per user
- Backend uses connection manager to handle many concurrent connections
- Dead connections are automatically cleaned up

### Bandwidth
- Average message size: 500 bytes - 2KB
- Price stream: ~2KB/second per market
- Position stream: ~5KB/update (depends on number of positions)

---

## 🧪 Testing

### Test WebSocket with JavaScript
```bash
# See example file
scripts/websocket_client_examples.js
```

### Test WebSocket with Python
```bash
# Install websockets
pip install websockets

# Run test script
python scripts/test_websockets.py
```

### Test with wscat (CLI tool)
```bash
# Install wscat
npm install -g wscat

# Connect to price stream
wscat -c ws://localhost:8000/api/v1/ws/prices/btc-usdc-perp

# Connect to liquidations
wscat -c ws://localhost:8000/api/v1/ws/liquidations
```

---

## 🎯 Use Cases

### Trading Dashboard
- Subscribe to prices for all markets
- Subscribe to user's positions
- Display real-time PnL
- Show liquidation warnings

### Liquidation Bot
- Subscribe to liquidation alerts
- Monitor positions at risk
- Execute liquidations automatically

### Market Analytics
- Subscribe to market stats
- Track OI changes
- Monitor funding rates
- Display market trends

### Mobile App
- Subscribe to user positions
- Push notifications for liquidation warnings
- Real-time portfolio updates

---

## ⚠️ Important Notes

1. **Liquidation Warnings are Critical**
   - Always implement UI alerts for liquidation warnings
   - Consider push notifications
   - Health factor < 1.2 means position is at risk

2. **Reconnection Logic**
   - Always implement automatic reconnection
   - Use exponential backoff
   - Don't hammer the server

3. **Message Handling**
   - Always parse JSON with try/catch
   - Handle unknown message types gracefully
   - Validate data before using

4. **Security**
   - WebSocket connections are public
   - Don't send sensitive data over WebSocket
   - User authentication should be done via REST API

---

## 📈 Monitoring

Check WebSocket statistics:
```bash
GET /api/v1/ws/stats
```

Response:
```json
{
  "success": true,
  "data": {
    "total_connections": 45,
    "by_type": {
      "prices": 20,
      "positions": 10,
      "liquidations": 5,
      "events": 10
    },
    "user_connections": 10,
    "market_connections": 15
  }
}
```

---

## 🔗 Related Documentation

- [API_DOCS.md](API_DOCS.md) - REST API documentation
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture
- [scripts/websocket_client_examples.js](../scripts/websocket_client_examples.js) - JavaScript examples
- [scripts/test_websockets.py](../scripts/test_websockets.py) - Python examples

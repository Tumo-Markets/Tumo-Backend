# API Documentation

## Base URL
```
http://localhost:8000/api/v1
```

## Authentication
Currently no authentication required. In production, implement JWT or API keys.

---

## Markets Endpoints

### List Markets
```http
GET /markets
```

**Query Parameters:**
- `page` (int): Page number (default: 1)
- `page_size` (int): Items per page (default: 20, max: 100)
- `status` (string): Filter by status (active, paused, closed)

**Response:**
```json
{
  "items": [...],
  "total": 10,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

### Get Market Details
```http
GET /markets/{market_id}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "market_id": "btc-usdc-perp",
    "symbol": "BTC/USDC",
    "max_leverage": "100",
    "status": "active",
    ...
  }
}
```

### Get Market Statistics
```http
GET /markets/{market_id}/stats
```

**Response:**
```json
{
  "success": true,
  "data": {
    "market_id": "btc-usdc-perp",
    "symbol": "BTC/USDC",
    "mark_price": "50000.50",
    "total_long_oi": "1000.5",
    "total_short_oi": "950.2",
    "current_funding_rate": "0.0001",
    "next_funding_time": "2024-01-15T12:00:00Z"
  }
}
```

### Get Funding Rate History
```http
GET /markets/{market_id}/funding-history?hours=24
```

**Query Parameters:**
- `hours` (int): Number of hours (default: 24, max: 168)

---

## Positions Endpoints

### List Positions
```http
GET /positions
```

**Query Parameters:**
- `user_address` (string): Filter by user
- `market_id` (string): Filter by market
- `status` (string): Filter by status
- `page` (int): Page number
- `page_size` (int): Items per page

### Get Position Details
```http
GET /positions/{position_id}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "position_id": "0x...",
    "market_id": "btc-usdc-perp",
    "user_address": "0x...",
    "side": "long",
    "size": "1.5",
    "collateral": "5000",
    "leverage": "10",
    "entry_price": "50000",
    "current_price": "51000",
    "unrealized_pnl": "1500",
    "health_factor": "2.5",
    "liquidation_price": "47500"
  }
}
```

### Get User Position Summary
```http
GET /positions/user/{address}/summary
```

**Response:**
```json
{
  "success": true,
  "data": {
    "user_address": "0x...",
    "total_positions": 5,
    "open_positions": 2,
    "total_collateral": "10000",
    "total_unrealized_pnl": "500",
    "total_realized_pnl": "1200"
  }
}
```

### Get Liquidation Candidates
```http
GET /positions/liquidation/candidates?limit=10
```

**Response:**
```json
{
  "success": true,
  "data": [
    {
      "position_id": "0x...",
      "user_address": "0x...",
      "health_factor": "0.95",
      "liquidation_price": "49000",
      "potential_reward": "50"
    }
  ]
}
```

---

## Oracle Endpoints

### Get Latest Price
```http
GET /oracle/price/{price_feed_id}
```

**Example:**
```http
GET /oracle/price/0xe62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43
```

**Response:**
```json
{
  "success": true,
  "data": {
    "price_id": "0xe62df...",
    "price": "5000000000",
    "confidence": "1000000",
    "expo": -8,
    "publish_time": 1705330800
  }
}
```

### Get Multiple Prices
```http
POST /oracle/prices
Content-Type: application/json

["0xe62df...", "0xff614..."]
```

---

## System Endpoints

### Health Check
```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:00:00Z",
  "version": "1.0.0",
  "database": true,
  "blockchain": true,
  "oracle": true
}
```

### System Statistics
```http
GET /stats
```

**Response:**
```json
{
  "success": true,
  "data": {
    "total_markets": 4,
    "total_positions": 150,
    "open_positions": 75,
    "total_volume_24h": "1000000",
    "total_long_oi": "500000",
    "total_short_oi": "480000"
  }
}
```

### Liquidation Bot Status
```http
GET /liquidation/status
```

**Response:**
```json
{
  "success": true,
  "data": {
    "is_running": true,
    "total_candidates": 3,
    "total_potential_reward": "150",
    "check_interval": 10,
    "min_health_factor": "1.0"
  }
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "success": false,
  "error": "Error message",
  "detail": "Detailed error description"
}
```

**Common Status Codes:**
- `200` - Success
- `400` - Bad Request
- `404` - Not Found
- `500` - Internal Server Error

---

## WebSocket Support (Future)

Plan to add WebSocket endpoints for:
- Real-time price updates
- Position updates
- Liquidation alerts
- Funding rate updates

---

## Rate Limiting

Currently no rate limiting. Recommended to implement in production:
- General endpoints: 100 req/min
- Price endpoints: 1000 req/min
- User-specific: 50 req/min

---

## Interactive Documentation

Once the server is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

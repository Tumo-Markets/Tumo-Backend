# 🔐 ADMIN APIs - Market Management

## Overview

Admin APIs cho phép **quản lý markets** trong hệ thống:
- ✅ Tạo market mới
- ✅ Cập nhật thông số market
- ✅ Pause/Resume market
- ✅ Xóa market (soft delete)
- ✅ Bulk create markets

---

## 🚨 LƯU Ý QUAN TRỌNG

### Security
⚠️ **Admin APIs KHÔNG có authentication trong code hiện tại!**

**Trong production, BẮT BUỘC phải:**
1. Implement authentication (JWT, API keys)
2. Implement authorization (admin role)
3. Rate limiting
4. Audit logging

**Khuyến nghị:**
- Chỉ expose admin endpoints cho internal network
- Sử dụng API Gateway với authentication
- Log tất cả admin actions

---

## 📡 ADMIN API ENDPOINTS

### Base URL
```
POST   /api/v1/admin/markets
PUT    /api/v1/admin/markets/{market_id}
PATCH  /api/v1/admin/markets/{market_id}/pause
PATCH  /api/v1/admin/markets/{market_id}/resume
DELETE /api/v1/admin/markets/{market_id}
POST   /api/v1/admin/markets/bulk
```

---

## 1. CREATE MARKET

### Endpoint
```
POST /api/v1/admin/markets
```

### Request Body
```json
{
  "market_id": "bnb-usdc-perp",
  "base_token": "0x0000000000000000000000000000000000000005",
  "quote_token": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
  "symbol": "BNB/USDC",
  "pyth_price_id": "0x2f95862b045670cd22bee3114c39763a4a08beeb663b145d283c31d7d1101c4f",
  "max_leverage": "50",
  "min_position_size": "0.01",
  "max_position_size": "1000",
  "maintenance_margin_rate": "0.05",
  "liquidation_fee_rate": "0.01",
  "funding_rate_interval": 3600,
  "max_funding_rate": "0.001"
}
```

### Response
```json
{
  "success": true,
  "message": "Market BNB/USDC created successfully",
  "data": {
    "id": 5,
    "market_id": "bnb-usdc-perp",
    "symbol": "BNB/USDC",
    "status": "active",
    "max_leverage": "50",
    "created_at": "2024-01-15T10:00:00Z"
  }
}
```

### cURL Example
```bash
curl -X POST http://localhost:8000/api/v1/admin/markets \
  -H "Content-Type: application/json" \
  -d '{
    "market_id": "bnb-usdc-perp",
    "base_token": "0x0000000000000000000000000000000000000005",
    "quote_token": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
    "symbol": "BNB/USDC",
    "pyth_price_id": "0x2f95862b045670cd22bee3114c39763a4a08beeb663b145d283c31d7d1101c4f",
    "max_leverage": "50",
    "min_position_size": "0.01",
    "max_position_size": "1000",
    "maintenance_margin_rate": "0.05",
    "liquidation_fee_rate": "0.01"
  }'
```

---

## 2. UPDATE MARKET

### Endpoint
```
PUT /api/v1/admin/markets/{market_id}
```

### Request Body (tất cả fields optional)
```json
{
  "max_leverage": "100",
  "maintenance_margin_rate": "0.04",
  "max_funding_rate": "0.002"
}
```

### Response
```json
{
  "success": true,
  "message": "Market BTC/USDC updated successfully",
  "data": {
    "market_id": "btc-usdc-perp",
    "max_leverage": "100",
    "maintenance_margin_rate": "0.04",
    ...
  }
}
```

### cURL Example
```bash
curl -X PUT http://localhost:8000/api/v1/admin/markets/btc-usdc-perp \
  -H "Content-Type: application/json" \
  -d '{
    "max_leverage": "100",
    "maintenance_margin_rate": "0.04"
  }'
```

---

## 3. PAUSE MARKET

### Endpoint
```
PATCH /api/v1/admin/markets/{market_id}/pause
```

### Request Body
Không cần

### Response
```json
{
  "success": true,
  "message": "Market BTC/USDC paused",
  "data": {
    "market_id": "btc-usdc-perp",
    "status": "paused",
    ...
  }
}
```

### cURL Example
```bash
curl -X PATCH http://localhost:8000/api/v1/admin/markets/btc-usdc-perp/pause
```

### Mô tả
- Market status → "paused"
- Users KHÔNG thể open positions mới
- Existing positions vẫn hoạt động bình thường
- Liquidation vẫn chạy

---

## 4. RESUME MARKET

### Endpoint
```
PATCH /api/v1/admin/markets/{market_id}/resume
```

### Request Body
Không cần

### Response
```json
{
  "success": true,
  "message": "Market BTC/USDC resumed",
  "data": {
    "market_id": "btc-usdc-perp",
    "status": "active",
    ...
  }
}
```

### cURL Example
```bash
curl -X PATCH http://localhost:8000/api/v1/admin/markets/btc-usdc-perp/resume
```

---

## 5. DELETE MARKET (Soft Delete)

### Endpoint
```
DELETE /api/v1/admin/markets/{market_id}
```

### Request Body
Không cần

### Response
```
HTTP 204 No Content
```

### cURL Example
```bash
curl -X DELETE http://localhost:8000/api/v1/admin/markets/btc-usdc-perp
```

### Mô tả
- **Soft delete** - market status → "closed"
- Chỉ delete được nếu KHÔNG có open positions
- Nếu có open positions → Error 400

### Error Response
```json
{
  "success": false,
  "error": "Cannot delete market with open positions"
}
```

---

## 6. BULK CREATE MARKETS

### Endpoint
```
POST /api/v1/admin/markets/bulk
```

### Request Body
```json
[
  {
    "market_id": "avax-usdc-perp",
    "base_token": "0x...",
    "quote_token": "0x...",
    "symbol": "AVAX/USDC",
    "pyth_price_id": "0x...",
    "max_leverage": "20",
    ...
  },
  {
    "market_id": "matic-usdc-perp",
    "base_token": "0x...",
    "quote_token": "0x...",
    "symbol": "MATIC/USDC",
    "pyth_price_id": "0x...",
    "max_leverage": "20",
    ...
  }
]
```

### Response
```json
{
  "success": true,
  "message": "Created 2 markets successfully",
  "data": [
    { "market_id": "avax-usdc-perp", ... },
    { "market_id": "matic-usdc-perp", ... }
  ]
}
```

### cURL Example
```bash
curl -X POST http://localhost:8000/api/v1/admin/markets/bulk \
  -H "Content-Type: application/json" \
  -d '[
    {
      "market_id": "avax-usdc-perp",
      "symbol": "AVAX/USDC",
      ...
    },
    {
      "market_id": "matic-usdc-perp",
      "symbol": "MATIC/USDC",
      ...
    }
  ]'
```

---

## 📝 PYTHON EXAMPLES

### Create Market
```python
import httpx

async def create_market():
    async with httpx.AsyncClient() as client:
        market_data = {
            "market_id": "bnb-usdc-perp",
            "base_token": "0x...",
            "quote_token": "0x...",
            "symbol": "BNB/USDC",
            "pyth_price_id": "0x...",
            "max_leverage": "50",
            "min_position_size": "0.01",
            "max_position_size": "1000",
            "maintenance_margin_rate": "0.05",
            "liquidation_fee_rate": "0.01",
        }
        
        response = await client.post(
            "http://localhost:8000/api/v1/admin/markets",
            json=market_data
        )
        
        if response.status_code == 201:
            print("✅ Market created:", response.json())
        else:
            print("❌ Error:", response.json())
```

### Update Market
```python
async def update_market(market_id: str):
    async with httpx.AsyncClient() as client:
        updates = {
            "max_leverage": "100",
            "maintenance_margin_rate": "0.04"
        }
        
        response = await client.put(
            f"http://localhost:8000/api/v1/admin/markets/{market_id}",
            json=updates
        )
        
        print(response.json())
```

### Pause Market
```python
async def pause_market(market_id: str):
    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"http://localhost:8000/api/v1/admin/markets/{market_id}/pause"
        )
        
        print(response.json())
```

---

## 🔍 VALIDATION RULES

### Market ID
- Format: `{base}-{quote}-{type}`
- Example: `btc-usdc-perp`
- Must be unique

### Leverage
- Min: 1
- Max: 100
- Example: 10, 20, 50, 100

### Position Size
- `min_position_size` < `max_position_size`
- Must be > 0

### Margin Rates
- `maintenance_margin_rate`: 0 < x < 1 (e.g., 0.05 = 5%)
- `liquidation_fee_rate`: 0 < x < 1 (e.g., 0.01 = 1%)

### Pyth Price Feed ID
- Must be valid Pyth price feed
- Format: `0x...` (66 characters)
- Get from: https://pyth.network/developers/price-feed-ids

---

## 🎯 USE CASES

### 1. Add New Token Market
```bash
# Step 1: Get Pyth price feed ID from https://pyth.network
# Step 2: Create market
curl -X POST http://localhost:8000/api/v1/admin/markets -d '{...}'

# Step 3: Verify
curl http://localhost:8000/api/v1/markets/new-market-id
```

### 2. Emergency Pause Market
```bash
# Pause trading immediately
curl -X PATCH http://localhost:8000/api/v1/admin/markets/btc-usdc-perp/pause

# Users can't open new positions
# Can resume later with /resume
```

### 3. Adjust Risk Parameters
```bash
# Lower leverage during high volatility
curl -X PUT http://localhost:8000/api/v1/admin/markets/btc-usdc-perp \
  -d '{"max_leverage": "20"}'
```

### 4. Bulk Launch Multiple Markets
```bash
# Launch 10 new markets at once
curl -X POST http://localhost:8000/api/v1/admin/markets/bulk \
  -d '[{...}, {...}, ...]'
```

---

## 🛡️ SECURITY RECOMMENDATIONS

### 1. Implement Authentication
```python
# Add to admin.py
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def verify_admin(token = Depends(security)):
    # Verify JWT token
    # Check admin role
    if not is_admin(token):
        raise HTTPException(status_code=403, detail="Admin only")
    return token

# Apply to all admin endpoints
@router.post("/", dependencies=[Depends(verify_admin)])
async def create_market(...):
    ...
```

### 2. Rate Limiting
```python
from slowapi import Limiter

limiter = Limiter(key_func=get_remote_address)

@router.post("/", dependencies=[Depends(limiter.limit("10/hour"))])
async def create_market(...):
    ...
```

### 3. Audit Logging
```python
# Log all admin actions
logger.info(f"Admin {admin_id} created market {market_id}")
```

### 4. Network Restriction
```nginx
# Nginx config - only allow from internal IPs
location /api/v1/admin/ {
    allow 10.0.0.0/8;
    deny all;
    proxy_pass http://backend;
}
```

---

## ✅ CHECKLIST

### Before Production:
- [ ] Add authentication
- [ ] Add authorization (admin role)
- [ ] Add rate limiting
- [ ] Add audit logging
- [ ] Restrict network access
- [ ] Add input sanitization
- [ ] Add transaction rollback on errors
- [ ] Add webhook notifications
- [ ] Add market creation approval workflow

---

## 📚 Related Documentation

- [API_DOCS.md](API_DOCS.md) - Public APIs
- [WEBSOCKET_DOCS.md](WEBSOCKET_DOCS.md) - WebSocket APIs
- Market parameters: See `app/schemas/market.py`

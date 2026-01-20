# Permissionless Derivatives Protocol - Backend

Backend service cho Permissionless Derivatives Protocol, cung cấp:
- Indexing on-chain events
- Liquidation bot tự động
- Funding rate management
- REST API cho frontend
- **WebSocket real-time updates** ✨ NEW!

## 🏗️ Kiến trúc

```
app/
├── api/              # FastAPI endpoints
│   ├── markets.py    # Market endpoints
│   ├── positions.py  # Position endpoints
│   └── system.py     # System & oracle endpoints
├── core/             # Core configuration
│   └── config.py     # Settings với Pydantic
├── db/               # Database
│   ├── models.py     # SQLAlchemy models
│   └── session.py    # Database session
├── schemas/          # Pydantic schemas
│   ├── market.py     # Market schemas
│   ├── position.py   # Position schemas
│   └── common.py     # Common schemas
├── services/         # Business logic
│   ├── blockchain.py # Blockchain interaction
│   ├── oracle.py     # Pyth oracle integration
│   ├── indexer.py    # Event indexing
│   ├── liquidation.py# Liquidation bot
│   └── funding.py    # Funding rate service
├── utils/            # Utilities
│   └── logging.py    # Logging configuration
└── main.py           # FastAPI application
```

## 🚀 Setup

### 1. Cài đặt dependencies

```bash
# Tạo virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# hoặc
venv\Scripts\activate  # Windows

# Cài đặt packages
pip install -r requirements.txt
```

### 2. Cấu hình môi trường

```bash
# Copy file .env.example
cp .env.example .env

# Chỉnh sửa .env với thông tin của bạn
nano .env
```

Cấu hình quan trọng trong `.env`:
```env
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/derivatives_db

# Blockchain
RPC_URL=https://eth-mainnet.g.alchemy.com/v2/your-api-key
CHAIN_ID=1
CONTRACT_ADDRESS=0x...
START_BLOCK=18000000

# Pyth Oracle
PYTH_HTTP_ENDPOINT=https://hermes.pyth.network
```

### 3. Khởi tạo database

```bash
# Tạo database
createdb derivatives_db

# Database sẽ tự động tạo tables khi chạy ứng dụng
```

## 🏃 Chạy ứng dụng

### Development mode

```bash
# Chạy với auto-reload
python -m app.main

# Hoặc với uvicorn trực tiếp
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production mode

```bash
# Với Gunicorn + Uvicorn workers
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## 📡 API Endpoints

### Health Check
- `GET /api/v1/health` - Health check
- `GET /api/v1/stats` - System statistics

### Markets
- `GET /api/v1/markets` - List markets (paginated)
- `GET /api/v1/markets/{market_id}` - Get market details
- `GET /api/v1/markets/{market_id}/stats` - Market statistics
- `GET /api/v1/markets/{market_id}/funding-history` - Funding rate history

### Positions
- `GET /api/v1/positions` - List positions (filtered, paginated)
- `GET /api/v1/positions/{position_id}` - Get position with PnL
- `GET /api/v1/positions/user/{address}/summary` - User position summary
- `GET /api/v1/positions/liquidation/candidates` - Liquidation candidates

### Oracle
- `GET /api/v1/oracle/price/{price_feed_id}` - Get latest price
- `POST /api/v1/oracle/prices` - Get multiple prices

### Liquidation
- `GET /api/v1/liquidation/status` - Liquidation bot status

### WebSocket (Real-time) ✨ NEW!
- `WS /api/v1/ws/prices/{market_id}` - Real-time price stream
- `WS /api/v1/ws/positions/{user_address}` - Position updates & PnL
- `WS /api/v1/ws/liquidations` - Liquidation alerts
- `WS /api/v1/ws/market-stats/{market_id}` - Market statistics
- `GET /api/v1/ws/stats` - WebSocket connection stats

## 🔧 Background Services

Backend chạy 4 background services:

### 1. Blockchain Indexer
- Sync events từ blockchain
- Index PositionOpened, PositionClosed, PositionLiquidated events
- Update market statistics

### 2. Liquidation Bot
- Monitor open positions
- Calculate health factors
- Tự động liquidate unhealthy positions
- Interval: mỗi 10 giây (configurable)

### 3. Funding Rate Service
- Calculate funding rates dựa trên OI imbalance
- Update mỗi 1 giờ (configurable)
- Record funding rate history

### 4. Event Broadcaster ✨ NEW!
- Broadcast blockchain events qua WebSocket
- Real-time price updates
- Position PnL streaming
- Liquidation warnings

## 🧪 Testing

```bash
# Chạy tests
pytest

# Với coverage
pytest --cov=app tests/
```

## 📊 Monitoring

### Logs
Logs được lưu tại:
- Console (development)
- `logs/app_YYYY-MM-DD.log` (production)

### Metrics
- Prometheus metrics available at `:9090` (nếu enabled)

## 🔒 Security

- Không lưu private keys trong code
- Sử dụng environment variables cho sensitive data
- Rate limiting (implement nếu cần)
- Input validation với Pydantic

## 📝 Database Models

### Markets
- market_id, symbol, tokens
- Leverage, margin parameters
- Open interest tracking
- Funding rate state

### Positions
- position_id, user_address
- Size, collateral, leverage
- Entry/exit prices
- PnL tracking
- Status (open/closed/liquidated)

### Funding Rates
- Historical funding rates
- OI snapshots

### Liquidations
- Liquidation event records

## 🛠️ Development

### Code Style
```bash
# Format code
black app/

# Sort imports
isort app/

# Type checking
mypy app/
```

### Database Migrations
```bash
# Tạo migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```

## 📚 Tài liệu tham khảo

- [WEBSOCKET_DOCS.md](WEBSOCKET_DOCS.md) - WebSocket real-time API ✨
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Web3.py Documentation](https://web3py.readthedocs.io/)
- [Pyth Network Documentation](https://docs.pyth.network/)

## ⚠️ Lưu ý

1. **Oracle Price Freshness**: Giá từ Pyth phải fresh (<10s) mới được sử dụng
2. **Gas Price**: Liquidation bot kiểm tra gas price trước khi gửi tx
3. **Health Factor**: Position với health factor ≤ 1.0 sẽ bị liquidate
4. **Funding Payments**: Được tính vào accumulated_funding của position

## 🤝 Contributing

1. Fork repository
2. Tạo feature branch
3. Commit changes
4. Push to branch
5. Tạo Pull Request

## 📄 License

MIT License

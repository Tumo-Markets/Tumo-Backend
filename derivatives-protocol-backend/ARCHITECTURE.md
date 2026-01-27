# Architecture Overview

## System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                          Frontend (Web/App)                      │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST API
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Backend (Python/FastAPI)                    │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   REST API   │  │  Indexer     │  │ Liquidation  │          │
│  │   Endpoints  │  │   Service    │  │     Bot      │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Funding    │  │   Oracle     │  │  Blockchain  │          │
│  │   Service    │  │   Service    │  │   Service    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                                                                  │
│                    ┌──────────────┐                             │
│                    │  PostgreSQL  │                             │
│                    │   Database   │                             │
│                    └──────────────┘                             │
└────────┬──────────────────────────────────────┬─────────────────┘
         │                                      │
         │ Read Events                          │ Get Prices
         ▼                                      ▼
┌─────────────────────┐              ┌──────────────────────┐
│  Smart Contract     │              │  Pyth Oracle         │
│  (EVM/Move/Rust)    │              │  Network             │
│                     │              │                      │
│  - Markets          │              │  - Price Feeds       │
│  - Positions        │              │  - VAA Data          │
│  - Liquidations     │              │  - Confidence        │
└─────────────────────┘              └──────────────────────┘
```

## Data Flow

### 1. Opening a Position (User-Initiated)

```
User → Frontend → Pyth Oracle (get price)
                ↓
            Build Tx with Price Data
                ↓
            User Signs Tx
                ↓
        Smart Contract (verify & execute)
                ↓
        Emit PositionOpened Event
                ↓
        Backend Indexer picks up event
                ↓
        Store in Database
```

### 2. Position Monitoring (Backend)

```
Every 10 seconds:
    Liquidation Bot
        ↓
    Query Open Positions from DB
        ↓
    Fetch Current Prices from Pyth
        ↓
    Calculate Health Factors
        ↓
    Identify Liquidation Candidates
        ↓
    For each candidate:
        Get fresh Price Update Data
        ↓
        Build Liquidation Tx
        ↓
        Send to Smart Contract
```

### 3. Funding Rate Update

```
Every 1 hour:
    Funding Service
        ↓
    Calculate Funding Rate
        (based on Long OI vs Short OI)
        ↓
    Update Market State in DB
        ↓
    Record Funding History
        ↓
    (Optional) Trigger On-Chain Update
```

### 4. Event Indexing

```
Every 5 seconds:
    Indexer checks last synced block
        ↓
    Fetch new blocks from blockchain
        ↓
    Extract relevant events:
        - PositionOpened
        - PositionClosed
        - PositionLiquidated
        ↓
    Update Database:
        - Create/Update Positions
        - Update Market Stats
        - Record Liquidations
        ↓
    Update last synced block
```

## Key Design Decisions

### 1. No On-Chain Price Updates
- **Rationale**: Gas efficiency, permissionless trading
- **Implementation**: Price data sent with each transaction
- **Benefits**: Lower gas costs, no price update MEV

### 2. Backend as Indexer, Not Authority
- **Rationale**: Permissionless, no single point of failure
- **Implementation**: Anyone can run indexer, liquidate, etc.
- **Benefits**: Decentralization, censorship resistance

### 3. Pydantic for Data Validation
- **Rationale**: Type safety, automatic validation
- **Implementation**: All request/response uses Pydantic models
- **Benefits**: Runtime type checking, clear schemas

### 4. Async Everything
- **Rationale**: Handle many concurrent operations
- **Implementation**: async/await throughout
- **Benefits**: Better performance, scalability

## Database Schema

### Markets Table
```sql
markets:
  - id (PK)
  - market_id (unique)
  - symbol
  - base_token, quote_token
  - pyth_price_id
  - max_leverage
  - maintenance_margin_rate
  - liquidation_fee_rate
  - total_long_positions
  - total_short_positions
  - current_funding_rate
  - last_funding_update
  - created_at, updated_at
```

### Positions Table
```sql
positions:
  - id (PK)
  - position_id (unique)
  - market_id (FK)
  - user_address
  - side (long/short)
  - size, collateral, leverage
  - entry_price, exit_price
  - realized_pnl
  - accumulated_funding
  - status (open/closed/liquidated)
  - block_number
  - transaction_hash
  - created_at, updated_at, closed_at
```

### Funding Rates Table
```sql
funding_rates:
  - id (PK)
  - market_id (FK)
  - funding_rate
  - long_oi, short_oi
  - timestamp
```

### Liquidations Table
```sql
liquidations:
  - id (PK)
  - position_id
  - market_id
  - user_address
  - liquidator_address
  - liquidation_price
  - liquidation_fee
  - transaction_hash
  - block_number
  - timestamp
```

## Background Services

### Indexer
- **Purpose**: Sync blockchain events to database
- **Frequency**: Every 5 seconds
- **Critical**: Yes (data source for all other services)

### Liquidation Bot
- **Purpose**: Monitor and liquidate unhealthy positions
- **Frequency**: Every 10 seconds
- **Critical**: Important but not required (anyone can liquidate)

### Funding Service
- **Purpose**: Calculate and update funding rates
- **Frequency**: Every 1 hour (configurable)
- **Critical**: Important for market balance

## Performance Considerations

### Database Indexing
- Index on: user_address, market_id, status, position_id
- Composite indexes for common queries

### Caching
- Price data cached for 10 seconds
- Market data can be cached longer
- Position data should be fresh

### Batch Operations
- Indexer processes blocks in batches (1000)
- Multi-price fetching in single API call
- Bulk database operations where possible

### Rate Limiting (Future)
- Per-endpoint limits
- Per-user limits
- Protect against abuse

## Security

### Smart Contract Interaction
- No private keys in backend (read-only for indexing)
- Liquidation bot can have its own key
- All transactions verified on-chain

### Input Validation
- All inputs validated via Pydantic
- SQL injection prevented by SQLAlchemy
- No direct user SQL queries

### Error Handling
- Comprehensive try/catch blocks
- Detailed logging
- User-friendly error messages
- No sensitive data in errors

## Monitoring & Observability

### Logging
- Structured logging with Loguru
- Different log levels (DEBUG, INFO, ERROR)
- Log rotation and compression

### Metrics (Future)
- Prometheus metrics
- Request latency
- Position counts
- Liquidation stats

### Alerts (Future)
- Database connection failures
- Blockchain sync delays
- Oracle unavailability
- High liquidation volumes

## Scalability

### Horizontal Scaling
- Stateless API servers (can run multiple instances)
- Load balancer in front
- Shared database

### Database Scaling
- Read replicas for queries
- Master for writes
- Connection pooling

### Background Services
- Only one instance of indexer needed
- Can run multiple liquidation bots
- Funding service can be distributed

## Future Enhancements

1. **WebSocket Support**
   - Real-time price feeds
   - Position updates
   - Event streaming

2. **Advanced Features**
   - Stop-loss/Take-profit orders
   - Limit orders
   - Multi-collateral support

3. **Analytics**
   - Trading volume charts
   - PnL analytics
   - User statistics

4. **Optimization**
   - GraphQL API
   - Event sourcing
   - CQRS pattern

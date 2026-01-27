# Project Structure

```
derivatives-protocol-backend/
│
├── app/                          # Main application package
│   ├── __init__.py
│   │
│   ├── main.py                   # FastAPI application entry point
│   │
│   ├── api/                      # API endpoints (routes)
│   │   ├── __init__.py
│   │   ├── markets.py            # Market endpoints
│   │   ├── positions.py          # Position endpoints
│   │   └── system.py             # System, oracle, liquidation endpoints
│   │
│   ├── core/                     # Core configuration
│   │   ├── __init__.py
│   │   └── config.py             # Settings with Pydantic
│   │
│   ├── db/                       # Database layer
│   │   ├── __init__.py
│   │   ├── models.py             # SQLAlchemy models
│   │   └── session.py            # Database session management
│   │
│   ├── schemas/                  # Pydantic schemas (request/response)
│   │   ├── __init__.py
│   │   ├── common.py             # Common schemas (responses, errors)
│   │   ├── market.py             # Market schemas
│   │   └── position.py           # Position schemas
│   │
│   ├── services/                 # Business logic services
│   │   ├── __init__.py
│   │   ├── blockchain.py         # Blockchain interaction
│   │   ├── funding.py            # Funding rate service
│   │   ├── indexer.py            # Event indexing service
│   │   ├── liquidation.py        # Liquidation bot
│   │   └── oracle.py             # Pyth oracle integration
│   │
│   └── utils/                    # Utility functions
│       ├── __init__.py
│       └── logging.py            # Logging configuration
│
├── scripts/                      # Utility scripts
│   ├── seed_db.py                # Seed database with sample markets
│   └── test_api.py               # API testing examples
│
├── tests/                        # Test suite
│   ├── __init__.py
│   ├── test_basic.py             # Basic tests
│   ├── unit/                     # Unit tests
│   └── integration/              # Integration tests
│
├── migrations/                   # Alembic migrations (to be created)
│
├── logs/                         # Application logs
│
├── .env.example                  # Environment variables template
├── .env                          # Environment variables (gitignored)
├── .gitignore                    # Git ignore rules
│
├── requirements.txt              # Python dependencies
├── Dockerfile                    # Docker container definition
├── docker-compose.yml            # Docker Compose configuration
│
├── quickstart.sh                 # Quick start setup script
│
├── README.md                     # Main documentation
├── API_DOCS.md                   # API documentation
├── ARCHITECTURE.md               # Architecture documentation
└── PROJECT_STRUCTURE.md          # This file
```

## File Descriptions

### Core Application Files

**app/main.py**
- FastAPI application setup
- Lifespan management (startup/shutdown)
- Router inclusion
- Middleware configuration

**app/core/config.py**
- Pydantic Settings for configuration
- Environment variable loading
- Validation of settings

### API Layer

**app/api/markets.py**
- Market listing and filtering
- Market statistics
- Funding rate history

**app/api/positions.py**
- Position queries with filters
- Position details with PnL calculations
- User position summaries
- Liquidation candidates

**app/api/system.py**
- Health checks
- System statistics
- Oracle endpoints
- Liquidation bot status

### Database Layer

**app/db/models.py**
- SQLAlchemy ORM models:
  - MarketModel
  - PositionModel
  - FundingRateModel
  - LiquidationModel
  - PriceHistoryModel
  - BlockSyncModel

**app/db/session.py**
- Async database session factory
- Connection management
- Database initialization

### Schema Layer

**app/schemas/common.py**
- PriceData, PriceUpdate
- FundingRate, FundingRateHistory
- ResponseBase, PaginatedResponse
- ErrorResponse, HealthCheck
- SystemStats

**app/schemas/market.py**
- Market, MarketCreate, MarketUpdate
- MarketStatus enum
- MarketStats

**app/schemas/position.py**
- Position, PositionCreate, PositionUpdate
- PositionWithPnL, PositionSummary
- PositionSide, PositionStatus enums
- LiquidationCandidate

### Service Layer

**app/services/blockchain.py**
- Web3 integration
- Smart contract interaction
- Health factor calculations
- Liquidation price calculations

**app/services/oracle.py**
- Pyth Network integration
- Price fetching (single & batch)
- Price update data (VAA)
- Price validation

**app/services/indexer.py**
- Blockchain event syncing
- Event processing:
  - PositionOpened
  - PositionClosed
  - PositionLiquidated
- Market statistics updates

**app/services/liquidation.py**
- Position monitoring
- Health factor calculations
- Liquidation candidate detection
- Automated liquidation execution

**app/services/funding.py**
- Funding rate calculation
- Funding rate updates
- History tracking
- Funding payment calculations

### Configuration & Setup

**.env.example**
- Template for environment variables
- All required configuration options
- Documentation of each variable

**requirements.txt**
- All Python dependencies
- Pinned versions for reproducibility

**Dockerfile**
- Container image definition
- Multi-stage build (optional)
- Health checks

**docker-compose.yml**
- PostgreSQL service
- Redis service
- Backend service
- Volume management

### Scripts

**scripts/seed_db.py**
- Populates database with sample markets
- Uses real Pyth price feed IDs
- Creates diverse market types

**scripts/test_api.py**
- Example API calls
- Demonstrates all endpoints
- Shows response formats

**quickstart.sh**
- Automated setup
- Virtual environment creation
- Dependency installation
- Initial configuration

### Documentation

**README.md**
- Project overview
- Setup instructions
- Running the application
- API endpoint summary

**API_DOCS.md**
- Detailed API documentation
- Request/response examples
- Error handling
- Rate limiting

**ARCHITECTURE.md**
- System architecture
- Data flows
- Design decisions
- Scalability considerations

**PROJECT_STRUCTURE.md**
- This file
- Directory structure
- File purposes
- Navigation guide

## Key Design Patterns

### Repository Pattern
- Services abstract database operations
- Clean separation of concerns

### Service Layer Pattern
- Business logic in services
- Reusable across endpoints

### DTO Pattern
- Pydantic schemas as DTOs
- Request/response validation

### Dependency Injection
- FastAPI's Depends for DB sessions
- Clean, testable code

### Background Tasks
- Async services for indexing, liquidation, funding
- Non-blocking operations

## Development Workflow

1. **Setup**: Run `./quickstart.sh`
2. **Configure**: Edit `.env` file
3. **Database**: Start PostgreSQL
4. **Seed**: Run `python scripts/seed_db.py`
5. **Develop**: Edit files in `app/`
6. **Test**: Run `pytest`
7. **Run**: `python -m app.main`

## Production Deployment

1. **Environment**: Set production env vars
2. **Database**: Use managed PostgreSQL
3. **Container**: Build Docker image
4. **Orchestration**: Deploy with K8s/ECS
5. **Monitoring**: Setup logging & metrics
6. **Scaling**: Multiple API replicas

## Testing Strategy

- **Unit Tests**: Test individual functions
- **Integration Tests**: Test API endpoints
- **E2E Tests**: Test complete workflows
- **Load Tests**: Test performance

## Maintenance

- **Logs**: Check `logs/` directory
- **Database**: Regular backups
- **Updates**: Monitor dependencies
- **Monitoring**: Track metrics

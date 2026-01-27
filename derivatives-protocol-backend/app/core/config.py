from decimal import Decimal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings.
    All configuration is loaded strictly from environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ======================
    # Application
    # ======================
    app_name: str = Field(default="Derivatives Protocol Backend", alias="APP_NAME")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    env: str = Field(default="development", alias="ENV")
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # ======================
    # API
    # ======================
    api_prefix: str = Field(default="/api/v1", alias="API_PREFIX")

    # ======================
    # Database (REQUIRED)
    # ======================
    database_url: str = Field(..., alias="DATABASE_URL")
    database_pool_size: int = Field(default=20, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=10, alias="DATABASE_MAX_OVERFLOW")

    # ======================
    # Redis
    # ======================
    redis_url: str = Field(
        default="redis://redis:6379/0",
        alias="REDIS_URL",
    )
    redis_cache_ttl: int = Field(default=300, alias="REDIS_CACHE_TTL")

    # ======================
    # Blockchain (REQUIRED)
    # ======================
    rpc_url: str = Field(..., alias="RPC_URL")
    chain_id: int = Field(..., alias="CHAIN_ID")
    contract_address: str = Field(..., alias="CONTRACT_ADDRESS")
    start_block: int = Field(default=0, alias="START_BLOCK")

    # ======================
    # Pyth Oracle
    # ======================
    pyth_network: str = Field(default="mainnet", alias="PYTH_NETWORK")
    pyth_ws_endpoint: str = Field(
        default="wss://hermes.pyth.network/ws",
        alias="PYTH_WS_ENDPOINT",
    )
    pyth_http_endpoint: str = Field(
        default="https://hermes.pyth.network",
        alias="PYTH_HTTP_ENDPOINT",
    )

    # ======================
    # Liquidation
    # ======================
    liquidation_check_interval: int = Field(
        default=10, alias="LIQUIDATION_CHECK_INTERVAL"
    )
    liquidation_gas_limit: int = Field(default=500_000, alias="LIQUIDATION_GAS_LIMIT")
    liquidation_max_gas_price: int = Field(
        default=100, alias="LIQUIDATION_MAX_GAS_PRICE"
    )
    min_health_factor: Decimal = Field(
        default=Decimal("1.0"), alias="MIN_HEALTH_FACTOR"
    )
    liquidation_reward_rate: Decimal = Field(
        default=Decimal("0.05"),
        alias="LIQUIDATION_REWARD_RATE",
    )

    # ======================
    # Funding Rate
    # ======================
    funding_interval: int = Field(default=3600, alias="FUNDING_INTERVAL")
    funding_rate_cap: Decimal = Field(
        default=Decimal("0.001"), alias="FUNDING_RATE_CAP"
    )

    # ======================
    # Security (REQUIRED)
    # ======================
    secret_key: str = Field(..., alias="SECRET_KEY")
    algorithm: str = Field(default="HS256", alias="ALGORITHM")
    access_token_expire_minutes: int = Field(
        default=30,
        alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )

    # ======================
    # Monitoring
    # ======================
    enable_metrics: bool = Field(default=True, alias="ENABLE_METRICS")
    metrics_port: int = Field(default=9090, alias="METRICS_PORT")

    # ======================
    # Validators
    # ======================
    @field_validator(
        "min_health_factor",
        "liquidation_reward_rate",
        "funding_rate_cap",
        mode="before",
    )
    @classmethod
    def to_decimal(cls, v):
        if isinstance(v, (int, float, str)):
            return Decimal(str(v))
        return v

    # ======================
    # Helpers
    # ======================
    @property
    def is_production(self) -> bool:
        return self.env.lower() == "production"

    @property
    def database_url_sync(self) -> str:
        return self.database_url.replace("+asyncpg", "")


settings = Settings()

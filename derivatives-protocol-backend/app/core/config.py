"""
Application Settings

Supports both EVM and Onechain (Move-based) blockchains.
"""

from decimal import Decimal
from typing import Literal

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
    # contract Service
    # ======================

    contract_service_url: str = Field(
        default="http://localhost:3001",
        alias="CONTRACT_SERVICE_URL",
    )
    contract_service_api_key: str = Field(
        default="",
        alias="CONTRACT_SERVICE_API_KEY",
    )

    # ======================
    # Blockchain Type Selection
    # ======================
    blockchain_type: Literal["evm", "onechain"] = Field(
        default="onechain",
        alias="BLOCKCHAIN_TYPE",
        description="Blockchain type: 'evm' for Ethereum-compatible chains, 'onechain' for Move-based chains",
    )

    # ======================
    # EVM Blockchain (for Ethereum, BSC, Polygon, etc.)
    # ======================
    # Only required if blockchain_type = "evm"
    evm_rpc_url: str = Field(default="http://localhost:8545", alias="EVM_RPC_URL")
    evm_chain_id: int = Field(default=1, alias="EVM_CHAIN_ID")
    evm_contract_address: str = Field(default="", alias="EVM_CONTRACT_ADDRESS")
    evm_start_block: int = Field(default=0, alias="EVM_START_BLOCK")

    # ======================
    # Onechain (Move-based blockchain)
    # ======================
    # Only required if blockchain_type = "onechain"
    onechain_network: Literal["local", "testnet", "mainnet"] = Field(
        default="testnet",
        alias="ONECHAIN_NETWORK",
        description="Onechain network selection",
    )

    # RPC URLs for each Onechain network
    onechain_rpc_local: str = Field(
        default="http://127.0.0.1:9000",
        alias="ONECHAIN_RPC_LOCAL",
    )
    onechain_rpc_testnet: str = Field(
        default="https://rpc-testnet.onelabs.cc:443",
        alias="ONECHAIN_RPC_TESTNET",
    )
    onechain_rpc_mainnet: str = Field(
        default="https://rpc.mainnet.onelabs.cc:443",
        alias="ONECHAIN_RPC_MAINNET",
    )

    # Onechain-specific settings
    onechain_chain_id: int = Field(
        default=1,
        alias="ONECHAIN_CHAIN_ID",
    )
    onechain_package_id: str = Field(
        default="0x31b6ea6f6c2e1727d590fba2b6ccd93dd0785f238fd91cb16030d468a466bc6e",
        alias="ONECHAIN_PACKAGE_ID",
        description="Deployed Move package ID",
    )
    onechain_start_checkpoint: int = Field(
        default=0,
        alias="ONECHAIN_START_CHECKPOINT",
    )

    # ======================
    # Backward Compatibility (Legacy)
    # ======================
    # These are kept for backward compatibility
    # They map to EVM settings when blockchain_type = "evm"
    rpc_url: str = Field(default="", alias="RPC_URL")
    chain_id: int = Field(default=0, alias="CHAIN_ID")
    contract_address: str = Field(default="", alias="CONTRACT_ADDRESS")
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
    # Properties - Blockchain Configuration
    # ======================

    @property
    def is_evm(self) -> bool:
        """Check if using EVM blockchain."""
        return self.blockchain_type == "evm"

    @property
    def is_onechain(self) -> bool:
        """Check if using Onechain blockchain."""
        return self.blockchain_type == "onechain"

    @property
    def onechain_rpc_url(self) -> str:
        """Get Onechain RPC URL based on selected network."""
        if self.onechain_network == "local":
            return self.onechain_rpc_local
        elif self.onechain_network == "testnet":
            return self.onechain_rpc_testnet
        else:
            return self.onechain_rpc_mainnet

    @property
    def active_rpc_url(self) -> str:
        """
        Get active RPC URL based on blockchain type.

        Returns:
            RPC URL for the active blockchain
        """
        if self.is_onechain:
            return self.onechain_rpc_url
        else:
            # EVM: Use legacy rpc_url if set, otherwise use evm_rpc_url
            return self.rpc_url or self.evm_rpc_url

    @property
    def active_chain_id(self) -> int | str:
        """
        Get active chain ID based on blockchain type.

        Returns:
            Chain ID (int for EVM, str for Onechain)
        """
        if self.is_onechain:
            return self.onechain_chain_id
        else:
            # EVM: Use legacy chain_id if set, otherwise use evm_chain_id
            return self.chain_id or self.evm_chain_id

    @property
    def active_start_block(self) -> int:
        """
        Get starting block/checkpoint based on blockchain type.

        Returns:
            Starting block number (EVM) or checkpoint (Onechain)
        """
        if self.is_onechain:
            return self.onechain_start_checkpoint
        else:
            # EVM: Use legacy start_block if set, otherwise use evm_start_block
            return self.start_block or self.evm_start_block

    # ======================
    # Helpers
    # ======================

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.env.lower() == "production"

    @property
    def database_url_sync(self) -> str:
        """Get synchronous database URL (for Alembic, etc.)."""
        return self.database_url.replace("+asyncpg", "")


settings = Settings()

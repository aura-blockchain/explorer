"""
AURA Block Explorer Configuration
Production-ready configuration for AURA blockchain explorer
"""

import os
from typing import Dict, Any


class Config:
    """Base configuration"""

    # AURA Node Configuration
    # -------------------------------------------------------------------------
    # PORT SENTINEL REQUIRED FOR PRODUCTION: These are development fallback
    # defaults only. For production deployments, ports MUST be allocated via
    # Port Sentinel to prevent conflicts:
    #   python scripts/port_sentinel.py allocate explorer_rpc --project aura
    #   python scripts/port_sentinel.py allocate explorer_api --project aura
    #   python scripts/port_sentinel.py allocate explorer_grpc --project aura
    # Then set NODE_RPC_URL, NODE_API_URL, NODE_GRPC_URL environment variables.
    # -------------------------------------------------------------------------
    NODE_RPC_URL = os.getenv(
        "NODE_RPC_URL", "http://localhost:26657"
    )  # DEV ONLY default
    NODE_API_URL = os.getenv(
        "NODE_API_URL", "http://localhost:1317"
    )  # DEV ONLY default
    NODE_GRPC_URL = os.getenv("NODE_GRPC_URL", "localhost:9090")  # DEV ONLY default

    # AURA Chain Configuration
    CHAIN_ID = os.getenv("CHAIN_ID", "aura-mvp-1")
    DENOM = os.getenv("DENOM", "uaura")
    DENOM_DECIMALS = int(os.getenv("DENOM_DECIMALS", "6"))

    # Explorer Configuration
    EXPLORER_PORT = int(os.getenv("EXPLORER_PORT", "8082"))
    EXPLORER_HOST = os.getenv("EXPLORER_HOST", "0.0.0.0")
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"

    # Database Configuration
    DB_PATH = os.getenv("EXPLORER_DB_PATH", "./explorer.db")

    # Cache Configuration
    CACHE_TTL_SHORT = int(os.getenv("CACHE_TTL_SHORT", "60"))  # 1 minute
    CACHE_TTL_MEDIUM = int(os.getenv("CACHE_TTL_MEDIUM", "300"))  # 5 minutes
    CACHE_TTL_LONG = int(os.getenv("CACHE_TTL_LONG", "600"))  # 10 minutes

    # API Rate Limiting
    RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

    # CORS Configuration
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

    # Logging Configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # WebSocket Configuration
    WS_HEARTBEAT_INTERVAL = int(os.getenv("WS_HEARTBEAT_INTERVAL", "30"))
    WS_MAX_CONNECTIONS = int(os.getenv("WS_MAX_CONNECTIONS", "100"))

    # Analytics Configuration
    ANALYTICS_ENABLED = os.getenv("ANALYTICS_ENABLED", "true").lower() == "true"
    ANALYTICS_RETENTION_DAYS = int(os.getenv("ANALYTICS_RETENTION_DAYS", "30"))

    # Rich List Configuration
    RICHLIST_MAX_SIZE = int(os.getenv("RICHLIST_MAX_SIZE", "1000"))
    RICHLIST_CACHE_TTL = int(os.getenv("RICHLIST_CACHE_TTL", "600"))

    # Search Configuration
    SEARCH_HISTORY_SIZE = int(os.getenv("SEARCH_HISTORY_SIZE", "100"))
    AUTOCOMPLETE_LIMIT = int(os.getenv("AUTOCOMPLETE_LIMIT", "10"))

    # Export Configuration
    EXPORT_MAX_TRANSACTIONS = int(os.getenv("EXPORT_MAX_TRANSACTIONS", "10000"))

    # Security Configuration
    ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")  # Set in production!
    REQUIRE_API_KEY = os.getenv("REQUIRE_API_KEY", "false").lower() == "true"

    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            key: value
            for key, value in cls.__dict__.items()
            if not key.startswith("_") and not callable(value)
        }

    @classmethod
    def validate(cls) -> None:
        """Validate configuration"""
        errors = []

        if not cls.NODE_RPC_URL:
            errors.append("NODE_RPC_URL is required")

        if not cls.CHAIN_ID:
            errors.append("CHAIN_ID is required")

        if cls.REQUIRE_API_KEY and not cls.ADMIN_API_KEY:
            errors.append("ADMIN_API_KEY is required when REQUIRE_API_KEY is enabled")

        if cls.EXPLORER_PORT < 1 or cls.EXPLORER_PORT > 65535:
            errors.append("EXPLORER_PORT must be between 1 and 65535")

        if errors:
            raise ValueError(f"Configuration validation failed: {', '.join(errors)}")


class DevelopmentConfig(Config):
    """Development configuration"""

    DEBUG = True
    DB_PATH = ":memory:"
    LOG_LEVEL = "DEBUG"


class ProductionConfig(Config):
    """Production configuration"""

    DEBUG = False
    REQUIRE_API_KEY = True
    RATE_LIMIT_ENABLED = True
    LOG_LEVEL = "WARNING"


class TestConfig(Config):
    """Test configuration"""

    DB_PATH = ":memory:"
    NODE_RPC_URL = "http://localhost:26657"
    CHAIN_ID = "aura-testnet-1"
    CACHE_TTL_SHORT = 1
    CACHE_TTL_MEDIUM = 1
    CACHE_TTL_LONG = 1


# Environment-based configuration selection
ENV_CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "test": TestConfig,
}


def get_config() -> Config:
    """Get configuration based on environment"""
    env = os.getenv("EXPLORER_ENV", "development")
    config_class = ENV_CONFIGS.get(env, DevelopmentConfig)
    config_class.validate()
    return config_class


# Export current configuration
config = get_config()

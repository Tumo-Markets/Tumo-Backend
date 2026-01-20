import sys
from loguru import logger
from app.core.config import settings


def setup_logging():
    """Configure logging with loguru."""
    
    # Remove default handler
    logger.remove()
    
    # Add custom handler with formatting
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    # Console handler
    logger.add(
        sys.stdout,
        format=log_format,
        level=settings.log_level,
        colorize=True,
    )
    
    # File handler for production
    if settings.is_production:
        logger.add(
            "logs/app_{time:YYYY-MM-DD}.log",
            format=log_format,
            level="INFO",
            rotation="00:00",
            retention="30 days",
            compression="zip",
        )
    
    logger.info(f"Logging configured at {settings.log_level} level")


# Configure logging on import
setup_logging()

import sys
from loguru import logger
from app.core.config import settings

logger.remove()

logger.add(
    sys.stdout,
    level=settings.LOG_LEVEL,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
           "<level>{level:<8}</level> | "
           "{message}",
)

logger.add(
    "logs/bot.log",
    rotation="10 MB",
    retention="30 days",
    level=settings.LOG_LEVEL,
    enqueue=True,
)

__all__ = ["logger"]

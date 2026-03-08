"""
Redis client singleton.

Provides async Redis connection with graceful fallback
when Redis is unavailable.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_redis_client = None


async def init_redis(url: str):
    """
    Initialize Redis connection.

    Args:
        url: Redis URL (e.g. redis://redis:6379/0)

    Returns:
        Redis client instance or None if connection fails.
    """
    global _redis_client
    try:
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(url, decode_responses=True)
        await _redis_client.ping()
        logger.info(f"Redis connected: {url}")
        return _redis_client
    except ImportError:
        logger.warning("redis package not installed, using in-memory fallback")
        return None
    except Exception as e:
        logger.warning(f"Redis connection failed ({e}), using in-memory fallback")
        _redis_client = None
        return None


async def close_redis():
    """Close Redis connection."""
    global _redis_client
    if _redis_client:
        try:
            await _redis_client.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.warning(f"Error closing Redis: {e}")
        finally:
            _redis_client = None


def get_redis():
    """
    Get current Redis client.

    Returns:
        Redis client or None if not connected.
    """
    return _redis_client
